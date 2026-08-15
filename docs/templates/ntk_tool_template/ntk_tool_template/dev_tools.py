# -*- coding: utf-8 -*-
"""Tool Template — バージョン表示と「GitHub から更新」。

全ツール共通の仕組みなので、**中身は基本的に触らない**。 書き換えるのは
下の CUSTOMIZE ブロック（GitHub の座標）だけ。

更新の流れは 3 段に分けてある（patterns doc §1-9）。 ボタンのコールバックの中で
自分を載せている親ウィンドウを消すと、その後の `show()` で開いたウィンドウが
見えなくなる。 `evalDeferred` で「今のコールバックが完全に抜けてから」次の段を
走らせることで避ける。

    Stage 1  update_from_github()   ボタンの callback。 即 return するだけ
    Stage 2  _run_update()          idle 時に fetch → 自ウィンドウを閉じる → install.py を exec
    Stage 3  _reopen_after_update() さらに次の idle で開き直す

取得先は必ず **commit SHA 固定の URL**（patterns doc §1-7）。 ブランチ名の URL は
CDN のキャッシュに引っかかり、更新したのに古いコードが降ってくる。
"""

from __future__ import annotations

from maya import cmds

from . import __version__


# ─── CUSTOMIZE ────────────────────────────────────────────────────────────
# install.py と同じ値にする（`tools/check_tools.py` が突き合わせる）
_GITHUB_OWNER = "soltoluna"
_GITHUB_REPO = "maya-tools"
_GITHUB_BRANCH = "main"
_REPO_SUBDIR = "ntk_tool_template"   # モノレポ内のツールフォルダ名。 単独リポジトリなら ""
# ─── END CUSTOMIZE ────────────────────────────────────────────────────────


# パッケージ名は自分の位置から導く。 定数で持つとリネーム時にずれるため
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]

_GITHUB_API = "https://api.github.com/repos/%s/%s" % (_GITHUB_OWNER, _GITHUB_REPO)
_GITHUB_RAW = "https://raw.githubusercontent.com/%s/%s" % (_GITHUB_OWNER, _GITHUB_REPO)
_INSTALLER_PATH = "/".join([p for p in (_REPO_SUBDIR, "install.py") if p])


def resolve_latest_sha():
    """`main` の先端 commit SHA。 失敗したらブランチ名にフォールバックする。"""
    import json
    import random
    import time
    import urllib.request

    salt = "%.6f_%d" % (time.time(), random.randint(0, 2 ** 32))
    req = urllib.request.Request(
        "%s/branches/%s?_=%s" % (_GITHUB_API, _GITHUB_BRANCH, salt),
        headers={
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "User-Agent": "%s-updater/%s" % (_PACKAGE, salt),
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        try:
            return json.loads(resp.read().decode("utf-8"))["commit"]["sha"]
        finally:
            resp.close()
    except Exception as exc:
        print("[%s] SHA lookup failed (%s); falling back to %s"
              % (_PACKAGE, exc, _GITHUB_BRANCH))
        return _GITHUB_BRANCH


def update_from_github(*_args):
    """Stage 1 — UI ボタンのコールバック。 実作業は次の idle に回す。"""
    cmds.evalDeferred(_run_update, lowestPriority=True)


def _run_update():
    """Stage 2 — install.py を取ってきて実行し、`sys.modules` を落とす。"""
    import sys
    import traceback
    import urllib.request

    from . import ui

    sha = resolve_latest_sha()
    url = "%s/%s/%s" % (_GITHUB_RAW, sha, _INSTALLER_PATH)
    print("[%s] update: fetching %s" % (_PACKAGE, url))
    try:
        req = urllib.request.Request(url, headers={
            "Cache-Control": "no-cache",
            "User-Agent": "%s-updater/%s" % (_PACKAGE, sha[:10]),
        })
        resp = urllib.request.urlopen(req, timeout=30)
        try:
            source = resp.read()
        finally:
            resp.close()
    except Exception as exc:
        traceback.print_exc()
        cmds.confirmDialog(title="Update failed",
                           message="install.py の取得に失敗しました:\n%s" % (exc,),
                           button=["OK"])
        return

    if cmds.window(ui.WINDOW, exists=True):
        try:
            cmds.deleteUI(ui.WINDOW)
        except Exception:
            pass

    ns = {"__name__": "install", "__file__": "<github>"}
    try:
        exec(compile(source, "install.py (from GitHub)", "exec"), ns)
    except Exception as exc:
        traceback.print_exc()
        cmds.confirmDialog(
            title="Update failed",
            message=("install.py が例外を投げました:\n%s: %s\n\n"
                     "詳細は Script Editor を見てください。"
                     % (type(exc).__name__, exc)),
            button=["OK"])
        return

    # 次の import がディスクから読み直すよう、自分ごと落とす
    for name in [k for k in list(sys.modules)
                 if k == _PACKAGE or k.startswith(_PACKAGE + ".")]:
        sys.modules.pop(name, None)

    # install() のモーダルが完全に閉じてから開き直す
    cmds.evalDeferred(_reopen_after_update, lowestPriority=True)


def _reopen_after_update():
    """Stage 3 — 新しいコードで開き直す。"""
    import importlib
    import traceback
    try:
        mod = importlib.import_module(_PACKAGE)
        mod.show()
    except Exception as exc:
        traceback.print_exc()
        cmds.confirmDialog(
            title="Reopen failed",
            message=("更新は終わりましたが、ウィンドウの開き直しに失敗しました:\n"
                     "%s: %s\n\nシェルフボタンから開き直してください。"
                     % (type(exc).__name__, exc)),
            button=["OK"])


def build_footer():
    """ウィンドウ下端に「バージョン表示 + GitHub から更新」の 1 行を作る。

    呼び出し元のレイアウト直下に `rowLayout` を 1 つ足して抜ける
    （`setParent("..")` まで済ませるので、呼んだあとは元の階層のまま）。

    **バージョンは必ず目に見えるところに出す。** 実機が手元に無いので、
    「更新が届いたか」をユーザーに確かめてもらう唯一の手段がこの表示になる。
    """
    cmds.separator(h=10, style="in")
    cmds.rowLayout(nc=2, adj=1, cw2=(200, 130))
    cmds.text(l="%s  v%s" % (_PACKAGE, __version__),
              al="left", fn="smallObliqueLabelFont")
    cmds.button(l="GitHub から更新", h=24, c=update_from_github,
                ann="GitHub の最新版を取得して開き直します（Maya の再起動は不要）")
    cmds.setParent("..")
