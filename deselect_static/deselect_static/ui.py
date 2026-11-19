# -*- coding: utf-8 -*-
"""Deselect Static — `maya.cmds` による UI。

ここは「`cmds.keyframe` で値を集める → `core` に渡す → 結果を `cmds.select` に
流す」だけに保つ。 判定は `core.py` にある（自宅に Maya が無いので、
`core` に無い処理は実機に持っていくまで一度も実行されない）。
"""

from __future__ import annotations

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


# Maya の optionVar / scriptJob / ウィンドウ名はフラットな 1 つの名前空間を
# 共有するので、必ず `<NAMESPACE>_<モジュール名>` を付ける（組み立てで付ける）
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)          # 例: ntk_deselect_static

# install.py の `_close_existing_window()` が同じ規則で古いウィンドウを探す
WINDOW = _NS + "Win"

_OPTVAR_TOLERANCE = _NS + "_tolerance"         # 例: ntk_deselect_static_tolerance

_CTRL = {}   # コントロール名の控え。 show() のたびに作り直す


def _log(message):
    print("[%s] %s" % (_PACKAGE, message))


def _safe_list(func, *args, **kwargs):
    """`cmds.*` の照会を、失敗・None でも空リストで返す。"""
    try:
        return list(func(*args, **kwargs) or [])
    except RuntimeError:
        return []


# --------------------------------------------------------------------------- #
# 本体
# --------------------------------------------------------------------------- #

def _load_tolerance():
    if cmds.optionVar(exists=_OPTVAR_TOLERANCE):
        return core.normalize_tolerance(cmds.optionVar(q=_OPTVAR_TOLERANCE))
    return core.DEFAULT_TOLERANCE


def _collect(objects):
    """`(source, values_by_object, selected_indices, curves_by_object)` を返す。

    selected_indices は `{curve: [index, ...]}`（選択キーで判定したときだけ。
    選択を変えた後にキー選択を戻すのに使う）。 curves_by_object は
    `{obj: [curve, ...]}`。
    """
    curves_by_object = {}
    for obj in objects:
        curves = _safe_list(cmds.keyframe, obj, q=True, name=True)
        curves_by_object[obj] = sorted(set(curves))

    selected_curves = _safe_list(cmds.keyframe, q=True, selected=True,
                                 name=True)
    source = core.choose_source(curves_by_object, selected_curves)
    selected_set = set(selected_curves)

    values_by_object = {}
    selected_indices = {}
    for obj, curves in curves_by_object.items():
        rows = []
        for curve in curves:
            if source == core.SOURCE_SELECTED_KEYS:
                if curve not in selected_set:
                    continue
                values = _safe_list(cmds.keyframe, curve, q=True,
                                    selected=True, valueChange=True)
                selected_indices[curve] = [
                    int(i) for i in _safe_list(cmds.keyframe, curve, q=True,
                                               selected=True, indexValue=True)]
            else:
                values = _safe_list(cmds.keyframe, curve, q=True,
                                    valueChange=True)
            rows.append(values)
        values_by_object[obj] = rows
    return source, values_by_object, selected_indices, curves_by_object


def _restore_key_selection(changed, curves_by_object, selected_indices):
    """オブジェクト選択を変えたあと、残したオブジェクトのキー選択を戻す。

    戻せなくても主機能（オブジェクトの選択解除）は済んでいるので、警告だけ出す。
    """
    try:
        cmds.selectKey(clear=True)
        for obj in changed:
            for curve in curves_by_object.get(obj, []):
                for index in selected_indices.get(curve, []):
                    cmds.selectKey(curve, add=True, index=(index, index))
    except RuntimeError as exc:
        cmds.warning("[%s] キー選択を戻せませんでした: %s" % (_PACKAGE, exc))


def deselect_static(tolerance=None):
    """選択オブジェクトのうち、キー値に変化が無いものの選択を外す。

    Graph Editor / Dope Sheet でキーが選択されていればそのキーだけで、
    無ければ全キーで判定する。 UI を開かずにホットキーなどから呼んでもよい。

    Returns:
        `(changed, static)` — 残したオブジェクトと外したオブジェクト。
    """
    if tolerance is None:
        tolerance = _load_tolerance()
    tolerance = core.normalize_tolerance(tolerance)

    objects = cmds.ls(selection=True, long=True) or []
    if not objects:
        cmds.warning("[%s] オブジェクトが選択されていません。" % (_PACKAGE,))
        return [], []

    source, values_by_object, selected_indices, curves_by_object = \
        _collect(objects)
    changed, static = core.split_by_change(objects, values_by_object,
                                           tolerance)

    # 選択の変更とキー選択の復元を 1 回の undo にまとめる。
    # openChunk したら例外が出ても必ず closeChunk する
    cmds.undoInfo(openChunk=True, chunkName="%s" % (_PACKAGE,))
    try:
        if changed:
            cmds.select(changed, replace=True)
        else:
            cmds.select(clear=True)
        if source == core.SOURCE_SELECTED_KEYS and changed:
            _restore_key_selection(changed, curves_by_object, selected_indices)
    finally:
        cmds.undoInfo(closeChunk=True)

    message = core.summary_message(changed, static, source)
    _log(message)
    for obj in static:
        _log("  deselected: %s" % (obj,))
    try:
        cmds.inViewMessage(amg=message, pos="topCenter", fade=True)
    except RuntimeError:
        pass
    return changed, static


# --------------------------------------------------------------------------- #
# コールバック
# --------------------------------------------------------------------------- #

def _on_apply(*_args):
    tolerance = core.normalize_tolerance(
        cmds.floatFieldGrp(_CTRL["tolerance"], q=True, value1=True))
    cmds.optionVar(fv=(_OPTVAR_TOLERANCE, tolerance))
    deselect_static(tolerance)


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _build_body():
    cmds.separator(h=4, style="none")
    cmds.text(l="キーが選択されていればそのキーで、無ければ全キーで判定し、\n"
                "値が変化しないオブジェクトの選択を外します。",
              align="left")
    _CTRL["tolerance"] = cmds.floatFieldGrp(
        label="Tolerance", numberOfFields=1, value1=_load_tolerance(),
        precision=6, cw2=(70, 120),
        ann="キー値の 最大 - 最小 がこの値以下なら「変化なし」とみなす")
    cmds.button(l="Deselect Static", h=32, c=_on_apply)


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    win = cmds.window(WINDOW,
                      title="Deselect Static  —  v%s" % (__version__,),
                      widthHeight=(340, 170),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    return win
