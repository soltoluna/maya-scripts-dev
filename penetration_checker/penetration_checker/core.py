# -*- coding: utf-8 -*-
"""Penetration Checker — Maya 非依存の純ロジック。

**このモジュールは `maya` を import しない。** 開発機に Maya が無いので、
ここに寄せた処理だけが自宅で実行・テストできる。

扱うもの:
    * バウンディングボックスの計算と重なり判定（総当たりの足切り）
    * 「点がメッシュの内側にあるか」の判定（最近接点 + 法線の符号）
    * めり込み頂点ごとのスキンウェイトから「効いている」インフルエンスの集計
    * インフルエンスから、動かすべきコントローラーを辿る探索（グラフは関数で受け取る）
    * 1 フレーム分の判定の段取り（`Checker`）と、フレーム範囲のスキャン（`scan`）
    * フレームごとの結果を「めり込んでいる区間」にまとめる（`group_frames`）

Maya に触る部分（頂点座標・最近接点・スキンウェイト・接続の取得・時間の移動）は
`scene.py` がアダプターや関数として渡してくる。 ここは受け取ったものを呼ぶだけ
なので、テストでは動く球や手書きのグラフを渡して境界条件まで詰められる。

単位はすべて呼び出し側の座標系のまま扱う（`scene.py` は Maya の内部単位 cm で渡す）。
"""

from __future__ import annotations

import math


# 深さ 0 ちょうどの頂点（許容値 0 で面にぴったり乗っている頂点など）でも
# 集計で数に入るよう、スコアに足す小さな値
_SCORE_EPSILON = 1e-4


# --------------------------------------------------------------------------- #
# バウンディングボックス
# --------------------------------------------------------------------------- #

def bbox_of_points(points):
    """点列のバウンディングボックス `(xmin, ymin, zmin, xmax, ymax, zmax)`。

    点が無ければ `None`。
    """
    pts = list(points)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def bbox_overlap(a, b, margin=0.0):
    """2 つのボックスが（`margin` だけ広げて）重なるか。 接しているだけでも True。"""
    if a is None or b is None:
        return False
    for axis in range(3):
        if a[axis] - margin > b[axis + 3] or b[axis] - margin > a[axis + 3]:
            return False
    return True


def point_in_bbox(point, bbox, margin=0.0):
    """点がボックスの内側（境界を含む）にあるか。"""
    if bbox is None:
        return False
    for axis in range(3):
        if point[axis] < bbox[axis] - margin or point[axis] > bbox[axis + 3] + margin:
            return False
    return True


def candidate_pairs(bboxes, margin=0.0):
    """ボックスが重なっている組を `(a, b)`（`a < b`）の昇順リストで返す。

    `bboxes` は `{名前: bbox}`。 重ならない組は内外判定を走らせても何も
    出ないので、ここで足切りする（総当たりの大半はここで落ちる）。
    """
    names = sorted(bboxes)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if bbox_overlap(bboxes[a], bboxes[b], margin):
                pairs.append((a, b))
    return pairs


# --------------------------------------------------------------------------- #
# 内外判定
# --------------------------------------------------------------------------- #

def penetration_depth(point, closest, normal):
    """`point` が面の裏側にどれだけ入り込んでいるか（正 = 内側）。

    `closest` は `point` に最も近いメッシュ上の点、`normal` はそこの外向き法線。
    `(point - closest)` と法線が逆向きなら内側にある。 返す値は面からの距離
    （法線の長さは問わない）。 法線が長さ 0 なら判定できないので `None`。
    """
    nx, ny, nz = normal
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 0.0:
        return None
    dx = point[0] - closest[0]
    dy = point[1] - closest[1]
    dz = point[2] - closest[2]
    return -(dx * nx + dy * ny + dz * nz) / length


