# -*- coding: utf-8 -*-
"""BlendShape Manager — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** 開発機に Maya が無いので、
ここに寄せた処理だけが自宅で実行・テストできる。

扱うもの:
    * `aliasAttr` / `getAttr(multiIndices=True)` の戻り値の解釈
    * ターゲット名の検証・一括リネームの計画（入れ替えを含む衝突の回避）
    * インビトウィーンの重みと `inputTargetItem` の番号の変換
    * 左右の名前の入れ替え（`L_smile` → `R_smile`）
    * 頂点座標からの左右対応表づくりと、シェイプの左右反転

ノードの生成・属性の読み書きは `scene.py`、ウィンドウは `ui.py` の仕事。
"""

from __future__ import annotations

import math
import re


# --------------------------------------------------------------------------- #
# 名前
# --------------------------------------------------------------------------- #

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WEIGHT_PLUG_RE = re.compile(r"^(?:weight|w)\[(\d+)\]$")

# blendShape ノードが元から持っている属性名。 エイリアスにすると
# `aliasAttr` が失敗するか、もっと悪いと紛らわしい名前になる
RESERVED_NAMES = frozenset((
    "weight", "w", "envelope", "en", "input", "ip", "outputGeometry", "og",
    "inputTarget", "it", "origin", "or", "baseOrigin", "bo", "targetOrigin",
    "to", "message", "caching", "nodeState", "frozen", "isHistoricallyInteresting",
    "topologyCheck", "icon",
))
# ここに無い既存属性と同名でも、`aliasAttr` が実機で弾くので壊れはしない
# （`scene.rename_targets` が例外を拾ってダイアログに出す）


def is_valid_name(name):
    """Maya のノード名 / 属性名として使えるか（英数字と `_`、数字始まり不可）。"""
    return bool(name) and _NAME_RE.match(name) is not None


def short_name(node):
    """`|grp|ns:body` → `body`（DAG パスと名前空間を外す）。"""
    return (node or "").rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def default_node_name(base):
    """ベースメッシュ名から blendShape ノードの既定名を作る（`body` → `body_BS`）。"""
    stem = re.sub(r"[^A-Za-z0-9_]", "_", short_name(base)) or "blendShape"
    if stem[0].isdigit():
        stem = "_" + stem
    return stem + "_BS"


def validate_target_name(name, others):
    """ターゲット名として使えなければ理由（文字列）を、使えるなら `None` を返す。

    `others` は**自分以外の**既存ターゲット名。
    """
    if not is_valid_name(name):
        return "名前に使えない文字が含まれている（英数字と _ のみ・数字始まり不可）: %r" % (name,)
    if name in RESERVED_NAMES:
        return "blendShape ノードの既存の属性名と同じ: %r" % (name,)
    if name in set(others):
        return "同じ名前のターゲットが既にある: %r" % (name,)
    return None


# --------------------------------------------------------------------------- #
# ターゲットの一覧
# --------------------------------------------------------------------------- #

def parse_alias_list(flat):
    """`cmds.aliasAttr(bs, q=True)` の戻り値を `{ウェイト番号: 名前}` にする。

    戻り値は `["smile", "weight[0]", "blink", "weight[1]"]` のような
    名前と属性の交互の平坦なリスト（エイリアスが 1 つも無いと `None`）。
    `weight[i]` 以外の属性へのエイリアスは無視する。
    """
    result = {}
    items = list(flat or [])
    for alias, plug in zip(items[0::2], items[1::2]):
        m = _WEIGHT_PLUG_RE.match(plug or "")
        if m:
            result[int(m.group(1))] = alias
    return result


def target_entries(indices, aliases):
    """ウェイト番号とエイリアスから、番号順の `[(番号, 名前), ...]` を作る。

    エイリアスの無い番号は `weight[i]` と表示する（Maya の Channel Box と同じ）。
    `indices` に無いがエイリアスだけ残っている番号も拾う。
    """
    all_indices = sorted(set(int(i) for i in (indices or [])) | set(aliases))
    return [(i, aliases.get(i, "weight[%d]" % i)) for i in all_indices]


def next_free_index(indices):
    """新しいターゲットに使う番号（既存の最大 + 1。 空なら 0）。

    抜けた番号を埋めないのは Maya の Shape Editor と同じ振る舞いにするため
    （埋めると、削除済みターゲットの残骸と番号がぶつかることがある）。
    """
    indices = [int(i) for i in (indices or [])]
    return max(indices) + 1 if indices else 0


def topology_mismatches(base_count, counts):
    """頂点数がベースと違うものの名前を返す。 `counts` は `{名前: 頂点数}`。"""
    return sorted(name for name, n in counts.items() if n != base_count)


