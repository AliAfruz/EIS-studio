"""Global DC-bias series fitting for custom equivalent circuits."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .io_utils import read_eis
from .models import custom_tree_params, evaluate_custom_tree
from .mott_schottky import potential_from_filename
from .theme import get_palette


@dataclass
class GlobalDCFitResult:
    potentials: np.ndarray
    parameter_values: dict[str, np.ndarray]
    z_fits: list[np.ndarray]
    rmse: np.ndarray
    success: bool
    message: str
    nfev: int

    def data_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame({"DC_potential_V": self.potentials, "RMSE_ohm": self.rmse})
        for name, values in self.parameter_values.items():
            frame[name] = values
        return frame


def _encode_value(value: float, pdef) -> float:
    value = min(max(float(value), pdef.low), pdef.high)
    if pdef.scale == "log" and pdef.low > 0:
        return float(np.log10(value))
    return value


def _decode_value(value: float, pdef) -> float:
    return float(10 ** value) if pdef.scale == "log" and pdef.low > 0 else float(value)


def global_fit_dc_series(
    tree: dict,
    studies: list[dict],
    initial_values: dict[str, float],
    modes: dict[str, str] | None = None,
    *,
    smooth_strength: float = .08,
    max_nfev: int = 3000,
) -> GlobalDCFitResult:
    """Fit multiple EIS spectra with shared/independent/smooth parameter modes."""
    if len(studies) < 2:
        raise ValueError("Global DC-series fitting requires at least two bias spectra.")
    normalized = []
    for index, study in enumerate(studies, 1):
        frequency = np.asarray(study.get("frequency"), dtype=float)
        impedance = np.asarray(study.get("impedance"), dtype=complex)
        potential = float(study.get("potential", np.nan))
        valid = np.isfinite(frequency) & (frequency > 0) & np.isfinite(impedance)
        if np.sum(valid) < 4 or not np.isfinite(potential):
            raise ValueError(f"Bias study {index} needs a finite potential and at least four EIS points.")
        normalized.append({
            **study,
            "frequency": frequency[valid],
            "impedance": impedance[valid],
            "potential": potential,
        })
    normalized.sort(key=lambda study: study["potential"])
    definitions = list(custom_tree_params(tree))
    if not definitions:
        raise ValueError("The circuit has no parameters to fit.")
    modes = {str(name): str(mode).lower() for name, mode in (modes or {}).items()}
    count = len(normalized)
    slots = []
    x0, lower, upper = [], [], []
    slot_index = {}
    for pdef in definitions:
        mode = modes.get(pdef.name, "shared")
        if mode not in {"shared", "independent", "smooth"}:
            mode = "shared"
        modes[pdef.name] = mode
        repeats = 1 if mode == "shared" else count
        start = _encode_value(
            initial_values.get(pdef.name, np.sqrt(pdef.low * pdef.high) if pdef.low > 0 else (pdef.low + pdef.high) / 2),
            pdef,
        )
        lo, hi = _encode_value(pdef.low, pdef), _encode_value(pdef.high, pdef)
        for study_index in range(repeats):
            key = (pdef.name, None if mode == "shared" else study_index)
            slot_index[key] = len(slots)
            slots.append((pdef, mode, study_index))
            x0.append(start)
            lower.append(lo)
            upper.append(hi)

    def decode(vector):
        output = [dict() for _ in range(count)]
        transformed = {}
        for pdef in definitions:
            mode = modes.get(pdef.name, "shared")
            if mode == "shared":
                encoded = float(vector[slot_index[(pdef.name, None)]])
                values = np.full(count, _decode_value(encoded, pdef))
                encoded_values = np.full(count, encoded)
            else:
                encoded_values = np.array([
                    float(vector[slot_index[(pdef.name, study_index)]])
                    for study_index in range(count)
                ])
                values = np.array([_decode_value(value, pdef) for value in encoded_values])
            transformed[pdef.name] = encoded_values
            for study_index, value in enumerate(values):
                output[study_index][pdef.name] = float(value)
        return output, transformed

    def residual(vector):
        parameter_sets, transformed = decode(vector)
        chunks = []
        for study, values in zip(normalized, parameter_sets):
            z_fit = evaluate_custom_tree(tree, study["frequency"], values)
            scale = np.maximum(np.abs(study["impedance"]), np.median(np.abs(study["impedance"])) * 1e-6 + 1e-30)
            difference = (z_fit - study["impedance"]) / scale
            chunks.extend((difference.real, difference.imag))
        for pdef in definitions:
            if modes.get(pdef.name, "shared") != "smooth":
                continue
            sequence = transformed[pdef.name]
            span = max(float(_encode_value(pdef.high, pdef) - _encode_value(pdef.low, pdef)), 1e-30)
            if len(sequence) >= 3:
                penalty = np.diff(sequence, 2) / span
            else:
                penalty = np.diff(sequence) / span
            chunks.append(np.sqrt(max(smooth_strength, 0.0)) * penalty)
        return np.concatenate([np.ravel(chunk) for chunk in chunks])

    result = least_squares(
        residual,
        np.asarray(x0, dtype=float),
        bounds=(np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)),
        loss="soft_l1",
        max_nfev=max(100, int(max_nfev)),
        x_scale="jac",
    )
    parameter_sets, _ = decode(result.x)
    z_fits, rmse = [], []
    for study, values in zip(normalized, parameter_sets):
        z_fit = evaluate_custom_tree(tree, study["frequency"], values)
        z_fits.append(z_fit)
        rmse.append(float(np.sqrt(np.mean(np.abs(z_fit - study["impedance"]) ** 2))))
    parameter_values = {
        pdef.name: np.array([values[pdef.name] for values in parameter_sets], dtype=float)
        for pdef in definitions
    }
    return GlobalDCFitResult(
        potentials=np.array([study["potential"] for study in normalized], dtype=float),
        parameter_values=parameter_values,
        z_fits=z_fits,
        rmse=np.asarray(rmse, dtype=float),
        success=bool(result.success),
        message=str(result.message),
        nfev=int(result.nfev),
    )


class ParameterTrendPlot(QWidget):
    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.x = np.array([])
        self.y = np.array([])
        self.label = "Parameter"
        self.setMinimumHeight(180)

    def set_series(self, x, y, label: str):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.label = str(label)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = get_palette(self.theme_name)
        painter.fillRect(self.rect(), QColor(palette.plot_bg))
        rect = QRectF(45, 22, self.width() - 62, self.height() - 50)
        painter.setPen(QPen(QColor(palette.grid), 1))
        painter.drawRect(rect)
        if not len(self.x):
            painter.setPen(QColor(palette.muted_text))
            painter.drawText(self.rect(), Qt.AlignCenter, "Run global fit to view parameter trends")
            return
        xmin, xmax = float(np.min(self.x)), float(np.max(self.x))
        ymin, ymax = float(np.min(self.y)), float(np.max(self.y))
        if xmin == xmax:
            xmin -= .1; xmax += .1
        if ymin == ymax:
            span = max(abs(ymin), 1.0) * .1
            ymin -= span; ymax += span
        points = [
            QPointF(
                rect.left() + (xx - xmin) / (xmax - xmin) * rect.width(),
                rect.bottom() - (yy - ymin) / (ymax - ymin) * rect.height(),
            )
            for xx, yy in zip(self.x, self.y)
        ]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor(palette.fit), 2.1))
        painter.drawPath(path)
        painter.setBrush(QColor(palette.accent))
        painter.setPen(QPen(QColor(palette.accent), 1))
        for point in points:
            painter.drawEllipse(point, 3.5, 3.5)
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(palette.text))
        painter.drawText(QRectF(rect.left(), 1, rect.width(), 18), Qt.AlignCenter, self.label)
        painter.setPen(QColor(palette.muted_text))
        painter.drawText(QRectF(rect.left(), rect.bottom() + 5, rect.width(), 17), Qt.AlignCenter, "DC potential / V")


class DCSeriesGlobalDialog(QDialog):
    """GUI for preparing and globally fitting potential-dependent EIS spectra."""

    def __init__(self, tree: dict, values: dict[str, float], theme_name="dark", studies=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DC-series global circuit laboratory")
        self.resize(1050, 720)
        self.tree = tree
        self.base_values = dict(values)
        self.theme_name = theme_name
        self.studies = list(studies or [])
        self.result: GlobalDCFitResult | None = None
        self.mode_combos: dict[str, QComboBox] = {}
        self.result_values: dict[str, float] | None = None
        self._build_ui()
        self._refresh_studies()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("GLOBAL DC-BIAS FIT")
        title.setObjectName("builderTitle")
        note = QLabel(
            "Fit one validated circuit to multiple bias spectra. Shared parameters use one value; "
            "independent parameters vary freely; smooth parameters vary with a regularized potential trend."
        )
        note.setWordWrap(True)
        note.setObjectName("builderHelp")
        layout.addWidget(title)
        layout.addWidget(note)

        body = QHBoxLayout()
        left = QVBoxLayout()
        file_row = QHBoxLayout()
        add_button = QPushButton("Add DC-bias EIS files…")
        remove_button = QPushButton("Remove selected")
        add_button.clicked.connect(self._add_files)
        remove_button.clicked.connect(self._remove_selected)
        file_row.addWidget(add_button); file_row.addWidget(remove_button)
        left.addLayout(file_row)
        self.study_table = QTableWidget(0, 3)
        self.study_table.setHorizontalHeaderLabels(["DC potential / V", "Points", "Source"])
        self.study_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.study_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        left.addWidget(self.study_table, 1)

        self.mode_table = QTableWidget(0, 3)
        self.mode_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Meaning"])
        self.mode_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        definitions = list(custom_tree_params(self.tree))
        self.mode_table.setRowCount(len(definitions))
        for row, pdef in enumerate(definitions):
            name_item = QTableWidgetItem(pdef.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            combo = QComboBox()
            combo.addItem("Shared", "shared")
            combo.addItem("Independent", "independent")
            combo.addItem("Smooth vs DC", "smooth")
            meaning = QTableWidgetItem("One value across every potential")
            meaning.setFlags(meaning.flags() & ~Qt.ItemIsEditable)
            combo.currentIndexChanged.connect(
                lambda _, c=combo, item=meaning: item.setText({
                    "shared": "One value across every potential",
                    "independent": "Separate value at every potential",
                    "smooth": "Separate values with smoothness regularization",
                }[str(c.currentData())])
            )
            self.mode_table.setItem(row, 0, name_item)
            self.mode_table.setCellWidget(row, 1, combo)
            self.mode_table.setItem(row, 2, meaning)
            self.mode_combos[pdef.name] = combo
        left.addWidget(self.mode_table, 1)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        run_button = QPushButton("Run global fit")
        run_button.setObjectName("primaryButton")
        run_button.clicked.connect(self._run_fit)
        right.addWidget(run_button)
        self.status_label = QLabel("Add at least two DC-bias spectra.")
        self.status_label.setWordWrap(True)
        right.addWidget(self.status_label)
        self.parameter_combo = QComboBox()
        self.parameter_combo.addItems([p.name for p in definitions])
        self.parameter_combo.currentTextChanged.connect(self._update_trend)
        right.addWidget(self.parameter_combo)
        self.trend_plot = ParameterTrendPlot(self.theme_name)
        right.addWidget(self.trend_plot)
        self.result_table = QTableWidget(0, 0)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right.addWidget(self.result_table, 1)
        export_button = QPushButton("Export global-fit table…")
        export_button.clicked.connect(self._export)
        right.addWidget(export_button)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Close")
        use_values = QPushButton("Use shared / median values")
        use_values.setObjectName("primaryButton")
        cancel.clicked.connect(self.reject)
        use_values.clicked.connect(self._accept_values)
        buttons.addWidget(cancel); buttons.addWidget(use_values)
        layout.addLayout(buttons)

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add DC-bias EIS files", "",
            "EIS data (*.csv *.txt *.tsv *.dat *.asc *.dta *.xlsx *.xls);;All files (*)",
        )
        for path in paths:
            try:
                data = read_eis(path)
                frequency = data["frequency_Hz"].to_numpy(float)
                impedance = data["Zreal_ohm"].to_numpy(float) + 1j * data["Zimag_ohm"].to_numpy(float)
                potential_values = (
                    data["potential_V"].dropna().to_numpy(float)
                    if "potential_V" in data.columns else np.array([])
                )
                potential = (
                    float(np.median(potential_values)) if len(potential_values)
                    and float(np.ptp(potential_values)) <= .005
                    else potential_from_filename(path)
                )
                self.studies.append({
                    "potential": float(potential) if potential is not None else np.nan,
                    "frequency": frequency,
                    "impedance": impedance,
                    "source": str(path),
                })
            except Exception as exc:
                QMessageBox.warning(self, "DC-series import", f"{path}\n{exc}")
        self._refresh_studies()

    def _refresh_studies(self):
        self.study_table.setRowCount(len(self.studies))
        for row, study in enumerate(self.studies):
            self.study_table.setItem(row, 0, QTableWidgetItem(f"{float(study.get('potential', np.nan)):.10g}"))
            points = QTableWidgetItem(str(len(study.get("frequency", []))))
            points.setFlags(points.flags() & ~Qt.ItemIsEditable)
            source = QTableWidgetItem(str(study.get("source", f"Study {row + 1}")))
            source.setFlags(source.flags() & ~Qt.ItemIsEditable)
            self.study_table.setItem(row, 1, points)
            self.study_table.setItem(row, 2, source)

    def _sync_potentials(self):
        for row, study in enumerate(self.studies):
            item = self.study_table.item(row, 0)
            study["potential"] = float(item.text()) if item else np.nan

    def _remove_selected(self):
        rows = sorted({index.row() for index in self.study_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.studies.pop(row)
        self._refresh_studies()

    def _run_fit(self):
        try:
            self._sync_potentials()
            modes = {name: str(combo.currentData()) for name, combo in self.mode_combos.items()}
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.result = global_fit_dc_series(
                    self.tree, self.studies, self.base_values, modes
                )
            finally:
                QApplication.restoreOverrideCursor()
            frame = self.result.data_frame()
            self.result_table.setRowCount(len(frame))
            self.result_table.setColumnCount(len(frame.columns))
            self.result_table.setHorizontalHeaderLabels([str(column) for column in frame.columns])
            for row, (_, values) in enumerate(frame.iterrows()):
                for column, value in enumerate(values):
                    self.result_table.setItem(row, column, QTableWidgetItem(f"{float(value):.8g}"))
            self.result_table.resizeColumnsToContents()
            self.status_label.setText(
                f"{'Converged' if self.result.success else 'Stopped'} • {self.result.nfev} evaluations • "
                f"mean RMSE {float(np.mean(self.result.rmse)):.4g} Ω\n{self.result.message}"
            )
            self._update_trend()
        except Exception as exc:
            QMessageBox.critical(self, "Global DC-series fit", str(exc))

    def _update_trend(self):
        if self.result is None:
            return
        name = self.parameter_combo.currentText()
        if name in self.result.parameter_values:
            self.trend_plot.set_series(
                self.result.potentials, self.result.parameter_values[name], f"{name} versus DC potential"
            )

    def _accept_values(self):
        if self.result is None:
            QMessageBox.information(self, "Global DC-series fit", "Run the global fit first.")
            return
        self.result_values = {
            name: float(values[0]) if np.allclose(values, values[0], rtol=1e-9, atol=0)
            else float(np.median(values))
            for name, values in self.result.parameter_values.items()
        }
        self.accept()

    def _export(self):
        if self.result is None:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "Export global DC-series fit", "dc_global_fit.xlsx",
            "Excel workbook (*.xlsx);;CSV table (*.csv);;TSV table (*.tsv)",
        )
        if not path:
            return
        frame = self.result.data_frame()
        suffix = Path(path).suffix.lower()
        if suffix == ".csv":
            frame.to_csv(path, index=False)
        elif suffix in {".tsv", ".txt"}:
            frame.to_csv(path, index=False, sep="\t")
        else:
            if not suffix:
                path = str(Path(path).with_suffix(".xlsx"))
            frame.to_excel(path, index=False)
