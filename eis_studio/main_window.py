from __future__ import annotations

import sys
from pathlib import Path
import traceback
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QPushButton, QLabel, QComboBox, QCheckBox, QLineEdit, QTabWidget,
    QHeaderView, QSplitter, QScrollArea, QPlainTextEdit, QProgressBar, QListWidget,
    QAbstractItemView, QDialog, QDialogButtonBox, QInputDialog, QTableWidgetItem
)

from .theme import get_stylesheet, get_palette
from .widgets import (
    PlotPanel, CircuitDiagram, CopyableTableWidget, NoWheelSpinBox,
    NoWheelDoubleSpinBox, ScientificDoubleSpinBox, WheelChangeBlocker,
    ManualParameterEditor, numeric_item
)
from .models import CIRCUITS, evaluate
from .fitting import (
    FitSettings, fit_model, auto_fit, calibration, initial_guess_values,
    effective_capacitance_from_fit,
)
from .diagnostics import consistency_checks, drt_tikhonov, diffusion_signature
from .io_utils import read_eis, save_fit_workbook, extract_concentration, import_audit_text
from .circuit_builder import CircuitBuilderDialog
from .paired_batch import PairedAnalysisBundle, analyze_st_folder
from .mott_schottky import (
    available_capacitance_methods,
    calculate_mott_schottky,
    extract_mott_schottky_from_eis,
    extract_mott_schottky_study,
    potential_from_filename,
    prepare_mott_schottky_from_batch_results,
    read_eis_potential_series,
    read_mott_schottky,
)
from .cinematic import (
    CinematicBackdrop,
    OrbitalEISMark,
    PageFadeController,
    apply_glass_shadow,
)


