# -*- coding: utf-8 -*-
"""テスト用ブートストラップ（ツール非依存・そのままコピーして使える）。

各テストファイルの先頭で `import _bootstrap` すると:

  1. `maya` / `maya.cmds` / `maya.mel` / `maya.utils` / `maya.api.OpenMaya` /
     `maya.OpenMayaUI` の最小スタブを `sys.modules` へ注入する
  2. ツール本体を `import` できるよう `sys.path` を整える

副作用は import 時に一度だけ発火し、二重 import しても冪等。

スタブは「ツールを import して `show()` を一往復させられるだけの表面積」を
狙っている。 **実 Maya の挙動を再現するものではない。** ノードの生成や
属性の読み書きは何も起きないので、機能の正しさは実機でしか確かめられない。
ここで担保するのは「壊れた状態で実機に持っていかない」ことだけ。

関数の入出力を確かめるテストは、`maya` を import しない `core.py` に対して
書く。 そちらは本物の Python として動くので、実機と同じ結果が出る。

## 公開している道具

- `TOOL_DIR` / `PACKAGE_NAME` — ツールフォルダのパスとパッケージ名
- `import_tool()` — ツール本体を import して返す（冪等）
- `reload_tool()` — `sys.modules` から落として import し直す
- `reset_registry()` — 下記の記録をすべてクリアする（`setUp` から呼ぶ）
- `CALLS` — `cmds.*` の呼び出し履歴 `(コマンド名, args, kwargs)`
- `WINDOWS` / `CONTROLS` — 生成された UI（`deleteUI` で消える）
- `OPTION_VARS` — `cmds.optionVar` の中身
- `UNDO_CHUNKS` — 開いたまま閉じていない undo チャンク（**空でなければ閉じ忘れ**）
- `DEFERRED` — `cmds.evalDeferred` に積まれた関数。 `run_deferred()` で流す
- `SCRIPT_JOBS` — 生きている scriptJob
- `DIALOGS` / `MESSAGES` — `confirmDialog` / `warning` の記録
- `set_selection([...])` — `cmds.ls(selection=True)` が返す値を差し替える
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import types


# --- 対象ツールの特定 --------------------------------------------------------

TOOL_DIR = pathlib.Path(__file__).resolve().parent.parent
PACKAGE_NAME = TOOL_DIR.name
PACKAGE_DIR = TOOL_DIR / PACKAGE_NAME
REPO_ROOT = TOOL_DIR.parent


# --- 記録用のグローバル ------------------------------------------------------

CALLS: list = []
WINDOWS: dict = {}
CONTROLS: dict = {}
OPTION_VARS: dict = {}
UNDO_CHUNKS: list = []
DEFERRED: list = []
SCRIPT_JOBS: dict = {}
DIALOGS: list = []
MESSAGES: list = []
_SELECTION: list = []
_PARENT_STACK: list = []
_COUNTER = {"n": 0}


def reset_registry():
    """記録をすべてクリアする。 テストの `setUp` から呼ぶ。"""
    CALLS.clear()
    WINDOWS.clear()
    CONTROLS.clear()
    OPTION_VARS.clear()
    UNDO_CHUNKS.clear()
    DEFERRED.clear()
    SCRIPT_JOBS.clear()
    DIALOGS.clear()
    MESSAGES.clear()
    del _SELECTION[:]
    del _PARENT_STACK[:]
    _COUNTER["n"] = 0


def set_selection(names):
    """`cmds.ls(selection=True)` が返す値を差し替える。"""
    del _SELECTION[:]
    _SELECTION.extend(names)


def run_deferred():
    """`evalDeferred` に積まれた関数を積んだ順に流す（再帰的に空になるまで）。

    実 Maya は idle で 1 つずつ実行する。 3 段の更新フローのように
    `evalDeferred` が `evalDeferred` を積む場合も追えるようにしてある。
    """
    executed = 0
    while DEFERRED:
        func = DEFERRED.pop(0)
        if callable(func):
            func()
        executed += 1
        if executed > 100:
            raise RuntimeError("evalDeferred loop did not settle (100 calls)")
    return executed


# --- cmds スタブ -------------------------------------------------------------

# 短縮フラグ → 正式名。 `cmds.text(l="x")` で作って `q=True, label=True` で
# 引くような、Maya では当たり前の書き分けを吸収するための最小限の対応表
_FLAG_ALIASES = {
    "l": "label", "t": "title", "tx": "text", "en": "enable", "vis": "visible",
    "v": "value", "ann": "annotation", "w": "width", "h": "height",
    "ca": "childArray", "sl": "selection", "q": "query", "e": "edit",
    "ex": "exists", "sv": "stringValue", "iv": "intValue", "fv": "floatValue",
    "cl": "closeChunk", "ock": "openChunk", "cck": "closeChunk",
}

_QUERY_FLAGS = ("query", "q")
_EDIT_FLAGS = ("edit", "e")


def _canonical(kwargs):
    """短縮フラグを正式名に寄せた dict を返す。"""
    out = {}
    for key, value in kwargs.items():
        out[_FLAG_ALIASES.get(key, key)] = value
    return out


def _is_query(kwargs):
    return any(kwargs.get(f) for f in _QUERY_FLAGS)


def _is_edit(kwargs):
    return any(kwargs.get(f) for f in _EDIT_FLAGS)


def _new_name(prefix):
    _COUNTER["n"] += 1
    return "%s%d" % (prefix, _COUNTER["n"])


class _MayaCmdsStub(types.ModuleType):
    """`maya.cmds` 相当。

    明示的に実装したコマンド以外は「作成なら名前を返す / 照会なら作成時の値を
    返す」汎用の記録関数になる。 実 Maya のように名前で状態を持つので、
    `cmds.textFieldGrp(ctrl, q=True, text=True)` のような往復はそのまま通る。
    """

    _maya_stub = True

    # -- 明示実装 ------------------------------------------------------------

    def window(self, name=None, *args, **kwargs):
        kw = _canonical(kwargs)
        CALLS.append(("window", (name,) + args, kwargs))
        if "exists" in kw:
            return name in WINDOWS
        if _is_query(kw):
            return WINDOWS.get(name, {}).get(_first_query_flag(kw))
        if _is_edit(kw):
            WINDOWS.setdefault(name, {}).update(kw)
            return name
        name = name or _new_name("window")
        WINDOWS[name] = dict(kw, _shown=False)
        del _PARENT_STACK[:]
        _PARENT_STACK.append(name)
        return name

    def showWindow(self, name=None, *_args, **kwargs):
        CALLS.append(("showWindow", (name,), kwargs))
        if name in WINDOWS:
            WINDOWS[name]["_shown"] = True
        return name

    def deleteUI(self, *names, **kwargs):
        CALLS.append(("deleteUI", names, kwargs))
        for name in names:
            WINDOWS.pop(name, None)
            CONTROLS.pop(name, None)
            for child in [c for c, meta in CONTROLS.items()
                          if meta.get("_parent") == name]:
                CONTROLS.pop(child, None)

    def setParent(self, target=None, *_args, **kwargs):
        CALLS.append(("setParent", (target,), kwargs))
        if target == "..":
            if _PARENT_STACK:
                _PARENT_STACK.pop()
        elif target:
            _PARENT_STACK.append(target)
        return _PARENT_STACK[-1] if _PARENT_STACK else None

    def optionVar(self, **kwargs):
        CALLS.append(("optionVar", (), kwargs))
        kw = _canonical(kwargs)
        if "exists" in kw:
            return kw["exists"] in OPTION_VARS
        if "remove" in kw:
            OPTION_VARS.pop(kw["remove"], None)
            return None
        for flag in ("stringValue", "intValue", "floatValue",
                     "stringValueAppend", "intValueAppend"):
            if flag in kw:
                key, value = kw[flag]
                OPTION_VARS[key] = value
                return None
        if _is_query(kw):
            # `cmds.optionVar(q="key")` は q にキー名が入る
            key = kw.get("query")
            if key is True:
                return None
            return OPTION_VARS.get(key)
        return None

    def undoInfo(self, **kwargs):
        CALLS.append(("undoInfo", (), kwargs))
        kw = _canonical(kwargs)
        if kw.get("openChunk"):
            UNDO_CHUNKS.append(kw.get("chunkName", "<unnamed>"))
        elif kw.get("closeChunk"):
            if not UNDO_CHUNKS:
                # 実 Maya は黙って壊れる。 テストでは即座に落とす
                raise RuntimeError(
                    "undoInfo(closeChunk=True) without a matching openChunk")
            UNDO_CHUNKS.pop()
        return None

    def evalDeferred(self, func=None, *_args, **kwargs):
        CALLS.append(("evalDeferred", (func,), kwargs))
        if func is not None:
            DEFERRED.append(func)
        return None

    def scriptJob(self, **kwargs):
        CALLS.append(("scriptJob", (), kwargs))
        kw = _canonical(kwargs)
        if "kill" in kw:
            SCRIPT_JOBS.pop(kw["kill"], None)
            return None
        if _is_query(kw):
            return list(SCRIPT_JOBS)
        job_id = len(SCRIPT_JOBS) + 1
        SCRIPT_JOBS[job_id] = kw
        return job_id

    def ls(self, *args, **kwargs):
        CALLS.append(("ls", args, kwargs))
        kw = _canonical(kwargs)
        if kw.get("selection"):
            return list(_SELECTION)
        return list(args) if args else []

    def select(self, *args, **kwargs):
        CALLS.append(("select", args, kwargs))
        kw = _canonical(kwargs)
        if kw.get("clear"):
            del _SELECTION[:]
        elif args:
            first = args[0]
            set_selection(list(first) if isinstance(first, (list, tuple)) else [first])
        return None

    def rename(self, node=None, new_name=None, **kwargs):
        CALLS.append(("rename", (node, new_name), kwargs))
        return new_name

    def objExists(self, name=None, **kwargs):
        CALLS.append(("objExists", (name,), kwargs))
        return False

    def confirmDialog(self, **kwargs):
        CALLS.append(("confirmDialog", (), kwargs))
        DIALOGS.append(kwargs)
        buttons = kwargs.get("button") or kwargs.get("b") or ["OK"]
        return buttons[0]

    def warning(self, message="", **kwargs):
        CALLS.append(("warning", (message,), kwargs))
        MESSAGES.append(("warning", message))
        return None

    def error(self, message="", **kwargs):
        CALLS.append(("error", (message,), kwargs))
        MESSAGES.append(("error", message))
        # 実 Maya の `cmds.error` は例外を送出して処理を止める
        raise RuntimeError(message)

    def internalVar(self, **kwargs):
        CALLS.append(("internalVar", (), kwargs))
        import tempfile
        return tempfile.gettempdir().replace("\\", "/") + "/"

    def about(self, **kwargs):
        CALLS.append(("about", (), kwargs))
        kw = _canonical(kwargs)
        if kw.get("version"):
            return "2024"
        if kw.get("apiVersion"):
            return 20240000
        return ""

    # -- 汎用フォールバック --------------------------------------------------

    def __getattr__(self, command):
        if command.startswith("_"):
            raise AttributeError(command)

        def _generic(*args, **kwargs):
            CALLS.append((command, args, kwargs))
            kw = _canonical(kwargs)
            name = args[0] if args and isinstance(args[0], str) else None

            if "exists" in kw:
                target = kw["exists"] if isinstance(kw["exists"], str) else name
                return target in CONTROLS or target in WINDOWS

            if _is_query(kw):
                stored = CONTROLS.get(name, {})
                flag = _first_query_flag(kw)
                if flag == "childArray":
                    return [c for c, meta in CONTROLS.items()
                            if meta.get("_parent") == name] or None
                return stored.get(flag)

            if _is_edit(kw) and name:
                CONTROLS.setdefault(name, {}).update(kw)
                return name

            # 生成: 名前を発行して控える（実 Maya と同じく名前を返す）
            name = name or _new_name(command)
            parent = kw.get("parent") or (_PARENT_STACK[-1] if _PARENT_STACK else None)
            CONTROLS[name] = dict(kw, _command=command, _parent=parent)
            if command.endswith("Layout"):
                _PARENT_STACK.append(name)
            return name

        _generic.__name__ = command
        return _generic


def _first_query_flag(kw):
    """照会で「何を聞かれているか」を取り出す（`q=True` 以外の True フラグ）。"""
    for key, value in kw.items():
        if key in _QUERY_FLAGS or key in _EDIT_FLAGS:
            continue
        if value is True:
            return key
    return None


# --- スタブの組み立てと注入 --------------------------------------------------

def _build_maya():
    maya = types.ModuleType("maya")
    maya._maya_stub = True

    cmds = _MayaCmdsStub("maya.cmds")

    mel = types.ModuleType("maya.mel")
    mel.eval = lambda script: CALLS.append(("mel.eval", (script,), {})) or ""

    utils = types.ModuleType("maya.utils")
    utils.executeDeferred = lambda func, *a, **k: DEFERRED.append(func)
    utils.executeInMainThreadWithResult = lambda func, *a, **k: (
        func(*a, **k) if callable(func) else None)

    # OpenMaya は import が通ればよい程度。 実際に使うテストを書くときは
    # そのツールの `fixtures.py` で差し替える
    api = types.ModuleType("maya.api")
    om = types.ModuleType("maya.api.OpenMaya")
    for name in ("MGlobal", "MSelectionList", "MFnDependencyNode", "MVector",
                 "MPoint", "MMatrix", "MDagPath", "MObject", "MEulerRotation"):
        setattr(om, name, type(name, (), {}))
    api.OpenMaya = om

    om_ui = types.ModuleType("maya.OpenMayaUI")
    om_ui.MQtUtil = type("MQtUtil", (), {})

    maya.cmds = cmds
    maya.mel = mel
    maya.utils = utils
    maya.api = api
    maya.OpenMayaUI = om_ui
    return maya


def _install():
    if "maya" in sys.modules and getattr(sys.modules["maya"], "_maya_stub", False):
        return  # 冪等

    maya = _build_maya()
    sys.modules["maya"] = maya
    sys.modules["maya.cmds"] = maya.cmds
    sys.modules["maya.mel"] = maya.mel
    sys.modules["maya.utils"] = maya.utils
    sys.modules["maya.api"] = maya.api
    sys.modules["maya.api.OpenMaya"] = maya.api.OpenMaya
    sys.modules["maya.OpenMayaUI"] = maya.OpenMayaUI

    root = str(TOOL_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)


_install()


def import_tool():
    """ツール本体を import して返す（何度呼んでも同じモジュール）。"""
    if PACKAGE_NAME in sys.modules:
        return sys.modules[PACKAGE_NAME]
    return importlib.import_module(PACKAGE_NAME)


def reload_tool():
    """`sys.modules` から落として import し直す（ホット更新後の状態を再現する）。"""
    for name in [k for k in list(sys.modules)
                 if k == PACKAGE_NAME or k.startswith(PACKAGE_NAME + ".")]:
        sys.modules.pop(name, None)
    return importlib.import_module(PACKAGE_NAME)


def tool_source_files():
    """パッケージを構成する `.py` の一覧（`__pycache__` を除く）。"""
    return sorted(p for p in PACKAGE_DIR.rglob("*.py")
                  if "__pycache__" not in p.parts)


def installer_path():
    """ハブ `install.py` のパス（**リポジトリ直下**）。

    ツールごとの `install.py` は廃止した。 リポジトリ直下の 1 本が tree API で
    全ツールを列挙してまとめて配る（`docs/TOOL_SCAFFOLD.md`）。
    """
    return REPO_ROOT / "install.py"
