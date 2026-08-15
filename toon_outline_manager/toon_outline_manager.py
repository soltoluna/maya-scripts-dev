# toon_outline_manager.py
# Maya 2024 - Toon Outline Manager (PySide2)
# Usage: Run in Maya's Script Editor (Python tab), or import and call build_ui()

import maya.cmds as cmds
import maya.mel as mel
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from PySide2 import QtWidgets, QtCore, QtGui
from PySide2.QtCore import Qt

# =========================================================================== #
#  Maya core logic
# =========================================================================== #

GRP_NAME = "outline_grp"

def add_toon_outline_to_selected(use_group=False):
    sel = cmds.ls(selection=True, long=True)
    if not sel:
        return False, "オブジェクトが選択されていません"
    try:
        before = set(get_all_toon_transforms())
        mel.eval('assignNewPfxToon;')
        after = set(get_all_toon_transforms())
        new_tfms = list(after - before)
        for tfm in new_tfms:
            pfx = get_pfx_node(tfm)
            if pfx:
                cmds.setAttr(pfx + ".lineWidth", 0.2)
                cmds.setAttr(pfx + ".borderLines", False)
                cmds.setAttr(pfx + ".screenspaceWidth", False)
                cmds.setAttr(pfx + ".maxPixelWidth", 0.5)
        if use_group and new_tfms:
            # outline_grp が存在すればそれを使う、なければ作成
            if cmds.objExists(GRP_NAME):
                grp = GRP_NAME
            else:
                grp = cmds.group(empty=True, name=GRP_NAME, world=True)
            cmds.parent(new_tfms, grp)
        names = [n.split("|")[-1] for n in sel]
        label = ", ".join(names) if len(names) <= 3 else names[0] + " 他 " + str(len(names)-1) + " オブジェクト"
        return True, "Toon Outline を追加しました"
    except Exception as e:
        cmds.warning("Toon Outline 追加失敗: " + str(e))
        return False, "Toon Outline の追加に失敗しました"


def get_all_toon_transforms():
    result = []
    for pfx in (cmds.ls(type="pfxToon") or []):
        parents = cmds.listRelatives(pfx, parent=True, fullPath=False) or []
        for p in parents:
            if p not in result:
                result.append(p)
    return result


def get_pfx_node(transform):
    shapes = cmds.listRelatives(transform, shapes=True, fullPath=False) or []
    for s in shapes:
        if cmds.nodeType(s) == "pfxToon":
            return s
    return None


def get_node_visibility(transform):
    try:
        return bool(cmds.getAttr(transform + ".visibility"))
    except Exception:
        return True


def set_node_visibility(transform, visible):
    try:
        cmds.setAttr(transform + ".visibility", visible)
    except Exception as e:
        cmds.warning("visibility 変更失敗: " + transform + " - " + str(e))


def get_node_line_width(transform):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            return cmds.getAttr(pfx + ".lineWidth")
    except Exception:
        pass
    return 0.0


def set_node_line_width(transform, value):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            cmds.setAttr(pfx + ".lineWidth", value)
    except Exception as e:
        cmds.warning("lineWidth 変更失敗: " + transform + " - " + str(e))



def get_node_max_pixel_width(transform):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            return float(cmds.getAttr(pfx + ".maxPixelWidth"))
    except Exception:
        pass
    return 0.5


def set_node_max_pixel_width(transform, value):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            cmds.setAttr(pfx + ".maxPixelWidth", value)
    except Exception as e:
        cmds.warning("maxPixelWidth 変更失敗: " + transform + " - " + str(e))


def get_node_border_lines(transform):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            return bool(cmds.getAttr(pfx + ".borderLines"))
    except Exception:
        pass
    return False


def set_node_border_lines(transform, enabled):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            cmds.setAttr(pfx + ".borderLines", enabled)
    except Exception as e:
        cmds.warning("borderLines 変更失敗: " + transform + " - " + str(e))


def get_node_screenspace(transform):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            return bool(cmds.getAttr(pfx + ".screenspaceWidth"))
    except Exception:
        pass
    return False


