# constraint_inspector.py
# Maya 2024 - Constraint Inspector Tool
# コンストレイン一覧・選択支援ツール

import maya.cmds as cmds
from PySide2 import QtWidgets, QtCore, QtGui
from PySide2.QtCore import Qt
import maya.OpenMayaUI as omui
from shiboken2 import wrapInstance

# ─── カラーパレット ──────────────────────────────────────────────
COLORS = {
    "bg_dark":        "#1E1A2E",   # 深いパープル（ベース）
    "bg_mid":         "#252038",   # ミッドトーン
    "bg_panel":       "#2E2845",   # パネル背景
    "bg_row_even":    "#2A2440",
    "bg_row_odd":     "#252038",
    "bg_row_hover":   "#3D3560",
    "bg_row_select":  "#5B3F8A",

    "accent_lavender":"#C9B8F5",   # メインアクセント
    "accent_pink":    "#F5A8C9",   # サブアクセント
    "accent_teal":    "#7FD8CE",   # ドライバー表示
    "accent_gold":    "#F5D08A",   # ドリブン表示

    "text_primary":   "#E8E2F5",
    "text_secondary": "#9A8FBB",
    "text_dim":       "#5C5278",

    "border":         "#3D3560",
    "border_focus":   "#C9B8F5",

    "type_parent":    "#A78BDF",
    "type_point":     "#7FC8F5",
    "type_orient":    "#F5A07F",
    "type_scale":     "#7FF5A0",
    "type_aim":       "#F5D07F",
    "type_geo":       "#F57FB8",
    "type_normal":    "#A0D8F5",
    "type_tangent":   "#D4F57F",
    "type_pole":      "#F5A0D4",
    "type_other":     "#9A9AB0",
}

# (bg_color, text_color) のペア — 背景を濃色にしてテキストを明色で統一
CONSTRAINT_TYPE_COLORS = {
    "parentConstraint":    ("#4A2D8A", "#D4BEFF"),  # 紫系
    "pointConstraint":     ("#1A4A6E", "#8DD6FF"),  # 青系
    "orientConstraint":    ("#6E3A1A", "#FFB87A"),  # オレンジ系
    "scaleConstraint":     ("#1A5E38", "#7FFFB0"),  # 緑系
    "aimConstraint":       ("#5E4E1A", "#FFE07A"),  # 黄系
    "geometryConstraint":  ("#6E1A42", "#FFB0D4"),  # ピンク系
    "normalConstraint":    ("#1A3E5E", "#A0D8FF"),  # 水色系
    "tangentConstraint":   ("#3E5E1A", "#C8FF7A"),  # 黄緑系
    "poleVectorConstraint":("#5E1A5A", "#FFB0F8"),  # マゼンタ系
}

