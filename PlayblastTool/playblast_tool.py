# -*- coding: utf-8 -*-
"""
Render Layer Playblast Tool for Maya 2023
Maya 標準 Render Setup レンダーレイヤー作成 & プレイブラストツール
レイヤーごとにオブジェクトをマッピングして作成
"""

import maya.cmds as cmds
import maya.mel as mel
import os
import sys
import subprocess

try:
    import maya.app.renderSetup.model.renderSetup as renderSetup
    import maya.app.renderSetup.model.renderLayer as renderLayerModel
    import maya.app.renderSetup.model.collection as collectionModel
    _RS_API_AVAILABLE = True
except ImportError:
    _RS_API_AVAILABLE = False


# ---------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------

DEFAULT_LAYER_DEFS = [
    {"name": "CHA_01"},
    {"name": "BG"},
]


def _get_or_create_layer(rs, layer_name):
    for rl in rs.getRenderLayers():
        if rl.name() == layer_name:
            return rl, False
    return rs.createRenderLayer(layer_name), True


def _get_or_create_collection(rl_obj, col_name):
    for c in rl_obj.getCollections():
        if c.name() == col_name:
            return c, False
    return rl_obj.createCollection(col_name), True


def _add_objects_to_collection(col_obj, obj_list):
    """コレクションにオブジェクトを追加する"""
    if not obj_list:
        return
    # パイプ階層のみ除去し、ネームスペースは保持する
    # 例: |group|ns:pSphere1 -> ns:pSphere1
    short_names = [obj.split("|")[-1] for obj in obj_list]
    try:
        selector = col_obj.getSelector()
        if hasattr(selector, "setPattern"):
            existing = selector.getPattern() if hasattr(selector, "getPattern") else ""
            existing_items = [x.strip() for x in existing.split(",") if x.strip()]
            for name in short_names:
                if name not in existing_items:
                    existing_items.append(name)
            selector.setPattern(", ".join(existing_items))
            print("[PlayblastTool] setPattern で追加: {}".format(short_names))
            return
        if hasattr(selector, "setCustomPatternString"):
            existing = selector.getCustomPatternString() if hasattr(
                selector, "getCustomPatternString") else ""
            existing_items = [x.strip() for x in existing.split() if x.strip()]
            for name in short_names:
                if name not in existing_items:
                    existing_items.append(name)
            selector.setCustomPatternString(" ".join(existing_items))
            print("[PlayblastTool] setCustomPatternString で追加: {}".format(short_names))
            return
        sets_nodes = cmds.ls(col_obj.name(), type="objectSet") or []
        if sets_nodes:
            cmds.sets(obj_list, addElement=sets_nodes[0])
            print("[PlayblastTool] cmds.sets で追加: {}".format(short_names))
            return
        prev_sel = cmds.ls(selection=True, long=True) or []
        try:
            cmds.select(obj_list, replace=True)
            mel.eval('renderSetup -sel addSelected "{}";'.format(col_obj.name()))
            print("[PlayblastTool] MEL で追加: {}".format(short_names))
        finally:
            cmds.select(prev_sel, replace=True) if prev_sel else cmds.select(clear=True)
    except Exception as e:
        cmds.warning("[PlayblastTool] コレクションへのオブジェクト追加エラー: {}".format(e))


def create_render_setup_layers(layer_defs, layer_objects_map=None):
    """
    Render Setup レンダーレイヤーとコレクションを作成する。

    Parameters
    ----------
    layer_defs       : list[dict]  {"name": str}
    layer_objects_map: dict or None  {layer_name: [obj, ...]}
                       None の場合はすべて空のコレクション
    """
    if not _RS_API_AVAILABLE:
        cmds.warning("Render Setup API が利用できません。")
        return []

    rs      = renderSetup.instance()
    results = []

    for defn in layer_defs:
        layer_name = defn["name"]
        result = {"layer": layer_name, "collection": "",
                  "status": "", "message": "", "added_objects": []}
        try:
            rl_obj, layer_created = _get_or_create_layer(rs, layer_name)
            result["status"]  = "created" if layer_created else "exists"
            result["message"] = "作成" if layer_created else "既存"

            col_name = layer_name + "_col"
            col_obj, col_created = _get_or_create_collection(rl_obj, col_name)
            result["collection"] = col_obj.name()
            result["message"] += " / コレクション{}".format("追加" if col_created else "既存")

            obj_list = (layer_objects_map or {}).get(layer_name, [])
            if obj_list:
                _add_objects_to_collection(col_obj, obj_list)
                result["added_objects"] = list(obj_list)
                result["message"] += " / {}個のオブジェクト追加".format(len(obj_list))
            else:
                result["message"] += " / オブジェクトなし"

        except Exception as e:
            result["status"]  = "error"
            result["message"] = str(e)
            cmds.warning("[PlayblastTool] エラー ({}): {}".format(layer_name, e))

        results.append(result)
        print("[PlayblastTool] {} -> {}".format(layer_name, result["message"]))

    return results


# ---------------------------------------------------------------
# Playblast
# ---------------------------------------------------------------

def get_render_layers():
    layers = cmds.ls(type="renderLayer")
    return [l for l in layers if not cmds.referenceQuery(l, isNodeReferenced=True)]


def strip_rs_prefix(name):
    return name[3:] if name.startswith("rs_") else name


def get_scene_folder():
    scene_path = cmds.file(query=True, sceneName=True)
    return os.path.dirname(scene_path) if scene_path else None


