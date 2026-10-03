"""Cinematic presentation primitives for the EIS Gold Studio shell.

The animation is deliberately lightweight: it uses a single timer-driven
painted backdrop plus small transition effects, and never touches scientific
data or fitting state.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QTabWidget,
    QWidget,
)


class CinematicBackdrop(QWidget):
    """Animated layered gradient with floating light volumes and particles."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._theme_name = theme_name
        self._motion_enabled = True
        self._phase = 0.0
        self.setObjectName("cinematicRoot")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

        # Stable pseudo-random particle coordinates keep the visual deterministic.
        self._particles = [
            (
                ((index * 47) % 101) / 100.0,
                ((index * 71 + 13) % 103) / 102.0,
                0.7 + (index % 4) * 0.45,
                index * 0.43,
            )
            for index in range(28)
        ]

    def _advance(self):
        if not self._motion_enabled:
            return
        self._phase = (self._phase + 0.018) % (2.0 * math.pi)
        self.update()

    def set_theme(self, theme_name: str):
        self._theme_name = "dark" if theme_name == "dark" else "light"
        self.update()

    def set_motion_enabled(self, enabled: bool):
        self._motion_enabled = bool(enabled)
        if self._motion_enabled and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._motion_enabled:
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = max(self.width(), 1)
        height = max(self.height(), 1)

        if self._theme_name == "dark":
            top, middle, bottom = QColor("#07121B"), QColor("#111522"), QColor("#160D18")
            orb_colors = (QColor(37, 181, 190, 105), QColor(226, 172, 65, 102), QColor(116, 76, 184, 92))
            particle = QColor(240, 207, 128, 82)
            grid = QColor(255, 229, 166, 16)
        else:
            top, middle, bottom = QColor("#F8F3E8"), QColor("#EEF5F3"), QColor("#F5E8D7")
            orb_colors = (QColor(40, 154, 164, 65), QColor(217, 156, 45, 72), QColor(132, 99, 183, 55))
            particle = QColor(124, 88, 25, 56)
            grid = QColor(91, 70, 34, 14)

        base = QLinearGradient(0, 0, width, height)
        base.setColorAt(0.0, top)
        base.setColorAt(0.48, middle)
        base.setColorAt(1.0, bottom)
        painter.fillRect(self.rect(), base)

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        orb_specs = (
            (0.15, 0.20, 0.31, 0.70, 1.00),
            (0.82, 0.14, 0.27, 1.15, 2.20),
            (0.70, 0.82, 0.36, 0.82, 4.00),
        )
        span = min(width, height)
        for color, (x, y, radius, speed, offset) in zip(orb_colors, orb_specs):
            drift_x = math.sin(self._phase * speed + offset) * width * 0.035
            drift_y = math.cos(self._phase * speed * 0.77 + offset) * height * 0.045
            center = QPointF(x * width + drift_x, y * height + drift_y)
            glow = QRadialGradient(center, radius * span)
            glow.setColorAt(0.0, color)
            faded = QColor(color)
            faded.setAlpha(max(8, color.alpha() // 4))
            glow.setColorAt(0.48, faded)
            clear = QColor(color)
            clear.setAlpha(0)
            glow.setColorAt(1.0, clear)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(center, radius * span, radius * span)
        painter.restore()

        # Slow star-like points and a restrained technical grid add depth.
        painter.setPen(QPen(grid, 1.0))
        grid_step = 64
        for x in range(-height, width + height, grid_step):
            painter.drawLine(x, 0, x - height, height)

        painter.setPen(Qt.NoPen)
        for x, y, radius, offset in self._particles:
            shimmer = 0.40 + 0.60 * (0.5 + 0.5 * math.sin(self._phase * 1.8 + offset))
            dot = QColor(particle)
            dot.setAlpha(int(particle.alpha() * shimmer))
            painter.setBrush(dot)
            px = x * width + math.sin(self._phase + offset) * 5.0
            py = y * height + math.cos(self._phase * 0.8 + offset) * 4.0
            painter.drawEllipse(QPointF(px, py), radius, radius)


class OrbitalEISMark(QWidget):
    """Animated orbital mark used as the visual object in the hero header."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._theme_name = theme_name
        self._phase = 0.0
        self._motion_enabled = True
        self.setFixedSize(62, 62)
        self.setToolTip("Live impedance-analysis workspace")
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _advance(self):
        if self._motion_enabled:
            self._phase = (self._phase + 0.035) % (2.0 * math.pi)
            self.update()

    def set_theme(self, theme_name: str):
        self._theme_name = "dark" if theme_name == "dark" else "light"
        self.update()

    def set_motion_enabled(self, enabled: bool):
        self._motion_enabled = bool(enabled)
        if enabled and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._motion_enabled:
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        gold = QColor("#F0C96A" if self._theme_name == "dark" else "#A96F12")
        cyan = QColor("#65D8DE" if self._theme_name == "dark" else "#167A84")

        glow = QRadialGradient(center, 29)
        core = QColor(cyan)
        core.setAlpha(68)
        glow.setColorAt(0.0, core)
        edge = QColor(cyan)
        edge.setAlpha(0)
        glow.setColorAt(1.0, edge)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, 29, 29)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(gold, 1.8))
        painter.drawEllipse(center, 21, 12)
        painter.save()
        painter.translate(center)
        painter.rotate(62)
        painter.drawEllipse(QPointF(0, 0), 21, 12)
        painter.restore()

        orbit_x = center.x() + math.cos(self._phase) * 21
        orbit_y = center.y() + math.sin(self._phase) * 12
        painter.setPen(Qt.NoPen)
        painter.setBrush(cyan)
        painter.drawEllipse(QPointF(orbit_x, orbit_y), 3.2, 3.2)

        path_points = []
        for index in range(25):
            x = center.x() - 14 + index * 28 / 24
            y = center.y() + math.sin(index / 24 * math.pi * 2 + self._phase) * 4.2
            path_points.append(QPointF(x, y))
        painter.setPen(QPen(cyan, 1.5))
        for start, end in zip(path_points, path_points[1:]):
            painter.drawLine(start, end)


class PageFadeController(QObject):
    """Apply a short cinematic fade whenever a tab page changes."""

    def __init__(self, tabs: QTabWidget, duration_ms: int = 240, parent=None):
        super().__init__(parent or tabs)
        self.tabs = tabs
        self.duration_ms = duration_ms
        self._animation: QPropertyAnimation | None = None
        self._target: QWidget | None = None
        tabs.currentChanged.connect(self.animate_current)

    def animate_current(self, _index: int):
        target = self.tabs.currentWidget()
        if target is None:
            return
        if self._animation is not None:
            self._animation.stop()
        if self._target is not None and self._target is not target:
            self._target.setGraphicsEffect(None)

        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(self.duration_ms)
        animation.setStartValue(0.20)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda: self._finish(target, effect))
        self._target = target
        self._animation = animation
        animation.start()

    def _finish(self, target: QWidget, effect: QGraphicsOpacityEffect):
        if self._target is target and target.graphicsEffect() is effect:
            target.setGraphicsEffect(None)


def apply_glass_shadow(widget: QWidget, dark: bool = True):
    """Give a glass card a soft depth shadow without changing its layout."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(30)
    effect.setOffset(0, 9)
    effect.setColor(QColor(0, 0, 0, 105 if dark else 48))
    widget.setGraphicsEffect(effect)
    return effect
