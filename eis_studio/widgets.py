from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QPoint, QPointF, QSize, QRect, QObject, QEvent, Signal
from PySide6.QtGui import (
    QAction, QPainter, QPen, QColor, QFont, QPalette, QKeySequence, QValidator
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QDoubleSpinBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QSlider, QDial, QVBoxLayout, QHBoxLayout, QGridLayout, QSizePolicy,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMenu, QFileDialog,
    QMessageBox, QLabel, QCheckBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .theme import get_palette


class WheelChangeBlocker(QObject):
    """Block mouse-wheel value changes in option controls application-wide.

    Wheel events over spin boxes, combo boxes, sliders, and dials are consumed so
    scrolling a settings panel cannot silently alter analysis parameters. The
    surrounding QScrollArea continues to scroll when the pointer is over labels,
    group boxes, and other non-value widgets. Values can still be changed using
    the keyboard, arrows, drop-down selection, or direct text entry.
    """

    _protected_types = (QAbstractSpinBox, QComboBox, QSlider, QDial)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            widget = watched if isinstance(watched, QWidget) else None
            # The event can originate from an internal child (for example the
            # line edit inside a spin box), so inspect the parent chain too.
            while widget is not None:
                if isinstance(widget, self._protected_types):
                    event.ignore()
                    return True
                widget = widget.parentWidget()
        return super().eventFilter(watched, event)


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """A double spin box that cannot be changed accidentally by wheel scrolling."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """An integer spin box that cannot be changed accidentally by wheel scrolling."""

    def wheelEvent(self, event):
        event.ignore()


class ScientificDoubleSpinBox(NoWheelDoubleSpinBox):
    """Compact scientific-notation editor with adaptive keyboard/button steps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(15)
        self.setKeyboardTracking(False)
        self.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)

    def textFromValue(self, value: float) -> str:
        return f"{value:.10g}"

    def valueFromText(self, text: str) -> float:
        try:
            return float(text.strip().replace(",", "."))
        except ValueError:
            return self.value()

    def validate(self, text: str, position: int):
        cleaned = text.strip().replace(",", ".")
        if cleaned in {"", "+", "-", ".", "+.", "-.", "e", "E"} or cleaned.lower().endswith("e"):
            return QValidator.State.Intermediate, text, position
        try:
            value = float(cleaned)
        except ValueError:
            return QValidator.State.Invalid, text, position
        if self.minimum() <= value <= self.maximum():
            return QValidator.State.Acceptable, text, position
        return QValidator.State.Intermediate, text, position

    def fixup(self, text: str) -> str:
        try:
            value = min(max(float(text.strip().replace(",", ".")), self.minimum()), self.maximum())
            return self.textFromValue(value)
        except ValueError:
            return self.textFromValue(self.value())