def _play_notification_sound():
    """
    プレイブラスト完了時に通知音を鳴らす。
    Windows: winsound.MessageBeep
    macOS  : afplay でシステムサウンドを再生
    Linux  : print (端末ベル)
    """
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception as e:
        cmds.warning("[PlayblastTool] 通知音エラー: {}".format(e))


def open_in_explorer(folder_path):
    target = folder_path
    while target and not os.path.isdir(target):
        parent = os.path.dirname(target)
        if parent == target:
            target = None
            break
        target = parent
    if not target:
        cmds.warning("開けるフォルダが見つかりませんでした: {}".format(folder_path))
        return
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", os.path.normpath(target)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception as e:
        cmds.warning("フォルダを開けませんでした: {}".format(str(e)))


def _get_render_camera():
    """
    レンダリング設定で指定されているカメラ形状ノードを返す。
    取得できない場合は None。
    """
    try:
        # renderable フラグが立っているカメラを探す
        all_cams = cmds.ls(type="camera")
        renderable = [c for c in all_cams if cmds.getAttr(c + ".renderable")]
        return renderable[0] if renderable else None
    except Exception:
        return None


def _get_persp_camera():
    """パースカメラ (perspShape) を返す。存在しない場合は None。"""
    persp = cmds.ls("perspShape", type="camera")
    if persp:
        return persp[0]
    try:
        shapes = cmds.listRelatives("persp", shapes=True, type="camera") or []
        return shapes[0] if shapes else None
    except Exception:
        return None




def _get_active_camera():
    """
    現在アクティブなビューパネルのカメラ形状ノードを返す。
    フォーカス取得が失敗した場合は全モデルパネルの先頭カメラを返す。
    """
    # フォーカス中パネルから取得
    try:
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            cam_transform = cmds.modelEditor(panel, query=True, camera=True)
            shapes = cmds.listRelatives(cam_transform, shapes=True, type="camera") or []
            if shapes:
                return shapes[0]
    except Exception:
        pass
    # 全モデルパネルから先頭を取得
    try:
        model_panels = cmds.getPanel(type="modelPanel") or []
        for p in model_panels:
            cam_transform = cmds.modelEditor(p, query=True, camera=True)
            shapes = cmds.listRelatives(cam_transform, shapes=True, type="camera") or []
            if shapes:
                return shapes[0]
    except Exception:
        pass
    persp = cmds.ls("perspShape", type="camera")
    return persp[0] if persp else None


def _get_playblast_camera():
    """
    UIのラジオボタン設定に従いプレイブラストに使うカメラ形状ノードを返す。
    UIが開いていない場合はアクティブカメラを使う。
    """
    try:
        use_render = cmds.radioButton(CAMERA_RADIO_RENDER, query=True, select=True)
        use_persp  = cmds.radioButton(CAMERA_RADIO_PERSP,  query=True, select=True)
        use_active = cmds.radioButton(CAMERA_RADIO_ACTIVE, query=True, select=True)
    except Exception:
        use_render, use_persp, use_active = False, False, True   # デフォルト: アクティブカメラ

    if use_active:
        cam = _cached_active_camera or _get_active_camera()
        if cam:
            return cam
        cmds.warning("[PlayblastTool] アクティブカメラが取得できません。パースカメラを使用します。")
        return _get_persp_camera()

    if use_persp:
        return _get_persp_camera()

    if use_render:
        cam = _get_render_camera()
        if cam:
            return cam
        cmds.warning("[PlayblastTool] レンダリング設定カメラが見つかりません。パースカメラを使用します。")

    return _get_persp_camera()


def backup_output_folder(base_folder, target_layer_names=None):
    """
    base_folder 直下のレイヤーフォルダを
    base_folder/old/YYYYMMDD[_NNN]/ にコピーする。

    target_layer_names が指定されている場合は、その名前と一致する
    フォルダのみをバックアップする（関係ないフォルダを除外）。

    - old フォルダが存在しない場合は作成する
    - 今日の日付フォルダが既にある場合は _001, _002 ... とナンバリングする
    - base_folder が存在しない場合は何もしない

    Returns
    -------
    str  バックアップ先フォルダのパス（何もコピーしなかった場合は None）
    """
    import shutil
    import datetime

    if not base_folder or not os.path.isdir(base_folder):
        return None

    # old フォルダ
    old_root = os.path.join(base_folder, "old")

    # 今日の日付文字列
    today = datetime.date.today().strftime("%Y%m%d")

    # ナンバリング: YYYYMMDD が既存なら YYYYMMDD_001, _002 ...
    dest_name = today
    dest_path = os.path.join(old_root, dest_name)
    if os.path.exists(dest_path):
        idx = 1
        while True:
            dest_name = "{}_{}".format(today, str(idx).zfill(3))
            dest_path = os.path.join(old_root, dest_name)
            if not os.path.exists(dest_path):
                break
            idx += 1

    # base_folder 直下のサブフォルダを収集
    # target_layer_names が指定されている場合はその名前のフォルダのみ対象
    subdirs = []
    for entry in os.listdir(base_folder):
        if entry == "old":
            continue
        full = os.path.join(base_folder, entry)
        if not os.path.isdir(full):
            continue
        if target_layer_names is not None:
            if entry not in target_layer_names:
                continue
        subdirs.append(full)

    if not subdirs:
        return None

    # コピー実行
    os.makedirs(dest_path, exist_ok=True)
    for src_dir in subdirs:
        dst = os.path.join(dest_path, os.path.basename(src_dir))
        shutil.copytree(src_dir, dst)
        print("[PlayblastTool] バックアップ: {} -> {}".format(src_dir, dst))

    return dest_path


