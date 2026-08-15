# -*- coding: utf-8 -*-
"""Tool Template — Maya へのインストーラ（ドラッグ&ドロップ）。

エンドユーザーが触る唯一のファイル。 使い方は 2 通り:

1. このファイルを Maya のビューポートへドラッグ&ドロップする
2. Script Editor (Python) で ``exec(open(r"C:/path/to/install.py").read())``

どちらの場合も次を行う:

* GitHub から実装一式を **commit SHA 固定の URL** で取得する
  （`raw.githubusercontent.com` の CDN はクエリ文字列を無視してパスだけで
  キャッシュするので、`?_=<時刻>` では最新が取れない）
* **全ファイルをメモリに揃えてから**書き込む（途中で 1 本落ちても、
  中途半端に混ざった状態を実機に残さない）
* Windows の read-only を外し、tmp + `os.replace` で原子的に上書きする
* `__pycache__` を消す（`.pyc` は mtime ベースなので、古いバイトコードが
  新しいソースを覆い隠すことがある）
* `sys.modules` から自分を落とす（次の import がディスクから読み直す）
* シェルフボタンを貼り直す（左クリック=起動 / 右クリック=GitHub から更新）

**同じファイルを 2 回ドラッグしても何も起きない。**`onMayaDroppedPythonFile`
はセッション内で 1 度しか呼ばれないため。 更新はツール UI の「GitHub から更新」
ボタンか、シェルフボタンの右クリックメニューから行う。

背景と踏んだ落とし穴の全記録は `docs/MAYA_HOT_UPDATE_PATTERNS.md`。

============================================================================
CUSTOMIZE — 新しいツールを作るときはこのブロックだけ書き換える
============================================================================
"""

from __future__ import annotations

import os
import re
import sys


# ─── CUSTOMIZE ────────────────────────────────────────────────────────────
_GITHUB_OWNER = "soltoluna"
_GITHUB_REPO = "maya-scripts-dev"
_GITHUB_BRANCH = "main"

# モノレポなので、リポジトリ内のツールフォルダ名を指定する。
# ツール 1 本 = 1 リポジトリにする場合は "" にする。
_REPO_SUBDIR = "ntk_tool_template"

_MODULE = "ntk_tool_template"           # パッケージ名（= フォルダ名）
_SHELF_BUTTON_LABEL = "ToolTmpl"        # シェルフに出す短い名前（10 文字以内）

# ダウンロード対象。 **新しい .py を足したら必ずここにも追記する。**
# 忘れると実機だけで ModuleNotFoundError になる（自宅では再現しない）。
# `python tools\check_tools.py <ツール名>` が突き合わせるので、コミット前に走らせる。
_REMOTE_FILES = (
    "__init__.py",
    "core.py",
    "ui.py",
    "dev_tools.py",
)
# ─── END CUSTOMIZE ────────────────────────────────────────────────────────


_WINDOW = _MODULE + "Win"
_GITHUB_API = "https://api.github.com/repos/%s/%s" % (_GITHUB_OWNER, _GITHUB_REPO)
_GITHUB_RAW = "https://raw.githubusercontent.com/%s/%s" % (_GITHUB_OWNER, _GITHUB_REPO)


def _remote_path(rel):
    """リポジトリ内でのパス。 モノレポなら `<ツールフォルダ>/<パッケージ>/<rel>`。"""
    parts = [p for p in (_REPO_SUBDIR, _MODULE, rel) if p]
    return "/".join(parts)


# --------------------------------------------------------------------------- #
# 強制上書きのための道具（Windows 対応）— patterns doc §1-3, §1-4
# --------------------------------------------------------------------------- #

def _force_writable(path):
    import stat
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass


def _force_rmtree(path):
    """read-only 属性やロックで転ぶ `rmtree` にリトライを付けたもの。"""
    import shutil
    import time

    def _on_error(func, p, _exc_info):
        try:
            _force_writable(p)
            func(p)
        except Exception:
            pass

    for _ in range(3):
        if not os.path.exists(path):
            return
        try:
            shutil.rmtree(path, onerror=_on_error)
        except Exception:
            time.sleep(0.2)
    if os.path.exists(path):
        raise RuntimeError("cannot remove %r" % (path,))


def _atomic_write_bytes(target, data):
    """一時ファイル + `os.replace` で上書きする。

    ディスクの上には常に「以前の完全な状態」か「新しい完全な状態」の
    どちらかしか存在しない。 書き込み中の中断で壊れた `.py` が残ると、
    以降の import が SyntaxError で全滅する。
    """
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.exists(target):
        _force_writable(target)
    tmp = target + ".tmp_install"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, target)


# --------------------------------------------------------------------------- #
# 取得
# --------------------------------------------------------------------------- #