def find_inside_vertices(points, container_bbox, closest_fn, tolerance=0.0):
    """`points` のうち、相手メッシュの内側にある頂点を `[(index, depth), ...]` で返す。

    * `container_bbox` — 相手メッシュのボックス。 外にある点は問い合わせない
    * `closest_fn(point) -> (closest, normal)` — 相手メッシュ上の最近接点と法線。
      失敗したら `None` を返してよい（その頂点は数えない）
    * `tolerance` — この深さを**超えて**入り込んだものだけを数える。
      接しているだけ・浮動小数の誤差を拾わないための遊び

    結果は深い順（同じ深さなら番号順）。
    """
    hits = []
    for index, point in enumerate(points):
        if not point_in_bbox(point, container_bbox, tolerance):
            continue
        answer = closest_fn(point)
        if answer is None:
            continue
        closest, normal = answer
        depth = penetration_depth(point, closest, normal)
        if depth is None or depth <= tolerance:
            continue
        hits.append((index, depth))
    hits.sort(key=lambda item: (-item[1], item[0]))
    return hits


# --------------------------------------------------------------------------- #
# 集計
# --------------------------------------------------------------------------- #

def influence_scores(hits, weights_fn, limit=None):
    """めり込み頂点ごとのスキンウェイトを `{インフルエンス: スコア}` に集計する。

    スコアは `Σ weight × (depth + ε)`。 深く刺さっている頂点を強く効かせる
    （浅く触れているだけの頂点が数で勝つと、直すべき場所がずれるため）。

    * `hits` — `find_inside_vertices` の戻り値（深い順）
    * `weights_fn(index) -> {インフルエンス: weight}`
    * `limit` — 先頭（深いほう）から何頂点までを見るか。 スキンウェイトの
      問い合わせは 1 頂点ずつで重いので、上限を付けられるようにしてある
    """
    scores = {}
    for count, (index, depth) in enumerate(hits):
        if limit is not None and count >= limit:
            break
        weights = weights_fn(index) or {}
        for influence, weight in weights.items():
            if weight <= 0.0:
                continue
            scores[influence] = scores.get(influence, 0.0) + weight * (
                max(depth, 0.0) + _SCORE_EPSILON)
    return scores


def rank_scores(scores):
    """`{名前: スコア}` を `[(名前, スコア), ...]` の降順にする（同点は名前順）。"""
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def aggregate_targets(contributions):
    """複数のめり込みから「選ぶべきノード」の順位表を作る。

    `contributions` は次の dict のリスト:

        {"target": ノード名, "kind": "controller" | "joint" | "transform",
         "score": float, "mesh": めり込んでいる側, "other": めり込まれている側,
         "count": 頂点数, "depth": 最大の深さ}

    同じ `target` をまとめ、スコアの降順で返す。 各要素は

        {"target", "kind", "score", "count", "depth", "pairs": [(mesh, other), ...]}

    `count` / `depth` はまとめたペアのうちの合計 / 最大。
    """
    merged = {}
    for item in contributions:
        key = item["target"]
        entry = merged.get(key)
        if entry is None:
            entry = merged[key] = {
                "target": key, "kind": item.get("kind", "transform"),
                "score": 0.0, "count": 0, "depth": 0.0, "pairs": [],
            }
        entry["score"] += item.get("score", 0.0)
        pair = (item.get("mesh"), item.get("other"))
        if pair not in entry["pairs"]:
            entry["pairs"].append(pair)
            entry["count"] += item.get("count", 0)
        entry["depth"] = max(entry["depth"], item.get("depth", 0.0))
    return sorted(merged.values(), key=lambda e: (-e["score"], e["target"]))


# --------------------------------------------------------------------------- #
# コントローラーの探索
# --------------------------------------------------------------------------- #

