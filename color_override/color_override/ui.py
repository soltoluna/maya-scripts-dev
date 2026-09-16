# -*- coding: utf-8 -*-
"""Color Override — `maya.cmds` による UI と、シェーダー割り当ての操作。

ここは「値を集める → `core` に渡す → 結果を `cmds` に流す」に保つ。
色の作り方・16 進の解釈・ノード名の組み立て・セットの畳み方・控えの
読み書きは、すべて `core.py`（Maya 非依存）にある。

## オーバーライドの持ち方

対象 1 つにつき `surfaceShader` + `shadingEngine` を 1 組作り、**シェーダー側に
復元用の情報を文字列属性で書き込む**。 セッション中の Python 辞書に持たないのは、
シーンを保存して開き直したあとも Restore を効かせるため。

    ntk_color_override_<対象名>_SHD   surfaceShader（outColor が表示色）
      .ntkColorOverrideOriginal       元の SG（旧形式・管理対象の目印）
      .ntkColorOverrideTarget         掛けた時点の対象ノード名（表示用）
      .ntkColorOverrideMembers        掛けた相手（シェイプ）
      .ntkColorOverrideOriginals      **それぞれの戻し先** ← 復元の情報源
      .ntkColorOverrideFaces          **フェース単位の戻し先**（JSON・下記）
      .ntkColorOverrideSet            所属するセット名 ← 一覧を畳む単位
    ntk_color_override_<対象名>_SG    上をつないだ shadingEngine

**戻し先はメンバーごとに持つ。** グループノードに掛けると中のシェイプは
別々のマテリアルを持ちうるので、1 件につき 1 つでは戻せない。

**さらにシェイプ 1 つの中がフェース単位で分かれていることもある。**
色を掛けるときはシェイプ全体を 1 色で塗る（そこは変えない）が、
**掛ける前にフェースの塊と戻し先を控えておき、Restore と Hide で
元の分割ごと戻す**。 控えられなかったシェイプには**掛けない**
（静かに割り当てを失うより、掛からないほうがよい）。

`surfaceShader` を使うのはライティングに影響されないフラットな色になるため。
陰影が乗らないぶん、同系色のオブジェクトの境界（＝貫通している箇所）が
輪郭としてはっきり出る。

**管理対象の判別は名前ではなく `.ntkColorOverrideOriginal` 属性の有無で行う。**
ユーザーがノードをリネームしても追跡できる。

## 3 つの状態

    Hide / Show    対象を元の SG に戻すだけ。 ノードは残すので掛け直せる
    Restore        元の SG に戻し、ノードごと削除する（シーンがきれいになる）
    控え (JSON)    Restore で消える前に、シーンの隣へ書き出しておく

**Restore はシーンからノードを消す。** それがこのツールの方針
（確認が終わったらシーンに何も残さない）だが、そのままでは同じ色分けに
二度と戻れない。 だから **Restore の直前に必ず控えを書き出し、一覧には
「まだ掛かっていないセット」として出し続ける**。 いつでも Apply で戻せる。

**解除中かどうかのフラグは持たない。** shadingEngine にメンバーが居るかどうかが
そのまま状態なので、Maya 側で手作業に割り当てを変えられても表示と食い違わない。
"""

from __future__ import annotations

import os

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


# Maya の optionVar / scriptJob / ウィンドウ名はフラットな 1 つの名前空間を
# 共有する。 接頭辞の無いキーは他人のツールと後勝ちで静かに衝突するので、
# 直書きせず `_NS` から組み立てる（CLAUDE.md「ルール」）
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)            # ntk_color_override

# ウィンドウ名は `<NAMESPACE>_<モジュール名>Win` 固定。 ハブ install.py の
# `_close_existing_window()` が同じ規則で古いウィンドウを探す
WINDOW = _NS + "Win"

_OPTVAR_LAST_COLOR = _NS + "_last_color"         # ntk_color_override_last_color

# **いま見ている控えのパス。** 既定はシーンの隣だが、別の控え（前のシーンの
# もの・共有フォルダに置いたもの・未保存シーンで自分で選んだ場所）を開けるよう
# にしてある。 覚えずに捨てると、書き出した控えを二度と読めず復元できない
_OPTVAR_BACKUP_PATH = _NS + "_backup_path"

# シーンに作るノードにも名前空間を付ける。 実機のシーンには他の人が作った
# ノードも同居するため
_NODE_PREFIX = _NS

# オーバーライド用シェーダーに書き込む印。 この属性の有無が管理対象の判定そのもの
_ATTR_ORIGINAL = NAMESPACE + "ColorOverrideOriginal"
_ATTR_TARGET = NAMESPACE + "ColorOverrideTarget"

# 一時解除（peek）中は shadingEngine が空になり、何に掛かっていたのかが
# シーンから読めなくなる。 掛けた相手をシェーダー側に控えておく
_ATTR_MEMBERS = NAMESPACE + "ColorOverrideMembers"

# メンバーと 1 対 1 で対応する戻し先。 グループに掛けると中のシェイプは
# 別々のマテリアルを持ちうるので、_ATTR_ORIGINAL の 1 つでは戻せない
_ATTR_ORIGINALS = NAMESPACE + "ColorOverrideOriginals"

# フェース単位で分かれていたシェイプの戻し先（JSON）。 `;` 区切りでは
# 入れ子（SG ごとのフェースの塊）を表せないのでここだけ形が違う
_ATTR_FACES = NAMESPACE + "ColorOverrideFaces"

# シェイプから SG への割り当ては instObjGroups を経由する。 フェース単位なら
# さらに objectGroups[n] が挟まる。 **接続プラグの形が判別そのもの**で、
# SG のメンバーを引かずに済むのはこのおかげ
_MEMBER_PLUG = ".instObjGroups"
_FACE_PLUG = ".objectGroups["

# 所属セット名。 一覧を畳む単位で、これが無い記録（v0.3.0 以前）は Unnamed へ
_ATTR_SET = NAMESPACE + "ColorOverrideSet"

# シェーダーを持たないオブジェクトを戻すときの行き先（Maya の既定）
_DEFAULT_SG = "initialShadingGroup"

# 控えの置き場所。 シーンと同じ場所・同じ名前にするので、どのシーンのものか
# 一目で分かり、要らなくなったら消せる
_BACKUP_SUFFIX = ".color_override.json"

# 1 行に並べる色見本の上限。 これを超えたら `+N` にする
_SWATCH_LIMIT = 8

# 「全メッシュ」でこの数を超えたら一度確認する。 1 オブジェクト = 2 ノードなので、
# 大きいシーンで何も聞かずに走ると戻すのも一苦労になる
_BULK_CONFIRM_THRESHOLD = 50

_DEFAULT_COLOR = core.color_at(0)

_CTRL = {}        # コントロール名の控え。 show() のたびに作り直す