STYLESHEET = f"""
QWidget {{
    background-color: {COLORS["bg_dark"]};
    color: {COLORS["text_primary"]};
    font-family: "Segoe UI", "Meiryo UI", sans-serif;
    font-size: 12px;
}}
QMainWindow, QDialog {{
    background-color: {COLORS["bg_dark"]};
}}

/* ヘッダー */
#header_widget {{
    background-color: {COLORS["bg_mid"]};
    border-bottom: 1px solid {COLORS["border"]};
}}
#title_label {{
    font-size: 15px;
    font-weight: bold;
    color: {COLORS["accent_lavender"]};
    letter-spacing: 0.5px;
}}
#subtitle_label {{
    font-size: 10px;
    color: {COLORS["text_secondary"]};
}}

/* ツールバーボタン */
QPushButton {{
    background-color: {COLORS["bg_panel"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 11px;
}}
QPushButton:hover {{
    background-color: {COLORS["bg_row_hover"]};
    border-color: {COLORS["accent_lavender"]};
    color: {COLORS["accent_lavender"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["bg_row_select"]};
}}
QPushButton#btn_primary {{
    background-color: {COLORS["bg_row_select"]};
    border-color: {COLORS["accent_lavender"]};
    color: {COLORS["accent_lavender"]};
    font-weight: bold;
}}
QPushButton#btn_primary:hover {{
    background-color: #6E4EA0;
}}
QPushButton#btn_driver {{
    border-color: {COLORS["accent_teal"]};
    color: {COLORS["accent_teal"]};
}}
QPushButton#btn_driver:hover {{
    background-color: rgba(127,216,206,0.15);
}}
QPushButton#btn_driven {{
    border-color: {COLORS["accent_gold"]};
    color: {COLORS["accent_gold"]};
}}
QPushButton#btn_driven:hover {{
    background-color: rgba(245,208,138,0.15);
}}

/* 検索/フィルター */
QLineEdit {{
    background-color: {COLORS["bg_panel"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {COLORS["bg_row_select"]};
}}
QLineEdit:focus {{
    border-color: {COLORS["accent_lavender"]};
}}
QComboBox {{
    background-color: {COLORS["bg_panel"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 130px;
}}
QComboBox:hover {{
    border-color: {COLORS["accent_lavender"]};
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["bg_row_select"]};
}}

/* テーブル */
QTableWidget {{
    background-color: {COLORS["bg_mid"]};
    alternate-background-color: {COLORS["bg_row_even"]};
    gridline-color: {COLORS["border"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    selection-background-color: {COLORS["bg_row_select"]};
    selection-color: {COLORS["text_primary"]};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}
QTableWidget::item:hover {{
    background-color: {COLORS["bg_row_hover"]};
}}
QTableWidget::item:selected {{
    background-color: {COLORS["bg_row_select"]};
}}
QHeaderView::section {{
    background-color: {COLORS["bg_panel"]};
    color: {COLORS["text_secondary"]};
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    border-right: 1px solid {COLORS["border"]};
    padding: 5px 8px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

/* ステータスバー */
QStatusBar {{
    background-color: {COLORS["bg_mid"]};
    color: {COLORS["text_secondary"]};
    border-top: 1px solid {COLORS["border"]};
    font-size: 10px;
    padding: 2px 8px;
}}

/* スプリッター */
QSplitter::handle {{
    background-color: {COLORS["border"]};
    width: 1px;
    height: 1px;
}}

/* スクロールバー */
QScrollBar:vertical {{
    background: {COLORS["bg_panel"]};
    width: 12px;
    border-left: 1px solid {COLORS["border"]};
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS["text_secondary"]};
    border-radius: 5px;
    min-height: 28px;
    margin: 2px 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["accent_lavender"]};
}}
QScrollBar::handle:vertical:pressed {{
    background: {COLORS["accent_pink"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background: {COLORS["bg_panel"]};
    height: 12px;
    border-top: 1px solid {COLORS["border"]};
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS["text_secondary"]};
    border-radius: 5px;
    min-width: 28px;
    margin: 2px 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COLORS["accent_lavender"]};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {COLORS["accent_pink"]};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* 詳細パネル */
#detail_panel {{
    background-color: {COLORS["bg_panel"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
}}
#detail_title {{
    font-size: 11px;
    font-weight: bold;
    color: {COLORS["text_secondary"]};
    letter-spacing: 0.8px;
}}
#node_name_label {{
    font-size: 13px;
    color: {COLORS["accent_lavender"]};
    font-weight: bold;
}}
#driver_label {{
    color: {COLORS["accent_teal"]};
    font-size: 12px;
}}
#driven_label {{
    color: {COLORS["accent_gold"]};
    font-size: 12px;
}}
#weight_label {{
    color: {COLORS["text_secondary"]};
    font-size: 11px;
}}

/* チェックボックス */
QCheckBox {{
    color: {COLORS["text_secondary"]};
    spacing: 5px;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {COLORS["border"]};
    border-radius: 2px;
    background: {COLORS["bg_panel"]};
}}
QCheckBox::indicator:checked {{
    background: {COLORS["bg_row_select"]};
    border-color: {COLORS["accent_lavender"]};
}}

QLabel#section_label {{
    color: {COLORS["text_secondary"]};
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.8px;
}}
"""


def get_maya_main_window():
    main_window_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


