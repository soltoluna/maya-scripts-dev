# -*- coding: utf-8 -*-
"""Tangent Fixer — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** 開発機に Maya が無いので、
ここに寄せた計算だけが自宅でテストできる。

## 何を解いているか

キー列 `(t_i, v_i)` を通る 3 次エルミート曲線の、各キーでの傾き `m_i` を決める。
Maya の非ウェイトタンジェントはハンドル長が区間の 1/3 固定なので、エルミート
補間と同値になる（傾きだけ決めればカーブ形状が決まる）。

既定のタンジェントの課題:

* **Auto**: 極値の間に置いたキーで、傾きの制限が左右で非対称に効き、
  カーブがわずかに歪む
* **Spline**: 左右の平均傾きをそのまま使うので、キーに無いオーバーシュートが出る

各キーの傾きは**前後のキーを通る放物線の接線**を基本にする
（Steffen 法, 1990 と同じ出発点）。 性質:

1. **接線になる** — 中間キーのタンジェントは、前後のキーを滑らかに通る
   曲線のその点での接線。 キー間隔の不均一も重みで考慮する
2. **極値のキーは自動でフラット** — 前後の区間の傾きの符号が変わるキーは 0
3. **はみ出さない（`smooth` / `strict`）** — 接線が区間の傾きの 3 倍
   （`strict` は 2 倍）を超えるときだけ頭打ちにする。 Fritsch–Carlson の
   十分条件で、両端キーの値の範囲から曲線が出ない
4. **C1 連続** — 入出力の傾きを同じにするので、キー位置で折れない
"""

from __future__ import annotations

import math


# 区間の傾きがこれ未満なら「同じ値が続いている」とみなして 0 にする。
# 浮動小数の誤差で極値判定が揺れて、平らなはずの区間が波打つのを防ぐ
SLOPE_EPSILON = 1e-9

END_FLAT = "flat"          # 端のキーは水平
END_NATURAL = "natural"    # 端のキーも隣の区間に沿わせる（はみ出さない範囲で）
END_MODES = (END_FLAT, END_NATURAL)


# --------------------------------------------------------------------------- #
# 傾きの計算（Steffen 法）
# --------------------------------------------------------------------------- #

def _sign(x):
    if x > 0.0:
        return 1.0
    if x < 0.0:
        return -1.0
    return 0.0


def segment_slopes(times, values, epsilon=SLOPE_EPSILON):
    """区間ごとの傾き `s_i = (v_{i+1} - v_i) / (t_{i+1} - t_i)` を返す。

    時間が同じキーが並んでいたら `ValueError`（Maya では起きないはずだが、
    0 除算で黙って壊れるより手元で落ちたほうがよい）。
    """
    _validate(times, values)
    slopes = []
    for i in range(len(times) - 1):
        h = float(times[i + 1]) - float(times[i])
        s = (float(values[i + 1]) - float(values[i])) / h
        slopes.append(0.0 if abs(s) < epsilon else s)
    return slopes


def _validate(times, values):
    if len(times) != len(values):
        raise ValueError("times と values の長さが違う: %d != %d"
                         % (len(times), len(values)))
    for i in range(len(times) - 1):
        if not float(times[i + 1]) > float(times[i]):
            raise ValueError("キーの時間が単調増加でない: index %d (%r -> %r)"
                             % (i, times[i], times[i + 1]))


# 傾きの頭打ちの倍率（区間の傾きに対して）。 Fritsch–Carlson の十分条件で、
# 区間の両端の傾きがどちらも区間の傾きの 3 倍以内なら、その区間の曲線は
# 両端キーの値の範囲からはみ出さない。 Steffen 法の原論文は 2 倍だが、
# 2 倍は必要以上に強く、片側が緩い区間で接線が寝て「歪み」に見える
_LIMIT_SMOOTH = 3.0
_LIMIT_STRICT = 2.0


def parabola_slope(s_prev, s_next, h_prev, h_next):
    """前後のキーを通る放物線の、キー位置での傾き（= その点の接線）。

    前後の区間の傾きを**相手側の区間長**で重み付けした平均。 キー間隔が
    不均一でも、3 キーを滑らかに通る曲線の接線になる。
    """
    return (s_prev * h_next + s_next * h_prev) / (h_prev + h_next)


def _clamp(p, s_prev, s_next, limit):
    """`p` を左右の区間の傾きの `limit` 倍で頭打ちにする（`None` なら素通し）。"""
    if limit is None:
        return p
    bound = limit * min(abs(s_prev), abs(s_next))
    return p if abs(p) <= bound else _sign(p) * bound


def _interior_slope(s_prev, s_next, h_prev, h_next, limit):
    """内側のキーの傾き。

    前後で傾きの符号が変わる（= 極値）か、どちらかが平らなら 0。
    それ以外は放物線の接線を、`limit` が与えられていれば頭打ちにして使う。
    """
    if s_prev * s_next <= 0.0:
        return 0.0
    return _clamp(parabola_slope(s_prev, s_next, h_prev, h_next),
                  s_prev, s_next, limit)