def resource_path(*parts: str) -> Path:
    """Return a source-tree, installed-package, or PyInstaller resource path."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).joinpath(*parts)
    source_tree_path = Path(__file__).resolve().parent.parent.joinpath(*parts)
    if source_tree_path.exists():
        return source_tree_path
    return Path(__file__).resolve().parent.joinpath(*parts)


def application_icon() -> QIcon:
    """Load the user-supplied app artwork (assets/1.png)."""
    png_path = resource_path("assets", "1.png")
    ico_path = resource_path("assets", "eis_gold_studio.ico")
    icon = QIcon(str(png_path)) if png_path.exists() else QIcon(str(ico_path))
    return icon


class BatchWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, files, model_key, auto, settings, parent=None):
        super().__init__(parent)
        self.files = files; self.model_key = model_key; self.auto = auto; self.settings = settings

    def run(self):
        rows = []
        try:
            for i, file in enumerate(self.files, 1):
                self.progress.emit(int((i-1) / max(len(self.files), 1) * 100), Path(file).name)
                data = read_eis(file)
                f = data["frequency_Hz"].to_numpy()
                z = data["Zreal_ohm"].to_numpy() + 1j * data["Zimag_ohm"].to_numpy()
                result = auto_fit(f, z, settings=self.settings)[0] if self.auto else fit_model(f, z, self.model_key, self.settings)
                row = {"file": str(file), **result.summary_row()}
                value, unit = extract_concentration(Path(file).stem)
                row["concentration"] = value; row["concentration_unit"] = unit
                embedded = (
                    data["potential_V"].dropna().to_numpy(float)
                    if "potential_V" in data.columns else np.array([], dtype=float)
                )
                if embedded.size and float(np.ptp(embedded)) <= 0.005:
                    row["DC_potential_V"] = float(np.median(embedded))
                    row["DC_potential_source"] = "embedded EIS column"
                else:
                    potential = potential_from_filename(file)
                    row["DC_potential_V"] = (
                        potential if potential is not None else np.nan
                    )
                    row["DC_potential_source"] = (
                        "filename" if potential is not None
                        else (
                            "multiple embedded steps — use Mott-Schottky workflow"
                            if embedded.size else "missing — enter in Batch results"
                        )
                    )
                row.update(effective_capacitance_from_fit(result))
                rows.append(row)
            self.progress.emit(100, "Complete")
            self.completed.emit(pd.DataFrame(rows))
        except Exception:
            self.failed.emit(traceback.format_exc())


class AutoFitWorker(QThread):
    """Run advanced auto-fit away from the GUI thread with per-model progress."""

    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, f, z, keys, settings, parent=None):
        super().__init__(parent)
        self.f = np.asarray(f, dtype=float).copy()
        self.z = np.asarray(z, dtype=complex).copy()
        self.keys = list(keys)
        self.settings = settings

    def run(self):
        try:
            ranking = auto_fit(
                self.f, self.z, self.keys, self.settings,
                progress=lambda percent, name: self.progress.emit(percent, name),
            )
            self.progress.emit(100, "Advanced auto-fit complete")
            self.completed.emit(ranking)
        except Exception:
            self.failed.emit(traceback.format_exc())


class PairedSTWorker(QThread):
    """Sequential ST A/B analysis with automatic detailed TXT reporting."""

    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self, input_folder, output_folder, model_key, auto, settings,
        rct_safe_auto=True, parent=None,
    ):
        super().__init__(parent)
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.model_key = model_key
        self.auto = auto
        self.settings = settings
        self.rct_safe_auto = rct_safe_auto

    def run(self):
        try:
            bundle = analyze_st_folder(
                self.input_folder,
                self.output_folder,
                settings=self.settings,
                auto_select=self.auto,
                model_key=self.model_key,
                rct_safe_auto=self.rct_safe_auto,
                progress=lambda percent, name: self.progress.emit(percent, name),
            )
            self.completed.emit(bundle)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self, theme_name: str = "dark", motion_enabled: bool = True):
        super().__init__()
        self.theme_name = theme_name if theme_name in {"light", "dark"} else "light"
        self._motion_enabled = bool(motion_enabled)
        self.setWindowTitle("EIS Gold Studio — Advanced Analysis & Fitting")
        self.setWindowIcon(application_icon())
        self.resize(1500, 920)
        self.data: pd.DataFrame | None = None
        self.current_file: Path | None = None
        self.fit_result = None
        self.ranking: list = []
        self.batch_df: pd.DataFrame | None = None
        self.paired_rct_df: pd.DataFrame | None = None
        self.paired_output_dir: Path | None = None
        self.drt_df: pd.DataFrame | None = None
        self.drt_reconstruction_df: pd.DataFrame | None = None
        self.calibration_df: pd.DataFrame | None = None
        self.calibration_stats: dict | None = None
        self.ms_data: pd.DataFrame | None = None
        self.ms_result_df: pd.DataFrame | None = None
        self.ms_stats: dict[str, object] | None = None
        self.ms_source_files: list[Path] = []
        self._last_ms_dc_potential_V = 0.0
        self._updating_ms_file_table = False
        self.worker = None
        self.paired_worker = None
        self.autofit_worker = None
        self._busy_operation: str | None = None
        self.manual_preview_z: np.ndarray | None = None
        self._manual_cache: dict[str, tuple[dict[str, float], set[str]]] = {}
        self._manual_model_key: str | None = None
        self._build_ui()
        self._connect()
        self.setAcceptDrops(True)
        self.set_theme(self.theme_name, persist=False)
        self.set_motion_enabled(self._motion_enabled, persist=False)
        self._update_circuit_info()
        self._update_action_states()
        self.statusBar().showMessage("Ready — import an EIS file to begin")

    def _build_ui(self):
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.open_action = QAction("Open", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_file)
        self.fit_action = QAction("Fit", self)
        self.fit_action.setShortcut("Ctrl+Return")
        self.fit_action.triggered.connect(self.run_fit)
        self.auto_fit_action = QAction("Auto-fit", self)
        self.auto_fit_action.triggered.connect(self.run_auto_fit)
        self.export_all_action = QAction("Export all", self)
        self.export_all_action.triggered.connect(self.export_analysis_package)
        self.reset_action = QAction("Reset plot", self)
        self.reset_action.triggered.connect(self.reset_view)
        for action in (
            self.open_action, self.fit_action, self.auto_fit_action,
            self.export_all_action, self.reset_action,
        ):
            toolbar.addAction(action)
        self.builder_action = QAction("Circuit composer", self)
        self.builder_action.setShortcut("Ctrl+B")
        self.builder_action.setStatusTip("Draw and fit a custom symbol-based electrical schematic")
        self.builder_action.triggered.connect(self.open_circuit_builder)
        toolbar.addAction(self.builder_action)
        circuit_menu = self.menuBar().addMenu("&Circuit")
        circuit_menu.addAction(self.builder_action)
        toolbar.addSeparator()
        self.dark_mode_action = QAction("Dark mode", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(self.theme_name == "dark")
        self.dark_mode_action.setShortcut("Ctrl+D")
        self.dark_mode_action.setStatusTip("Switch between pale-gold light mode and gold-accented dark mode")
        toolbar.addAction(self.dark_mode_action)
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.dark_mode_action)
        self.motion_action = QAction("Cinematic motion", self)
        self.motion_action.setCheckable(True)
        self.motion_action.setChecked(self._motion_enabled)
        self.motion_action.setShortcut("Ctrl+M")
        self.motion_action.setStatusTip("Animate ambient light volumes, particles, and page transitions")
        toolbar.addAction(self.motion_action)
        view_menu.addAction(self.motion_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("About EIS Gold Studio", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        self.signature_label = QLabel(
            'Developed by <a href="https://www.linkedin.com/in/ali-afruz/">A. Afruz</a>'
            ' &nbsp;·&nbsp; <a href="mailto:a.a.afruz@gmail.com">Email</a>'
            ' &nbsp;·&nbsp; <a href="https://www.linkedin.com/in/ali-afruz/">LinkedIn</a>'
        )
        self.signature_label.setTextFormat(Qt.RichText)
        self.signature_label.setOpenExternalLinks(True)
        self.signature_label.setToolTip(
            "A. Afruz | a.a.afruz@gmail.com | linkedin.com/in/ali-afruz"
        )
        self.statusBar().addPermanentWidget(self.signature_label)

        export_menu = self.menuBar().addMenu("&Export")
        self.export_workbook_action = QAction("Fit workbook…", self)
        self.export_workbook_action.triggered.connect(self.export_fit)
        self.export_package_action = QAction("Complete analysis package…", self)
        self.export_package_action.setShortcut("Ctrl+Shift+E")
        self.export_package_action.triggered.connect(self.export_analysis_package)
        self.export_plot_action = QAction("Current plot image…", self)
        self.export_plot_action.triggered.connect(self.export_current_plot)
        self.export_plot_data_action = QAction("Current plot data…", self)
        self.export_plot_data_action.triggered.connect(self.export_current_plot_data)
        self.export_circuit_action = QAction("Equivalent circuit image…", self)
        self.export_circuit_action.triggered.connect(lambda: self.circuit_diagram.export_diagram())
        self.export_log_action = QAction("Diagnostics log…", self)
        self.export_log_action.triggered.connect(self.export_log)
        export_menu.addAction(self.export_workbook_action)
        export_menu.addAction(self.export_package_action)
        export_menu.addSeparator()
        export_menu.addAction(self.export_plot_action)
        export_menu.addAction(self.export_plot_data_action)
        export_menu.addAction(self.export_circuit_action)
        export_menu.addSeparator()
        export_menu.addAction(self.export_log_action)

        self.cinematic_backdrop = CinematicBackdrop(self.theme_name)
        self.setCentralWidget(self.cinematic_backdrop)
        root = QVBoxLayout(self.cinematic_backdrop); root.setContentsMargins(12, 10, 12, 12); root.setSpacing(10)

        self.hero_panel = QWidget()
        self.hero_panel.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(self.hero_panel)
        hero_layout.setContentsMargins(16, 9, 16, 9)
        hero_layout.setSpacing(12)
        self.orbital_mark = OrbitalEISMark(self.theme_name)
        hero_layout.addWidget(self.orbital_mark)
        hero_copy = QWidget(); hero_copy.setObjectName("heroCopy")
        hero_copy_layout = QVBoxLayout(hero_copy); hero_copy_layout.setContentsMargins(0, 0, 0, 0); hero_copy_layout.setSpacing(1)
        hero_title = QLabel("EIS GOLD STUDIO")
        hero_title.setObjectName("heroTitle")
        hero_subtitle = QLabel("Cinematic electrochemical intelligence workspace")
        hero_subtitle.setObjectName("heroSubtitle")
        hero_copy_layout.addWidget(hero_title); hero_copy_layout.addWidget(hero_subtitle)
        hero_layout.addWidget(hero_copy)
        hero_layout.addStretch(1)
        hero_mode = QLabel("IMPEDANCE LAB")
        hero_mode.setObjectName("heroModeBadge")
        self.hero_status = QLabel("READY")
        self.hero_status.setObjectName("heroStatus")
        self.hero_status.setProperty("state", "ready")
        hero_layout.addWidget(hero_mode)
        hero_layout.addWidget(self.hero_status)
        root.addWidget(self.hero_panel)

        split = QSplitter(Qt.Horizontal); split.setObjectName("workspaceSplitter"); root.addWidget(split, 1)

        self.workflow_tabs = QTabWidget()
        self.workflow_tabs.setObjectName("workflowTabs")
        self.workflow_tabs.setMinimumWidth(380)

        def workflow_page(title: str):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setAlignment(Qt.AlignTop)
            layout.setContentsMargins(6, 6, 6, 6)
            scroll.setWidget(page)
            self.workflow_tabs.addTab(scroll, title)
            return scroll, layout

        self.data_workflow_page, data_layout = workflow_page("Data")
        self.fit_workflow_page, fit_layout = workflow_page("Fit")
        self.circuit_workflow_page, circuit_layout = workflow_page("Circuit")
        self.diagnostics_workflow_page, diagnostics_layout = workflow_page("Diagnostics")
        self.batch_workflow_page, batch_layout = workflow_page("Batch")
        self.ms_workflow_page, ms_layout = workflow_page("Mott-Schottky")

        data_group = QGroupBox("Import EIS data")
        dg = QGridLayout(data_group)
        self.open_btn = QPushButton("Open EIS data")
        self.open_btn.setObjectName("primaryButton")
        self.file_label = QLabel("No file loaded"); self.file_label.setWordWrap(True)
        self.file_label.setObjectName("fileSummary")
        self.sign_flip = QCheckBox("Invert imaginary sign")
        self.delimiter_combo = QComboBox()
        for label, value in (
            ("Auto-detect", "auto"),
            ("Space / whitespace", "space"),
            ("Tab", "tab"),
            ("Comma (,)", "comma"),
            ("Semicolon (;)", "semicolon"),
            ("Colon (:)", "colon"),
        ):
            self.delimiter_combo.addItem(label, value)
        self.delimiter_combo.setToolTip(
            "Delimiter used by ASCII TXT/CSV/TSV files. Auto-detect is recommended; "
            "choose a delimiter manually when an unusual export is ambiguous."
        )
        self.decimal_combo = QComboBox()
        for label, value in (
            ("Auto-detect", "auto"),
            ("Dot (.)", "dot"),
            ("Comma (,)", "comma"),
        ):
            self.decimal_combo.addItem(label, value)
        self.decimal_combo.setToolTip(
            "Decimal separator used inside numerical values. Decimal comma is commonly "
            "combined with semicolon, tab, space, or colon column delimiters."
        )
        dg.addWidget(self.open_btn, 0, 0, 1, 2)
        dg.addWidget(self.file_label, 1, 0, 1, 2)
        dg.addWidget(QLabel("Column delimiter"), 2, 0); dg.addWidget(self.delimiter_combo, 2, 1)
        dg.addWidget(QLabel("Decimal separator"), 3, 0); dg.addWidget(self.decimal_combo, 3, 1)
        dg.addWidget(self.sign_flip, 4, 0, 1, 2)
        drop_hint = QLabel("Tip: you can also drag and drop a supported EIS file anywhere on this window.")
        drop_hint.setObjectName("helpText"); drop_hint.setWordWrap(True)
        dg.addWidget(drop_hint, 5, 0, 1, 2)
        data_layout.addWidget(data_group)
        data_layout.addStretch(1)

        fit_group = QGroupBox("Equivalent-circuit fitting")
        fg = QGridLayout(fit_group)
        self.model_combo = QComboBox()
        for k, spec in CIRCUITS.items(): self.model_combo.addItem(spec.name, k)
        self.weight_combo = QComboBox(); self.weight_combo.addItems(["modulus", "unit", "proportional"])
        self.loss_combo = QComboBox(); self.loss_combo.addItems(["soft_l1", "linear", "huber", "cauchy", "arctan"])
        self.optimizer_combo = QComboBox()
        self.optimizer_combo.addItem("Hybrid global + bounded LS", "hybrid")
        self.optimizer_combo.addItem("Bounded LS multistart only", "least_squares")
        self.optimizer_combo.setToolTip("Hybrid mode uses differential evolution for a global search, then bounded least-squares refinement.")
        self.nfev_spin = NoWheelSpinBox(); self.nfev_spin.setRange(500, 100000); self.nfev_spin.setValue(8000); self.nfev_spin.setSingleStep(500)
        self.multistart_spin = NoWheelSpinBox(); self.multistart_spin.setRange(1, 30); self.multistart_spin.setValue(8)
        self.fit_btn = QPushButton("Fit model")
        self.fit_btn.setObjectName("primaryButton")
        self.auto_btn = QPushButton("Compare models (auto-fit)")
        self.auto_btn.setObjectName("secondaryButton")
        self.all_models_check = QCheckBox("Include high-complexity diffusion/TLM models"); self.all_models_check.setChecked(True)
        fg.addWidget(QLabel("Model"), 0, 0); fg.addWidget(self.model_combo, 0, 1)

        self.advanced_toggle = QPushButton("Advanced fitting settings  ▸")
        self.advanced_toggle.setObjectName("quietButton")
        self.advanced_toggle.setCheckable(True)
        self.advanced_settings = QWidget()
        advanced_grid = QGridLayout(self.advanced_settings)
        advanced_grid.setContentsMargins(0, 2, 0, 2)
        advanced_labels = [
            ("Weighting", self.weight_combo), ("Robust loss", self.loss_combo),
            ("Optimizer", self.optimizer_combo), ("Maximum evaluations", self.nfev_spin),
            ("Multi-starts", self.multistart_spin),
        ]
        for row, (label, widget) in enumerate(advanced_labels):
            advanced_grid.addWidget(QLabel(label), row, 0)
            advanced_grid.addWidget(widget, row, 1)
        advanced_grid.addWidget(self.all_models_check, len(advanced_labels), 0, 1, 2)
        self.advanced_settings.setVisible(False)
        fg.addWidget(self.advanced_toggle, 1, 0, 1, 2)
        fg.addWidget(self.advanced_settings, 2, 0, 1, 2)
        self.autofit_progress = QProgressBar(); self.autofit_progress.setValue(0)
        self.autofit_progress.setFormat("Advanced auto-fit: %p%")
        self.autofit_progress.setToolTip("Shows model-by-model progress while the advanced auto-fit runs in the background.")
        self.autofit_progress.setVisible(False)
        fg.addWidget(self.fit_btn, 3, 0, 1, 2)
        fg.addWidget(self.auto_btn, 4, 0, 1, 2)
        fg.addWidget(self.autofit_progress, 5, 0, 1, 2)
        chi_info = QLabel("χ²red uses dimensionless Z-modulus normalization (N − k degrees of freedom).")
        chi_info.setObjectName("helpText"); chi_info.setWordWrap(True)
        chi_info.setToolTip(
            "Formula: Σ[(ΔZ′² + ΔZ″²)/|Z|²] / (N − k). "
            "This is scale-independent and comparable to EIS software using the same Zmod convention. "
            "Exact values can differ when another program uses different weights or degrees of freedom."
        )
        fg.addWidget(chi_info, 6, 0, 1, 2)
        fit_layout.addWidget(fit_group)

        circuit_group = QGroupBox("Circuit visualization and wiring")
        cg = QVBoxLayout(circuit_group)
        self.circuit_diagram = CircuitDiagram(theme_name=self.theme_name)
        self.circuit_scroll = QScrollArea(); self.circuit_scroll.setWidgetResizable(False); self.circuit_scroll.setMinimumHeight(250)
        self.circuit_scroll.setWidget(self.circuit_diagram)
        self.circuit_label = QLabel(); self.circuit_label.setWordWrap(True)
        self.builder_btn = QPushButton("Open live circuit laboratory…")
        self.builder_btn.setObjectName("primaryButton")
        self.builder_btn.setToolTip("Draw a custom circuit with real symbols and live wires. Shortcut: Ctrl+B")
        cg.addWidget(self.circuit_scroll); cg.addWidget(self.circuit_label); cg.addWidget(self.builder_btn)
        circuit_layout.addWidget(circuit_group)
        circuit_layout.addStretch(1)

        manual_group = QGroupBox("Manual element values and locks")
        mg = QVBoxLayout(manual_group)
        manual_info = QLabel(
            "Edit each value directly. Values are used as starting guesses; checked Lock boxes keep selected parameters fixed during fitting."
        )
        manual_info.setWordWrap(True)
        self.manual_editor = ManualParameterEditor()
        self.manual_start_check = QCheckBox("Use displayed values as fitting starts")
        self.manual_start_check.setChecked(True)
        manual_buttons = QGridLayout()
        self.estimate_values_btn = QPushButton("Estimate from data")
        self.fitted_values_btn = QPushButton("Use fitted values")
        self.preview_values_btn = QPushButton("Preview manual curve")
        self.clear_preview_btn = QPushButton("Clear preview")
        self.clear_preview_btn.setObjectName("quietButton")
        manual_buttons.addWidget(self.estimate_values_btn, 0, 0); manual_buttons.addWidget(self.fitted_values_btn, 0, 1)
        manual_buttons.addWidget(self.preview_values_btn, 1, 0); manual_buttons.addWidget(self.clear_preview_btn, 1, 1)
        mg.addWidget(manual_info); mg.addWidget(self.manual_editor); mg.addWidget(self.manual_start_check); mg.addLayout(manual_buttons)
        fit_layout.addWidget(manual_group)
        fit_layout.addStretch(1)

        drt_group = QGroupBox("DRT and consistency")
        drg = QGridLayout(drt_group)
        self.drt_lambda = NoWheelDoubleSpinBox(); self.drt_lambda.setDecimals(6); self.drt_lambda.setRange(1e-6, 100); self.drt_lambda.setValue(0.01); self.drt_lambda.setSingleStep(0.005)
        self.drt_points = NoWheelSpinBox(); self.drt_points.setRange(30, 300); self.drt_points.setValue(90)
        self.drt_btn = QPushButton("Calculate DRT")
        self.drt_btn.setObjectName("primaryButton")
        self.check_btn = QPushButton("Run consistency checks")
        drg.addWidget(QLabel("Regularization λ"),0,0); drg.addWidget(self.drt_lambda,0,1)
        drg.addWidget(QLabel("τ grid points"),1,0); drg.addWidget(self.drt_points,1,1)
        drg.addWidget(self.drt_btn,2,0,1,2); drg.addWidget(self.check_btn,3,0,1,2)
        diagnostics_note = QLabel(
            "Use these screening tools after importing data. Review DRT reconstruction error "
            "and consistency messages before drawing mechanistic conclusions."
        )
        diagnostics_note.setObjectName("helpText"); diagnostics_note.setWordWrap(True)
        diagnostics_layout.addWidget(diagnostics_note)
        diagnostics_layout.addWidget(drt_group)
        diagnostics_layout.addStretch(1)

        batch_group = QGroupBox("Batch folder analysis")
        bg = QGridLayout(batch_group)
        self.batch_folder = QLineEdit(); self.batch_folder.setPlaceholderText("Input folder containing EIS files")
        self.batch_browse = QPushButton("Browse")
        self.batch_auto = QCheckBox("Auto-select model for each file"); self.batch_auto.setChecked(True)
        self.batch_run = QPushButton("Run batch")
        self.batch_run.setObjectName("primaryButton")
        self.batch_export = QPushButton("Export batch results")
        self.batch_mott_btn = QPushButton("Send fitted capacitance to Mott-Schottky")
        self.batch_mott_btn.setToolTip(
            "Uses fitted C/Cdl or a supported R||CPE effective capacitance. "
            "DC potentials are read from embedded columns or filenames and remain editable."
        )
        self.batch_progress = QProgressBar(); self.batch_progress.setValue(0)
        bg.addWidget(self.batch_folder,0,0); bg.addWidget(self.batch_browse,0,1)
        bg.addWidget(self.batch_auto,1,0,1,2); bg.addWidget(self.batch_run,2,0,1,2)
        bg.addWidget(self.batch_export,3,0,1,2)
        bg.addWidget(self.batch_mott_btn,4,0,1,2)
        bg.addWidget(self.batch_progress,5,0,1,2)

        paired_group = QGroupBox("Paired ST A/B reports")
        pg = QGridLayout(paired_group)
        self.paired_heading = QLabel("<b>ST1-A / ST1-B paired Rct reports</b>")
        self.paired_info = QLabel(
            "Processes ST1-A, ST1-B, ST2-A, ST2-B… sequentially, writes one detailed TXT per data file, "
            "and creates one RctA−RctB summary TXT."
        )
        self.paired_info.setWordWrap(True)
        self.paired_output = QLineEdit(); self.paired_output.setPlaceholderText("Output folder (blank = EIS_Gold_ST_Reports)")
        self.paired_output_browse = QPushButton("Output…")
        self.paired_auto = QCheckBox("Rct-compatible auto-fit for each file"); self.paired_auto.setChecked(True)
        self.paired_run = QPushButton("Run ST A/B analysis + TXT reports")
        self.paired_open = QPushButton("Open reports folder"); self.paired_open.setEnabled(False)
        self.paired_open.setObjectName("quietButton")
        self.paired_progress = QProgressBar(); self.paired_progress.setValue(0)
        pg.addWidget(self.paired_heading,0,0,1,2)
        pg.addWidget(self.paired_info,1,0,1,2)
        pg.addWidget(self.paired_output,2,0); pg.addWidget(self.paired_output_browse,2,1)
        pg.addWidget(self.paired_auto,3,0,1,2)
        pg.addWidget(self.paired_run,4,0,1,2)
        pg.addWidget(self.paired_open,5,0,1,2)
        pg.addWidget(self.paired_progress,6,0,1,2)
        batch_layout.addWidget(batch_group)
        batch_layout.addWidget(paired_group)
        batch_layout.addStretch(1)

        ms_source_group = QGroupBox("Potential-series source")
        msg = QGridLayout(ms_source_group)
        self.ms_use_loaded_btn = QPushButton("Add current EIS study / detect bias series")
        self.ms_use_loaded_btn.setObjectName("primaryButton")
        self.ms_open_series_btn = QPushButton("Add multiple bias EIS files…")
        self.ms_calculate_series_btn = QPushButton("Extract points from file/DC table")
        self.ms_open_btn = QPushButton("Open prepared potential-C / potential-Z table…")
        self.ms_file_label = QLabel("No Mott-Schottky series prepared")
        self.ms_file_label.setObjectName("fileSummary")
        self.ms_file_label.setWordWrap(True)
        msg.addWidget(self.ms_use_loaded_btn, 0, 0, 1, 2)
        msg.addWidget(self.ms_open_series_btn, 1, 0, 1, 2)
        msg.addWidget(self.ms_calculate_series_btn, 2, 0, 1, 2)
        msg.addWidget(self.ms_open_btn, 3, 0, 1, 2)
        msg.addWidget(self.ms_file_label, 4, 0, 1, 2)

        ms_fit_group = QGroupBox("Mott-Schottky physics and fit window")
        mfg = QGridLayout(ms_fit_group)
        self.ms_method_combo = QComboBox()
        self.ms_method_combo.addItem("Parallel apparent C from admittance", "parallel")
        self.ms_method_combo.addItem("Series apparent C from Z imaginary", "series")
        self.ms_method_combo.addItem("Direct capacitance column / circuit fit", "direct")
        self.ms_frequency = ScientificDoubleSpinBox()
        self.ms_frequency.setRange(1e-9, 1e12); self.ms_frequency.setValue(1000.0)
        self.ms_frequency_tolerance = NoWheelDoubleSpinBox()
        self.ms_frequency_tolerance.setDecimals(2)
        self.ms_frequency_tolerance.setRange(0.0, 1000.0)
        self.ms_frequency_tolerance.setValue(35.0)
        self.ms_potential_tolerance = NoWheelDoubleSpinBox()
        self.ms_potential_tolerance.setDecimals(3)
        self.ms_potential_tolerance.setRange(0.0, 1000.0)
        self.ms_potential_tolerance.setValue(5.0)
        self.ms_area = ScientificDoubleSpinBox()
        self.ms_area.setRange(1e-12, 1e8); self.ms_area.setValue(1.0)
        self.ms_epsilon = ScientificDoubleSpinBox()
        self.ms_epsilon.setRange(1e-12, 1e6); self.ms_epsilon.setValue(10.0)
        self.ms_temperature = NoWheelDoubleSpinBox()
        self.ms_temperature.setDecimals(2)
        self.ms_temperature.setRange(1.0, 5000.0)
        self.ms_temperature.setValue(298.15)
        self.ms_fit_min = NoWheelDoubleSpinBox()
        self.ms_fit_min.setDecimals(6); self.ms_fit_min.setRange(-1e4, 1e4)
        self.ms_fit_min.setValue(-0.5)
        self.ms_fit_max = NoWheelDoubleSpinBox()
        self.ms_fit_max.setDecimals(6); self.ms_fit_max.setRange(-1e4, 1e4)
        self.ms_fit_max.setValue(0.5)
        for row, (label, widget) in enumerate((
            ("Capacitance source", self.ms_method_combo),
            ("Target common frequency / Hz", self.ms_frequency),
            ("Maximum frequency mismatch / %", self.ms_frequency_tolerance),
            ("Potential grouping tolerance / mV", self.ms_potential_tolerance),
            ("Electrode area / cm²", self.ms_area),
            ("Relative permittivity εr", self.ms_epsilon),
            ("Temperature / K", self.ms_temperature),
            ("Fit potential minimum / V", self.ms_fit_min),
            ("Fit potential maximum / V", self.ms_fit_max),
        )):
            mfg.addWidget(QLabel(label), row, 0)
            mfg.addWidget(widget, row, 1)
        self.ms_areal_input = QCheckBox(
            "Direct capacitance values are areal (F cm⁻²)"
        )
        self.ms_normalized_plot = QCheckBox("Fit area-normalized 1/(C/A)²")
        self.ms_normalized_plot.setChecked(True)
        self.ms_thermal = QCheckBox("Apply kT/q flat-band correction")
        self.ms_thermal.setChecked(True)
        self.ms_full_range_btn = QPushButton("Use full potential range")
        self.ms_calculate_btn = QPushButton("Calculate Mott-Schottky")
        self.ms_calculate_btn.setObjectName("primaryButton")
        self.ms_clear_series_btn = QPushButton("Clear Mott-Schottky series")
        self.ms_clear_series_btn.setObjectName("quietButton")
        base_row = 9
        mfg.addWidget(self.ms_areal_input, base_row, 0, 1, 2)
        mfg.addWidget(self.ms_normalized_plot, base_row + 1, 0, 1, 2)
        mfg.addWidget(self.ms_thermal, base_row + 2, 0, 1, 2)
        mfg.addWidget(self.ms_full_range_btn, base_row + 3, 0, 1, 2)
        mfg.addWidget(self.ms_calculate_btn, base_row + 4, 0, 1, 2)
        mfg.addWidget(self.ms_clear_series_btn, base_row + 5, 0, 1, 2)
        ms_caution = QLabel(
            "Scientific guardrail: fit only a justified linear depletion region. "
            "The result is an apparent carrier density unless planar geometry, "
            "space-charge capacitance, permittivity, and frequency independence are valid."
        )
        ms_caution.setObjectName("helpText")
        ms_caution.setWordWrap(True)
        ms_layout.addWidget(ms_source_group)
        ms_layout.addWidget(ms_fit_group)
        ms_layout.addWidget(ms_caution)
        ms_layout.addStretch(1)
        split.addWidget(self.workflow_tabs)

        right = QWidget(); right.setObjectName("resultsPane"); rl = QVBoxLayout(right); rl.setContentsMargins(4,0,0,0)
        self.tabs = QTabWidget(); self.tabs.setObjectName("resultTabs"); rl.addWidget(self.tabs)

        plot_page = QWidget()
        plot_page_layout = QVBoxLayout(plot_page)
        plot_page_layout.setContentsMargins(4, 4, 4, 4)
        self.empty_state = QLabel(
            "<b>Start with an EIS spectrum</b><br>Open or drop a CSV, TXT, Excel, or DTA file to view "
            "Nyquist and Bode plots."
        )
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.plot_tabs = QTabWidget(); self.plot_tabs.setObjectName("plotTabs")
        self.nyquist = PlotPanel(theme_name=self.theme_name); self.bode = PlotPanel(theme_name=self.theme_name); self.residual = PlotPanel(theme_name=self.theme_name); self.drt_plot = PlotPanel(theme_name=self.theme_name); self.cal_plot = PlotPanel(theme_name=self.theme_name); self.ms_plot = PlotPanel(theme_name=self.theme_name)
        self.plot_tabs.addTab(self.nyquist, "Nyquist"); self.plot_tabs.addTab(self.bode, "Bode")
        self.plot_tabs.addTab(self.residual, "Residuals"); self.plot_tabs.addTab(self.drt_plot, "DRT")
        self.plot_tabs.addTab(self.cal_plot, "Calibration")
        self.plot_tabs.addTab(self.ms_plot, "Mott-Schottky")
        plot_page_layout.addWidget(self.empty_state)
        plot_page_layout.addWidget(self.plot_tabs, 1)
        self.tabs.addTab(plot_page, "Plots")

        self.data_table = CopyableTableWidget(0, 3); self.data_table.setHorizontalHeaderLabels(["Frequency / Hz", "Z′ / Ω", "Z″ / Ω"])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.data_table, "Data")

        result_page = QWidget(); result_layout = QVBoxLayout(result_page)
        self.param_table = CopyableTableWidget(0, 5); self.param_table.setHorizontalHeaderLabels(["Parameter", "Value", "Std. error", "Relative SE / %", "Unit"])
        self.param_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.metric_table = CopyableTableWidget(0, 2); self.metric_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.metric_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        result_layout.addWidget(QLabel("Fitted parameters")); result_layout.addWidget(self.param_table)
        result_layout.addWidget(QLabel("Fit quality")); result_layout.addWidget(self.metric_table)
        self.tabs.addTab(result_page, "Fit results")

        self.ranking_table = CopyableTableWidget(); self.ranking_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.ranking_table, "Auto-fit ranking")
        self.batch_table = CopyableTableWidget()
        self.batch_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.tabs.addTab(self.batch_table, "Batch results")
        self.paired_table = CopyableTableWidget(); self.paired_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.paired_table, "ST Rct A−B")

        self.ms_page = QWidget()
        ms_result_layout = QVBoxLayout(self.ms_page)
        ms_result_layout.setContentsMargins(6, 6, 6, 6)
        self.ms_file_table = CopyableTableWidget(0, 5)
        self.ms_file_table.setHorizontalHeaderLabels([
            "Order", "EIS file", "DC potential / V", "Potential source", "Status"
        ])
        self.ms_file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.ms_file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ms_file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ms_file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ms_file_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        ms_file_actions = QHBoxLayout()
        self.ms_table_remove_btn = QPushButton("Remove selected")
        self.ms_table_up_btn = QPushButton("Move up")
        self.ms_table_down_btn = QPushButton("Move down")
        self.ms_table_filename_btn = QPushButton("Read DC from filenames")
        self.ms_table_clear_btn = QPushButton("Clear file table")
        for button in (
            self.ms_table_remove_btn, self.ms_table_up_btn, self.ms_table_down_btn,
            self.ms_table_filename_btn, self.ms_table_clear_btn,
        ):
            ms_file_actions.addWidget(button)
        ms_file_actions.addStretch(1)
        self.ms_metric_table = CopyableTableWidget(0, 2)
        self.ms_metric_table.setHorizontalHeaderLabels([
            "Mott-Schottky metric", "Value"
        ])
        self.ms_metric_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ms_data_table = CopyableTableWidget()
        ms_result_layout.addWidget(
            QLabel("Bias-file table — edit DC potential cells in volts"), 0
        )
        ms_result_layout.addWidget(self.ms_file_table, 1)
        ms_result_layout.addLayout(ms_file_actions)
        ms_result_layout.addWidget(QLabel("Calculated semiconductor parameters"))
        ms_result_layout.addWidget(self.ms_metric_table, 1)
        ms_result_layout.addWidget(QLabel("Capacitance and fitted data"))
        ms_result_layout.addWidget(self.ms_data_table, 1)
        self.tabs.addTab(self.ms_page, "Mott-Schottky")

        self.log_toggle = QPushButton("Activity & diagnostics  ▸")
        self.log_toggle.setObjectName("quietButton")
        self.log_toggle.setCheckable(True)
        rl.addWidget(self.log_toggle)
        # The log stays available without permanently reducing plot space.
        self.lower_scroll = QScrollArea(); self.lower_scroll.setWidgetResizable(True); self.lower_scroll.setMinimumHeight(150)
        lower = QWidget(); lower_l = QVBoxLayout(lower)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(130)
        lower_l.addWidget(self.log)
        self.lower_scroll.setWidget(lower); self.lower_scroll.setVisible(False); rl.addWidget(self.lower_scroll)
        split.addWidget(right); split.setStretchFactor(1, 1); split.setSizes([390, 1090])

        self._glass_cards = [
            self.hero_panel, data_group, fit_group, circuit_group, manual_group,
            drt_group, batch_group, paired_group, ms_source_group, ms_fit_group,
        ]
        for card in self._glass_cards:
            apply_glass_shadow(card, self.theme_name == "dark")
        self._workflow_fade = PageFadeController(self.workflow_tabs, parent=self)
        self._results_fade = PageFadeController(self.tabs, parent=self)
        self._plot_fade = PageFadeController(self.plot_tabs, duration_ms=190, parent=self)

    def _connect(self):
        self.open_btn.clicked.connect(self.open_file)
        self.fit_btn.clicked.connect(self.run_fit); self.auto_btn.clicked.connect(self.run_auto_fit)
        self.model_combo.currentIndexChanged.connect(self._update_circuit_info)
        self.builder_btn.clicked.connect(self.open_circuit_builder)
        self.manual_editor.valuesChanged.connect(self._manual_values_changed)
        self.estimate_values_btn.clicked.connect(self.estimate_manual_values)
        self.fitted_values_btn.clicked.connect(self.use_fitted_values)
        self.preview_values_btn.clicked.connect(self.preview_manual_values)
        self.clear_preview_btn.clicked.connect(self.clear_manual_preview)
        self.sign_flip.toggled.connect(self._plot_data)
        self.drt_btn.clicked.connect(self.run_drt); self.check_btn.clicked.connect(self.run_checks)
        self.batch_browse.clicked.connect(self.choose_batch_folder); self.batch_run.clicked.connect(self.run_batch)
        self.batch_export.clicked.connect(self.export_batch)
        self.batch_mott_btn.clicked.connect(self.run_mott_schottky_from_batch_results)
        self.paired_output_browse.clicked.connect(self.choose_paired_output_folder)
        self.paired_run.clicked.connect(self.run_paired_st_analysis)
        self.paired_open.clicked.connect(self.open_paired_output_folder)
        self.ms_use_loaded_btn.clicked.connect(self.calculate_mott_schottky_from_loaded_eis)
        self.ms_open_series_btn.clicked.connect(self.open_eis_potential_series)
        self.ms_calculate_series_btn.clicked.connect(
            self.calculate_mott_schottky_from_file_table
        )
        self.ms_open_btn.clicked.connect(self.open_mott_schottky_file)
        self.ms_full_range_btn.clicked.connect(self.use_full_mott_schottky_range)
        self.ms_calculate_btn.clicked.connect(self.run_mott_schottky)
        self.ms_clear_series_btn.clicked.connect(self.clear_mott_schottky_series)
        self.ms_table_remove_btn.clicked.connect(
            self.remove_selected_mott_schottky_files
        )
        self.ms_table_up_btn.clicked.connect(
            lambda: self.move_mott_schottky_file_rows(-1)
        )
        self.ms_table_down_btn.clicked.connect(
            lambda: self.move_mott_schottky_file_rows(1)
        )
        self.ms_table_filename_btn.clicked.connect(
            self.refresh_mott_schottky_filename_potentials
        )
        self.ms_table_clear_btn.clicked.connect(
            self.clear_mott_schottky_file_table
        )
        self.ms_file_table.itemChanged.connect(
            self._mott_schottky_file_table_changed
        )
        self.dark_mode_action.toggled.connect(self.toggle_dark_mode)
        self.motion_action.toggled.connect(self.toggle_cinematic_motion)
        self.advanced_toggle.toggled.connect(self._toggle_advanced_settings)
        self.log_toggle.toggled.connect(self._toggle_activity_log)

    def _toggle_advanced_settings(self, expanded: bool):
        self.advanced_settings.setVisible(expanded)
        self.advanced_toggle.setText(
            "Advanced fitting settings  ▾" if expanded else "Advanced fitting settings  ▸"
        )

    def _toggle_activity_log(self, expanded: bool):
        self.lower_scroll.setVisible(expanded)
        self.log_toggle.setText(
            "Activity & diagnostics  ▾" if expanded else "Activity & diagnostics  ▸"
        )

    @staticmethod
    def _is_supported_eis_path(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in {
            ".csv", ".txt", ".tsv", ".dat", ".asc", ".dta", ".xlsx", ".xls",
        }

    def dragEnterEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if any(self._is_supported_eis_path(path) for path in paths):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        selected = next((path for path in paths if self._is_supported_eis_path(path)), None)
        if selected is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self._load_data_file(selected)

    def _update_action_states(self):
        """Keep actions aligned with the current data/result and worker state."""
        busy = self._busy_operation is not None
        has_data = self.data is not None
        has_fit = self.fit_result is not None
        fit_matches_model = has_fit and self.fit_result.model_key == self.model_combo.currentData()
        has_batch = self.batch_df is not None
        has_ms = self.ms_data is not None
        has_ms_result = self.ms_result_df is not None
        has_preview = self.manual_preview_z is not None

        for widget in (
            self.fit_btn, self.auto_btn, self.drt_btn, self.check_btn,
            self.estimate_values_btn, self.preview_values_btn,
        ):
            widget.setEnabled(has_data and not busy)
        self.fitted_values_btn.setEnabled(fit_matches_model and not busy)
        self.clear_preview_btn.setEnabled(has_preview and not busy)
        self.batch_run.setEnabled(not busy)
        self.paired_run.setEnabled(not busy)
        self.batch_export.setEnabled(has_batch and not busy)
        self.batch_mott_btn.setEnabled(has_batch and not busy)
        self.ms_use_loaded_btn.setEnabled(has_data and not busy)
        self.ms_calculate_series_btn.setEnabled(
            self.ms_file_table.rowCount() > 0 and not busy
        )
        self.ms_calculate_btn.setEnabled(has_ms and not busy)
        self.ms_full_range_btn.setEnabled(has_ms and not busy)
        self.paired_open.setEnabled(
            not busy and self.paired_output_dir is not None and self.paired_output_dir.is_dir()
        )

        self.fit_action.setEnabled(has_data and not busy)
        self.auto_fit_action.setEnabled(has_data and not busy)
        self.export_all_action.setEnabled((has_data or has_batch or has_ms) and not busy)
        self.reset_action.setEnabled(has_data or has_ms_result)
        self.export_workbook_action.setEnabled(has_fit and not busy)
        self.export_package_action.setEnabled((has_data or has_batch or has_ms) and not busy)
        self.export_plot_action.setEnabled(has_data or has_ms_result)
        self.export_plot_data_action.setEnabled(has_data or has_ms_result)
        self.export_log_action.setEnabled(bool(self.log.toPlainText().strip()))

        if hasattr(self, "hero_status"):
            if busy:
                state, text = "busy", self._busy_operation.upper()
            elif has_ms_result:
                state, text = "fit", "MOTT READY"
            elif has_fit:
                state, text = "fit", "FIT READY"
            elif has_data:
                state, text = "data", "DATA LOADED"
            else:
                state, text = "ready", "READY"
            if self.hero_status.property("state") != state or self.hero_status.text() != text:
                self.hero_status.setProperty("state", state)
                self.hero_status.setText(text)
                self.hero_status.style().unpolish(self.hero_status)
                self.hero_status.style().polish(self.hero_status)

    def show_about_dialog(self):
        """Show application-only developer information with clickable links."""
        dialog = QDialog(self)
        dialog.setWindowTitle("About EIS Gold Studio")
        dialog.setModal(True)
        dialog.setMinimumWidth(440)

        layout = QVBoxLayout(dialog)
        title = QLabel("<h2>EIS Gold Studio</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        description = QLabel(
            "Advanced electrochemical impedance spectroscopy analysis, "
            "equivalent-circuit fitting, DRT, Mott-Schottky semiconductor analysis, "
            "batch processing, and visualization."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)

        developer = QLabel(
            '<p style="text-align:center"><b>Developed by A. Afruz</b><br>'
            '<a href="mailto:a.a.afruz@gmail.com">a.a.afruz@gmail.com</a><br>'
            '<a href="https://www.linkedin.com/in/ali-afruz/">'
            'linkedin.com/in/ali-afruz</a></p>'
        )
        developer.setTextFormat(Qt.RichText)
        developer.setTextInteractionFlags(Qt.TextBrowserInteraction)
        developer.setOpenExternalLinks(True)
        layout.addWidget(developer)

        privacy_note = QLabel(
            "Developer details are displayed only in the application interface "
            "and are not inserted into exported datasets, reports, figures, or analysis packages."
        )
        privacy_note.setWordWrap(True)
        privacy_note.setAlignment(Qt.AlignCenter)
        layout.addWidget(privacy_note)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def toggle_dark_mode(self, enabled: bool):
        self.set_theme("dark" if enabled else "light")

    def toggle_cinematic_motion(self, enabled: bool):
        self.set_motion_enabled(enabled)

    def set_motion_enabled(self, enabled: bool, persist: bool = True):
        self._motion_enabled = bool(enabled)
        if hasattr(self, "motion_action"):
            self.motion_action.blockSignals(True)
            self.motion_action.setChecked(self._motion_enabled)
            self.motion_action.blockSignals(False)
        if hasattr(self, "cinematic_backdrop"):
            self.cinematic_backdrop.set_motion_enabled(self._motion_enabled)
        if hasattr(self, "orbital_mark"):
            self.orbital_mark.set_motion_enabled(self._motion_enabled)
        if persist:
            QSettings("EIS Gold Studio", "EIS Gold Studio").setValue(
                "appearance/cinematic_motion", self._motion_enabled
            )
            self.statusBar().showMessage(
                "Cinematic motion enabled" if self._motion_enabled else "Cinematic motion paused"
            )

    def set_theme(self, theme_name: str, persist: bool = True):
        """Apply and optionally persist a complete application theme."""
        theme_name = theme_name if theme_name in {"light", "dark"} else "light"
        self.theme_name = theme_name
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(get_stylesheet(theme_name))
        if hasattr(self, "dark_mode_action"):
            self.dark_mode_action.blockSignals(True)
            self.dark_mode_action.setChecked(theme_name == "dark")
            self.dark_mode_action.blockSignals(False)
            self.dark_mode_action.setText("Dark mode")
            self.dark_mode_action.setToolTip("Disable dark mode" if theme_name == "dark" else "Enable dark mode")
        if hasattr(self, "circuit_diagram"):
            self.circuit_diagram.set_theme(theme_name)
        if hasattr(self, "cinematic_backdrop"):
            self.cinematic_backdrop.set_theme(theme_name)
        if hasattr(self, "orbital_mark"):
            self.orbital_mark.set_theme(theme_name)
        for card in getattr(self, "_glass_cards", ()):
            apply_glass_shadow(card, theme_name == "dark")
        for panel in self._plot_panels() if hasattr(self, "nyquist") else ():
            panel.apply_theme(theme_name)
        if persist:
            QSettings("EIS Gold Studio", "EIS Gold Studio").setValue("appearance/theme", theme_name)
            self.statusBar().showMessage(f"{theme_name.title()} theme enabled")

    def _plot_panels(self):
        return (
            self.nyquist, self.bode, self.residual, self.drt_plot,
            self.cal_plot, self.ms_plot,
        )

    @staticmethod
    def _finite_xy_from_complex(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values = np.asarray(arr, dtype=complex)
        mask = np.isfinite(values.real) & np.isfinite(values.imag)
        return values.real[mask], -values.imag[mask]

    def _apply_nyquist_limits(self, ax, *complex_series: np.ndarray):
        """Autoscale Nyquist limits with padding so edge points are not clipped."""
        xs = []
        ys = []
        for series in complex_series:
            if series is None:
                continue
            x, y = self._finite_xy_from_complex(series)
            if x.size:
                xs.append(x)
                ys.append(y)
        if not xs:
            return
        x = np.concatenate(xs)
        y = np.concatenate(ys)
        xmin, xmax = float(np.nanmin(x)), float(np.nanmax(x))
        ymin, ymax = float(np.nanmin(y)), float(np.nanmax(y))
        xpad = max((xmax - xmin) * 0.08, max(abs(xmin), abs(xmax), 1.0) * 1e-3)
        ypad = max((ymax - ymin) * 0.08, max(abs(ymin), abs(ymax), 1.0) * 1e-3)
        ax.set_xlim(xmin - xpad, xmax + xpad)
        ax.set_ylim(ymin - ypad, ymax + ypad)
        ax.margins(x=0.08, y=0.08)

    def _finish_plot(self, panel: PlotPanel):
        panel.apply_theme(self.theme_name, redraw=False)
        panel.canvas.draw_idle()

    def _settings(self):
        return FitSettings(
            weighting=self.weight_combo.currentText(),
            max_nfev=self.nfev_spin.value(),
            robust_loss=self.loss_combo.currentText(),
            multistart=self.multistart_spin.value(),
            optimizer=self.optimizer_combo.currentData(),
        )

    def _current_arrays(self):
        if self.data is None: raise ValueError("Load an EIS file first.")
        f = self.data["frequency_Hz"].to_numpy(float)
        zi = self.data["Zimag_ohm"].to_numpy(float)
        if self.sign_flip.isChecked(): zi = -zi
        z = self.data["Zreal_ohm"].to_numpy(float) + 1j * zi
        return f, z


    def _save_manual_state(self):
        if self._manual_model_key and hasattr(self, "manual_editor"):
            self._manual_cache[self._manual_model_key] = (
                self.manual_editor.values(), self.manual_editor.locks()
            )

    @staticmethod
    def _generic_parameter_values(spec):
        values = {}
        for pdef in spec.params:
            if pdef.scale == "log":
                values[pdef.name] = float(np.sqrt(pdef.low * pdef.high))
            else:
                values[pdef.name] = float((pdef.low + pdef.high) / 2.0)
        return values

    def _manual_state_for_model(self, key: str):
        if key in self._manual_cache:
            values, locks = self._manual_cache[key]
            return dict(values), set(locks)
        spec = CIRCUITS[key]
        if self.fit_result is not None and self.fit_result.model_key == key:
            return dict(self.fit_result.params), set(self.fit_result.fixed_params)
        if self.data is not None:
            try:
                f, z = self._current_arrays()
                return initial_guess_values(f, z, key), set()
            except Exception:
                pass
        return self._generic_parameter_values(spec), set()

    def _manual_values_changed(self):
        key = self.model_combo.currentData()
        if not key or self._manual_model_key != key:
            return
        values = self.manual_editor.values()
        locks = self.manual_editor.locks()
        self._manual_cache[key] = (dict(values), set(locks))
        spec = CIRCUITS[key]
        self.circuit_diagram.set_values(values, {p.name: p.unit for p in spec.params})

    def estimate_manual_values(self, silent: bool = False):
        try:
            f, z = self._current_arrays()
            key = self.model_combo.currentData()
            values = initial_guess_values(f, z, key)
            self.manual_editor.set_values(values, preserve_locks=True)
            self._manual_values_changed()
            if not silent:
                self.log.appendPlainText(f"Estimated manual starting values from the data for {CIRCUITS[key].name}.")
                self.statusBar().showMessage("Manual starting values estimated from data")
        except Exception as exc:
            if not silent:
                self._error(str(exc))

    def use_fitted_values(self):
        key = self.model_combo.currentData()
        if self.fit_result is None or self.fit_result.model_key != key:
            self._error("Fit the currently selected circuit before loading fitted values.")
            return
        self.manual_editor.set_values(self.fit_result.params, preserve_locks=True)
        self._manual_values_changed()
        self.statusBar().showMessage("Loaded fitted values into the manual editor")

    def preview_manual_values(self):
        try:
            f, _ = self._current_arrays()
            key = self.model_combo.currentData()
            values = self.manual_editor.values()
            self.manual_preview_z = evaluate(key, f, values)
            self._manual_values_changed()
            self._plot_data()
            locked = sorted(self.manual_editor.locks())
            self.log.appendPlainText(
                f"Manual preview: {CIRCUITS[key].name}." +
                (f" Locked parameters: {', '.join(locked)}." if locked else " No parameters locked.")
            )
            self.statusBar().showMessage("Manual circuit response previewed")
            self._update_action_states()
        except Exception as exc:
            self._error(str(exc))

    def clear_manual_preview(self):
        self.manual_preview_z = None
        self._plot_data()
        self.statusBar().showMessage("Manual preview cleared")
        self._update_action_states()

    def open_circuit_builder(self):
        try:
            self._save_manual_state()
            key = self.model_combo.currentData()
            spec = CIRCUITS[key]
            values, locks = self._manual_state_for_model(key)
            frequencies = measured = None
            dc_series = []
            if self.data is not None:
                frequencies, measured = self._current_arrays()
                embedded = (
                    self.data["potential_V"].dropna().to_numpy(float)
                    if "potential_V" in self.data.columns else np.array([], dtype=float)
                )
                potential = (
                    float(np.median(embedded))
                    if len(embedded) and float(np.ptp(embedded)) <= .005
                    else potential_from_filename(self.current_file) if self.current_file else None
                )
                if potential is not None:
                    dc_series.append({
                        "potential": float(potential),
                        "frequency": frequencies,
                        "impedance": measured,
                        "source": str(self.current_file or "Current EIS study"),
                    })
            fit_diagnostics = (
                self.fit_result
                if self.fit_result is not None and self.fit_result.model_key == key
                else None
            )
            dialog = CircuitBuilderDialog(
                spec,
                values,
                locks,
                self.theme_name,
                self,
                frequencies=frequencies,
                measured_impedance=measured,
                fit_diagnostics=fit_diagnostics,
                dc_series=dc_series,
                drt_data=self.drt_df,
            )
            if not dialog.exec():
                return
            custom_spec, custom_values, custom_locks = dialog.result_payload()
            CIRCUITS[custom_spec.key] = custom_spec
            index = self.model_combo.findData(custom_spec.key)
            if index < 0:
                self.model_combo.addItem(custom_spec.name, custom_spec.key)
                index = self.model_combo.findData(custom_spec.key)
            else:
                self.model_combo.setItemText(index, custom_spec.name)
            self._manual_cache[custom_spec.key] = (dict(custom_values), set(custom_locks))
            self.model_combo.setCurrentIndex(index)
            self.manual_preview_z = None
            self._update_circuit_info()
            self.log.appendPlainText(
                f"Applied custom circuit: {custom_spec.expression}. "
                f"Elements can be edited and locked in the manual-value panel."
            )
            self.statusBar().showMessage("Custom visual circuit applied")
        except Exception as exc:
            self._error(str(exc))

    def open_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Open EIS data",
            "",
            "EIS data (*.csv *.txt *.tsv *.dat *.asc *.dta *.xlsx *.xls);;ASCII text (*.txt *.tsv *.csv *.dat *.asc *.dta);;Excel (*.xlsx *.xls);;All files (*)",
        )
        if not file:
            return
        self._load_data_file(Path(file))

    def _load_data_file(self, file: str | Path):
        file = Path(file)
        try:
            self.data = read_eis(
                file,
                delimiter=self.delimiter_combo.currentData(),
                decimal=self.decimal_combo.currentData(),
            )
            self.current_file = file; self.file_label.setText(str(self.current_file))
            # The importer already resolves explicit -Z″ headers. Reset the manual
            # override so a newly opened file is not accidentally inverted twice.
            self.sign_flip.blockSignals(True); self.sign_flip.setChecked(False); self.sign_flip.blockSignals(False)
            self.fit_result = None; self.ranking = []; self.manual_preview_z = None
            self.drt_df = None; self.drt_reconstruction_df = None
            self.calibration_df = None; self.calibration_stats = None
            self._populate_data(); self.estimate_manual_values(silent=True); self._plot_data()
            self.log.appendPlainText(f"Loaded {len(self.data)} points from {file}")
            for line in import_audit_text(self.data):
                self.log.appendPlainText("  " + line)
            self.empty_state.setVisible(False)
            self.workflow_tabs.setCurrentWidget(self.fit_workflow_page)
            self.tabs.setCurrentIndex(0)
            self._update_action_states()
            self.statusBar().showMessage(f"Loaded {self.current_file.name}")
        except Exception as e: self._error(str(e))

    def _populate_data(self):
        columns = [
            ("frequency_Hz", "Frequency / Hz"),
            ("Zreal_ohm", "Z′ / Ω"),
            ("Zimag_ohm", "Z″ / Ω"),
        ]
        optional = [
            ("source_index", "Index"),
            ("impedance_magnitude_ohm", "|Z| / Ω"),
            ("phase_deg", "Phase / °"),
            ("time_s", "Time / s"),
            ("potential_V", "Potential / V"),
        ]
        columns.extend(item for item in optional if item[0] in self.data.columns)
        self.data_table.clear()
        self.data_table.setRowCount(len(self.data)); self.data_table.setColumnCount(len(columns))
        self.data_table.setHorizontalHeaderLabels([label for _, label in columns])
        for r, (_, row) in enumerate(self.data.iterrows()):
            for c, (key, _) in enumerate(columns):
                self.data_table.setItem(r, c, numeric_item(row.get(key, np.nan)))
        self.data_table.resizeColumnsToContents()

    def _plot_data(self):
        if self.data is None: return
        palette = get_palette(self.theme_name)
        f, z = self._current_arrays(); zfit = self.fit_result.z_fit if self.fit_result is not None and len(self.fit_result.z_fit)==len(z) else None
        zpreview = self.manual_preview_z if self.manual_preview_z is not None and len(self.manual_preview_z) == len(z) else None
        fig = self.nyquist.figure; fig.clear(); ax = fig.add_subplot(111)
        ax.scatter(z.real, -z.imag, s=27, label="Measured", color=palette.measured)
        if zpreview is not None: ax.plot(zpreview.real, -zpreview.imag, "--", linewidth=1.8, label="Manual preview", color=palette.secondary)
        if zfit is not None: ax.plot(zfit.real, -zfit.imag, linewidth=2, label="Fit", color=palette.fit)
        ax.set_xlabel("Z′ / Ω"); ax.set_ylabel("−Z″ / Ω"); ax.set_title("Nyquist plot"); ax.grid(True, alpha=.25)
        # Keep the Nyquist axes freely zoomable.  A fixed/equal data aspect makes
        # Matplotlib ignore toolbar zoom limits with warnings such as
        # "Ignoring fixed x/y limits to fulfill fixed data aspect".
        ax.set_aspect("auto", adjustable="box")
        self._apply_nyquist_limits(ax, z, zpreview, zfit)
        ax.legend(); self._finish_plot(self.nyquist)
        fig = self.bode.figure; fig.clear(); ax1 = fig.add_subplot(211); ax2 = fig.add_subplot(212, sharex=ax1)
        positive_f = np.asarray(f, dtype=float) > 0
        if not np.all(positive_f):
            self.log.appendPlainText("Warning: non-positive frequencies were skipped in the Bode plot because the x-axis is logarithmic.")
        fb = np.asarray(f, dtype=float)[positive_f]
        zb = z[positive_f]
        zpreview_b = zpreview[positive_f] if zpreview is not None else None
        zfit_b = zfit[positive_f] if zfit is not None else None
        ax1.set_xscale("log"); ax2.set_xscale("log")
        ax1.plot(fb, np.abs(zb), "o", label="Measured", color=palette.measured)
        ax2.plot(fb, np.angle(zb, deg=True), "o", label="Measured", color=palette.measured)
        if zpreview_b is not None:
            ax1.plot(fb, np.abs(zpreview_b), "--", label="Manual preview", color=palette.secondary)
            ax2.plot(fb, np.angle(zpreview_b, deg=True), "--", label="Manual preview", color=palette.secondary)
        if zfit_b is not None:
            ax1.plot(fb, np.abs(zfit_b), "-", label="Fit", color=palette.fit)
            ax2.plot(fb, np.angle(zfit_b,deg=True), "-", label="Fit", color=palette.fit)
        ax1.set_ylabel("|Z| / Ω"); ax2.set_ylabel("Phase / °"); ax2.set_xlabel("Frequency / Hz"); ax1.grid(True,which="both",alpha=.25); ax2.grid(True,which="both",alpha=.25); ax1.legend(); ax2.legend(); self._finish_plot(self.bode)

    def run_fit(self):
        try:
            f,z=self._current_arrays(); key=self.model_combo.currentData(); self.statusBar().showMessage("Fitting…")
            initial = self.manual_editor.values() if self.manual_start_check.isChecked() else None
            fixed = self.manual_editor.fixed_values()
            self.manual_preview_z = None
            self.fit_result=fit_model(f,z,key,self._settings(),initial=initial,fixed=fixed)
            self.ranking=[]; self._show_fit()
            fixed_text = f"; fixed={', '.join(self.fit_result.fixed_params)}" if self.fit_result.fixed_params else ""
            self.log.appendPlainText(f"Fit complete: {self.fit_result.model_name}, RMSE={self.fit_result.rmse:.5g}{fixed_text}")
            self._update_action_states()
        except Exception as e: self._error(str(e))

    def run_auto_fit(self):
        try:
            f, z = self._current_arrays()
            keys = list(CIRCUITS)
            if not self.all_models_check.isChecked():
                complex_keys = {
                    "R-(R||CPE)-(R||CPE)", "R-(R||CPE)-(R||CPE)-Wo",
                    "R-TLMo", "R-(R||CPE)-TLMo", "R-(R||CPE)-TLMs",
                    "R-(R||CPE)-(R||Lads)",
                }
                keys = [key for key in keys if key not in complex_keys]
            self.manual_preview_z = None
            self._busy_operation = "auto-fit"
            self._update_action_states()
            self.autofit_progress.setValue(0)
            self.autofit_progress.setVisible(True)
            self.statusBar().showMessage("Advanced auto-fit is running…")
            self.log.appendPlainText(f"Advanced auto-fit started for {len(keys)} candidate circuits.")
            self.autofit_worker = AutoFitWorker(f, z, keys, self._settings(), self)
            self.autofit_worker.progress.connect(self._auto_fit_progress)
            self.autofit_worker.completed.connect(self._auto_fit_done)
            self.autofit_worker.failed.connect(self._auto_fit_failed)
            self.autofit_worker.start()
        except Exception as e:
            self._busy_operation = None
            self._update_action_states()
            self._error(str(e))

    def _auto_fit_progress(self, percent: int, message: str):
        self.autofit_progress.setValue(max(0, min(100, int(percent))))
        self.statusBar().showMessage(message)

    def _set_fit_controls_enabled(self, enabled: bool):
        if enabled:
            self._busy_operation = None
        self._update_action_states()

    def _auto_fit_done(self, ranking):
        self._set_fit_controls_enabled(True)
        self.autofit_progress.setValue(100)
        self.ranking = list(ranking)
        self.fit_result = self.ranking[0]
        idx = self.model_combo.findData(self.fit_result.model_key)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self._show_ranking()
        self._show_fit()
        self.tabs.setCurrentWidget(self.ranking_table)
        f, z = self._current_arrays()
        sig = diffusion_signature(f, z)
        self.log.appendPlainText(
            f"Low-frequency diffusion screen: {sig['classification']} "
            f"(angle={sig['tail_angle_deg']:.2f}°, β≈{sig['frequency_beta']:.3f}, "
            f"R²={sig['nyquist_r2']:.4f}, strength={sig['strength']:.3f})."
        )
        self.log.appendPlainText(f"Auto-fit selected {self.fit_result.model_name}. Rank score={self.fit_result.rank_score:.4g}")
        if self.fit_result.model_key == "R-(R||CPE)-Wf":
            beta = self.fit_result.params.get("beta", np.nan)
            if np.isfinite(beta):
                kind = "close to ideal Warburg" if abs(beta - 0.5) <= 0.05 else "fractional/anomalous diffusion"
                self.log.appendPlainText(f"Fitted diffusion exponent βW={beta:.4f}: {kind}.")
        if any(token in self.fit_result.model_key for token in ("Wo", "Ws", "G", "TLM")):
            self.log.appendPlainText(
                "Selected model contains finite-length/diffusion-distribution physics; "
                "check parameter errors, bounds, and residuals before assigning a mechanism."
            )
        if self.fit_result.warnings:
            self.log.appendPlainText("Model-selection warnings:")
            for warning in self.fit_result.warnings:
                self.log.appendPlainText(f"  • {warning}")
        self._update_action_states()

    def _auto_fit_failed(self, text):
        self._set_fit_controls_enabled(True)
        self.autofit_progress.setValue(0)
        self._error(text)

    def _show_fit(self):
        r=self.fit_result; spec=CIRCUITS[r.model_key]
        self.param_table.setRowCount(len(spec.params))
        for i,p in enumerate(spec.params):
            v=r.params[p.name]; se=r.stderr.get(p.name,np.nan); rel=100*se/abs(v) if np.isfinite(se) and v else np.nan
            for c,item in enumerate((p.label,numeric_item(v),numeric_item(se),numeric_item(rel),p.unit)):
                self.param_table.setItem(i,c,item if hasattr(item,"text") else numeric_item(item))
        metrics={
            "Model":r.model_name,
            "Success":r.success,
            "RMSE / Ω":r.rmse,
            "Normalized pseudo χ² (Zmod)":r.pseudo_chi2,
            "Normalized χ²red (Zmod)":r.red_chi2,
            "Relative residual RMS / %":r.relative_rmse_percent,
            "χ² degrees of freedom (N−k)":r.chi2_dof,
            "Legacy raw reduced variance / Ω²":r.raw_red_var,
            "RSS / Ω²":r.rss,
            "AICc":r.aicc,
            "BIC":r.bic,
            "Residual structure":r.residual_score,
            "Physical penalty":r.physical_score,
            "Rank score":r.rank_score,
            "Fixed parameters":", ".join(r.fixed_params) or "None",
            "Free parameters":len(spec.params)-len(r.fixed_params),
            "Optimizer":r.optimizer_name,
            "Max |parameter correlation|":r.max_abs_correlation,
            "Jacobian condition":r.jacobian_condition,
            "Warnings":" | ".join(r.warnings) if r.warnings else "None",
            "Evaluations":r.nfev,
            "Message":r.message
        }
        self.metric_table.setRowCount(len(metrics))
        from PySide6.QtWidgets import QTableWidgetItem
        for i,(k,v) in enumerate(metrics.items()): self.metric_table.setItem(i,0,QTableWidgetItem(str(k))); self.metric_table.setItem(i,1,numeric_item(v) if isinstance(v,(int,float,np.number)) else QTableWidgetItem(str(v)))
        self.manual_editor.set_values(r.params, preserve_locks=True)
        self._manual_cache[r.model_key] = (dict(r.params), set(self.manual_editor.locks()))
        self.circuit_diagram.set_values(r.params, {p.name:p.unit for p in spec.params})
        f,z=self._current_arrays(); self._plot_data()
        palette=get_palette(self.theme_name)
        fig=self.residual.figure; fig.clear(); a1=fig.add_subplot(211); a2=fig.add_subplot(212,sharex=a1)
        a1.semilogx(f,r.residual_complex.real,"o-",color=palette.measured,label="Real residual")
        a2.semilogx(f,r.residual_complex.imag,"o-",color=palette.secondary,label="Imaginary residual")
        a1.axhline(0,linewidth=1,color=palette.muted_text); a2.axhline(0,linewidth=1,color=palette.muted_text); a1.set_ylabel("ΔZ′ / Ω"); a2.set_ylabel("ΔZ″ / Ω"); a2.set_xlabel("Frequency / Hz"); a1.grid(True,which="both",alpha=.25); a2.grid(True,which="both",alpha=.25); self._finish_plot(self.residual)
        self.tabs.setCurrentIndex(2); self.statusBar().showMessage(f"Fit complete — {r.model_name}")

    def _show_ranking(self):
        df=pd.DataFrame([r.summary_row() for r in self.ranking])
        self._df_to_table(df,self.ranking_table)

    def run_checks(self):
        try:
            f,z=self._current_arrays(); d=consistency_checks(f,z)
            self.log.appendPlainText("\nConsistency diagnostics (screening-level):")
            for k,v in d.items(): self.log.appendPlainText(f"  {k}: {v}")
            self.statusBar().showMessage(f"Consistency check: {d['overall']}")
            self._update_action_states()
        except Exception as e:self._error(str(e))

    def run_drt(self):
        try:
            f,z=self._current_arrays(); tau,gamma,zr=drt_tikhonov(f,z,self.drt_points.value(),self.drt_lambda.value())
            order=np.argsort(f); fs=f[order]; zs=z[order]
            self.drt_df=pd.DataFrame({"tau_s":tau,"gamma_ohm":gamma})
            self.drt_reconstruction_df=pd.DataFrame({
                "frequency_Hz":fs,
                "Zreal_measured_ohm":zs.real,
                "Zimag_measured_ohm":zs.imag,
                "Zreal_DRT_reconstructed_ohm":zr.real,
                "Zimag_DRT_reconstructed_ohm":zr.imag,
                "residual_real_ohm":zs.real-zr.real,
                "residual_imag_ohm":zs.imag-zr.imag,
            })
            palette=get_palette(self.theme_name)
            fig=self.drt_plot.figure; fig.clear(); ax=fig.add_subplot(111); ax.semilogx(tau,gamma,linewidth=2,color=palette.measured,label="DRT")
            ax.set_xlabel("Relaxation time τ / s"); ax.set_ylabel("γ(ln τ) / Ω"); ax.set_title("Regularized DRT"); ax.grid(True,which="both",alpha=.25); self._finish_plot(self.drt_plot); self.plot_tabs.setCurrentWidget(self.drt_plot)
            err=np.sqrt(np.mean(np.abs(zr-zs)**2)); self.log.appendPlainText(f"DRT complete. Reconstruction RMSE={err:.5g}; λ={self.drt_lambda.value():g}")
            self._update_action_states()
        except Exception as e:self._error(str(e))

    def _set_mott_schottky_data(
        self,
        data: pd.DataFrame,
        label: str,
        sources: list[Path] | None = None,
    ):
        self.ms_data = data
        self.ms_result_df = None
        self.ms_stats = None
        self.ms_source_files = list(sources or [])
        self.ms_file_label.setText(label)
        self.ms_metric_table.setRowCount(0)
        self.ms_plot.figure.clear()
        self._finish_plot(self.ms_plot)
        methods = available_capacitance_methods(data)
        current_method = self.ms_method_combo.currentData()
        if current_method not in methods and methods:
            preferred = "direct" if "direct" in methods else "parallel"
            index = self.ms_method_combo.findData(preferred)
            if index >= 0:
                self.ms_method_combo.setCurrentIndex(index)
        if "capacitance_is_areal_hint" in data.attrs:
            self.ms_areal_input.setChecked(
                bool(data.attrs.get("capacitance_is_areal_hint"))
            )
        self.use_full_mott_schottky_range()
        self._df_to_table(data, self.ms_data_table)
        self.tabs.setCurrentWidget(self.ms_page)
        self.workflow_tabs.setCurrentWidget(self.ms_workflow_page)
        self._update_action_states()

    def _prompt_dc_potential_for_current_study(
        self, default_value: float = 0.0
    ) -> float | None:
        value, accepted = QInputDialog.getDouble(
            self,
            "DC potential for this EIS study",
            (
                "Enter the DC bias used while recording this spectrum.\n"
                "Potential / V vs the experiment reference electrode:"
            ),
            float(default_value),
            -10000.0,
            10000.0,
            6,
        )
        if not accepted:
            return None
        self._last_ms_dc_potential_V = float(value)
        return float(value)

    def _append_current_studies_to_mott_schottky_series(
        self,
        points: pd.DataFrame,
        source_path: Path | None,
    ) -> pd.DataFrame:
        points = points.copy()
        source_key = (
            str(source_path.resolve())
            if source_path is not None else "current in-memory EIS table"
        )
        study_id = f"{source_key}|{self.ms_frequency.value():.12g}Hz"
        points["study_id"] = study_id
        if source_path is not None:
            points["source_file"] = str(source_path)
        existing = None
        if (
            self.ms_data is not None
            and self.ms_data.attrs.get("source_kind") == "collected EIS DC series"
        ):
            existing = self.ms_data.copy()
            if "study_id" in existing:
                existing = existing.loc[
                    existing["study_id"].astype(str) != study_id
                ].copy()
        combined = (
            pd.concat([existing, points], ignore_index=True)
            if existing is not None else points
        )
        combined = combined.sort_values(["potential_V", "study_id"]).reset_index(
            drop=True
        )
        paths = list(self.ms_source_files) if existing is not None else []
        if source_path is not None and source_path not in paths:
            paths.append(source_path)
        combined.attrs.update({
            "source_kind": "collected EIS DC series",
            "source_paths": [str(path) for path in paths],
            "target_frequency_Hz": float(self.ms_frequency.value()),
            "max_frequency_deviation_percent": float(
                self.ms_frequency_tolerance.value()
            ),
        })
        self._set_mott_schottky_data(
            combined,
            (
                f"Collected {len(combined)} point(s) at "
                f"{combined['potential_V'].nunique()} distinct potential(s), "
                f"target {self.ms_frequency.value():g} Hz"
            ),
            paths,
        )
        return combined

    def calculate_mott_schottky_from_loaded_eis(self):
        if self.data is None:
            self._error("Load an EIS study first.")
            return
        try:
            source = self.data.copy()
            source.attrs = dict(self.data.attrs)
            if self.sign_flip.isChecked():
                source["Zimag_ohm"] = -source["Zimag_ohm"]
            tolerance_V = max(
                float(self.ms_potential_tolerance.value()) * 1e-3, 1e-9
            )
            embedded = (
                source["potential_V"].dropna().to_numpy(float)
                if "potential_V" in source else np.array([], dtype=float)
            )
            clusters = (
                np.unique(np.round(embedded / tolerance_V).astype(np.int64))
                if embedded.size else np.array([], dtype=int)
            )
            if len(clusters) >= 2:
                extracted = extract_mott_schottky_from_eis(
                    source,
                    target_frequency_hz=self.ms_frequency.value(),
                    max_frequency_deviation_percent=(
                        self.ms_frequency_tolerance.value()
                    ),
                    potential_group_tolerance_V=tolerance_V,
                    minimum_potentials=1,
                )
                self.log.appendPlainText(
                    f"\nMott-Schottky: detected {len(clusters)} embedded "
                    "DC-potential steps in the loaded EIS table."
                )
            else:
                if embedded.size:
                    dc_value = float(np.median(embedded))
                    potential_source = "embedded EIS potential"
                else:
                    dc_value = self._prompt_dc_potential_for_current_study(
                        self._last_ms_dc_potential_V
                    )
                    if dc_value is None:
                        return
                    potential_source = "user-entered DC value"
                extracted = extract_mott_schottky_study(
                    source,
                    dc_value,
                    target_frequency_hz=self.ms_frequency.value(),
                    max_frequency_deviation_percent=(
                        self.ms_frequency_tolerance.value()
                    ),
                )
                extracted["potential_source"] = potential_source
                self.log.appendPlainText(
                    f"\nMott-Schottky: added current spectrum at "
                    f"{dc_value:.6g} V ({potential_source})."
                )
            combined = self._append_current_studies_to_mott_schottky_series(
                extracted, self.current_file
            )
            distinct = int(combined["potential_V"].nunique())
            if distinct >= 4:
                self.run_mott_schottky()
            else:
                self.statusBar().showMessage(
                    f"Mott-Schottky point stored — {distinct}/4 distinct potentials"
                )
        except Exception as exc:
            self._error(str(exc))

    @staticmethod
    def _readonly_table_item(text: object) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _mott_schottky_file_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for row in range(self.ms_file_table.rowCount()):
            file_item = self.ms_file_table.item(row, 1)
            potential_item = self.ms_file_table.item(row, 2)
            if file_item is None:
                continue
            raw_path = file_item.data(Qt.UserRole)
            rows.append({
                "path": Path(str(raw_path or file_item.text())),
                "potential_text": (
                    potential_item.text().strip() if potential_item else ""
                ),
                "potential_origin": (
                    potential_item.data(Qt.UserRole)
                    if potential_item else "automatic"
                ),
                "source": (
                    self.ms_file_table.item(row, 3).text()
                    if self.ms_file_table.item(row, 3) else "automatic"
                ),
                "status": (
                    self.ms_file_table.item(row, 4).text()
                    if self.ms_file_table.item(row, 4) else "Ready"
                ),
            })
        return rows

    def _set_mott_schottky_file_rows(self, rows: list[dict[str, object]]):
        self._updating_ms_file_table = True
        try:
            self.ms_file_table.setRowCount(len(rows))
            for row_index, entry in enumerate(rows):
                path = Path(entry["path"])
                order_item = self._readonly_table_item(row_index + 1)
                file_item = self._readonly_table_item(path.name)
                file_item.setData(Qt.UserRole, str(path))
                file_item.setToolTip(str(path))
                potential_item = QTableWidgetItem(
                    str(entry.get("potential_text", ""))
                )
                potential_item.setData(
                    Qt.UserRole, str(entry.get("potential_origin", "automatic"))
                )
                potential_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ms_file_table.setItem(row_index, 0, order_item)
                self.ms_file_table.setItem(row_index, 1, file_item)
                self.ms_file_table.setItem(row_index, 2, potential_item)
                self.ms_file_table.setItem(
                    row_index, 3,
                    self._readonly_table_item(entry.get("source", "automatic")),
                )
                self.ms_file_table.setItem(
                    row_index, 4,
                    self._readonly_table_item(entry.get("status", "Ready")),
                )
        finally:
            self._updating_ms_file_table = False
        self._update_action_states()

    def _mott_schottky_file_table_changed(self, item: QTableWidgetItem):
        if self._updating_ms_file_table or item.column() != 2:
            return
        text = item.text().strip().replace(",", ".")
        self._updating_ms_file_table = True
        try:
            source_item = self.ms_file_table.item(item.row(), 3)
            status_item = self.ms_file_table.item(item.row(), 4)
            if not text:
                item.setData(Qt.UserRole, "automatic")
                source_item.setText("automatic: embedded/filename")
                status_item.setText("DC will be detected")
            else:
                try:
                    value = float(text)
                    if not np.isfinite(value):
                        raise ValueError
                    item.setText(f"{value:.10g}")
                    item.setData(Qt.UserRole, "table")
                    source_item.setText("table/manual")
                    status_item.setText("Ready")
                except ValueError:
                    item.setData(Qt.UserRole, "invalid")
                    source_item.setText("invalid table value")
                    status_item.setText("Enter numeric volts")
        finally:
            self._updating_ms_file_table = False

    def refresh_mott_schottky_filename_potentials(self):
        rows = self._mott_schottky_file_rows()
        recovered = 0
        for entry in rows:
            potential = potential_from_filename(entry["path"])
            if potential is None:
                continue
            entry.update({
                "potential_text": f"{potential:.10g}",
                "potential_origin": "filename",
                "source": "filename",
                "status": "Ready",
            })
            recovered += 1
        self._set_mott_schottky_file_rows(rows)
        self.statusBar().showMessage(
            f"Recovered DC potential from {recovered} filename(s)"
        )

    def remove_selected_mott_schottky_files(self):
        selected = sorted({
            index.row()
            for index in self.ms_file_table.selectionModel().selectedRows()
        })
        if not selected:
            return
        selected_set = set(selected)
        rows = [
            entry for index, entry in enumerate(self._mott_schottky_file_rows())
            if index not in selected_set
        ]
        self._set_mott_schottky_file_rows(rows)

    def move_mott_schottky_file_rows(self, direction: int):
        selected = sorted({
            index.row()
            for index in self.ms_file_table.selectionModel().selectedRows()
        })
        if not selected:
            return
        rows = self._mott_schottky_file_rows()
        if direction < 0:
            for index in selected:
                if index > 0 and index - 1 not in selected:
                    rows[index - 1], rows[index] = rows[index], rows[index - 1]
            new_selected = [max(0, index - 1) for index in selected]
        else:
            for index in reversed(selected):
                if index < len(rows) - 1 and index + 1 not in selected:
                    rows[index + 1], rows[index] = rows[index], rows[index + 1]
            new_selected = [min(len(rows) - 1, index + 1) for index in selected]
        self._set_mott_schottky_file_rows(rows)
        self.ms_file_table.clearSelection()
        for index in new_selected:
            self.ms_file_table.selectRow(index)

    def clear_mott_schottky_file_table(self):
        self._set_mott_schottky_file_rows([])
        self.statusBar().showMessage("Mott-Schottky bias-file table cleared")

    def clear_mott_schottky_series(self):
        self.ms_data = None
        self.ms_result_df = None
        self.ms_stats = None
        self.ms_source_files = []
        self.ms_metric_table.setRowCount(0)
        self.ms_data_table.setRowCount(0)
        self.ms_plot.figure.clear()
        self._finish_plot(self.ms_plot)
        self.ms_file_label.setText("No Mott-Schottky series prepared")
        self.clear_mott_schottky_file_table()
        self._update_action_states()

    def open_eis_potential_series(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add EIS files measured at different DC potentials",
            "",
            "EIS data (*.csv *.txt *.tsv *.dat *.asc *.dta *.xlsx *.xls);;"
            "ASCII text (*.txt *.tsv *.csv *.dat *.asc *.dta);;"
            "Excel (*.xlsx *.xls);;All files (*)",
        )
        if not files:
            return
        rows = self._mott_schottky_file_rows()
        existing = {str(Path(entry["path"]).resolve()) for entry in rows}
        for filename in files:
            path = Path(filename)
            if str(path.resolve()) in existing:
                continue
            potential = potential_from_filename(path)
            rows.append({
                "path": path,
                "potential_text": (
                    f"{potential:.10g}" if potential is not None else ""
                ),
                "potential_origin": (
                    "filename" if potential is not None else "automatic"
                ),
                "source": (
                    "filename" if potential is not None
                    else "automatic: embedded/filename"
                ),
                "status": (
                    "Ready" if potential is not None
                    else "Type DC volts or use embedded potential"
                ),
            })
            existing.add(str(path.resolve()))
        self._set_mott_schottky_file_rows(rows)
        self.ms_file_label.setText(
            f"Bias-file table: {len(rows)} file(s); edit DC values in results"
        )
        self.tabs.setCurrentWidget(self.ms_page)

    def calculate_mott_schottky_from_file_table(self):
        rows = self._mott_schottky_file_rows()
        if not rows:
            self._error("Add EIS files to the bias-file table first.")
            return
        paths: list[Path] = []
        potentials: list[float | None] = []
        invalid_rows: list[int] = []
        for row_index, entry in enumerate(rows, 1):
            paths.append(Path(entry["path"]))
            origin = str(entry.get("potential_origin", "automatic"))
            text = str(entry.get("potential_text", "")).strip().replace(",", ".")
            if origin == "invalid":
                invalid_rows.append(row_index)
                potentials.append(None)
            elif origin == "table":
                try:
                    value = float(text)
                    if not np.isfinite(value):
                        raise ValueError
                    potentials.append(value)
                except ValueError:
                    invalid_rows.append(row_index)
                    potentials.append(None)
            else:
                potentials.append(None)
        if invalid_rows:
            self._error(
                "Invalid DC potential in bias-file row(s): "
                + ", ".join(map(str, invalid_rows))
            )
            return
        try:
            extracted = read_eis_potential_series(
                paths,
                potential_values_V=potentials,
                target_frequency_hz=self.ms_frequency.value(),
                max_frequency_deviation_percent=(
                    self.ms_frequency_tolerance.value()
                ),
                potential_group_tolerance_V=(
                    self.ms_potential_tolerance.value() * 1e-3
                ),
                delimiter=self.delimiter_combo.currentData(),
                decimal=self.decimal_combo.currentData(),
                preserve_input_order=True,
            )
            skipped = extracted.attrs.get("skipped_files", [])
            for entry in rows:
                subset = extracted.loc[
                    extracted["source_file"].astype(str)
                    == str(Path(entry["path"]))
                ]
                if subset.empty:
                    entry["status"] = "Not used"
                    continue
                sources = ", ".join(sorted(set(
                    subset["potential_source"].astype(str)
                )))
                frequencies = subset["frequency_Hz"].to_numpy(float)
                entry["status"] = (
                    f"Used ({sources}); {np.min(frequencies):g}-"
                    f"{np.max(frequencies):g} Hz"
                )
                if len(subset) == 1 and not entry["potential_text"]:
                    entry["potential_text"] = (
                        f"{float(subset.iloc[0]['potential_V']):.10g}"
                    )
                    entry["potential_origin"] = "detected"
                    entry["source"] = str(
                        subset.iloc[0]["potential_source"]
                    )
            self._set_mott_schottky_file_rows(rows)
            self._set_mott_schottky_data(
                extracted,
                f"{len(extracted)} common-frequency point(s) from {len(paths)} file(s)",
                paths,
            )
            for failure in skipped:
                self.log.appendPlainText("Mott-Schottky skipped: " + failure)
            self.run_mott_schottky()
        except Exception as exc:
            self._error(str(exc))

    def open_mott_schottky_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Open prepared Mott-Schottky data",
            "",
            "Mott-Schottky data (*.csv *.txt *.tsv *.dat *.asc *.dta *.xlsx *.xls);;"
            "ASCII text (*.txt *.tsv *.csv *.dat *.asc *.dta);;"
            "Excel (*.xlsx *.xls);;All files (*)",
        )
        if not file:
            return
        try:
            prepared = read_mott_schottky(
                file,
                delimiter=self.delimiter_combo.currentData(),
                decimal=self.decimal_combo.currentData(),
            )
            self._set_mott_schottky_data(
                prepared, f"Prepared table: {Path(file).name}", [Path(file)]
            )
            mapping = prepared.attrs.get("source_columns", {})
            self.log.appendPlainText(
                "\nLoaded prepared Mott-Schottky table. Mapping: "
                f"potential={mapping.get('potential_V')}; "
                f"C={mapping.get('capacitance_F')}; "
                f"f={mapping.get('frequency_Hz')}; "
                f"Z′={mapping.get('Zreal_ohm')}; Z″={mapping.get('Zimag_ohm')}."
            )
        except Exception as exc:
            self._error(str(exc))

    def use_full_mott_schottky_range(self):
        if self.ms_data is None or self.ms_data.empty:
            return
        potential = self.ms_data["potential_V"].to_numpy(float)
        self.ms_fit_min.setValue(float(np.nanmin(potential)))
        self.ms_fit_max.setValue(float(np.nanmax(potential)))

    def run_mott_schottky(self):
        if self.ms_data is None:
            self._error("Prepare a potential-capacitance series first.")
            return
        try:
            result = calculate_mott_schottky(
                self.ms_data,
                method=self.ms_method_combo.currentData(),
                fixed_frequency_hz=self.ms_frequency.value(),
                electrode_area_cm2=self.ms_area.value(),
                relative_permittivity=self.ms_epsilon.value(),
                temperature_K=self.ms_temperature.value(),
                fit_min_V=self.ms_fit_min.value(),
                fit_max_V=self.ms_fit_max.value(),
                input_capacitance_is_areal=(
                    self.ms_areal_input.isChecked()
                    and self.ms_method_combo.currentData() == "direct"
                ),
                use_area_normalized_plot=self.ms_normalized_plot.isChecked(),
                apply_thermal_correction=self.ms_thermal.isChecked(),
            )
            self.ms_result_df = result.data
            self.ms_stats = dict(result.statistics)
            self._show_mott_schottky_result()
            self._update_action_states()
        except Exception as exc:
            self._error(str(exc))

    def _show_mott_schottky_result(self):
        if self.ms_result_df is None or not self.ms_stats:
            return
        stats = self.ms_stats
        confidence_percent = 100.0 * float(stats["confidence_level"])
        metric_rows = [
            ("Slope-sign classification", stats["semiconductor_type_from_slope"]),
            ("Apparent carrier density / cm⁻³", stats["carrier_density_cm_minus3"]),
            (
                f"Carrier density {confidence_percent:g}% CI / cm⁻³",
                (
                    f"{stats['carrier_density_confidence_interval_low_cm_minus3']:.6g}"
                    f" to {stats['carrier_density_confidence_interval_high_cm_minus3']:.6g}"
                ),
            ),
            ("Flat-band potential / V", stats["flat_band_potential_V"]),
            (
                f"Flat-band {confidence_percent:g}% CI / V",
                (
                    f"{stats['flat_band_confidence_interval_low_V']:.6g}"
                    f" to {stats['flat_band_confidence_interval_high_V']:.6g}"
                ),
            ),
            ("Slope", stats["slope"]),
            ("Slope standard error", stats["slope_standard_error"]),
            ("Intercept", stats["intercept"]),
            ("R²", stats["r_squared"]),
            ("RMSE", stats["rmse"]),
            ("Fit points", stats["fit_points"]),
            (
                "Fit potential range / V",
                f"{stats['fit_min_V']:.8g} to {stats['fit_max_V']:.8g}",
            ),
            ("Capacitance method", stats["capacitance_method"]),
            ("Fit basis", stats["fit_basis"]),
            ("Electrode area / cm²", stats["electrode_area_cm2"]),
            ("Relative permittivity εr", stats["relative_permittivity"]),
            ("Temperature / K", stats["temperature_K"]),
            ("Thermal correction applied", stats["thermal_correction_applied"]),
            ("Data source", stats.get("source_kind", "prepared potential table")),
        ]
        warnings = tuple(stats.get("warnings", ()))
        metric_rows.append(("Scientific warnings", " | ".join(warnings)))
        self.ms_metric_table.setRowCount(len(metric_rows))
        for row, (label, value) in enumerate(metric_rows):
            self.ms_metric_table.setItem(row, 0, QTableWidgetItem(str(label)))
            self.ms_metric_table.setItem(
                row,
                1,
                numeric_item(value)
                if isinstance(value, (int, float, np.number))
                and not isinstance(value, bool)
                else QTableWidgetItem(str(value)),
            )
        self._df_to_table(self.ms_result_df, self.ms_data_table)

        palette = get_palette(self.theme_name)
        frame = self.ms_result_df
        x = frame["potential_V"].to_numpy(float)
        y = frame["mott_schottky_y"].to_numpy(float)
        selected = frame["fit_selected"].to_numpy(bool)
        fig = self.ms_plot.figure
        fig.clear()
        ax = fig.add_subplot(111)
        if np.any(~selected):
            ax.scatter(
                x[~selected], y[~selected], s=26, label="Excluded",
                color=palette.muted_text,
            )
        ax.scatter(
            x[selected], y[selected], s=34, label="Selected depletion region",
            color=palette.measured,
        )
        line_x = np.linspace(
            float(np.min(x[selected])), float(np.max(x[selected])), 200
        )
        line_y = stats["slope"] * line_x + stats["intercept"]
        ax.plot(
            line_x, line_y, linewidth=2.2,
            label=f"OLS fit (R²={stats['r_squared']:.5f})",
            color=palette.fit,
        )
        ax.axvline(
            stats["flat_band_potential_V"], linestyle="--", linewidth=1.5,
            label=f"Efb={stats['flat_band_potential_V']:.5g} V",
            color=palette.secondary,
        )
        ax.set_xlabel("Potential / V")
        ax.set_ylabel(f"Mott-Schottky ordinate / {stats['fit_y_unit']}")
        ax.set_title("Mott-Schottky depletion-region analysis")
        ax.grid(True, alpha=.25)
        ax.legend()
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
        self._finish_plot(self.ms_plot)
        self.empty_state.setVisible(False)
        self.plot_tabs.setCurrentWidget(self.ms_plot)
        self.tabs.setCurrentIndex(0)
        self.log.appendPlainText(
            "\nMott-Schottky result: "
            f"{stats['semiconductor_type_from_slope']}; "
            f"Napp={stats['carrier_density_cm_minus3']:.6g} cm^-3; "
            f"Efb={stats['flat_band_potential_V']:.6g} V; "
            f"R²={stats['r_squared']:.6g}."
        )
        for warning in warnings:
            self.log.appendPlainText("  Scientific caution: " + warning)
        self.statusBar().showMessage("Mott-Schottky calculation complete")

    def _df_to_batch_table(self, df: pd.DataFrame):
        table = self.batch_table
        table.blockSignals(True)
        try:
            table.setRowCount(len(df))
            table.setColumnCount(len(df.columns))
            table.setHorizontalHeaderLabels([str(column) for column in df.columns])
            for row_index, (_, row) in enumerate(df.iterrows()):
                for column_index, column in enumerate(df.columns):
                    value = row[column]
                    if column == "DC_potential_V":
                        item = QTableWidgetItem(
                            "" if pd.isna(value) else f"{float(value):.10g}"
                        )
                        item.setToolTip(
                            "Editable DC bias in volts for Mott-Schottky handoff."
                        )
                    elif (
                        isinstance(value, (int, float, np.number))
                        and not isinstance(value, bool)
                    ):
                        item = numeric_item(value)
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    else:
                        item = QTableWidgetItem(str(value))
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row_index, column_index, item)
            table.resizeColumnsToContents()
        finally:
            table.blockSignals(False)

    def _sync_batch_dc_table(self) -> list[int]:
        if self.batch_df is None or "DC_potential_V" not in self.batch_df:
            return []
        dc_column = list(self.batch_df.columns).index("DC_potential_V")
        invalid_rows: list[int] = []
        for row_index in range(len(self.batch_df)):
            item = self.batch_table.item(row_index, dc_column)
            text = item.text().strip().replace(",", ".") if item else ""
            if not text:
                self.batch_df.at[
                    self.batch_df.index[row_index], "DC_potential_V"
                ] = np.nan
                continue
            try:
                value = float(text)
                if not np.isfinite(value):
                    raise ValueError
            except ValueError:
                invalid_rows.append(row_index + 1)
                continue
            self.batch_df.at[
                self.batch_df.index[row_index], "DC_potential_V"
            ] = value
            self.batch_df.at[
                self.batch_df.index[row_index], "DC_potential_source"
            ] = "batch results table"
        return invalid_rows

    def run_mott_schottky_from_batch_results(self):
        if self.batch_df is None or self.batch_df.empty:
            self._error("Run batch fitting first.")
            return
        required = {"file", "DC_potential_V", "fit_capacitance_F"}
        missing = sorted(required.difference(self.batch_df.columns))
        if missing:
            self._error(
                "Rerun batch fitting to create Mott-Schottky columns: "
                + ", ".join(missing)
            )
            return
        invalid_rows = self._sync_batch_dc_table()
        if invalid_rows:
            self._error(
                "Invalid DC potential in Batch results row(s): "
                + ", ".join(map(str, invalid_rows))
            )
            return
        try:
            prepared = prepare_mott_schottky_from_batch_results(self.batch_df)
            methods = sorted(set(
                prepared.get("fit_capacitance_method", pd.Series(dtype=str)).astype(str)
            ))
            models = sorted(set(
                prepared.get("batch_model", pd.Series(dtype=str)).astype(str)
            ))
            self.ms_method_combo.setCurrentIndex(
                self.ms_method_combo.findData("direct")
            )
            self.ms_areal_input.setChecked(False)
            self._set_mott_schottky_data(
                prepared,
                f"Batch-fit capacitance: {len(prepared)} bias spectra",
                [Path(value) for value in prepared["source_file"]],
            )
            self.log.appendPlainText(
                "\nMott-Schottky input prepared from batch fitted capacitance: "
                + "; ".join(methods)
            )
            if len(methods) > 1 or len(models) > 1:
                self.log.appendPlainText(
                    "  Scientific caution: models or capacitance definitions differ "
                    "across bias; confirm that every value represents the same process."
                )
            self.run_mott_schottky()
        except Exception as exc:
            self._df_to_batch_table(self.batch_df)
            self.tabs.setCurrentWidget(self.batch_table)
            self._error(str(exc))

    def _update_circuit_info(self):
        self._save_manual_state()
        key=self.model_combo.currentData()
        if key not in CIRCUITS:
            return
        spec=CIRCUITS[key]
        values, locks = self._manual_state_for_model(key)
        self._manual_model_key = key
        self.circuit_diagram.set_diagram(spec.diagram)
        self.circuit_diagram.set_values(values, {p.name:p.unit for p in spec.params})
        self.manual_editor.set_spec(spec, values, locks)
        self.circuit_label.setText(f"<b>{spec.expression}</b><br>{spec.description}")
        self._update_action_states()

    def choose_batch_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Choose batch folder")
        if folder:
            self.batch_folder.setText(folder)
            if not self.paired_output.text().strip():
                self.paired_output.setText(str(Path(folder) / "EIS_Gold_ST_Reports"))

    def choose_paired_output_folder(self):
        start = self.paired_output.text().strip() or self.batch_folder.text().strip()
        folder = QFileDialog.getExistingDirectory(self, "Choose ST report output folder", start)
        if folder:
            self.paired_output.setText(folder)

    def run_paired_st_analysis(self):
        input_text = self.batch_folder.text().strip()
        input_folder = Path(input_text) if input_text else None
        if input_folder is None or not input_folder.is_dir():
            self._error("Choose a valid input folder containing ST1-A, ST1-B, ST2-A, ST2-B… files.")
            return
        output_text = self.paired_output.text().strip()
        output_folder = Path(output_text) if output_text else input_folder / "EIS_Gold_ST_Reports"
        self.paired_output.setText(str(output_folder))

        model_key = self.model_combo.currentData()
        if not self.paired_auto.isChecked():
            spec = CIRCUITS.get(model_key)
            if spec is None or not any(param.name == "Rct" for param in spec.params):
                self._error(
                    "The selected fixed circuit has no explicit Rct parameter. "
                    "Choose an Rct circuit or enable Rct-compatible auto-fit."
                )
                return

        self._busy_operation = "paired analysis"
        self._update_action_states()
        self.paired_progress.setValue(0)
        self.paired_worker = PairedSTWorker(
            input_folder,
            output_folder,
            model_key,
            self.paired_auto.isChecked(),
            self._settings(),
            rct_safe_auto=True,
            parent=self,
        )
        self.paired_worker.progress.connect(
            lambda percent, name: (
                self.paired_progress.setValue(percent),
                self.statusBar().showMessage(f"ST paired analysis: {name}"),
            )
        )
        self.paired_worker.completed.connect(self._paired_st_done)
        self.paired_worker.failed.connect(self._paired_st_failed)
        self.paired_worker.start()

    def _paired_st_done(self, bundle: PairedAnalysisBundle):
        self.batch_df = bundle.file_results
        self.paired_rct_df = bundle.rct_summary
        self.paired_output_dir = bundle.output_dir
        self._df_to_batch_table(bundle.file_results)
        self._df_to_table(bundle.rct_summary, self.paired_table)
        self.tabs.setCurrentWidget(self.paired_table)
        self._busy_operation = None
        self.paired_progress.setValue(100)
        complete = int((bundle.rct_summary.get("status") == "complete").sum()) if not bundle.rct_summary.empty else 0
        self.log.appendPlainText(
            f"ST A/B analysis complete: {len(bundle.file_results)} files, {complete} complete pairs."
        )
        self.log.appendPlainText(f"TXT reports saved to: {bundle.output_dir}")
        for warning in bundle.warnings:
            self.log.appendPlainText("ST report warning: " + warning)
        self._update_action_states()
        self.statusBar().showMessage(f"ST reports saved to {bundle.output_dir}")

    def _paired_st_failed(self, text):
        self._busy_operation = None
        self._update_action_states()
        self._error(text)

    def open_paired_output_folder(self):
        text = self.paired_output.text().strip()
        folder = self.paired_output_dir if self.paired_output_dir is not None else (Path(text) if text else None)
        if folder is None or not Path(folder).is_dir():
            self._error("The ST report output folder does not exist yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(folder).resolve())))

    def run_batch(self):
        folder_text=self.batch_folder.text().strip(); folder=Path(folder_text) if folder_text else None
        if folder is None or not folder.is_dir(): self._error("Choose a valid batch folder."); return
        supported={".csv", ".txt", ".tsv", ".dat", ".asc", ".dta", ".xlsx", ".xls"}
        files=sorted(
            [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in supported],
            key=lambda path:path.name.lower(),
        )
        if not files:self._error("No supported files found in the selected folder.");return
        self._busy_operation = "batch analysis"
        self._update_action_states()
        self.batch_progress.setValue(0)
        self.worker=BatchWorker(files,self.model_combo.currentData(),self.batch_auto.isChecked(),self._settings(),self)
        self.worker.progress.connect(lambda p,name:(self.batch_progress.setValue(p),self.statusBar().showMessage(f"Batch: {name}")))
        self.worker.completed.connect(self._batch_done); self.worker.failed.connect(self._batch_failed); self.worker.start()

    def _batch_done(self,df):
        self.batch_df=df; self._df_to_batch_table(df); self.tabs.setCurrentWidget(self.batch_table); self._busy_operation=None; self.batch_progress.setValue(100)
        potentials = int(pd.to_numeric(df.get("DC_potential_V"), errors="coerce").notna().sum())
        capacitances = int((pd.to_numeric(df.get("fit_capacitance_F"), errors="coerce") > 0).sum())
        self.log.appendPlainText(
            f"Batch analysis complete: {len(df)} files; {potentials} DC potentials; "
            f"{capacitances} supported fitted capacitances."
        ); self.statusBar().showMessage("Batch complete")
        self._plot_calibration_from_batch()
        self._update_action_states()

    def _batch_failed(self,text):
        self._busy_operation=None; self._update_action_states(); self._error(text)

    def _plot_calibration_from_batch(self):
        if self.batch_df is None or "concentration" not in self.batch_df: return
        df=self.batch_df.dropna(subset=["concentration"])
        if len(df)<3:return
        candidates=[c for c in ("Rct","R1","Rs") if c in df.columns]
        if not candidates:return
        ycol=candidates[0]; x=df["concentration"].to_numpy(float); y=df[ycol].to_numpy(float)
        try: stats=calibration(x,y)
        except ValueError:return
        self.calibration_stats=dict(stats)
        self.calibration_df=pd.DataFrame({
            "concentration":x,
            "concentration_unit":df["concentration_unit"].astype(str).to_numpy(),
            "response_parameter":ycol,
            "response_ohm":y,
            "predicted_response_ohm":stats["intercept"]+stats["slope"]*x,
            "calibration_residual_ohm":y-(stats["intercept"]+stats["slope"]*x),
        })
        xx=np.linspace(x.min(),x.max(),200); yy=stats["intercept"]+stats["slope"]*xx
        palette=get_palette(self.theme_name)
        fig=self.cal_plot.figure; fig.clear(); ax=fig.add_subplot(111); ax.scatter(x,y,s=36,color=palette.measured,label="Batch data"); ax.plot(xx,yy,linewidth=2,color=palette.fit,label="Linear fit")
        ax.set_xlabel(f"Concentration / {df['concentration_unit'].dropna().iloc[0] if df['concentration_unit'].notna().any() else 'filename unit'}"); ax.set_ylabel(f"{ycol} / Ω")
        ax.set_title(f"Calibration: R²={stats['r2']:.5f}; LOD={stats['LOD_3.3syx_slope']:.4g}"); ax.grid(True,alpha=.25); ax.legend(); self._finish_plot(self.cal_plot)
        self.log.appendPlainText("Calibration from batch filenames: "+", ".join(f"{k}={v:.5g}" for k,v in stats.items()))

    def _df_to_table(self,df,table):
        from PySide6.QtWidgets import QTableWidgetItem
        table.setRowCount(len(df)); table.setColumnCount(len(df.columns)); table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for i,(_,row) in enumerate(df.iterrows()):
            for j,c in enumerate(df.columns):
                v=row[c]; table.setItem(i,j,numeric_item(v) if isinstance(v,(int,float,np.number)) and not isinstance(v,bool) else QTableWidgetItem(str(v)))
        table.resizeColumnsToContents()

    def _fit_metrics_dict(self):
        if self.fit_result is None:
            return {}
        r=self.fit_result
        return {
            "Model":r.model_name,"Model key":r.model_key,"Success":r.success,
            "RMSE_ohm":r.rmse,
            "Pseudo_chi_square_Zmod":r.pseudo_chi2,
            "Reduced_chi_square_Zmod":r.red_chi2,
            "Relative_residual_RMS_percent":r.relative_rmse_percent,
            "Chi_square_degrees_of_freedom_N_minus_k":r.chi2_dof,
            "Legacy_raw_reduced_variance_ohm2":r.raw_red_var,
            "RSS_ohm2":r.rss,
            "AICc":r.aicc,"BIC":r.bic,"Residual structure":r.residual_score,
            "Physical penalty":r.physical_score,"Rank score":r.rank_score,
            "Fixed parameters":", ".join(r.fixed_params) or "None",
            "Free parameters":len(CIRCUITS[r.model_key].params)-len(r.fixed_params),
            "Warnings":" | ".join(r.warnings) if r.warnings else "None",
            "Max_abs_parameter_correlation":r.max_abs_correlation,
            "Jacobian_condition":r.jacobian_condition,
            "Evaluations":r.nfev,"Optimizer message":r.message,
            "Weighting":self.weight_combo.currentText(),"Robust loss":self.loss_combo.currentText(),
            "Optimizer":self.optimizer_combo.currentText(),
            "Multi-starts":self.multistart_spin.value(),"Maximum evaluations":self.nfev_spin.value(),
        }

    def _analysis_frames(self):
        """Collect every available numerical result as named DataFrames."""
        frames: dict[str, pd.DataFrame] = {}
        key = self.model_combo.currentData()
        if key in CIRCUITS and hasattr(self, "manual_editor"):
            spec = CIRCUITS[key]
            manual_values = self.manual_editor.values()
            manual_locks = self.manual_editor.locks()
            frames["Manual circuit settings"] = pd.DataFrame([
                {
                    "model_key": key, "model_name": spec.name, "expression": spec.expression,
                    "parameter": p.name, "label": p.label, "value": manual_values.get(p.name, np.nan),
                    "unit": p.unit, "locked": p.name in manual_locks,
                    "used_as_start": self.manual_start_check.isChecked(),
                }
                for p in spec.params
            ])
        if self.data is not None:
            imported=self.data.copy()
            f,z=self._current_arrays()
            imported["Zimag_used_for_fitting_ohm"]=z.imag
            imported["Z_magnitude_calculated_ohm"]=np.abs(z)
            imported["phase_calculated_deg"]=np.angle(z,deg=True)
            frames["Imported data"]=imported

            checks=consistency_checks(f,z)
            frames["Consistency checks"]=pd.DataFrame(
                [{"diagnostic":key,"value":value} for key,value in checks.items()]
            )
            signature=diffusion_signature(f,z)
            frames["Diffusion signature"]=pd.DataFrame(
                [{"diagnostic":key,"value":value} for key,value in signature.items()]
            )

        if self.data is not None and self.fit_result is not None:
            f,z=self._current_arrays(); r=self.fit_result
            fit_data=pd.DataFrame({
                "frequency_Hz":f,
                "Zreal_measured_ohm":z.real,
                "Zimag_measured_ohm":z.imag,
                "minus_Zimag_measured_ohm":-z.imag,
                "Z_magnitude_measured_ohm":np.abs(z),
                "phase_measured_deg":np.angle(z,deg=True),
                "Zreal_fit_ohm":r.z_fit.real,
                "Zimag_fit_ohm":r.z_fit.imag,
                "minus_Zimag_fit_ohm":-r.z_fit.imag,
                "Z_magnitude_fit_ohm":np.abs(r.z_fit),
                "phase_fit_deg":np.angle(r.z_fit,deg=True),
                "residual_real_ohm":r.residual_complex.real,
                "residual_imag_ohm":r.residual_complex.imag,
                "residual_magnitude_ohm":np.abs(r.residual_complex),
            })
            frames["Fitted spectrum"]=fit_data
            spec=CIRCUITS[r.model_key]
            parameter_rows=[]
            for parameter in spec.params:
                value=r.params[parameter.name]
                stderr=r.stderr.get(parameter.name,np.nan)
                parameter_rows.append({
                    "parameter":parameter.name,"label":parameter.label,"value":value,
                    "standard_error":stderr,
                    "relative_standard_error_percent":100*stderr/abs(value) if np.isfinite(stderr) and value else np.nan,
                    "unit":parameter.unit,
                    "locked_during_fit":parameter.name in r.fixed_params,
                })
            frames["Fit parameters"]=pd.DataFrame(parameter_rows)
            frames["Fit metrics"]=pd.DataFrame(
                [{"metric":key,"value":value} for key,value in self._fit_metrics_dict().items()]
            )
        if self.ranking:
            frames["Model ranking"]=pd.DataFrame([result.summary_row() for result in self.ranking])
        if self.batch_df is not None:
            frames["Batch results"]=self.batch_df.copy()
        if self.paired_rct_df is not None:
            frames["ST Rct A-B summary"]=self.paired_rct_df.copy()
        if self.drt_df is not None:
            frames["DRT distribution"]=self.drt_df.copy()
        if self.drt_reconstruction_df is not None:
            frames["DRT reconstruction"]=self.drt_reconstruction_df.copy()
        if self.calibration_df is not None:
            frames["Calibration data"]=self.calibration_df.copy()
        if self.calibration_stats:
            frames["Calibration statistics"]=pd.DataFrame(
                [{"metric":key,"value":value} for key,value in self.calibration_stats.items()]
            )
        if self.ms_data is not None:
            frames["Mott-Schottky input"] = self.ms_data.copy()
        if self.ms_result_df is not None:
            frames["Mott-Schottky calculated"] = self.ms_result_df.copy()
        if self.ms_stats:
            frames["Mott-Schottky statistics"] = pd.DataFrame([
                {
                    "metric": key,
                    "value": (
                        " | ".join(map(str, value))
                        if isinstance(value, (tuple, list)) else value
                    ),
                }
                for key, value in self.ms_stats.items()
            ])

        plot_names=(
            "Nyquist", "Bode", "Residuals", "DRT plot",
            "Calibration plot", "Mott-Schottky plot",
        )
        for name,panel in zip(plot_names,self._plot_panels()):
            plot_frame=panel.data_frame()
            if not plot_frame.empty:
                frames[f"Plot data - {name}"]=plot_frame
        return frames

    @staticmethod
    def _safe_sheet_name(name: str, used: set[str]) -> str:
        cleaned="".join("_" if char in "[]:*?/\\" else char for char in str(name)).strip() or "Sheet"
        base=cleaned[:31]
        candidate=base
        counter=2
        while candidate.lower() in used:
            suffix=f"_{counter}"
            candidate=base[:31-len(suffix)]+suffix
            counter+=1
        used.add(candidate.lower())
        return candidate

    def _write_analysis_workbook(self, path: str | Path, frames: dict[str,pd.DataFrame] | None = None):
        frames=frames if frames is not None else self._analysis_frames()
        path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        used:set[str]=set()
        with pd.ExcelWriter(path,engine="openpyxl") as writer:
            if not frames:
                pd.DataFrame({"message":["No numerical data were available at export time."]}).to_excel(
                    writer,index=False,sheet_name="Summary"
                )
            for name,frame in frames.items():
                safe_frame=frame.copy()
                for column in safe_frame.columns:
                    safe_frame[column]=safe_frame[column].map(
                        lambda value: str(value) if isinstance(value,(dict,list,tuple,set)) else value
                    )
                sheet=self._safe_sheet_name(name,used)
                safe_frame.to_excel(writer,index=False,sheet_name=sheet)
                worksheet=writer.sheets[sheet]
                worksheet.freeze_panes="A2"
                worksheet.auto_filter.ref=worksheet.dimensions
                for cells in worksheet.iter_cols(min_row=1,max_row=min(worksheet.max_row,250),max_col=worksheet.max_column):
                    width=min(42,max(10,max(len(str(cell.value)) if cell.value is not None else 0 for cell in cells)+2))
                    worksheet.column_dimensions[cells[0].column_letter].width=width

    def _current_plot_panel(self):
        panel=self.plot_tabs.currentWidget()
        return panel if isinstance(panel,PlotPanel) else None

    def export_current_plot(self):
        panel=self._current_plot_panel()
        if panel is None:
            self._error("Select a plot tab before exporting.");return
        panel.export_plot_image()

    def export_current_plot_data(self):
        panel=self._current_plot_panel()
        if panel is None:
            self._error("Select a plot tab before exporting.");return
        panel.export_plot_data()

    def export_log(self):
        path,_=QFileDialog.getSaveFileName(self,"Export diagnostics log","eis_diagnostics_log.txt","Text file (*.txt)")
        if not path:return
        Path(path).write_text(self.log.toPlainText(),encoding="utf-8")
        self.statusBar().showMessage(f"Exported {path}")

    def export_fit(self):
        if self.data is None or self.fit_result is None:self._error("Fit a dataset before exporting.");return
        default=(self.current_file or Path("fit")).with_suffix(".fit.xlsx")
        path,_=QFileDialog.getSaveFileName(self,"Export fit workbook",str(default),"Excel workbook (*.xlsx)")
        if not path:return
        if not str(path).lower().endswith(".xlsx"):path=str(path)+".xlsx"
        self._write_analysis_workbook(path)
        self.log.appendPlainText(f"Exported complete fit workbook: {path}")
        self.statusBar().showMessage(f"Exported {path}")

    def export_analysis_package(self):
        if self.data is None and self.batch_df is None and self.ms_data is None:
            self._error("Load EIS or Mott-Schottky data before exporting a complete package.");return
        source_stem = (
            self.current_file.stem
            if self.current_file is not None
            else (
                self.ms_source_files[0].stem
                if self.ms_source_files else "eis_analysis"
            )
        )
        stem=source_stem+"_complete_export.zip"
        path,_=QFileDialog.getSaveFileName(self,"Export complete analysis package",stem,"ZIP archive (*.zip)")
        if not path:return
        output=Path(path)
        if output.suffix.lower()!=".zip":output=output.with_suffix(".zip")

        frames=self._analysis_frames()
        with tempfile.TemporaryDirectory(prefix="eis_gold_export_") as tmp:
            root=Path(tmp)/"EIS_Gold_Studio_Export"; root.mkdir()
            data_dir=root/"data_tables"; data_dir.mkdir()
            plots_dir=root/"plots"; plots_dir.mkdir()
            source_dir=root/"source"; source_dir.mkdir()
            paired_reports_dir=root/"ST_paired_TXT_reports"

            self._write_analysis_workbook(root/"complete_analysis.xlsx",frames)
            for name,frame in frames.items():
                safe="".join(char if char.isalnum() or char in "-_" else "_" for char in name).strip("_").lower()
                frame.to_csv(data_dir/f"{safe or 'table'}.csv",index=False)

            plot_map={
                "nyquist":self.nyquist,"bode":self.bode,"residuals":self.residual,
                "drt":self.drt_plot,"calibration":self.cal_plot,
                "mott_schottky":self.ms_plot,
            }
            exported_plots=[]
            for name,panel in plot_map.items():
                if not panel.figure.axes:
                    continue
                panel.save_figure(plots_dir/f"{name}.png",dpi=300)
                panel.save_figure(plots_dir/f"{name}.svg")
                panel.save_figure(plots_dir/f"{name}.pdf")
                plot_data=panel.data_frame()
                if not plot_data.empty:
                    plot_data.to_csv(plots_dir/f"{name}_plot_data.csv",index=False)
                exported_plots.append(name)

            self.circuit_diagram.save_diagram(root/"equivalent_circuit.png")
            try:
                self.circuit_diagram.save_diagram(root/"equivalent_circuit.svg")
            except Exception as exc:
                self.log.appendPlainText(f"SVG circuit export warning: {exc}")

            selected_key = self.model_combo.currentData()
            selected_spec = CIRCUITS.get(selected_key)
            if selected_spec is not None and selected_spec.metadata and selected_spec.metadata.get("tree"):
                circuit_payload = {
                    "name": selected_spec.name,
                    "expression": selected_spec.expression,
                    "tree": selected_spec.metadata["tree"],
                    "values": self.manual_editor.values(),
                    "locks": sorted(self.manual_editor.locks()),
                }
                (root/"custom_circuit.json").write_text(
                    json.dumps(circuit_payload, indent=2, ensure_ascii=False), encoding="utf-8"
                )

            (root/"diagnostics_audit_log.txt").write_text(self.log.toPlainText(),encoding="utf-8")
            if self.current_file is not None and self.current_file.exists():
                shutil.copy2(self.current_file,source_dir/self.current_file.name)
            copied_ms_sources = 0
            copied_names: set[str] = set()
            for source in self.ms_source_files:
                source = Path(source)
                if not source.exists() or not source.is_file():
                    continue
                name = source.name
                if name in copied_names:
                    name = f"{source.stem}_{copied_ms_sources + 1}{source.suffix}"
                shutil.copy2(source, source_dir / name)
                copied_names.add(name)
                copied_ms_sources += 1

            copied_paired_reports = 0
            if self.paired_output_dir is not None and self.paired_output_dir.is_dir():
                paired_reports_dir.mkdir()
                for report in sorted(self.paired_output_dir.glob("*.txt")):
                    shutil.copy2(report, paired_reports_dir / report.name)
                    copied_paired_reports += 1
                for report in sorted(self.paired_output_dir.glob("*.tsv")):
                    shutil.copy2(report, paired_reports_dir / report.name)
                    copied_paired_reports += 1

            manifest=[
                "EIS Gold Studio complete analysis export",
                f"Created: {datetime.now().astimezone().isoformat(timespec='seconds')}",
                f"Source file: {self.current_file if self.current_file else 'batch/no single source'}",
                f"Theme: {self.theme_name}",
                f"Selected circuit: {self.model_combo.currentText()}",
                f"Circuit expression: {CIRCUITS[self.model_combo.currentData()].expression if self.model_combo.currentData() in CIRCUITS else 'unknown'}",
                f"Locked parameters: {', '.join(sorted(self.manual_editor.locks())) or 'none'}",
                f"Fitted model: {self.fit_result.model_name if self.fit_result is not None else 'not fitted'}",
                f"Tables: {', '.join(frames.keys()) if frames else 'none'}",
                f"Plots: {', '.join(exported_plots) if exported_plots else 'none'}",
                f"ST paired TXT/TSV reports copied: {copied_paired_reports}",
                f"Mott-Schottky source files copied: {copied_ms_sources}",
                (
                    "Mott-Schottky apparent carrier density / cm^-3: "
                    f"{self.ms_stats.get('carrier_density_cm_minus3')}"
                    if self.ms_stats else "Mott-Schottky: not calculated"
                ),
                "Image formats: PNG 300 dpi, SVG vector, and PDF vector.",
                "CSV files are UTF-8 and the Excel workbook contains the same numerical outputs in separate sheets.",
            ]
            (root/"MANIFEST.txt").write_text("\n".join(manifest),encoding="utf-8")

            output.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                for file in root.rglob("*"):
                    if file.is_file():
                        archive.write(file,file.relative_to(root.parent))

        self.log.appendPlainText(f"Exported complete analysis package: {output}")
        self.statusBar().showMessage(f"Exported {output}")

    def export_batch(self):
        if self.batch_df is None:self._error("Run batch analysis first.");return
        path,_=QFileDialog.getSaveFileName(self,"Export batch results","batch_eis_results.xlsx","Excel workbook (*.xlsx);;CSV (*.csv);;TSV (*.tsv)")
        if not path:return
        lower=path.lower()
        if lower.endswith(".csv"):self.batch_df.to_csv(path,index=False)
        elif lower.endswith((".tsv",".txt")):self.batch_df.to_csv(path,index=False,sep="\t")
        else:
            if not lower.endswith(".xlsx"):path=path+".xlsx"
            self._write_analysis_workbook(path,{"Batch results":self.batch_df,**({"ST Rct A-B summary":self.paired_rct_df} if self.paired_rct_df is not None else {}),**({"Calibration data":self.calibration_df} if self.calibration_df is not None else {}),**({"Calibration statistics":pd.DataFrame([{"metric":k,"value":v} for k,v in self.calibration_stats.items()])} if self.calibration_stats else {})})
        self.statusBar().showMessage(f"Exported {path}")

    def reset_view(self):
        for panel in self._plot_panels():
            for ax in panel.figure.axes:
                ax.set_aspect("auto", adjustable="box")
                ax.relim(); ax.autoscale()
            self._finish_plot(panel)

    def _error(self,text):
        self.log.appendPlainText("ERROR: "+text)
        if not self.log_toggle.isChecked():
            self.log_toggle.setChecked(True)
        self._update_action_states()
        QMessageBox.critical(self,"EIS Gold Studio",text)
        self.statusBar().showMessage("Error")


def run():
    # Give Windows a stable taskbar identity so the bundled EXE consistently
    # uses the custom icon instead of a generic Python/Qt icon.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "AAfruz.EISGoldStudio"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("EIS Gold Studio")
    app.setApplicationDisplayName("EIS Gold Studio")
    app.setOrganizationName("EIS Gold Studio")
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")
    # Keep a persistent reference: Qt event filters can otherwise be garbage
    # collected. This blocks accidental wheel changes on every value/option
    # control while leaving normal scroll areas and Matplotlib interaction intact.
    app._wheel_change_blocker = WheelChangeBlocker(app)
    app.installEventFilter(app._wheel_change_blocker)
    settings = QSettings("EIS Gold Studio", "EIS Gold Studio")
    theme_name = str(settings.value("appearance/theme", "dark"))
    if theme_name not in {"light", "dark"}:
        theme_name = "dark"
    motion_enabled = settings.value("appearance/cinematic_motion", True, type=bool)
    app.setStyleSheet(get_stylesheet(theme_name))
    win = MainWindow(theme_name=theme_name, motion_enabled=motion_enabled)
    win.show()
    sys.exit(app.exec())