# --------------------------------------------------------------------------- #
# シーンの読み取り
# --------------------------------------------------------------------------- #

def _shapes_of(node):
    """色を割り当てる相手（シェイプ）をフルパスで返す。

    **`listRelatives(shapes=True)` では足りない。** グループノードの子は
    トランスフォームなので直下にシェイプが無く、空が返る。 v0.2.0 までは
    その場合にノード自身へフォールバックしていたため、**グループに掛けると
    「元の shadingEngine が見つからない」→ `initialShadingGroup` を元として
    記録**し、Restore で中身が全部グレーになった（v0.3.0 で修正）。

    `ls(dag=True, shapes=True)` は部分木をたどるので、グループでも中の
    シェイプを全部拾う（ノード自身がシェイプならそれを返す）。
    """
    shapes = cmds.ls(node, dag=True, shapes=True, noIntermediate=True,
                     long=True) or []
    return shapes or [node]


def _listed(value):
    """`cmds` の戻りを必ず一覧にする（1 件のとき文字列が返る場合がある）。"""
    if not value:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _component_list(plug, shape):
    """`objectGroups[n]` プラグが抱えるフェースの塊をフルパスで返す。

    `objectGrpCompList` は `['f[0:2]', 'f[7]']` のような形で返る。 SG の
    メンバー（`cmds.sets(sg, q=True)`）を舐めるより安く、しかも
    **どの SG のどのフェースか**が接続から直接たどれる。

    **`f[...]` の形をしていないものは捨てる。** ここで拾い損ねると
    「読めなかった」扱いになって色が掛からないだけだが、変な名前を混ぜると
    戻すときの `cmds.sets` が落ちる。 掛からないほうがまだよい。
    """
    try:
        value = cmds.getAttr(plug + ".objectGrpCompList")
    except Exception:
        return []

    items = []
    for item in _listed(value):
        # 実機の戻りが入れ子だった場合に備えて 1 段だけほどく
        items.extend(_listed(item) if isinstance(item, (list, tuple))
                     else [item])
    return ["%s.%s" % (shape, item) for item in items
            if isinstance(item, str) and "[" in item]


def _read_assignment(shape):
    """シェイプの現在の割り当てを `(戻し先, フェースの塊, 読めたか)` で返す。

    **フェース単位（マルチマテリアル）かどうかは接続プラグの形で分かる。**
    ふつうのシェイプは `instObjGroups[0]` が直接 SG につながるので、
    セットの中身を引かずに済む（大きいシーンの `initialShadingGroup` を
    舐めない）。

    「読めたか」が False なのは、フェース単位で割り当たっているのに塊を
    読み出せなかったとき。 **この場合は色を掛けない。** 掛けてしまうと
    `forceElement` が元の分割を落とし、戻す手掛かりがどこにも残らない。
    """
    pairs = _listed(cmds.listConnections(shape, type="shadingEngine",
                                         connections=True, plugs=True))
    wholes = []
    entries = []
    unreadable = False
    for index in range(0, len(pairs) - 1, 2):
        local, remote = pairs[index], pairs[index + 1]
        # **向きを当てにしない。** シェイプ側のプラグは必ず instObjGroups を
        # 通るので、そちらで見分ける。 取り違えるとシェイプ名を SG として
        # 控えてしまい、戻すときに存在しない SG を指す
        if _MEMBER_PLUG not in (local or ""):
            if _MEMBER_PLUG in (remote or ""):
                local, remote = remote, local
            else:
                continue
        engine = (remote or "").split(".", 1)[0]
        if not engine:
            continue
        if _FACE_PLUG not in (local or ""):
            wholes.append(engine)
            continue
        components = _component_list(local, shape)
        if components:
            entries.append({"sg": engine, "components": components})
        else:
            unreadable = True

    if not entries:
        return (wholes[0] if wholes else _DEFAULT_SG, [], not unreadable)
    # 土台はシェイプ全体に掛かっていた SG。 全面がフェース割り当てなら
    # 最初の塊の SG で埋める（どの塊にも入らないフェースの行き先になる）
    return (wholes[0] if wholes else entries[0]["sg"], entries, not unreadable)


def _is_override_shader(shader):
    """このツールが作ったシェーダーか（名前ではなく属性で判定する）。"""
    if not shader:
        return False
    return bool(cmds.attributeQuery(_ATTR_ORIGINAL, node=shader, exists=True))


def _read_attr(node, attr, default=""):
    """文字列属性を読む。 読めなければ `default`。"""
    try:
        value = cmds.getAttr("%s.%s" % (node, attr))
    except Exception:
        return default
    return default if value is None else value


def _collect_records():
    """シーンにある全オーバーライドを記録の一覧として返す。

    情報源はシーンのノードそのもの。 Python 側にキャッシュを持たないので、
    シーンを開き直したあとでも、他のツールで消されたあとでも実態と食い違わない。
    """
    records = []
    for shader in cmds.ls(type="surfaceShader", long=True) or []:
        if not _is_override_shader(shader):
            continue
        shading_engines = cmds.listConnections(shader + ".outColor",
                                               type="shadingEngine") or []
        members = []
        for shading_engine in shading_engines:
            members.extend(cmds.sets(shading_engine, q=True) or [])
        color = cmds.getAttr(shader + ".outColor") or [(0.0, 0.0, 0.0)]

        # **色が出ているかは shadingEngine にメンバーが居るかで決まる。**
        # フラグを別に持たないので、Maya 側で手作業に割り当てを変えられても
        # 一覧が実態と食い違わない
        stored = core.split_members(_read_attr(shader, _ATTR_MEMBERS))
        legacy = _read_attr(shader, _ATTR_ORIGINAL, _DEFAULT_SG)

        # **元の SG はメンバーごとに控える**（グループに掛けると中の
        # シェイプは別々のマテリアルを持ちうる）
        known = dict(core.align_originals(
            stored, core.split_members(_read_attr(shader, _ATTR_ORIGINALS)),
            legacy))
        live = members or stored

        records.append({
            "shader": shader,
            "sg": shading_engines[0] if shading_engines else None,
            "original": legacy,
            "originals": [known.get(name, legacy) for name in live],
            # フェース単位で分かれていたシェイプの戻し先（無ければ空）
            "faces": core.decode_faces(_read_attr(shader, _ATTR_FACES)),
            "target": (_read_attr(shader, _ATTR_TARGET)
                       or (live[0] if live else shader)),
            "set": _read_attr(shader, _ATTR_SET),
            "color": tuple(color[0])[:3],
            "members": live,
            "enabled": bool(members),
        })
    records.sort(key=lambda rec: core.short_name(rec["target"]))
    return records


def _selected_objects():
    """選択されているオブジェクトをフルパスで返す（コンポーネント選択は除く）。"""
    return core.unique(cmds.ls(selection=True, long=True,
                               objectsOnly=True) or [])


