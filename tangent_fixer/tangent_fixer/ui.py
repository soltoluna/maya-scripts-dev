# -*- coding: utf-8 -*-
"""Tangent Fixer — `maya.cmds` による UI とカーブへの書き込み。

傾きの計算は全部 `core`（Maya 非依存・テスト済み）にある。 ここは
「カーブからキーを読む → `core.plan_curve` に渡す → 返ってきた傾きを
タンジェント角にして書く」だけ。

**角度の単位は実機で確定していない**ので、カーブごとに 1 区間だけ
タンジェントを Linear にして角度を実測し、倍率を逆算してから書く
（`core.scale_from_measurement`）。 測れないときは秒基準の仮定
（`core.default_angle_scale`）に落とし、止めずに続ける。
"""

from __future__ import annotations

import math

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)          # ntk_tangent_fixer

WINDOW = _NS + "Win"

_OPTVAR_END_MODE = _NS + "_end_mode"           # ntk_tangent_fixer_end_mode

_PROBE_NODE = _NS + "_probe"

# 書き換えない出力タンジェント（段差のキーは傾きに意味が無い）
_SKIP_OUT_TYPES = ("step", "stepnext")

_END_LABELS = (("Flat", core.END_FLAT), ("Natural", core.END_NATURAL))

_CTRL = {}   # コントロール名の控え。 show() のたびに作り直す


def _log(message):
    print("[%s] %s" % (_PACKAGE, message))


# --------------------------------------------------------------------------- #
# 対象の収集
# --------------------------------------------------------------------------- #

def _collect_targets():
    """`[(curve, target_indices or None), ...]` と、対象の出どころを返す。

    Graph Editor でキーが選択されていればそのキーだけ。 無ければ選択
    オブジェクトのアニメーションカーブの全キー。
    """
    curves = cmds.keyframe(q=True, selected=True, name=True) or []
    if curves:
        targets = []
        for curve in curves:
            indices = cmds.keyframe(curve, q=True, selected=True,
                                    indexValue=True) or []
            targets.append((curve, [int(i) for i in indices]))
        return targets, "selected keys"

    selection = cmds.ls(selection=True) or []
    if not selection:
        return [], None
    curves = cmds.keyframe(selection, q=True, name=True) or []
    return [(c, None) for c in sorted(set(curves))], "selected objects"


def _fps():
    unit = cmds.currentUnit(q=True, time=True)
    return core.fps_from_time_unit(unit), unit


# --------------------------------------------------------------------------- #
# 書き込み
# --------------------------------------------------------------------------- #

def _measure_scale(curve, times, values, target_indices):
    """カーブ 1 本の「傾き → 角度」の倍率を実測する。 測れなければ None。

    対象キーのどれかのタンジェントを一時的に Linear にして角度を読む。
    対象キーはこの後すぐに上書きするので後片付けは要らない。
    """
    seg = core.segment_slopes(times, values)
    pick = core.pick_calibration_segment(seg, target_indices)
    if pick is None:
        return None
    index, side = pick
    if side == "out":
        cmds.keyTangent(curve, edit=True, index=(index, index),
                        outTangentType="linear")
        angle = cmds.keyTangent(curve, q=True, index=(index, index),
                                outAngle=True)
    else:
        cmds.keyTangent(curve, edit=True, index=(index, index),
                        inTangentType="linear")
        angle = cmds.keyTangent(curve, q=True, index=(index, index),
                                inAngle=True)
    if not angle:
        return None
    return core.scale_from_measurement(float(angle[0]),
                                       seg[core.segment_for(index, side)])


def _fix_curve(curve, target_indices, end_mode, fallback_scale):
    """1 本のカーブを直す。 `(書き換えたキー数, 段差で飛ばした数, 倍率, 実測か)`。"""
    times = cmds.keyframe(curve, q=True, timeChange=True) or []
    values = cmds.keyframe(curve, q=True, valueChange=True) or []
    if len(times) < 2:
        return 0, 0, None, False

    plan = core.plan_curve(times, values, target_indices, end_mode=end_mode)
    out_types = cmds.keyTangent(curve, q=True, outTangentType=True) or []
    skipped = [i for i, _ in plan
               if i < len(out_types) and out_types[i] in _SKIP_OUT_TYPES]
    plan = [(i, m) for i, m in plan if i not in skipped]
    if not plan:
        return 0, len(skipped), None, False

    scale = _measure_scale(curve, times, values, [i for i, _ in plan])
    measured = scale is not None
    if not measured:
        scale = fallback_scale

    for index, slope in plan:
        angle = core.slope_to_angle(slope, scale)
        cmds.keyTangent(curve, edit=True, index=(index, index),
                        inTangentType="fixed", outTangentType="fixed")
        cmds.keyTangent(curve, edit=True, absolute=True, index=(index, index),
                        inAngle=angle, outAngle=angle)
        cmds.keyTangent(curve, edit=True, index=(index, index), lock=True)
    return len(plan), len(skipped), scale, measured