def find_controller(start, sources_fn, parent_fn, is_controller_fn,
                    max_steps=12, max_nodes=500):
    """`start`（ジョイントなど）を動かしているコントローラーを上流へ辿って探す。

    幅優先で、**入力接続 → DAG の親**の順に広げ、最初に見つかった
    コントローラーを返す。 段数の少ないものが勝つので、ジョイントに直接
    コンストレイントしているコントローラーが、親ジョイント経由のもの
    （= 親のコントローラー）より優先される。

    * `sources_fn(node) -> [node, ...]` — 入力接続の元ノード
    * `parent_fn(node) -> node or None` — DAG の親。 辿らせたくないノード
      （ジョイントの親ジョイントなど）では `None` を返す
    * `is_controller_fn(node) -> bool`

    戻り値は `(コントローラー or None, 辿った経路 [start, ..., コントローラー])`。
    見つからなければ `(None, [start])`。
    """
    if is_controller_fn(start):
        return start, [start]

    queue = [(start, 0)]
    came_from = {start: None}
    head = 0
    while head < len(queue):
        node, steps = queue[head]
        head += 1
        if steps >= max_steps:
            continue
        neighbors = list(sources_fn(node) or [])
        parent = parent_fn(node)
        if parent:
            neighbors.append(parent)
        for nxt in neighbors:
            if not nxt or nxt in came_from:
                continue
            if len(came_from) >= max_nodes:
                return None, [start]
            came_from[nxt] = node
            if is_controller_fn(nxt):
                return nxt, _trace(came_from, nxt)
            queue.append((nxt, steps + 1))
    return None, [start]


def _trace(came_from, node):
    path = []
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


# --------------------------------------------------------------------------- #
# 表示
# --------------------------------------------------------------------------- #

_KIND_MARK = {"controller": "CTRL", "joint": "JNT", "transform": "OBJ"}


def short_name(name):
    """`|grp|mesh` → `mesh`（名前空間は残す）。"""
    return (name or "").rsplit("|", 1)[-1]


def format_target_row(entry, unit=""):
    """結果一覧の 1 行。 `[CTRL] arm_L_fk1_ctl   12 vtx  max 0.83cm  (hand > body)`"""
    pairs = entry.get("pairs") or []
    if pairs:
        mesh, other = pairs[0]
        where = "%s > %s" % (short_name(mesh), short_name(other))
        if len(pairs) > 1:
            where += " ほか %d 組" % (len(pairs) - 1)
    else:
        where = ""
    return "[%s] %s   %d vtx  max %.3g%s  (%s)" % (
        _KIND_MARK.get(entry.get("kind"), "OBJ"), short_name(entry["target"]),
        entry.get("count", 0), entry.get("depth", 0.0), unit, where)


def format_frame(value):
    """フレーム番号の表示。 `12.0` → `12`、`12.5` → `12.5`。 数でなければそのまま。"""
    try:
        return "%g" % float(value)
    except (TypeError, ValueError):
        return str(value)


# --------------------------------------------------------------------------- #
# 1 フレーム分の判定
# --------------------------------------------------------------------------- #