# ─── データ収集 ──────────────────────────────────────────────────

CONSTRAINT_TYPES = [
    "parentConstraint", "pointConstraint", "orientConstraint",
    "scaleConstraint", "aimConstraint", "geometryConstraint",
    "normalConstraint", "tangentConstraint", "poleVectorConstraint",
]


def get_constraints_in_hierarchy(root_node):
    """指定ノード以下の全コンストレインを収集する"""
    results = []
    if not root_node or not cmds.objExists(root_node):
        return results

    all_nodes = cmds.listRelatives(root_node, allDescendents=True, fullPath=True) or []
    all_nodes.append(root_node)

    for node in all_nodes:
        for ctype in CONSTRAINT_TYPES:
            constraints = cmds.listRelatives(node, type=ctype, fullPath=True) or []
            for con in constraints:
                info = get_constraint_info(con, ctype)
                if info:
                    results.append(info)

    return results


def extract_namespace(node_name):
    """ノード名（short or long）からネームスペースを返す。なければ空文字。"""
    if not node_name:
        return ""
    short = node_name.split("|")[-1]
    if ":" in short:
        return ":".join(short.split(":")[:-1])
    return ""


def get_constraint_info(con_node, ctype):
    """コンストレインノードから情報を抽出する"""
    try:
        short_name = con_node.split("|")[-1]

        # コンストレイン先（driven）= コンストレインの親ノード
        driven = cmds.listRelatives(con_node, parent=True, fullPath=True)
        driven = driven[0] if driven else ""

        # コンストレイン元（driver）= targetList attribute
        drivers = []
        target_list_attr = con_node + ".target"
        target_count = 0
        try:
            target_count = cmds.getAttr(target_list_attr, size=True)
        except Exception:
            pass

        weights = []
        for i in range(target_count):
            # ターゲットウェイト
            weight_attr = f"{con_node}.target[{i}].targetWeight"
            w = 1.0
            try:
                w = cmds.getAttr(weight_attr)
            except Exception:
                pass
            weights.append(w)

            # ターゲットノードを接続から逆引き
            # parentConstraint -> targetParentMatrix, pointConstraint -> targetTranslate etc.
            target_node = _find_driver_node(con_node, i, ctype)
            drivers.append(target_node)

        # ウェイトアトリビュート（外部から操作できるもの）
        weight_attrs = cmds.listAttr(con_node, userDefined=False, keyable=True) or []
        weight_attrs = [a for a in weight_attrs if "W" in a and not a.startswith("target")]

        ns_con    = extract_namespace(con_node)
        ns_driven = extract_namespace(driven)
        ns_driver = extract_namespace(drivers[0]) if drivers else ""

        return {
            "node":       con_node,
            "short_name": short_name,
            "type":       ctype,
            "driven":     driven,
            "drivers":    drivers,
            "weights":    weights,
            "weight_attrs": weight_attrs,
            # ネームスペース（3種）
            "ns_con":     ns_con,
            "ns_driven":  ns_driven,
            "ns_driver":  ns_driver,
            # 旧互換（NS フィルターコンボ用）
            "namespace":  ns_driven or ns_con,
        }
    except Exception as e:
        print(f"[ConstraintInspector] Error reading {con_node}: {e}")
        return None


def _find_driver_node(con_node, index, ctype):
    """コンストレインのindex番目のドライバーノードを接続から逆引き"""
    attr_map = {
        "parentConstraint":    f"{con_node}.target[{index}].targetParentMatrix",
        "pointConstraint":     f"{con_node}.target[{index}].targetTranslate",
        "orientConstraint":    f"{con_node}.target[{index}].targetRotate",
        "scaleConstraint":     f"{con_node}.target[{index}].targetScale",
        "aimConstraint":       f"{con_node}.target[{index}].targetTranslate",
        "poleVectorConstraint":f"{con_node}.target[{index}].targetTranslate",
        "geometryConstraint":  f"{con_node}.target[{index}].targetGeometry",
        "normalConstraint":    f"{con_node}.target[{index}].targetGeometry",
        "tangentConstraint":   f"{con_node}.target[{index}].targetGeometry",
    }
    src_attr = attr_map.get(ctype)
    if not src_attr:
        return ""
    connections = cmds.listConnections(src_attr, source=True, destination=False, plugs=False) or []
    if connections:
        return connections[0]
    return ""


