"""Interactive electrical-schematic canvas for the equivalent-circuit composer."""
from __future__ import annotations

from math import hypot, sin
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPageSize, QPdfWriter, QPen, QPixmap, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView, QStyle, QStyleOptionGraphicsItem, QWidget,
)

from .theme import get_palette


ELEMENT_MIME = "application/x-eis-element"
NODE_MIME = "application/x-eis-circuit-node"


def _symbol_kind(kind: str) -> str:
    return str(kind or "").replace("ₒ", "o").replace("ₛ", "s")


def draw_electrical_symbol(
    painter: QPainter,
    kind: str,
    center: QPointF,
    width: float,
    color: QColor,
    accent: QColor,
    line_width: float = 2.2,
):
    """Draw a recognizable IEC/ANSI-style EIS element between two terminals."""
    kind = _symbol_kind(kind)
    cx, cy = center.x(), center.y()
    left, right = cx - width / 2, cx + width / 2
    body_left, body_right = left + width * 0.18, right - width * 0.18
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(color, line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    if kind == "PARALLEL":
        painter.drawLine(QPointF(left, cy), QPointF(body_left, cy))
        painter.drawLine(QPointF(body_left, cy - 12), QPointF(body_left, cy + 12))
        painter.drawLine(QPointF(body_right, cy - 12), QPointF(body_right, cy + 12))
        painter.drawLine(QPointF(body_right, cy), QPointF(right, cy))
        painter.drawLine(QPointF(body_left, cy - 10), QPointF(body_right, cy - 10))
        painter.drawLine(QPointF(body_left, cy + 10), QPointF(body_right, cy + 10))
    elif kind == "R":
        painter.drawLine(QPointF(left, cy), QPointF(body_left, cy))
        points = [QPointF(body_left, cy)]
        steps = 8
        for i in range(1, steps):
            xx = body_left + (body_right - body_left) * i / steps
            yy = cy + (-8 if i % 2 else 8)
            points.append(QPointF(xx, yy))
        points.append(QPointF(body_right, cy))
        painter.drawPolyline(QPolygonF(points))
        painter.drawLine(QPointF(body_right, cy), QPointF(right, cy))
    elif kind in {"C", "CPE"}:
        plate_left = cx - 7
        plate_right = cx + 7
        painter.drawLine(QPointF(left, cy), QPointF(plate_left, cy))
        painter.drawLine(QPointF(plate_left, cy - 14), QPointF(plate_left, cy + 14))
        painter.drawLine(QPointF(plate_right, cy - 14), QPointF(plate_right, cy + 14))
        painter.drawLine(QPointF(plate_right, cy), QPointF(right, cy))
        if kind == "CPE":
            painter.setPen(QPen(accent, max(1.4, line_width - .3), Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(QPointF(cx + 13, cy - 15), QPointF(cx + 22, cy - 7))
            painter.drawText(QRectF(cx + 18, cy - 27, 18, 16), Qt.AlignCenter, "α")
    elif kind == "L":
        painter.drawLine(QPointF(left, cy), QPointF(body_left, cy))
        coil_width = (body_right - body_left) / 4
        for i in range(4):
            painter.drawArc(
                QRectF(body_left + i * coil_width, cy - 8, coil_width + 1, 16),
                0, 180 * 16,
            )
        painter.drawLine(QPointF(body_right, cy), QPointF(right, cy))
    elif kind == "G":
        painter.drawLine(QPointF(left, cy), QPointF(body_left, cy))
        painter.drawRoundedRect(QRectF(body_left, cy - 14, body_right - body_left, 28), 4, 4)
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(body_left, cy - 13, body_right - body_left, 26), Qt.AlignCenter, "G")
        painter.drawLine(QPointF(body_right, cy), QPointF(right, cy))
    elif kind in {"TLMo", "TLMs"}:
        painter.drawLine(QPointF(left, cy), QPointF(right, cy))
        for i in range(4):
            xx = body_left + (body_right - body_left) * i / 3
            painter.drawLine(QPointF(xx, cy), QPointF(xx, cy + 12))
            painter.drawLine(QPointF(xx - 5, cy + 12), QPointF(xx + 5, cy + 12))
        painter.setPen(QPen(accent, max(1.3, line_width - .5)))
        if kind == "TLMo":
            painter.drawEllipse(QPointF(body_right + 3, cy), 3.2, 3.2)
        else:
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(body_right + 3, cy), 3.2, 3.2)
    elif kind in {"W", "Wβ", "Wo", "Ws"}:
        painter.drawLine(QPointF(left, cy), QPointF(right, cy))
        for i in range(5):
            xx = body_left + (body_right - body_left) * i / 4
            painter.drawLine(QPointF(xx - 5, cy - 9), QPointF(xx + 5, cy + 9))
        painter.setPen(QPen(accent, max(1.3, line_width - .5)))
        if kind == "Wβ":
            painter.drawText(QRectF(cx + 18, cy - 28, 22, 18), Qt.AlignCenter, "β")
        elif kind == "Wo":
            painter.drawEllipse(QPointF(body_right + 3, cy), 3.4, 3.4)
        elif kind == "Ws":
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(body_right + 3, cy), 3.4, 3.4)
    else:
        painter.drawLine(QPointF(left, cy), QPointF(body_left, cy))
        painter.drawRoundedRect(QRectF(body_left, cy - 13, body_right - body_left, 26), 4, 4)
        painter.drawLine(QPointF(body_right, cy), QPointF(right, cy))

    painter.restore()