def _disable_camera_overlays(camera, disable_panzoom=False):
    """
    指定カメラシェイプの displayResolution / displaySafeAction /
    displayGateMask / displayFilmGate / overscan を無効化し元の値を返す。
    panZoomEnabled はトランスフォームノードに対して操作する。

    Parameters
    ----------
    camera : str  カメラシェイプノード名
    """
    saved = {}
    if not camera:
        return saved

    # シェイプノードのアトリビュート
    for attr in ("displayResolution", "displaySafeAction",
                 "displayGateMask", "displayFilmGate"):
        try:
            val = cmds.getAttr("{}.{}".format(camera, attr))
            saved[attr] = val
            cmds.setAttr("{}.{}".format(camera, attr), False)
        except Exception as e:
            cmds.warning("[PlayblastTool] {}.{}: {}".format(camera, attr, e))

    # overscan を 1.0 にリセット
    try:
        val = cmds.getAttr("{}.overscan".format(camera))
        saved["overscan"] = val
        cmds.setAttr("{}.overscan".format(camera), 1.0)
    except Exception as e:
        cmds.warning("[PlayblastTool] {}.overscan: {}".format(camera, e))

    # panZoomEnabled はトランスフォームノードのアトリビュート
    if disable_panzoom:
        parents = cmds.listRelatives(camera, parent=True) or []
        if parents:
            try:
                val = cmds.getAttr("{}.panZoomEnabled".format(parents[0]))
                saved["__panZoom_transform__"] = parents[0]
                saved["panZoomEnabled"] = val
                cmds.setAttr("{}.panZoomEnabled".format(parents[0]), False)
            except Exception as e:
                cmds.warning("[PlayblastTool] panZoomEnabled {}: {}".format(parents[0], e))

    print("[PlayblastTool] オーバーレイ無効化: {}".format(camera))
    return saved


def _restore_camera_overlays(camera, saved):
    """_disable_camera_overlays で保存した値を元に戻す。"""
    if not camera or not saved:
        return

    transform = saved.get("__panZoom_transform__")
    for attr, val in saved.items():
        if attr == "__panZoom_transform__":
            continue
        if attr == "panZoomEnabled" and transform:
            try:
                cmds.setAttr("{}.panZoomEnabled".format(transform), val)
            except Exception as e:
                cmds.warning("[PlayblastTool] panZoomEnabled 復元エラー: {}".format(e))
        else:
            try:
                cmds.setAttr("{}.{}".format(camera, attr), val)
            except Exception as e:
                cmds.warning("[PlayblastTool] {}.{} 復元エラー: {}".format(camera, attr, e))

    print("[PlayblastTool] オーバーレイ復元完了: {}".format(camera))


def run_playblast(layer_names, base_folder=None):
    output_base = base_folder if base_folder else get_scene_folder()
    if not output_base:
        cmds.confirmDialog(title="エラー",
                           message="出力先フォルダが設定されていません。",
                           button=["OK"], defaultButton="OK")
        return

    current_layer = cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True)

    # プレイブラスト前にカメラのオーバーレイを無効化
    # PANZOOM_CHECKBOX が存在する（UIが開いている）場合はその値を使う
    try:
        disable_panzoom = cmds.checkBox(PANZOOM_CHECKBOX, query=True, value=True)
    except Exception:
        disable_panzoom = True   # UI未表示時はデフォルトで無効化

    # アクティブカメラ選択かどうかを判定
    try:
        use_active = cmds.radioButton(CAMERA_RADIO_ACTIVE, query=True, select=True)
    except Exception:
        use_active = False

    if use_active:
        # アクティブカメラモード: カメラ指定なしでアクティブビューをそのまま使う
        # オーバーレイ無効化対象はアクティブビューのカメラ
        camera = _get_active_camera()
        cam_saved = _disable_camera_overlays(camera, disable_panzoom=disable_panzoom) if camera else {}
        prev_cam = None
        panel    = None
    else:
        # レンダリング設定 / パースカメラ: 指定カメラにビューを切り替える
        camera = _get_playblast_camera()
        cam_saved = _disable_camera_overlays(camera, disable_panzoom=disable_panzoom) if camera else {}
        prev_cam = None
        panel    = None
        try:
            panel = cmds.getPanel(withFocus=True)
            if panel and cmds.getPanel(typeOf=panel) == "modelPanel" and camera:
                cam_transform  = (cmds.listRelatives(camera, parent=True) or [camera])[0]
                prev_cam_shape = cmds.modelEditor(panel, query=True, camera=True)
                prev_cam = (cmds.listRelatives(prev_cam_shape, parent=True) or [prev_cam_shape])[0]
                if prev_cam != cam_transform:
                    cmds.lookThru(panel, cam_transform)
                else:
                    prev_cam = None   # 変更不要
        except Exception as e:
            cmds.warning("[PlayblastTool] カメラ切り替えエラー: {}".format(e))
            prev_cam = None

    errors = []
    try:
        for layer in layer_names:
            try:
                cmds.editRenderLayerGlobals(currentRenderLayer=layer)
                folder_name   = strip_rs_prefix(layer)
                output_folder = os.path.join(output_base, folder_name)
                if not os.path.exists(output_folder):
                    os.makedirs(output_folder)
                output_path = os.path.join(output_folder, folder_name)
                width  = cmds.getAttr("defaultResolution.width")
                height = cmds.getAttr("defaultResolution.height")
                cmds.playblast(format="image", compression="png",
                               filename=output_path, widthHeight=[width, height],
                               percent=100, framePadding=4,
                               forceOverwrite=True, viewer=False, showOrnaments=False)
                print("[PlayblastTool] 完了 (cam={}): {} -> {}".format(camera, layer, output_folder))
            except Exception as e:
                msg = "レイヤー '{}' でエラー: {}".format(layer, str(e))
                cmds.warning(msg)
                errors.append(msg)
    finally:
        # エラーが発生しても必ずカメラ・設定・レンダーレイヤーを元に戻す
        if camera and cam_saved:
            _restore_camera_overlays(camera, cam_saved)
        if prev_cam:
            try:
                cmds.lookThru(panel, prev_cam)
            except Exception:
                pass
        cmds.editRenderLayerGlobals(currentRenderLayer=current_layer)

    _play_notification_sound()
    if errors:
        cmds.confirmDialog(title="プレイブラスト完了（一部エラーあり）",
                           message="\n".join(errors), button=["OK"], defaultButton="OK")
    else:
        cmds.confirmDialog(title="プレイブラスト完了",
                           message="{} 個のレイヤーが完了しました。\n出力先: {}".format(
                               len(layer_names), output_base),
                           button=["OK"], defaultButton="OK")


