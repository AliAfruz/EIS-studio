from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import numpy as np

from PySide6.QtCore import (
    Qt, QEasingCurve, QMimeData, QPropertyAnimation, QRectF, QSize, Signal
)
from PySide6.QtGui import (
    QColor, QDoubleValidator, QDrag, QFont, QKeySequence, QPainter, QPen,
    QPixmap, QShortcut
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout,
    QFrame, QGraphicsOpacityEffect, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QInputDialog, QListView, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSlider, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget
)

from .models import (
    CIRCUITS, CircuitSpec, custom_element_param_names, custom_param_def,
    custom_tree_params, default_custom_values, evaluate_custom_tree,
    make_custom_circuit,
)
from .theme import get_palette
from .cinematic import apply_glass_shadow
from .schematic_canvas import (
    ELEMENT_MIME, NODE_MIME, SchematicCanvas, schematic_symbol_icon,
    schematic_symbol_pixmap,
)
from .circuit_lab import (
    FloatingEISMonitor, identifiability_map, local_element_sensitivity,
    topology_hypotheses,
)
from .dc_series_lab import DCSeriesGlobalDialog
from .fitting import FitSettings, fit_model


ROLE_UID = Qt.UserRole
ROLE_TYPE = Qt.UserRole + 1


ELEMENT_LIBRARY = (
    ("R", "RESISTOR", "R", "Ohmic or charge-transfer resistance"),
    ("C", "CAPACITOR", "C", "Ideal capacitance"),
    ("CPE", "CONSTANT PHASE", "CPE", "Distributed/non-ideal capacitance"),
    ("L", "INDUCTOR", "L", "Lead or adsorption inductance"),
    ("W", "WARBURG", "W", "Semi-infinite diffusion"),
    ("Wβ", "FRACTIONAL W", "Wβ", "Anomalous diffusion exponent"),
    ("Wo", "FINITE OPEN", "Wₒ", "Blocking finite diffusion"),
    ("Ws", "FINITE SHORT", "Wₛ", "Transmissive finite diffusion"),
    ("G", "GERISCHER", "G", "Coupled reaction-diffusion"),
    ("TLMo", "TLM OPEN", "TLMₒ", "Porous line, blocking end"),
    ("TLMs", "TLM SHORT", "TLMₛ", "Porous line, transmissive end"),
    ("PARALLEL", "PARALLEL BLOCK", "∥", "Create two wired branches"),
)


