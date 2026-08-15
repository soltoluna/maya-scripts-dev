# =============================================================================
# mgear_pkr_to_dwpicker.py
#
# mGear Anim Picker (.pkr) を DreamWall Picker (.json) に変換するスクリプト
#
# 使い方（Maya の Script Editor で実行）:
#
#   import sys
#   sys.path.insert(0, r"C:\Users\<ユーザー名>\Documents\maya\scripts")
#   import importlib, mgear_pkr_to_dwpicker
#   importlib.reload(mgear_pkr_to_dwpicker)
#   mgear_pkr_to_dwpicker.show()
#
# =============================================================================

import json
import uuid
import os
import math
from PySide2 import QtWidgets, QtCore, QtGui


# ---------------------------------------------------------------------------
# .pkr 読み込み
# ---------------------------------------------------------------------------

def load_pkr(pkr_path):
    try:
        with open(pkr_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace(': True', ': true').replace(': False', ': false')
        content = content.replace(':True', ':true').replace(':False', ':false')
        data = json.loads(content)
        return data
    except Exception:
        pass
    try:
        import pickle
        with open(pkr_path, 'rb') as f:
            data = pickle.load(f, encoding='latin1')
        return data
    except Exception as e:
        raise RuntimeError(".pkr の読み込みに失敗しました: {}".format(e))


# ---------------------------------------------------------------------------
# 色変換
# ---------------------------------------------------------------------------

def rgb_to_hex(color):
    if not color or len(color) < 3:
        return '#888888'
    if all(isinstance(c, float) and c <= 1.0 for c in color[:3]):
        r, g, b = [int(c * 255) for c in color[:3]]
    else:
        r, g, b = [int(c) for c in color[:3]]
    return '#{:02X}{:02X}{:02X}'.format(r, g, b)


def transparency_to_int(t):
    return int((t or 0.0) * 255)


# ---------------------------------------------------------------------------
# 形状判定・shape.path 変換
# ---------------------------------------------------------------------------

def _is_circle(handles):
    """頂点が原点中心の等距離円近似かどうかを判定"""
    if len(handles) < 6:
        return False
    dists = [math.sqrt(x**2 + y**2) for x, y in handles]
    avg = sum(dists) / len(dists)
    if avg == 0:
        return False
    variance = sum((d - avg)**2 for d in dists) / len(dists)
    return (variance / avg**2) < 0.05  # 5%以内のばらつきなら円とみなす


def _is_rect(handles):
    """4頂点で軸平行な四角形かどうかを判定"""
    if len(handles) != 4:
        return False
    xs = [h[0] for h in handles]
    ys = [h[1] for h in handles]
    # x が2種類・y が2種類なら軸平行四角形
    return len(set(round(x, 2) for x in xs)) == 2 and \
           len(set(round(y, 2) for y in ys)) == 2


def _is_diamond(handles):
    """ひし形判定（現在無効）"""
    return False


def classify_shape(handles):
    """
    handles リストから DWPicker の shape タイプと shape.path を返す

    mGear の handles 形式：
      2頂点  → 円（handles[1][0] が半径）
      3頂点  → 三角形
      4頂点  → 四角形（軸平行）または菱形
      5頂点  → 五角形
      8頂点  → 八角形（円近似）
      12頂点 → 十字形

    戻り値: (shape_type, shape_path)
      shape_type: 'square' | 'round' | 'custom'
      shape_path: [] または辞書リスト
    """
    n = len(handles)

    # 2頂点 → 円
    if n == 2:
        return 'round', []

    # 8頂点以上で等距離 → 円近似
    if n >= 6 and _is_circle(handles):
        return 'round', []

    # ひし形（縦横比ほぼ1:1の4頂点）→ _is_rect より先に判定
    # handles の bbox から中心・幅・高さを求め、ひし形の4頂点を相対座標で生成
    if n == 4 and _is_diamond(handles):
        xs = [h[0] for h in handles]
        ys = [h[1] for h in handles]
        w = max(xs) - min(xs)
        h_size = max(ys) - min(ys)
        # bbox の左上からの相対座標でひし形の4頂点（上・右・下・左）
        # bbox左上 = (min(xs), min(ys))、中心 = (w/2, h_size/2)
        path = [
            {'point': [w/2,      0       ], 'tangent_in': None, 'tangent_out': None},  # 上
            {'point': [w,        h_size/2], 'tangent_in': None, 'tangent_out': None},  # 右
            {'point': [w/2,      h_size  ], 'tangent_in': None, 'tangent_out': None},  # 下
            {'point': [0,        h_size/2], 'tangent_in': None, 'tangent_out': None},  # 左
        ]
        return 'custom', path

    # 軸平行四角形（ひし形でないもの）
    if _is_rect(handles):
        return 'square', []

    # それ以外（3・5・12頂点など）→ custom
    import math

    # 12頂点の十字形: mGear が45°傾けて描画するため -45°回転して×にする
    if n == 12:
        angle = math.radians(-45)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        handles = [
            [h[0]*cos_a - h[1]*sin_a, h[0]*sin_a + h[1]*cos_a]
            for h in handles
        ]

    # 5頂点の五角形: mGear の最初頂点が54°(右上)なので 36°回転して頂点を真上(90°)に
    elif n == 5:
        angle = math.radians(36)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        handles = [
            [h[0]*cos_a - h[1]*sin_a, h[0]*sin_a + h[1]*cos_a]
            for h in handles
        ]

    path = [{'point': [h[0], h[1]], 'tangent_in': None, 'tangent_out': None}
            for h in handles]
    return 'custom', path


def handles_to_rect(position, handles):
    """handles + position からバウンディングボックス (left, top, width, height) を返す"""
    if not handles:
        return position[0] - 25, position[1] - 10, 50, 20

    if len(handles) == 2:
        # 2頂点 = 円: handles[0]=[0,0]が中心、handles[1][0]が半径
        import math
        dx = handles[1][0] - handles[0][0]
        dy = handles[1][1] - handles[0][1]
        radius = math.sqrt(dx**2 + dy**2)
        if radius < 1:
            radius = 5
        diameter = radius * 2
        # 中心は position そのもの（handles[0]=[0,0]はオフセットなし）
        cx = position[0] + handles[0][0]
        cy = position[1] + handles[0][1]
        return cx - radius, cy - radius, diameter, diameter

    xs = [position[0] + h[0] for h in handles]
    ys = [position[1] + h[1] for h in handles]
    left   = min(xs)
    top    = min(ys)
    width  = max(max(xs) - left, 4)
    height = max(max(ys) - top, 4)
    return left, top, width, height


# ---------------------------------------------------------------------------
# 変換コア
# ---------------------------------------------------------------------------

def convert_picker(picker, scale=1.0, size_scale=1.0):
    """単一タブ (picker dict) を DWPicker 形式の dict に変換する"""
    shapes_data = picker['shapes']
    max_bottom = max(s['shape.top'] + s['shape.height'] for s in shapes_data)

    shapes = []
    for s in shapes_data:
        targets_raw = s.get('targets', '')
        target_list = (
            [t.strip() for t in targets_raw.split('\n') if t.strip()]
            if targets_raw else []
        )

        bgcolor     = rgb_to_hex(s.get('bgcolor.normal.color'))
        bordercolor = rgb_to_hex(s.get('border.normal.color'))
        textcolor   = rgb_to_hex(s.get('text.color', [1.0, 1.0, 1.0]))
        bg_transp   = transparency_to_int(s.get('bgcolor.normal.transparency', 0.0))

        original_left = s.get('shape.left', 0.0)
        original_top  = s.get('shape.top', 0.0)
        width         = s.get('shape.width', 120.0)
        height        = s.get('shape.height', 25.0)
        new_top       = max_bottom - original_top - height

        # handles があれば形状を判定、なければ中間ファイル由来なので square
        handles      = s.get('handles', [])
        shape_path   = s.get('shape.path', [])  # 既に変換済みの場合
        shape_type   = s.get('shape', 'square')

        if handles:
            shape_type, shape_path = classify_shape(handles)
            if shape_type == 'custom' and shape_path:
                n_h = len(handles)
                if n_h == 4 and _is_diamond(handles):
                    # ひし形: shape.path は bbox左上からの相対座標（Y下方向が正）
                    # → Y反転不要、スケールのみ適用
                    shape_path = [
                        {
                            'point': [p['point'][0] * scale * size_scale,
                                      p['point'][1] * scale * size_scale],
                            'tangent_in': None,
                            'tangent_out': None,
                        }
                        for p in shape_path
                    ]
                    # new_top は通常通り（bbox基準）
                    new_top = max_bottom - original_top - height
                else:
                    # その他 custom: shape.path は position からの相対座標（Y反転・スケール適用）
                    shape_path = [
                        {
                            'point': [p['point'][0] * scale * size_scale,
                                      -p['point'][1] * scale * size_scale],
                            'tangent_in': None,
                            'tangent_out': None,
                        }
                        for p in shape_path
                    ]
                    # custom シェイプは shape.left/top = position そのまま
                    # new_top は height を使わず position[1] だけで反転する
                    new_top = max_bottom - original_top

        shape = {
            'background':               not bool(target_list),
            'visibility_layer':         None,
            'shape.ignored_by_focus':   False,
            'panel':                    0,
            'shape':                    shape_type,
            'shape.space':              'world',
            'shape.anchor':             'top_left',
            'shape.path':               shape_path,
            'shape.left':               original_left * scale,
            'shape.top':                new_top * scale,
            'shape.width':              width * scale * size_scale,
            'shape.height':             height * scale * size_scale,
            'shape.cornersx':           4,
            'shape.cornersy':           4,
            'border':                   True,
            'borderwidth.normal':       1.0,
            'borderwidth.hovered':      1.25,
            'borderwidth.clicked':      2,
            'bordercolor.normal':       bordercolor,
            'bordercolor.hovered':      '#393939',
            'bordercolor.clicked':      '#FFFFFF',
            'bordercolor.transparency': 0,
            'bgcolor.normal':           bgcolor,
            'bgcolor.hovered':          '#AAAAAA',
            'bgcolor.clicked':          '#DDDDDD',
            'bgcolor.transparency':     bg_transp,
            'text.content':             s.get('text.content', ''),
            'text.size':                s.get('text.size', 12),
            'text.bold':                s.get('text.bold', False),
            'text.italic':              s.get('text.italic', False),
            'text.color':               textcolor,
            'text.valign':              s.get('text.valign', 'center'),
            'text.halign':              s.get('text.halign', 'center'),
            'action.targets':           target_list,
            'action.commands':          [],
            'action.menu_commands':     [],
            'image.path':               '',
            'image.fit':                True,
            'image.ratio':              True,
            'image.height':             32,
            'image.width':              32,
            'id':                       s.get('id', str(uuid.uuid4())),
            'children':                 [],
        }
        shapes.append(shape)

    return {
        'general': {
            'version':              [1, 0, 4],
            'name':                 picker['name'],
            'panels':               [[1.0, [1.0]]],
            'panels.orientation':   'vertical',
            'panels.zoom_locked':   [False],
            'panels.as_sub_tab':    False,
            'panels.colors':        [None],
            'panels.names':         ['Panel 1'],
            'hidden_layers':        [],
            'menu_commands':        [],
        },
        'shapes': shapes,
    }


def convert(pkr_path, output_dir=None, scale=0.8, tab_scales=None):
    """
    .pkr を DWPicker .json に変換してタブごとにファイル出力する

    pkr_path   : 入力 .pkr または中間 .json ファイルパス
    output_dir : 出力フォルダ（省略時は .pkr と同じ場所）
    scale      : 全体の位置・サイズ倍率（デフォルト 0.8）
    tab_scales : タブ別サイズ追加倍率 dict 例: {"facial": 0.5}
    """
    if output_dir is None:
        output_dir = os.path.dirname(pkr_path)
    if tab_scales is None:
        tab_scales = {}

    raw = load_pkr(pkr_path)

    if 'pickers' in raw:
        # 中間JSON形式（handles なし）
        pickers = raw['pickers']
    elif 'tabs' in raw:
        # 生の .pkr 形式（handles あり）← こちらを優先
        pickers = [
            {'name': t['name'], 'shapes': _tab_to_shapes(t)}
            for t in raw['tabs']
        ]
    else:
        raise RuntimeError("未対応の .pkr 形式です。キー: {}".format(list(raw.keys())))

    base_name = os.path.splitext(os.path.basename(pkr_path))[0]
    results = []

    for picker in pickers:
        tab_name   = picker['name']
        size_scale = tab_scales.get(tab_name, 1.0)
        dw_data    = convert_picker(picker, scale=scale, size_scale=size_scale)
        out_path   = os.path.join(output_dir, "{}_{}.json".format(base_name, tab_name))

        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(dw_data, f, indent=2, ensure_ascii=False)

        msg = "[OK] {} ({} shapes) -> {}".format(tab_name, len(dw_data['shapes']), out_path)
        print(msg)
        results.append(msg)

    return results


# ---------------------------------------------------------------------------
# 生の .pkr (tabs形式) → 中間形式 shapes リスト変換
# ---------------------------------------------------------------------------

def _tab_to_shapes(tab):
    """mGear tabs[n] を中間形式の shapes リストに変換（handles を保持）"""
    items = tab.get('data', {}).get('items', [])
    shapes = []
    for item in items:
        position = item.get('position', [0, 0])
        handles  = item.get('handles', [])
        color    = item.get('color', [115, 115, 115, 255])

        left, top, width, height = handles_to_rect(position, handles)

        # テキストラベル（controls なし・text あり）は position を中心に固定サイズにする
        label_text = item.get('text', '')
        if label_text and not item.get('controls', []):
            label_w = max(len(label_text) * 8 + 40, 80)
            label_h = 20
            left   = position[0] - label_w / 2
            top    = position[1] - label_h / 2
            width  = label_w
            height = label_h

        # custom シェイプ（3・5・12頂点など）の場合は
        # shape.left/top を position そのものにする
        # （shape.path が position からの相対座標になるため）
        n_handles = len(handles)
        is_custom = (
            n_handles >= 3 and
            not (n_handles == 2) and
            not (n_handles >= 6 and _is_circle(handles)) and
            not _is_rect(handles) and
            not (n_handles == 4 and _is_diamond(handles))
        )
        if is_custom and not (label_text and not item.get('controls', [])):
            left = position[0]
            top  = position[1]
            # width/height はパスのバウンディングボックスを維持

        a = color[3] / 255.0 if len(color) >= 4 else 1.0
        r, g, b = [c / 255.0 for c in color[:3]]

        controls = item.get('controls', [])
        targets  = '\n'.join(controls) if isinstance(controls, list) else str(controls)

        shapes.append({
            'id':                         str(uuid.uuid4()),
            'shape.left':                 left,
            'shape.top':                  top,
            'shape.width':                width,
            'shape.height':               height,
            'handles':                    handles,   # ← 形状判定のために保持
            'bgcolor.normal.color':       [r, g, b],
            'bgcolor.normal.transparency': 1.0 - a,
            'border.normal.color':        [r * 0.7, g * 0.7, b * 0.7],
            'border.normal.transparency': 0.0,
            'text.content':               item.get('text', ''),
            'text.color':                 [1.0, 1.0, 1.0],
            'text.size':                  item.get('text_size', 9),
            'text.bold':                  False,
            'text.italic':                False,
            'text.halign':                'center',
            'text.valign':                'center',
            'targets':                    targets,
        })
    return shapes


# ---------------------------------------------------------------------------
# タブ別スケール設定ウィジェット
# ---------------------------------------------------------------------------

class TabScaleWidget(QtWidgets.QWidget):
    def __init__(self, tab_name='', size_scale=1.0, parent=None):
        super(TabScaleWidget, self).__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.name_edit  = QtWidgets.QLineEdit(tab_name)
        self.name_edit.setPlaceholderText('タブ名')
        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 5.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setDecimals(2)
        self.scale_spin.setValue(size_scale)

        self.remove_btn = QtWidgets.QPushButton('✕')
        self.remove_btn.setFixedWidth(28)
        self.remove_btn.clicked.connect(self._remove)

        layout.addWidget(self.name_edit)
        layout.addWidget(QtWidgets.QLabel('サイズ倍率:'))
        layout.addWidget(self.scale_spin)
        layout.addWidget(self.remove_btn)

    def _remove(self):
        self.setParent(None)
        self.deleteLater()

    def values(self):
        return self.name_edit.text().strip(), self.scale_spin.value()


# ---------------------------------------------------------------------------
# メインUI
# ---------------------------------------------------------------------------

class PkrConverterUI(QtWidgets.QDialog):

    def __init__(self, parent=None):
        if parent is None:
            try:
                from maya import OpenMayaUI as omui
                from shiboken2 import wrapInstance
                ptr = omui.MQtUtil.mainWindow()
                parent = wrapInstance(int(ptr), QtWidgets.QWidget)
            except Exception:
                pass

        super(PkrConverterUI, self).__init__(parent)
        self.setWindowTitle('mGear Picker → DWPicker 変換ツール')
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(8)

        # 入力ファイル
        grp_in = QtWidgets.QGroupBox('入力 .pkr ファイル')
        lay_in = QtWidgets.QHBoxLayout(grp_in)
        self.pkr_edit = QtWidgets.QLineEdit()
        self.pkr_edit.setPlaceholderText('例: N:\\_Works\\Nakagawa\\picker\\rig.pkr')
        btn_pkr = QtWidgets.QPushButton('参照…')
        btn_pkr.clicked.connect(self._browse_pkr)
        lay_in.addWidget(self.pkr_edit)
        lay_in.addWidget(btn_pkr)
        root.addWidget(grp_in)

        # 出力フォルダ
        grp_out = QtWidgets.QGroupBox('出力フォルダ')
        lay_out = QtWidgets.QHBoxLayout(grp_out)
        self.out_edit = QtWidgets.QLineEdit()
        self.out_edit.setPlaceholderText('空白の場合は .pkr と同じフォルダに出力')
        btn_out = QtWidgets.QPushButton('参照…')
        btn_out.clicked.connect(self._browse_out)
        lay_out.addWidget(self.out_edit)
        lay_out.addWidget(btn_out)
        root.addWidget(grp_out)

        # 全体スケール
        grp_scale = QtWidgets.QGroupBox('全体スケール（位置・サイズ共通）')
        lay_scale = QtWidgets.QHBoxLayout(grp_scale)
        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 5.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setDecimals(2)
        self.scale_spin.setValue(0.8)
        lay_scale.addWidget(self.scale_spin)
        lay_scale.addStretch()
        root.addWidget(grp_scale)

        # タブ別サイズ倍率
        grp_tab = QtWidgets.QGroupBox('タブ別 サイズ追加倍率（オプション）')
        self.tab_layout = QtWidgets.QVBoxLayout(grp_tab)
        self.tab_layout.setSpacing(4)
        btn_add_tab = QtWidgets.QPushButton('＋ タブを追加')
        btn_add_tab.clicked.connect(self._add_tab_row)
        self.tab_layout.addWidget(btn_add_tab)
        root.addWidget(grp_tab)

        # ログ
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFixedHeight(120)
        self.log_edit.setPlaceholderText('変換ログがここに表示されます')
        root.addWidget(self.log_edit)

        # 実行ボタン
        btn_run = QtWidgets.QPushButton('変換実行')
        btn_run.setFixedHeight(36)
        btn_run.clicked.connect(self._run)
        root.addWidget(btn_run)

    def _browse_pkr(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, '入力 .pkr ファイルを選択', '', 'Picker Files (*.pkr *.json)')
        if path:
            self.pkr_edit.setText(path)
            if not self.out_edit.text():
                self.out_edit.setText(os.path.dirname(path))

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, '出力フォルダを選択', self.out_edit.text() or '')
        if path:
            self.out_edit.setText(path)

    def _add_tab_row(self, tab_name='', size_scale=1.0):
        row = TabScaleWidget(tab_name, size_scale, self)
        self.tab_layout.insertWidget(self.tab_layout.count() - 1, row)

    def _collect_tab_scales(self):
        tab_scales = {}
        for i in range(self.tab_layout.count()):
            widget = self.tab_layout.itemAt(i).widget()
            if isinstance(widget, TabScaleWidget):
                name, scale = widget.values()
                if name:
                    tab_scales[name] = scale
        return tab_scales

    def _run(self):
        self.log_edit.clear()

        pkr_path = self.pkr_edit.text().strip()
        if not pkr_path or not os.path.exists(pkr_path):
            self._log('ERROR: 入力ファイルが見つかりません: {}'.format(pkr_path))
            return

        out_dir = self.out_edit.text().strip() or None
        if out_dir and not os.path.isdir(out_dir):
            self._log('ERROR: 出力フォルダが存在しません: {}'.format(out_dir))
            return

        scale      = self.scale_spin.value()
        tab_scales = self._collect_tab_scales()

        self._log('変換開始...')
        self._log('入力: {}'.format(pkr_path))
        self._log('出力: {}'.format(out_dir or '(入力と同じフォルダ)'))
        self._log('スケール: {}  タブ別: {}'.format(scale, tab_scales))

        try:
            results = convert(
                pkr_path   = pkr_path,
                output_dir = out_dir,
                scale      = scale,
                tab_scales = tab_scales,
            )
            for r in results:
                self._log(r)
            self._log('\n変換完了！')
        except Exception as e:
            import traceback
            self._log('ERROR: {}'.format(e))
            self._log(traceback.format_exc())

    def _log(self, msg):
        self.log_edit.appendPlainText(msg)
        QtWidgets.QApplication.processEvents()


# ---------------------------------------------------------------------------
# 起動
# ---------------------------------------------------------------------------

_window = None

def show():
    global _window
    if _window is not None:
        try:
            _window.close()
        except Exception:
            pass
    _window = PkrConverterUI()
    _window.show()
    return _window