# ---------------------------------------------------------------
# UI State
# ---------------------------------------------------------------

WINDOW_ID      = "renderLayerPlayblastWindow"
LAYER_DEF_LIST = "layerDefScrollList"     # 左: レイヤー一覧
OBJ_LIST       = "layerObjScrollList"     # 右: 選択レイヤーのオブジェクト一覧
OBJ_COUNT_TEXT = "layerObjCountText"      # 右: 件数ラベル
LAYER_LABEL    = "currentLayerLabel"      # 右: 現在のレイヤー名ラベル
SCROLL_LIST      = "renderLayerCheckList"   # プレイブラスト対象リスト
OUTPUT_FIELD     = "outputFolderField"
PANZOOM_CHECKBOX  = "disablePanZoomCheck"    # 2D Pan/Zoom 無効化チェックボックス
BACKUP_CHECKBOX   = "backupBeforePlayblast"  # プレイブラスト前バックアップ
CAMERA_RADIO_COLL = "cameraRadioCollection"  # カメラ選択ラジオボタングループ
CAMERA_RADIO_RENDER  = "cameraRadioRender"    # レンダリング設定カメラ
CAMERA_RADIO_PERSP   = "cameraRadioPersp"     # パースカメラ
CAMERA_RADIO_ACTIVE  = "cameraRadioActive"    # アクティブカメラ

# {"layer_name": [obj_long_path, ...]}
_layer_defs    = [dict(d) for d in DEFAULT_LAYER_DEFS]
_layer_obj_map = {}   # layer_name -> list[str]
_layer_map             = {}   # 表示名 -> renderLayer ノード名
_cached_active_camera  = None  # アクティブカメラ選択時にキャッシュ


def _selected_layer_name():
    """左リストで現在選択されているレイヤー名を返す。なければ None"""
    sel = cmds.textScrollList(LAYER_DEF_LIST, query=True, selectItem=True)
    return sel[0] if sel else None


# ---------------------------------------------------------------
# UI Callbacks - レイヤー定義リスト (左ペイン)
# ---------------------------------------------------------------

def refresh_layer_def_list(*args):
    existing = cmds.textScrollList(LAYER_DEF_LIST, query=True, allItems=True)
    if existing:
        cmds.textScrollList(LAYER_DEF_LIST, edit=True, removeAll=True)
    for defn in _layer_defs:
        name     = defn["name"]
        obj_cnt  = len(_layer_obj_map.get(name, []))
        label    = "{} ({} objs)".format(name, obj_cnt) if obj_cnt else name
        cmds.textScrollList(LAYER_DEF_LIST, edit=True, append=label)


def _layer_name_from_label(label):
    """'CHA_01 (3 objs)' のような表示文字列から実際のレイヤー名を取り出す"""
    return label.split(" (")[0]


def on_layer_selected(*args):
    """左リストの選択が変わったとき右ペインを更新する"""
    sel = cmds.textScrollList(LAYER_DEF_LIST, query=True, selectItem=True)
    if not sel:
        cmds.text(LAYER_LABEL,    edit=True, label="レイヤーを選択してください")
        cmds.text(OBJ_COUNT_TEXT, edit=True, label="")
        _refresh_obj_list([])
        return
    layer_name = _layer_name_from_label(sel[0])
    cmds.text(LAYER_LABEL,    edit=True, label="レイヤー: {}".format(layer_name))
    objs = _layer_obj_map.get(layer_name, [])
    cmds.text(OBJ_COUNT_TEXT, edit=True, label="{}個のオブジェクト".format(len(objs)))
    _refresh_obj_list(objs)


def on_add_layer_def(*args):
    name = cmds.textField("newLayerNameField", query=True, text=True).strip()
    if not name:
        return
    if any(d["name"] == name for d in _layer_defs):
        cmds.confirmDialog(title="重複", message="'{}' は既にリストにあります。".format(name),
                           button=["OK"], defaultButton="OK")
        return
    _layer_defs.append({"name": name})
    if name not in _layer_obj_map:
        _layer_obj_map[name] = []
    cmds.textField("newLayerNameField", edit=True, text="")
    refresh_layer_def_list()