def _resolve_latest_sha():
    """`main` の先端 commit SHA を取る。

    SHA 固定 URL が raw.githubusercontent.com に対する唯一の確実な
    cache buster（CDN の cache key は URL のパス部分だけ）。
    """
    import json
    import random
    import time
    from urllib.request import Request, urlopen

    salt = "%.6f_%d" % (time.time(), random.randint(0, 2 ** 32))
    req = Request(
        "%s/branches/%s?_=%s" % (_GITHUB_API, _GITHUB_BRANCH, salt),
        headers={
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "User-Agent": "%s-installer/%s" % (_MODULE, salt),
        },
    )
    try:
        resp = urlopen(req, timeout=30)
        try:
            sha = json.loads(resp.read().decode("utf-8"))["commit"]["sha"]
        finally:
            resp.close()
        print("[%s] resolved %s -> %s" % (_MODULE, _GITHUB_BRANCH, sha[:10]))
        return sha
    except Exception as exc:
        print("[%s] SHA lookup failed (%s); falling back to branch name "
              "(may hit CDN cache)" % (_MODULE, exc))
        return _GITHUB_BRANCH


def _collect_sources():
    """`_REMOTE_FILES` を**すべて**メモリに読み込んでから返す。

    1 本ずつ書きながら進めると、途中で落ちたときに新旧が混ざった
    パッケージが実機に残る。 揃ってから書けばその状態を作らない。
    ローカル開発用に `<MODULE>_USE_LOCAL=1` でリポジトリの実体を使える。
    """
    from urllib.request import Request, urlopen

    env_flag = _MODULE.upper() + "_USE_LOCAL"
    here = os.path.dirname(os.path.abspath(globals().get("__file__") or "."))
    use_local = (os.environ.get(env_flag) == "1"
                 and os.path.isdir(os.path.join(here, _MODULE)))

    sources = {}
    if use_local:
        print("[%s] %s=1 -> using local checkout %s" % (_MODULE, env_flag, here))
        for rel in _REMOTE_FILES:
            src = os.path.join(here, _MODULE, rel.replace("/", os.sep))
            with open(src, "rb") as fh:
                sources[rel] = fh.read()
    else:
        sha = _resolve_latest_sha()
        for rel in _REMOTE_FILES:
            url = "%s/%s/%s" % (_GITHUB_RAW, sha, _remote_path(rel))
            req = Request(url, headers={
                "Cache-Control": "no-cache",
                "User-Agent": "%s-installer/%s" % (_MODULE, sha[:10]),
            })
            try:
                resp = urlopen(req, timeout=30)
                try:
                    sources[rel] = resp.read()
                finally:
                    resp.close()
            except Exception as exc:
                raise RuntimeError("Failed to download %s: %s" % (url, exc))
            print("[%s]   fetched %s (%d bytes)" % (_MODULE, rel, len(sources[rel])))

    # 書く前に構文を確かめる。 プロキシが HTML のエラーページを返した場合も
    # ここで止まる（そのまま .py として置くと import が全滅する）
    for rel, data in sources.items():
        try:
            compile(data, rel, "exec")
        except SyntaxError as exc:
            raise RuntimeError("downloaded %s is not valid Python: %s" % (rel, exc))
    return sources


def _write_sources(dest_root, sources):
    pkg_dir = os.path.join(dest_root, _MODULE)
    for rel, data in sources.items():
        target = os.path.join(pkg_dir, rel.replace("/", os.sep))
        _atomic_write_bytes(target, data)
        print("[%s]   -> %s (%d bytes)" % (_MODULE, target, len(data)))


# --------------------------------------------------------------------------- #
# 後処理
# --------------------------------------------------------------------------- #

def _verify_install(dest_root):
    pkg_dir = os.path.join(dest_root, _MODULE)
    for rel in _REMOTE_FILES:
        p = os.path.join(pkg_dir, rel.replace("/", os.sep))
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            raise RuntimeError("install verification failed - %s missing/empty" % (p,))


def _clean_pycache(dest_root):
    """`__pycache__` を消す — patterns doc §1-5。

    `.pyc` の有効性判定は元 `.py` の mtime なので、mtime が偶然一致すると
    古いバイトコードが使われ続ける。 毎回消すのが確実。
    """
    pkg_dir = os.path.join(dest_root, _MODULE)
    for root, dirs, _files in os.walk(pkg_dir):
        for d in list(dirs):
            if d == "__pycache__":
                _force_rmtree(os.path.join(root, d))
                dirs.remove(d)


def _flush_imports():
    """`sys.modules` から自分とサブモジュールを落とす — patterns doc §1-6。"""
    for name in list(sys.modules):
        if name == _MODULE or name.startswith(_MODULE + "."):
            sys.modules.pop(name, None)


def _read_installed_version(dest_root):
    p = os.path.join(dest_root, _MODULE, "__init__.py")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"""\s*__version__\s*=\s*['"]([^'"]+)['"]""", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "(unknown)"


def _close_existing_window():
    """更新前に開いているウィンドウを閉じる。

    ウィンドウ名は `<モジュール名>Win` 固定（CLAUDE.md の命名規則）。
    ここを外すと更新後に古いウィンドウが残る。
    """
    try:
        from maya import cmds
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# シェルフボタン（右クリックに Update — patterns doc §1-8）
# --------------------------------------------------------------------------- #

