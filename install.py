# -*- coding: utf-8 -*-
"""Maya Tools — 全ツール共通のインストーラ（ドラッグ&ドロップ）。

エンドユーザーが触る唯一のファイル。 **このリポジトリの全ツールをまとめて**
インストール／更新する。 使い方は 2 通り:

1. このファイルを Maya のビューポートへドラッグ&ドロップする
2. Script Editor (Python) で次を実行する::

       exec(open(r"C:/path/to/install.py", encoding="utf-8").read())

   **`encoding="utf-8"` を省かないこと。** `open()` は省略すると OS の
   ロケール既定で読むので、日本語版 Windows では cp932 になり、
   このファイル（UTF-8 + 日本語コメント）が読めずに
   `UnicodeDecodeError` で落ちる（patterns doc §1-11）

どちらの場合も次を行う:

* GitHub から実装一式を **commit SHA 固定の URL** で取得する
  （`raw.githubusercontent.com` の CDN はクエリ文字列を無視してパスだけで
  キャッシュするので、`?_=<時刻>` では最新が取れない — patterns doc §1-7）
* **配布対象は tree API で自動列挙する。** リポジトリ直下の `<名前>/<名前>/`
  という形のフォルダをツールと見なし、その中身を全部配る。 ハードコードした
  ファイル一覧を持たないので、**モジュールを足して追記を忘れる事故（§1-10）が
  原理的に起きない**
* **全ツールのファイルをメモリに揃えてから**書き込む（途中で 1 本落ちても、
  中途半端に混ざった状態を実機に残さない）
* Windows の read-only を外し、tmp + `os.replace` で原子的に上書きする
* `__pycache__` を消す（`.pyc` は mtime ベースなので、古いバイトコードが
  新しいソースを覆い隠すことがある — §1-5）
* `sys.modules` から各ツールを落とす（次の import がディスクから読み直す）
* ツールごとにシェルフボタンを貼り直す（左クリック=起動 / 右クリック=更新）

**同じファイルを 2 回ドラッグしても何も起きない**（`onMayaDroppedPythonFile`
はセッション内で 1 度しか呼ばれない — §1-8）。 更新はツール UI の
「GitHub から更新」ボタンか、シェルフボタンの右クリックメニューから行う。

**このファイルはどのツールのパッケージにも依存しない。** パッケージが壊れて
いても更新で復旧できる必要があるため（`docs/TOOL_SCAFFOLD.md`）。

背景と踏んだ落とし穴の全記録は `docs/MAYA_HOT_UPDATE_PATTERNS.md`。

============================================================================
CUSTOMIZE — リポジトリを引っ越すときだけ書き換える
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

# optionVar / scriptJob / ウィンドウ名の衝突回避に使う接頭辞。
# **各パッケージの `__init__.py` の `NAMESPACE` と同じ値にする**
# （ずれると更新時に古いウィンドウを閉じられない。`check_tools.py` が検査する）。
# ツール名には付けない — ここは Maya の内部でぶつからないための札
_NAMESPACE = "ntk"
# ─── END CUSTOMIZE ────────────────────────────────────────────────────────


_GITHUB_API = "https://api.github.com/repos/%s/%s" % (_GITHUB_OWNER, _GITHUB_REPO)
_GITHUB_RAW = "https://raw.githubusercontent.com/%s/%s" % (_GITHUB_OWNER, _GITHUB_REPO)

_LOG = "maya-tools"

# リポジトリ直下の `<名前>/<名前>/...` だけをツールと見なす。
# `docs/templates/tool_template/tool_template/...` は先頭 2 段が
# `docs` / `templates` で一致しないので自動的に外れる
_TOOL_PATH = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)/(?P=name)/(?P<rel>.+)$")

# パッケージに置いてよいもの。 `.py` 以外（アイコン等）も配れるが、
# 巨大なバイナリが紛れ込むと更新が重くなるので拡張子で絞る
_ALLOWED_SUFFIXES = (".py", ".json", ".png", ".svg", ".ui", ".txt", ".md")

_USE_LOCAL_ENV = "MAYA_TOOLS_USE_LOCAL"

# **オフライン配布バンドルの合図。** このファイルが install.py の隣にあると、
# ハブは GitHub を一切見ず、隣のフォルダの中身だけをインストールする。
#
# 環境変数（`_USE_LOCAL_ENV`）だと受け取った人が Maya で先に Python を
# 実行しないといけない。 ファイルなら**ドラッグ&ドロップするだけ**で済む。
# 開発用のリポジトリには置かないので、普段の配布は今までどおり GitHub から。
# バンドルは `python tools\make_bundle.py <ツール名>` で作る
_OFFLINE_MARKER = "maya_tools_offline.txt"

# GitHub に届かないときの案内。 社内ネットワークでは TLS 傍受プロキシ・
# 自動構成スクリプト (PAC)・セキュリティソフトのどれかで **Maya の Python だけが
# 外に出られない**ことがある（ブラウザは通るので気づきにくい）。 その場合でも
# ブラウザで ZIP を落としてあればオフラインで入れられる
_OFFLINE_HINT = (
    "ブラウザで次を開いて ZIP をダウンロードし、展開してください:\n"
    "  https://github.com/%s/%s/archive/refs/heads/%s.zip\n\n"
    "展開した**フォルダの中にある** install.py を Maya のビューポートへ\n"
    "ドラッグ&ドロップすると、GitHub に接続せずにインストールできます。\n"
    "（install.py だけを取り出すとオフラインでは入りません）"
    % (_GITHUB_OWNER, _GITHUB_REPO, _GITHUB_BRANCH))


def _log(message):
    print("[%s] %s" % (_LOG, message))


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
# GitHub から取る
# --------------------------------------------------------------------------- #

def _urlopen(url, timeout=30, accept=None):
    from urllib.request import Request, urlopen
    headers = {
        "Cache-Control": "no-cache",
        "User-Agent": "%s-installer" % (_LOG,),
    }
    if accept:
        headers["Accept"] = accept
    resp = urlopen(Request(url, headers=headers), timeout=timeout)
    try:
        return resp.read()
    finally:
        resp.close()


def _resolve_latest_sha():
    """`main` の先端 commit SHA を取る。

    SHA 固定 URL が raw.githubusercontent.com に対する唯一の確実な
    cache buster（CDN の cache key は URL のパス部分だけ）。
    """
    import json
    import random
    import time

    salt = "%.6f_%d" % (time.time(), random.randint(0, 2 ** 32))
    url = "%s/branches/%s?_=%s" % (_GITHUB_API, _GITHUB_BRANCH, salt)
    try:
        sha = json.loads(_urlopen(url, accept="application/vnd.github+json")
                         .decode("utf-8"))["commit"]["sha"]
        _log("resolved %s -> %s" % (_GITHUB_BRANCH, sha[:10]))
        return sha
    except Exception as exc:
        _log("SHA lookup failed (%s); falling back to branch name "
             "(may hit CDN cache)" % (exc,))
        return _GITHUB_BRANCH


def _fetch_tree(sha):
    """`sha` 時点の全ファイルパスを 1 回の API コールで取る。

    ツールが何本あっても API コールは（SHA 解決と合わせて）2 回で済む。
    未認証の GitHub API は **1 時間 60 回 / IP** で、会社では NAT で
    全員が同じ枠を共有するため、ここを増やさないことに意味がある。
    """
    import json

    url = "%s/git/trees/%s?recursive=1" % (_GITHUB_API, sha)
    payload = json.loads(_urlopen(url, accept="application/vnd.github+json")
                         .decode("utf-8"))
    if payload.get("truncated"):
        raise RuntimeError(
            "GitHub の tree が truncated で返ってきた（リポジトリが大きすぎる）。"
            "配布対象を絞る仕組みが必要。")
    return [item["path"] for item in payload.get("tree", [])
            if item.get("type") == "blob"]


def _discover_tools(paths):
    """パスの一覧から `{ツール名: [パッケージ内の相対パス, ...]}` を作る。

    ツールの定義は「リポジトリ直下に `<名前>/<名前>/__init__.py` がある」こと。
    `check_tools.py` と `docs/TOOL_SCAFFOLD.md` の定義と同じで、
    **どこにも一覧を宣言しない**のがこの方式の要点。
    """
    tools = {}
    for path in paths:
        found = _TOOL_PATH.match(path)
        if not found:
            continue
        rel = found.group("rel")
        if "__pycache__" in rel.split("/"):
            continue
        if not rel.endswith(_ALLOWED_SUFFIXES):
            continue
        tools.setdefault(found.group("name"), []).append(rel)

    return {name: sorted(rels) for name, rels in tools.items()
            if "__init__.py" in rels}


def _local_tools(here):
    """ローカルのチェックアウトから同じ形の dict を作る（開発用）。"""
    paths = []
    for root, dirs, files in os.walk(here):
        # `docs/` `tools/` は除外しなくてよい — `<名前>/<名前>/` の形に
        # ならないので `_discover_tools` の正規表現が落とす
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for name in files:
            full = os.path.join(root, name)
            paths.append(os.path.relpath(full, here).replace(os.sep, "/"))
    return _discover_tools(paths)


def _offline_reason(here):
    """ネットワークを使わずに入れる指定があるか。 理由の文字列、無ければ None。

    2 通り受け付ける:

    * `maya_tools_offline.txt` が install.py の隣にある（配布バンドル）
    * 環境変数 `MAYA_TOOLS_USE_LOCAL=1`（開発中の動作確認用）
    """
    if not os.path.isdir(here):
        return None
    if os.path.isfile(os.path.join(here, _OFFLINE_MARKER)):
        return _OFFLINE_MARKER
    if os.environ.get(_USE_LOCAL_ENV) == "1":
        return "%s=1" % (_USE_LOCAL_ENV,)
    return None


def _offline_fallback(exc, here):
    """GitHub に届かないとき、install.py の隣から入れられるか尋ねる。

    **黙ってローカルに切り替えない。** 隣のフォルダの中身が最新とは限らず、
    「更新したつもりで古い版が入っていた」は実機で最も厄介な事故になるため、
    必ず確認を出して利用者に選ばせる。

    隣にツールが無ければ（install.py 単体を保存した場合）、ZIP を落とす
    手順を添えて諦める。
    """
    _log("GitHub への接続に失敗: %s" % (exc,))
    tools = _local_tools(here) if os.path.isdir(here) else {}

    if not tools:
        raise RuntimeError(
            "GitHub に接続できませんでした。\n  %s\n\n%s"
            % (exc, _OFFLINE_HINT))

    from maya import cmds

    proceed = "オフラインで入れる"
    answer = cmds.confirmDialog(
        title="Maya Tools",
        message=("GitHub に接続できませんでした。\n  %s\n\n"
                 "install.py の隣に %d 本のツールが見つかりました。\n"
                 "このフォルダの中身を**そのまま**インストールしますか？\n\n"
                 "※ 最新かどうかは、このフォルダをいつ取得したか次第です。"
                 % (exc, len(tools))),
        button=[proceed, "キャンセル"],
        defaultButton=proceed, cancelButton="キャンセル",
        dismissString="キャンセル")
    if answer != proceed:
        raise RuntimeError("インストールを中止しました（GitHub へ接続できず）。")

    _log("offline install from %s" % (here,))
    return tools


def _collect_sources(sha, tools, here=None):
    """**全ツールのファイルをすべて**メモリに読み込んでから返す。

    1 本ずつ書きながら進めると、途中で落ちたときに新旧が混ざった状態が
    実機に残る。 揃ってから書けばその状態を作らない。
    """
    use_local = here is not None
    sources = {}
    for name in sorted(tools):
        sources[name] = {}
        for rel in tools[name]:
            if use_local:
                src = os.path.join(here, name, name, rel.replace("/", os.sep))
                with open(src, "rb") as fh:
                    data = fh.read()
            else:
                url = "%s/%s/%s/%s/%s" % (_GITHUB_RAW, sha, name, name, rel)
                try:
                    data = _urlopen(url)
                except Exception as exc:
                    raise RuntimeError("Failed to download %s: %s" % (url, exc))
            sources[name][rel] = data
        _log("  fetched %s (%d files)" % (name, len(sources[name])))

    # 書く前に構文を確かめる。 プロキシが HTML のエラーページを返した場合も
    # ここで止まる（そのまま .py として置くと import が全滅する）
    for name, files in sources.items():
        for rel, data in files.items():
            if not rel.endswith(".py"):
                continue
            try:
                compile(data, "%s/%s" % (name, rel), "exec")
            except SyntaxError as exc:
                raise RuntimeError("downloaded %s/%s is not valid Python: %s"
                                   % (name, rel, exc))
    return sources


# --------------------------------------------------------------------------- #
# 書き込みと後処理
# --------------------------------------------------------------------------- #

def _write_tool(dest_root, name, files):
    pkg_dir = os.path.join(dest_root, name)
    for rel, data in sorted(files.items()):
        target = os.path.join(pkg_dir, rel.replace("/", os.sep))
        _atomic_write_bytes(target, data)


def _verify_install(dest_root, name, files):
    pkg_dir = os.path.join(dest_root, name)
    for rel in files:
        p = os.path.join(pkg_dir, rel.replace("/", os.sep))
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            raise RuntimeError("install verification failed - %s missing/empty"
                               % (p,))


def _clean_pycache(dest_root, name):
    """`__pycache__` を消す — patterns doc §1-5。

    `.pyc` の有効性判定は元 `.py` の mtime なので、mtime が偶然一致すると
    古いバイトコードが使われ続ける。 毎回消すのが確実。
    """
    pkg_dir = os.path.join(dest_root, name)
    for root, dirs, _files in os.walk(pkg_dir):
        for d in list(dirs):
            if d == "__pycache__":
                _force_rmtree(os.path.join(root, d))
                dirs.remove(d)


def _flush_imports(name):
    """`sys.modules` から自分とサブモジュールを落とす — patterns doc §1-6。"""
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            sys.modules.pop(key, None)


def _read_constant(source, name, default=""):
    """`NAME = "値"` をソース（bytes か str）から拾う。 import はしない。"""
    if isinstance(source, bytes):
        source = source.decode("utf-8", "replace")
    found = re.search(r"""^\s*%s\s*=\s*['"]([^'"]+)['"]""" % (name,),
                      source, re.M)
    return found.group(1) if found else default


def _read_installed_constant(dest_root, name, constant, default="(unknown)"):
    p = os.path.join(dest_root, name, "__init__.py")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return _read_constant(fh.read(), constant, default)
    except Exception:
        return default


def _shelf_label(name, init_source):
    """シェルフに出す短い名前。 パッケージの `SHELF_LABEL` を使う。

    無ければモジュール名から作る（`unload_reference_delete` → `UnlRefDel`）。
    """
    label = _read_constant(init_source, "SHELF_LABEL")
    if label:
        return label[:10]
    parts = [p for p in name.split("_") if p]
    return ("".join(p[:3].capitalize() for p in parts) or name)[:10]


def _close_existing_window(name, init_source):
    """更新前に開いているウィンドウを閉じる。

    ウィンドウ名は `<NAMESPACE>_<モジュール名>Win` 固定（CLAUDE.md の命名規則）。
    ここを外すと更新後に古いウィンドウが残る。
    """
    namespace = _read_constant(init_source, "NAMESPACE", _NAMESPACE)
    try:
        from maya import cmds
        window = "%s_%sWin" % (namespace, name)
        if cmds.window(window, exists=True):
            cmds.deleteUI(window)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# シェルフボタン（右クリックに Update — patterns doc §1-8）
# --------------------------------------------------------------------------- #

# Update は**どのパッケージにも依存しない自己完結の snippet**にする。
# パッケージが壊れていても更新で復旧できるようにするため
_SHELF_UPDATE_CMD = (
    "# Auto-generated by maya-scripts-dev install.py\n"
    "import json, urllib.request\n"
    "_api = 'https://api.github.com/repos/%(owner)s/%(repo)s/branches/%(branch)s'\n"
    "_sha = json.loads(urllib.request.urlopen(_api, timeout=30).read())"
    "['commit']['sha']\n"
    "_u = 'https://raw.githubusercontent.com/%(owner)s/%(repo)s/' + _sha + "
    "'/install.py'\n"
    "print('[maya-tools] update via SHA', _sha[:10])\n"
    "exec(compile(urllib.request.urlopen(_u, timeout=30).read(),\n"
    "             'install.py (from GitHub)', 'exec'),\n"
    "     {'__name__': 'install', '__file__': '<github>'})\n"
) % {"owner": _GITHUB_OWNER, "repo": _GITHUB_REPO, "branch": _GITHUB_BRANCH}


def _launch_cmd(name):
    return (
        "# Auto-generated by maya-scripts-dev install.py\n"
        "import sys\n"
        "for _m in [k for k in list(sys.modules)\n"
        "           if k == %(mod)r or k.startswith(%(mod)r + '.')]:\n"
        "    sys.modules.pop(_m, None)\n"
        "import %(mod)s as _t; _t.show()\n"
    ) % {"mod": name}


def _add_shelf_button(name, label):
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
            if cmds.shelfButton(child, q=True, label=True) == label:
                cmds.deleteUI(child)
        except Exception:
            pass

    launch = _launch_cmd(name)
    button = cmds.shelfButton(
        parent=current,
        label=label,
        annotation="Left-click: launch.  Right-click: update all tools.",
        image="pythonFamily.png",
        imageOverlayLabel=label[:5],
        command=launch,
        sourceType="python",
    )
    popup = cmds.popupMenu(parent=button, button=3)
    cmds.menuItem(parent=popup, label="Launch Tool",
                  command=launch, sourceType="python")
    cmds.menuItem(parent=popup, divider=True)
    cmds.menuItem(parent=popup, label="Update All Tools from GitHub",
                  command=_SHELF_UPDATE_CMD, sourceType="python")


# --------------------------------------------------------------------------- #
# エントリポイント
# --------------------------------------------------------------------------- #

def install():
    from maya import cmds

    user_scripts = cmds.internalVar(userScriptDir=True).rstrip("/\\")
    if not os.path.isdir(user_scripts):
        os.makedirs(user_scripts)

    here = os.path.dirname(os.path.abspath(globals().get("__file__") or "."))
    reason = _offline_reason(here)
    if reason:
        _log("%s -> ネットワークを使わず %s から入れる" % (reason, here))
        sha, tools = "(local)", _local_tools(here)
        if not tools:
            raise RuntimeError(
                "オフライン指定ですが、install.py の隣にツールが "
                "見つかりません。\n  %s\n\n"
                "`<名前>/<名前>/__init__.py` の形のフォルダが必要です "
                "（ZIP を展開した中の install.py をドラッグしてください）。"
                % (here,))
        _log("found %d tool(s): %s" % (len(tools), ", ".join(sorted(tools))))
        sources = _collect_sources(sha, tools, here=here)
    else:
        try:
            sha = _resolve_latest_sha()
            tools = _discover_tools(_fetch_tree(sha))
            if not tools:
                raise RuntimeError(
                    "配布対象のツールが 1 本も見つからない "
                    "（<名前>/<名前>/__init__.py の形になっているか）")
            _log("found %d tool(s): %s"
                 % (len(tools), ", ".join(sorted(tools))))
            sources = _collect_sources(sha, tools)   # 全部揃えてから
        except Exception as exc:
            # 社内ネットワークでは Maya の Python だけが外に出られないことが
            # ある。 生のトレースバックで終わらせず、逃げ道を出す
            sha = "(local)"
            tools = _offline_fallback(exc, here)
            sources = _collect_sources(sha, tools, here=here)

    # 旧バージョンは書き込む前に読む
    previous = {name: _read_installed_constant(user_scripts, name, "__version__")
                for name in sources}

    for name, files in sorted(sources.items()):
        _close_existing_window(name, files.get("__init__.py", b""))
        _write_tool(user_scripts, name, files)   # ここでようやく書く
        _clean_pycache(user_scripts, name)
        _verify_install(user_scripts, name, files)
        _flush_imports(name)

    if user_scripts not in sys.path:
        sys.path.insert(0, user_scripts)

    lines = []
    for name, files in sorted(sources.items()):
        label = _shelf_label(name, files.get("__init__.py", b""))
        _add_shelf_button(name, label)
        current = _read_installed_constant(user_scripts, name, "__version__")
        lines.append("%-28s %s -> %s  [%s]"
                     % (name, previous.get(name, "(unknown)"), current, label))

    _log("=" * 60)
    _log("installed to: %s" % (user_scripts,))
    for line in lines:
        _log("  " + line)
    _log("=" * 60)

    try:
        cmds.confirmDialog(
            title="Maya Tools",
            message=("Installed to:\n%s\n\n%s\n\n"
                     "シェルフボタンを貼り直しました。\n"
                     "左クリックで起動、右クリックで全ツールを更新。"
                     % (user_scripts, "\n".join(lines))),
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