def _selection_with_shapes():
    """選択物と、その下にあるシェイプをまとめて返す。

    記録が抱えているのはシェイプなので、グループやトランスフォームを
    選んだままでは突き合わせられない。
    """
    selection = _selected_objects()
    names = list(selection)
    for node in selection:
        names.extend(_shapes_of(node))
    return core.unique(names)


def _all_mesh_objects():
    """シーン内の全メッシュを、その親トランスフォームの形で返す。"""
    nodes = []
    for shape in cmds.ls(type="mesh", noIntermediate=True, long=True) or []:
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        nodes.append(parents[0] if parents else shape)
    return core.unique(nodes)


# --------------------------------------------------------------------------- #
# 控え（シーンの隣の JSON）
# --------------------------------------------------------------------------- #

def _scene_path():
    try:
        return cmds.file(q=True, sceneName=True) or ""
    except Exception:
        return ""


def _chosen_backup_path():
    """ユーザーが明示的に選んだ控え（選んでいなければ None）。"""
    if not cmds.optionVar(exists=_OPTVAR_BACKUP_PATH):
        return None
    return cmds.optionVar(q=_OPTVAR_BACKUP_PATH) or None


def _default_backup_path():
    """シーンの隣（＝既定の置き場所）。 シーンが未保存なら None。"""
    return core.backup_path_for(_scene_path(), _BACKUP_SUFFIX)


def _backup_path():
    """いま見ている控えのパス（無ければ None）。

    **明示的に選んだものが最優先。** 既定はシーンの隣だが、

      * シーンが未保存だと置き場所が決まらない（選ばせるしかない）
      * 前のシーンの控えや、共有フォルダに置いた控えを開きたいことがある

    ので、選ばれていればそちらを見る。 選択は `既定に戻す` で解除できる。
    """
    return _chosen_backup_path() or _default_backup_path()


def _read_backup(path=None):
    """控えを読む。 無ければ空、壊れていれば警告して空。"""
    path = path or _backup_path()
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return core.catalog_from_text(handle.read())
    except (OSError, ValueError) as exc:
        cmds.warning("[%s] 控えを読めませんでした（%s）: %s"
                     % (_PACKAGE, path, exc))
        return []


def _write_backup(sets, path):
    """控えを書く。 書けたらパス、書けなければ例外。"""
    text = core.catalog_to_text(sets, scene=_scene_path(),
                                tool_version=__version__)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _ask_backup_path():
    """シーンが未保存のとき、控えをどうするか尋ねる。

    戻り値は `パス` / `None`（控えずに進む）/ `False`（中止）。
    """
    keep = "保存先を選ぶ"
    skip = "控えずに片付ける"
    answer = cmds.confirmDialog(
        title="Color Override",
        message=("シーンが未保存なので、色分けの控えを置く場所が決まりません。\n"
                 "控えずに片付けると、同じ色分けには戻せません。"),
        button=[keep, skip, "キャンセル"],
        defaultButton=keep, cancelButton="キャンセル",
        dismissString="キャンセル")
    if answer == skip:
        return None
    if answer != keep:
        return False
    chosen = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2,
                              fileMode=0, caption="色分けの控えを保存") or []
    if not chosen:
        return False
    # 次に読むときも同じ場所を見る（覚えないと一覧から消える）
    _remember_backup_path(chosen[0])
    return chosen[0]


def _backup_sets(sets):
    """セットを控えに取り込む。 `パス` / `None`（控えなかった）/ `False`（中止）。

    **Restore はシーンからノードを消す。** 消す前にここを通らないと、
    同じ色分けに二度と戻れない。 だから書けなかったときは `False` を返して
    片付けそのものを止める（消してから「書けませんでした」では遅い）。
    """
    payload = [{"name": entry["name"], "items": entry.get("items") or []}
               for entry in sets if entry.get("items")]
    if not payload:
        return None

    path = _backup_path()
    if not path:
        path = _ask_backup_path()
        if path is None or path is False:
            return path

    try:
        return _write_backup(core.merge_catalog(_read_backup(path), payload),
                             path)
    except OSError as exc:
        cmds.confirmDialog(
            title="Color Override",
            message=("色分けの控えを書けませんでした:\n%s\n\n%s\n\n"
                     "控えられないので片付けを中止します。" % (path, exc)),
            button=["OK"])
        return False


def _remember_backup_path(path):
    """以降この控えを見る（`None` で選択を解除し、シーンの隣へ戻す）。"""
    if path:
        cmds.optionVar(sv=(_OPTVAR_BACKUP_PATH, path))
    elif cmds.optionVar(exists=_OPTVAR_BACKUP_PATH):
        cmds.optionVar(remove=_OPTVAR_BACKUP_PATH)


def _forget_backup(name):
    """控えから 1 セット消す。"""
    path = _backup_path()
    if not path:
        return
    remaining = [entry for entry in _read_backup(path)
                 if entry["name"] != name]
    try:
        _write_backup(remaining, path)
    except OSError as exc:
        cmds.warning("[%s] 控えを更新できませんでした: %s" % (_PACKAGE, exc))


# --------------------------------------------------------------------------- #
# セット（一覧の単位）
# --------------------------------------------------------------------------- #

def _all_sets():
    """扱うセット全部 — **掛かっているセット + 控えだけのセット**。

    一覧では 2 つに分けて出す（`applied` が上、そうでないものが「控え」欄）。
    **同じ名前が掛かっていれば控えの側は出さない。** 同じものが 2 行に
    見えるのを避けるため。

    作るのを 1 本にまとめてあるのは、新しいセット名の採番（`new_set_name`）が
    掛かっている名前と控えの名前の**両方**と衝突してはいけないため。
    """
    applied = core.group_by_set(_collect_records())
    known = {entry["name"] for entry in applied}

    entries = list(applied)
    for backup in _read_backup():
        if backup["name"] in known:
            continue
        entries.append({
            "name": backup["name"],
            "applied": False,
            "enabled": False,
            "records": [],
            "items": backup["items"],
            "colors": [item["color"] for item in backup["items"]],
            "count": len(backup["items"]),
        })
    return entries


def _find_set(name):
    for entry in _all_sets():
        if entry["name"] == name:
            return entry
    return None


# --------------------------------------------------------------------------- #
# シーンの書き換え
# --------------------------------------------------------------------------- #

def _write_string(node, attr, value):
    """文字列属性を（無ければ足してから）書く。"""
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")
    cmds.setAttr("%s.%s" % (node, attr), value or "", type="string")


