# -*- coding: utf-8 -*-
"""Penetration Checker — シーンを読む層（Maya 依存）。

**シーンを変更しない**（時間を動かすのはスキャン中だけで、終わったら戻す）。
読むのは頂点座標・最近接点・スキンウェイト・接続だけで、判定・集計・
スキャンの段取りは `core` に任せる。 ここは `core.Checker` に渡す
アダプター（`MeshAdapter`）と、時間まわりの小さな関数を持つだけに保つ。

座標はすべて **Maya の内部単位（cm）のワールド空間**で扱う。 OpenMaya の
`getPoints(kWorld)` は UI の単位設定に関係なく内部単位で返すので、
`cmds.exactWorldBoundingBox`（UI 単位）と混ぜない。 ボックスも点から作る。
許容値の入力と深さの表示だけ `MDistance` で UI 単位と変換する。

最近接点の求め方は 2 通り持っている（`set_backend()` で切り替え）:

* `"intersector"`（既定）— `MMeshIntersector`。 八分木を作るので速い。
  **問い合わせはオブジェクト空間で行い**、ワールドへの変換は自分でする
  （行列を渡したときの戻り値の空間を推測しないため）
* `"fnmesh"` — `MFnMesh.getClosestPointAndNormal(kWorld)`。 総当たりで遅いが、
  空間の扱いに曖昧さが無い。 `diagnose()` が両者を突き合わせる
"""

from __future__ import annotations

from maya import cmds, mel
from maya.api import OpenMaya as om

from . import NAMESPACE, core


_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_OPTVAR_BACKEND = "%s_%s_backend" % (NAMESPACE, _PACKAGE)

_BACKENDS = ("intersector", "fnmesh")

# 接続を辿るときに無視する入力アトリビュート。 これらはジョイントの動きの
# 「出どころ」ではない（親ジョイントの scale・表示レイヤー・セットなど）
_IGNORED_DEST_ATTRS = frozenset((
    "message", "inverseScale", "drawOverride", "instObjGroups",
    "lockInfluenceWeights", "bindPose", "objectColorRGB", "useObjectColor",
    "hiddenInOutliner", "isHistoricallyInteresting",
))

# 1 組のめり込みにつき、スキンウェイトを問い合わせる頂点数の上限（深い順）
_WEIGHT_SAMPLE_LIMIT = 200


def get_backend():
    if cmds.optionVar(exists=_OPTVAR_BACKEND):
        value = cmds.optionVar(q=_OPTVAR_BACKEND)
        if value in _BACKENDS:
            return value
    return _BACKENDS[0]


def set_backend(name):
    """最近接点の求め方を切り替える（`"intersector"` / `"fnmesh"`）。 保存される。"""
    if name not in _BACKENDS:
        raise ValueError("backend must be one of %s: %r" % (_BACKENDS, name))
    cmds.optionVar(sv=(_OPTVAR_BACKEND, name))
    print("[%s] backend: %s" % (_PACKAGE, name))


# --------------------------------------------------------------------------- #
# 対象メッシュの列挙
# --------------------------------------------------------------------------- #