class Checker(object):
    """対象メッシュの組を持ち、フレームごとに判定を繰り返す。

    `meshes` はアダプターのリスト。 アダプターに求めるもの（`scene.MeshAdapter`
    が実装する。 テストでは偽物を渡す）:

        name                  フルパス（結果の表示と識別に使う）
        begin_frame()         フレームが変わったので座標のキャッシュを捨てる
        points()              今のフレームのワールド頂点座標 [(x, y, z), ...]
        bbox()                今のフレームのボックス（points から作ってよい）
        closest(point)        (最近接点, 外向き法線) or None
        is_closed()           境界エッジが無いか（フレームをまたいで変わらない）
        weights(index)        {インフルエンス: weight}。 スキンが無ければ None

    `resolve_fn(influence) -> (target, kind, path)` はインフルエンスを選ぶべき
    ノードに直す関数。 結果はインスタンスの中でキャッシュする（リグの接続は
    再生中に変わらない）。 スキンウェイトもフレームをまたいで変わらないので
    キャッシュする — 再生しながら判定するときに効く。
    """

    def __init__(self, meshes, resolve_fn, tolerance=0.0,
                 use_open_containers=False, weight_limit=200):
        self.meshes = list(meshes)
        self.resolve_fn = resolve_fn
        self.tolerance = float(tolerance)
        self.use_open_containers = bool(use_open_containers)
        self.weight_limit = weight_limit
        self.warnings = []
        self._warned = set()
        self._resolved = {}
        self._weights = {}

    def _warn(self, key, message):
        if key not in self._warned:
            self._warned.add(key)
            self.warnings.append(message)

    def check_frame(self, progress=None):
        """今のフレームを調べる。 戻り値は 1 フレーム分の結果 dict:

            {"hits": [{"mesh", "other", "vertices": [(index, depth), ...]}, ...],
             "targets": aggregate_targets(...) の戻り値,
             "pairs": 調べた組の数, "cancelled": bool}

        `progress(done, total, label) -> bool` が False を返したら中断する。
        読めないメッシュは警告に回して残りで続ける（1 つ消えただけで全部
        止めない）。
        """
        by_name = {}
        bboxes = {}
        for mesh in self.meshes:
            try:
                mesh.begin_frame()
                bboxes[mesh.name] = mesh.bbox()
                by_name[mesh.name] = mesh
            except Exception as exc:
                self._warn(("read", mesh.name), "%s を読めませんでした: %s"
                           % (short_name(mesh.name), exc))

        pairs = candidate_pairs(bboxes, margin=self.tolerance)
        result = {"hits": [], "targets": [], "pairs": len(pairs),
                  "cancelled": False}
        for done, (a, b) in enumerate(pairs):
            if progress and not progress(done, len(pairs), "%s / %s" % (
                    short_name(a), short_name(b))):
                result["cancelled"] = True
                break
            for mesh, other in ((a, b), (b, a)):
                container = by_name[other]
                if not self.use_open_containers and not container.is_closed():
                    self._warn(("open", other),
                               "%s は開いたメッシュなので、めり込まれる側としては"
                               "調べていません" % short_name(other))
                    continue
                vertices = find_inside_vertices(
                    by_name[mesh].points(), container.bbox(), container.closest,
                    self.tolerance)
                if vertices:
                    result["hits"].append({"mesh": mesh, "other": other,
                                           "vertices": vertices})
        result["targets"] = aggregate_targets(self._contributions(
            result["hits"], by_name))
        return result

    def _weights_of(self, mesh):
        cache = self._weights.setdefault(mesh.name, {})

        def weights(index):
            if index not in cache:
                cache[index] = mesh.weights(index)
            value = cache[index]
            # スキンの無いメッシュ（コンストレイントされた小物など）は
            # メッシュ自身から辿る
            return {mesh.name: 1.0} if value is None else value
        return weights

    def resolve(self, influence):
        if influence not in self._resolved:
            try:
                self._resolved[influence] = self.resolve_fn(influence)
            except Exception as exc:
                self._warn(("resolve", influence), "%s からコントローラーを"
                           "探せませんでした: %s" % (short_name(influence), exc))
                self._resolved[influence] = (influence, "transform", [influence])
        return self._resolved[influence]

    def _contributions(self, hits, by_name):
        out = []
        for hit in hits:
            mesh = by_name[hit["mesh"]]
            vertices = hit["vertices"]
            scores = influence_scores(vertices, self._weights_of(mesh),
                                      limit=self.weight_limit)
            if not scores:
                continue
            # 1 組につき最も効いているインフルエンスを 1 つ選ぶ
            influence, score = rank_scores(scores)[0]
            target, kind, _path = self.resolve(influence)
            out.append({"target": target, "kind": kind, "score": score,
                        "mesh": hit["mesh"], "other": hit["other"],
                        "count": len(vertices), "depth": vertices[0][1]})
        return out


# --------------------------------------------------------------------------- #
# フレーム範囲
# --------------------------------------------------------------------------- #