def _write_assignment(shader, members, originals, faces=None):
    """「誰に掛けたか」と「それぞれの戻し先」をシェーダーに控える。

    復元の情報源はシーンに置く。 Python の辞書に持つとシーンを開き直した
    時点で戻せなくなり、一時解除中は shadingEngine が空なので
    シーンからも読めなくなる。

    `faces` はフェース単位で分かれていたシェイプの戻し先。 いま抱えている
    メンバーの分だけを書く（外したシェイプの控えを持ち回らない）。
    """
    if not shader or not cmds.objExists(shader):
        return
    kept = {name: entries for name, entries in (faces or {}).items()
            if name in set(members or [])}
    _write_string(shader, _ATTR_MEMBERS, core.join_members(members))
    _write_string(shader, _ATTR_ORIGINALS, core.join_members(originals))
    _write_string(shader, _ATTR_FACES, core.encode_faces(kept))


def _delete_override(record):
    """オーバーライド用に作ったノードを片付ける。"""
    for node in (record.get("sg"), record.get("shader")):
        if node and cmds.objExists(node):
            cmds.delete(node)


def _assignment_resolver(records):
    """シェイプ → **本当の**元の割り当て `(戻し先, フェースの塊, 読めたか)`。

    既にオーバーライドが掛かっているシェイプは、現在の割り当てが
    オーバーライド用の SG なので、そのまま控えると二度と元に戻せない。
    記録に控えてある分を優先する。

    シーンから読んだ分は控えておく。 同じシェイプが 2 回出てきても
    `listConnections` と `getAttr` を往復しない。
    """
    known = {}
    for record in records or []:
        for member, original in core.align_originals(
                record.get("members"), record.get("originals"),
                record.get("original") or _DEFAULT_SG):
            known[member] = (original, core.face_entries_for(record, member),
                             True)

    cache = {}

    def _resolve(shape):
        if shape in known:
            return known[shape]
        if shape not in cache:
            cache[shape] = _read_assignment(shape)
        return cache[shape]

    return _resolve


def _release_members(records, index, shapes):
    """これから別のオーバーライドが抱えるシェイプを、既存の記録から外す。

    **1 シェイプ = 1 オーバーライド**を保つための後始末。 たとえばグループに
    掛けたあと中の 1 つだけ色を変えると、そのシェイプは新しい記録に移る。
    外した結果メンバーが 0 になった記録は、シェーダーごと片付ける。
    """
    claimed = set(shapes)
    for record in list(records):
        members = record.get("members") or []
        keep = [name for name in members if name not in claimed]
        if len(keep) == len(members):
            continue

        pairs = dict(core.align_originals(members, record.get("originals"),
                                          record.get("original")
                                          or _DEFAULT_SG))
        for name in members:
            if name not in claimed:
                continue
            for key in (name, core.short_name(name)):
                if index.get(key) is record:
                    index.pop(key, None)

        faces = {name: entries
                 for name, entries in (record.get("faces") or {}).items()
                 if name not in claimed}

        record["members"] = keep
        record["originals"] = [pairs[name] for name in keep]
        record["faces"] = faces

        if keep:
            _write_assignment(record["shader"], keep, record["originals"],
                              faces)
            continue

        _delete_override(record)
        records.remove(record)
        for key in [k for k, value in index.items() if value is record]:
            index.pop(key, None)


def _apply_one(node, rgb, set_name, records, index, resolve_assignment):
    """ノード 1 つに色を掛ける。 既に掛かっていれば色とセットを差し替える。

    `index` は `core.index_by_object()` が作った「対象名 → 記録」の索引。
    **シーンの現在の割り当てを辿らないのが要点**で、一時解除中は対象が元の
    SG に戻っているため、割り当てからは既存のオーバーライドを見つけられない。
    見つけ損なうと 2 本目のシェーダーを作ってしまい、記録が二重になる。

    グループノードを渡すと、**中のシェイプを全部拾って 1 件の記録にまとめる**。
    戻し先はシェイプごとに控えるので、中身のマテリアルがばらばらでも戻せる。

    **フェース単位の割り当てを読み取れないシェイプが 1 つでもあれば、その
    ノードには掛けずに `None` を返す。** 掛けた時点で元の分割が落ち、戻す
    手掛かりがどこにも残らないため（グループなら中の 1 つでも駄目なら止める。
    半分だけ掛かっているほうが分かりにくい）。
    """
    record = index.get(node) or index.get(core.short_name(node))

    if record:
        cmds.setAttr(record["shader"] + ".outColor", rgb[0], rgb[1], rgb[2],
                     type="double3")
        # 掛け直したものは新しいセットに移す（1 回の Apply = 1 セット）
        _write_string(record["shader"], _ATTR_SET, set_name)
        record["set"] = set_name
        # 一時解除中に色を掛けたなら、見えるように戻す（掛けたのに何も
        # 変わらないほうが分かりにくい）
        if not record.get("enabled", True):
            _enable_records([record])
            record["enabled"] = True
        return record["shader"]

    shapes = [name for name in _shapes_of(node) if cmds.objExists(name)]
    if not shapes:
        cmds.warning("[%s] %s にシェイプが見つかりません。"
                     % (_PACKAGE, core.short_name(node)))
        return None

    # **割り当てを書き換える前に、シェイプごとの戻し先を控える。**
    assignments = [resolve_assignment(shape) for shape in shapes]

    # 読み取れないフェース割り当てがあれば掛けない（A: 静かに壊さない）
    blocked = [shape for shape, item in zip(shapes, assignments) if not item[2]]
    if blocked:
        cmds.warning(
            "[%s] %s: フェース単位の割り当てを読み取れないシェイプが %d 個あるため"
            "掛けませんでした（戻せなくなるため）。 例: %s"
            % (_PACKAGE, core.short_name(node), len(blocked),
               core.short_name(blocked[0])))
        return None

    originals = [item[0] for item in assignments]
    faces = {shape: item[1]
             for shape, item in zip(shapes, assignments) if item[1]}

    # これから抱えるシェイプを既存の記録から外す（1 シェイプ = 1 記録）
    _release_members(records, index, shapes)

    shader_name, sg_name = core.override_node_names(_NODE_PREFIX, node)
    shader = cmds.shadingNode("surfaceShader", asShader=True, name=shader_name)
    shading_engine = cmds.sets(name=sg_name, renderable=True,
                               noSurfaceShader=True, empty=True)
    cmds.connectAttr(shader + ".outColor", shading_engine + ".surfaceShader",
                     force=True)

    # _ATTR_ORIGINAL は「このツールが作ったシェーダーか」の目印も兼ねるので、
    # 旧形式の単一値として必ず書く
    _write_string(shader, _ATTR_ORIGINAL, originals[0])
    _write_string(shader, _ATTR_TARGET, node)
    _write_string(shader, _ATTR_SET, set_name)

    cmds.setAttr(shader + ".outColor", rgb[0], rgb[1], rgb[2], type="double3")
    cmds.sets(shapes, edit=True, forceElement=shading_engine)
    _write_assignment(shader, shapes, originals, faces)

    # 同じ処理の中で続けて引けるよう、作ったものも索引に足しておく
    record = {"shader": shader, "sg": shading_engine, "original": originals[0],
              "originals": originals, "faces": faces, "target": node,
              "members": shapes, "set": set_name, "enabled": True}
    records.append(record)
    for name in [node] + shapes:
        index.setdefault(name, record)
        index.setdefault(core.short_name(name), record)
    index[node] = record
    return shader