# ─── UI ─────────────────────────────────────────────────────────

SHORT_TYPE_MAP = {
    "parentConstraint":    "Parent",
    "pointConstraint":     "Point",
    "orientConstraint":    "Orient",
    "scaleConstraint":     "Scale",
    "aimConstraint":       "Aim",
    "geometryConstraint":  "Geo",
    "normalConstraint":    "Normal",
    "tangentConstraint":   "Tangent",
    "poleVectorConstraint":"PoleVec",
}

class TypeBadge(QtWidgets.QLabel):
    def __init__(self, ctype, parent=None):
        super().__init__(parent)
        label = SHORT_TYPE_MAP.get(ctype, ctype)
        pair  = CONSTRAINT_TYPE_COLORS.get(ctype, ("#3A3A50", "#C0C0D8"))
        bg, fg = pair
        self.setText(label)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {fg}55;
                border-radius: 3px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self.setFixedHeight(18)


class ConstraintDetailPanel(QtWidgets.QWidget):
    """右パネル: 選択されたコンストレインの詳細と選択ボタン"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detail_panel")
        self.current_info = None
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # タイトル
        title = QtWidgets.QLabel("CONSTRAINT DETAIL")
        title.setObjectName("detail_title")
        layout.addWidget(title)

        # コンストレインノード名
        self.node_label = QtWidgets.QLabel("—")
        self.node_label.setObjectName("node_name_label")
        self.node_label.setWordWrap(True)
        layout.addWidget(self.node_label)

        # タイプバッジエリア
        self.type_badge_container = QtWidgets.QHBoxLayout()
        self.type_badge_container.setAlignment(Qt.AlignLeft)
        layout.addLayout(self.type_badge_container)

        layout.addWidget(self._hline())

        # ── ドリブン（コンストレイン先）──
        sec_driven = QtWidgets.QLabel("DRIVEN  ／  コンストレイン先")
        sec_driven.setObjectName("section_label")
        layout.addWidget(sec_driven)

        self.driven_label = QtWidgets.QLabel("—")
        self.driven_label.setObjectName("driven_label")
        self.driven_label.setWordWrap(True)
        layout.addWidget(self.driven_label)

        driven_btns = QtWidgets.QHBoxLayout()
        self.btn_select_driven = QtWidgets.QPushButton("選択")
        self.btn_select_driven.setObjectName("btn_driven")
        self.btn_select_driven.setToolTip("コンストレイン先ノードを Maya ビューポートで選択")
        self.btn_select_driven.clicked.connect(self._select_driven)
        self.btn_highlight_driven = QtWidgets.QPushButton("ハイライト")
        self.btn_highlight_driven.setObjectName("btn_driven")
        self.btn_highlight_driven.setToolTip("コンストレイン先ノードを追加選択")
        self.btn_highlight_driven.clicked.connect(lambda: self._select_driven(add=True))
        driven_btns.addWidget(self.btn_select_driven)
        driven_btns.addWidget(self.btn_highlight_driven)
        driven_btns.addStretch()
        layout.addLayout(driven_btns)

        layout.addWidget(self._hline())

        # ── ドライバー（コンストレイン元）──
        sec_driver = QtWidgets.QLabel("DRIVER  ／  コンストレイン元")
        sec_driver.setObjectName("section_label")
        layout.addWidget(sec_driver)

        self.drivers_container = QtWidgets.QVBoxLayout()
        self.drivers_container.setSpacing(4)
        layout.addLayout(self.drivers_container)

        layout.addWidget(self._hline())

        # ── コンストレインノード選択 ──
        self.btn_select_con = QtWidgets.QPushButton("コンストレインノードを選択")
        self.btn_select_con.setObjectName("btn_primary")
        self.btn_select_con.clicked.connect(self._select_constraint_node)
        layout.addWidget(self.btn_select_con)

        layout.addStretch()

    def _hline(self):
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet(f"color: {COLORS['border']};")
        return line

    def set_constraint(self, info):
        self.current_info = info

        # ノード名（短縮）
        self.node_label.setText(info["short_name"])

        # タイプバッジ
        while self.type_badge_container.count():
            item = self.type_badge_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        badge = TypeBadge(info["type"])
        self.type_badge_container.addWidget(badge)
        self.type_badge_container.addStretch()

        # Driven
        driven_short = info["driven"].split("|")[-1] if info["driven"] else "—"
        self.driven_label.setText(driven_short)

        # Drivers
        while self.drivers_container.count():
            item = self.drivers_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if info["drivers"]:
            for i, drv in enumerate(info["drivers"]):
                drv_short = drv.split("|")[-1] if drv else "(不明)"
                weight = info["weights"][i] if i < len(info["weights"]) else 1.0

                row = QtWidgets.QHBoxLayout()
                row.setSpacing(6)

                name_lbl = QtWidgets.QLabel(drv_short)
                name_lbl.setObjectName("driver_label")
                name_lbl.setToolTip(drv)
                row.addWidget(name_lbl, 1)

                w_lbl = QtWidgets.QLabel(f"W: {weight:.2f}")
                w_lbl.setObjectName("weight_label")
                row.addWidget(w_lbl)

                btn = QtWidgets.QPushButton("選択")
                btn.setObjectName("btn_driver")
                btn.setFixedWidth(48)
                btn.setFixedHeight(22)
                btn.clicked.connect(lambda checked=False, d=drv: self._select_node(d))
                row.addWidget(btn)

                container = QtWidgets.QWidget()
                container.setLayout(row)
                self.drivers_container.addWidget(container)
        else:
            no_lbl = QtWidgets.QLabel("ドライバーが見つかりません")
            no_lbl.setStyleSheet(f"color: {COLORS['text_dim']};")
            self.drivers_container.addWidget(no_lbl)

    def _select_node(self, node, add=False):
        if not node or not cmds.objExists(node):
            return
        if add:
            cmds.select(node, add=True)
        else:
            cmds.select(node, replace=True)

    def _select_driven(self, add=False):
        if self.current_info and self.current_info["driven"]:
            self._select_node(self.current_info["driven"], add=add)

    def _select_constraint_node(self):
        if self.current_info and self.current_info["node"]:
            self._select_node(self.current_info["node"])

    def clear(self):
        self.current_info = None
        self.node_label.setText("—")
        self.driven_label.setText("—")
        while self.type_badge_container.count():
            item = self.type_badge_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self.drivers_container.count():
            item = self.drivers_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class ConstraintInspectorUI(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Constraint Inspector  |  Maya 2024")
        self.setMinimumSize(1032, 560)
        self.resize(1200, 640)
        self.setStyleSheet(STYLESHEET)
        self._constraint_data = []
        self._build_ui()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── ヘッダー ──
        header = QtWidgets.QWidget()
        header.setObjectName("header_widget")
        header.setFixedHeight(56)
        h_layout = QtWidgets.QHBoxLayout(header)
        h_layout.setContentsMargins(16, 8, 16, 8)
        h_layout.setSpacing(10)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)
        title = QtWidgets.QLabel("Constraint Inspector")
        title.setObjectName("title_label")
        subtitle = QtWidgets.QLabel("コンストレイン一覧・選択支援ツール")
        subtitle.setObjectName("subtitle_label")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        h_layout.addLayout(title_col)
        h_layout.addStretch()

        # ルートノード入力
        root_lbl = QtWidgets.QLabel("Root:")
        root_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        self.root_input = QtWidgets.QLineEdit()
        self.root_input.setPlaceholderText("ルートノード名を入力 (空欄 = シーン全体)")
        self.root_input.setFixedWidth(230)
        self.root_input.returnPressed.connect(self._scan)

        btn_pick = QtWidgets.QPushButton("選択から取得")
        btn_pick.setToolTip("Maya で選択中のノードをルートとして設定")
        btn_pick.clicked.connect(self._pick_from_selection)

        btn_scan = QtWidgets.QPushButton("スキャン")
        btn_scan.setObjectName("btn_primary")
        btn_scan.setFixedWidth(72)
        btn_scan.clicked.connect(self._scan)

        h_layout.addWidget(root_lbl)
        h_layout.addWidget(self.root_input)
        h_layout.addWidget(btn_pick)
        h_layout.addWidget(btn_scan)
        main_layout.addWidget(header)

        # ── フィルターバー（2段） ──
        filter_bar = QtWidgets.QWidget()
        filter_bar.setStyleSheet(f"background: {COLORS['bg_mid']}; border-bottom: 1px solid {COLORS['border']};")
        f_outer = QtWidgets.QVBoxLayout(filter_bar)
        f_outer.setContentsMargins(12, 6, 12, 6)
        f_outer.setSpacing(4)

        def _lbl(text):
            lb = QtWidgets.QLabel(text)
            lb.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px; font-weight: bold;")
            return lb

        # 1段目: テキスト検索 + Type
        f_row1 = QtWidgets.QHBoxLayout()
        f_row1.setSpacing(8)

        search_icon = QtWidgets.QLabel("🔍")
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("ノード名で絞り込み…")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._apply_filter)

        self.type_filter = QtWidgets.QComboBox()
        self.type_filter.addItem("すべて")
        for ct in CONSTRAINT_TYPES:
            self.type_filter.addItem(ct.replace("Constraint", ""))
        self.type_filter.setMinimumWidth(110)
        self.type_filter.currentIndexChanged.connect(self._apply_filter)

        self.count_label = QtWidgets.QLabel("0 件")
        self.count_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")

        f_row1.addWidget(search_icon)
        f_row1.addWidget(self.search_input)
        f_row1.addWidget(_lbl("TYPE:"))
        f_row1.addWidget(self.type_filter)
        f_row1.addStretch()
        f_row1.addWidget(self.count_label)

        # 2段目: NS 3本コンボ
        f_row2 = QtWidgets.QHBoxLayout()
        f_row2.setSpacing(8)

        def _ns_combo():
            cb = QtWidgets.QComboBox()
            cb.addItem("すべて")
            cb.setMinimumWidth(130)
            cb.currentIndexChanged.connect(self._apply_filter)
            return cb

        self.ns_con_filter    = _ns_combo()
        self.ns_driven_filter = _ns_combo()
        self.ns_driver_filter = _ns_combo()

        f_row2.addWidget(_lbl("CON NS:"))
        f_row2.addWidget(self.ns_con_filter)
        f_row2.addSpacing(8)
        f_row2.addWidget(_lbl("DRIVEN NS:"))
        f_row2.addWidget(self.ns_driven_filter)
        f_row2.addSpacing(8)
        f_row2.addWidget(_lbl("DRIVER NS:"))
        f_row2.addWidget(self.ns_driver_filter)
        f_row2.addStretch()

        f_outer.addLayout(f_row1)
        f_outer.addLayout(f_row2)
        main_layout.addWidget(filter_bar)

        # ── メインコンテンツ（スプリッター）──
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # テーブル
        # 列構成: CON_NS | TYPE | CON名 | DRIVEN_NS | DRIVEN | DRIVER_NS | DRIVER | 重み
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "CON NS", "TYPE", "コンストレイン名",
            "DRIVEN NS", "DRIVEN（先）",
            "DRIVER NS", "DRIVER（元）", "重み",
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.setSortingEnabled(True)
        self.table.setColumnWidth(0, 100)   # CON NS
        self.table.setColumnWidth(1, 80)    # TYPE
        self.table.setColumnWidth(2, 190)   # CON名
        self.table.setColumnWidth(3, 100)   # DRIVEN NS
        self.table.setColumnWidth(4, 150)   # DRIVEN
        self.table.setColumnWidth(5, 100)   # DRIVER NS
        self.table.setColumnWidth(6, 150)   # DRIVER
        self.table.setColumnWidth(7, 60)    # 重み
        self.table.setShowGrid(True)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(self._on_double_click)
        splitter.addWidget(self.table)

        # 詳細パネル
        self.detail_panel = ConstraintDetailPanel()
        self.detail_panel.setMinimumWidth(260)
        self.detail_panel.setMaximumWidth(340)
        splitter.addWidget(self.detail_panel)
        splitter.setSizes([680, 300])

        main_layout.addWidget(splitter, 1)

        # ステータスバー
        self.statusBar().showMessage("ルートノードを指定してスキャンしてください。")

    # ── イベント ────────────────────────────────────────────

    def _pick_from_selection(self):
        sel = cmds.ls(selection=True, long=True)
        if sel:
            self.root_input.setText(sel[0].split("|")[-1])
        else:
            self.statusBar().showMessage("ノードが選択されていません。")

    def _scan(self):
        root = self.root_input.text().strip()

        # ルートが空の場合はシーン全体
        if not root:
            data = []
            for ctype in CONSTRAINT_TYPES:
                nodes = cmds.ls(type=ctype, long=True) or []
                for n in nodes:
                    info = get_constraint_info(n, ctype)
                    if info:
                        data.append(info)
            self._constraint_data = data
        else:
            if not cmds.objExists(root):
                self.statusBar().showMessage(f"ノードが見つかりません: {root}")
                return
            self._constraint_data = get_constraints_in_hierarchy(root)

        self._refresh_ns_combo()
        self._apply_filter()
        self.statusBar().showMessage(f"スキャン完了  —  {len(self._constraint_data)} 件のコンストレインを検出")

    def _refresh_ns_combo(self):
        """スキャン後にネームスペースコンボを再構築する（3本独立）"""
        def _rebuild(combo, key):
            prev = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("すべて")
            ns_set = sorted(set(info[key] for info in self._constraint_data))
            for ns in ns_set:
                combo.addItem(ns if ns else "（なし）")
            idx = combo.findText(prev)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        _rebuild(self.ns_con_filter,    "ns_con")
        _rebuild(self.ns_driven_filter, "ns_driven")
        _rebuild(self.ns_driver_filter, "ns_driver")

    def _apply_filter(self):
        keyword = self.search_input.text().strip().lower()
        type_filter_str = self.type_filter.currentText()
        if type_filter_str == "すべて":
            type_filter_str = ""

        def ns_match(combo, info_key, info):
            sel = combo.currentText()
            if sel == "すべて":
                return True
            val = info[info_key]
            if sel == "（なし）":
                return val == ""
            return val == sel

        filtered = []
        for info in self._constraint_data:
            if type_filter_str and type_filter_str.lower() not in info["type"].lower():
                continue
            if not ns_match(self.ns_con_filter,    "ns_con",    info):
                continue
            if not ns_match(self.ns_driven_filter, "ns_driven", info):
                continue
            if not ns_match(self.ns_driver_filter, "ns_driver", info):
                continue
            search_target = " ".join([
                info["short_name"].lower(),
                info["driven"].lower(),
                " ".join([d.lower() for d in info["drivers"]]),
            ])
            if keyword and keyword not in search_target:
                continue
            filtered.append(info)

        self._populate_table(filtered)
        self.count_label.setText(f"{len(filtered)} 件")

    def _populate_table(self, data):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(data))

        dim = COLORS["text_dim"]
        lav = COLORS["accent_lavender"]

        for row, info in enumerate(data):
            self.table.setRowHeight(row, 28)

            def ns_item(ns, col):
                txt = ns if ns else "—"
                clr = lav if ns else dim
                it = self._item(txt, color=clr)
                if col == 0:
                    it.setData(Qt.UserRole, info)  # UserRole は col0 に集約
                return it

            # col 0: CON NS
            self.table.setItem(row, 0, ns_item(info["ns_con"], 0))

            # col 1: TYPE バッジ（CellWidget） + 隠しソートキー Item
            badge_widget = QtWidgets.QWidget()
            b_layout = QtWidgets.QHBoxLayout(badge_widget)
            b_layout.setContentsMargins(4, 2, 4, 2)
            b_layout.addWidget(TypeBadge(info["type"]))
            b_layout.addStretch()
            self.table.setCellWidget(row, 1, badge_widget)
            type_sort_item = QtWidgets.QTableWidgetItem(info["type"])
            type_sort_item.setForeground(QtGui.QColor(0, 0, 0, 0))
            self.table.setItem(row, 1, type_sort_item)

            # col 2: コンストレイン名（NS 除いた短縮名）
            short_no_ns = info["short_name"].split(":")[-1]
            self.table.setItem(row, 2, self._item(short_no_ns))

            # col 3: DRIVEN NS
            self.table.setItem(row, 3, ns_item(info["ns_driven"], 3))

            # col 4: DRIVEN（NS 除いた短縮名）
            driven_short = info["driven"].split("|")[-1].split(":")[-1] if info["driven"] else "—"
            driven_item = self._item(driven_short, color=COLORS["accent_gold"])
            driven_item.setToolTip(info["driven"])
            self.table.setItem(row, 4, driven_item)

            # col 5: DRIVER NS（先頭ドライバーのみ表示）
            self.table.setItem(row, 5, ns_item(info["ns_driver"], 5))

            # col 6: DRIVER（NS 除いた短縮名、複数対応）
            if info["drivers"]:
                drivers_short = ", ".join([
                    d.split("|")[-1].split(":")[-1] if d else "?" for d in info["drivers"]
                ])
            else:
                drivers_short = "—"
            driver_item = self._item(drivers_short, color=COLORS["accent_teal"])
            self.table.setItem(row, 6, driver_item)

            # col 7: 重み
            w_str = ", ".join([f"{w:.2f}" for w in info["weights"]]) if info["weights"] else "—"
            self.table.setItem(row, 7, self._item(w_str, color=COLORS["text_secondary"]))

        self.table.setSortingEnabled(True)

    def _item(self, text, color=None):
        item = QtWidgets.QTableWidgetItem(text)
        if color:
            item.setForeground(QtGui.QColor(color))
        return item

    def _get_info_from_row(self, row):
        """行番号から info dict を取得（UserRole は col 0 の NS item に格納）"""
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_row_selected(self):
        items = self.table.selectedItems()
        if not items:
            self.detail_panel.clear()
            return
        info = self._get_info_from_row(items[0].row())
        if info:
            self.detail_panel.set_constraint(info)

    def _on_double_click(self, index):
        """列に応じて選択対象を切り替え
        col 4 (DRIVEN)  -> コンストレイン先ノード
        col 6 (DRIVER)  -> コンストレイン元ノード（複数時は全選択）
        それ以外         -> コンストレインノード自身
        """
        info = self._get_info_from_row(index.row())
        if not info:
            return

        col = index.column()

        if col == 4:
            node = info["driven"]
            if node and cmds.objExists(node):
                cmds.select(node, replace=True)
                self.statusBar().showMessage(f"DRIVEN 選択: {node.split(chr(124))[-1]}")

        elif col == 6:
            valid = [d for d in info["drivers"] if d and cmds.objExists(d)]
            if valid:
                cmds.select(valid, replace=True)
                names = ", ".join(d.split(chr(124))[-1] for d in valid)
                self.statusBar().showMessage(f"DRIVER 選択: {names}")

        else:
            if cmds.objExists(info["node"]):
                cmds.select(info["node"], replace=True)
                self.statusBar().showMessage(f"選択: {info['short_name']}")


# ─── 起動 ────────────────────────────────────────────────────────

_window_instance = None


def show():
    global _window_instance
    try:
        _window_instance.close()
        _window_instance.deleteLater()
    except Exception:
        pass

    parent = get_maya_main_window()
    _window_instance = ConstraintInspectorUI(parent=parent)
    _window_instance.show()
    _window_instance.raise_()
    return _window_instance


if __name__ == "__main__":
    show()

# import / importlib.reload どちらでも即起動
show()