class ManualParameterEditor(QWidget):
    """Editable circuit parameters with optional fixed-value locks."""

    valuesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec = None
        self._spins: dict[str, ScientificDoubleSpinBox] = {}
        self._locks: dict[str, QCheckBox] = {}
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(6)
        self._layout.setVerticalSpacing(4)

    @staticmethod
    def _parameter_element_map(diagram) -> dict[str, str]:
        mapping: dict[str, str] = {}

        def walk(item):
            if isinstance(item, tuple) and item:
                if item[0] == "element":
                    _, _kind, label, params = item
                    for name in params:
                        mapping[str(name)] = str(label)
                elif item[0] in {"parallel", "series"}:
                    for child in item[1:]:
                        walk(child)

        for item in diagram or ():
            walk(item)
        return mapping

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._spins.clear()
        self._locks.clear()

    def set_spec(self, spec, values: dict[str, float] | None = None, locks: set[str] | None = None):
        self._clear()
        self._spec = spec
        values = values or {}
        locks = set(locks or ())
        headers = ("Element", "Parameter", "Value", "Unit", "Lock")
        for column, text in enumerate(headers):
            label = QLabel(f"<b>{text}</b>")
            self._layout.addWidget(label, 0, column)
        element_map = self._parameter_element_map(spec.diagram)
        for row, pdef in enumerate(spec.params, 1):
            element_label = QLabel(element_map.get(pdef.name, pdef.label))
            parameter_label = QLabel(pdef.label)
            spin = ScientificDoubleSpinBox()
            spin.setRange(pdef.low, pdef.high)
            spin.setValue(float(values.get(pdef.name, (pdef.low * pdef.high) ** 0.5 if pdef.scale == "log" else (pdef.low + pdef.high) / 2)))
            spin.setToolTip(
                f"Manual value for {pdef.label}. Range: {pdef.low:g} to {pdef.high:g} {pdef.unit}. "
                "This value is used as the fit starting guess; lock it to keep it fixed."
            )
            unit = QLabel(pdef.unit or "—")
            lock = QCheckBox()
            lock.setChecked(pdef.name in locks)
            lock.setToolTip("Lock this value so it is not changed by the optimizer.")
            spin.valueChanged.connect(lambda _value: self.valuesChanged.emit())
            lock.toggled.connect(lambda _checked: self.valuesChanged.emit())
            self._layout.addWidget(element_label, row, 0)
            self._layout.addWidget(parameter_label, row, 1)
            self._layout.addWidget(spin, row, 2)
            self._layout.addWidget(unit, row, 3)
            self._layout.addWidget(lock, row, 4, alignment=Qt.AlignCenter)
            self._spins[pdef.name] = spin
            self._locks[pdef.name] = lock
        self._layout.setColumnStretch(2, 1)

    def values(self) -> dict[str, float]:
        return {name: spin.value() for name, spin in self._spins.items()}

    def locks(self) -> set[str]:
        return {name for name, box in self._locks.items() if box.isChecked()}

    def fixed_values(self) -> dict[str, float]:
        values = self.values()
        return {name: values[name] for name in self.locks()}

    def set_values(self, values: dict[str, float], preserve_locks: bool = True):
        for name, value in values.items():
            spin = self._spins.get(name)
            if spin is not None:
                spin.blockSignals(True)
                spin.setValue(float(value))
                spin.blockSignals(False)
        if not preserve_locks:
            for box in self._locks.values():
                box.setChecked(False)
        self.valuesChanged.emit()

    def set_locks(self, locks: set[str]):
        locks = set(locks)
        for name, box in self._locks.items():
            box.blockSignals(True)
            box.setChecked(name in locks)
            box.blockSignals(False)
        self.valuesChanged.emit()