def _enable_records(records):
    """一時解除していたオーバーライドを掛け直す。 戻した件数を返す。"""
    restored = 0
    for record in records or []:
        if record.get("enabled", True):
            continue
        shading_engine = record.get("sg")
        if not shading_engine or not cmds.objExists(shading_engine):
            continue
        members = [name for name in (record.get("members") or [])
                   if cmds.objExists(name)]
        if not members:
            continue
        cmds.sets(members, edit=True, forceElement=shading_engine)
        restored += 1
    return restored


def _disable_records(records):
    """色を一時的に外して元のマテリアルに戻す（記録は残す）。 外した件数を返す。

    `Restore` と違ってシェーダーとセットは消さないので、そのまま掛け直せる。
    """
    targets = [rec for rec in records or [] if rec.get("enabled", True)]
    if not targets:
        return 0

    # どこへ戻すかを先に控える。 外した時点で shadingEngine が空になり、
    # シーンからは「何に掛かっていたか」が読めなくなる
    for record in targets:
        _write_assignment(record.get("shader"), record.get("members"),
                          record.get("originals"), record.get("faces"))

    _return_to_originals(targets)
    return len(targets)


def _return_to_originals(records):
    """記録のメンバーを、**それぞれの**元の shadingEngine へ戻す。

    手順は `core.restore_plan`。 戻し先が同じものは 1 回の `cmds.sets` に
    まとめる（対象ごとに呼ぶと数百オブジェクトで往復が効いてくる）。

    **フェース単位で分かれていたシェイプは 2 段階で戻す。** 先にシェイプ全体を
    土台の SG へ戻し、そのあとフェースの塊を割り当て直す。 順序が逆だと、
    どの塊にも入っていないフェースがオーバーライド用の SG に残る。

    元のマテリアルが既に消えていたら Maya の既定へ逃がす。
    """
    for original, items in core.restore_plan(records, _DEFAULT_SG):
        # コンポーネントは持ち主のシェイプの有無で見る（`objExists` に
        # `pCubeShape1.f[0:2]` を渡したときの挙動に寄りかからない）
        existing = [name for name in items
                    if cmds.objExists(core.component_owner(name))]
        if not existing:
            continue
        destination = (original if original and cmds.objExists(original)
                       else _DEFAULT_SG)
        cmds.sets(existing, edit=True, forceElement=destination)


def _in_undo_chunk(name, func):
    """1 操作 = 1 undo にまとめる。 例外が出ても必ず閉じる。

    閉じ忘れると以降の undo が壊れ、Maya を再起動するまで直らない。
    """
    cmds.undoInfo(openChunk=True, chunkName="%s %s" % (_PACKAGE, name))
    try:
        return func()
    finally:
        cmds.undoInfo(closeChunk=True)


# --------------------------------------------------------------------------- #
# 色のやりとり
# --------------------------------------------------------------------------- #

def _load_last_color():
    """前回使った色（無ければ既定色）。"""
    if cmds.optionVar(exists=_OPTVAR_LAST_COLOR):
        try:
            return core.parse_hex(cmds.optionVar(q=_OPTVAR_LAST_COLOR))
        except ValueError:
            pass
    return _DEFAULT_COLOR


def _current_color():
    """カラースライダの現在値。 読めなければ前回値に落とす。"""
    ctrl = _CTRL.get("color")
    rgb = None
    if ctrl and cmds.colorSliderGrp(ctrl, exists=True):
        rgb = cmds.colorSliderGrp(ctrl, q=True, rgbValue=True)
    try:
        return tuple(core.clamp01(c) for c in rgb)[:3]
    except (TypeError, ValueError):
        return _load_last_color()


def _set_color(rgb):
    """スライダと 16 進欄の両方を同じ色に揃え、optionVar に控える。"""
    if _CTRL.get("color"):
        cmds.colorSliderGrp(_CTRL["color"], edit=True, rgbValue=rgb)
    if _CTRL.get("hex"):
        cmds.textField(_CTRL["hex"], edit=True, text=core.to_hex(rgb))
    cmds.optionVar(sv=(_OPTVAR_LAST_COLOR, core.to_hex(rgb)))


# --------------------------------------------------------------------------- #
# 掛ける
# --------------------------------------------------------------------------- #

def _apply_pairs(pairs, label, set_name=None):
    """`(対象, 色)` の組をまとめて掛ける。 **1 回の呼び出し = 1 セット。**"""
    pairs = [(node, rgb) for node, rgb in pairs if node]
    if not pairs:
        cmds.warning("[%s] 対象がありません。" % (_PACKAGE,))
        return None

    # 既存のオーバーライドは 1 度のスキャンで索引にしておく。 ノードごとに
    # 割り当てを辿ると、対象が増えたときに cmds の往復が効いてくる
    records = _collect_records()
    index = core.index_by_object(records)
    resolve_assignment = _assignment_resolver(records)

    name = (core.normalize_set_name(set_name) if set_name
            else core.new_set_name([entry["name"] for entry in _all_sets()]))

    # 掛からなかったものは黙って落とさない。 数が合わないまま進むと、
    # 「塗ったつもりのオブジェクトが素のまま」に気付けない
    skipped = []

    def _run():
        for node, rgb in pairs:
            if _apply_one(node, rgb, name, records, index,
                          resolve_assignment) is None:
                skipped.append(node)

    _in_undo_chunk(label, _run)
    _refresh_list()
    print("[%s] %s: %d object(s) -> %s%s"
          % (_PACKAGE, label, len(pairs) - len(skipped), name,
             ("  skipped: %d" % (len(skipped),)) if skipped else ""))
    return name


def _on_apply_selected(*_args):
    """選択物すべてに、いま指定している色を掛ける。"""
    nodes = _selected_objects()
    rgb = _current_color()
    _set_color(rgb)
    _apply_pairs([(node, rgb) for node in nodes], "apply color")


def _on_random_selected(*_args):
    """選択物に互いに見分けやすい色を振る。"""
    nodes = _selected_objects()
    start = core.next_start_index(_collect_records())
    _apply_pairs(list(zip(nodes, core.distinct_colors(len(nodes), start))),
                 "random color")


