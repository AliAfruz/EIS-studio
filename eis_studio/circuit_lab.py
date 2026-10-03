"""Live plotting and scientific diagnostics for the circuit composer."""
from __future__ import annotations

from math import hypot

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .diagnostics import diffusion_signature
from .models import custom_tree_params, evaluate_custom_tree
from .theme import get_palette


def _finite_xy(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


class MiniEISPlot(QWidget):
    """Lightweight Qt-painted Nyquist/Bode plot designed for live updates."""

    cursorIndexSelected = Signal(int)

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.mode = "nyquist"
        self.frequency = np.array([], dtype=float)
        self.simulated = np.array([], dtype=complex)
        self.measured_frequency = np.array([], dtype=float)
        self.measured = np.array([], dtype=complex)
        self.cursor_index = 0
        self.show_measured = True
        self.message = "Build a valid circuit to simulate"
        self._hit_points: list[tuple[int, QPointF]] = []
        self.setMinimumSize(286, 155)

    def set_data(
        self,
        frequency,
        simulated,
        measured_frequency=None,
        measured=None,
        cursor_index: int = 0,
    ):
        self.frequency = np.asarray(frequency if frequency is not None else [], dtype=float)
        self.simulated = np.asarray(simulated if simulated is not None else [], dtype=complex)
        self.measured_frequency = np.asarray(
            measured_frequency if measured_frequency is not None else [], dtype=float
        )
        self.measured = np.asarray(measured if measured is not None else [], dtype=complex)
        self.cursor_index = max(0, min(int(cursor_index), max(len(self.frequency) - 1, 0)))
        self.message = "" if len(self.simulated) else "Circuit is incomplete"
        self.update()

    def set_mode(self, mode: str):
        self.mode = "bode" if str(mode).lower().startswith("bode") else "nyquist"
        self.update()

    def set_cursor_index(self, index: int):
        self.cursor_index = max(0, min(int(index), max(len(self.frequency) - 1, 0)))
        self.update()

    @staticmethod
    def _range(values, padding=.08):
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        if not len(values):
            return 0.0, 1.0
        low, high = float(np.min(values)), float(np.max(values))
        if low == high:
            span = max(abs(low), 1.0) * .2
            return low - span, high + span
        span = high - low
        return low - padding * span, high + padding * span

    @staticmethod
    def _map_points(x, y, rect: QRectF, x_range, y_range) -> list[QPointF]:
        xmin, xmax = x_range
        ymin, ymax = y_range
        dx, dy = max(xmax - xmin, 1e-30), max(ymax - ymin, 1e-30)
        points = []
        for xx, yy in zip(x, y):
            px = rect.left() + (float(xx) - xmin) / dx * rect.width()
            py = rect.bottom() - (float(yy) - ymin) / dy * rect.height()
            points.append(QPointF(px, py))
        return points

    def _draw_axes(self, painter: QPainter, rect: QRectF, xlabel: str, ylabel: str):
        palette = get_palette(self.theme_name)
        grid = QColor(palette.grid)
        grid.setAlpha(62)
        painter.setPen(QPen(grid, .8))
        for i in range(1, 5):
            xx = rect.left() + rect.width() * i / 5
            yy = rect.top() + rect.height() * i / 5
            painter.drawLine(QPointF(xx, rect.top()), QPointF(xx, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), yy), QPointF(rect.right(), yy))
        painter.setPen(QPen(QColor(palette.muted_text), 1))
        painter.drawRect(rect)
        font = QFont("Segoe UI", 6.5)
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), rect.bottom() + 2, rect.width(), 13), Qt.AlignCenter, xlabel)
        painter.save()
        painter.translate(rect.left() - 15, rect.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-rect.height() / 2, -7, rect.height(), 13), Qt.AlignCenter, ylabel)
        painter.restore()

    def _draw_curve(self, painter: QPainter, points, color: QColor, width=1.8, dots=False):
        if not points:
            return
        if len(points) > 1:
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        if dots:
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            stride = max(1, len(points) // 45)
            for point in points[::stride]:
                painter.drawEllipse(point, 1.8, 1.8)

    def _draw_cursor(self, painter: QPainter, point: QPointF):
        palette = get_palette(self.theme_name)
        glow = QColor(palette.accent)
        glow.setAlpha(70)
        painter.setPen(QPen(glow, 7))
        painter.drawEllipse(point, 4.5, 4.5)
        painter.setPen(QPen(QColor(palette.accent), 2))
        painter.setBrush(QColor(palette.panel))
        painter.drawEllipse(point, 3.8, 3.8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = get_palette(self.theme_name)
        painter.fillRect(self.rect(), QColor(palette.plot_bg))
        if not len(self.simulated):
            painter.setPen(QColor(palette.muted_text))
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.message)
            return
        if self.mode == "bode":
            self._paint_bode(painter)
        else:
            self._paint_nyquist(painter)

    def _paint_nyquist(self, painter: QPainter):
        palette = get_palette(self.theme_name)
        rect = QRectF(28, 10, self.width() - 40, self.height() - 35)
        sx, sy = _finite_xy(self.simulated.real, -self.simulated.imag)
        measured_x, measured_y = (np.array([]), np.array([]))
        if self.show_measured and len(self.measured):
            measured_x, measured_y = _finite_xy(self.measured.real, -self.measured.imag)
        xr = self._range(np.concatenate([sx, measured_x]))
        yr = self._range(np.concatenate([sy, measured_y]))
        self._draw_axes(painter, rect, "Z′ / Ω", "−Z″ / Ω")
        if len(measured_x):
            points = self._map_points(measured_x, measured_y, rect, xr, yr)
            self._draw_curve(painter, points, QColor(palette.measured), 1.0, True)
        points = self._map_points(sx, sy, rect, xr, yr)
        self._hit_points = list(enumerate(points))
        self._draw_curve(painter, points, QColor(palette.fit), 2.1)
        if self.cursor_index < len(self.simulated):
            z = self.simulated[self.cursor_index]
            cursor = self._map_points([z.real], [-z.imag], rect, xr, yr)[0]
            self._draw_cursor(painter, cursor)

    def _paint_bode(self, painter: QPainter):
        palette = get_palette(self.theme_name)
        valid = np.isfinite(self.frequency) & (self.frequency > 0) & np.isfinite(self.simulated)
        valid_indices = np.flatnonzero(valid)
        f = self.frequency[valid]
        z = self.simulated[valid]
        if not len(f):
            return
        x = np.log10(f)
        top = QRectF(28, 8, self.width() - 40, (self.height() - 43) / 2)
        bottom = QRectF(28, top.bottom() + 17, self.width() - 40, (self.height() - 43) / 2)
        mag = np.log10(np.maximum(np.abs(z), 1e-30))
        phase = np.angle(z, deg=True)
        xr = self._range(x, .02)
        mag_range, phase_range = self._range(mag), self._range(phase)
        self._draw_axes(painter, top, "", "log |Z|")
        self._draw_axes(painter, bottom, "log f / Hz", "Phase / °")
        self._draw_curve(
            painter, self._map_points(x, mag, top, xr, mag_range), QColor(palette.fit), 1.8
        )
        self._hit_points = list(zip(
            [int(index) for index in valid_indices],
            self._map_points(x, mag, top, xr, mag_range),
        ))
        self._draw_curve(
            painter, self._map_points(x, phase, bottom, xr, phase_range), QColor(palette.secondary), 1.8
        )
        if self.show_measured and len(self.measured):
            mask = (
                np.isfinite(self.measured_frequency) & (self.measured_frequency > 0)
                & np.isfinite(self.measured)
            )
            mf, mz = self.measured_frequency[mask], self.measured[mask]
            if len(mf):
                mx = np.log10(mf)
                self._draw_curve(
                    painter,
                    self._map_points(mx, np.log10(np.maximum(np.abs(mz), 1e-30)), top, xr, mag_range),
                    QColor(palette.measured), 1.0, True,
                )
                self._draw_curve(
                    painter,
                    self._map_points(mx, np.angle(mz, deg=True), bottom, xr, phase_range),
                    QColor(palette.measured), 1.0, True,
                )
        cursor_frequency = self.frequency[self.cursor_index]
        nearest = int(np.argmin(np.abs(np.log10(f / cursor_frequency))))
        self._draw_cursor(
            painter, self._map_points([x[nearest]], [mag[nearest]], top, xr, mag_range)[0]
        )
        self._draw_cursor(
            painter, self._map_points([x[nearest]], [phase[nearest]], bottom, xr, phase_range)[0]
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._hit_points:
            position = event.position()
            distance, index = min(
                (
                    hypot(point.x() - position.x(), point.y() - position.y()),
                    point_index,
                )
                for point_index, point in self._hit_points
            )
            if distance <= 22.0:
                self.cursorIndexSelected.emit(int(index))
                event.accept()
                return
        super().mousePressEvent(event)


class FloatingEISMonitor(QFrame):
    """Movable glass monitor overlaid on the circuit-design canvas."""

    frequencyChanged = Signal(float)
    fitRequested = Signal()

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.embedded = False
        self.setObjectName("floatingEISMonitor")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(340, 260)
        self._collapsed = False
        self._drag_offset: QPoint | None = None
        self.frequency = np.array([], dtype=float)
        self.simulated = np.array([], dtype=complex)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(5)
        self.header = QFrame()
        self.header.setObjectName("floatingPlotHeader")
        self.header.installEventFilter(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(5, 1, 2, 1)
        title = QLabel("LIVE EIS MONITOR")
        title.setObjectName("floatingPlotTitle")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.rmse_label = QLabel("SIMULATION")
        self.rmse_label.setObjectName("floatingPlotBadge")
        self.rmse_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.collapse_button = QPushButton("−")
        self.collapse_button.setObjectName("floatingPlotClose")
        self.collapse_button.setFixedSize(24, 22)
        self.collapse_button.setToolTip("Collapse or expand the live monitor")
        self.collapse_button.clicked.connect(self._toggle_collapsed)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("floatingPlotClose")
        self.close_button.setFixedSize(24, 22)
        self.close_button.clicked.connect(self.hide)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.rmse_label)
        header_layout.addWidget(self.collapse_button)
        header_layout.addWidget(self.close_button)
        layout.addWidget(self.header)

        controls = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Nyquist", "Bode"])
        self.overlay_check = QCheckBox("Measured")
        self.overlay_check.setChecked(True)
        self.fit_button = QPushButton("Fit measured")
        self.fit_button.setObjectName("quietButton")
        self.fit_button.setToolTip("Fit the current custom circuit directly to the measured overlay")
        self.fit_button.clicked.connect(self.fitRequested.emit)
        controls.addWidget(self.mode_combo)
        controls.addWidget(self.overlay_check)
        controls.addWidget(self.fit_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.plot = MiniEISPlot(theme_name)
        layout.addWidget(self.plot, 1)

        frequency_row = QHBoxLayout()
        self.frequency_label = QLabel("f —")
        self.frequency_label.setObjectName("floatingFrequencyLabel")
        self.frequency_slider = QSlider(Qt.Horizontal)
        self.frequency_slider.setRange(0, 0)
        frequency_row.addWidget(self.frequency_label)
        frequency_row.addWidget(self.frequency_slider, 1)
        layout.addLayout(frequency_row)

        self.mode_combo.currentTextChanged.connect(self.plot.set_mode)
        self.overlay_check.toggled.connect(self._overlay_changed)
        self.frequency_slider.valueChanged.connect(self._cursor_changed)
        self.plot.cursorIndexSelected.connect(self.frequency_slider.setValue)

    def set_embedded(self, embedded: bool = True):
        """Switch between a floating overlay and a clean docked right-panel page."""
        self.embedded = bool(embedded)
        self.setProperty("embedded", self.embedded)
        self.style().unpolish(self)
        self.style().polish(self)
        if self._collapsed:
            self._collapsed = False
            for widget in (
                self.mode_combo, self.overlay_check, self.fit_button, self.plot,
                self.frequency_label, self.frequency_slider,
            ):
                widget.show()
        self.collapse_button.setVisible(not self.embedded)
        self.close_button.setVisible(not self.embedded)
        if self.embedded:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.setFixedSize(340, 260)

    def _toggle_collapsed(self):
        if self.embedded:
            return
        self._collapsed = not self._collapsed
        for widget in (
            self.mode_combo, self.overlay_check, self.fit_button, self.plot,
            self.frequency_label, self.frequency_slider,
        ):
            widget.setVisible(not self._collapsed)
        self.collapse_button.setText("□" if self._collapsed else "−")
        self.setFixedHeight(43 if self._collapsed else 260)

    def eventFilter(self, watched, event):
        if watched is self.header and not self.embedded:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.raise_()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                parent = self.parentWidget()
                position = parent.mapFromGlobal(event.globalPosition().toPoint() - self._drag_offset)
                x = max(0, min(position.x(), max(parent.width() - self.width(), 0)))
                y = max(0, min(position.y(), max(parent.height() - self.height(), 0)))
                self.move(x, y)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)

    def set_data(self, frequency, simulated, measured_frequency=None, measured=None):
        old_frequency = self.current_frequency()
        self.frequency = np.asarray(frequency if frequency is not None else [], dtype=float)
        self.simulated = np.asarray(simulated if simulated is not None else [], dtype=complex)
        self.frequency_slider.blockSignals(True)
        self.frequency_slider.setRange(0, max(len(self.frequency) - 1, 0))
        if len(self.frequency):
            if old_frequency and old_frequency > 0:
                index = int(np.argmin(np.abs(np.log10(self.frequency / old_frequency))))
            else:
                index = len(self.frequency) // 2
            self.frequency_slider.setValue(index)
        else:
            index = 0
            self.frequency_slider.setValue(0)
        self.frequency_slider.blockSignals(False)
        self.plot.set_data(
            self.frequency, self.simulated, measured_frequency, measured, index
        )
        self._update_frequency_label(index)
        measured_array = np.asarray(measured if measured is not None else [], dtype=complex)
        measured_f = np.asarray(
            measured_frequency if measured_frequency is not None else [], dtype=float
        )
        if len(measured_array) and len(self.simulated) and len(measured_f):
            order = np.argsort(np.log10(self.frequency))
            sf = np.log10(self.frequency[order])
            sz = self.simulated[order]
            valid = np.isfinite(measured_f) & (measured_f > 0) & np.isfinite(measured_array)
            if np.any(valid):
                mx = np.log10(measured_f[valid])
                zr = np.interp(mx, sf, sz.real)
                zi = np.interp(mx, sf, sz.imag)
                rmse = float(np.sqrt(np.mean(np.abs(measured_array[valid] - (zr + 1j * zi)) ** 2)))
                self.rmse_label.setText(f"RMSE {rmse:.3g} Ω")
            else:
                self.rmse_label.setText("SIMULATION")
        else:
            self.rmse_label.setText("SIMULATION")

    def current_frequency(self) -> float | None:
        index = self.frequency_slider.value()
        if 0 <= index < len(self.frequency):
            return float(self.frequency[index])
        return None

    def _cursor_changed(self, index: int):
        self.plot.set_cursor_index(index)
        self._update_frequency_label(index)
        if 0 <= index < len(self.frequency):
            self.frequencyChanged.emit(float(self.frequency[index]))

    def _update_frequency_label(self, index: int):
        if 0 <= index < len(self.frequency):
            value = float(self.frequency[index])
            self.frequency_label.setText(f"f {value:.3g} Hz")
        else:
            self.frequency_label.setText("f —")

    def _overlay_changed(self, checked: bool):
        self.plot.show_measured = bool(checked)
        self.plot.update()


def _walk_elements(tree: dict):
    for child in tree.get("children", []):
        if child.get("type") == "element":
            yield child
        elif child.get("type") == "parallel":
            for branch in child.get("branches", []):
                yield from _walk_elements(branch)


def local_element_sensitivity(
    tree: dict, values: dict[str, float], frequency_hz: float
) -> dict[str, float]:
    """Normalized finite-difference |dZ/dln(parameter)| contribution per element."""
    if not np.isfinite(frequency_hz) or frequency_hz <= 0:
        return {}
    frequency = np.array([float(frequency_hz)])
    try:
        baseline = evaluate_custom_tree(tree, frequency, values)[0]
    except Exception:
        return {}
    scale = max(abs(baseline), 1e-30)
    raw = {}
    for element in _walk_elements(tree):
        scores = []
        for name in element.get("params", []):
            value = float(values.get(name, 0.0))
            if not np.isfinite(value):
                continue
            delta = max(abs(value) * 1e-3, 1e-12)
            perturbed = dict(values)
            perturbed[name] = value + delta
            try:
                response = evaluate_custom_tree(tree, frequency, perturbed)[0]
                scores.append(abs(response - baseline) / scale / (delta / max(abs(value), delta)))
            except Exception:
                continue
        raw[str(element.get("uid", ""))] = float(np.sqrt(np.sum(np.square(scores)))) if scores else 0.0
    maximum = max(raw.values(), default=0.0)
    return {uid: score / maximum if maximum > 0 else 0.0 for uid, score in raw.items()}


def identifiability_map(
    tree: dict,
    values: dict[str, float],
    frequency: np.ndarray,
    stderr: dict[str, float] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Screen element identifiability from bounds, uncertainty, and response sensitivity."""
    stderr = dict(stderr or {})
    definitions = {p.name: p for p in custom_tree_params(tree)}
    frequency = np.asarray(frequency, dtype=float)
    frequency = frequency[np.isfinite(frequency) & (frequency > 0)]
    if len(frequency) > 24:
        frequency = frequency[np.linspace(0, len(frequency) - 1, 24).astype(int)]
    try:
        baseline = evaluate_custom_tree(tree, frequency, values) if len(frequency) else np.array([])
        baseline_norm = max(float(np.linalg.norm(baseline)), 1e-30)
    except Exception:
        baseline, baseline_norm = np.array([]), 1.0
    states, details = {}, {}
    for element in _walk_elements(tree):
        state = "good"
        messages = []
        for name in element.get("params", []):
            pdef = definitions.get(name)
            value = float(values.get(name, np.nan))
            if pdef is None or not np.isfinite(value):
                state = "bad"
                messages.append(f"{name}: missing")
                continue
            if pdef.scale == "log" and pdef.low > 0 and value > 0:
                span = np.log10(pdef.high / pdef.low)
                bound_distance = min(np.log10(value / pdef.low), np.log10(pdef.high / value)) / max(span, 1e-30)
            else:
                bound_distance = min(value - pdef.low, pdef.high - value) / max(pdef.high - pdef.low, 1e-30)
            se = float(stderr.get(name, np.nan))
            relative_se = abs(se / value) if np.isfinite(se) and value else np.nan
            response = np.nan
            if len(baseline):
                delta = max(abs(value) * 1e-3, 1e-12)
                perturbed = dict(values)
                perturbed[name] = min(value + delta, pdef.high)
                try:
                    shifted = evaluate_custom_tree(tree, frequency, perturbed)
                    response = float(np.linalg.norm(shifted - baseline) / baseline_norm / (delta / max(abs(value), delta)))
                except Exception:
                    pass
            if bound_distance < .02 or (np.isfinite(relative_se) and relative_se > 1.0) or (np.isfinite(response) and response < 1e-5):
                state = "bad"
            elif state != "bad" and (
                bound_distance < .07 or (np.isfinite(relative_se) and relative_se > .5)
                or (np.isfinite(response) and response < 1e-3)
            ):
                state = "warning"
            messages.append(
                f"{name}: bound {100 * bound_distance:.1f}%"
                + (f", SE {100 * relative_se:.0f}%" if np.isfinite(relative_se) else "")
                + (f", sensitivity {response:.2g}" if np.isfinite(response) else "")
            )
        uid = str(element.get("uid", ""))
        states[uid] = state
        details[uid] = "; ".join(messages)
    return states, details


def topology_hypotheses(
    tree: dict,
    frequency,
    measured,
    simulated=None,
    identifiability: dict[str, str] | None = None,
    drt_data=None,
) -> list[str]:
    """Return conservative, explicitly labelled circuit hypotheses."""
    f = np.asarray(frequency if frequency is not None else [], dtype=float)
    z = np.asarray(measured if measured is not None else [], dtype=complex)
    if not len(f) or len(f) != len(z):
        return ["Load measured EIS data to generate topology hypotheses."]
    valid = np.isfinite(f) & (f > 0) & np.isfinite(z)
    f, z = f[valid], z[valid]
    if len(f) < 5:
        return ["At least five measured frequencies are needed for topology hypotheses."]
    hypotheses = []
    kinds = {str(element.get("kind")) for element in _walk_elements(tree)}
    try:
        diffusion = diffusion_signature(f, z)
        if float(diffusion.get("strength", 0.0)) >= .45 and not kinds.intersection({"W", "Wβ", "Wo", "Ws", "G", "TLMo", "TLMs"}):
            hypotheses.append("Hypothesis: a low-frequency diffusion/distributed-transport element may be missing.")
    except Exception:
        pass
    if np.any(z.imag > 0) and "L" not in kinds:
        hypotheses.append("Hypothesis: an inductive lead or adsorption loop may be present.")
    order = np.argsort(f)[::-1]
    y = np.maximum(-z.imag[order], 0)
    peaks = int(np.sum((y[1:-1] > y[:-2]) & (y[1:-1] > y[2:]) & (y[1:-1] > .08 * max(np.max(y), 1e-30))))
    parallel_blocks = 0
    def count_parallel(node):
        nonlocal parallel_blocks
        if node.get("type") == "parallel":
            parallel_blocks += 1
            for branch in node.get("branches", []):
                count_parallel(branch)
        else:
            for child in node.get("children", []):
                count_parallel(child)
    count_parallel(tree)
    if peaks >= 2 and parallel_blocks < 2:
        hypotheses.append("Hypothesis: the data may contain a second resolved time constant.")
    if drt_data is not None:
        try:
            gamma = np.asarray(drt_data["gamma_ohm"], dtype=float)
            gamma = gamma[np.isfinite(gamma)]
            drt_peaks = int(np.sum(
                (gamma[1:-1] > gamma[:-2]) & (gamma[1:-1] > gamma[2:])
                & (gamma[1:-1] > .10 * max(float(np.max(gamma)), 1e-30))
            )) if len(gamma) >= 3 else 0
            if drt_peaks > max(parallel_blocks, 1):
                hypotheses.append(
                    f"Hypothesis: DRT screening shows {drt_peaks} resolved peak candidates, more than the current relaxation branches."
                )
        except Exception:
            pass
    if simulated is not None:
        sim = np.asarray(simulated, dtype=complex)
        if len(sim) == len(z):
            residual = z - sim
            normalized = float(np.sqrt(np.mean(np.abs(residual) ** 2)) / max(np.sqrt(np.mean(np.abs(z) ** 2)), 1e-30))
            if normalized > .12:
                hypotheses.append("Hypothesis: structured model mismatch remains; inspect Nyquist/Bode residual regions before adding complexity.")
    if identifiability and any(state == "bad" for state in identifiability.values()):
        hypotheses.append("Caution: one or more elements are weakly identifiable, boundary-limited, or highly uncertain.")
        if any(
            element.get("kind") == "CPE"
            and identifiability.get(str(element.get("uid", ""))) == "bad"
            for element in _walk_elements(tree)
        ):
            hypotheses.append(
                "Caution: a CPE is poorly identifiable at the current values/window; avoid mechanistic interpretation of Q or α."
            )
    if not hypotheses:
        hypotheses.append("No strong topology mismatch was detected by the current screening rules.")
    return hypotheses[:5]