def fix(end_mode=None):
    """選択キー（無ければ選択オブジェクトの全キー）のタンジェントを直す。

    ホットキーやシェルフから直接呼べる。 戻り値は結果の 1 行要約。
    """
    if end_mode is None:
        end_mode = _saved_end_mode()

    targets, source = _collect_targets()
    if not targets:
        cmds.warning("[%s] キーかアニメーションのあるオブジェクトを"
                     "選択してください。" % (_PACKAGE,))
        return None

    fps, unit = _fps()
    fallback = core.default_angle_scale(fps)

    n_curves = n_keys = n_skipped = 0
    weighted = []
    failed = []
    unmeasured = []
    cmds.undoInfo(openChunk=True, chunkName="%s fix" % (_PACKAGE,))
    try:
        for curve, indices in targets:
            try:
                keys, skipped, scale, measured = _fix_curve(
                    curve, indices, end_mode, fallback)
            except Exception as exc:   # 1 本の失敗で全体を止めない
                failed.append((curve, exc))
                continue
            if keys:
                n_curves += 1
                n_keys += keys
                if not measured:
                    unmeasured.append(curve)
                if (cmds.keyTangent(curve, q=True, weightedTangents=True)
                        or [False])[0]:
                    weighted.append(curve)
                _log("%s: %d key(s), scale=%.6g (%s, default=%.6g)"
                     % (curve, keys, scale,
                        "measured" if measured else "fallback", fallback))
            n_skipped += skipped
    finally:
        cmds.undoInfo(closeChunk=True)

    summary = "%d key(s) on %d curve(s) from %s" % (n_keys, n_curves, source)
    if n_skipped:
        summary += ", %d stepped key(s) skipped" % (n_skipped,)
    _log(summary + "  [time unit: %s]" % (unit,))
    for curve, exc in failed:
        cmds.warning("[%s] %s: %s" % (_PACKAGE, curve, exc))
    if weighted:
        cmds.warning("[%s] ウェイト付きタンジェントのカーブが %d 本あります。 "
                     "ウェイトは変えないので、はみ出しが残ることがあります: %s"
                     % (_PACKAGE, len(weighted), ", ".join(weighted[:5])))
    if failed:
        summary += ", %d curve(s) failed" % (len(failed),)
    _set_status(summary)
    return summary


# --------------------------------------------------------------------------- #
# 調査関数（実機の単位を持ち帰る）
# --------------------------------------------------------------------------- #

def _safe(func, *args, **kwargs):
    """例外を上げずに `<ERROR ...>` を値として返す（調査を最後まで出すため）。"""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        return "<ERROR %s: %s>" % (type(exc).__name__, exc)


def _probe_curve(curve, fps, max_keys=12):
    lines = ["  curve: %s  type=%s  weighted=%s" % (
        curve, _safe(cmds.nodeType, curve),
        _safe(cmds.keyTangent, curve, q=True, weightedTangents=True))]
    times = _safe(cmds.keyframe, curve, q=True, timeChange=True)
    values = _safe(cmds.keyframe, curve, q=True, valueChange=True)
    if not isinstance(times, list) or not isinstance(values, list):
        lines.append("    times=%r values=%r" % (times, values))
        return lines
    seg = _safe(core.segment_slopes, times, values)
    for i in range(min(len(times), max_keys)):
        q = {}
        for flag in ("inTangentType", "outTangentType", "inAngle", "outAngle",
                     "ix", "iy", "ox", "oy", "inWeight", "outWeight", "lock"):
            q[flag] = _safe(cmds.keyTangent, curve, q=True, index=(i, i),
                            **{flag: True})
        lines.append("    [%d] t=%r v=%r %r" % (i, times[i], values[i], q))
        # Linear の出力タンジェントなら、どの単位の仮定が合うかを並べる
        ott = q["outTangentType"]
        oa = q["outAngle"]
        if (isinstance(seg, list) and i < len(seg) and isinstance(ott, list)
                and ott and ott[0] == "linear" and isinstance(oa, list)):
            s = seg[i]
            lines.append(
                "        linear: measured scale=%r  hyp(frame)=1  hyp(sec)=%r"
                "  hyp(sec,rad)=%r" % (
                    core.scale_from_measurement(float(oa[0]), s), fps,
                    (fps or 1.0) * math.pi / 180.0))
    return lines


