# -*- coding: utf-8 -*-
"""Deselect Static — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** 開発機に Maya が無い以上、
ここに寄せた処理だけが自宅で実行・テストできる。

ui.py が `cmds.keyframe` で集めた「オブジェクトごとのキー値の列」を受け取り、
値が動いているオブジェクトと動いていないオブジェクトに振り分ける。
"""

from __future__ import annotations

# 既定の許容誤差。 キー値の最大 - 最小がこれ以下なら「変化なし」と見なす
DEFAULT_TOLERANCE = 1e-4

# 判定に使ったキーの出どころ
SOURCE_SELECTED_KEYS = "selected keys"
SOURCE_ALL_KEYS = "all keys"


def normalize_tolerance(value, default=DEFAULT_TOLERANCE):
    """UI から来た許容誤差を、0 以上の float に整える。

    数値として読めなければ `default`。 負の値は絶対値にする
    （「どれだけずれたら変化とみなすか」なので符号に意味は無い）。
    """
    try:
        tol = float(value)
    except (TypeError, ValueError):
        return float(default)
    if tol != tol:  # NaN
        return float(default)
    return abs(tol)


def has_change(values, tolerance=DEFAULT_TOLERANCE):
    """キー値の列に、許容誤差を超える変化があるか。

    >>> has_change([1.0, 1.0, 1.0])
    False
    >>> has_change([0.0, 0.5])
    True

    キーが 0〜1 個なら変化は無い。 判定は「最大 - 最小 > 許容誤差」で、
    隣同士の差ではなく列全体の幅を見る（ゆっくり漂うカーブを取りこぼさない）。
    """
    vals = [float(v) for v in (values or [])]
    if len(vals) < 2:
        return False
    return (max(vals) - min(vals)) > tolerance


def choose_source(curves_by_object, selected_curves):
    """判定にどのキーを使うかを決める。

    Graph Editor / Dope Sheet でキーが選択されていて、そのカーブが選択
    オブジェクトのものなら `SOURCE_SELECTED_KEYS`。 それ以外は
    `SOURCE_ALL_KEYS`（選択オブジェクトのカーブの全キー）。

    キー選択があっても選択オブジェクトのカーブと 1 本も重ならないときは、
    全オブジェクトを外してしまわないよう全キーに落とす。
    """
    selected = set(selected_curves or [])
    if not selected:
        return SOURCE_ALL_KEYS
    for curves in (curves_by_object or {}).values():
        if selected.intersection(curves or []):
            return SOURCE_SELECTED_KEYS
    return SOURCE_ALL_KEYS


def split_by_change(objects, values_by_object, tolerance=DEFAULT_TOLERANCE):
    """オブジェクトを「変化あり」と「変化なし」に分ける。

    Args:
        objects: 選択オブジェクト名のリスト（この順序を保つ）。
        values_by_object: `{オブジェクト名: [カーブ 1 本分のキー値の列, ...]}`。
            キーが無い（判定対象のキーが無い）オブジェクトは欠けていてよい。
        tolerance: 許容誤差。

    Returns:
        `(changed, static)`。 いずれかのカーブが変化していれば changed。
        判定対象のキーが 1 本も無いオブジェクトは static に入る。
    """
    changed = []
    static = []
    seen = set()
    for obj in objects or []:
        if obj in seen:
            continue
        seen.add(obj)
        curves = (values_by_object or {}).get(obj) or []
        if any(has_change(values, tolerance) for values in curves):
            changed.append(obj)
        else:
            static.append(obj)
    return changed, static


def summary_message(changed, static, source):
    """結果を 1 行で返す（Script Editor / inViewMessage 用）。"""
    label = "選択キー" if source == SOURCE_SELECTED_KEYS else "全キー"
    return "%s で判定: %d 個を残し、%d 個の選択を解除しました。" % (
        label, len(changed), len(static))
