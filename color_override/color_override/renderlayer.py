# -*- coding: utf-8 -*-
"""レンダーセットアップ（Render Setup）越しに色を掛けるための薄い層。

**このモジュールの存在理由は「マテリアルの割り当てを書き換えないこと」。**

v0.5.0〜v0.9.2 は対象の shadingEngine を直接差し替えていた。 掛けた時点で
**フェース単位の割り当て（マルチマテリアル）が落ちる**ので、戻すために
「どのフェースがどの SG に入っていたか」を読み取って控える必要があった。
その読み取りが実機で通らず、3 版続けて外した（`CHANGELOG.md` の 0.5.0〜0.9.0）。

レンダーセットアップのマテリアルオーバーライドは**割り当てを触らない**。
レイヤーが表示されている間だけ別のマテリアルで描画し、外せば元がそのまま戻る。
**読み取りも控えも要らない**——問題の原因を突き止める代わりに、問題が起きる
構造そのものを無くした。

## 使う API（**2026-09-16 に Maya 2024 の実機で確認**）

    rs    = renderSetup.instance()
    layer = rs.createRenderLayer(name)
    col   = layer.createCollection(name)
    col.getSelector().setStaticSelection(nodes)
    ov    = col.createOverride(name, typeIDs.materialOverride)
    ov.setMaterial(shading_engine)      # setShader は**存在しない**
    rs.switchToLayer(layer)

- `MaterialOverride` は `override` ではなく **`connectionOverride`** モジュール
- レイヤーの削除は `rs.detachRenderLayer(layer)` → `cmds.delete(layer.name())`
  （`RenderLayer` 自体に削除メソッドは無い）
- 元の表示レイヤーは `rs.getVisibleRenderLayer()` で覚えて戻せる

## レイヤーのメンバー（**2026-10-01 に実機で判明。 v1.0.1 で対応**）

v1.0.0 は「アプライするとビューポートから消える」。 原因は 2 つあり、
**どちらもコレクションのメンバーの渡し方**だった。

1. **シェイプを渡すとメンバーとして効かない。** `setStaticSelection` に
   `|anm:pCube1|anm:pCubeShape1` を渡すと、Render Setup ウィンドウには
   並ぶのにレイヤーには入らない。 **トランスフォームを渡す**
   （実機で色が出た `probe_render_setup(try_it=True)` は選択物、つまり
   トランスフォームを渡していた。 v1.0.0 だけがシェイプに変えてしまった）
2. **レイヤーはコレクションに入っていないものをビューポートから消す。**
   色のコレクションだけでは「塗った物以外が消えたシーン」になる。
   オーバーライドを持たない土台のコレクションでシーン全体を抱える
   （`ensure_scene_collection`）

## 方針

- **import は関数の中で行う。** `maya.app.renderSetup` が無い / 無効な環境でも
  パッケージ自体は読めるようにする（旧方式に落とせなくなると詰む）
- 失敗は `RenderSetupError` 1 つに寄せる。 呼ぶ側が「使えなかった」と
  「使ったが失敗した」を区別せずに済む
"""

from __future__ import annotations

from maya import cmds


class RenderSetupError(RuntimeError):
    """レンダーセットアップを使えない／操作に失敗した。"""


def _modules():
    """`(renderSetup, typeIDs)` を返す。 使えなければ `RenderSetupError`。"""
    try:
        import maya.app.renderSetup.model.renderSetup as render_setup
        import maya.app.renderSetup.model.typeIDs as type_ids
    except Exception as exc:
        raise RenderSetupError(
            "レンダーセットアップを読み込めません: %s" % (exc,))
    return (render_setup, type_ids)


def available():
    """この環境でレンダーセットアップ方式を使えるか。"""
    try:
        _modules()
    except RenderSetupError:
        return False
    return True


def _instance():
    render_setup, _ = _modules()
    try:
        return render_setup.instance()
    except Exception as exc:
        raise RenderSetupError("renderSetup.instance() に失敗: %s" % (exc,))


# --------------------------------------------------------------------------- #
# レイヤー
# --------------------------------------------------------------------------- #

def find_layer(name):
    """名前でレイヤーを探す（無ければ None）。"""
    try:
        layers = _instance().getRenderLayers() or []
    except RenderSetupError:
        raise
    except Exception as exc:
        raise RenderSetupError("レイヤー一覧を取れません: %s" % (exc,))
    for layer in layers:
        try:
            if layer.name() == name:
                return layer
        except Exception:
            continue
    return None