def schematic_symbol_pixmap(kind: str, theme_name: str, size: QSize | None = None) -> QPixmap:
    """Create a transparent palette/drag pixmap using the real circuit symbol."""
    size = size or QSize(112, 40)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    palette = get_palette(theme_name)
    draw_electrical_symbol(
        painter, kind, QPointF(size.width() / 2, size.height() / 2),
        max(54.0, size.width() - 12.0), QColor(palette.text), QColor(palette.accent), 2.0,
    )
    painter.end()
    return pixmap


def schematic_symbol_icon(kind: str, theme_name: str) -> QIcon:
    return QIcon(schematic_symbol_pixmap(kind, theme_name))


class SchematicWireItem(QGraphicsItem):
    """Orthogonal wire whose endpoints may follow moving schematic nodes."""

    def __init__(self, canvas: "SchematicCanvas", start_ref, end_ref):
        super().__init__()
        self.canvas = canvas
        self.start_ref = start_ref
        self.end_ref = end_ref
        self.path = QPainterPath()
        self.setZValue(-5)
        self.refresh()

    def _point(self, ref) -> QPointF:
        if isinstance(ref, tuple):
            item, side = ref
            return item.port_scene(side)
        return QPointF(ref)

    def refresh(self):
        start, end = self._point(self.start_ref), self._point(self.end_ref)
        path = QPainterPath(start)
        dx = end.x() - start.x()
        if abs(start.y() - end.y()) < 1.0:
            path.lineTo(end)
        else:
            middle_x = start.x() + dx / 2
            path.lineTo(QPointF(middle_x, start.y()))
            path.lineTo(QPointF(middle_x, end.y()))
            path.lineTo(end)
        self.prepareGeometryChange()
        self.path = path
        self.update()

    def boundingRect(self) -> QRectF:
        return self.path.boundingRect().adjusted(-8, -8, 8, 8)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        palette = get_palette(self.canvas.theme_name)
        glow = QColor(palette.fit)
        glow.setAlpha(54 if self.canvas.theme_name == "dark" else 30)
        painter.setPen(QPen(glow, 7.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self.path)
        wire = QColor(palette.fit if self.canvas.theme_name == "dark" else palette.plot_text)
        painter.setPen(QPen(wire, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self.path)


class InsertionPortalItem(QGraphicsObject):
    """A magnetic XMind-style insertion target tied to a valid topology slot."""

    def __init__(self, canvas: "SchematicCanvas", payload: dict, label: str = ""):
        super().__init__()
        self.canvas = canvas
        self.payload = dict(payload)
        self.label = label
        self.highlighted = False
        self.setZValue(4)
        self.setToolTip(label or "Drop here to insert into this circuit path")

    def boundingRect(self) -> QRectF:
        return QRectF(-13, -13, 26, 26)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        palette = get_palette(self.canvas.theme_name)
        pulse = .5 + .5 * sin(self.canvas.pulse_phase)
        accent = QColor(palette.accent)
        accent.setAlpha(220 if self.highlighted else int(72 + 38 * pulse))
        fill = QColor(palette.accent)
        fill.setAlpha(90 if self.highlighted else int(18 + 12 * pulse))
        radius = 8.5 if self.highlighted else 5.0 + pulse
        painter.setPen(QPen(accent, 2.0 if self.highlighted else 1.2))
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        if self.highlighted:
            painter.drawLine(QPointF(-4, 0), QPointF(4, 0))
            painter.drawLine(QPointF(0, -4), QPointF(0, 4))


class SchematicNodeItem(QGraphicsObject):
    """Movable, selectable electrical symbol with live wire endpoints."""

    def __init__(self, canvas: "SchematicCanvas", node: dict, value_text: str):
        super().__init__()
        self.canvas = canvas
        self.node = node
        self.uid = str(node.get("uid", ""))
        self.kind = str(node.get("kind", "?"))
        self.element_id = str(node.get("id", self.kind))
        self.value_text = value_text
        self.sensitivity_score = 0.0
        self.identifiability_state = "good"
        self.science_detail = ""
        self._press_pos = QPointF()
        self._port_dragging = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(
            f"{self.element_id} ({self.kind})\nDrag freely; release over a glowing + portal to rewire."
        )
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        return QRectF(-72, -48, 144, 96)

    def port_scene(self, side: str) -> QPointF:
        return self.mapToScene(QPointF(-64 if side == "left" else 64, 0))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        palette = get_palette(self.canvas.theme_name)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if self.sensitivity_score > .015:
            response_glow = QRadialGradient(QPointF(0, 0), 78)
            response = QColor(palette.fit)
            response.setAlpha(int(28 + 105 * min(self.sensitivity_score, 1.0)))
            response_glow.setColorAt(0, response)
            response_edge = QColor(palette.fit)
            response_edge.setAlpha(0)
            response_glow.setColorAt(1, response_edge)
            painter.setPen(Qt.NoPen)
            painter.setBrush(response_glow)
            painter.drawRoundedRect(self.boundingRect(), 18, 18)
        if selected or hovered:
            glow = QRadialGradient(QPointF(0, 0), 74)
            glow_color = QColor(palette.accent)
            glow_color.setAlpha(76 if selected else 38)
            glow.setColorAt(0, glow_color)
            edge = QColor(palette.accent)
            edge.setAlpha(0)
            glow.setColorAt(1, edge)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(self.boundingRect().adjusted(3, 3, -3, -3), 16, 16)
            border = QColor(palette.accent)
            border.setAlpha(190 if selected else 95)
            painter.setPen(QPen(border, 1.2))
            card = QColor(palette.panel_alt)
            card.setAlpha(120 if self.canvas.theme_name == "dark" else 155)
            painter.setBrush(card)
            painter.drawRoundedRect(QRectF(-68, -43, 136, 86), 14, 14)

        symbol_color = QColor(palette.text)
        accent = QColor(palette.accent)
        draw_electrical_symbol(
            painter, self.kind, QPointF(0, 0), 128, symbol_color, accent, 2.4
        )
        painter.setPen(symbol_color)
        title_font = QFont("Segoe UI", 8)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(-68, -39, 136, 18), Qt.AlignCenter, self.element_id)
        if self.value_text:
            value_font = QFont("Segoe UI", 6.8)
            painter.setFont(value_font)
            painter.setPen(QColor(palette.muted_text))
            painter.drawText(QRectF(-70, 24, 140, 18), Qt.AlignCenter, self.value_text)

        painter.setPen(QPen(accent, 1.4))
        painter.setBrush(QColor(palette.panel))
        painter.drawEllipse(QPointF(-64, 0), 3.0, 3.0)
        painter.drawEllipse(QPointF(64, 0), 3.0, 3.0)

        if self.identifiability_state in {"warning", "bad"}:
            status = QColor(palette.negative if self.identifiability_state == "bad" else palette.accent)
            painter.setPen(QPen(status, 1.4))
            painter.setBrush(status)
            painter.drawEllipse(QPointF(58, -34), 4.2, 4.2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.canvas is not None and not self.canvas.rebuilding:
                self.canvas.refresh_wires()
                self.canvas.update_drop_candidate(self.scenePos(), self.uid, 100.0)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        distances = {
            "left": hypot(event.pos().x() + 64, event.pos().y()),
            "right": hypot(event.pos().x() - 64, event.pos().y()),
        }
        side = min(distances, key=distances.get)
        if distances[side] <= 13.0 and event.button() == Qt.MouseButton.LeftButton:
            self.setSelected(True)
            self._port_dragging = True
            self.canvas.begin_port_wire(self, side, event.scenePos())
            event.accept()
            return
        self._press_pos = self.pos()
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._port_dragging:
            self.canvas.update_port_wire(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._port_dragging:
            self._port_dragging = False
            self.canvas.end_port_wire(event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        moved = hypot(self.pos().x() - self._press_pos.x(), self.pos().y() - self._press_pos.y())
        self.canvas.node_released(self, moved)


class SchematicCanvas(QGraphicsView):
    """Freeform schematic editor that emits safe series/parallel model operations."""

    selectionRequested = Signal(str)
    dropRequested = Signal(object)
    nodePositionRequested = Signal(str, object)
    portConnectionRequested = Signal(object)

    ELEMENT_WIDTH = 170.0
    ELEMENT_HEIGHT = 112.0
    PARALLEL_GAP = 34.0

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.setObjectName("schematicCanvas")
        self.scene_model = QGraphicsScene(self)
        self.setScene(self.scene_model)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setMinimumSize(540, 420)
        self.setToolTip(
            "Drag symbols from the deck. Drag placed symbols freely, or release over a + portal to rewire. "
            "Mouse wheel zooms; middle-drag pans."
        )
        self.tree: dict = {}
        self.values: dict[str, float] = {}
        self.units: dict[str, str] = {}
        self.node_items: dict[str, SchematicNodeItem] = {}
        self.wires: list[SchematicWireItem] = []
        self.portals: list[InsertionPortalItem] = []
        self.rebuilding = False
        self._selecting = False
        self._active_portal: InsertionPortalItem | None = None
        self._port_wire: SchematicWireItem | None = None
        self._port_source: tuple[SchematicNodeItem, str] | None = None
        self._port_target: tuple[SchematicNodeItem, str] | None = None
        self._panning = False
        self._pan_start = QPointF()
        self.pulse_phase = 0.0
        self.snap_enabled = True
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(42)
        self._pulse_timer.timeout.connect(self._tick)
        self._pulse_timer.start()
        self.scene_model.selectionChanged.connect(self._scene_selection_changed)
        self.minimap = QGraphicsView(self.scene_model, self.viewport())
        self.minimap.setObjectName("schematicMinimap")
        self.minimap.setFixedSize(178, 108)
        self.minimap.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.minimap.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.minimap.setInteractive(False)
        self.minimap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.minimap.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        minimap_palette = get_palette(self.theme_name)
        self.minimap.setBackgroundBrush(QBrush(QColor(minimap_palette.plot_bg)))
        self.minimap.show()

    def _tick(self):
        self.pulse_phase += .16
        for portal in self.portals:
            portal.update()

    @staticmethod
    def _format_value(value: float) -> str:
        value = float(value)
        if value == 0:
            return "0"
        if abs(value) >= 1e4 or abs(value) < 1e-3:
            return f"{value:.2e}"
        return f"{value:.4g}"

    def _value_text(self, node: dict) -> str:
        chunks = []
        replacements = {"alpha": "α", "beta": "β", "sigma": "σ", "tau": "τ"}
        for name in node.get("params", []):
            if name not in self.values:
                continue
            short = name
            for prefix, symbol in replacements.items():
                if name.lower().startswith(prefix):
                    short = symbol + name[len(prefix):]
                    break
            unit = self.units.get(name, "")
            chunks.append(f"{short}={self._format_value(self.values[name])}{unit}")
        text = " · ".join(chunks)
        return text if len(text) <= 28 else text[:27] + "…"

    def set_circuit(
        self,
        tree: dict,
        values: dict[str, float] | None = None,
        units: dict[str, str] | None = None,
        selected_uid: str | None = None,
        *,
        fit: bool = False,
    ):
        self.cancel_port_wire()
        self.rebuilding = True
        self.scene_model.clear()
        self.tree = tree
        self.values = dict(values or {})
        self.units = dict(units or {})
        self.node_items = {}
        self.wires = []
        self.portals = []
        self._active_portal = None

        total_width = max(180.0, self._measure_series(tree))
        total_height = max(150.0, self._series_height(tree))
        start = QPointF(70, 0)
        terminal = QPointF(35, 0)
        self._add_terminal(terminal, "IN")
        end_x, end_ref = self._layout_series(tree, start.x(), 0.0, terminal)
        output = QPointF(end_x + 45, 0)
        self._add_wire(end_ref, output)
        self._add_terminal(output, "OUT")
        for annotation in tree.get("canvas_annotations", []):
            self._add_annotation(annotation)

        bounds = self.scene_model.itemsBoundingRect().adjusted(-100, -100, 100, 100)
        bounds.setWidth(max(bounds.width(), total_width + 220))
        bounds.setHeight(max(bounds.height(), total_height + 200))
        self.scene_model.setSceneRect(bounds)
        self.rebuilding = False
        self.select_uid(selected_uid or "")
        self.refresh_wires()
        if fit:
            QTimer.singleShot(0, self.fit_circuit)
        QTimer.singleShot(0, self.update_minimap)

    def _add_terminal(self, point: QPointF, label: str):
        palette = get_palette(self.theme_name)
        dot = self.scene_model.addEllipse(
            QRectF(point.x() - 5, point.y() - 5, 10, 10),
            QPen(QColor(palette.accent), 2), QBrush(QColor(palette.accent)),
        )
        dot.setZValue(2)
        text = QGraphicsSimpleTextItem(label)
        font = QFont("Segoe UI", 7)
        font.setBold(True)
        text.setFont(font)
        text.setBrush(QBrush(QColor(palette.muted_text)))
        text.setPos(point.x() - 12, point.y() + 11)
        self.scene_model.addItem(text)

    def _add_annotation(self, annotation: dict):
        text_value = str(annotation.get("text", "")).strip()
        if not text_value:
            return
        palette = get_palette(self.theme_name)
        item = QGraphicsSimpleTextItem("✦  " + text_value)
        font = QFont("Segoe UI", 8)
        font.setItalic(True)
        item.setFont(font)
        item.setBrush(QBrush(QColor(palette.accent)))
        position = annotation.get("position", [0, 90])
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            position = [0, 90]
        item.setPos(float(position[0]), float(position[1]))
        item.setToolTip("Canvas annotation (saved with circuit JSON)")
        item.setZValue(3)
        self.scene_model.addItem(item)

    def _measure_child(self, child: dict) -> float:
        if child.get("type") == "element":
            return self.ELEMENT_WIDTH
        if child.get("type") == "parallel":
            branch_width = max(
                [self._measure_series(branch) for branch in child.get("branches", [])]
                or [120.0]
            )
            return branch_width + 110.0
        return 120.0

    def _measure_series(self, container: dict) -> float:
        children = container.get("children", [])
        return sum(self._measure_child(child) for child in children) if children else 120.0

    def _child_height(self, child: dict) -> float:
        if child.get("type") == "parallel":
            heights = [max(self.ELEMENT_HEIGHT, self._series_height(branch))
                       for branch in child.get("branches", [])]
            return sum(heights) + self.PARALLEL_GAP * max(0, len(heights) - 1)
        return self.ELEMENT_HEIGHT

    def _series_height(self, container: dict) -> float:
        return max([self._child_height(child) for child in container.get("children", [])]
                   or [self.ELEMENT_HEIGHT])

    def _layout_series(self, container: dict, x: float, y: float, entry_ref):
        previous = entry_ref
        children = container.get("children", [])
        if not children:
            self._add_portal(
                QPointF(x + 42, y),
                {"target_uid": str(container.get("uid", "")), "zone": "on"},
                container.get("label", "Empty path"),
            )
            return x + 84, previous

        for child in children:
            child_type = child.get("type")
            if child_type == "element":
                before = QPointF(x + 18, y)
                self._add_portal(
                    before,
                    {"target_uid": str(child.get("uid", "")), "zone": "above"},
                    f"Insert before {child.get('id', child.get('kind', 'element'))}",
                )
                base_position = QPointF(x + self.ELEMENT_WIDTH / 2, y)
                saved = child.get("canvas_pos")
                position = QPointF(float(saved[0]), float(saved[1])) if (
                    isinstance(saved, (list, tuple)) and len(saved) == 2
                ) else base_position
                item = SchematicNodeItem(self, child, self._value_text(child))
                item.setPos(position)
                self.scene_model.addItem(item)
                self.node_items[item.uid] = item
                self._add_wire(previous, (item, "left"))
                previous = (item, "right")
                x += self.ELEMENT_WIDTH
            elif child_type == "parallel":
                width = self._measure_child(child)
                split = QPointF(x + 36, y)
                join = QPointF(x + width - 36, y)
                self._add_portal(
                    QPointF(x + 16, y),
                    {"target_uid": str(child.get("uid", "")), "zone": "above"},
                    "Insert before parallel block",
                )
                self._add_wire(previous, split)
                branches = child.get("branches", [])
                heights = [max(self.ELEMENT_HEIGHT, self._series_height(branch)) for branch in branches]
                total_height = sum(heights) + self.PARALLEL_GAP * max(0, len(heights) - 1)
                cursor = y - total_height / 2
                branch_ys = []
                for height in heights:
                    branch_ys.append(cursor + height / 2)
                    cursor += height + self.PARALLEL_GAP
                if branch_ys:
                    self._add_wire(QPointF(split.x(), branch_ys[0]), QPointF(split.x(), branch_ys[-1]))
                    self._add_wire(QPointF(join.x(), branch_ys[0]), QPointF(join.x(), branch_ys[-1]))
                for index, (branch, branch_y) in enumerate(zip(branches, branch_ys), 1):
                    branch_start = QPointF(split.x(), branch_y)
                    branch_end_x, branch_end = self._layout_series(
                        branch, split.x() + 30, branch_y, branch_start
                    )
                    self._add_wire(branch_end, QPointF(join.x(), branch_y))
                    self._add_branch_label(branch, index, QPointF(split.x() + 10, branch_y - 48))
                previous = join
                x += width
            else:
                x += 120.0

        last_child = children[-1]
        self._add_portal(
            QPointF(x - 16, y),
            {"target_uid": str(last_child.get("uid", "")), "zone": "below"},
            "Insert after this node",
        )
        self._add_portal(
            QPointF(x + 26, y),
            {"target_uid": str(container.get("uid", "")), "zone": "on"},
            f"Append to {container.get('label', 'path')}",
        )
        return x, previous

    def _add_branch_label(self, branch: dict, index: int, point: QPointF):
        palette = get_palette(self.theme_name)
        text = QGraphicsSimpleTextItem(str(branch.get("label") or f"BRANCH {index}").upper())
        font = QFont("Segoe UI", 6.5)
        font.setBold(True)
        text.setFont(font)
        color = QColor(palette.accent)
        color.setAlpha(145)
        text.setBrush(QBrush(color))
        text.setPos(point)
        text.setZValue(1)
        self.scene_model.addItem(text)

    def _add_wire(self, start_ref, end_ref):
        wire = SchematicWireItem(self, start_ref, end_ref)
        self.scene_model.addItem(wire)
        self.wires.append(wire)
        return wire

    def _add_portal(self, point: QPointF, payload: dict, label: str):
        portal = InsertionPortalItem(self, payload, label)
        portal.setPos(point)
        self.scene_model.addItem(portal)
        self.portals.append(portal)
        return portal

    def refresh_wires(self):
        for wire in self.wires:
            wire.refresh()
        self.scene_model.update()

    def _nearest_node_port(
        self, scene_pos: QPointF, exclude_uid: str = "", radius: float = 22.0
    ) -> tuple[SchematicNodeItem, str] | None:
        candidates = []
        for uid, item in self.node_items.items():
            if str(uid) == str(exclude_uid):
                continue
            for side in ("left", "right"):
                point = item.port_scene(side)
                distance = hypot(point.x() - scene_pos.x(), point.y() - scene_pos.y())
                if distance <= radius:
                    candidates.append((distance, item, side))
        if not candidates:
            return None
        _, item, side = min(candidates, key=lambda candidate: candidate[0])
        return item, side

    def begin_port_wire(self, item: SchematicNodeItem, side: str, scene_pos: QPointF):
        self.cancel_port_wire()
        self._port_source = (item, str(side))
        self._port_wire = SchematicWireItem(
            self, (item, str(side)), QPointF(scene_pos)
        )
        self._port_wire.setZValue(8)
        self.scene_model.addItem(self._port_wire)
        item.setCursor(Qt.CrossCursor)

    def update_port_wire(self, scene_pos: QPointF):
        if self._port_wire is None or self._port_source is None:
            return
        source_item, _ = self._port_source
        self._port_target = self._nearest_node_port(scene_pos, source_item.uid)
        if self._port_target is not None:
            target_item, target_side = self._port_target
            self._port_wire.end_ref = (target_item, target_side)
            self.clear_drop_candidate()
        else:
            self._port_wire.end_ref = QPointF(scene_pos)
            self.update_drop_candidate(scene_pos, source_item.uid, 75.0)
        self._port_wire.refresh()

    def end_port_wire(self, scene_pos: QPointF):
        if self._port_source is None:
            self.cancel_port_wire()
            return
        source_item, source_side = self._port_source
        target = self._nearest_node_port(scene_pos, source_item.uid)
        portal = self._nearest_portal(scene_pos, source_item.uid, 70.0)
        payload = None
        if target is not None:
            target_item, target_side = target
            payload = {
                "source_uid": source_item.uid,
                "source_side": source_side,
                "target_uid": target_item.uid,
                "target_side": target_side,
            }
        elif portal is not None:
            payload = dict(portal.payload)
            payload.update({"action": "move", "source_uid": source_item.uid})
        self.cancel_port_wire()
        if payload is not None:
            if payload.get("action") == "move":
                self.dropRequested.emit(payload)
            else:
                self.portConnectionRequested.emit(payload)

    def cancel_port_wire(self):
        source = self._port_source[0] if self._port_source is not None else None
        if source is not None:
            source.setCursor(Qt.OpenHandCursor)
        if self._port_wire is not None and self._port_wire.scene() is self.scene_model:
            self.scene_model.removeItem(self._port_wire)
        self._port_wire = None
        self._port_source = None
        self._port_target = None
        self.clear_drop_candidate()

    def _scene_selection_changed(self):
        if self.rebuilding or self._selecting:
            return
        selected = [item for item in self.scene_model.selectedItems()
                    if isinstance(item, SchematicNodeItem)]
        if selected:
            self.selectionRequested.emit(selected[0].uid)

    def select_uid(self, uid: str):
        self._selecting = True
        try:
            for node_uid, item in self.node_items.items():
                item.setSelected(str(node_uid) == str(uid))
        finally:
            self._selecting = False
        self.viewport().update()

    def set_science_overlay(
        self,
        sensitivity: dict[str, float] | None = None,
        identifiability: dict[str, str] | None = None,
        details: dict[str, str] | None = None,
    ):
        sensitivity = sensitivity or {}
        identifiability = identifiability or {}
        details = details or {}
        for uid, item in self.node_items.items():
            item.sensitivity_score = float(sensitivity.get(uid, 0.0))
            item.identifiability_state = str(identifiability.get(uid, "good"))
            item.science_detail = str(details.get(uid, ""))
            status = (
                "Weak identifiability" if item.identifiability_state == "bad"
                else "Identifiability caution" if item.identifiability_state == "warning"
                else "No local identifiability warning"
            )
            item.setToolTip(
                f"{item.element_id} ({item.kind})\n"
                f"Relative local sensitivity: {item.sensitivity_score:.3f}\n"
                f"{status}"
                + (f"\n{item.science_detail}" if item.science_detail else "")
                + "\nDrag freely; release over a glowing + portal to rewire."
            )
            item.update()

    def _nearest_portal(
        self, scene_pos: QPointF, source_uid: str = "", radius: float = 150.0
    ) -> InsertionPortalItem | None:
        candidates = []
        for portal in self.portals:
            target_uid = str(portal.payload.get("target_uid", ""))
            if source_uid and target_uid == source_uid:
                continue
            distance = hypot(portal.scenePos().x() - scene_pos.x(), portal.scenePos().y() - scene_pos.y())
            if distance <= radius:
                candidates.append((distance, portal))
        return min(candidates, key=lambda pair: pair[0])[1] if candidates else None

    def update_drop_candidate(self, scene_pos: QPointF, source_uid: str = "", radius: float = 150.0):
        portal = self._nearest_portal(scene_pos, source_uid, radius)
        if portal is self._active_portal:
            return portal
        if self._active_portal is not None:
            self._active_portal.highlighted = False
            self._active_portal.update()
        self._active_portal = portal
        if portal is not None:
            portal.highlighted = True
            portal.update()
        return portal

    def clear_drop_candidate(self):
        if self._active_portal is not None:
            self._active_portal.highlighted = False
            self._active_portal.update()
        self._active_portal = None

    def node_released(self, item: SchematicNodeItem, moved_distance: float):
        if moved_distance < 4.0:
            self.clear_drop_candidate()
            return
        portal = self._nearest_portal(item.scenePos(), item.uid, 88.0)
        if portal is not None:
            payload = dict(portal.payload)
            payload.update({"action": "move", "source_uid": item.uid})
            self.clear_drop_candidate()
            self.dropRequested.emit(payload)
            return
        if self.snap_enabled:
            item.setPos(
                round(item.pos().x() / 24.0) * 24.0,
                round(item.pos().y() / 24.0) * 24.0,
            )
        self.clear_drop_candidate()
        self.nodePositionRequested.emit(item.uid, QPointF(item.pos()))

    @staticmethod
    def _accepted(mime) -> bool:
        return mime.hasFormat(ELEMENT_MIME) or mime.hasFormat(NODE_MIME)

    def dragEnterEvent(self, event):
        if self._accepted(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if not self._accepted(event.mimeData()):
            super().dragMoveEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        source_uid = ""
        if event.mimeData().hasFormat(NODE_MIME):
            source_uid = bytes(event.mimeData().data(NODE_MIME)).decode("utf-8")
        self.update_drop_candidate(point, source_uid, 180.0)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.clear_drop_candidate()
        event.accept()

    def dropEvent(self, event):
        mime = event.mimeData()
        if not self._accepted(mime):
            super().dropEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        source_uid = ""
        if mime.hasFormat(NODE_MIME):
            source_uid = bytes(mime.data(NODE_MIME)).decode("utf-8")
        portal = self._nearest_portal(point, source_uid, 210.0)
        target = dict(portal.payload) if portal is not None else {
            "target_uid": str(self.tree.get("uid", "")), "zone": "on"
        }
        if mime.hasFormat(ELEMENT_MIME):
            target.update({
                "action": "add",
                "kind": bytes(mime.data(ELEMENT_MIME)).decode("utf-8"),
            })
        else:
            target.update({"action": "move", "source_uid": source_uid})
        self.clear_drop_candidate()
        self.dropRequested.emit(target)
        event.acceptProposedAction()

    def wheelEvent(self, event):
        factor = 1.16 if event.angleDelta().y() > 0 else 1 / 1.16
        current = self.transform().m11()
        if .28 <= current * factor <= 3.8:
            self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = QPointF(event.position())
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = QPointF(event.position()) - self._pan_start
            self._pan_start = QPointF(event.position())
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def zoom_in(self):
        if self.transform().m11() < 3.8:
            self.scale(1.18, 1.18)

    def zoom_out(self):
        if self.transform().m11() > .28:
            self.scale(1 / 1.18, 1 / 1.18)

    def fit_circuit(self):
        rect = self.scene_model.itemsBoundingRect().adjusted(-45, -45, 45, 45)
        if rect.isValid() and not rect.isEmpty():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            if self.transform().m11() < 2.6:
                self.scale(1.22, 1.22)
        self.update_minimap()

    def update_minimap(self):
        if not hasattr(self, "minimap"):
            return
        rect = self.scene_model.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        if rect.isValid() and not rect.isEmpty():
            self.minimap.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.minimap.raise_()

    def selected_node_uids(self) -> list[str]:
        return [
            item.uid for item in self.scene_model.selectedItems()
            if isinstance(item, SchematicNodeItem)
        ]

    def center_scene_position(self) -> QPointF:
        return self.mapToScene(self.viewport().rect().center())

    def export_schematic(self, path: str | Path):
        """Export scene items as vector SVG/PDF or a high-resolution raster image."""
        path = Path(path)
        source = self.scene_model.itemsBoundingRect().adjusted(-35, -35, 35, 35)
        width = max(900, int(source.width() * 2))
        height = max(320, int(source.height() * 2))
        suffix = path.suffix.lower()
        if suffix == ".svg":
            from PySide6.QtSvg import QSvgGenerator
            device = QSvgGenerator()
            device.setFileName(str(path))
            device.setSize(QSize(width, height))
            device.setViewBox(QRectF(0, 0, width, height))
            device.setTitle("EIS equivalent-circuit schematic")
            painter = QPainter(device)
            painter.fillRect(QRectF(0, 0, width, height), Qt.white)
            self.scene_model.render(
                painter, QRectF(24, 24, width - 48, height - 48), source,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            painter.end()
            return
        if suffix == ".pdf":
            writer = QPdfWriter(str(path))
            writer.setResolution(300)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            painter = QPainter(writer)
            target = QRectF(120, 120, writer.width() - 240, writer.height() - 240)
            painter.fillRect(target, Qt.white)
            self.scene_model.render(
                painter, target, source, Qt.AspectRatioMode.KeepAspectRatio
            )
            painter.end()
            return
        pixmap = QPixmap(width, height)
        palette = get_palette(self.theme_name)
        pixmap.fill(QColor(palette.plot_bg))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene_model.render(
            painter, QRectF(24, 24, width - 48, height - 48), source,
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        painter.end()
        if not pixmap.save(str(path)):
            raise RuntimeError(f"Could not save schematic image: {path}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "minimap"):
            self.minimap.move(12, max(self.viewport().height() - self.minimap.height() - 12, 8))
            self.minimap.raise_()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        palette = get_palette(self.theme_name)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(palette.plot_bg))
        gradient.setColorAt(1, QColor(palette.window))
        painter.fillRect(rect, gradient)

        minor = QColor(palette.grid)
        minor.setAlpha(24 if self.theme_name == "dark" else 32)
        major = QColor(palette.accent)
        major.setAlpha(25 if self.theme_name == "dark" else 18)
        left = int(rect.left()) - (int(rect.left()) % 24)
        top = int(rect.top()) - (int(rect.top()) % 24)
        painter.setPen(QPen(minor, 1))
        for x in range(left, int(rect.right()) + 24, 24):
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for y in range(top, int(rect.bottom()) + 24, 24):
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(major, 1))
        for x in range(left - (left % 120), int(rect.right()) + 120, 120):
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for y in range(top - (top % 120), int(rect.bottom()) + 120, 120):
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