def on_remove_layer_def(*args):
    sel = cmds.textScrollList(LAYER_DEF_LIST, query=True, selectItem=True)
    if not sel:
        return
    for label in sel:
        name = _layer_name_from_label(label)
        _layer_defs[:] = [d for d in _layer_defs if d["name"] != name]
        _layer_obj_map.pop(name, None)
    refresh_layer_def_list()
    # 右ペインをリセット
    cmds.text(LAYER_LABEL,    edit=True, label="レイヤーを選択してください")
    cmds.text(OBJ_COUNT_TEXT, edit=True, label="")
    _refresh_obj_list([])


# ---------------------------------------------------------------
# UI Callbacks - オブジェクトリスト (右ペイン)
# ---------------------------------------------------------------

def _refresh_obj_list(obj_list):
    """右ペインのオブジェクトリストを指定内容で更新する"""
    existing = cmds.textScrollList(OBJ_LIST, query=True, allItems=True)
    if existing:
        cmds.textScrollList(OBJ_LIST, edit=True, removeAll=True)
    for obj in obj_list:
        short = obj.split("|")[-1]
        cmds.textScrollList(OBJ_LIST, edit=True, append=short)


def on_capture_selection(*args):
    """ビューポートの選択を現在のレイヤーに追加する"""
    sel = cmds.textScrollList(LAYER_DEF_LIST, query=True, selectItem=True)
    if not sel:
        cmds.confirmDialog(title="レイヤー未選択",
                           message="レイヤー一覧からレイヤーを選択してください",
                           button=["OK"], defaultButton="OK")
        return
    layer_name = _layer_name_from_label(sel[0])
    viewport_sel = cmds.ls(selection=True, long=True)
    if not viewport_sel:
        cmds.confirmDialog(title="選択なし",
                           message="ビューポートでオブジェクトを選択してください。",
                           button=["OK"], defaultButton="OK")
        return
    current = _layer_obj_map.setdefault(layer_name, [])
    added = 0
    for obj in viewport_sel:
        if obj not in current:
            current.append(obj)
            added += 1
    cmds.text(OBJ_COUNT_TEXT, edit=True,
              label="{}個のオブジェクト".format(len(current)))
    _refresh_obj_list(current)
    refresh_layer_def_list()
    # 選択を復元
    if sel:
        cmds.textScrollList(LAYER_DEF_LIST, edit=True, selectItem=sel[0])
    print("[PlayblastTool] {} に {} 個追加しました".format(layer_name, added))


def on_remove_sel_obj(*args):
    """右ペインで選択中の行をそのレイヤーのリストから除去する"""
    layer_sel = cmds.textScrollList(LAYER_DEF_LIST, query=True, selectItem=True)
    if not layer_sel:
        return
    layer_name = _layer_name_from_label(layer_sel[0])
    obj_sel = cmds.textScrollList(OBJ_LIST, query=True, selectItem=True) or []
    current = _layer_obj_map.get(layer_name, [])
    # ショートネームで照合して削除
    _layer_obj_map[layer_name] = [
        o for o in current if o.split("|")[-1] not in obj_sel
    ]
    cmds.text(OBJ_COUNT_TEXT, edit=True,
              label="{}個のオブジェクト".format(len(_layer_obj_map[layer_name])))
    _refresh_obj_list(_layer_obj_map[layer_name])
    refresh_layer_def_list()
    if layer_sel:
        cmds.textScrollList(LAYER_DEF_LIST, edit=True, selectItem=layer_sel[0])


def on_clear_layer_objs(*args):
    """現在のレイヤーのオブジェクトリストをクリアする"""
    sel = cmds.textScrollList(LAYER_DEF_LIST, query=True, selectItem=True)
    if not sel:
        return
    layer_name = _layer_name_from_label(sel[0])
    _layer_obj_map[layer_name] = []
    cmds.text(OBJ_COUNT_TEXT, edit=True, label="0個のオブジェクト")
    _refresh_obj_list([])
    refresh_layer_def_list()
    if sel:
        cmds.textScrollList(LAYER_DEF_LIST, edit=True, selectItem=sel[0])


def on_clear_all_objs(*args):
    """全レイヤーのオブジェクトリストをクリアする"""
    for key in _layer_obj_map:
        _layer_obj_map[key] = []
    cmds.text(OBJ_COUNT_TEXT, edit=True, label="0個のオブジェクト")
    _refresh_obj_list([])
    refresh_layer_def_list()


# ---------------------------------------------------------------
# UI Callbacks - レイヤー作成
# ---------------------------------------------------------------

def on_create_layers_clicked(*args):
    """空のコレクションでレンダーレイヤーを作成"""
    if not _layer_defs:
        cmds.confirmDialog(title="レイヤーなし", message="作成するレイヤーがありません。",
                           button=["OK"], defaultButton="OK")
        return
    results = create_render_setup_layers(_layer_defs, layer_objects_map=None)
    _show_create_result(results)
    refresh_layer_list()


def on_create_layers_with_objects_clicked(*args):
    """レイヤーごとに設定されたオブジェクトをコレクションに追加してレイヤーを作成"""
    if not _layer_defs:
        cmds.confirmDialog(title="レイヤーなし", message="作成するレイヤーがありません。",
                           button=["OK"], defaultButton="OK")
        return
    # オブジェクトが1件も設定されていない場合は確認
    total_objs = sum(len(v) for v in _layer_obj_map.values())
    if total_objs == 0:
        ans = cmds.confirmDialog(
            title="オブジェクト未設定",
            message="すべてのレイヤーにオブジェクトが設定されていません。\n空のコレクションで作成しますか？",
            button=["作成する", "キャンセル"], defaultButton="キャンセル")
        if ans != "作成する":
            return
    results = create_render_setup_layers(_layer_defs, layer_objects_map=_layer_obj_map)
    _show_create_result(results)
    refresh_layer_list()


