# -*- coding: utf-8 -*-
"""Color Override — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** 開発機に Maya が無いので、
ここに寄せた処理だけが自宅で実行・テストできる（`docs/TOOL_SCAFFOLD.md`）。

このツールで `core` が持っているのは次の 4 つ:

    * 識別色の生成       — 何個並べても隣り合う色が似ないようにする
    * 16 進カラーの往復  — UI のテキスト入力と RGB の相互変換
    * ノード名の組み立て — オーバーライド用シェーダー / セットの命名と無害化
    * 記録の突き合わせ   — 「選択されているもの」と「オーバーライド済みのもの」

`ui.py` 側に残るのは `cmds` の呼び出しだけで、判断はすべてここにある。
"""

from __future__ import annotations

import colorsys
import re


# 色相を黄金比の小数部だけずらしていくと、何個取っても隣り合う色が似ない。
# 等間隔（0.1 刻みなど）にすると周期で色が戻り、10 個目と 20 個目が同色になる。
# 貫通の判別が目的なので「隣接するオブジェクトの色が必ず違う」ことを優先する
_HUE_STEP = 0.6180339887498949

# 彩度を上げ切らないのは、ビューポートの背景（中間グレー）でも白飛びせず、
# かつ Maya のデフォルトのワイヤー色と混同しにくい範囲に収めるため
_DEFAULT_SATURATION = 0.62
_DEFAULT_VALUE = 1.0

_HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")
_INVALID_IN_NAME = re.compile(r"[^A-Za-z0-9_]")


# --------------------------------------------------------------------------- #
# 色
# --------------------------------------------------------------------------- #

def clamp01(value):
    """0.0–1.0 に丸める。

    >>> clamp01(1.4), clamp01(-0.2), clamp01(0.5)
    (1.0, 0.0, 0.5)
    """
    value = float(value)
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def color_at(index, saturation=_DEFAULT_SATURATION, value=_DEFAULT_VALUE):
    """`index` 番目の識別色を `(r, g, b)`（各 0.0–1.0）で返す。

    同じ `index` なら必ず同じ色になる（乱数を使わないので、掛け直しても
    色が入れ替わらない）。

    >>> color_at(0) == color_at(0)
    True
    >>> color_at(0) != color_at(1)
    True
    """
    if index < 0:
        raise ValueError("index must be >= 0: %r" % (index,))
    hue = (index * _HUE_STEP) % 1.0
    return colorsys.hsv_to_rgb(hue, clamp01(saturation), clamp01(value))


def distinct_colors(count, start_index=0,
                    saturation=_DEFAULT_SATURATION, value=_DEFAULT_VALUE):
    """互いに見分けやすい色を `count` 個返す。

    `start_index` をずらすと、既に色が付いているものとも重ならない色から
    続けられる（オブジェクトを足して掛け直すときに使う）。

    >>> len(distinct_colors(3))
    3
    >>> len(set(distinct_colors(20))) == 20
    True
    """
    if count < 0:
        raise ValueError("count must be >= 0: %r" % (count,))
    return [color_at(start_index + i, saturation, value) for i in range(count)]