class CopyableTableWidget(QTableWidget):
    """Read-only spreadsheet-like table with clipboard and file export support.

    The widget supports Ctrl+C, right-click copy commands, rectangular clipboard
    output that pastes cleanly into Excel, and CSV/TSV/XLSX export for either the
    selected area or the complete table.
    """

    def __init__(self, rows: int = 0, columns: int = 0, parent=None):
        super().__init__(rows, columns, parent)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setToolTip(
            "Ctrl+C copies selected cells. Right-click for copy, row-copy, "
            "select-all, and CSV/Excel export options."
        )

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def _selected_bounds(self):
        indexes = self.selectedIndexes()
        if not indexes and self.currentRow() >= 0 and self.currentColumn() >= 0:
            indexes = [self.model().index(self.currentRow(), self.currentColumn())]
        if not indexes:
            return None
        rows = [index.row() for index in indexes]
        cols = [index.column() for index in indexes]
        return min(rows), max(rows), min(cols), max(cols), {(i.row(), i.column()) for i in indexes}

    def _cell_text(self, row: int, column: int) -> str:
        item = self.item(row, column)
        return "" if item is None else item.text()

    def _headers(self, columns: list[int]) -> list[str]:
        output = []
        for column in columns:
            item = self.horizontalHeaderItem(column)
            output.append(item.text() if item is not None else f"Column {column + 1}")
        return output

    def _tabular_text(self, rows: list[int], columns: list[int], *,
                      include_headers: bool, selected_cells: set[tuple[int, int]] | None = None) -> str:
        lines: list[str] = []
        if include_headers:
            lines.append("\t".join(self._headers(columns)))
        for row in rows:
            values = []
            for column in columns:
                if selected_cells is not None and (row, column) not in selected_cells:
                    values.append("")
                else:
                    values.append(self._cell_text(row, column))
            lines.append("\t".join(values))
        return "\n".join(lines)

    def copy_selection(self, include_headers: bool = False):
        bounds = self._selected_bounds()
        if bounds is None:
            return
        r0, r1, c0, c1, selected = bounds
        text = self._tabular_text(
            list(range(r0, r1 + 1)), list(range(c0, c1 + 1)),
            include_headers=include_headers, selected_cells=selected
        )
        QApplication.clipboard().setText(text)

    def copy_selected_rows(self):
        indexes = self.selectedIndexes()
        rows = sorted({index.row() for index in indexes})
        if not rows and self.currentRow() >= 0:
            rows = [self.currentRow()]
        if not rows:
            return
        columns = list(range(self.columnCount()))
        QApplication.clipboard().setText(
            self._tabular_text(rows, columns, include_headers=True)
        )

    def copy_all(self):
        if self.rowCount() == 0 or self.columnCount() == 0:
            return
        rows = list(range(self.rowCount()))
        columns = list(range(self.columnCount()))
        QApplication.clipboard().setText(
            self._tabular_text(rows, columns, include_headers=True)
        )

    def to_dataframe(self, selected_only: bool = False) -> pd.DataFrame:
        if selected_only:
            bounds = self._selected_bounds()
            if bounds is None:
                return pd.DataFrame()
            r0, r1, c0, c1, selected = bounds
            rows = list(range(r0, r1 + 1))
            columns = list(range(c0, c1 + 1))
            records = []
            for row in rows:
                records.append([
                    self._cell_text(row, column) if (row, column) in selected else ""
                    for column in columns
                ])
        else:
            rows = list(range(self.rowCount()))
            columns = list(range(self.columnCount()))
            records = [[self._cell_text(row, column) for column in columns] for row in rows]
        return pd.DataFrame(records, columns=self._headers(columns))

    def export_table(self, selected_only: bool = False):
        frame = self.to_dataframe(selected_only=selected_only)
        if frame.empty and len(frame.columns) == 0:
            QMessageBox.information(self, "Export table", "There are no cells to export.")
            return
        default_name = "selected_table.xlsx" if selected_only else "table_export.xlsx"
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export selected cells" if selected_only else "Export complete table",
            default_name,
            "Excel workbook (*.xlsx);;CSV comma-delimited (*.csv);;TSV tab-delimited (*.tsv)"
        )
        if not path:
            return
        path_obj = Path(path)
        if not path_obj.suffix:
            if "CSV" in selected_filter:
                path_obj = path_obj.with_suffix(".csv")
            elif "TSV" in selected_filter:
                path_obj = path_obj.with_suffix(".tsv")
            else:
                path_obj = path_obj.with_suffix(".xlsx")
        suffix = path_obj.suffix.lower()
        if suffix == ".csv":
            frame.to_csv(path_obj, index=False)
        elif suffix in {".tsv", ".txt"}:
            frame.to_csv(path_obj, index=False, sep="\t")
        else:
            frame.to_excel(path_obj, index=False)

    def _show_context_menu(self, position):
        index = self.indexAt(position)
        if index.isValid() and not self.selectionModel().isSelected(index):
            self.clearSelection()
            self.setCurrentCell(index.row(), index.column())
            item = self.item(index.row(), index.column())
            if item is not None:
                item.setSelected(True)

        menu = QMenu(self)
        copy_action = menu.addAction("Copy selected cells")
        copy_action.setShortcut(QKeySequence.Copy)
        copy_headers_action = menu.addAction("Copy selected cells with headers")
        copy_rows_action = menu.addAction("Copy selected row(s) with headers")
        copy_all_action = menu.addAction("Copy entire table with headers")
        menu.addSeparator()
        select_all_action = menu.addAction("Select all")
        menu.addSeparator()
        export_selection_action = menu.addAction("Export selected cells…")
        export_all_action = menu.addAction("Export complete table…")

        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen == copy_action:
            self.copy_selection()
        elif chosen == copy_headers_action:
            self.copy_selection(include_headers=True)
        elif chosen == copy_rows_action:
            self.copy_selected_rows()
        elif chosen == copy_all_action:
            self.copy_all()
        elif chosen == select_all_action:
            self.selectAll()
        elif chosen == export_selection_action:
            self.export_table(selected_only=True)
        elif chosen == export_all_action:
            self.export_table(selected_only=False)