_SHELF_LAUNCH_CMD = (
    "# Auto-generated by %(mod)s install.py\n"
    "import sys\n"
    "for _m in [k for k in list(sys.modules)\n"
    "           if k == %(mod)r or k.startswith(%(mod)r + '.')]:\n"
    "    sys.modules.pop(_m, None)\n"
    "import %(mod)s as _t; _t.show()\n"
) % {"mod": _MODULE}

# Update は**パッケージに依存しない自己完結の snippet**にする。
# パッケージが壊れていても更新で復旧できるようにするため。
_SHELF_UPDATE_CMD = (
    "# Auto-generated by %(mod)s install.py\n"
    "import json, urllib.request\n"
    "_api = 'https://api.github.com/repos/%(owner)s/%(repo)s/branches/%(branch)s'\n"
    "_sha = json.loads(urllib.request.urlopen(_api, timeout=30).read())"
    "['commit']['sha']\n"
    "_u = 'https://raw.githubusercontent.com/%(owner)s/%(repo)s/' + _sha + "
    "'/%(path)s'\n"
    "print('[%(mod)s] update via SHA', _sha[:10])\n"
    "exec(compile(urllib.request.urlopen(_u, timeout=30).read(),\n"
    "             'install.py (from GitHub)', 'exec'),\n"
    "     {'__name__': 'install', '__file__': '<github>'})\n"
) % {
    "mod": _MODULE,
    "owner": _GITHUB_OWNER,
    "repo": _GITHUB_REPO,
    "branch": _GITHUB_BRANCH,
    "path": "/".join([p for p in (_REPO_SUBDIR, "install.py") if p]),
}


def _add_shelf_button():
    from maya import cmds, mel

    top_shelf = mel.eval("$tmp = $gShelfTopLevel")
    if not top_shelf or not cmds.tabLayout(top_shelf, exists=True):
        return
    current = cmds.tabLayout(top_shelf, q=True, selectTab=True)
    if not current:
        return

    # 貼り直しなので、同じラベルの既存ボタンは消してから作る
    for child in cmds.shelfLayout(current, q=True, ca=True) or []:
        try:
            if cmds.shelfButton(child, q=True, label=True) == _SHELF_BUTTON_LABEL:
                cmds.deleteUI(child)
        except Exception:
            pass

    button = cmds.shelfButton(
        parent=current,
        label=_SHELF_BUTTON_LABEL,
        annotation="Left-click: launch.  Right-click: update from GitHub.",
        image="pythonFamily.png",
        imageOverlayLabel=_SHELF_BUTTON_LABEL[:5],
        command=_SHELF_LAUNCH_CMD,
        sourceType="python",
    )
    popup = cmds.popupMenu(parent=button, button=3)
    cmds.menuItem(parent=popup, label="Launch Tool",
                  command=_SHELF_LAUNCH_CMD, sourceType="python")
    cmds.menuItem(parent=popup, divider=True)
    cmds.menuItem(parent=popup, label="Update from GitHub",
                  command=_SHELF_UPDATE_CMD, sourceType="python")


# --------------------------------------------------------------------------- #
# エントリポイント
# --------------------------------------------------------------------------- #

def install():
    from maya import cmds

    user_scripts = cmds.internalVar(userScriptDir=True).rstrip("/\\")
    if not os.path.isdir(user_scripts):
        os.makedirs(user_scripts)

    prev_version = _read_installed_version(user_scripts)

    _close_existing_window()
    sources = _collect_sources()          # 全部揃えてから
    _write_sources(user_scripts, sources)  # 書く
    _clean_pycache(user_scripts)
    _verify_install(user_scripts)
    _flush_imports()

    if user_scripts not in sys.path:
        sys.path.insert(0, user_scripts)

    _add_shelf_button()
    new_version = _read_installed_version(user_scripts)

    print("[%s] %s" % (_MODULE, "=" * 55))
    print("[%s] installed to:      %s" % (_MODULE, user_scripts))
    print("[%s] previous version:  %s" % (_MODULE, prev_version))
    print("[%s] current  version:  %s" % (_MODULE, new_version))
    print("[%s] %s" % (_MODULE, "=" * 55))

    try:
        cmds.confirmDialog(
            title=_SHELF_BUTTON_LABEL,
            message=("Installed to:\n%s\n\nVersion: %s -> %s\n\n"
                     "'%s' シェルフボタンを貼り直しました。\n"
                     "左クリックで起動、右クリックで GitHub から更新。"
                     % (user_scripts, prev_version, new_version,
                        _SHELF_BUTTON_LABEL)),
            button=["OK"])
    except Exception:
        pass
    return user_scripts


def onMayaDroppedPythonFile(*_args):
    install()


# Script Editor からの `exec(open(...).read())` は `__name__ == '__main__'` にも
# `onMayaDroppedPythonFile` にも乗らないので、ここで自動実行する。
# install() は冪等（書き込み前に全ファイルを揃える）なので、ドラッグ経由で
# 二重に走っても害はない。
try:
    from maya import cmds as _cmds  # noqa: F401
    install()
except ImportError:
    # Maya の外（テスト・静的検査）で読み込まれた場合は何もしない
    pass