def _on_random_all(*_args):
    """シーンの全メッシュに互いに見分けやすい色を振る。"""
    nodes = _all_mesh_objects()
    if len(nodes) > _BULK_CONFIRM_THRESHOLD:
        answer = cmds.confirmDialog(
            title="Color Override",
            message=("%d 個のメッシュに色を掛けます。\n"
                     "同じ数だけシェーダーとセットが作られます。 続けますか？"
                     % (len(nodes),)),
            button=["OK", "Cancel"], defaultButton="Cancel",
            cancelButton="Cancel", dismissString="Cancel")
        if answer != "OK":
            return
    start = core.next_start_index(_collect_records())
    _apply_pairs(list(zip(nodes, core.distinct_colors(len(nodes), start))),
                 "random color")


# --------------------------------------------------------------------------- #
# 片付ける / 一時解除
# --------------------------------------------------------------------------- #

def _restore(records, label, sets=None):
    """記録を元のマテリアルに戻し、ノードごと片付ける。

    **片付ける前に必ず控えを書き出す。** シーンをきれいにするのがこの操作の
    目的だが、控えが無いと同じ色分けに戻れない。
    """
    if not records:
        cmds.warning("[%s] 戻す対象がありません。" % (_PACKAGE,))
        return

    saved = _backup_sets(sets if sets is not None
                         else core.group_by_set(records))
    if saved is False:
        return

    def _run():
        _return_to_originals(records)
        for record in records:
            _delete_override(record)

    _in_undo_chunk(label, _run)
    _refresh_list()
    print("[%s] %s: %d override(s)%s"
          % (_PACKAGE, label, len(records),
             ("  backup: %s" % (saved,)) if saved else "  (控えなし)"))


def _on_restore_selected(*_args):
    """シーンで選択中のものを含むセットを片付ける。"""
    records = core.match_records(_collect_records(), _selection_with_shapes())
    _restore(records, "restore")


def _on_restore_all(*_args):
    _restore(_collect_records(), "restore all")


def _on_toggle(*_args):
    """色の表示を一時的に外す／掛け直す（記録は残す）。"""
    records = _collect_records()
    if not records:
        cmds.warning("[%s] オーバーライドが掛かっていません。" % (_PACKAGE,))
        _refresh_list()
        return

    if core.any_enabled(records):
        count = _in_undo_chunk("hide overrides",
                               lambda: _disable_records(records))
        message = "hide overrides"
    else:
        count = _in_undo_chunk("show overrides",
                               lambda: _enable_records(records))
        message = "show overrides"

    _refresh_list()
    print("[%s] %s: %d object(s)" % (_PACKAGE, message, count))


def toggle():
    """オーバーライドの表示を一時的に切り替える。

    ウィンドウを開いていなくても呼べるので、**ホットキーやシェルフボタンに
    割り当てて使える**。 「一瞬だけ元のマテリアルを見たい」のが主な用途なので、
    ボタンまでマウスを運ばずに往復できるほうが速い。

        import color_override
        color_override.toggle()
    """
    return _on_toggle()


# --------------------------------------------------------------------------- #
# セットごとの操作（一覧の各行）
# --------------------------------------------------------------------------- #

def _on_set_rename(name, field, *_args):
    """行の名前欄を編集したとき。 セットに属する全シェーダーに書き戻す。"""
    new_name = core.normalize_set_name(
        cmds.textField(field, q=True, text=True), name)
    if new_name == name:
        return

    entry = _find_set(name)
    if entry is None:
        _refresh_list()
        return

    if entry["applied"]:
        def _run():
            for record in entry["records"]:
                _write_string(record["shader"], _ATTR_SET, new_name)
        _in_undo_chunk("rename set", _run)
    else:
        # 控えだけのセットは JSON 側を書き換える
        path = _backup_path()
        if path:
            catalog = _read_backup(path)
            for item in catalog:
                if item["name"] == name:
                    item["name"] = new_name
            try:
                _write_backup(catalog, path)
            except OSError as exc:
                cmds.warning("[%s] 控えを更新できませんでした: %s"
                             % (_PACKAGE, exc))

    _refresh_list()
    print("[%s] rename set: %s -> %s" % (_PACKAGE, name, new_name))


def _on_set_toggle(name, *_args):
    """このセットだけ一時的に外す／掛け直す。"""
    entry = _find_set(name)
    if entry is None or not entry["applied"]:
        return
    records = entry["records"]
    if entry["enabled"]:
        _in_undo_chunk("hide set", lambda: _disable_records(records))
    else:
        _in_undo_chunk("show set", lambda: _enable_records(records))
    _refresh_list()


def _on_set_select(name, *_args):
    """セットが抱えているオブジェクトをシーンで選択する。"""
    entry = _find_set(name)
    if entry is None:
        return
    if entry["applied"]:
        wanted = [member for record in entry["records"]
                  for member in record.get("members") or []]
    else:
        wanted = [item["target"] for item in entry["items"]]
    alive = [node for node in core.unique(wanted) if cmds.objExists(node)]
    if alive:
        cmds.select(alive, replace=True)
    else:
        cmds.warning("[%s] %s のオブジェクトが見つかりません。"
                     % (_PACKAGE, name))


def _on_set_restore(name, *_args):
    entry = _find_set(name)
    if entry is None or not entry["applied"]:
        return
    _restore(entry["records"], "restore set", sets=[entry])


def _on_set_reapply(name, *_args):
    """控えに残っているセットを掛け直す。

    **戻し先は控えから読まず、そのときの割り当てを見て取り直す。**
    片付けたあとにマテリアルを差し替えているかもしれないため。
    """
    entry = _find_set(name)
    if entry is None or entry["applied"]:
        return

    pairs = [(item["target"], item["color"]) for item in entry["items"]
             if cmds.objExists(item["target"])]
    missing = len(entry["items"]) - len(pairs)
    if not pairs:
        cmds.warning("[%s] %s のオブジェクトが 1 つも見つかりません。"
                     % (_PACKAGE, name))
        return
    if missing:
        cmds.warning("[%s] %s: %d 個のオブジェクトが見つからないので飛ばします。"
                     % (_PACKAGE, name, missing))
    _apply_pairs(pairs, "reapply set", set_name=name)


def _on_set_forget(name, *_args):
    """控えから 1 セット消す（掛かっていないものだけ）。"""
    answer = cmds.confirmDialog(
        title="Color Override",
        message="控えから「%s」を削除します。 元に戻せません。" % (name,),
        button=["削除", "キャンセル"], defaultButton="キャンセル",
        cancelButton="キャンセル", dismissString="キャンセル")
    if answer != "削除":
        return
    _forget_backup(name)
    _refresh_list()


# --------------------------------------------------------------------------- #
# 一覧
# --------------------------------------------------------------------------- #