class ElementPalette(QListWidget):
    """Glass tile palette that exports element kinds through Qt drag/drop."""

    elementActivated = Signal(str)

    def __init__(self, theme_name: str, parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.setObjectName("elementPalette")
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setGridSize(QSize(146, 78))
        self.setIconSize(QSize(108, 34))
        self.setSpacing(4)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumWidth(306)
        self.itemDoubleClicked.connect(
            lambda item: self.elementActivated.emit(str(item.data(ROLE_TYPE)))
        )
        for kind, title, symbol, description in ELEMENT_LIBRARY:
            item = QListWidgetItem(
                schematic_symbol_icon(kind, self.theme_name), f"{symbol}  {title}"
            )
            item.setData(ROLE_TYPE, kind)
            item.setTextAlignment(Qt.AlignCenter)
            item.setToolTip(
                f"{description}\nDrag to a path or double-click to add after selection."
            )
            item.setSizeHint(QSize(138, 70))
            self.addItem(item)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return
        kind = str(item.data(ROLE_TYPE) or "")
        if not kind:
            return
        mime = QMimeData()
        mime.setData(ELEMENT_MIME, kind.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap(kind, item.text()))
        drag.setHotSpot(drag.pixmap().rect().center())
        drag.exec(Qt.CopyAction)

    def _drag_pixmap(self, kind: str, text: str) -> QPixmap:
        pixmap = QPixmap(196, 72)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = get_palette(self.theme_name)
        painter.setPen(QPen(QColor(palette.accent), 1.4))
        fill = QColor(palette.panel_alt)
        fill.setAlpha(238)
        painter.setBrush(fill)
        painter.drawRoundedRect(2, 2, 192, 66, 15, 15)
        symbol = schematic_symbol_pixmap(kind, self.theme_name, QSize(104, 38))
        painter.drawPixmap(9, 15, symbol)
        font = QFont("Segoe UI", 7.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(palette.text))
        painter.drawText(QRectF(112, 7, 76, 56), Qt.AlignCenter | Qt.TextWordWrap, text)
        painter.end()
        return pixmap


class TopologyDropTree(QTreeWidget):
    """Topology outline that translates visual drops into model operations."""

    dropRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topologyDropTree")
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None or str(item.data(0, ROLE_TYPE)) not in {"element", "parallel"}:
            return
        uid = str(item.data(0, ROLE_UID) or "")
        if not uid:
            return
        mime = QMimeData()
        mime.setData(NODE_MIME, uid.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self.viewport().grab(self.visualItemRect(item))
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.MoveAction)

    @staticmethod
    def _accepted(mime) -> bool:
        return mime.hasFormat(ELEMENT_MIME) or mime.hasFormat(NODE_MIME)

    def dragEnterEvent(self, event):
        if self._accepted(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self._accepted(event.mimeData()):
            event.ignore()
            return
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            self.setCurrentItem(item)
        event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if not self._accepted(mime):
            event.ignore()
            return
        position = event.position().toPoint()
        item = self.itemAt(position)
        target_uid = str(item.data(0, ROLE_UID)) if item is not None else ""
        zone = "on"
        if item is not None:
            rect = self.visualItemRect(item)
            relative = (
                (position.y() - rect.top()) / max(rect.height(), 1)
            )
            zone = "above" if relative < 0.28 else "below" if relative > 0.72 else "on"
        if mime.hasFormat(ELEMENT_MIME):
            payload = {
                "action": "add",
                "kind": bytes(mime.data(ELEMENT_MIME)).decode("utf-8"),
                "target_uid": target_uid,
                "zone": zone,
            }
        else:
            payload = {
                "action": "move",
                "source_uid": bytes(mime.data(NODE_MIME)).decode("utf-8"),
                "target_uid": target_uid,
                "zone": zone,
            }
        self.dropRequested.emit(payload)
        event.acceptProposedAction()


def _uid() -> str:
    return uuid4().hex


def _series(children=None, *, label: str = "Series circuit") -> dict:
    return {"type": "series", "uid": _uid(), "label": label, "children": list(children or [])}


def _element(kind: str, element_id: str, params: list[str] | None = None) -> dict:
    return {
        "type": "element", "uid": _uid(), "kind": kind, "id": element_id,
        "params": list(params or custom_element_param_names(kind, element_id)),
    }


def _parallel(branches=None) -> dict:
    return {
        "type": "parallel", "uid": _uid(),
        "branches": list(branches or [_series(label="Branch 1"), _series(label="Branch 2")]),
    }


def _ensure_uids(node: dict):
    node.setdefault("uid", _uid())
    if node.get("type") == "series":
        node.setdefault("children", [])
        for child in node["children"]:
            _ensure_uids(child)
    elif node.get("type") == "parallel":
        node.setdefault("branches", [])
        for i, branch in enumerate(node["branches"], 1):
            branch.setdefault("label", f"Branch {i}")
            _ensure_uids(branch)


def diagram_to_custom_tree(diagram: tuple) -> dict:
    """Convert the annotated renderer diagram into the builder tree format."""
    def parse_series(items, label="Series circuit"):
        container = _series(label=label)
        for item in items:
            if isinstance(item, tuple) and item and item[0] == "element":
                _, kind, element_id, params = item
                container["children"].append(_element(str(kind), str(element_id), list(params)))
            elif isinstance(item, tuple) and item and item[0] == "parallel":
                branches = []
                for i, branch_item in enumerate(item[1:], 1):
                    if isinstance(branch_item, tuple) and branch_item and branch_item[0] == "series":
                        branch = parse_series(branch_item[1:], label=f"Branch {i}")
                    else:
                        branch = parse_series((branch_item,), label=f"Branch {i}")
                    branches.append(branch)
                container["children"].append(_parallel(branches))
        return container

    return parse_series(diagram)


def tree_for_spec(spec: CircuitSpec) -> dict:
    if spec.metadata and spec.metadata.get("tree"):
        tree = deepcopy(spec.metadata["tree"])
        _ensure_uids(tree)
        return tree
    return diagram_to_custom_tree(spec.diagram)


class CircuitBuilderDialog(QDialog):
    """Visual series/parallel circuit builder with per-element values and locks."""

    def __init__(
        self,
        spec: CircuitSpec,
        values: dict[str, float] | None = None,
        locks: set[str] | None = None,
        theme_name: str = "light",
        parent=None,
        *,
        frequencies=None,
        measured_impedance=None,
        fit_diagnostics=None,
        dc_series=None,
        drt_data=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Cinematic equivalent-circuit laboratory")
        self.resize(1380, 840)
        self.setMinimumSize(1120, 700)
        self.theme_name = theme_name
        self.original_tree = tree_for_spec(spec)
        self.tree = deepcopy(self.original_tree)
        self.values = default_custom_values(self.tree)
        self.values.update({k: float(v) for k, v in (values or {}).items()})
        self.locks = set(locks or ())
        self.measured_frequency = np.asarray(
            frequencies if frequencies is not None else [], dtype=float
        )
        self.measured_impedance = np.asarray(
            measured_impedance if measured_impedance is not None else [], dtype=complex
        )
        if len(self.measured_frequency) != len(self.measured_impedance):
            self.measured_frequency = np.array([], dtype=float)
            self.measured_impedance = np.array([], dtype=complex)
        valid_f = self.measured_frequency[
            np.isfinite(self.measured_frequency) & (self.measured_frequency > 0)
        ]
        if len(valid_f):
            self.simulation_frequency = np.logspace(
                np.log10(float(np.max(valid_f))), np.log10(float(np.min(valid_f))), 280
            )
        else:
            self.simulation_frequency = np.logspace(6, -2, 280)
        self.fit_diagnostics = fit_diagnostics
        self.dc_series = list(dc_series or [])
        self.drt_data = drt_data
        self._identifiability: dict[str, str] = {}
        self._identifiability_details: dict[str, str] = {}
        self._selection_from_canvas = False
        self._copied_element: dict | None = None
        self._property_widgets: dict[str, tuple[QLineEdit, QCheckBox, QSlider]] = {}
        self._history: list[dict[str, object]] = []
        self._history_index = -1
        self._preview_animation = None
        self._build_ui(spec.name)
        self._rebuild_tree()
        self._update_preview()
        self._record_history()

    def _build_ui(self, default_name: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.builder_hero = QFrame()
        self.builder_hero.setObjectName("builderHero")
        hero_layout = QHBoxLayout(self.builder_hero)
        hero_layout.setContentsMargins(18, 11, 18, 11)
        hero_copy = QVBoxLayout()
        hero_title = QLabel("LIVE CIRCUIT LABORATORY")
        hero_title.setObjectName("builderTitle")
        hero_subtitle = QLabel(
            "Build a real schematic: place symbols, move them freely, and wire by magnetic drop."
        )
        hero_subtitle.setObjectName("builderSubtitle")
        hero_copy.addWidget(hero_title)
        hero_copy.addWidget(hero_subtitle)
        hero_layout.addLayout(hero_copy)
        hero_layout.addStretch(1)
        self.builder_status = QLabel("READY")
        self.builder_status.setObjectName("builderStatus")
        hero_layout.addWidget(self.builder_status)
        root.addWidget(self.builder_hero)

        header = QHBoxLayout()
        name_label = QLabel("Circuit name")
        name_label.setObjectName("builderFieldLabel")
        header.addWidget(name_label)
        self.name_edit = QLineEdit(default_name if default_name else "Manual visual circuit")
        self.name_edit.setPlaceholderText("Example: Cholesterol sensor Randles model")
        header.addWidget(self.name_edit, 1)
        root.addLayout(header)

        info = QLabel(
            "Drag a symbol to a + portal. Move it freely or wire terminal-to-terminal. "
            "Wheel zooms • middle-drag pans • double-click quick-adds."
        )
        info.setObjectName("builderHelp")
        info.setWordWrap(True)
        root.addWidget(info)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("builderSplitter")
        root.addWidget(splitter, 1)

        palette_box = QGroupBox("Element deck")
        palette_box.setMaximumWidth(336)
        palette_layout = QVBoxLayout(palette_box)
        palette_hint = QLabel("DRAG A TILE  •  DOUBLE-CLICK TO QUICK ADD")
        palette_hint.setObjectName("builderMicrocopy")
        palette_hint.setWordWrap(True)
        self.element_palette = ElementPalette(self.theme_name)
        self.element_palette.setCurrentRow(-1)
        self.element_palette.scrollToTop()
        self.element_palette.elementActivated.connect(self._add_palette_kind)
        palette_layout.addWidget(palette_hint)
        palette_layout.addWidget(self.element_palette, 1)
        splitter.addWidget(palette_box)

        canvas_box = QGroupBox("Live schematic workspace")
        canvas_layout = QVBoxLayout(canvas_box)
        canvas_hint = QLabel(
            "SYMBOLS + LIVE WIRES  •  DROP ON A PULSING PORTAL TO CONNECT  •  FREE MOVE ANYWHERE"
        )
        canvas_hint.setObjectName("builderMicrocopy")
        canvas_hint.setWordWrap(True)
        self.canvas = SchematicCanvas(self.theme_name)
        self.canvas.dropRequested.connect(self._handle_topology_drop)
        self.canvas.portConnectionRequested.connect(self._handle_port_connection)
        self.canvas.selectionRequested.connect(self._select_uid_from_canvas)
        self.canvas.nodePositionRequested.connect(self._canvas_node_position_changed)
        self.preview = self.canvas
        # Keep overlay widgets (monitor/minimap) as native viewport children.
        # A graphics effect on the viewport offsets and clips them on Windows.
        self.preview_effect = QGraphicsOpacityEffect(self)
        self.preview_effect.setOpacity(1.0)
        canvas_layout.addWidget(canvas_hint)
        canvas_layout.addWidget(self.canvas, 1)
        canvas_tools = QHBoxLayout()
        canvas_lab_tools = QHBoxLayout()
        zoom_out_button = QPushButton("−")
        zoom_in_button = QPushButton("+")
        fit_canvas_button = QPushButton("Fit view")
        self.auto_layout_button = QPushButton("Layout")
        self.monitor_button = QPushButton("Monitor")
        self.snap_button = QPushButton("Snap")
        self.snap_button.setCheckable(True)
        self.snap_button.setChecked(True)
        note_button = QPushButton("Note")
        align_h_button = QPushButton("Align ↔")
        align_v_button = QPushButton("Align ↕")
        self.template_combo = QComboBox()
        self.template_combo.addItem("Circuit templates…", "")
        for template_key in (
            "R", "R-C", "R-(R||C)", "R-(R||CPE)",
            "R-(R||CPE)-W", "R-(R||CPE)-Wo", "R-(R||CPE)-(R||CPE)",
        ):
            if template_key in CIRCUITS:
                self.template_combo.addItem(CIRCUITS[template_key].name, template_key)
        dc_global_button = QPushButton("DC series")
        for button in (
            zoom_out_button, zoom_in_button, fit_canvas_button,
            self.auto_layout_button, self.monitor_button, self.snap_button,
            note_button, align_h_button, align_v_button,
            dc_global_button,
        ):
            button.setObjectName("quietButton")
            button.setProperty("compact", True)
        zoom_out_button.setToolTip("Zoom out")
        zoom_in_button.setToolTip("Zoom in")
        fit_canvas_button.setToolTip("Fit the complete schematic in view")
        self.auto_layout_button.setToolTip("Clear free positions and restore the topology layout")
        self.monitor_button.setToolTip("Open the live Nyquist/Bode plot in the right panel")
        self.snap_button.setToolTip("Snap freely moved symbols to the cinematic grid")
        note_button.setToolTip("Add a scientific annotation to the schematic")
        align_h_button.setToolTip("Align selected symbols to one horizontal row")
        align_v_button.setToolTip("Align selected symbols to one vertical column")
        dc_global_button.setToolTip(
            "Jointly fit multiple DC-bias spectra with shared, independent, or smooth parameters"
        )
        zoom_out_button.clicked.connect(self.canvas.zoom_out)
        zoom_in_button.clicked.connect(self.canvas.zoom_in)
        fit_canvas_button.clicked.connect(self.canvas.fit_circuit)
        self.auto_layout_button.clicked.connect(self._auto_layout_canvas)
        self.monitor_button.clicked.connect(self._show_live_monitor)
        self.snap_button.toggled.connect(self._toggle_snap_grid)
        note_button.clicked.connect(self._add_canvas_note)
        align_h_button.clicked.connect(lambda: self._align_canvas_selection("row"))
        align_v_button.clicked.connect(lambda: self._align_canvas_selection("column"))
        self.template_combo.currentIndexChanged.connect(self._apply_circuit_template)
        dc_global_button.clicked.connect(self._open_dc_series_lab)
        canvas_tools.addWidget(zoom_out_button)
        canvas_tools.addWidget(zoom_in_button)
        canvas_tools.addWidget(fit_canvas_button)
        canvas_tools.addWidget(self.auto_layout_button)
        canvas_tools.addWidget(self.monitor_button)
        canvas_tools.addWidget(self.snap_button)
        canvas_tools.addStretch(1)
        lab_label = QLabel("LAB TOOLS")
        lab_label.setObjectName("builderMicrocopy")
        canvas_lab_tools.addWidget(lab_label)
        canvas_lab_tools.addWidget(note_button)
        canvas_lab_tools.addWidget(align_h_button)
        canvas_lab_tools.addWidget(align_v_button)
        canvas_lab_tools.addWidget(self.template_combo, 1)
        canvas_lab_tools.addWidget(dc_global_button)
        canvas_layout.addLayout(canvas_tools)
        canvas_layout.addLayout(canvas_lab_tools)
        splitter.addWidget(canvas_box)

        right = QWidget()
        right.setObjectName("builderRight")
        right.setMinimumWidth(320)
        right.setMaximumWidth(410)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_tabs = QTabWidget()
        right_tabs.setObjectName("builderRightTabs")
        right_tabs.setDocumentMode(True)
        right_tabs.tabBar().setUsesScrollButtons(False)
        right_tabs.tabBar().setExpanding(True)
        right_tabs.tabBar().setElideMode(Qt.ElideRight)
        self.right_tabs = right_tabs
        self.live_monitor = FloatingEISMonitor(self.theme_name)
        self.live_monitor.set_embedded(True)
        self.live_monitor.frequencyChanged.connect(self._frequency_cursor_changed)
        self.live_monitor.fitRequested.connect(self._fit_to_measured)
        right_tabs.addTab(self.live_monitor, "PLOT")

        properties_box = QGroupBox()
        properties_layout = QVBoxLayout(properties_box)
        self.selected_label = QLabel("Select an electrical symbol on the canvas.")
        self.selected_label.setObjectName("builderSelectedLabel")
        self.selected_label.setWordWrap(True)
        properties_layout.addWidget(self.selected_label)
        self.property_table = QTableWidget(0, 5)
        self.property_table.setObjectName("builderPropertyTable")
        self.property_table.setHorizontalHeaderLabels(
            ["Param", "Value", "Tune", "Unit", "●"]
        )
        self.property_table.horizontalHeader().setStretchLastSection(False)
        property_header = self.property_table.horizontalHeader()
        property_header.setSectionResizeMode(0, QHeaderView.Fixed)
        property_header.setSectionResizeMode(1, QHeaderView.Fixed)
        property_header.setSectionResizeMode(2, QHeaderView.Stretch)
        property_header.setSectionResizeMode(3, QHeaderView.Fixed)
        property_header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.property_table.setColumnWidth(0, 62)
        self.property_table.setColumnWidth(1, 72)
        self.property_table.setColumnWidth(3, 45)
        self.property_table.setColumnWidth(4, 30)
        self.property_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.property_table.verticalHeader().setVisible(False)
        self.property_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.property_table.setMinimumHeight(150)
        properties_layout.addWidget(self.property_table)
        right_tabs.addTab(properties_box, "EDIT")

        hypotheses_box = QGroupBox()
        hypotheses_layout = QVBoxLayout(hypotheses_box)
        hypotheses_note = QLabel(
            "SCREENING HINTS ONLY — VERIFY WITH RESIDUALS, UNCERTAINTY, AND PHYSICS"
        )
        hypotheses_note.setObjectName("builderMicrocopy")
        hypotheses_note.setWordWrap(True)
        self.hypothesis_list = QListWidget()
        self.hypothesis_list.setObjectName("hypothesisList")
        self.hypothesis_list.setWordWrap(True)
        self.hypothesis_list.setTextElideMode(Qt.ElideNone)
        self.hypothesis_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hypothesis_list.setSelectionMode(QAbstractItemView.NoSelection)
        hypotheses_layout.addWidget(hypotheses_note)
        hypotheses_layout.addWidget(self.hypothesis_list)
        right_tabs.addTab(hypotheses_box, "SCIENCE")

        topology_box = QGroupBox()
        topology_layout = QVBoxLayout(topology_box)
        topology_hint = QLabel(
            "Scientific outline synchronized with the schematic canvas."
        )
        topology_hint.setObjectName("builderMicrocopy")
        topology_hint.setWordWrap(True)
        self.tree_widget = TopologyDropTree()
        self.tree_widget.setHeaderLabels(["Validated series / parallel topology"])
        self.tree_widget.setMinimumHeight(180)
        self.tree_widget.itemSelectionChanged.connect(self._selection_changed)
        self.tree_widget.dropRequested.connect(self._handle_topology_drop)
        topology_layout.addWidget(topology_hint)
        topology_layout.addWidget(self.tree_widget, 1)
        tools = QGridLayout()
        self.up_button = QPushButton("Move up")
        self.down_button = QPushButton("Move down")
        self.duplicate_button = QPushButton("Duplicate")
        self.remove_button = QPushButton("Remove")
        self.branch_button = QPushButton("Add branch")
        self.reset_button = QPushButton("Reset")
        self.empty_button = QPushButton("Start empty")
        self.up_button.clicked.connect(lambda: self._move_selected(-1))
        self.down_button.clicked.connect(lambda: self._move_selected(1))
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        self.branch_button.clicked.connect(self._add_branch)
        self.reset_button.clicked.connect(self._reset_template)
        self.empty_button.clicked.connect(self._start_empty)
        tools.addWidget(self.up_button, 0, 0); tools.addWidget(self.down_button, 0, 1)
        tools.addWidget(self.duplicate_button, 1, 0); tools.addWidget(self.remove_button, 1, 1)
        tools.addWidget(self.branch_button, 2, 0, 1, 2)
        tools.addWidget(self.reset_button, 3, 0); tools.addWidget(self.empty_button, 3, 1)
        topology_layout.addLayout(tools)

        history_row = QHBoxLayout()
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.undo_button.setObjectName("quietButton")
        self.redo_button.setObjectName("quietButton")
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        history_row.addWidget(self.undo_button)
        history_row.addWidget(self.redo_button)
        topology_layout.addLayout(history_row)
        right_tabs.addTab(topology_box, "TOPOLOGY")
        right_tabs.setCurrentWidget(properties_box)
        right_layout.addWidget(right_tabs, 1)

        file_row = QHBoxLayout()
        save_button = QPushButton("Save JSON")
        load_button = QPushButton("Load JSON")
        export_button = QPushButton("Export")
        save_button.setObjectName("quietButton")
        load_button.setObjectName("quietButton")
        export_button.setObjectName("quietButton")
        save_button.clicked.connect(self._save_json)
        load_button.clicked.connect(self._load_json)
        export_button.clicked.connect(self._export_schematic)
        file_row.addWidget(save_button); file_row.addWidget(load_button)
        file_row.addWidget(export_button)
        right_layout.addLayout(file_row)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([305, 760, 350])

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("quietButton")
        apply_button = QPushButton("Apply circuit")
        apply_button.setObjectName("primaryButton")
        apply_button.setDefault(True)
        cancel.clicked.connect(self.reject)
        apply_button.clicked.connect(self._validate_and_accept)
        buttons.addWidget(cancel); buttons.addWidget(apply_button)
        root.addLayout(buttons)

        self.undo_shortcut = QShortcut(QKeySequence.Undo, self)
        self.redo_shortcut = QShortcut(QKeySequence.Redo, self)
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self)
        self.copy_shortcut = QShortcut(QKeySequence.Copy, self)
        self.paste_shortcut = QShortcut(QKeySequence.Paste, self)
        self.undo_shortcut.activated.connect(self._undo)
        self.redo_shortcut.activated.connect(self._redo)
        self.delete_shortcut.activated.connect(self._remove_selected)
        self.copy_shortcut.activated.connect(self._copy_selected_element)
        self.paste_shortcut.activated.connect(self._paste_copied_element)

        for card in (
            self.builder_hero, palette_box, canvas_box, topology_box,
            properties_box, hypotheses_box,
        ):
            apply_glass_shadow(card, self.theme_name == "dark")

    def _all_elements(self):
        def walk(container):
            for child in container.get("children", []):
                if child.get("type") == "element":
                    yield child
                elif child.get("type") == "parallel":
                    for branch in child.get("branches", []):
                        yield from walk(branch)
        yield from walk(self.tree)

    def _next_id(self, kind: str) -> str:
        prefix = kind.replace("β", "f")
        elements = list(self._all_elements())
        used_ids = {element["id"] for element in elements}
        used_params = {name for element in elements for name in element.get("params", [])}
        i = 1
        while True:
            candidate = f"{prefix}{i}"
            candidate_params = set(custom_element_param_names(kind, candidate))
            if candidate not in used_ids and not (candidate_params & used_params):
                return candidate
            i += 1

    def _find(self, uid: str):
        if self.tree.get("uid") == uid:
            return self.tree, None, None

        def walk_series(container):
            for index, child in enumerate(container.get("children", [])):
                if child.get("uid") == uid:
                    return child, container, ("children", index)
                if child.get("type") == "parallel":
                    for branch_index, branch in enumerate(child.get("branches", [])):
                        if branch.get("uid") == uid:
                            return branch, child, ("branches", branch_index)
                        found = walk_series(branch)
                        if found:
                            return found
            return None

        return walk_series(self.tree)

    def _selected_uid(self) -> str | None:
        items = self.tree_widget.selectedItems()
        return str(items[0].data(0, ROLE_UID)) if items else None

    def _selected_node(self):
        uid = self._selected_uid()
        return self._find(uid) if uid else (self.tree, None, None)

    def _tree_item_for_node(self, node: dict, parent_item: QTreeWidgetItem | None = None):
        node_type = node.get("type")
        if node_type == "series":
            text = node.get("label", "Series circuit")
        elif node_type == "parallel":
            text = "Parallel block  ∥"
        else:
            text = self._element_text(node)
        item = QTreeWidgetItem([text])
        item.setData(0, ROLE_UID, node["uid"])
        item.setData(0, ROLE_TYPE, node_type)
        flags = item.flags() | Qt.ItemIsDropEnabled
        if node_type in {"element", "parallel"}:
            flags |= Qt.ItemIsDragEnabled
        else:
            flags &= ~Qt.ItemIsDragEnabled
        item.setFlags(flags)
        if node_type == "series":
            item.setToolTip(0, "Drop an element here to append it to this path.")
        elif node_type == "parallel":
            item.setToolTip(0, "Drag to reorder this block, or drop on a branch beneath it.")
        else:
            item.setToolTip(0, "Drag to rewire. Drop above/below to insert around this element.")
        if parent_item is None:
            self.tree_widget.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        if node_type == "series":
            for child in node.get("children", []):
                self._tree_item_for_node(child, item)
        elif node_type == "parallel":
            for i, branch in enumerate(node.get("branches", []), 1):
                branch["label"] = f"Branch {i}"
                self._tree_item_for_node(branch, item)
        return item

    def _element_text(self, element: dict) -> str:
        names = element.get("params") or custom_element_param_names(element["kind"], element["id"])
        chunks = []
        for name in names:
            value = self.values.get(name)
            if value is not None:
                chunks.append(f"{name}={value:.4g}")
        lock_mark = "  🔒" if any(name in self.locks for name in names) else ""
        suffix = f"  [{'; '.join(chunks)}]" if chunks else ""
        return f"{element['id']}  ({element['kind']}){suffix}{lock_mark}"

    def _rebuild_tree(self, select_uid: str | None = None):
        select_uid = select_uid or self._selected_uid() or self.tree.get("uid")
        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()
        root_item = self._tree_item_for_node(self.tree)
        self.tree_widget.expandAll()
        matches = self.tree_widget.findItems("*", Qt.MatchFlag.MatchWildcard | Qt.MatchFlag.MatchRecursive, 0)
        selected = None
        for item in matches + [root_item]:
            if str(item.data(0, ROLE_UID)) == str(select_uid):
                selected = item; break
        self.tree_widget.setCurrentItem(selected or root_item)
        self.tree_widget.blockSignals(False)
        self._selection_changed()

    def _select_uid_from_canvas(self, uid: str):
        """Keep the compact scientific outline synchronized with canvas selection."""
        matches = self.tree_widget.findItems(
            "*", Qt.MatchFlag.MatchWildcard | Qt.MatchFlag.MatchRecursive, 0
        )
        for item in matches:
            if str(item.data(0, ROLE_UID)) == str(uid):
                self._selection_from_canvas = True
                try:
                    self.tree_widget.setCurrentItem(item)
                finally:
                    self._selection_from_canvas = False
                return

    def _canvas_node_position_changed(self, uid: str, position):
        found = self._find(uid)
        if not found:
            return
        node, _, _ = found
        if node.get("type") != "element":
            return
        node["canvas_pos"] = [round(float(position.x()), 3), round(float(position.y()), 3)]
        self._commit_change(uid, "Moved symbol freely; live wires preserved")

    @staticmethod
    def _clear_canvas_positions(node: dict):
        node.pop("canvas_pos", None)
        if node.get("type") == "series":
            for child in node.get("children", []):
                CircuitBuilderDialog._clear_canvas_positions(child)
        elif node.get("type") == "parallel":
            for branch in node.get("branches", []):
                CircuitBuilderDialog._clear_canvas_positions(branch)

    def _auto_layout_canvas(self):
        self._clear_canvas_positions(self.tree)
        self._commit_change(self._selected_uid(), "Restored automatic schematic layout")
        self.canvas.fit_circuit()

    def _toggle_snap_grid(self, enabled: bool):
        self.canvas.snap_enabled = bool(enabled)

    def _add_canvas_note(self):
        text, accepted = QInputDialog.getText(
            self, "Canvas annotation", "Scientific note:"
        )
        text = str(text).strip()
        if not accepted or not text:
            return
        position = self.canvas.center_scene_position()
        self.tree.setdefault("canvas_annotations", []).append({
            "text": text,
            "position": [round(position.x(), 3), round(position.y(), 3)],
        })
        self._commit_change(self._selected_uid(), "Added schematic annotation")

    def _align_canvas_selection(self, mode: str):
        uids = self.canvas.selected_node_uids()
        if len(uids) < 2:
            QMessageBox.information(
                self, "Align symbols", "Select two or more symbols with the canvas rubber band first."
            )
            return
        positions = [self.canvas.node_items[uid].pos() for uid in uids]
        coordinate = (
            float(np.mean([point.y() for point in positions]))
            if mode == "row"
            else float(np.mean([point.x() for point in positions]))
        )
        for uid, point in zip(uids, positions):
            found = self._find(uid)
            if not found:
                continue
            node, _, _ = found
            x = point.x() if mode == "row" else coordinate
            y = coordinate if mode == "row" else point.y()
            if self.canvas.snap_enabled:
                x = round(x / 24.0) * 24.0
                y = round(y / 24.0) * 24.0
            node["canvas_pos"] = [round(float(x), 3), round(float(y), 3)]
        self._commit_change(
            uids[0], f"Aligned {len(uids)} symbols to one {mode}"
        )

    def _apply_circuit_template(self, index: int):
        key = str(self.template_combo.itemData(index) or "")
        if not key or key not in CIRCUITS:
            return
        self.tree = tree_for_spec(CIRCUITS[key])
        self.values = default_custom_values(self.tree)
        self.locks = set()
        self._commit_change(self.tree.get("uid"), f"Loaded template: {CIRCUITS[key].name}")
        self.template_combo.blockSignals(True)
        self.template_combo.setCurrentIndex(0)
        self.template_combo.blockSignals(False)

    def _open_dc_series_lab(self):
        dialog = DCSeriesGlobalDialog(
            self.tree,
            self.values,
            self.theme_name,
            self.dc_series,
            self,
        )
        if not dialog.exec() or not dialog.result_values:
            return
        valid_names = {p.name for p in custom_tree_params(self.tree)}
        self.values.update({
            name: float(value)
            for name, value in dialog.result_values.items()
            if name in valid_names
        })
        self.dc_series = list(dialog.studies)
        self._commit_change(
            self._selected_uid(), "Applied shared/median DC-series global-fit values"
        )

    def _copy_selected_element(self):
        node, _, _ = self._selected_node()
        if node.get("type") != "element":
            return
        self._copied_element = {
            "node": deepcopy(node),
            "values": {
                name: self.values.get(name)
                for name in node.get("params", []) if name in self.values
            },
            "locks": {
                name for name in node.get("params", []) if name in self.locks
            },
        }
        self.builder_status.setToolTip(f"Copied {node.get('id', node.get('kind'))}")

    def _paste_copied_element(self):
        if not self._copied_element:
            return
        source = self._copied_element["node"]
        kind = str(source.get("kind", ""))
        if kind not in {entry[0] for entry in ELEMENT_LIBRARY if entry[0] != "PARALLEL"}:
            return
        container, index = self._target_series()
        pasted = _element(kind, self._next_id(kind))
        old_names = list(source.get("params", []))
        for old_name, new_name in zip(old_names, pasted["params"]):
            if old_name in self._copied_element["values"]:
                self.values[new_name] = float(self._copied_element["values"][old_name])
            if old_name in self._copied_element["locks"]:
                self.locks.add(new_name)
        self.values.update({
            name: value for name, value in default_custom_values(_series([deepcopy(pasted)])).items()
            if name not in self.values
        })
        container.setdefault("children", []).insert(index, pasted)
        self._commit_change(pasted["uid"], f"Pasted {kind} element")

    def _show_live_monitor(self):
        self.right_tabs.setCurrentWidget(self.live_monitor)

    @staticmethod
    def _slider_to_parameter(position: int, pdef) -> float:
        fraction = min(max(float(position) / 1000.0, 0.0), 1.0)
        if pdef.scale == "log" and pdef.low > 0 and pdef.high > pdef.low:
            return float(10 ** (
                np.log10(pdef.low) + fraction * np.log10(pdef.high / pdef.low)
            ))
        return float(pdef.low + fraction * (pdef.high - pdef.low))

    @staticmethod
    def _parameter_to_slider(value: float, pdef) -> int:
        value = min(max(float(value), pdef.low), pdef.high)
        if pdef.scale == "log" and pdef.low > 0 and pdef.high > pdef.low and value > 0:
            fraction = np.log10(value / pdef.low) / np.log10(pdef.high / pdef.low)
        else:
            fraction = (value - pdef.low) / max(pdef.high - pdef.low, 1e-30)
        return int(round(1000 * min(max(float(fraction), 0.0), 1.0)))

    def _parameter_slider_preview(self, name: str, position: int, edit: QLineEdit, pdef):
        value = self._slider_to_parameter(position, pdef)
        self.values[name] = value
        edit.setText(f"{value:.10g}")
        self._update_preview()

    def _parameter_slider_commit(self, name: str):
        self._commit_change(self._selected_uid(), f"Updated {name} with live control")

    def _fit_stderr(self) -> dict[str, float]:
        result = self.fit_diagnostics
        if result is None:
            return {}
        if isinstance(result, dict):
            return {str(k): float(v) for k, v in result.get("stderr", {}).items()}
        return {
            str(k): float(v)
            for k, v in getattr(result, "stderr", {}).items()
        }

    def _fit_to_measured(self):
        if len(self.measured_frequency) < 5 or len(self.measured_impedance) < 5:
            QMessageBox.information(
                self, "Fit measured EIS", "Load measured EIS data before opening the composer."
            )
            return
        try:
            spec = make_custom_circuit(
                self.tree, self.name_edit.text().strip() or "Live composer circuit"
            )
            CIRCUITS[spec.key] = spec
            fixed = {
                name: float(self.values[name])
                for name in self.locks if name in self.values
            }
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                result = fit_model(
                    self.measured_frequency,
                    self.measured_impedance,
                    spec.key,
                    FitSettings(max_nfev=2500, multistart=2, robust_loss="soft_l1"),
                    initial=self.values,
                    fixed=fixed,
                )
            finally:
                QApplication.restoreOverrideCursor()
            self.values.update(result.params)
            self.fit_diagnostics = result
            self._commit_change(
                self._selected_uid(),
                f"Live fit complete • RMSE {result.rmse:.4g} Ω",
            )
            self.builder_status.setText(f"FIT • {result.rmse:.3g} Ω")
        except Exception as exc:
            QMessageBox.critical(self, "Fit measured EIS", str(exc))

    def _frequency_cursor_changed(self, frequency_hz: float):
        sensitivity = local_element_sensitivity(
            self.tree, self.values, float(frequency_hz)
        )
        self.canvas.set_science_overlay(
            sensitivity, self._identifiability, self._identifiability_details
        )
        valid = self.simulation_frequency[
            np.isfinite(self.simulation_frequency) & (self.simulation_frequency > 0)
        ]
        if len(valid):
            log_fraction = (
                np.log10(float(frequency_hz) / float(np.min(valid)))
                / max(np.log10(float(np.max(valid)) / float(np.min(valid))), 1e-30)
            )
            band = "HIGH-FREQUENCY" if log_fraction >= .67 else "LOW-FREQUENCY" if log_fraction <= .33 else "MID-FREQUENCY"
            strongest = max(sensitivity, key=sensitivity.get) if sensitivity else ""
            element = self._find(strongest) if strongest else None
            element_name = element[0].get("id", "") if element else ""
            self.live_monitor.frequency_label.setToolTip(
                f"{band} response" + (f" • strongest local element: {element_name}" if element_name else "")
            )

    def _update_live_science(self):
        try:
            simulated = evaluate_custom_tree(
                self.tree, self.simulation_frequency, self.values
            )
            self.live_monitor.set_data(
                self.simulation_frequency,
                simulated,
                self.measured_frequency,
                self.measured_impedance,
            )
            self._identifiability, self._identifiability_details = identifiability_map(
                self.tree,
                self.values,
                self.simulation_frequency,
                self._fit_stderr(),
            )
            current_frequency = self.live_monitor.current_frequency()
            if current_frequency is not None:
                self._frequency_cursor_changed(current_frequency)

            simulated_measured = None
            if len(self.measured_frequency) and len(self.measured_impedance):
                order = np.argsort(np.log10(self.simulation_frequency))
                log_sim_f = np.log10(self.simulation_frequency[order])
                valid = np.isfinite(self.measured_frequency) & (self.measured_frequency > 0)
                simulated_measured = np.full(len(self.measured_frequency), np.nan + 1j * np.nan)
                if np.any(valid):
                    log_measured = np.log10(self.measured_frequency[valid])
                    simulated_measured[valid] = (
                        np.interp(log_measured, log_sim_f, simulated[order].real)
                        + 1j * np.interp(log_measured, log_sim_f, simulated[order].imag)
                    )
            hypotheses = topology_hypotheses(
                self.tree,
                self.measured_frequency,
                self.measured_impedance,
                simulated_measured,
                self._identifiability,
                self.drt_data,
            )
        except Exception as exc:
            self.live_monitor.set_data([], [])
            self._identifiability = {}
            self._identifiability_details = {}
            self.canvas.set_science_overlay()
            hypotheses = [f"Complete every branch to enable simulation: {exc}"]
        self.hypothesis_list.clear()
        for text in hypotheses:
            item = QListWidgetItem(str(text))
            item.setToolTip(str(text))
            lines = max(1, (len(str(text)) + 41) // 42)
            item.setSizeHint(QSize(300, min(22 * lines + 8, 82)))
            self.hypothesis_list.addItem(item)

    def _target_series(self):
        node, parent, location = self._selected_node()
        if node.get("type") == "series":
            return node, len(node.get("children", []))
        if node.get("type") == "element" and parent and parent.get("type") == "series":
            return parent, location[1] + 1
        if node.get("type") == "parallel":
            branches = node.get("branches", [])
            if branches:
                return branches[0], len(branches[0].get("children", []))
        return self.tree, len(self.tree.get("children", []))

    def _add_palette_kind(self, kind: str):
        if kind == "PARALLEL":
            self._add_parallel()
        else:
            self._add_element(kind)

    def _new_parallel_node(self) -> dict:
        resistor_id = self._next_id("R")
        cpe_id = self._next_id("CPE")
        return _parallel([
            _series([_element("R", resistor_id)], label="Branch 1"),
            _series([_element("CPE", cpe_id)], label="Branch 2"),
        ])

    def _insert_kind(
        self, kind: str, container: dict, index: int
    ) -> dict:
        if kind == "PARALLEL":
            node = self._new_parallel_node()
        else:
            node = _element(kind, self._next_id(kind))
        container.setdefault("children", []).insert(index, node)
        self.values.update(default_custom_values(_series([deepcopy(node)])))
        return node

    def _drop_destination(
        self, target_uid: str | None, zone: str
    ) -> tuple[dict, int]:
        if not target_uid:
            return self.tree, len(self.tree.get("children", []))
        found = self._find(str(target_uid))
        if not found:
            return self.tree, len(self.tree.get("children", []))
        node, parent, location = found
        node_type = node.get("type")
        if node_type == "series":
            return node, len(node.get("children", []))
        if node_type == "parallel" and zone == "on":
            branches = node.get("branches", [])
            if branches:
                return branches[0], len(branches[0].get("children", []))
        if (
            parent is not None and parent.get("type") == "series"
            and location and location[0] == "children"
        ):
            index = int(location[1])
            return parent, index if zone == "above" else index + 1
        return self.tree, len(self.tree.get("children", []))

    @staticmethod
    def _contains_uid(node: dict, uid: str) -> bool:
        if str(node.get("uid")) == str(uid):
            return True
        if node.get("type") == "series":
            return any(
                CircuitBuilderDialog._contains_uid(child, uid)
                for child in node.get("children", [])
            )
        if node.get("type") == "parallel":
            return any(
                CircuitBuilderDialog._contains_uid(branch, uid)
                for branch in node.get("branches", [])
            )
        return False

    def _handle_topology_drop(self, payload: dict):
        action = str(payload.get("action", ""))
        target_uid = str(payload.get("target_uid", "") or "")
        zone = str(payload.get("zone", "on"))
        if action == "add":
            kind = str(payload.get("kind", ""))
            if kind not in {entry[0] for entry in ELEMENT_LIBRARY}:
                return
            container, index = self._drop_destination(target_uid, zone)
            node = self._insert_kind(kind, container, index)
            self._commit_change(
                node["uid"],
                f"Inserted {kind} by drag and drop",
            )
            return
        if action == "move":
            moved = self._move_node_to_drop(
                str(payload.get("source_uid", "")), target_uid, zone
            )
            if not moved:
                # A rejected magnetic drop must snap the visual item back to the
                # unchanged validated topology instead of leaving a false wire view.
                self._update_preview()

    def _handle_port_connection(self, payload: dict):
        source_uid = str(payload.get("source_uid", ""))
        target_uid = str(payload.get("target_uid", ""))
        source_side = str(payload.get("source_side", ""))
        target_side = str(payload.get("target_side", ""))
        if not source_uid or not target_uid or source_uid == target_uid:
            self._update_preview()
            return
        if source_side == "right" and target_side == "left":
            # Output → input means the target follows the source in series.
            moved = self._move_node_to_drop(target_uid, source_uid, "below")
        elif source_side == "left" and target_side == "right":
            # Input ← output means the source follows the target in series.
            moved = self._move_node_to_drop(source_uid, target_uid, "below")
        elif source_side == target_side:
            moved = self._parallelize_elements(source_uid, target_uid)
        else:
            QMessageBox.information(
                self,
                "Invalid terminal connection",
                "Connect an output terminal to an input terminal. Use a parallel "
                "block or branch portal to create a scientifically valid parallel path.",
            )
            moved = False
        if not moved:
            self._update_preview()

    def _parallelize_elements(self, first_uid: str, second_uid: str) -> bool:
        first_found, second_found = self._find(first_uid), self._find(second_uid)
        if not first_found or not second_found:
            return False
        first, first_parent, first_location = first_found
        second, second_parent, second_location = second_found
        if (
            first.get("type") != "element" or second.get("type") != "element"
            or first_parent is None or first_parent is not second_parent
            or first_parent.get("type") != "series"
            or not first_location or not second_location
            or first_location[0] != "children" or second_location[0] != "children"
        ):
            QMessageBox.information(
                self,
                "Automatic parallel connection",
                "Automatic input-to-input/output-to-output parallelization currently "
                "requires both elements to be on the same series path. Move them to one "
                "path first, or use a parallel branch portal.",
            )
            return False
        first_index, second_index = int(first_location[1]), int(second_location[1])
        children = first_parent["children"]
        nodes_by_index = {first_index: first, second_index: second}
        for index in sorted((first_index, second_index), reverse=True):
            children.pop(index)
        ordered_nodes = [nodes_by_index[index] for index in sorted(nodes_by_index)]
        for node in ordered_nodes:
            self._clear_canvas_positions(node)
        parallel_node = _parallel([
            _series([ordered_nodes[0]], label="Branch 1"),
            _series([ordered_nodes[1]], label="Branch 2"),
        ])
        children.insert(min(first_index, second_index), parallel_node)
        self._commit_change(
            parallel_node["uid"], "Created an automatic parallel block from terminal wiring"
        )
        return True

    def _move_node_to_drop(
        self, source_uid: str, target_uid: str, zone: str
    ) -> bool:
        if not source_uid or source_uid == target_uid:
            return False
        found = self._find(source_uid)
        if not found:
            return False
        node, source_parent, source_location = found
        if (
            source_parent is None or not source_location
            or source_location[0] != "children"
            or node.get("type") not in {"element", "parallel"}
        ):
            return False
        if target_uid and self._contains_uid(node, target_uid):
            QMessageBox.information(
                self, "Cannot rewire", "A block cannot be dropped inside itself."
            )
            return False
        destination, destination_index = self._drop_destination(target_uid, zone)
        if self._contains_uid(node, str(destination.get("uid"))):
            return False
        source_index = int(source_location[1])
        if source_parent is destination and source_index < destination_index:
            destination_index -= 1
        moved = source_parent["children"].pop(source_index)
        self._clear_canvas_positions(moved)
        destination.setdefault("children", []).insert(destination_index, moved)
        self._commit_change(
            moved["uid"], "Rewired topology by drag and drop"
        )
        return True

    def _commit_change(
        self, select_uid: str | None, message: str, *, record: bool = True
    ):
        self._rebuild_tree(select_uid)
        self._update_preview()
        self._animate_preview()
        if record:
            self._record_history()
        self.builder_status.setToolTip(message)

    def _add_element(self, kind: str):
        container, index = self._target_series()
        node = self._insert_kind(kind, container, index)
        self._commit_change(node["uid"], f"Added {kind}")

    def _add_parallel(self):
        container, index = self._target_series()
        node = self._insert_kind("PARALLEL", container, index)
        self._commit_change(node["uid"], "Added parallel block")

    def _add_branch(self):
        node, parent, _ = self._selected_node()
        parallel_node = node if node.get("type") == "parallel" else parent if parent and parent.get("type") == "parallel" else None
        if parallel_node is None:
            QMessageBox.information(self, "Add branch", "Select a parallel block or one of its branches first.")
            return
        index = len(parallel_node.get("branches", [])) + 1
        branch = _series(label=f"Branch {index}")
        parallel_node["branches"].append(branch)
        self._commit_change(branch["uid"], "Added parallel branch")

    def _remove_selected(self):
        node, parent, location = self._selected_node()
        if parent is None or location is None:
            return
        collection, index = location
        if collection == "branches" and len(parent.get("branches", [])) <= 2:
            QMessageBox.information(self, "Remove branch", "A parallel block must keep at least two branches.")
            return
        removed = parent[collection].pop(index)
        removed_names = set()
        if removed.get("type") == "element":
            removed_names.update(removed.get("params", []))
        else:
            temp = _series([removed]) if removed.get("type") != "series" else removed
            try:
                removed_names.update(p.name for p in custom_tree_params(temp))
            except Exception:
                pass
        for name in removed_names:
            self.values.pop(name, None); self.locks.discard(name)
        self._commit_change(parent.get("uid"), "Removed topology node")

    def _move_selected(self, direction: int):
        node, parent, location = self._selected_node()
        if parent is None or location is None:
            return
        collection, index = location
        new_index = index + direction
        items = parent.get(collection, [])
        if new_index < 0 or new_index >= len(items):
            return
        items[index], items[new_index] = items[new_index], items[index]
        self._commit_change(node["uid"], "Reordered topology")

    def _selection_changed(self):
        node, parent, location = self._selected_node()
        if hasattr(self, "canvas") and not self._selection_from_canvas:
            self.canvas.select_uid(str(node.get("uid", "")))
        movable = bool(
            parent is not None and location is not None
            and location[0] in {"children", "branches"}
        )
        self.up_button.setEnabled(movable)
        self.down_button.setEnabled(movable)
        self.remove_button.setEnabled(movable)
        self.duplicate_button.setEnabled(node.get("type") == "element")
        parallel_node = (
            node if node.get("type") == "parallel"
            else parent if parent and parent.get("type") == "parallel"
            else None
        )
        self.branch_button.setEnabled(parallel_node is not None)
        self._property_widgets.clear()
        self.property_table.setRowCount(0)
        if node.get("type") != "element":
            self.selected_label.setText("Select an electrical symbol to edit its numerical values.")
            return
        self.selected_label.setText(f"{node['id']} — {node['kind']} element")
        names = node.get("params") or custom_element_param_names(node["kind"], node["id"])
        self.property_table.setRowCount(len(names))
        for row, name in enumerate(names):
            pdef = custom_param_def(node["kind"], name, node["id"])
            label_item = QTableWidgetItem(pdef.label if len(names) == 1 else name)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            unit_item = QTableWidgetItem(pdef.unit)
            unit_item.setFlags(unit_item.flags() & ~Qt.ItemIsEditable)
            edit = QLineEdit(f"{self.values.get(name, (pdef.low + pdef.high) / 2):.10g}")
            validator = QDoubleValidator(pdef.low, pdef.high, 16, edit)
            validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
            edit.setValidator(validator)
            lock = QCheckBox()
            lock.setChecked(name in self.locks)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 1000)
            slider.setValue(self._parameter_to_slider(
                self.values.get(name, (pdef.low + pdef.high) / 2), pdef
            ))
            slider.setToolTip(
                f"Live {pdef.label} control: {pdef.low:g} to {pdef.high:g} {pdef.unit}"
            )
            edit.editingFinished.connect(lambda n=name, e=edit, pd=pdef: self._property_value_changed(n, e, pd))
            lock.toggled.connect(lambda checked, n=name: self._property_lock_changed(n, checked))
            slider.valueChanged.connect(
                lambda position, n=name, e=edit, pd=pdef:
                self._parameter_slider_preview(n, position, e, pd)
            )
            slider.sliderReleased.connect(
                lambda n=name: self._parameter_slider_commit(n)
            )
            self.property_table.setItem(row, 0, label_item)
            self.property_table.setCellWidget(row, 1, edit)
            self.property_table.setCellWidget(row, 2, slider)
            self.property_table.setItem(row, 3, unit_item)
            self.property_table.setCellWidget(row, 4, lock)
            self._property_widgets[name] = (edit, lock, slider)
        self.property_table.resizeColumnsToContents()

    def _property_value_changed(self, name, edit: QLineEdit, pdef):
        try:
            value = float(edit.text())
        except ValueError:
            return
        value = min(max(value, pdef.low), pdef.high)
        self.values[name] = value
        edit.setText(f"{value:.10g}")
        uid = self._selected_uid()
        self._commit_change(uid, f"Updated {name}")

    def _property_lock_changed(self, name: str, checked: bool):
        if checked:
            self.locks.add(name)
        else:
            self.locks.discard(name)
        self._commit_change(
            self._selected_uid(),
            f"{'Locked' if checked else 'Unlocked'} {name}",
        )

    def _update_preview(self):
        try:
            params = custom_tree_params(self.tree)
            units = {p.name: p.unit for p in params}
            self.canvas.set_circuit(
                self.tree, self.values, units, self._selected_uid(),
                fit=not bool(getattr(self.canvas, "node_items", {})),
            )
            self._update_live_science()
            element_count = len(list(self._all_elements()))
            parallel_count = self._parallel_count(self.tree)
            self.builder_status.setText(
                f"{element_count} ELEMENT{'S' if element_count != 1 else ''}  •  "
                f"{len(params)} PARAM{'S' if len(params) != 1 else ''}"
            )
            self.builder_status.setProperty(
                "state", "active" if element_count else "empty"
            )
            self.builder_status.style().unpolish(self.builder_status)
            self.builder_status.style().polish(self.builder_status)
            self.builder_status.setToolTip(
                f"{parallel_count} parallel block(s)"
            )
        except Exception:
            self.canvas.set_circuit(self.tree, self.values, {}, self._selected_uid())
            self._update_live_science()
            self.builder_status.setText("BUILDING")

    @staticmethod
    def _parallel_count(node: dict) -> int:
        count = 1 if node.get("type") == "parallel" else 0
        if node.get("type") == "series":
            count += sum(
                CircuitBuilderDialog._parallel_count(child)
                for child in node.get("children", [])
            )
        elif node.get("type") == "parallel":
            count += sum(
                CircuitBuilderDialog._parallel_count(branch)
                for branch in node.get("branches", [])
            )
        return count

    def _animate_preview(self):
        self._preview_animation = QPropertyAnimation(
            self.preview_effect, b"opacity", self
        )
        self._preview_animation.setDuration(210)
        self._preview_animation.setStartValue(0.48)
        self._preview_animation.setEndValue(1.0)
        self._preview_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._preview_animation.start()

    def _duplicate_selected(self):
        node, parent, location = self._selected_node()
        if (
            node.get("type") != "element" or parent is None
            or not location or location[0] != "children"
        ):
            return
        old_names = (
            node.get("params")
            or custom_element_param_names(node["kind"], node["id"])
        )
        duplicate = _element(node["kind"], self._next_id(node["kind"]))
        new_names = duplicate["params"]
        for old_name, new_name in zip(old_names, new_names):
            if old_name in self.values:
                self.values[new_name] = self.values[old_name]
            if old_name in self.locks:
                self.locks.add(new_name)
        parent["children"].insert(int(location[1]) + 1, duplicate)
        self._commit_change(duplicate["uid"], "Duplicated element")

    def _start_empty(self):
        self.tree = _series(label="Series circuit")
        self.values = {}
        self.locks = set()
        self._commit_change(self.tree["uid"], "Started an empty circuit")

    def _reset_template(self):
        self.tree = deepcopy(self.original_tree)
        _ensure_uids(self.tree)
        defaults = default_custom_values(self.tree)
        defaults.update({k: v for k, v in self.values.items() if k in {p.name for p in custom_tree_params(self.tree)}})
        self.values = defaults
        self.locks.intersection_update(self.values)
        self._commit_change(self.tree.get("uid"), "Reset to opening template")

    def _history_state(self) -> dict[str, object]:
        return {
            "tree": deepcopy(self.tree),
            "values": dict(self.values),
            "locks": set(self.locks),
        }

    def _record_history(self):
        state = self._history_state()
        if (
            0 <= self._history_index < len(self._history)
            and self._history[self._history_index] == state
        ):
            self._update_history_actions()
            return
        if self._history_index < len(self._history) - 1:
            self._history = self._history[:self._history_index + 1]
        self._history.append(state)
        if len(self._history) > 60:
            self._history.pop(0)
        self._history_index = len(self._history) - 1
        self._update_history_actions()

    def _update_history_actions(self):
        self.undo_button.setEnabled(self._history_index > 0)
        self.redo_button.setEnabled(
            0 <= self._history_index < len(self._history) - 1
        )

    def _restore_history(self):
        state = self._history[self._history_index]
        self.tree = deepcopy(state["tree"])
        self.values = dict(state["values"])
        self.locks = set(state["locks"])
        self._rebuild_tree(self.tree.get("uid"))
        self._update_preview()
        self._animate_preview()
        self._update_history_actions()

    def _undo(self):
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_history()

    def _redo(self):
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_history()

    def _save_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save visual circuit", "manual_circuit.json", "Circuit JSON (*.json)")
        if not path:
            return
        path_obj = Path(path)
        if path_obj.suffix.lower() != ".json":
            path_obj = path_obj.with_suffix(".json")
        payload = {"name": self.name_edit.text().strip(), "tree": self.tree, "values": self.values, "locks": sorted(self.locks)}
        path_obj.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _export_schematic(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export publication schematic",
            "equivalent_circuit.svg",
            "SVG vector (*.svg);;PDF document (*.pdf);;PNG image (*.png)",
        )
        if not path:
            return
        path_obj = Path(path)
        if not path_obj.suffix:
            suffix = ".pdf" if "PDF" in selected_filter else ".png" if "PNG" in selected_filter else ".svg"
            path_obj = path_obj.with_suffix(suffix)
        try:
            self.canvas.export_schematic(path_obj)
            self.builder_status.setToolTip(f"Exported publication schematic: {path_obj}")
        except Exception as exc:
            QMessageBox.critical(self, "Export schematic", str(exc))

    def _load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load visual circuit", "", "Circuit JSON (*.json)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            tree = payload.get("tree")
            if not isinstance(tree, dict) or tree.get("type") != "series":
                raise ValueError("The JSON file does not contain a valid series-root circuit.")
            _ensure_uids(tree)
            custom_tree_params(tree)
            self.tree = tree
            self.values = default_custom_values(tree)
            self.values.update({k: float(v) for k, v in payload.get("values", {}).items()})
            self.locks = set(payload.get("locks", []))
            self.name_edit.setText(str(payload.get("name") or "Manual visual circuit"))
            self._commit_change(self.tree.get("uid"), "Loaded circuit JSON")
        except Exception as exc:
            QMessageBox.critical(self, "Load circuit", str(exc))

    def _validate_and_accept(self):
        try:
            for name, (edit, _, _) in self._property_widgets.items():
                if edit.hasAcceptableInput():
                    self.values[name] = float(edit.text())
            spec = make_custom_circuit(self.tree, self.name_edit.text().strip() or "Manual visual circuit")
            names = {p.name for p in spec.params}
            missing = sorted(name for name in names if name not in self.values)
            if missing:
                raise ValueError(f"Missing values for: {', '.join(missing)}")
            validated = {}
            for pdef in spec.params:
                value = float(self.values[pdef.name])
                if not (pdef.low <= value <= pdef.high):
                    raise ValueError(
                        f"{pdef.name} must be between {pdef.low:g} and {pdef.high:g} {pdef.unit}."
                    )
                validated[pdef.name] = value
            self.values = validated
            self.locks.intersection_update(names)
        except Exception as exc:
            QMessageBox.critical(self, "Invalid circuit", str(exc))
            return
        self.accept()

    def result_payload(self):
        spec = make_custom_circuit(self.tree, self.name_edit.text().strip() or "Manual visual circuit")
        return spec, dict(self.values), set(self.locks)