def expand_meshes(nodes, skip_hidden=True):
    """指定ノード（グループ可）の配下にあるメッシュのトランスフォームを返す。

    中間オブジェクト（スキンの元形状など）は除く。 重複は 1 つにまとめ、
    フルパスで返す。 非表示の判定は呼んだ時点のもの（キーで表示が変わる
    メッシュには、スキャン中は追従しない）。
    """
    found = []
    seen = set()
    for node in nodes or []:
        if not cmds.objExists(node):
            continue
        shapes = []
        if cmds.nodeType(node) == "mesh":
            shapes.append(node)
        shapes.extend(cmds.listRelatives(node, allDescendents=True, type="mesh",
                                         fullPath=True, noIntermediate=True) or [])
        for shape in shapes:
            if cmds.getAttr(shape + ".intermediateObject"):
                continue
            parent = (cmds.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
            if not parent or parent in seen:
                continue
            if skip_hidden and not _is_visible(shape):
                continue
            seen.add(parent)
            found.append(parent)
    return found


def _dag_path(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDagPath(0)


def _shape_path(transform):
    # extendToShape() は使わない。 スキンされたメッシュは中間オブジェクト
    # （ShapeOrig）も持つので、シェイプが 2 つになって失敗しうる
    shapes = cmds.listRelatives(transform, shapes=True, type="mesh",
                                fullPath=True, noIntermediate=True) or []
    if not shapes:
        raise RuntimeError("no mesh shape under %s" % transform)
    return _dag_path(shapes[0])


def _is_visible(node):
    try:
        return _dag_path(node).isVisible()
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# メッシュのアダプター（core.Checker に渡す）
# --------------------------------------------------------------------------- #

class MeshAdapter(object):
    """1 メッシュ分の読み取り。 `core.Checker` が求める形（core の docstring）。

    座標と最近接点の準備はフレームごとに捨てて作り直す（`begin_frame`）。
    スキンクラスターと閉じているかどうかはフレームをまたいで使い回す。
    """

    def __init__(self, transform, backend=None):
        self.name = transform
        self.shape_path = _shape_path(transform)
        self.shape = self.shape_path.fullPathName()
        self.backend = backend or get_backend()
        self.skin = find_skin_cluster(self.shape)
        self._closed = None
        self.begin_frame()

    # -- フレームごと --------------------------------------------------------

    def begin_frame(self):
        self._points = None
        self._bbox = None
        self._query = None

    def points(self):
        if self._points is None:
            fn = om.MFnMesh(self.shape_path)
            self._points = [(p.x, p.y, p.z)
                            for p in fn.getPoints(om.MSpace.kWorld)]
        return self._points

    def bbox(self):
        if self._bbox is None:
            self._bbox = core.bbox_of_points(self.points())
        return self._bbox

    def make_query(self, backend=None):
        backend = backend or self.backend
        if backend == "intersector":
            return _IntersectorQuery(self.shape_path)
        return _FnMeshQuery(self.shape_path)

    def closest(self, point):
        if self._query is None:
            self._query = self.make_query()
        try:
            return self._query(point)
        except Exception:
            return None

    # -- フレームをまたいで変わらない ----------------------------------------

    def is_closed(self):
        """境界エッジが 1 本も無ければ閉じたメッシュ。"""
        if self._closed is None:
            closed = True
            it = om.MItMeshEdge(self.shape_path)
            while not it.isDone():
                if it.onBoundary():
                    closed = False
                    break
                it.next()
            self._closed = closed
        return self._closed

    def weights(self, index):
        """`{インフルエンス: weight}`。 スキンが無ければ `None`。"""
        if not self.skin:
            return None
        component = "%s.vtx[%d]" % (self.shape, index)
        try:
            names = cmds.skinPercent(self.skin, component, q=True, transform=None,
                                     ignoreBelow=1e-4) or []
            values = cmds.skinPercent(self.skin, component, q=True, value=True,
                                      ignoreBelow=1e-4) or []
        except Exception:
            return {}
        out = {}
        for name, value in zip(names, values):
            long_name = _long(name)
            out[long_name] = out.get(long_name, 0.0) + float(value)
        return out


class _FnMeshQuery(object):
    """`MFnMesh.getClosestPointAndNormal(kWorld)`。 遅いが空間が明確。"""

    def __init__(self, shape_path):
        self.fn = om.MFnMesh(shape_path)

    def __call__(self, point):
        hit, normal, _face = self.fn.getClosestPointAndNormal(
            om.MPoint(point[0], point[1], point[2]), om.MSpace.kWorld)
        return (hit.x, hit.y, hit.z), (normal.x, normal.y, normal.z)


class _IntersectorQuery(object):
    """`MMeshIntersector`。 単位行列で作り、問い合わせはオブジェクト空間で行う。

    点はワールド → オブジェクトへ逆行列で移し、戻ってきた点は行列でワールドへ、
    法線は逆行列の転置でワールドへ戻す（非一様スケールでも向きが正しい）。
    """

    def __init__(self, shape_path):
        self.matrix = shape_path.inclusiveMatrix()
        self.inverse = shape_path.inclusiveMatrixInverse()
        self.normal_matrix = self.inverse.transpose()
        self.intersector = om.MMeshIntersector()
        self.intersector.create(shape_path.node(), om.MMatrix())

    def __call__(self, point):
        local = om.MPoint(point[0], point[1], point[2]) * self.inverse
        info = self.intersector.getClosestPoint(local)
        hit = om.MPoint(info.point) * self.matrix
        normal = om.MVector(info.normal) * self.normal_matrix
        return (hit.x, hit.y, hit.z), (normal.x, normal.y, normal.z)


# --------------------------------------------------------------------------- #
# スキン
# --------------------------------------------------------------------------- #

def find_skin_cluster(shape):
    history = cmds.listHistory(shape, pruneDagObjects=True) or []
    clusters = cmds.ls(history, type="skinCluster") or []
    return clusters[0] if clusters else None


# --------------------------------------------------------------------------- #
# コントローラーの探索（グラフを core に渡す）
# --------------------------------------------------------------------------- #

def _long(node):
    return (cmds.ls(node, long=True) or [node])[0]


def sources_of(node):
    """`node` の入力接続の元ノード（無視するアトリビュートを除く）。"""
    pairs = cmds.listConnections(node, source=True, destination=False,
                                 connections=True, plugs=True,
                                 skipConversionNodes=True) or []
    out = []
    for dest, src in zip(pairs[0::2], pairs[1::2]):
        attr = dest.split(".", 1)[-1].split("[", 1)[0]
        if attr in _IGNORED_DEST_ATTRS:
            continue
        src_node = _long(src.split(".", 1)[0])
        if src_node not in out:
            out.append(src_node)
    return out


def parent_of(node):
    """DAG の親。 **ジョイントからは親を辿らない**（親ジョイントのコントローラーを
    拾ってしまうため。 ジョイントは入力接続からだけ辿る）。"""
    try:
        if cmds.nodeType(node) == "joint":
            return None
        if not cmds.objectType(node, isAType="dagNode"):
            return None
    except Exception:
        return None
    return (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]


def is_controller(node):
    """コントローラーとみなすか。

    次のどちらかを満たすトランスフォーム:
      * コントローラータグ（`controller` ノード）が付いている
      * 中間オブジェクトでない NURBS カーブのシェイプを持つ
    """
    try:
        if not cmds.objectType(node, isAType="transform"):
            return False
        if cmds.listConnections(node + ".message", type="controller",
                                source=False, destination=True):
            return True
        curves = cmds.listRelatives(node, shapes=True, type="nurbsCurve",
                                    fullPath=True, noIntermediate=True)
        return bool(curves)
    except Exception:
        return False


def resolve_target(node):
    """`node`（インフルエンス or メッシュ）を選ぶべきノードに直す。

    戻り値 `(target, kind, path)`。 コントローラーが見つからなければ
    `node` 自身（ジョイントなら `"joint"`）を返す。
    """
    ctrl, path = core.find_controller(node, sources_of, parent_of, is_controller)
    if ctrl:
        return ctrl, "controller", path
    kind = "joint" if cmds.nodeType(node) == "joint" else "transform"
    return node, kind, [node]


# --------------------------------------------------------------------------- #
# Checker の組み立て
# --------------------------------------------------------------------------- #

def make_checker(nodes, tolerance_ui=0.0, use_open_containers=False,
                 skip_hidden=True):
    """対象ノードから `core.Checker` を作る。 戻り値 `(checker, meshes, warnings)`。

    メッシュが 2 つ未満なら `checker` は `None`。 読めないメッシュは警告に
    回して残りで作る。
    """
    meshes = expand_meshes(nodes, skip_hidden=skip_hidden)
    warnings = []
    adapters = []
    backend = get_backend()
    for transform in meshes:
        try:
            adapters.append(MeshAdapter(transform, backend))
        except Exception as exc:
            warnings.append("%s を読めませんでした: %s"
                            % (core.short_name(transform), exc))
    if len(adapters) < 2:
        warnings.append("メッシュが 2 つ以上必要です（%d 個）" % len(adapters))
        return None, meshes, warnings
    checker = core.Checker(
        adapters, resolve_target,
        tolerance=om.MDistance.uiToInternal(float(tolerance_ui)),
        use_open_containers=use_open_containers,
        weight_limit=_WEIGHT_SAMPLE_LIMIT)
    return checker, meshes, warnings


# --------------------------------------------------------------------------- #
# 時間・単位
# --------------------------------------------------------------------------- #

def current_frame():
    return cmds.currentTime(query=True)


def set_frame(frame):
    """時間を動かして評価させる（`update=True`）。"""
    cmds.currentTime(frame, update=True)


def is_playing():
    return bool(cmds.play(query=True, state=True))


def time_range():
    """調べる範囲 `(start, end, 説明)`。

    タイムスライダーで範囲を選んで（Shift + ドラッグ）赤く表示していればそこ、
    無ければ再生範囲（スライダーの min / max）。
    """
    try:
        slider = mel.eval("$ntkPenTmp = $gPlayBackSlider")
        if slider and cmds.timeControl(slider, query=True, rangeVisible=True):
            start, end = cmds.timeControl(slider, query=True, rangeArray=True)
            # rangeArray は終端を含まない（[start, end)）
            return float(start), float(end) - 1.0, "選択範囲"
    except Exception:
        pass
    return (cmds.playbackOptions(query=True, minTime=True),
            cmds.playbackOptions(query=True, maxTime=True), "再生範囲")


def to_ui_distance(value):
    return om.MDistance.internalToUI(value)


def ui_unit():
    return cmds.currentUnit(query=True, linear=True) or ""


# --------------------------------------------------------------------------- #
# 調査関数
# --------------------------------------------------------------------------- #

def _safe(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        return "<ERROR %s: %s>" % (type(exc).__name__, exc)


def diagnose(node=None):
    """コントローラー探索・メッシュの読み取り・最近接点の 2 方式を Script Editor に出す。

    **シーンを変更しない。 途中で例外を上げず、`<ERROR ...>` を値にして最後まで出す。**
    結果が期待と違ったら、この出力を貼ってもらって直す（推測で直さない）。

    `node` を省略すると選択中のノード（複数可）を調べる。 渡すと良いもの:
      * めり込んでいるメッシュ 2 つ — スキン・閉じているか・最近接点の 2 方式の突き合わせ
      * ジョイント — 上流のどこでコントローラーに当たるか
    """
    targets = [node] if node else (cmds.ls(selection=True, long=True) or [])
    lines = ["=" * 60, "[penetration_checker] diagnose", "=" * 60]
    lines.append("maya: %s / unit: %s / backend: %s" % (
        _safe(cmds.about, version=True), _safe(ui_unit), _safe(get_backend)))
    lines.append("frame: %s / time_range: %s / evaluationManager: %s" % (
        _safe(current_frame), _safe(time_range),
        _safe(cmds.evaluationManager, query=True, mode=True)))
    if not targets:
        lines.append("<nothing selected>")
    all_meshes = []
    for target in targets:
        lines.append("-" * 60)
        lines.append("node: %s" % target)
        lines.append("  type: %s" % _safe(cmds.nodeType, target))
        lines.append("  is_controller: %s" % _safe(is_controller, target))
        lines.append("  sources: %s" % _safe(sources_of, target))
        lines.append("  parent_of: %s" % _safe(parent_of, target))
        found = _safe(core.find_controller, target, sources_of, parent_of,
                      is_controller)
        lines.append("  find_controller: %s" % (found,))
        meshes = _safe(expand_meshes, [target], False)
        lines.append("  meshes: %s" % (meshes,))
        if isinstance(meshes, list):
            for mesh in meshes[:5]:
                lines.extend(_diagnose_mesh(mesh))
                all_meshes.append(mesh)
    if len(all_meshes) >= 2:
        lines.extend(_diagnose_pair(all_meshes[0], all_meshes[1]))
    lines.append("=" * 60)
    text = "\n".join(lines)
    print(text)
    return text


def _diagnose_mesh(mesh):
    out = ["  mesh: %s" % mesh]
    data = _safe(MeshAdapter, mesh, "fnmesh")
    if isinstance(data, str):
        out.append("    read: %s" % data)
        return out
    points = _safe(data.points)
    if isinstance(points, str):
        out.append("    points: %s" % points)
        return out
    out.append("    vertices: %d / bbox(cm): %s" % (len(points), _fmt(_safe(data.bbox))))
    out.append("    closed: %s" % _safe(data.is_closed))
    out.append("    skinCluster: %s" % (data.skin,))
    if data.skin and points:
        weights = _safe(data.weights, 0)
        out.append("    weights(v0): %s" % (weights,))
        if isinstance(weights, dict) and weights:
            top = core.rank_scores(weights)[0][0]
            out.append("    resolve_target(%s): %s"
                       % (core.short_name(top), _safe(resolve_target, top)))
    return out


def _diagnose_pair(a, b):
    """a の頂点（最大 5 個）と a のボックス中心を b に問い合わせ、2 方式を並べる。"""
    out = ["-" * 60, "closest: %s -> %s" % (core.short_name(a), core.short_name(b))]
    src = _safe(MeshAdapter, a, "fnmesh")
    dst = _safe(MeshAdapter, b, "fnmesh")
    if isinstance(src, str) or isinstance(dst, str):
        out.append("  read: %s / %s" % (src, dst))
        return out
    points = _safe(src.points)
    if isinstance(points, str) or not points:
        out.append("  points: %s" % (points,))
        return out
    box = src.bbox()
    samples = list(points[:5]) + [tuple((box[i] + box[i + 3]) * 0.5 for i in range(3))]
    queries = {}
    for backend in _BACKENDS:
        queries[backend] = _safe(dst.make_query, backend)
    for p in samples:
        out.append("  p=%s" % (_fmt(p),))
        for backend in _BACKENDS:
            query = queries[backend]
            if isinstance(query, str):
                out.append("    %-11s: %s" % (backend, query))
                continue
            answer = _safe(query, p)
            depth = (_safe(core.penetration_depth, p, *answer)
                     if isinstance(answer, tuple) else "-")
            out.append("    %-11s: %s depth=%s" % (backend, _fmt(answer), _fmt(depth)))
    return out


def _fmt(value):
    if isinstance(value, float):
        return "%.4f" % value
    if isinstance(value, (tuple, list)):
        return "(" + ", ".join(_fmt(v) for v in value) + ")"
    return str(value)