def _build_swatches(colors):
    """色見本を横に並べる。 **カラーコードではなく色そのものを出す。**

    16 進の値はツールチップに残す（必要なときだけ読めればよい）。
    """
    shown, overflow = core.swatch_colors(colors, _SWATCH_LIMIT)
    columns = max(len(shown), 1) + (1 if overflow else 0)
    cmds.rowLayout(numberOfColumns=columns, height=18)
    if not shown:
        cmds.text(label="")
    for rgb in shown:
        cmds.canvas(width=10, height=14, rgbValue=rgb,
                    annotation=core.to_hex(rgb))
    if overflow:
        cmds.text(label="+%d" % (overflow,), fn="smallPlainLabelFont")
    cmds.setParent("..")


def _build_set_row(entry):
    """一覧の 1 行 = 1 セット。 掛かっているものと控えで持たせる操作が違う。"""
    name = entry["name"]
    if entry["applied"]:
        cmds.rowLayout(numberOfColumns=6, adjustableColumn=2,
                       columnWidth6=(98, 110, 50, 46, 40, 62),
                       columnAlign6=("left", "left", "left",
                                     "center", "center", "center"))
    else:
        cmds.rowLayout(numberOfColumns=5, adjustableColumn=2,
                       columnWidth5=(98, 110, 50, 40, 62),
                       columnAlign5=("left", "left", "left",
                                     "center", "center"))

    _build_swatches(entry["colors"])

    field = cmds.textField(text=name,
                           annotation="名前を変えて Enter でリネームできる")
    cmds.textField(field, edit=True,
                   changeCommand=lambda *a, n=name, f=field:
                   _on_set_rename(n, f))
    if not entry["applied"]:
        # 控えは放っておくと溜まる一方なので、消す手段を右クリックに置く。
        # 行のボタンを 1 つ増やすより幅を食わない
        cmds.popupMenu(parent=field)
        cmds.menuItem(label="控えから削除",
                      c=lambda *a, n=name: _on_set_forget(n))

    cmds.text(label="%d obj" % (entry["count"],), align="left",
              fn="smallPlainLabelFont")

    if entry["applied"]:
        cmds.button(label="Hide" if entry["enabled"] else "Show", height=22,
                    c=lambda *a, n=name: _on_set_toggle(n),
                    ann="このセットだけ一時的に外す／掛け直す")
        cmds.button(label="Sel", height=22,
                    c=lambda *a, n=name: _on_set_select(n),
                    ann="このセットのオブジェクトをシーンで選択する")
        cmds.button(label="Restore", height=22,
                    c=lambda *a, n=name: _on_set_restore(n),
                    ann="元のマテリアルに戻してノードを片付ける\n"
                        "（控えに残るので後から掛け直せる）")
    else:
        cmds.button(label="Sel", height=22,
                    c=lambda *a, n=name: _on_set_select(n),
                    ann="このセットのオブジェクトをシーンで選択する")
        cmds.button(label="復元", height=22,
                    c=lambda *a, n=name: _on_set_reapply(n),
                    ann=("控えの色分けをシーンに掛け直す\n"
                         "（上の一覧に戻る）"))

    cmds.setParent("..")


def _fill_rows(parent, entries, empty_label):
    """欄の中身を丸ごと作り直す。 差分更新はしない（実態と食い違わせない）。"""
    if not parent or not cmds.columnLayout(parent, exists=True):
        return
    for child in cmds.columnLayout(parent, q=True, childArray=True) or []:
        cmds.deleteUI(child)
    cmds.setParent(parent)

    for entry in entries:
        _build_set_row(entry)
    if not entries:
        cmds.text(label=empty_label, align="left", fn="smallObliqueLabelFont")


def _refresh_backup_path():
    """**いまどの控えを見ているか**を控え欄に出す。

    ここが見えないと、「保存したのに 0 セット」のときに何を疑えばよいか
    分からない（シーンが未保存なのか、別の控えを見ているのか）。
    """
    ctrl = _CTRL.get("backup_path")
    if not ctrl or not cmds.text(ctrl, exists=True):
        return

    chosen = _chosen_backup_path()
    path = _backup_path()
    if not path:
        label = "シーンが未保存です（「読み込む…」で控えを選べます）"
    else:
        label = os.path.basename(path)
        if chosen:
            label += "   ＊選択中"
        elif not os.path.isfile(path):
            label += "   （まだありません）"

    cmds.text(ctrl, edit=True, label=label, ann=path or "")
    if _CTRL.get("backup_reset"):
        cmds.button(_CTRL["backup_reset"], edit=True, enable=bool(chosen))


def _refresh_list(*_args):
    """一覧を作り直す。 **上は掛かっているセット、下は控え**。

    分けているのは「片付いたことが見て分かる」ため。 1 つの欄に混ぜると、
    `Restore` したセットがその場に残って見え、片付いたのかどうか分からない。
    """
    # **ウィンドウを閉じたあとも `_CTRL` には名前が残る。** `toggle()` は
    # ホットキーから呼べるので、ここを通らない経路が実際にある。 消えた
    # コントロールを edit すると Maya 側で例外になる
    parent = _CTRL.get("rows")
    if not parent or not cmds.columnLayout(parent, exists=True):
        return

    entries = _all_sets()
    applied = [entry for entry in entries if entry["applied"]]
    backups = [entry for entry in entries if not entry["applied"]]

    _fill_rows(parent, applied, "   まだ何も掛かっていません")
    _fill_rows(_CTRL.get("backup_rows"), backups, "   控えはまだありません")

    frame = _CTRL.get("backup_frame")
    if frame and cmds.frameLayout(frame, exists=True):
        cmds.frameLayout(frame, edit=True,
                         label="控え  —  %d セット" % (len(backups),))
    _refresh_backup_path()

    showing = any(entry["enabled"] for entry in applied) if applied else True

    if _CTRL.get("count"):
        cmds.text(_CTRL["count"], edit=True,
                  label="Sets: %d applied / %d backup%s"
                        % (len(applied), len(backups),
                           "" if showing else "   — 一時解除中"))

    # トグルのラベルは**シーンの実態から**決める。 別にフラグを持つと、
    # Maya 側で割り当てを手で変えられたときに表示と食い違う
    if _CTRL.get("toggle"):
        cmds.button(_CTRL["toggle"], edit=True, enable=bool(applied),
                    label="Hide Colors" if showing else "Show Colors")


# --------------------------------------------------------------------------- #
# コールバック（上段）
# --------------------------------------------------------------------------- #

def _on_color_changed(*_args):
    _set_color(_current_color())


def _on_hex_changed(*_args):
    """16 進欄の入力を色に反映する。 読めなければ元の表示に戻す。"""
    text = cmds.textField(_CTRL["hex"], q=True, text=True)
    try:
        rgb = core.parse_hex(text)
    except ValueError:
        cmds.warning("[%s] %s は #RRGGBB の形で入れてください。"
                     % (_PACKAGE, text))
        cmds.textField(_CTRL["hex"], edit=True,
                       text=core.to_hex(_current_color()))
        return
    _set_color(rgb)