def parse_hex(text):
    """`#RRGGBB` / `RRGGBB` を `(r, g, b)`（0.0–1.0）に変換する。

    読めなければ `ValueError`。 実機で `setAttr` に渡してから落ちるより、
    入力欄を離れた時点で弾きたい。

    >>> parse_hex("#FF0000")
    (1.0, 0.0, 0.0)
    >>> parse_hex("00ff00")
    (0.0, 1.0, 0.0)
    """
    match = _HEX.match((text or "").strip())
    if not match:
        raise ValueError("16 進カラーコードとして読めない: %r" % (text,))
    digits = match.group(1)
    return tuple(int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def to_hex(rgb):
    """`(r, g, b)`（0.0–1.0）を `#RRGGBB` にする。

    >>> to_hex((1.0, 0.0, 0.0))
    '#FF0000'
    >>> to_hex((2.0, -1.0, 0.5))
    '#FF0080'
    """
    channels = list(rgb or [])
    if len(channels) != 3:
        raise ValueError("rgb は 3 要素で渡す: %r" % (rgb,))
    return "#%02X%02X%02X" % tuple(
        int(round(clamp01(c) * 255.0)) for c in channels)


# --------------------------------------------------------------------------- #
# 名前
# --------------------------------------------------------------------------- #

def short_name(dag_path):
    """`|grp|pSphere1` や `ns:pSphere1` から末尾の要素を取り出す。

    >>> short_name("|grp|pSphere1")
    'pSphere1'
    >>> short_name("pSphere1")
    'pSphere1'
    """
    return (dag_path or "").rsplit("|", 1)[-1]


def sanitize_identifier(name, fallback="node"):
    """Maya のノード名に使える形へ落とす（英数字と `_` のみ・数字始まり不可）。

    名前空間の `:` や階層の `|` をそのまま `cmds.shadingNode(name=...)` に
    渡すと実機で落ちるので、ここで潰しておく。

    >>> sanitize_identifier("|grp|char:body_geo")
    'char_body_geo'
    >>> sanitize_identifier("123")
    '_123'
    >>> sanitize_identifier("")
    'node'
    """
    token = _INVALID_IN_NAME.sub("_", short_name(name or "")).strip("_")
    if not token:
        return fallback
    if token[0].isdigit():
        token = "_" + token
    return token


def override_node_names(prefix, target):
    """対象ノードに対応する `(シェーダー名, シェーディングセット名)` を返す。

    実機のシーンには他の人のノードも同居するので、必ず名前空間付きの
    `prefix`（`ntk_color_override`）から組み立てる。

    >>> override_node_names("ntk_color_override", "|grp|pSphere1")
    ('ntk_color_override_pSphere1_SHD', 'ntk_color_override_pSphere1_SG')
    """
    stem = "%s_%s" % (prefix, sanitize_identifier(target))
    return (stem + "_SHD", stem + "_SG")


# --------------------------------------------------------------------------- #
# 記録
# --------------------------------------------------------------------------- #

def unique(items):
    """順序を保ったまま重複を落とす。

    >>> unique(["b", "a", "b", "c"])
    ['b', 'a', 'c']
    """
    seen = set()
    out = []
    for item in items or []:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def format_row(record):
    """一覧に出す 1 行（`短い名前   #RRGGBB`。 一時解除中は `(off)` を付ける）。

    >>> format_row({"target": "|grp|pSphere1", "color": (1.0, 0.0, 0.0)})
    'pSphere1   #FF0000'
    >>> format_row({"target": "a", "color": (1.0, 0.0, 0.0), "enabled": False})
    'a   #FF0000   (off)'
    """
    row = "%s   %s" % (short_name(record.get("target")),
                       to_hex(record.get("color") or (0.0, 0.0, 0.0)))
    return row if record.get("enabled", True) else row + "   (off)"


def match_records(records, selection):
    """`selection` に含まれる対象の記録だけを、元の順序で返す。

    フルパスでも短い名前でも一致させる。 ユーザーがアウトライナで選んだのか
    ビューポートで選んだのかで `cmds.ls` の返す形が変わるので、どちらでも
    拾えるようにしておく。

    グループに掛けた場合、`target` はグループでも実際に色が乗っているのは
    中のシェイプなので、**メンバーでも一致させる**（子を選んで Restore した
    ときに何も起きないと、掛かっていないように見える）。

    >>> recs = [{"target": "|grp|a"}, {"target": "|grp|b"}]
    >>> match_records(recs, ["b"])
    [{'target': '|grp|b'}]
    >>> match_records([{"target": "|g", "members": ["|g|a|aShape"]}],
    ...               ["aShape"])
    [{'target': '|g', 'members': ['|g|a|aShape']}]
    >>> match_records(recs, [])
    []
    """
    wanted = set()
    for name in selection or []:
        wanted.add(name)
        wanted.add(short_name(name))

    found = []
    for record in records or []:
        names = [record.get("target")] + list(record.get("members") or [])
        if any(name in wanted or short_name(name) in wanted
               for name in names if name):
            found.append(record)
    return found


def next_start_index(records):
    """既存の記録に続けて色を振るときの開始インデックス。

    シーンに既に n 個オーバーライドがあるなら n 番目から振ると、
    既存の色とも重なりにくい。

    >>> next_start_index([{"target": "a"}, {"target": "b"}])
    2
    """
    return len(records or [])


# --------------------------------------------------------------------------- #
# 一時解除（peek）
# --------------------------------------------------------------------------- #

# メンバー一覧を 1 本の文字列属性に畳むときの区切り。 Maya のノード名には
# 使えない文字なので、名前と衝突しない
_MEMBER_SEP = ";"


def join_members(members):
    """メンバー名の一覧を、属性に書ける 1 本の文字列にする。

    >>> join_members(["|a|aShape", "|b|bShape"])
    '|a|aShape;|b|bShape'
    >>> join_members(None)
    ''
    """
    return _MEMBER_SEP.join(name for name in (members or []) if name)


def split_members(text):
    """`join_members` の逆。

    >>> split_members("|a|aShape;|b|bShape")
    ['|a|aShape', '|b|bShape']
    >>> split_members("")
    []
    """
    return [name for name in (text or "").split(_MEMBER_SEP) if name]


def any_enabled(records):
    """1 つでも色が出ている状態か（トグルがどちら向きに倒れるかの判断）。

    `enabled` を持たない記録は「出ている」と見なす（v0.1.0 で作られた
    オーバーライドを開いたときに、解除済みと誤判定しないため）。

    >>> any_enabled([{"enabled": False}, {"enabled": True}])
    True
    >>> any_enabled([{"enabled": False}])
    False
    >>> any_enabled([{}])
    True
    >>> any_enabled([])
    False
    """
    return any(rec.get("enabled", True) for rec in records or [])


def align_originals(members, originals, fallback=""):
    """メンバーと「元の shadingEngine」を 1 対 1 に揃えて返す。

    **グループに掛けると、中のシェイプはそれぞれ別のマテリアルを持ちうる。**
    だから元の SG はオーバーライド 1 件につき 1 つではなく、**メンバーごと**に
    控える必要がある（v0.3.0 で直した不具合の核心）。

    v0.2.0 までのシーンには `originals` が無いので、その場合は旧形式の
    単一値 `fallback` で埋める。

    >>> align_originals(["a", "b"], ["sgA", "sgB"])
    [('a', 'sgA'), ('b', 'sgB')]
    >>> align_originals(["a", "b"], [], fallback="sgX")
    [('a', 'sgX'), ('b', 'sgX')]
    >>> align_originals(["a", "b"], ["sgA"], fallback="sgX")
    [('a', 'sgX'), ('b', 'sgX')]
    >>> align_originals(None, None)
    []
    """
    members = list(members or [])
    originals = list(originals or [])
    if len(originals) != len(members):
        originals = [fallback] * len(members)
    return list(zip(members, originals))


def group_by_original(records):
    """戻し先の shadingEngine ごとに対象をまとめる。

    一時解除も Restore も「まとめて元の SG へ戻す」操作なので、対象ごとに
    `cmds.sets` を呼ぶと数百回の往復になる。 戻り先が同じものを 1 回の
    呼び出しにまとめるためのグルーピング。 順序は最初に出てきた順。

    メンバーごとの `originals` があればそれを使い、無ければ旧形式の
    `original`（1 件に 1 つ）で埋める。

    >>> group_by_original([{"original": "sgA", "members": ["a"]},
    ...                    {"original": "sgB", "members": ["b"]},
    ...                    {"original": "sgA", "members": ["c"]}])
    [('sgA', ['a', 'c']), ('sgB', ['b'])]
    >>> group_by_original([{"members": ["a", "b"],
    ...                     "originals": ["sgA", "sgB"]}])
    [('sgA', ['a']), ('sgB', ['b'])]
    >>> group_by_original([{"original": "sgA", "members": []}])
    []
    """
    groups = {}
    order = []
    for record in records or []:
        pairs = align_originals(record.get("members"),
                                record.get("originals"),
                                record.get("original") or "")
        for member, original in pairs:
            if original not in groups:
                groups[original] = []
                order.append(original)
            groups[original].append(member)
    return [(key, groups[key]) for key in order if groups[key]]


def index_by_object(records):
    """対象名から記録を引く索引（フルパス・短い名前・メンバー名で引ける）。

    **一時解除中は対象が元の SG に戻っているので、現在の割り当てを辿っても
    オーバーライドを見つけられない。** 見つけ損なうと掛け直しで 2 本目の
    シェーダーを作ってしまい、元のマテリアルの記録が二重になる。 それを
    防ぐため、シーンの割り当てではなく記録側から引く。

    >>> idx = index_by_object([{"target": "|grp|a",
    ...                         "members": ["|grp|a|aShape"]}])
    >>> idx["|grp|a"] is idx["a"] is idx["|grp|a|aShape"]
    True
    >>> "nope" in idx
    False
    """
    index = {}
    for record in records or []:
        names = [record.get("target")] + list(record.get("members") or [])
        for name in names:
            if not name:
                continue
            index.setdefault(name, record)
            index.setdefault(short_name(name), record)
    return index