def set_node_screenspace(transform, enabled):
    try:
        pfx = get_pfx_node(transform)
        if pfx:
            cmds.setAttr(pfx + ".screenspaceWidth", enabled)
    except Exception as e:
        cmds.warning("screenspaceWidth 変更失敗: " + transform + " - " + str(e))


# =========================================================================== #
#  Stylesheet
# =========================================================================== #

STYLE = """
QWidget {
    background-color: #22202a;
    color: #d8d0da;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 12px;
}

/* セクションタイトル */
QLabel#sectionTitle {
    color: #b898b8;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 2px 0px;
}

/* 区切り線 */
QFrame#divider {
    background-color: #38303a;
    max-height: 1px;
}

/* 汎用ボタン */
QPushButton {
    background-color: #302838;
    color: #d0c8d8;
    border: 1px solid #483850;
    border-radius: 4px;
    padding: 5px 10px;
}
QPushButton:hover {
    background-color: #3a3042;
    border-color: #806888;
}
QPushButton:pressed {
    background-color: #261e2e;
}

/* Add ボタン */
QPushButton#addBtn {
    background-color: #4a3058;
    border-color: #6a4878;
    color: #e8d8f0;
    padding: 7px 10px;
}
QPushButton#addBtn:hover {
    background-color: #5a3868;
}
QPushButton#addBtn:pressed {
    background-color: #382048;
}

/* 全選択ボタン */
QPushButton#selectAllBtn {
    background-color: #2e2840;
    border-color: #504868;
    color: #c0aed8;
}
QPushButton#selectAllBtn:hover { background-color: #38304c; }

/* 全解除ボタン */
QPushButton#deselectAllBtn {
    background-color: #38282e;
    border-color: #584048;
    color: #d8a8b8;
}
QPushButton#deselectAllBtn:hover { background-color: #443038; }

/* 更新ボタン */
QPushButton#refreshBtn {
    background-color: #2a2232;
    border-color: #3e3048;
    color: #9888a8;
    padding: 3px 8px;
}
QPushButton#refreshBtn:hover { background-color: #342a3e; }

/* 表示/非表示ボタン */
QPushButton#bulkVisBtn {
    padding: 6px 10px;
}

/* スライダー */
QSlider::groove:horizontal {
    background: #302838;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #9878b8;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #b898d8;
}
QSlider::sub-page:horizontal {
    background: #7858a0;
    border-radius: 2px;
}

/* 数値入力 */
QDoubleSpinBox {
    background-color: #2a2232;
    border: 1px solid #483858;
    border-radius: 4px;
    padding: 3px 6px;
    color: #d8c8e0;
    min-width: 68px;
}
QDoubleSpinBox:focus {
    border-color: #9878b8;
}

/* ノードリスト */
QScrollArea {
    border: 1px solid #38303a;
    border-radius: 4px;
    background-color: #1c1820;
}
QScrollBar:vertical {
    background: #221e28;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #584868;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

/* ノード行 */
QFrame#nodeRow {
    background-color: #1e1a26;
    border-radius: 3px;
}
QFrame#nodeRow[selected="true"] {
    background-color: #5a3870;
}

/* ノード名ラベル（クリック可能） */
QPushButton#nodeLabel {
    background-color: transparent;
    border: none;
    color: #888098;
    text-align: left;
    padding: 0px 6px;
    border-radius: 3px;
}
QPushButton#nodeLabel:hover {
    background-color: #2a1e34;
}
QPushButton#nodeLabel[selected="true"] {
    color: #f0d8ff;
    background-color: transparent;
}

/* 可視性ボタン */
QPushButton#visBtn {
    border-radius: 3px;
    padding: 2px 2px;
    font-size: 10px;
    min-width: 40px;
    max-width: 40px;
}
QPushButton#visBtn[visible="true"] {
    background-color: #2a3a2e;
    border: 1px solid #3a5a42;
    color: #90c8a0;
}
QPushButton#visBtn[visible="true"]:hover {
    background-color: #344838;
}
QPushButton#visBtn[visible="false"] {
    background-color: #3a2830;
    border: 1px solid #583840;
    color: #c09090;
}
QPushButton#visBtn[visible="false"]:hover {
    background-color: #483038;
}

/* 凡例テキスト */
QLabel#legend {
    color: #786878;
    font-size: 11px;
}

/* 適用対象テキスト */
QLabel#targetLabel {
    color: #707088;
    font-size: 11px;
}

/* コンテナ */
QWidget#section {
    background-color: #1a1a22;
    border: 1px solid #28283a;
    border-radius: 6px;
}
"""