class PlotPanel(QWidget):
    """Matplotlib panel with themes, clipboard copy, and image/data export."""

    def __init__(self, parent=None, theme_name: str = "light"):
        super().__init__(parent)
        self.theme_name = theme_name
        self.figure = Figure(figsize=(7, 5), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._show_plot_menu)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        self.copy_image_action = QAction("Copy image", self)
        self.copy_image_action.setShortcut(QKeySequence.Copy)
        self.copy_image_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.copy_image_action.triggered.connect(self.copy_plot_image)
        self.addAction(self.copy_image_action)

        self.copy_data_action = QAction("Copy data", self)
        self.copy_data_action.setShortcut("Ctrl+Shift+C")
        self.copy_data_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.copy_data_action.triggered.connect(self.copy_plot_data)
        self.addAction(self.copy_data_action)

        self.save_image_action = QAction("Export image", self)
        self.save_image_action.triggered.connect(self.export_plot_image)
        self.export_data_action = QAction("Export data", self)
        self.export_data_action.triggered.connect(self.export_plot_data)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.copy_image_action)
        self.toolbar.addAction(self.save_image_action)
        self.toolbar.addAction(self.export_data_action)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip(
            "Right-click a plot to copy it, save PNG/SVG/PDF, or export every plotted series. "
            "Ctrl+C copies the plot image when the plot is focused."
        )
        self.apply_theme(theme_name, redraw=False)

    def _default_stem(self) -> str:
        title = ""
        for axis in self.figure.axes:
            if axis.get_title().strip():
                title = axis.get_title().strip()
                break
        title = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
        return title or "eis_plot"

    def copy_plot_image(self):
        QApplication.clipboard().setPixmap(self.canvas.grab())

    def data_frame(self) -> pd.DataFrame:
        """Return all line and scatter data in a portable long-form table."""
        records: list[dict] = []
        for axis_index, axis in enumerate(self.figure.axes, start=1):
            axis_title = axis.get_title() or f"Axis {axis_index}"
            x_label = axis.get_xlabel()
            y_label = axis.get_ylabel()

            for line_index, line in enumerate(axis.lines, start=1):
                x = np.asarray(line.get_xdata())
                y = np.asarray(line.get_ydata())
                count = min(len(x), len(y))
                label = str(line.get_label())
                if not label or label.startswith("_"):
                    label = f"line_{line_index}"
                for point in range(count):
                    records.append({
                        "axis": axis_index,
                        "axis_title": axis_title,
                        "x_label": x_label,
                        "y_label": y_label,
                        "series": label,
                        "artist_type": "line",
                        "point": point + 1,
                        "x": x[point],
                        "y": y[point],
                    })

            for collection_index, collection in enumerate(axis.collections, start=1):
                try:
                    offsets = np.asarray(collection.get_offsets())
                except Exception:
                    continue
                if offsets.ndim != 2 or offsets.shape[1] < 2 or len(offsets) == 0:
                    continue
                label = str(collection.get_label())
                if not label or label.startswith("_"):
                    label = f"scatter_{collection_index}"
                for point, (x_value, y_value, *_) in enumerate(offsets.tolist(), start=1):
                    records.append({
                        "axis": axis_index,
                        "axis_title": axis_title,
                        "x_label": x_label,
                        "y_label": y_label,
                        "series": label,
                        "artist_type": "scatter",
                        "point": point,
                        "x": x_value,
                        "y": y_value,
                    })
        return pd.DataFrame.from_records(records, columns=[
            "axis", "axis_title", "x_label", "y_label", "series",
            "artist_type", "point", "x", "y"
        ])

    def copy_plot_data(self):
        frame = self.data_frame()
        if frame.empty:
            QMessageBox.information(self, "Copy plot data", "This plot does not contain exportable series yet.")
            return
        QApplication.clipboard().setText(frame.to_csv(index=False, sep="\t"))

    def save_figure(self, path: str | Path, *, dpi: int = 300):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor=self.figure.get_facecolor())

    def export_plot_image(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export plot",
            self._default_stem() + ".png",
            "PNG image (*.png);;SVG vector image (*.svg);;PDF document (*.pdf);;JPEG image (*.jpg *.jpeg);;TIFF image (*.tif *.tiff)"
        )
        if not path:
            return
        path_obj = Path(path)
        if not path_obj.suffix:
            suffix = ".svg" if "SVG" in selected_filter else ".pdf" if "PDF" in selected_filter else ".png"
            path_obj = path_obj.with_suffix(suffix)
        self.save_figure(path_obj)

    def export_plot_data(self):
        frame = self.data_frame()
        if frame.empty:
            QMessageBox.information(self, "Export plot data", "This plot does not contain exportable series yet.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export plotted data",
            self._default_stem() + "_data.xlsx",
            "Excel workbook (*.xlsx);;CSV comma-delimited (*.csv);;TSV tab-delimited (*.tsv)"
        )
        if not path:
            return
        path_obj = Path(path)
        if not path_obj.suffix:
            path_obj = path_obj.with_suffix(".csv" if "CSV" in selected_filter else ".tsv" if "TSV" in selected_filter else ".xlsx")
        if path_obj.suffix.lower() == ".csv":
            frame.to_csv(path_obj, index=False)
        elif path_obj.suffix.lower() in {".tsv", ".txt"}:
            frame.to_csv(path_obj, index=False, sep="\t")
        else:
            frame.to_excel(path_obj, index=False)

    def _show_plot_menu(self, position):
        menu = QMenu(self)
        copy_image = menu.addAction("Copy plot image")
        copy_data = menu.addAction("Copy plotted data")
        menu.addSeparator()
        export_image = menu.addAction("Export plot image…")
        export_data = menu.addAction("Export plotted data…")
        chosen = menu.exec(self.canvas.mapToGlobal(position))
        if chosen == copy_image:
            self.copy_plot_image()
        elif chosen == copy_data:
            self.copy_plot_data()
        elif chosen == export_image:
            self.export_plot_image()
        elif chosen == export_data:
            self.export_plot_data()

    def apply_theme(self, theme_name: str, redraw: bool = True):
        """Apply colors to the figure, all existing axes, legends, and toolbar."""
        self.theme_name = theme_name
        p = get_palette(theme_name)
        self.figure.set_facecolor(p.plot_bg)
        self.canvas.setStyleSheet(f"background-color: {p.plot_bg}; border: 0;")
        self.toolbar.setStyleSheet(
            f"QToolBar {{background: {p.panel_alt}; color: {p.text}; border: 0;}}"
            f"QToolButton {{color: {p.text}; background: transparent; border-radius: 4px; padding: 3px;}}"
            f"QToolButton:hover {{background: {p.accent}; color: {p.accent_text};}}"
            f"QLabel {{color: {p.text};}}"
        )

        toolbar_palette = self.toolbar.palette()
        toolbar_palette.setColor(QPalette.Window, QColor(p.panel_alt))
        toolbar_palette.setColor(QPalette.WindowText, QColor(p.text))
        toolbar_palette.setColor(QPalette.Text, QColor(p.text))
        toolbar_palette.setColor(QPalette.ButtonText, QColor(p.text))
        self.toolbar.setPalette(toolbar_palette)

        for ax in self.figure.axes:
            ax.set_facecolor(p.plot_bg)
            ax.title.set_color(p.plot_text)
            ax.xaxis.label.set_color(p.plot_text)
            ax.yaxis.label.set_color(p.plot_text)
            ax.tick_params(axis="both", which="both", colors=p.plot_text)
            ax.xaxis.get_offset_text().set_color(p.plot_text)
            ax.yaxis.get_offset_text().set_color(p.plot_text)
            for spine in ax.spines.values():
                spine.set_color(p.border)
            for gridline in list(ax.get_xgridlines()) + list(ax.get_ygridlines()):
                gridline.set_color(p.grid)
                gridline.set_alpha(0.32)

            sequence = (p.measured, p.fit, p.secondary)
            for index, line in enumerate(ax.lines):
                label = str(line.get_label()).lower()
                if "fit" in label:
                    color = p.fit
                elif "imag" in label:
                    color = p.secondary
                elif "measured" in label or "batch" in label or "real residual" in label:
                    color = p.measured
                else:
                    y_data = line.get_ydata()
                    try:
                        is_zero_reference = len(y_data) > 0 and all(abs(float(y)) < 1e-15 for y in y_data)
                    except Exception:
                        is_zero_reference = False
                    color = p.muted_text if is_zero_reference else sequence[index % len(sequence)]
                line.set_color(color)
                line.set_markeredgecolor(color)
                line.set_markerfacecolor(color)
            for index, collection in enumerate(ax.collections):
                label = str(collection.get_label()).lower()
                color = p.fit if "fit" in label else p.measured if ("measured" in label or "batch" in label) else sequence[index % len(sequence)]
                try:
                    collection.set_facecolor(color)
                    collection.set_edgecolor(color)
                except Exception:
                    pass

            legend = ax.get_legend()
            if legend is not None:
                legend.get_frame().set_facecolor(p.panel)
                legend.get_frame().set_edgecolor(p.border)
                legend.get_frame().set_alpha(0.94)
                for text in legend.get_texts():
                    text.set_color(p.plot_text)

        if redraw:
            self.canvas.draw_idle()