def ensure_layer(name):
    """レイヤーを返す（無ければ作る）。"""
    layer = find_layer(name)
    if layer is not None:
        return layer
    try:
        return _instance().createRenderLayer(name)
    except Exception as exc:
        raise RenderSetupError("レイヤーを作れません: %s" % (exc,))


def delete_layer(name):
    """レイヤーを消す。 **消す前に既定のレイヤーへ戻す。**

    表示中のレイヤーを消すとビューポートが宙に浮く。
    """
    layer = find_layer(name)
    if layer is None:
        return False
    instance = _instance()
    try:
        if layer.isVisible():
            instance.switchToLayer(instance.getDefaultRenderLayer())
    except Exception:
        pass

    node = None
    try:
        node = layer.name()
    except Exception:
        pass
    try:
        # `RenderLayer` 自体に削除メソッドは無い。 外してからノードを消す
        instance.detachRenderLayer(layer)
    except Exception as exc:
        raise RenderSetupError("レイヤーを外せません: %s" % (exc,))
    if node and cmds.objExists(node):
        cmds.delete(node)
    return True


def visible_layer_name():
    """いま表示されているレイヤー名（既定レイヤーなら空文字）。"""
    instance = _instance()
    try:
        visible = instance.getVisibleRenderLayer()
        default = instance.getDefaultRenderLayer()
        if visible is None or visible is default:
            return ""
        return visible.name()
    except Exception:
        return ""


def show_layer(name):
    """そのレイヤーを表示する。 切り替える前の表示レイヤー名を返す。

    **戻り先を返すのが要点。** 実作業のレンダーレイヤーがあるシーンで、
    こちらの都合で表示を奪ったままにしない。
    """
    previous = visible_layer_name()
    layer = ensure_layer(name)
    try:
        _instance().switchToLayer(layer)
    except Exception as exc:
        raise RenderSetupError("レイヤーを表示できません: %s" % (exc,))
    return previous


def show_default_layer(previous=""):
    """既定のレイヤー（または `previous` で指定したレイヤー）へ戻す。"""
    instance = _instance()
    target = None
    if previous:
        target = find_layer(previous)
    if target is None:
        try:
            target = instance.getDefaultRenderLayer()
        except Exception as exc:
            raise RenderSetupError("既定レイヤーを取れません: %s" % (exc,))
    try:
        instance.switchToLayer(target)
    except Exception as exc:
        raise RenderSetupError("レイヤーを切り替えられません: %s" % (exc,))


def layer_is_visible(name):
    return visible_layer_name() == name


# --------------------------------------------------------------------------- #
# コレクション（= 1 つの色の掛かり）
# --------------------------------------------------------------------------- #

def scene_nodes():
    """レイヤーに「シーン全体」を入れるためのノード一覧。

    **トランスフォームを渡す。** シェイプだけではレイヤーのメンバーとして
    効かない（v1.0.0 の不具合。 下の `ensure_scene_collection` 参照）。
    """
    return cmds.ls(dag=True, transforms=True, long=True) or []


def ensure_scene_collection(layer_name, collection_name, nodes=None):
    """**シーン全体を抱えるだけ**のコレクションを用意する（色は掛けない）。

    レンダーセットアップのレイヤーは、**コレクションに入っていないものを
    ビューポートから消す**。 色のコレクションしか無いと、掛けた瞬間に
    「塗った物以外が全部消えたシーン」になってしまう（v1.0.0 の不具合。
    報告は「アプライするとビューから消える」）。

    そこでオーバーライドを持たない土台のコレクションを 1 つ置き、レイヤーの
    メンバーをシーン全体にしておく。 オーバーライドが無いので、ここに
    入れること自体は何の変化も起こさない。

    **パターン（`*`）ではなく静的選択で渡す。** 実機で通ることを確認できて
    いるのは `setStaticSelection` だけで、パターンが効かなかったときに
    「何も見えない」に戻ってしまう。 代わりに**掛けるたび・表示するたびに
    呼び直して**、後から作られたものを取り込む。
    """
    layer = ensure_layer(layer_name)
    collection = find_collection(layer_name, collection_name)
    if collection is None:
        try:
            collection = layer.createCollection(collection_name)
        except Exception as exc:
            raise RenderSetupError("土台のコレクションを作れません: %s" % (exc,))
    try:
        collection.getSelector().setStaticSelection(
            list(nodes) if nodes is not None else scene_nodes())
    except Exception as exc:
        raise RenderSetupError("シーン全体を渡せません: %s" % (exc,))
    try:
        return collection.name()
    except Exception:
        return collection_name