# =========================================================================== #
#  Node row widget
# =========================================================================== #

class NodeRowWidget(QtWidgets.QFrame):
    selectionChanged = QtCore.Signal(str, bool)   # node, is_selected
    visibilityToggled = QtCore.Signal(str)         # node
    screenspaceToggled = QtCore.Signal(str)        # node
    borderLinesToggled = QtCore.Signal(str)        # node

    def __init__(self, node, width, visible, selected, parent=None):
        super().__init__(parent)
        self.node = node
        self._selected = selected
        self.setObjectName("nodeRow")
        self.setProperty("selected", selected)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(2)

        # ノード名ボタン
        ss = get_node_screenspace(node)
        mpw = get_node_max_pixel_width(node)
        bl = get_node_border_lines(node)
        self.nameBtn = QtWidgets.QPushButton(self._make_label(node, width, ss, mpw, bl))
        self.nameBtn.setObjectName("nodeLabel")
        self.nameBtn.setProperty("selected", selected)
        self.nameBtn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.nameBtn.clicked.connect(self._on_name_clicked)

        # 可視性ボタン
        self.visBtn = QtWidgets.QPushButton("表示")
        self.visBtn.setObjectName("visBtn")
        self.visBtn.setFixedWidth(40)
        self.visBtn.clicked.connect(self._on_vis_clicked)
        self.update_vis(visible)

        # Screenspace Width ボタン
        self.ssBtn = QtWidgets.QPushButton()
        self.ssBtn.setFixedWidth(40)
        self.ssBtn.clicked.connect(self._on_ss_clicked)
        self.update_ss(ss)

        # Border Lines ボタン
        self.blBtn = QtWidgets.QPushButton()
        self.blBtn.setFixedWidth(40)
        self.blBtn.clicked.connect(self._on_bl_clicked)
        self.update_bl(bl)

        layout.addWidget(self.nameBtn)
        layout.addWidget(self.blBtn)
        layout.addWidget(self.ssBtn)
        layout.addWidget(self.visBtn)

    def _make_label(self, node, width, ss, mpw, bl):
        ss_str = f"SS:{mpw:.2f}" if ss else "SS:off"
        bl_str = "BL:open" if bl else "BL:off"
        return f"  {node}   ( W:{width:.3f}  {ss_str}  {bl_str} )"

    def _on_name_clicked(self):
        self._selected = not self._selected
        self.set_selected(self._selected)
        self.selectionChanged.emit(self.node, self._selected)

    def _on_vis_clicked(self):
        self.visibilityToggled.emit(self.node)

    def _on_ss_clicked(self):
        self.screenspaceToggled.emit(self.node)

    def _on_bl_clicked(self):
        self.borderLinesToggled.emit(self.node)

    def set_selected(self, selected):
        self._selected = selected
        self.setProperty("selected", selected)
        self.nameBtn.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.nameBtn.style().unpolish(self.nameBtn)
        self.nameBtn.style().polish(self.nameBtn)

    def update_vis(self, visible):
        self.visBtn.setText("表示" if visible else "非表示")
        if visible:
            self.visBtn.setStyleSheet(
                "QPushButton { background-color: #2a3a2e; border: 1px solid #3a5a42;"
                " color: #90c8a0; border-radius: 3px; padding: 2px 6px; font-size: 11px; }"
                "QPushButton:hover { background-color: #344838; }"
            )
        else:
            self.visBtn.setStyleSheet(
                "QPushButton { background-color: #3a2830; border: 1px solid #583840;"
                " color: #c09090; border-radius: 3px; padding: 2px 6px; font-size: 11px; }"
                "QPushButton:hover { background-color: #483038; }"
            )

    def update_ss(self, enabled):
        self.ssBtn.setText("SS" if enabled else "SS")
        if enabled:
            self.ssBtn.setStyleSheet(
                "QPushButton { background-color: #2a3050; border: 1px solid #4050a0;"
                " color: #a0b8f0; border-radius: 3px; padding: 2px 4px; font-size: 11px; }"
                "QPushButton:hover { background-color: #343c60; }"
            )
        else:
            self.ssBtn.setStyleSheet(
                "QPushButton { background-color: #28242e; border: 1px solid #403848;"
                " color: #605870; border-radius: 3px; padding: 2px 4px; font-size: 11px; }"
                "QPushButton:hover { background-color: #322c3c; }"
            )

    def update_bl(self, enabled):
        self.blBtn.setText("BL")
        if enabled:
            self.blBtn.setStyleSheet(
                "QPushButton { background-color: #2a3050; border: 1px solid #5050a0;"
                " color: #b0a0f0; border-radius: 3px; padding: 2px 4px; font-size: 11px; }"
                "QPushButton:hover { background-color: #343c60; }"
            )
        else:
            self.blBtn.setStyleSheet(
                "QPushButton { background-color: #28242e; border: 1px solid #403848;"
                " color: #605870; border-radius: 3px; padding: 2px 4px; font-size: 11px; }"
                "QPushButton:hover { background-color: #322c3c; }"
            )

    def update_width_label(self, width):
        ss = get_node_screenspace(self.node)
        mpw = get_node_max_pixel_width(self.node)
        bl = get_node_border_lines(self.node)
        self.nameBtn.setText(self._make_label(self.node, width, ss, mpw, bl))

    def update_ss_label(self):
        w = get_node_line_width(self.node)
        ss = get_node_screenspace(self.node)
        mpw = get_node_max_pixel_width(self.node)
        bl = get_node_border_lines(self.node)
        self.nameBtn.setText(self._make_label(self.node, w, ss, mpw, bl))

    def update_bl_label(self):
        w = get_node_line_width(self.node)
        ss = get_node_screenspace(self.node)
        mpw = get_node_max_pixel_width(self.node)
        bl = get_node_border_lines(self.node)
        self.nameBtn.setText(self._make_label(self.node, w, ss, mpw, bl))