class CircuitDiagram(QWidget):
    """Theme-aware circuit renderer with labels, values, clipboard, and export."""

    def __init__(self, parent=None, theme_name: str = "light"):
        super().__init__(parent)
        self.diagram = (("element", "R", "Rₛ", ("Rs",)),
                        ("parallel", ("element", "R", "Rct", ("Rct",)),
                         ("element", "CPE", "CPE", ("Q", "alpha"))))
        self.values: dict[str, float] = {}
        self.units: dict[str, str] = {}
        self.theme_name = theme_name
        self.setMinimumHeight(190)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setToolTip("Right-click to copy or export the equivalent-circuit diagram.")
        self._resize_for_diagram()

    def set_diagram(self, diagram):
        self.diagram = tuple(diagram or ())
        self._resize_for_diagram()
        self.update()

    def set_values(self, values: dict[str, float] | None, units: dict[str, str] | None = None):
        self.values = dict(values or {})
        self.units = dict(units or {})
        self.update()

    def set_theme(self, theme_name: str):
        self.theme_name = theme_name
        self.update()

    def _element_info(self, item):
        if isinstance(item, tuple) and item and item[0] == "element":
            return str(item[1]), str(item[2]), tuple(item[3])
        text = str(item)
        if text.startswith("CPE"):
            return "CPE", text, ()
        if text.startswith("Wβ"):
            return "Wβ", text, ()
        if text.startswith("Wₒ") or text.startswith("Wo"):
            return "Wo", text, ()
        if text.startswith("Wₛ") or text.startswith("Ws"):
            return "Ws", text, ()
        if text.startswith("TLMₒ") or text.startswith("TLMo"):
            return "TLMo", text, ()
        if text.startswith("TLMₛ") or text.startswith("TLMs"):
            return "TLMs", text, ()
        if text.startswith("G"):
            return "G", text, ()
        return text[:1] if text else "?", text, ()

    def _item_size(self, item) -> tuple[float, float]:
        if isinstance(item, tuple) and item:
            if item[0] == "element":
                return 112.0, 76.0
            if item[0] == "series":
                sizes = [self._item_size(child) for child in item[1:]]
                return max(80.0, sum(w for w, _ in sizes) + 14 * max(len(sizes) - 1, 0)), max([h for _, h in sizes] or [76.0])
            if item[0] == "parallel":
                sizes = [self._item_size(branch) for branch in item[1:]]
                branch_width = max([w for w, _ in sizes] or [100.0])
                total_height = sum(max(h, 68.0) for _, h in sizes) + 18.0
                return branch_width + 58.0, max(total_height, 118.0)
        return 100.0, 76.0

    def _diagram_size(self) -> tuple[float, float]:
        sizes = [self._item_size(item) for item in self.diagram]
        width = sum(w for w, _ in sizes) + 20 * max(len(sizes) - 1, 0) + 70
        height = max([h for _, h in sizes] or [150.0]) + 50
        return max(width, 360.0), max(height, 190.0)

    def _resize_for_diagram(self):
        width, height = self._diagram_size()
        self.setMinimumSize(int(width), int(height))
        self.resize(int(width), int(height))
        self.updateGeometry()

    def sizeHint(self):
        width, height = self._diagram_size()
        return QSize(int(width), int(height))

    def copy_diagram(self):
        QApplication.clipboard().setPixmap(self.grab())

    def save_diagram(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".svg":
            from PySide6.QtSvg import QSvgGenerator
            generator = QSvgGenerator()
            generator.setFileName(str(path))
            generator.setSize(QSize(max(self.width(), 800), max(self.height(), 240)))
            generator.setViewBox(QRect(0, 0, self.width(), self.height()))
            generator.setTitle("Equivalent circuit")
            painter = QPainter()
            if not painter.begin(generator):
                raise RuntimeError("Could not initialize SVG circuit export.")
            try:
                self.render(painter, QPoint())
            finally:
                painter.end()
        else:
            self.grab().save(str(path))

    def export_diagram(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export equivalent circuit", "equivalent_circuit.png",
            "PNG image (*.png);;SVG vector image (*.svg);;JPEG image (*.jpg *.jpeg)"
        )
        if not path:
            return
        path_obj = Path(path)
        if not path_obj.suffix:
            path_obj = path_obj.with_suffix(".svg" if "SVG" in selected_filter else ".png")
        self.save_diagram(path_obj)

    def _show_context_menu(self, position):
        menu = QMenu(self)
        copy_action = menu.addAction("Copy circuit image")
        export_action = menu.addAction("Export circuit image…")
        chosen = menu.exec(self.mapToGlobal(position))
        if chosen == copy_action:
            self.copy_diagram()
        elif chosen == export_action:
            self.export_diagram()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = get_palette(self.theme_name)
        painter.fillRect(self.rect(), QColor(palette.panel))
        painter.setPen(QPen(QColor(palette.plot_text), 2.1))
        y = self.height() / 2
        x = 24.0
        painter.drawLine(QPointF(7, y), QPointF(x, y))
        x = self._draw_series(painter, self.diagram, x, y)
        painter.drawLine(QPointF(x, y), QPointF(max(x + 16, self.width() - 7), y))

    def _draw_series(self, painter: QPainter, items, x: float, y: float) -> float:
        for index, item in enumerate(items):
            x = self._draw_item(painter, item, x, y)
            if index < len(items) - 1:
                painter.drawLine(QPointF(x, y), QPointF(x + 20, y))
                x += 20
        return x

    def _draw_item(self, painter: QPainter, item, x: float, y: float) -> float:
        if isinstance(item, tuple) and item:
            if item[0] == "element":
                width, _ = self._item_size(item)
                kind, label, params = self._element_info(item)
                self._draw_symbol(painter, kind, label, params, x, y, width)
                return x + width
            if item[0] == "series":
                return self._draw_series(painter, item[1:], x, y)
            if item[0] == "parallel":
                branches = item[1:]
                width, height = self._item_size(item)
                left = x + 12
                right = x + width - 12
                top = y - height / 2 + 10
                bottom = y + height / 2 - 10
                painter.drawLine(QPointF(x, y), QPointF(left, y))
                painter.drawLine(QPointF(left, top), QPointF(left, bottom))
                painter.drawLine(QPointF(right, top), QPointF(right, bottom))
                branch_heights = [max(self._item_size(branch)[1], 68.0) for branch in branches]
                cursor = top
                for branch, branch_height in zip(branches, branch_heights):
                    yy = cursor + branch_height / 2
                    cursor += branch_height
                    painter.drawLine(QPointF(left, yy), QPointF(left + 14, yy))
                    branch_x = left + 14
                    if isinstance(branch, tuple) and branch and branch[0] == "series":
                        branch_x = self._draw_series(painter, branch[1:], branch_x, yy)
                    else:
                        branch_x = self._draw_item(painter, branch, branch_x, yy)
                    painter.drawLine(QPointF(branch_x, yy), QPointF(right, yy))
                painter.drawLine(QPointF(right, y), QPointF(x + width, y))
                return x + width
        width = 100.0
        kind, label, params = self._element_info(item)
        self._draw_symbol(painter, kind, label, params, x, y, width)
        return x + width

    @staticmethod
    def _format_value(value: float) -> str:
        value = float(value)
        if value == 0:
            return "0"
        if abs(value) >= 1e4 or abs(value) < 1e-3:
            return f"{value:.3e}"
        return f"{value:.5g}"

    def _value_text(self, params: tuple[str, ...]) -> str:
        parts = []
        replacements = {"alpha": "α", "beta": "β", "sigma": "σ", "tau": "τ"}
        for name in params:
            if name not in self.values:
                continue
            short = name
            for prefix, symbol in replacements.items():
                if name.lower().startswith(prefix):
                    suffix = name[len(prefix):]
                    short = symbol + suffix
                    break
            unit = self.units.get(name, "")
            parts.append(f"{short}={self._format_value(self.values[name])}{(' ' + unit) if unit else ''}")
        text = "; ".join(parts)
        return text if len(text) <= 32 else text[:30] + "…"

    def _draw_symbol(self, painter: QPainter, kind: str, label: str, params: tuple[str, ...], x: float, y: float, width: float):
        label_font = QFont("Segoe UI", 9)
        label_font.setBold(True)
        painter.setFont(label_font)
        symbol_y = y - 2
        symbol_width = max(58.0, width - 12)
        sx = x + 6
        if kind == "R":
            points = [QPointF(sx, symbol_y)]
            steps = 8
            for i in range(1, steps):
                xx = sx + symbol_width * i / steps
                yy = symbol_y + (-8 if i % 2 else 8)
                points.append(QPointF(xx, yy))
            points.append(QPointF(sx + symbol_width, symbol_y))
            painter.drawPolyline(points)
        elif kind in {"C", "CPE"}:
            painter.drawLine(QPointF(sx, symbol_y), QPointF(sx + symbol_width * 0.42, symbol_y))
            painter.drawLine(QPointF(sx + symbol_width * 0.42, symbol_y - 12), QPointF(sx + symbol_width * 0.42, symbol_y + 12))
            painter.drawLine(QPointF(sx + symbol_width * 0.58, symbol_y - 12), QPointF(sx + symbol_width * 0.58, symbol_y + 12))
            painter.drawLine(QPointF(sx + symbol_width * 0.58, symbol_y), QPointF(sx + symbol_width, symbol_y))
        elif kind in {"W", "Wβ", "Wo", "Ws", "TLMo", "TLMs"}:
            painter.drawLine(QPointF(sx, symbol_y), QPointF(sx + symbol_width, symbol_y))
            count = max(4, int(symbol_width // 14))
            spacing = max(7.0, (symbol_width - 18) / max(count, 1))
            for i in range(count):
                xx = sx + 7 + i * spacing
                painter.drawLine(QPointF(xx, symbol_y - 8), QPointF(min(xx + 7, sx + symbol_width - 2), symbol_y + 8))
        elif kind == "G":
            painter.drawLine(QPointF(sx, symbol_y), QPointF(sx + symbol_width, symbol_y))
            painter.drawRect(int(sx + symbol_width * 0.25), int(symbol_y - 12), int(symbol_width * 0.50), 24)
            painter.drawText(QRect(int(sx + symbol_width * 0.25), int(symbol_y - 10), int(symbol_width * 0.50), 20), Qt.AlignCenter, "G")
        elif kind == "L":
            painter.drawLine(QPointF(sx, symbol_y), QPointF(sx + 8, symbol_y))
            coil_width = max(11, int((symbol_width - 16) / 4))
            for i in range(4):
                painter.drawArc(int(sx + 8 + i * coil_width), int(symbol_y - 8), coil_width + 2, 16, 0, 180 * 16)
            painter.drawLine(QPointF(sx + symbol_width - 8, symbol_y), QPointF(sx + symbol_width, symbol_y))
        else:
            painter.drawRect(int(sx + 5), int(symbol_y - 12), int(symbol_width - 10), 24)

        painter.drawText(QRect(int(x), int(y - 34), int(width), 18), Qt.AlignCenter, label)
        value_text = self._value_text(params)
        if value_text:
            value_font = QFont("Segoe UI", 7)
            painter.setFont(value_font)
            painter.drawText(QRect(int(x - 8), int(y + 18), int(width + 16), 30), Qt.AlignHCenter | Qt.AlignTop, value_text)


def numeric_item(value, precision=6):
    if value is None:
        text = ""
    else:
        try:
            text = f"{float(value):.{precision}g}"
        except Exception:
            text = str(value)
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item