def _natural_end_slope(s_near, s_far, h_near, h_far, limit):
    """端のキーの傾き。

    端から 3 キーを通る放物線の端点での傾き。 区間の傾きと符号が逆なら 0
    （逆向きに出るとはみ出す）。 `limit` があれば区間の傾きの倍数で頭打ち。
    """
    p = s_near * (1.0 + h_near / (h_near + h_far)) - s_far * h_near / (h_near + h_far)
    if p * s_near <= 0.0:
        return 0.0
    if limit is not None and abs(p) > limit * abs(s_near):
        return limit * s_near
    return p


METHOD_SMOOTH = "smooth"     # 接線を優先し、はみ出す分だけ頭打ち（既定）
METHOD_TANGENT = "tangent"   # 接線そのもの。 極値だけ水平（わずかにはみ出し得る）
METHOD_STRICT = "strict"     # Steffen 法の原式（v0.1.0 の挙動）
METHODS = (METHOD_SMOOTH, METHOD_TANGENT, METHOD_STRICT)

_METHOD_LIMIT = {METHOD_SMOOTH: _LIMIT_SMOOTH, METHOD_TANGENT: None,
                 METHOD_STRICT: _LIMIT_STRICT}


def compute_slopes(times, values, end_mode=END_FLAT, method=METHOD_SMOOTH,
                   epsilon=SLOPE_EPSILON):
    """各キーのタンジェントの傾き（値 / 時間）を返す。

    入出力は同じ傾き（C1 連続）にするので、1 キーに 1 つの値を返す。
    単位は `times` と `values` の単位そのまま（フレームを渡せば 値/フレーム）。

    method:
        * `smooth`  — 前後のキーを通る放物線の接線。 区間の傾きの 3 倍を
          超えるとはみ出すので、そのときだけ頭打ち（はみ出し 0 を保証）
        * `tangent` — 放物線の接線そのもの。 極値だけ水平。 隣のキーとの
          傾きの差が大きい箇所ではわずかにはみ出すことがある
        * `strict`  — Steffen 法の原式（2 倍で頭打ち。 v0.1.0 の挙動）

    >>> compute_slopes([0, 10, 20], [0, 10, 0])    # 山の頂点はフラット
    [0.0, 0.0, 0.0]
    >>> compute_slopes([0, 10, 20], [0, 5, 10])    # 直線上なら直線の傾き
    [0.0, 0.5, 0.0]
    """
    if end_mode not in END_MODES:
        raise ValueError("end_mode は %r のどれか: %r" % (END_MODES, end_mode))
    if method not in METHODS:
        raise ValueError("method は %r のどれか: %r" % (METHODS, method))
    limit = _METHOD_LIMIT[method]
    n = len(times)
    _validate(times, values)
    if n < 2:
        return [0.0] * n

    s = segment_slopes(times, values, epsilon)
    h = [float(times[i + 1]) - float(times[i]) for i in range(n - 1)]

    slopes = [0.0] * n
    for i in range(1, n - 1):
        slopes[i] = _interior_slope(s[i - 1], s[i], h[i - 1], h[i], limit)

    if end_mode == END_NATURAL:
        if n == 2:
            slopes[0] = slopes[1] = s[0]       # 2 キーだけなら直線
        else:
            slopes[0] = _natural_end_slope(s[0], s[1], h[0], h[1], limit)
            # 右端は左右を入れ替えた同じ式（向きを反転しても符号は相殺する）
            slopes[-1] = _natural_end_slope(s[-1], s[-2], h[-1], h[-2], limit)
    return [0.0 if abs(m) < epsilon else m for m in slopes]

# --------------------------------------------------------------------------- #
# 検算（テストと調査関数で使う）
# --------------------------------------------------------------------------- #

def hermite(t, t0, t1, v0, v1, m0, m1):
    """区間 `[t0, t1]` の 3 次エルミート曲線の値（Maya の非ウェイト曲線と同値）。"""
    h = float(t1 - t0)
    u = (t - t0) / h
    u2 = u * u
    u3 = u2 * u
    return ((2 * u3 - 3 * u2 + 1) * v0 + (u3 - 2 * u2 + u) * h * m0
            + (-2 * u3 + 3 * u2) * v1 + (u3 - u2) * h * m1)


def max_overshoot(times, values, slopes, samples=32):
    """各区間で、曲線が両端キーの値の範囲からはみ出した量の最大値を返す。

    0 なら「キーとして打っていないオーバーシュートが無い」。
    """
    worst = 0.0
    for i in range(len(times) - 1):
        lo = min(values[i], values[i + 1])
        hi = max(values[i], values[i + 1])
        for k in range(1, samples):
            t = times[i] + (times[i + 1] - times[i]) * k / float(samples)
            v = hermite(t, times[i], times[i + 1], values[i], values[i + 1],
                        slopes[i], slopes[i + 1])
            worst = max(worst, lo - v, v - hi)
    return worst


# --------------------------------------------------------------------------- #
# Maya のタンジェント角への変換
# --------------------------------------------------------------------------- #