def frame_list(start, end, step=1.0):
    """`start` から `end` まで（両端を含む）のフレーム。 逆順なら入れ替える。"""
    step = abs(float(step)) or 1.0
    start, end = float(start), float(end)
    if end < start:
        start, end = end, start
    count = int(math.floor((end - start) / step + 1e-6)) + 1
    return [start + i * step for i in range(count)]


def scan(checker, frames, set_time_fn, progress=None):
    """`frames` を順に `set_time_fn(frame)` で移動しながら `checker` で調べる。

    戻り値 `(results, cancelled)`。 `results` は `{frame: check_frame の戻り値}`。
    `progress(done, total, label) -> bool` が False を返したら、そこまでで止める。
    時間を元に戻すのは呼び出し側の仕事（例外でも戻せるよう finally で）。
    """
    results = {}
    total = len(frames)
    for done, frame in enumerate(frames):
        if progress and not progress(done, total, "frame %s" % format_frame(frame)):
            return results, True
        set_time_fn(frame)
        results[frame] = checker.check_frame()
    return results, False


def group_frames(results, step=1.0):
    """めり込みのあるフレームを連続した区間にまとめる。

    `results` は `{frame: check_frame の戻り値}`。 戻り値は区間のリスト（時間順）:

        {"start", "end", "frames": [...], "worst_frame", "depth",
         "targets": [(target, kind), ...]  ← 区間内のスコア合計の大きい順}

    `step` より間が空いたら別の区間にする。
    """
    frames = sorted(f for f, r in results.items() if r and r.get("targets"))
    groups = []
    for frame in frames:
        if groups and frame - groups[-1][-1] <= abs(step) + 1e-6:
            groups[-1].append(frame)
        else:
            groups.append([frame])

    out = []
    for group in groups:
        scores = {}
        kinds = {}
        worst_frame, worst_depth = group[0], -1.0
        for frame in group:
            for entry in results[frame]["targets"]:
                key = entry["target"]
                scores[key] = scores.get(key, 0.0) + entry.get("score", 0.0)
                kinds.setdefault(key, entry.get("kind", "transform"))
                if entry.get("depth", 0.0) > worst_depth:
                    worst_frame, worst_depth = frame, entry.get("depth", 0.0)
        out.append({
            "start": group[0], "end": group[-1], "frames": group,
            "worst_frame": worst_frame, "depth": max(worst_depth, 0.0),
            "targets": [(name, kinds[name]) for name, _s in rank_scores(scores)],
        })
    return out


def format_range_row(group, unit="", scale=None):
    """区間一覧の 1 行。 `12-18 (7f)  hand_ctl ほか 1  max 0.83cm @15`"""
    scale = scale or (lambda v: v)
    if group["start"] == group["end"]:
        span = format_frame(group["start"])
    else:
        span = "%s-%s" % (format_frame(group["start"]), format_frame(group["end"]))
    targets = group.get("targets") or []
    who = short_name(targets[0][0]) if targets else "?"
    if len(targets) > 1:
        who += " ほか %d" % (len(targets) - 1)
    return "%s (%df)  %s  max %.3g%s @%s" % (
        span, len(group["frames"]), who, scale(group.get("depth", 0.0)), unit,
        format_frame(group["worst_frame"]))


def hud_text(result, unit="", scale=None):
    """ビューポートの HUD に出す 1 行。

    ASCII だけで組む（HUD のフォントで日本語が化ける環境に備える）。
    `result` は 1 フレーム分の結果。 `None` は「このフレームは調べていない」。
    """
    scale = scale or (lambda v: v)
    if result is None:
        return "-- (not checked)"
    targets = result.get("targets") or []
    if not targets:
        return "OK"
    top = targets[0]
    text = "HIT  %s  %.3g%s" % (short_name(top["target"]),
                                 scale(top.get("depth", 0.0)), unit)
    if len(targets) > 1:
        text += "  (+%d)" % (len(targets) - 1)
    return text
