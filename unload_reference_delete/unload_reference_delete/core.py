# -*- coding: utf-8 -*-
"""Unload Reference Delete — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** 開発機に Maya が無いので、
ここに寄せた処理だけが自宅で実行・テストできる。

このツールで「判断」に当たるのは次の 3 つで、すべてここにある:

1. どのリファレンスが削除対象か（アンロード中か）
2. 親ごと消えるので触らなくてよいのはどれか（入れ子のリファレンス）
3. リファレンスノードが引けず、そもそも消せないのはどれか

`ui.py` は `cmds` で `ReferenceEntry` を組み立て、`plan_removal()` に渡し、
返ってきた `targets` を消すだけに保つ。
"""

from __future__ import annotations

import posixpath
import re
from collections import namedtuple


# Maya は同じファイルを複数回参照すると、パスの末尾にコピー番号を付ける
# （`.../char_rig.ma{1}`）。 表示するときは邪魔なので分けて扱う
_COPY_SUFFIX = re.compile(r"\{(\d+)\}$")


ReferenceEntry = namedtuple(
    "ReferenceEntry",
    ("reference_node", "file_path", "is_loaded", "parent_node"))
# `parent_node` は省略可（実 Maya から親を引けなかった場合は None）
ReferenceEntry.__new__.__defaults__ = (None,)

RemovalPlan = namedtuple("RemovalPlan", ("targets", "nested", "unresolved"))
"""`plan_removal()` の結果。

* `targets`    — 実際に `removeReference` を呼ぶもの
* `nested`     — アンロード中だが、祖先も削除対象なので触らなくてよいもの
* `unresolved` — アンロード中だが、リファレンスノードが引けず消せないもの
"""


# --------------------------------------------------------------------------- #
# 表示
# --------------------------------------------------------------------------- #

def split_copy_number(file_path):
    """`.../char_rig.ma{1}` を `('.../char_rig.ma', 1)` に分ける。

    >>> split_copy_number("C:/p/char_rig.ma{1}")
    ('C:/p/char_rig.ma', 1)
    >>> split_copy_number("C:/p/char_rig.ma")
    ('C:/p/char_rig.ma', None)
    """
    path = file_path or ""
    found = _COPY_SUFFIX.search(path)
    if not found:
        return (path, None)
    return (path[:found.start()], int(found.group(1)))


def file_base_name(file_path):
    """パスとコピー番号を落としたファイル名。

    >>> file_base_name("C:/proj/scenes/char_rig.ma{2}")
    'char_rig.ma'
    """
    path, _copy = split_copy_number(file_path)
    return posixpath.basename(path.replace("\\", "/"))


def display_label(entry):
    """一覧に 1 行で出す文字列。

    >>> display_label(ReferenceEntry("charRN", "C:/p/char.ma{1}", False))
    'char.ma  {1}   [charRN]'
    """
    name = file_base_name(entry.file_path) or "(unknown)"
    _path, copy = split_copy_number(entry.file_path)
    copy_text = "  {%d}" % (copy,) if copy is not None else ""
    node = entry.reference_node or "?"
    return "%s%s   [%s]" % (name, copy_text, node)


# --------------------------------------------------------------------------- #
# 判断
# --------------------------------------------------------------------------- #

def plan_removal(entries):
    """`ReferenceEntry` の一覧から `RemovalPlan` を組み立てる。

    削除対象は「アンロード中で」「祖先が削除対象でなく」「リファレンス
    ノードが分かっている」もの。

    入れ子を除くのは、**親を消すと子も一緒に消える**ため。 残したまま
    `removeReference` を呼ぶと、既に無いノードを指してエラーになる。
    親子関係が取れなかった場合（`parent_node` が None）はすべて独立した
    リファレンスとして扱う — 実機で親が引けなくても、多めに消そうとして
    個別に失敗するだけで済む。
    """
    entries = list(entries)
    by_node = {e.reference_node: e for e in entries if e.reference_node}

    targets, nested, unresolved = [], [], []
    for entry in entries:
        if entry.is_loaded:
            continue
        if _has_unloaded_ancestor(entry, by_node):
            nested.append(entry)
        elif not entry.reference_node:
            unresolved.append(entry)
        else:
            targets.append(entry)
    return RemovalPlan(targets, nested, unresolved)


def _has_unloaded_ancestor(entry, by_node):
    """祖先をたどって、アンロード中のものがあるか。

    `parent_node` が壊れていて輪になっていても止まるようにしてある
    （実機のデータを信用しきらない）。 **自分自身は祖先に数えない** —
    輪の中で自分に戻ってきたときに「親がアンロード中」と誤判定すると、
    本来消せるはずの参照が永久に消せなくなる。
    """
    seen = {entry.reference_node}
    node = entry.parent_node
    while node and node in by_node and node not in seen:
        seen.add(node)
        parent = by_node[node]
        if not parent.is_loaded:
            return True
        node = parent.parent_node
    return False


# --------------------------------------------------------------------------- #
# 文言
# --------------------------------------------------------------------------- #

def format_plan(plan):
    """確認ダイアログに出す本文。 何を消すのかを名指しで見せる。"""
    lines = ["以下 %d 件のリファレンスを削除します（undo できません）:"
             % (len(plan.targets),), ""]
    lines += ["  - %s" % (display_label(e),) for e in plan.targets]
    if plan.nested:
        lines += ["", "親ごと消えるため個別には削除しません: %d 件"
                  % (len(plan.nested),)]
    if plan.unresolved:
        lines += ["", "リファレンスノードが引けず削除できません: %d 件"
                  % (len(plan.unresolved),)]
        lines += ["  - %s" % (e.file_path,) for e in plan.unresolved]
    return "\n".join(lines)


def format_result(removed, failed):
    """実行後の報告。 `failed` は `(entry, エラー文字列)` の並び。"""
    lines = ["削除: %d 件" % (len(removed),)]
    lines += ["  - %s" % (display_label(e),) for e in removed]
    if failed:
        lines += ["", "失敗: %d 件" % (len(failed),)]
        lines += ["  - %s: %s" % (display_label(e), message)
                  for e, message in failed]
    return "\n".join(lines)