def probe(try_it=False):
    """実機の単位とタンジェントの値を Script Editor に出す（不具合の切り分け用）。

        import tangent_fixer
        tangent_fixer.probe()              # 選択中のカーブを読むだけ（安全）
        tangent_fixer.probe(try_it=True)   # 一時ノードを作って試し、消す

    出力をそのまま貼ってもらう前提。 途中で失敗しても `<ERROR ...>` を値に
    して最後まで出す。
    """
    fps, unit = _fps()
    lines = ["===== %s probe v%s =====" % (_PACKAGE, __version__),
             "maya=%s  time=%s fps=%r  linear=%s  angle=%s" % (
                 _safe(cmds.about, version=True), unit, fps,
                 _safe(cmds.currentUnit, q=True, linear=True),
                 _safe(cmds.currentUnit, q=True, angle=True))]

    collected = _safe(_collect_targets)
    if isinstance(collected, str):
        lines.append("collect: %s" % (collected,))
        collected = ([], None)
    targets, source = collected
    lines.append("targets from %s: %d curve(s)" % (source, len(targets)))
    for curve, indices in targets[:6]:
        lines.append("  selected indices: %r" % (indices,))
        lines.extend(_probe_curve(curve, fps))

    if try_it:
        lines.extend(_probe_try(fps))

    lines.append("===== end =====")
    text = "\n".join(lines)
    print(text)
    return text


def _probe_try(fps):
    """一時ノードに直線と山のキーを打ち、実測と書き込み結果を出して消す。"""
    lines = ["--- try_it ---"]
    node = None
    cmds.undoInfo(openChunk=True, chunkName="%s probe" % (_PACKAGE,))
    try:
        node = cmds.createNode("transform", name=_PROBE_NODE)
        keys = {"translateX": [(0, 0.0), (24, 10.0)],
                "rotateX": [(0, 0.0), (24, 90.0)],
                "translateY": [(0, 0.0), (10, 10.0), (20, 9.0), (30, 0.0)]}
        for attr, pairs in keys.items():
            for t, v in pairs:
                _safe(cmds.setKeyframe, node, attribute=attr, time=t, value=v,
                      inTangentType="linear", outTangentType="linear")
        for attr in ("translateX", "rotateX"):
            curve = (_safe(cmds.keyframe, node, attribute=attr, q=True,
                           name=True) or ["?"])
            curve = curve[0] if isinstance(curve, list) else curve
            lines.extend(_probe_curve(curve, fps, max_keys=2))

        ty = _safe(cmds.keyframe, node, attribute="translateY", q=True,
                   name=True)
        if isinstance(ty, list) and ty:
            curve = ty[0]
            result = _safe(_fix_curve, curve, None, core.END_FLAT,
                           core.default_angle_scale(fps))
            lines.append("  fix translateY -> %r" % (result,))
            lines.extend(_probe_curve(curve, fps, max_keys=4))
            samples = []
            for t in (5, 12, 15, 18, 25):
                samples.append((t, _safe(cmds.keyframe, curve, q=True,
                                         eval=True, time=(t, t))))
            lines.append("  eval (keys 0,10,9,0 @ 0,10,20,30): %r" % (samples,))
    except Exception as exc:
        lines.append("  <ERROR %s: %s>" % (type(exc).__name__, exc))
    finally:
        if node and cmds.objExists(node):
            _safe(cmds.delete, node)
        cmds.undoInfo(closeChunk=True)
    return lines


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _saved_end_mode():
    if cmds.optionVar(exists=_OPTVAR_END_MODE):
        value = cmds.optionVar(q=_OPTVAR_END_MODE)
        if value in core.END_MODES:
            return value
    return core.END_FLAT


def _on_end_mode_changed(*_args):
    selected = cmds.radioButtonGrp(_CTRL["end"], q=True, select=True) or 1
    selected = max(1, min(len(_END_LABELS), int(selected)))
    mode = _END_LABELS[selected - 1][1]
    cmds.optionVar(sv=(_OPTVAR_END_MODE, mode))


def _on_fix(*_args):
    fix()


def _set_status(message):
    ctrl = _CTRL.get("status")
    if ctrl and cmds.text(ctrl, exists=True):
        cmds.text(ctrl, e=True, label=message)


def _build_body():
    mode = _saved_end_mode()
    selected = [m for _, m in _END_LABELS].index(mode) + 1

    cmds.separator(h=4, style="none")
    cmds.text(l="キーを選択（無ければオブジェクトを選択）して Fix。\n"
                "極値はフラット、中間キーは前後に滑らかにつなぎ、\n"
                "キーに無いオーバーシュートを作らない。",
              align="left")
    _CTRL["end"] = cmds.radioButtonGrp(
        label="End Keys", labelArray2=[l for l, _ in _END_LABELS],
        numberOfRadioButtons=2, select=selected, cw3=(70, 70, 70),
        changeCommand=_on_end_mode_changed,
        annotation="Flat: 端のキーは水平 / Natural: 端も隣のキーへ向ける")
    cmds.button(l="Fix Tangents", h=32, c=_on_fix)
    _CTRL["status"] = cmds.text(l="", align="left")


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    win = cmds.window(WINDOW,
                      title="Tangent Fixer  —  v%s" % (__version__,),
                      widthHeight=(320, 190),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    return win