def create_collection(layer_name, collection_name, nodes, shading_engine):
    """対象にマテリアルオーバーライドを掛けるコレクションを作る。

    `shading_engine` は**シェーダーではなく shadingEngine**。
    `MaterialOverride.setShader` は存在しない（実機で確認済み）。

    `nodes` は**シェイプではなくトランスフォーム**を渡す（v1.0.1）。
    シェイプを渡すとレイヤーのメンバーとして効かず、対象がビューポートから
    消える。 2026-09-17 に実機で色が出た `probe_render_setup(try_it=True)` が
    渡していたのも選択物（＝トランスフォーム）だった。

    作ったコレクションのノード名を返す（Maya が名前を変えることがあるので、
    指定した名前ではなく**実際の名前**を控える）。
    """
    _, type_ids = _modules()
    layer = ensure_layer(layer_name)

    try:
        collection = layer.createCollection(collection_name)
    except Exception as exc:
        raise RenderSetupError("コレクションを作れません: %s" % (exc,))

    try:
        # **静的選択で渡す。** パターンだと名前が一致する無関係なノードまで拾う
        collection.getSelector().setStaticSelection(list(nodes))
    except Exception as exc:
        raise RenderSetupError("対象を渡せません: %s" % (exc,))

    try:
        override = collection.createOverride(collection_name + "_mat",
                                             type_ids.materialOverride)
        override.setMaterial(shading_engine)
    except Exception as exc:
        raise RenderSetupError("マテリアルオーバーライドを作れません: %s"
                               % (exc,))
    try:
        return collection.name()
    except Exception:
        return collection_name


def find_collection(layer_name, collection_name):
    """レイヤーの中からコレクションを名前で探す（無ければ None）。"""
    layer = find_layer(layer_name)
    if layer is None:
        return None
    try:
        for collection in layer.getCollections() or []:
            if collection.name() == collection_name:
                return collection
    except Exception:
        return None
    return None


def delete_collection(layer_name, collection_name):
    """コレクションを消す（レイヤーからも外す）。"""
    layer = find_layer(layer_name)
    collection = find_collection(layer_name, collection_name)
    if layer is None or collection is None:
        return False
    try:
        layer.detachCollection(collection)
    except Exception as exc:
        raise RenderSetupError("コレクションを外せません: %s" % (exc,))
    if cmds.objExists(collection_name):
        cmds.delete(collection_name)
    return True


def collection_count(layer_name, ignore=()):
    """レイヤーが抱えている**色の**コレクションの数。

    `ignore` に土台のコレクション（`ensure_scene_collection`）を渡す。
    **土台を数に入れると 0 にならず、全部戻してもレイヤーが残る。**
    """
    layer = find_layer(layer_name)
    if layer is None:
        return 0
    skip = set(ignore or ())
    try:
        collections = layer.getCollections() or []
    except Exception:
        return 0
    count = 0
    for collection in collections:
        try:
            name = collection.name()
        except Exception:
            name = ""
        if name not in skip:
            count += 1
    return count


def set_collection_enabled(layer_name, collection_name, enabled):
    """コレクションの有効／無効を切り替える（= そのセットだけ色を外す）。"""
    collection = find_collection(layer_name, collection_name)
    if collection is None:
        return False
    try:
        collection.setSelfEnabled(bool(enabled))
    except Exception as exc:
        raise RenderSetupError("コレクションを切り替えられません: %s" % (exc,))
    return True


def collection_is_enabled(layer_name, collection_name):
    collection = find_collection(layer_name, collection_name)
    if collection is None:
        return False
    try:
        return bool(collection.isSelfEnabled())
    except Exception:
        return False


def set_collection_members(layer_name, collection_name, nodes):
    """コレクションが抱える対象を差し替える。

    **1 シェイプ = 1 オーバーライド**を保つための後始末に使う（グループに
    掛けたあと中の 1 つだけ色を変えたとき、そのシェイプは新しいコレクションへ
    移る）。 古いほうに残したままだと、どちらの色が出るかが不定になる。
    """
    collection = find_collection(layer_name, collection_name)
    if collection is None:
        return False
    try:
        collection.getSelector().setStaticSelection(list(nodes))
    except Exception as exc:
        raise RenderSetupError("対象を差し替えられません: %s" % (exc,))
    return True


def collection_members(layer_name, collection_name):
    """コレクションが抱えている対象（静的選択）。"""
    collection = find_collection(layer_name, collection_name)
    if collection is None:
        return []
    try:
        return list(collection.getSelector().getStaticSelection() or [])
    except Exception:
        return []