def split_create_selection(selection):
    """作成時の選択を `(ターゲット, ベース)` に分ける。 ベースは**最後に選んだもの**。

    Maya の Deform > Blend Shape と同じ順番。 空なら `ValueError`。
    """
    selection = list(selection or [])
    if not selection:
        raise ValueError("ベースメッシュを選択してください（ターゲットがあれば先に、ベースは最後に選択）")
    base = selection[-1]
    targets = [n for n in selection[:-1] if n != base]
    return targets, base


# --------------------------------------------------------------------------- #
# リネーム
# --------------------------------------------------------------------------- #

def batch_rename(names, prefix="", suffix="", search="", replace=""):
    """検索置換 → 接頭辞 → 接尾辞 の順に適用した名前を返す。"""
    out = []
    for name in names:
        if search:
            name = name.replace(search, replace)
        out.append("%s%s%s" % (prefix, name, suffix))
    return out


def plan_renames(entries, new_names):
    """リネームの手順を組み立てる。

    `entries` は全ターゲットの `[(番号, 現在の名前), ...]`、`new_names` は
    変えたいものだけの `{番号: 新しい名前}`。

    戻り値は `(steps, errors)`。 `steps` は `[(番号, 名前), ...]` の実行順で、
    `errors` が空でないときは何もしてはいけない。

    `A→B, B→A` のような入れ替えや、`A→B` と `B→C` の連鎖を素直に順番に
    実行すると、途中で同名が 2 つできて `aliasAttr` が失敗する。 衝突する
    場合だけ、いったん一時名に逃がしてから最終名を付ける 2 段にする。
    """
    current = dict(entries)
    final = dict(current)
    final.update(new_names)

    errors = []
    for index, name in sorted(new_names.items()):
        others = [n for i, n in final.items() if i != index]
        reason = validate_target_name(name, others)
        if reason:
            errors.append("%s → %s: %s" % (current.get(index, index), name, reason))
    if errors:
        return [], errors

    changes = [(i, n) for i, n in sorted(new_names.items()) if current.get(i) != n]
    if not changes:
        return [], []

    # 順に付けていって、付ける時点でまだ他の誰かがその名前を持っていたら衝突
    taken = dict(current)
    collides = False
    for index, name in changes:
        if any(n == name for i, n in taken.items() if i != index):
            collides = True
            break
        taken[index] = name
    if not collides:
        return changes, []

    used = set(current.values()) | set(final.values())
    steps = []
    for index, _name in changes:
        temp = _unique("bsmTmp%d" % index, used)
        used.add(temp)
        steps.append((index, temp))
    steps.extend(changes)
    return steps, []


def _unique(stem, used):
    name, n = stem, 0
    while name in used:
        n += 1
        name = "%s_%d" % (stem, n)
    return name


# --------------------------------------------------------------------------- #
# インビトウィーン
# --------------------------------------------------------------------------- #

# `inputTargetItem[i]` の番号は 5000 + 重み×1000（6000 がフルの 1.0）
ITEM_BASE = 5000
ITEM_FULL = 6000


def weight_to_item_index(weight):
    return ITEM_BASE + int(round(float(weight) * 1000))


def item_index_to_weight(item_index):
    return (int(item_index) - ITEM_BASE) / 1000.0


def inbetween_weights(item_indices):
    """`inputTargetItem` の番号から、インビトウィーンの重みだけを昇順で返す（1.0 を除く）。"""
    return sorted(item_index_to_weight(i) for i in (item_indices or [])
                  if int(i) != ITEM_FULL)


def validate_inbetween_weight(weight, item_indices):
    """インビトウィーンを置けない重みなら理由を、置けるなら `None` を返す。"""
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        return "重みが数値ではない: %r" % (weight,)
    if not 0.0 < weight < 1.0:
        return "インビトウィーンの重みは 0 より大きく 1 より小さくする: %g" % weight
    index = weight_to_item_index(weight)
    if index in set(int(i) for i in (item_indices or [])):
        return "重み %.3f には既にシェイプがある" % item_index_to_weight(index)
    return None


# --------------------------------------------------------------------------- #
# ミラー
# --------------------------------------------------------------------------- #

# (左, 右) の組。 上から順に試し、最初に当たったものだけ入れ替える
_SIDE_PREFIXES = (("L_", "R_"), ("l_", "r_"), ("Lf_", "Rt_"), ("lf_", "rt_"))
_SIDE_SUFFIXES = (("_L", "_R"), ("_l", "_r"), ("_Lf", "_Rt"), ("_lf", "_rt"))
_SIDE_WORDS = (("Left", "Right"), ("left", "right"), ("LEFT", "RIGHT"))