# `cmds.currentUnit(q=True, time=True)` の名前 → 1 秒あたりの単位数
_TIME_UNIT_FPS = {
    "game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0, "show": 48.0,
    "palf": 50.0, "ntscf": 60.0,
    "hour": 1.0 / 3600.0, "min": 1.0 / 60.0, "sec": 1.0, "millisec": 1000.0,
    "2fps": 2.0, "3fps": 3.0, "4fps": 4.0, "5fps": 5.0, "6fps": 6.0,
    "8fps": 8.0, "10fps": 10.0, "12fps": 12.0, "16fps": 16.0, "20fps": 20.0,
    "40fps": 40.0, "75fps": 75.0, "80fps": 80.0, "100fps": 100.0,
    "120fps": 120.0, "125fps": 125.0, "150fps": 150.0, "200fps": 200.0,
    "240fps": 240.0, "250fps": 250.0, "300fps": 300.0, "375fps": 375.0,
    "400fps": 400.0, "500fps": 500.0, "600fps": 600.0, "750fps": 750.0,
    "1200fps": 1200.0, "1500fps": 1500.0, "2000fps": 2000.0,
    "3000fps": 3000.0, "6000fps": 6000.0,
    "23.976fps": 24000.0 / 1001.0, "29.97fps": 30000.0 / 1001.0,
    "29.97df": 30000.0 / 1001.0, "47.952fps": 48000.0 / 1001.0,
    "59.94fps": 60000.0 / 1001.0, "44100fps": 44100.0, "48000fps": 48000.0,
}


def fps_from_time_unit(unit):
    """時間単位名から fps を返す。 知らない名前は `"<数値>fps"` として読み、
    それも無理なら `None`。"""
    if not unit:
        return None
    key = str(unit).strip().lower()
    if key in _TIME_UNIT_FPS:
        return _TIME_UNIT_FPS[key]
    for suffix in ("fps", "df"):
        if key.endswith(suffix):
            try:
                return float(key[:-len(suffix)])
            except ValueError:
                return None
    return None


def default_angle_scale(fps):
    """傾き（値/フレーム）→ Maya のタンジェント角の計算に掛ける倍率の既定値。

    Maya のタンジェント角は**時間を秒で測った**傾きの atan とされているので、
    値/フレーム に fps を掛ける。 **実機で確定していない仮定**なので、`ui` は
    カーブごとに実測した倍率（`scale_from_measurement`）を優先し、測れない
    ときだけこれに落とす。
    """
    return float(fps) if fps else 1.0


def scale_from_measurement(angle_deg, slope, epsilon=SLOPE_EPSILON):
    """実測から倍率を逆算する。

    あるキーのタンジェントを Linear にすると、隣のキーへ向いた直線になる。
    そのときの角度 `angle_deg` と区間の傾き `slope`（値/フレーム）から
    `tan(angle) = slope * scale` を解く。 時間・角度の単位が何であっても
    これで吸収できる。 求まらなければ `None`。
    """
    if abs(slope) < epsilon:
        return None
    if abs(abs(angle_deg) - 90.0) < 1e-6:
        return None
    scale = math.tan(math.radians(angle_deg)) / slope
    if not math.isfinite(scale) or scale <= 0.0:
        return None
    return scale


def slope_to_angle(slope, scale):
    """傾き（値/フレーム）を Maya のタンジェント角（度）にする。"""
    return math.degrees(math.atan(slope * scale))


def pick_calibration_segment(slopes, target_indices):
    """倍率を実測するのに使う区間を選ぶ。

    対象キーのうち、隣の区間の傾きが最も大きいもの（測定誤差が小さい）を
    `(キー index, "out" | "in")` で返す。 対象キーのタンジェントは
    どうせ上書きするので、測定で一時的に Linear にしても後片付けが要らない。
    全部 0 なら `None`（その場合は傾きも全部 0 で、倍率は結果に効かない）。

    `slopes` は `segment_slopes` の戻り値（区間ごと）。
    """
    best = None
    best_abs = 0.0
    n_keys = len(slopes) + 1
    for i in sorted(set(target_indices)):
        candidates = []
        if i < n_keys - 1:
            candidates.append((abs(slopes[i]), "out"))
        if i > 0:
            candidates.append((abs(slopes[i - 1]), "in"))
        for magnitude, side in candidates:
            if magnitude > best_abs:
                best, best_abs = (i, side), magnitude
    return best


def segment_for(index, side):
    """`pick_calibration_segment` の結果に対応する区間 index。"""
    return index if side == "out" else index - 1


def plan_curve(times, values, target_indices=None, end_mode=END_FLAT,
               method=METHOD_SMOOTH):
    """1 本のカーブに対して「どのキーをどの傾きにするか」を返す。

    `target_indices` が None なら全キー。 対象外のキーも傾きの計算には使う
    （選択キーだけ直しても、前後のつながりは保たれる）。

    戻り値: `[(index, slope_per_frame), ...]`（index 昇順）
    """
    slopes = compute_slopes(times, values, end_mode=end_mode, method=method)
    if target_indices is None:
        targets = range(len(times))
    else:
        targets = sorted(i for i in set(target_indices) if 0 <= i < len(times))
    return [(i, slopes[i]) for i in targets]
