# -*- coding: utf-8 -*-
"""Tool Template — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** それがこのファイルの唯一かつ
最大の役割で、開発機に Maya が無い以上、ここに寄せた処理だけが自宅で実行・
テストできる。

書いてよいもの:
    * 名前の生成・パース・検証（リネーム規則、連番、接頭辞の付け外し）
    * 数値の計算（座標変換、補間、単位変換、しきい値判定）
    * データ構造の組み立て・並べ替え・グルーピング
    * 「選択されたノード名のリスト」を受け取って「やることのリスト」を返す関数

書いてはいけないもの:
    * `from maya import cmds`（`ui.py` の仕事）
    * ノードの生成・削除・属性の読み書き

`ui.py` は「`cmds` で値を集める → `core` に渡す → 返ってきた結果を `cmds` に流す」
だけに保つ。 そうすると UI 側に残る未検証コードが薄くなる。
"""

from __future__ import annotations

import re


# 雛形のサンプル。 最初の機能を実装したら消す。
_TRAILING_DIGITS = re.compile(r"^(?P<stem>.*?)(?P<digits>\d+)$")


def make_numbered_names(base, count, start=1, padding=2):
    """`base` に連番を付けた名前を `count` 個返す。

    >>> make_numbered_names("arm", 3)
    ['arm01', 'arm02', 'arm03']
    >>> make_numbered_names("arm", 2, start=9, padding=3)
    ['arm009', 'arm010']

    Maya のノード名として使えない文字が `base` に含まれていたら `ValueError`。
    実機で `cmds.rename` に弾かれてから気づくより、手元で落ちたほうがよい。
    """
    if count < 0:
        raise ValueError("count must be >= 0: %r" % (count,))
    if padding < 1:
        raise ValueError("padding must be >= 1: %r" % (padding,))
    if not is_valid_node_name(base):
        raise ValueError("invalid node name: %r" % (base,))
    return ["%s%0*d" % (base, padding, start + i) for i in range(count)]


def is_valid_node_name(name):
    """Maya のノード名として使えるか（英数字とアンダースコアで、数字始まり不可）。"""
    if not name:
        return False
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) is not None


def strip_trailing_number(name):
    """末尾の連番を外して `(語幹, 数値 or None)` を返す。

    >>> strip_trailing_number("arm01")
    ('arm', 1)
    >>> strip_trailing_number("arm")
    ('arm', None)
    """
    m = _TRAILING_DIGITS.match(name or "")
    if not m:
        return (name, None)
    return (m.group("stem"), int(m.group("digits")))