def _on_choose_backup(*_args):
    """**読み込む控えを選ぶ。**

    既定はシーンの隣だが、それだけでは届かない場面がある:

      * シーンが未保存で、控えを自分で選んだ場所に置いた
      * 前のシーンの控え（別名保存で置いてきたもの）を呼び戻したい
      * 共有フォルダに置いた色分けを他の人と使い回したい

    **読めなかった控えには切り替えない。** 切り替えてから空だと、それまで
    見えていた控えまで見失う。
    """
    current = _backup_path() or ""
    options = {"fileFilter": "Color Override の控え (*.json);;すべて (*.*)",
               "dialogStyle": 2, "fileMode": 1,
               "caption": "読み込む控えを選ぶ"}
    folder = os.path.dirname(current)
    if folder and os.path.isdir(folder):
        options["startingDirectory"] = folder

    chosen = cmds.fileDialog2(**options) or []
    if not chosen:
        return

    path = chosen[0]
    if not _read_backup(path):
        cmds.warning("[%s] 色分けが入っていないので切り替えません: %s"
                     % (_PACKAGE, path))
        return

    _remember_backup_path(path)
    _refresh_list()
    print("[%s] backup: %s" % (_PACKAGE, path))


def _on_reset_backup(*_args):
    """控えの選択を解除して、シーンの隣に戻す。"""
    if not _chosen_backup_path():
        return
    _remember_backup_path(None)
    _refresh_list()
    print("[%s] backup: %s" % (_PACKAGE, _backup_path() or "（未保存）"))


def _on_open_backup(*_args):
    """控えの JSON がどこにあるかを示す（場所を確かめたいとき）。"""
    path = _backup_path()
    if not path:
        cmds.warning("[%s] シーンが未保存なので控えの場所が決まりません。"
                     % (_PACKAGE,))
        return
    print("[%s] backup: %s" % (_PACKAGE, path))
    if not os.path.isfile(path):
        cmds.warning("[%s] 控えはまだありません: %s" % (_PACKAGE, path))
        return
    try:
        os.startfile(os.path.dirname(path))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _build_body():
    color = _load_last_color()

    cmds.separator(h=4, style="none")

    _CTRL["color"] = cmds.colorSliderGrp(
        label="Color", rgbValue=color, columnWidth3=(44, 60, 150),
        adjustableColumn=3, changeCommand=_on_color_changed,
        annotation="オーバーライドに使う色")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2,
                   columnWidth2=(44, 210))
    cmds.text(label="Hex", align="left")
    _CTRL["hex"] = cmds.textField(text=core.to_hex(color),
                                  changeCommand=_on_hex_changed,
                                  annotation="#RRGGBB で直接指定する")
    cmds.setParent("..")

    cmds.button(label="Apply to Selected", height=28, c=_on_apply_selected,
                ann="選択したオブジェクトに上の色を掛ける（1 セットになる）")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,
                   columnWidth2=(170, 170))
    cmds.button(label="Random → Selected", height=26, c=_on_random_selected,
                ann="選択物に互いに見分けやすい色を振る")
    cmds.button(label="Random → All Meshes", height=26, c=_on_random_all,
                ann="シーンの全メッシュに互いに見分けやすい色を振る")
    cmds.setParent("..")

    cmds.separator(h=8, style="in")

    _CTRL["count"] = cmds.text(label="Sets: 0 applied / 0 backup",
                               align="left", fn="boldLabelFont")

    # 「一瞬だけ元のマテリアルを見る」ための往復。 Restore と違って
    # シェーダーは消さないので、何度でも掛け直せる
    _CTRL["toggle"] = cmds.button(
        label="Hide Colors", height=28, c=_on_toggle, enable=False,
        ann="掛かっている色を一時的に全部外す／掛け直す。\n"
            "ホットキーに割り当てるなら: "
            "import color_override; color_override.toggle()")

    # 一覧は行ごとに色見本（canvas）を並べるので textScrollList では作れない。
    # scrollLayout の中に rowLayout を並べ、更新のたびに丸ごと作り直す
    _CTRL["list"] = cmds.scrollLayout(height=140, childResizable=True,
                                      horizontalScrollBarThickness=0)
    _CTRL["rows"] = cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.setParent("..")
    cmds.setParent("..")

    # 控えは**別の欄**に出す。 `Restore` したセットが上の一覧から消えて
    # ここに移る、という見え方にするため（混ぜると片付いたのか分からない）。
    # **空でも畳まない。** 「控えを保存したのに 0 件」のときにこそ
    # 「読み込む…」で探しに行きたいので、入口を隠すと詰む
    _CTRL["backup_frame"] = cmds.frameLayout(
        label="控え  —  0 セット", collapsable=True, collapse=False,
        marginHeight=4, marginWidth=2,
        ann="Restore で片付けたセット。 「復元」で同じ色分けを掛け直す")
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)

    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1,
                   columnWidth3=(190, 86, 74),
                   columnAlign3=("left", "center", "center"))
    _CTRL["backup_path"] = cmds.text(label="", align="left",
                                     fn="smallPlainLabelFont")
    cmds.button(label="読み込む…", height=22, c=_on_choose_backup,
                ann=("別の控え（JSON）を開く。\n"
                     "前のシーンの控えや、共有フォルダに置いた控えも読める"))
    _CTRL["backup_reset"] = cmds.button(
        label="既定", height=22, c=_on_reset_backup, enable=False,
        ann="控えの選択を解除して、シーンの隣に戻す")
    cmds.setParent("..")

    _CTRL["backup_list"] = cmds.scrollLayout(height=92, childResizable=True,
                                             horizontalScrollBarThickness=0)
    _CTRL["backup_rows"] = cmds.columnLayout(adjustableColumn=True,
                                             rowSpacing=2)
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1,
                   columnWidth3=(130, 110, 90))
    cmds.button(label="Restore Selected", height=26, c=_on_restore_selected,
                ann="シーンで選択中のオブジェクトを含むセットを片付ける")
    cmds.button(label="Restore All", height=26, c=_on_restore_all,
                ann="掛かっているものを全部片付ける\n"
                    "（控えに書き出すので後から掛け直せる）")
    cmds.button(label="Refresh", height=26, c=_refresh_list,
                ann="一覧をシーンと控えの実態から作り直す")
    cmds.setParent("..")

    cmds.button(label="控えの場所を開く", height=22, c=_on_open_backup,
                ann="シーンの隣に置いている色分けの控え（JSON）")


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    _CTRL.clear()

    win = cmds.window(WINDOW,
                      title="Color Override  —  v%s" % (__version__,),
                      widthHeight=(440, 610),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    _refresh_list()
    return win