AXES = ("x", "y", "z")


def mirror_name(name):
    """左右を表す部分を入れ替えた名前を返す: `(新しい名前, 入れ替えたか)`。

    >>> mirror_name("L_smile")
    ('R_smile', True)
    >>> mirror_name("browUp_R")
    ('browUp_L', True)
    >>> mirror_name("jawOpen")
    ('jawOpen_mirror', False)
    """
    for left, right in _SIDE_PREFIXES:
        if name.startswith(left):
            return right + name[len(left):], True
        if name.startswith(right):
            return left + name[len(right):], True
    for left, right in _SIDE_SUFFIXES:
        if name.endswith(left):
            return name[:-len(left)] + right, True
        if name.endswith(right):
            return name[:-len(right)] + left, True
    for left, right in _SIDE_WORDS:
        if left in name:
            return name.replace(left, right, 1), True
        if right in name:
            return name.replace(right, left, 1), True
    return name + "_mirror", False


def plan_mirror(names):
    """ミラーする名前を決める: `(処理する名前, 飛ばす名前)`。

    `L_smile` と `R_smile` を両方選んでミラーすると、片方を作った直後に
    もう片方でそれを上書きし直すことになる（結果は元に戻るだけ）。
    左右の組が両方選ばれていたら、先に出てきたほうだけを処理する。
    """
    todo, skipped = [], []
    for name in names:
        partner, swapped = mirror_name(name)
        if swapped and partner in todo:
            skipped.append(name)
        else:
            todo.append(name)
    return todo, skipped


def filter_entries(entries, text):
    """`[(番号, 名前), ...]` を名前の部分一致（大文字小文字を無視）で絞る。

    空白区切りで複数書くと、どれかに当たれば残す（`L_ brow` など）。
    """
    words = [w.lower() for w in (text or "").split()]
    if not words:
        return list(entries)
    return [(i, n) for i, n in entries if any(w in n.lower() for w in words)]


def axis_index(axis):
    axis = str(axis).lower()
    if axis not in AXES:
        raise ValueError("axis must be one of %s: %r" % (AXES, axis))
    return AXES.index(axis)


def _mirrored(point, axis):
    p = list(point[:3])
    p[axis] = -p[axis]
    return p


def build_mirror_map(points, axis="x", tolerance=1e-3):
    """各頂点について、対称面の反対側にある頂点の番号を返す（見つからなければ -1）。

    `points` はベース（ニュートラル）の頂点座標 `[(x, y, z), ...]`。
    位置で対応を取るので、**ベースが対称面に対して左右対称であること**が前提。
    格子に振り分けてから近傍だけを調べるので、頂点数に対してほぼ線形。
    """
    ax = axis_index(axis)
    tol = float(tolerance)
    if tol <= 0:
        raise ValueError("tolerance must be > 0: %r" % (tolerance,))
    cell = tol * 2.0

    def key(p):
        return (int(math.floor(p[0] / cell)), int(math.floor(p[1] / cell)),
                int(math.floor(p[2] / cell)))

    grid = {}
    for i, p in enumerate(points):
        grid.setdefault(key(p), []).append(i)

    tol2 = tol * tol
    result = []
    for p in points:
        q = _mirrored(p, ax)
        kx, ky, kz = key(q)
        best, best_d = -1, tol2
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in grid.get((kx + dx, ky + dy, kz + dz), ()):
                        o = points[j]
                        d = ((o[0] - q[0]) ** 2 + (o[1] - q[1]) ** 2
                             + (o[2] - q[2]) ** 2)
                        if d <= best_d:
                            best, best_d = j, d
        result.append(best)
    return result


def mirror_shape(base, target, mirror_map, axis="x"):
    """ターゲットの形を左右反転した頂点座標を返す: `(座標, 対応の無かった頂点数)`。

    頂点 i の新しい位置は「反対側の頂点 j の、ターゲットでの位置」を鏡に
    映したもの。 対応の見つからない頂点はベースの位置（＝動かない）にする。
    """
    if not (len(base) == len(target) == len(mirror_map)):
        raise ValueError("base / target / mirror_map の頂点数が揃っていない: %d / %d / %d"
                         % (len(base), len(target), len(mirror_map)))
    ax = axis_index(axis)
    out = []
    missing = 0
    for i, j in enumerate(mirror_map):
        if j < 0:
            out.append(list(base[i][:3]))
            missing += 1
        else:
            out.append(_mirrored(target[j], ax))
    return out, missing