# =========================================================================== #
#  Main window
# =========================================================================== #

class ToonOutlineManager(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Toon Outline Manager")
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setMinimumWidth(360)
        self.setStyleSheet(STYLE)

        self._selected = set()       # 選択中ノード名
        self._row_widgets = {}       # node -> NodeRowWidget

        self._build_ui()
        self.refresh_node_list()

    # ------------------------------------------------------------------ #
    #  UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── ① Add Toon Outline ─────────────────────────────────────────
        root.addWidget(self._make_section_title("①  Add Toon Outline"))

        self.addBtn = QtWidgets.QPushButton("Add Toon Outline")
        self.addBtn.setObjectName("addBtn")
        self.addBtn.clicked.connect(self._on_add)
        root.addWidget(self.addBtn)

        addDesc = QtWidgets.QLabel("Width = 0.2 / Border line (BL) = OFF / Screenspace Width (SS) = 0.5 で作成")
        addDesc.setObjectName("legend")
        addDesc.setAlignment(Qt.AlignCenter)
        root.addWidget(addDesc)

        grpRow = QtWidgets.QHBoxLayout()
        grpRow.setSpacing(8)
        grpLbl = QtWidgets.QLabel("outline_grp の中に作成")
        grpLbl.setStyleSheet("QLabel { color: #c8b0d8; font-size: 12px; }")

        self.useGrpChk = QtWidgets.QPushButton("ON")
        self.useGrpChk.setCheckable(True)
        self.useGrpChk.setChecked(True)
        self.useGrpChk.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.useGrpChk.toggled.connect(self._update_grp_btn_style)

        grpRow.addWidget(self.useGrpChk)
        grpRow.addWidget(grpLbl)
        grpRow.addStretch()
        root.addLayout(grpRow)

        self._update_grp_btn_style(True)

        root.addWidget(self._make_divider())

        # ── ② Line Width / Visibility ───────────────────────────────────
        root.addWidget(self._make_section_title("②  Line Width  /  Visibility"))

        # ヘッダ行
        hdr = QtWidgets.QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        self.countLabel = QtWidgets.QLabel("— ノード")
        self.countLabel.setObjectName("targetLabel")
        self.legendLabel = QtWidgets.QLabel("表示 / 非表示")
        self.legendLabel.setObjectName("legend")
        self.legendLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.refreshBtn = QtWidgets.QPushButton("↺ 更新")
        self.refreshBtn.setObjectName("refreshBtn")
        self.refreshBtn.setFixedWidth(52)
        self.refreshBtn.clicked.connect(self.refresh_node_list)
        hdr.addWidget(self.countLabel)
        hdr.addWidget(self.legendLabel, 1)
        hdr.addSpacing(6)
        hdr.addWidget(self.refreshBtn)
        root.addLayout(hdr)

        # ノードリスト（スクロール）
        self.scrollArea = QtWidgets.QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.listContainer = QtWidgets.QWidget()
        self.listContainer.setStyleSheet("background-color: #18181f;")
        self.listLayout = QtWidgets.QVBoxLayout(self.listContainer)
        self.listLayout.setContentsMargins(3, 3, 3, 3)
        self.listLayout.setSpacing(2)
        self.listLayout.addStretch()

        self.scrollArea.setWidget(self.listContainer)
        root.addWidget(self.scrollArea)

        # 全選択 / 全解除
        selRow = QtWidgets.QHBoxLayout()
        selRow.setSpacing(4)
        self.selectAllBtn = QtWidgets.QPushButton("全て選択")
        self.selectAllBtn.setObjectName("selectAllBtn")
        self.deselectAllBtn = QtWidgets.QPushButton("全ての選択を解除")
        self.deselectAllBtn.setObjectName("deselectAllBtn")
        self.selectAllBtn.clicked.connect(self._on_select_all)
        self.deselectAllBtn.clicked.connect(self._on_deselect_all)
        selRow.addWidget(self.selectAllBtn)
        selRow.addWidget(self.deselectAllBtn)
        root.addLayout(selRow)

        # SS一括 / 表示非表示ボタン 横並び
        bulkRow = QtWidgets.QHBoxLayout()
        bulkRow.setSpacing(4)

        self.bulkSsBtn = QtWidgets.QPushButton("SS: ON")
        self.bulkSsBtn.setStyleSheet(
            "QPushButton { background-color: #1e3050; border: 1px solid #305090;"
            " color: #90b8f0; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #253c60; }"
        )
        self.bulkSsBtn.clicked.connect(self._on_bulk_toggle_ss)

        self.bulkVisBtn = QtWidgets.QPushButton("選択を非表示")
        self.bulkVisBtn.setObjectName("bulkVisBtn")
        self.bulkVisBtn.clicked.connect(self._on_bulk_toggle_vis)

        bulkRow.addWidget(self.bulkSsBtn)
        bulkRow.addWidget(self.bulkVisBtn)
        root.addLayout(bulkRow)

        root.addWidget(self._make_divider())

        # 適用対象ラベル
        self.targetLabel = QtWidgets.QLabel("適用対象:  ( 未選択 = 全ノードに適用 )")
        self.targetLabel.setObjectName("targetLabel")
        root.addWidget(self.targetLabel)

        # 線幅コントロール
        widthRow = QtWidgets.QHBoxLayout()
        widthRow.setSpacing(8)
        widthLbl = QtWidgets.QLabel("線幅")
        widthLbl.setFixedWidth(30)

        self.widthSpin = QtWidgets.QDoubleSpinBox()
        self.widthSpin.setRange(0.001, 20.0)
        self.widthSpin.setSingleStep(0.001)
        self.widthSpin.setDecimals(3)
        self.widthSpin.setValue(0.2)
        self.widthSpin.setFixedWidth(72)

        self.widthSlider = QtWidgets.QSlider(Qt.Horizontal)
        self.widthSlider.setRange(1, 5000)   # 実値 × 1000
        self.widthSlider.setValue(200)

        widthRow.addWidget(widthLbl)
        widthRow.addWidget(self.widthSpin)
        widthRow.addWidget(self.widthSlider, 1)
        root.addLayout(widthRow)

        # スライダー ↔ スピンボックス の同期
        self.widthSlider.valueChanged.connect(self._on_slider_changed)
        self.widthSpin.valueChanged.connect(self._on_spin_changed)
        self._slider_updating = False

        # Max Pixel Width コントロール（SS ON時のみ有効）
        self.ssRow = QtWidgets.QHBoxLayout()
        self.ssRow.setSpacing(8)
        ssLbl = QtWidgets.QLabel("SS max")
        ssLbl.setFixedWidth(45)
        ssLbl.setStyleSheet("QLabel { color: #9888a8; font-size: 11px; }")

        self.ssSpin = QtWidgets.QDoubleSpinBox()
        self.ssSpin.setRange(0.0, 100.0)
        self.ssSpin.setSingleStep(0.1)
        self.ssSpin.setDecimals(2)
        self.ssSpin.setValue(0.5)
        self.ssSpin.setFixedWidth(72)

        self.ssSlider = QtWidgets.QSlider(Qt.Horizontal)
        self.ssSlider.setRange(0, 10000)   # 実値 × 100
        self.ssSlider.setValue(50)

        self.ssRow.addWidget(ssLbl)
        self.ssRow.addWidget(self.ssSpin)
        self.ssRow.addWidget(self.ssSlider, 1)
        root.addLayout(self.ssRow)

        self.ssSlider.valueChanged.connect(self._on_ss_slider_changed)
        self.ssSpin.valueChanged.connect(self._on_ss_spin_changed)
        self._ss_updating = False
        self._update_ss_row_enabled()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _make_section_title(self, text):
        lbl = QtWidgets.QLabel(text.upper())
        lbl.setObjectName("sectionTitle")
        return lbl

    def _make_divider(self):
        line = QtWidgets.QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QtWidgets.QFrame.HLine)
        return line

    def _get_target_nodes(self):
        all_nodes = get_all_toon_transforms()
        sel = [n for n in all_nodes if n in self._selected]
        return sel if sel else all_nodes

    def _update_bulk_vis_btn(self):
        target = self._get_target_nodes()
        states = [get_node_visibility(n) for n in target]
        if not states or all(states):
            self.bulkVisBtn.setText("選択を非表示")
            self.bulkVisBtn.setStyleSheet(
                "QPushButton#bulkVisBtn { background-color: #3a2830; border-color: #583840; color: #c09090; }"
                "QPushButton#bulkVisBtn:hover { background-color: #483038; }"
            )
        elif not any(states):
            self.bulkVisBtn.setText("選択を表示")
            self.bulkVisBtn.setStyleSheet(
                "QPushButton#bulkVisBtn { background-color: #103020; border-color: #204530; color: #50b870; }"
                "QPushButton#bulkVisBtn:hover { background-color: #183c28; }"
            )
        else:
            self.bulkVisBtn.setText("表示 / 非表示  ( 混在 )")
            self.bulkVisBtn.setStyleSheet(
                "QPushButton#bulkVisBtn { background-color: #3a3010; border-color: #504020; color: #c0a840; }"
                "QPushButton#bulkVisBtn:hover { background-color: #4a3c18; }"
            )

    def _update_target_label(self):
        all_nodes = get_all_toon_transforms()
        sel = [n for n in all_nodes if n in self._selected]
        if sel:
            t = f"{len(sel)} ノード選択中" if len(sel) < len(all_nodes) else "全ノードに適用"
        else:
            t = "( 未選択 = 全ノードに適用 )"
        self.targetLabel.setText(f"適用対象:  {t}")

    def _update_scroll_height(self, count):
        row_h = 30
        h = max(56, min(count * row_h + 6, row_h * 8 + 6))
        self.scrollArea.setFixedHeight(h)

    # ------------------------------------------------------------------ #
    #  Node list
    # ------------------------------------------------------------------ #

    def refresh_node_list(self):
        nodes = get_all_toon_transforms()
        self._selected.intersection_update(set(nodes))

        # 既存ウィジェットをクリア
        while self.listLayout.count() > 1:
            item = self.listLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row_widgets.clear()

        for node in nodes:
            w = get_node_line_width(node)
            vis = get_node_visibility(node)
            sel = node in self._selected
            row = NodeRowWidget(node, w, vis, sel)
            row.selectionChanged.connect(self._on_row_selection)
            row.visibilityToggled.connect(self._on_row_vis_toggle)
            row.screenspaceToggled.connect(self._on_row_ss_toggle)
            row.borderLinesToggled.connect(self._on_row_bl_toggle)
            self.listLayout.insertWidget(self.listLayout.count() - 1, row)
            self._row_widgets[node] = row

        count = len(nodes)
        self.countLabel.setText(f"シーン内の Toon Outline ノード: {count} 件")
        self._update_scroll_height(count)
        self._update_target_label()
        self._update_bulk_vis_btn()
        self._update_bulk_ss_btn()
        self._sync_slider_to_selection()
        QtCore.QTimer.singleShot(0, self.adjustSize)

    # ------------------------------------------------------------------ #
    #  Slots
    # ------------------------------------------------------------------ #

    def _update_grp_btn_style(self, checked):
        if checked:
            self.useGrpChk.setText("ON")
            self.useGrpChk.setStyleSheet(
                "QPushButton { background-color: #4a2870; border: 1px solid #8050b0;"
                " color: #e0c0ff; border-radius: 4px; padding: 3px 8px; }"
                "QPushButton:hover { background-color: #5a3280; }"
            )
        else:
            self.useGrpChk.setText("OFF")
            self.useGrpChk.setStyleSheet(
                "QPushButton { background-color: #28202e; border: 1px solid #483858;"
                " color: #807090; border-radius: 4px; padding: 3px 8px; }"
                "QPushButton:hover { background-color: #322840; }"
            )

    def _on_add(self):
        ok, msg = add_toon_outline_to_selected(use_group=self.useGrpChk.isChecked())
        self.refresh_node_list()

    def _on_row_selection(self, node, selected):
        if selected:
            self._selected.add(node)
        else:
            self._selected.discard(node)
        self._update_target_label()
        self._update_bulk_vis_btn()
        self._update_bulk_ss_btn()
        self._sync_slider_to_selection()

    def _on_row_vis_toggle(self, node):
        vis = get_node_visibility(node)
        set_node_visibility(node, not vis)
        if node in self._row_widgets:
            self._row_widgets[node].update_vis(not vis)
        self._update_bulk_vis_btn()
        self._update_bulk_ss_btn()

    def _on_row_ss_toggle(self, node):
        ss = get_node_screenspace(node)
        set_node_screenspace(node, not ss)
        if node in self._row_widgets:
            self._row_widgets[node].update_ss(not ss)
            self._row_widgets[node].update_ss_label()
        self._update_ss_row_enabled()

    def _on_row_bl_toggle(self, node):
        bl = get_node_border_lines(node)
        set_node_border_lines(node, not bl)
        if node in self._row_widgets:
            self._row_widgets[node].update_bl(not bl)
            self._row_widgets[node].update_bl_label()

    def _update_ss_row_enabled(self):
        target = self._get_target_nodes()
        # 対象ノードのいずれかが SS ON なら有効
        any_ss = any(get_node_screenspace(n) for n in target) if target else False
        self.ssSpin.setEnabled(any_ss)
        self.ssSlider.setEnabled(any_ss)
        opacity = 1.0 if any_ss else 0.4
        self.ssRow.itemAt(0).widget().setStyleSheet(
            f"QLabel {{ color: rgba(152,136,168,{int(opacity*255)}); font-size: 11px; }}"
        )

    def _on_ss_slider_changed(self, int_val):
        if self._ss_updating:
            return
        value = int_val / 100.0
        self._ss_updating = True
        self.ssSpin.setValue(value)
        self._ss_updating = False
        for node in self._get_target_nodes():
            set_node_max_pixel_width(node, value)

    def _on_ss_spin_changed(self, value):
        if self._ss_updating:
            return
        self._ss_updating = True
        self.ssSlider.setValue(int(value * 100))
        self._ss_updating = False
        for node in self._get_target_nodes():
            set_node_max_pixel_width(node, value)
            if node in self._row_widgets:
                self._row_widgets[node].update_ss_label()

    def _on_select_all(self):
        nodes = get_all_toon_transforms()
        self._selected = set(nodes)
        for node, row in self._row_widgets.items():
            row.set_selected(True)
        self._update_target_label()
        self._update_bulk_vis_btn()
        self._update_bulk_ss_btn()
        self._sync_slider_to_selection()

    def _on_deselect_all(self):
        self._selected.clear()
        for row in self._row_widgets.values():
            row.set_selected(False)
        self._update_target_label()
        self._update_bulk_vis_btn()
        self._update_bulk_ss_btn()
        self._sync_slider_to_selection()

    def _on_bulk_toggle_ss(self):
        target = self._get_target_nodes()
        if not target:
            return
        states = [get_node_screenspace(n) for n in target]
        new_ss = not (all(states) or any(states))  # 全ON or 混在→OFF、全OFF→ON
        new_ss = False if any(states) else True
        for node in target:
            set_node_screenspace(node, new_ss)
            if node in self._row_widgets:
                self._row_widgets[node].update_ss(new_ss)
                self._row_widgets[node].update_ss_label()
        self._update_bulk_ss_btn()
        self._update_ss_row_enabled()

    def _update_bulk_ss_btn(self):
        if not cmds.ls(type="pfxToon"):
            return
        target = self._get_target_nodes()
        states = [get_node_screenspace(n) for n in target]
        if all(states):
            label, color = "SS: OFF にする", "#1e3050"
        elif not any(states):
            label, color = "SS: ON にする", "#1e3050"
        else:
            label, color = "SS: 混在", "#1e2840"
        self.bulkSsBtn.setText(label)
        self.bulkSsBtn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border: 1px solid #305090;"
            " color: #90b8f0; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #253c60; }"
        )

    def _on_bulk_toggle_vis(self):
        target = self._get_target_nodes()
        states = [get_node_visibility(n) for n in target]
        new_vis = not (all(states) or (any(states) and not all(states)))
        # 全表示or混在→非表示、全非表示→表示
        new_vis = False if (all(states) or (any(states))) else True
        for node in target:
            set_node_visibility(node, new_vis)
            if node in self._row_widgets:
                self._row_widgets[node].update_vis(new_vis)
        self._update_bulk_vis_btn()
        self._update_bulk_ss_btn()

    def _sync_slider_to_selection(self):
        target = self._get_target_nodes()
        if target:
            w = get_node_line_width(target[0])
            self._slider_updating = True
            self.widthSpin.setValue(w)
            self.widthSlider.setValue(int(w * 1000))
            self._slider_updating = False
            mpw = get_node_max_pixel_width(target[0])
            self._ss_updating = True
            self.ssSpin.setValue(mpw)
            self.ssSlider.setValue(int(mpw * 100))
            self._ss_updating = False
        self._update_ss_row_enabled()

    def _apply_width(self, value):
        if self._slider_updating:
            return
        for node in self._get_target_nodes():
            set_node_line_width(node, value)
            if node in self._row_widgets:
                self._row_widgets[node].update_width_label(value)

    def _on_slider_changed(self, int_val):
        if self._slider_updating:
            return
        value = int_val / 1000.0
        self._slider_updating = True
        self.widthSpin.setValue(value)
        self._slider_updating = False
        self._apply_width(value)

    def _on_spin_changed(self, value):
        if self._slider_updating:
            return
        self._slider_updating = True
        self.widthSlider.setValue(int(value * 1000))
        self._slider_updating = False
        self._apply_width(value)


# =========================================================================== #
#  Entry point
# =========================================================================== #

_window_instance = None
_WINDOW_OBJ_NAME = "ToonOutlineManagerWindow"

def build_ui():
    global _window_instance

    from maya import OpenMayaUI as omui
    from shiboken2 import wrapInstance
    ptr = omui.MQtUtil.mainWindow()
    maya_main = wrapInstance(int(ptr), QtWidgets.QWidget)

    # 既存ウィンドウをオブジェクト名で検索して確実に閉じる
    for widget in maya_main.findChildren(QtWidgets.QWidget, _WINDOW_OBJ_NAME):
        try:
            widget.close()
            widget.deleteLater()
        except Exception:
            pass
    if _window_instance is not None:
        try:
            _window_instance.close()
            _window_instance.deleteLater()
        except Exception:
            pass

    _window_instance = ToonOutlineManager(parent=maya_main)
    _window_instance.setObjectName(_WINDOW_OBJ_NAME)
    _window_instance.setAttribute(Qt.WA_DeleteOnClose, False)
    _window_instance.show()
    return _window_instance


if __name__ == "__main__":
    build_ui()