def _show_create_result(results):
    if not results:
        return
    lines = []
    for r in results:
        icon = "✓" if r["status"] in ("created", "exists") else "✗"
        lines.append("{} {}  |  {}".format(icon, r["layer"], r["message"]))
    cmds.confirmDialog(title="レンダーレイヤー作成完了",
                       message="\n".join(lines), button=["OK"], defaultButton="OK")
    # 新規作成するレイヤー一覧をクリア
    global _layer_defs, _layer_obj_map
    _layer_defs = []
    _layer_obj_map = {}
    try:
        refresh_layer_def_list()
        _refresh_obj_list([])
        cmds.text(LAYER_LABEL,    edit=True, label="レイヤーを選択してください")
        cmds.text(OBJ_COUNT_TEXT, edit=True, label="")
    except Exception:
        pass


# ---------------------------------------------------------------
# UI Callbacks - カメラ選択
# ---------------------------------------------------------------

def on_camera_radio_changed(*args):
    """カメラ選択ラジオボタンが変更されたときのコールバック。
    アクティブカメラ選択時は変更前（ビューにフォーカスがある状態）の
    カメラをキャッシュしておく。
    """
    global _cached_active_camera
    try:
        if cmds.radioButton(CAMERA_RADIO_ACTIVE, query=True, select=True):
            _cached_active_camera = _get_active_camera()
            print("[PlayblastTool] アクティブカメラをキャッシュ: {}".format(_cached_active_camera))
        else:
            _cached_active_camera = None
    except Exception as e:
        cmds.warning("[PlayblastTool] カメラキャッシュエラー: {}".format(e))


# ---------------------------------------------------------------
# UI Callbacks - 出力先 / プレイブラスト
# ---------------------------------------------------------------

def get_current_output_folder():
    custom = cmds.textField(OUTPUT_FIELD, query=True, text=True).strip()
    return custom if custom else get_scene_folder()


def refresh_layer_list(*args):
    global _layer_map
    _layer_map = {}
    existing = cmds.textScrollList(SCROLL_LIST, query=True, allItems=True)
    if existing:
        cmds.textScrollList(SCROLL_LIST, edit=True, removeAll=True)
    layers = get_render_layers()
    for layer in layers:
        display_name = strip_rs_prefix(layer)
        _layer_map[display_name] = layer
        cmds.textScrollList(SCROLL_LIST, edit=True, append=display_name)
    if layers:
        cmds.textScrollList(SCROLL_LIST, edit=True,
                            selectIndexedItem=list(range(1, len(layers) + 1)))


def on_browse_folder(*args):
    result = cmds.fileDialog2(dialogStyle=2, fileMode=3, caption="出力先フォルダを選択")
    if result:
        cmds.textField(OUTPUT_FIELD, edit=True, text=result[0])


def on_use_scene_folder(*args):
    cmds.textField(OUTPUT_FIELD, edit=True, text="")


def on_open_explorer(*args):
    folder = get_current_output_folder()
    if not folder:
        cmds.confirmDialog(title="エラー", message="出力先フォルダが設定されていません。",
                           button=["OK"], defaultButton="OK")
        return
    open_in_explorer(folder)


def on_backup_clicked(*args):
    """出力先フォルダの内容を old/<日付> にバックアップする"""
    folder = get_current_output_folder()
    if not folder:
        cmds.confirmDialog(title="エラー",
                           message="出力先フォルダが設定されていません。",
                           button=["OK"], defaultButton="OK")
        return
    if not os.path.isdir(folder):
        cmds.confirmDialog(title="エラー",
                           message="出力先フォルダが存在しません:\n{}".format(folder),
                           button=["OK"], defaultButton="OK")
        return

    dest = backup_output_folder(folder)
    if dest:
        cmds.confirmDialog(
            title="バックアップ完了",
            message="バックアップが完了しました。\n\n保存先:\n{}".format(dest),
            button=["OK"], defaultButton="OK"
        )
    else:
        cmds.confirmDialog(
            title="バックアップ",
            message="バックアップ対象のフォルダがありませんでした。",
            button=["OK"], defaultButton="OK"
        )


def on_playblast_clicked(*args):
    selected_display = cmds.textScrollList(SCROLL_LIST, query=True, selectItem=True)
    if not selected_display:
        cmds.confirmDialog(title="選択なし",
                           message="プレイブラストするレンダーレイヤーを選択してください。",
                           button=["OK"], defaultButton="OK")
        return
    custom_folder = cmds.textField(OUTPUT_FIELD, query=True, text=True).strip()
    base_folder   = custom_folder if custom_folder else None

    # バックアップチェックボックスがONならプレイブラスト前にバックアップ
    try:
        do_backup = cmds.checkBox(BACKUP_CHECKBOX, query=True, value=True)
    except Exception:
        do_backup = False

    if do_backup:
        folder = base_folder or get_scene_folder()
        if folder and os.path.isdir(folder):
            # 書き出し対象レイヤーのフォルダ名（rs_ プレフィックスを除去）のみバックアップ
            target_folders = [strip_rs_prefix(_layer_map.get(d, d)) for d in selected_display]
            dest = backup_output_folder(folder, target_layer_names=target_folders)
            if dest:
                print("[PlayblastTool] バックアップ完了: {}".format(dest))
            else:
                print("[PlayblastTool] バックアップ対象フォルダなし。スキップしました。")

    node_names = [_layer_map.get(d, d) for d in selected_display]
    run_playblast(node_names, base_folder=base_folder)


def on_select_all(*args):
    all_items = cmds.textScrollList(SCROLL_LIST, query=True, allItems=True) or []
    if all_items:
        cmds.textScrollList(SCROLL_LIST, edit=True,
                            selectIndexedItem=list(range(1, len(all_items) + 1)))


def on_deselect_all(*args):
    cmds.textScrollList(SCROLL_LIST, edit=True, deselectAll=True)


# ---------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------

def build_ui():
    if cmds.window(WINDOW_ID, exists=True):
        cmds.deleteUI(WINDOW_ID, window=True)

    # radioCollection はウィンドウ削除後も残留するため個別に削除する
    if cmds.radioCollection(CAMERA_RADIO_COLL, exists=True):
        cmds.deleteUI(CAMERA_RADIO_COLL, radioCollection=True)

    win = cmds.window(
        WINDOW_ID,
        title="Render Layer Playblast Tool",
        widthHeight=(660, 700),
        sizeable=True,
        resizeToFitChildren=False
    )
    root_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=0, parent=win)

    # ── プレイブラストボタン（最上部） ───────────────────────
    cmds.separator(height=6, style="none", parent=root_col)
    cmds.button(label="▶  選択したレイヤーをプレイブラスト",
                height=34, backgroundColor=(0.2, 0.55, 0.2),
                command=on_playblast_clicked, parent=root_col)
    cmds.separator(height=4, style="none", parent=root_col)
    cmds.separator(height=1, style="in",   parent=root_col)
    cmds.separator(height=4, style="none", parent=root_col)

    # ════════════════════════════════════════════════════════
    # セクション 1: レイヤー定義 / オブジェクトマッピング
    # ════════════════════════════════════════════════════════
    mapping_frame = cmds.frameLayout(
        label="レンダーレイヤー定義  /  オブジェクトマッピング",
        collapsable=True, collapse=False,
        marginWidth=8, marginHeight=8, parent=root_col
    )

    # 左右2カラム
    two_col = cmds.rowLayout(
        numberOfColumns=2,
        columnWidth2=(300, 320),
        columnAttach=[(1, "both", 4), (2, "both", 4)],
        adjustableColumn=2,
        parent=mapping_frame
    )

    # ── 左ペイン ────────────────────────────────────────────
    left_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4, parent=two_col)

    # 現在のレンダーレイヤー（プレイブラスト対象）
    cmds.text(label="現在のレンダーレイヤー", font="boldLabelFont",
              align="left", height=16, parent=left_col)
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(140, 140),
                   columnAttach=[(1, "both", 2), (2, "both", 2)], parent=left_col)
    cmds.button(label="全選択", height=22, command=on_select_all)
    cmds.button(label="全解除", height=22, command=on_deselect_all)
    cmds.setParent("..")
    cmds.textScrollList(SCROLL_LIST, numberOfRows=15, allowMultiSelection=True,
                        height=300, parent=left_col)
    cmds.button(label="リストを更新", height=24,
                command=refresh_layer_list, parent=left_col)

    cmds.setParent(two_col)  # left_col 終わり

    # ── 右ペイン ─────────────────────────────────────────────
    right_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4, parent=two_col)

       # ════════════════════════════════════════════════════════
    # セクション 2: レイヤー作成ボタン
    # ════════════════════════════════════════════════════════
    exec_frame = cmds.frameLayout(
        label="レンダーレイヤー作成",
        collapsable=True, collapse=False,
        marginWidth=10, marginHeight=8, parent=root_col
    )
    exec_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=6, parent=exec_frame)
    cmds.button(
        label="▶  空のコレクションでレンダーレイヤーを作成",
        height=28, backgroundColor=(0.35, 0.5, 0.25),
        command=on_create_layers_clicked, parent=exec_col
    )
    cmds.button(
        label="▶  レイヤーごとのオブジェクトをコレクションに含めてレンダーレイヤーを作成",
        height=28, backgroundColor=(0.28, 0.42, 0.6),
        command=on_create_layers_with_objects_clicked, parent=exec_col
    )
    cmds.setParent(root_col)
    cmds.separator(height=4, style="none", parent=root_col)

    # 新規作成するレンダーレイヤー一覧
    cmds.text(label="新規作成するレンダーレイヤー一覧", font="boldLabelFont",
              align="left", height=16, parent=right_col)
    cmds.textScrollList(
        LAYER_DEF_LIST,
        numberOfRows=4,
        allowMultiSelection=False,
        height=88,
        selectCommand=on_layer_selected,
        parent=right_col
    )
    cmds.rowLayout(numberOfColumns=3,
                   columnWidth3=(140, 60, 80),
                   columnAttach=[(1, "both", 2), (2, "both", 2), (3, "both", 2)],
                   adjustableColumn=1, parent=right_col)
    cmds.textField("newLayerNameField", placeholderText="レイヤー名", height=24)
    cmds.button(label="追加",    height=24, command=on_add_layer_def)
    cmds.button(label="選択削除", height=24, command=on_remove_layer_def)
    cmds.setParent("..")

    cmds.setParent(root_col)  # mapping_frame 終わり
    cmds.separator(height=4, style="none", parent=root_col)
    
    cmds.separator(height=6, style="in", parent=right_col)
    
    # 新規作成するレイヤーのコレクションに追加するオブジェクト一覧
    cmds.text(label="新規作成するレイヤーのコレクションに追加するオブジェクト一覧",
              font="boldLabelFont", align="center", height=20, parent=right_col)
    cmds.text(LAYER_LABEL, label="レイヤーを選択してください",
              font="smallPlainLabelFont", align="left", parent=right_col)
    cmds.text(OBJ_COUNT_TEXT, label="",
              font="smallPlainLabelFont", align="left", parent=right_col)
    cmds.textScrollList(
        OBJ_LIST,
        numberOfRows=6,
        allowMultiSelection=True,
        height=130,
        parent=right_col
    )
    cmds.rowLayout(numberOfColumns=3,
                   columnWidth3=(110, 100, 100),
                   columnAttach=[(1, "both", 2), (2, "both", 2), (3, "both", 2)],
                   parent=right_col)
    cmds.button(label="選択を取り込む", height=24,
                backgroundColor=(0.35, 0.52, 0.28),
                command=on_capture_selection)
    cmds.button(label="選択行を削除", height=24, command=on_remove_sel_obj)
    cmds.button(label="このレイヤーをクリア", height=24, command=on_clear_layer_objs)
    cmds.setParent("..")
    cmds.button(label="全レイヤーのオブジェクトをクリア", height=22,
                command=on_clear_all_objs, parent=right_col)

   
 

    # ════════════════════════════════════════════════════════
    # セクション 3: プレイブラスト設定
    # ════════════════════════════════════════════════════════
    settings_frame = cmds.frameLayout(
        label="プレイブラスト設定",
        collapsable=True, collapse=True,
        marginWidth=10, marginHeight=6, parent=root_col
    )
    settings_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=3, parent=settings_frame)
    for lbl, val in [
        ("フォーマット:",      "image  /  PNG"),
        ("ディスプレイサイズ:", "レンダー設定に従う"),
        ("スケール:",          "1.0  (100%)"),
        ("フレームパディング:", "4"),
    ]:
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(140, 260), parent=settings_col)
        cmds.text(label=lbl, align="right")
        cmds.text(label=val, align="left")
        cmds.setParent("..")
    cmds.setParent(root_col)

    # カメラ選択ラジオボタン
    cmds.radioCollection(CAMERA_RADIO_COLL, parent=root_col)
    cmds.rowLayout(
        numberOfColumns=4,
        columnWidth4=(130, 170, 155, 140),
        columnAttach=[(1, "both", 4), (2, "both", 4), (3, "both", 4), (4, "both", 4)],
        parent=root_col
    )
    cmds.text(label="プレイブラストカメラ:", align="right")
    cmds.radioButton(CAMERA_RADIO_ACTIVE, label="アクティブカメラ",
                     select=True,  collection=CAMERA_RADIO_COLL,
                     changeCommand=on_camera_radio_changed)
    cmds.radioButton(CAMERA_RADIO_PERSP,  label="パースカメラ (persp)",
                     select=False, collection=CAMERA_RADIO_COLL,
                     changeCommand=on_camera_radio_changed)
    cmds.radioButton(CAMERA_RADIO_RENDER, label="レンダリング設定カメラ",
                     select=False, collection=CAMERA_RADIO_COLL,
                     changeCommand=on_camera_radio_changed)
    cmds.setParent("..")
    cmds.separator(height=4, style="none", parent=root_col)
    cmds.checkBox(
        PANZOOM_CHECKBOX,
        label="2D Pan/Zoom を無効化してプレイブラスト（終了後に元に戻す）",
        value=True, height=24, parent=root_col
    )
    cmds.separator(height=4, style="none", parent=root_col)

    # ════════════════════════════════════════════════════════
    # セクション 4: 出力先フォルダ
    # ════════════════════════════════════════════════════════
    output_frame = cmds.frameLayout(
        label="出力先フォルダ",
        collapsable=True, collapse=False,
        marginWidth=10, marginHeight=8, parent=root_col
    )
    output_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=6, parent=output_frame)
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(480, 72),
                   columnAttach=[(1, "both", 0), (2, "both", 4)],
                   adjustableColumn=1, parent=output_col)
    cmds.textField(OUTPUT_FIELD,
                   placeholderText="空欄の場合はシーンファイルと同じフォルダに出力",
                   height=26)
    cmds.button(label="参照...", height=26, command=on_browse_folder)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(276, 276),
                   columnAttach=[(1, "both", 2), (2, "both", 2)],
                   parent=output_col)
    cmds.button(label="シーンフォルダを使用（クリア）", height=26, command=on_use_scene_folder)
    cmds.button(label="エクスプローラで開く", height=26,
                backgroundColor=(0.25, 0.45, 0.65), command=on_open_explorer)
    cmds.setParent("..")
    cmds.checkBox(
        BACKUP_CHECKBOX,
        label="プレイブラスト前に old フォルダへバックアップする",
        value=False, height=24, parent=output_col
    )
    cmds.setParent(root_col)
    cmds.separator(height=6, style="none", parent=root_col)

    cmds.showWindow(win)

    # 初期化
    for defn in _layer_defs:
        if defn["name"] not in _layer_obj_map:
            _layer_obj_map[defn["name"]] = []
    refresh_layer_def_list()
    refresh_layer_list()


# ---------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------

def main():
    build_ui()


if __name__ == "__main__":
    main()
