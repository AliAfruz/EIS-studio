# EIS Gold Studio

**Version 1.13.2 · Research software · MIT License**

EIS Gold Studio is released as open research software by **Ali Afruz** (University of Mohaghegh Ardabili) and **Maryam Kaffash Jamshid**. The canonical repository is [github.com/AliAfruz/EIS-studio](https://github.com/AliAfruz/EIS-studio). If the software contributes to a publication, cite the archived software release described in [`CITATION.cff`](CITATION.cff). Zenodo metadata are provided in [`.zenodo.json`](.zenodo.json); the DOI must be added only after Zenodo has archived the first GitHub release.

The complete scientific equations, fitting algorithm, uncertainty treatment, TLM definition, Mott–Schottky workflow, global DC-series algorithm, and reporting limits are documented in [`docs/SCIENTIFIC_METHODS.md`](docs/SCIENTIFIC_METHODS.md). Validation requirements and known limitations are listed in [`docs/VALIDATION.md`](docs/VALIDATION.md).

> **Scientific scope:** automatic rankings, diffusion signatures, DRT peaks, TLM fits, and topology suggestions are screening evidence—not unique proof of a mechanism. The current consistency screen is not a formal Lin-KK implementation, and the modulus-normalized statistic is a pseudo-chi-square unless experimental variances are available.

Publication and DOI instructions are provided in [`docs/RELEASE_AND_ZENODO.md`](docs/RELEASE_AND_ZENODO.md).

A polished desktop GUI for electrochemical impedance spectroscopy (EIS) analysis, equivalent-circuit fitting, automatic model comparison, DRT screening, Mott-Schottky semiconductor analysis, batch processing and calibration.

## Highlights

- Cinematic glass interface with layered depth, luminous gold/cyan accents, and an animated impedance-inspired backdrop.
- Instant theme switching from the toolbar or **View → Dark mode** (`Ctrl+D`). The selected theme is restored at the next launch.
- Optional ambient motion and page transitions, controlled from the toolbar, **View → Cinematic motion**, or `Ctrl+M`.
- CSV, TXT, TSV, DAT, ASC, DTA and Excel import with automatic column detection.
- Automatic or manual ASCII delimiter handling for space, tab, comma, semicolon and colon, including dot/comma decimal separators.
- Nyquist, Bode, residual, DRT, calibration, and Mott-Schottky plots with padded Nyquist limits so edge points are not clipped.
- Equivalent-circuit visualization with live parameter labels and values.
- Manual value editing for every resistor, capacitor, CPE, inductor, and Warburg parameter, including optional parameter locking.
- Visual series/parallel circuit builder with automatic element naming, live wiring preview, and JSON save/load.
- Live circuit laboratory with real electrical symbols, direct terminal wiring, free movement, attached wires, docked Nyquist/Bode simulation, sensitivity glow, identifiability warnings, and measured-data overlay.
- Circuit library: R, R–C, Randles RC, Randles CPE, ideal and fractional Warburg, finite-length Warburg open/short, Gerischer, porous-electrode TLM open/short, two-time-constant, and inductive/adsorption branches.
- Hybrid fitting with optional differential-evolution global search followed by bounded least-squares refinement, robust losses, bounds, log-parameterization and multistart optimization.
- Advanced auto-fit runs in a background worker with a visible model-by-model progress bar to prevent GUI freezing.
- Dimensionless Z-modulus-normalized pseudo-χ² and reduced χ² reporting for scale-independent comparison.
- Automatic model ranking using AICc, BIC, residual structure, parameter uncertainty, physical plausibility, model complexity, and low-frequency diffusion screening.
- Batch analysis in a worker thread.
- Sequential `ST1-A` / `ST1-B`, `ST2-A` / `ST2-B` paired analysis with automatic per-file TXT reports and a combined `RctA − RctB` summary.
- Concentration extraction from filenames such as `cholesterol_2.5mM.csv` and automatic calibration.
- Screening-level consistency diagnostics and Tikhonov-regularized DRT.
- Mott-Schottky analysis from prepared capacitance, potential-stepped EIS, multiple bias files, collected single-bias studies, or batch-fitted equivalent-circuit capacitance.
- Apparent carrier density, flat-band potential, n/p slope classification, fit-window selection, 95% OLS confidence intervals, and explicit assumption/frequency/extrapolation warnings.
- Spreadsheet-style copy and export from every table, plus individual plot image/data export and a complete ZIP analysis package.
- Scrollable control/diagnostic regions.
- Mouse-wheel value changes are disabled globally for spin boxes, drop-down option lists, sliders, and dials. Scrolling the settings panel cannot silently change model, weighting, loss, DRT, or optimization settings.

## Installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

For an editable installation with the `eis-gold-studio` command:

```bash
python -m pip install -e .
eis-gold-studio
```

## Appearance

Use the **Dark mode** action on the main toolbar, choose **View → Dark mode**, or press `Ctrl+D`. The dark theme updates the complete Qt interface, Matplotlib plot backgrounds, axes, legends, tables, scroll areas, dialogs, and equivalent-circuit renderer. Switching themes does not clear loaded spectra or fitting results. The choice is saved automatically.

Version 1.9 introduces the cinematic glass shell. The default dark workspace uses animated light volumes, particles, an orbital EIS object, translucent analysis cards, live analysis-state feedback, and short page fades. Use **Cinematic motion** or `Ctrl+M` to pause every ambient animation; this setting is also restored at the next launch. Motion is visual only and never changes fitting, data, or export state.

Version 1.8 organizes the main controls into task-focused **Data**, **Fit**, **Circuit**, **Diagnostics**, and **Batch** pages. Advanced optimizer settings stay collapsed until needed, and unavailable actions remain disabled until their required data or result exists. The diagnostics log is collapsible so plots keep more vertical space. Supported EIS files can also be dragged directly onto the main window.

## Mott-Schottky semiconductor analysis

Version 1.10 adds a dedicated **Mott-Schottky** workflow. Input can come from:

- a prepared potential-capacitance table such as `sample_mott_schottky.csv`;
- a potential-stepped EIS table containing potential, frequency, Z real, and Z imaginary;
- multiple ordinary EIS files whose DC potentials are embedded, encoded in names such as `sample_-0.20V.csv`, or entered in the editable bias-file table;
- single-bias spectra collected one at a time with a confirmed DC potential;
- batch-fit capacitance from a physically assigned ideal capacitor or supported parallel R||CPE arc.

Choose the target frequency, permitted mismatch, electrode area, relative permittivity, temperature, and the potential limits of the physically justified linear depletion region. The result reports slope-sign classification, apparent carrier density, flat-band potential, R², standard errors, and 95% OLS confidence intervals. Every point records the actual selected frequency and conversion method.

The software deliberately labels the density as **apparent**. Classical interpretation assumes a planar depletion layer, known permittivity, space-charge capacitance dominating the measured response, and negligible Helmholtz/surface-state effects. Frequency dependence, rough/nanostructured geometry, or an unjustified linear window can produce plausible-looking but nonphysical values; warnings are therefore shown in the table, audit log, and exports.

## ASCII text import and delimiters

The **Data** panel contains two import selectors:

- **Column delimiter:** Auto-detect, Space/whitespace, Tab, Comma, Semicolon, or Colon.
- **Decimal separator:** Auto-detect, Dot, or Comma.

Auto-detect is recommended for routine work. The importer examines the header and multiple numerical rows instead of relying only on the filename extension. This avoids common errors such as treating decimal commas as column separators in semicolon-delimited European exports. The diagnostics log records the selected delimiter, decimal separator, encoding, column mapping, and any sign conversions.

Examples supported include:

```text
Index<TAB>Frequency (Hz)<TAB>Z' (Ω)<TAB>-Z'' (Ω)
Index;Frequency (Hz);Z' (Ω);-Z'' (Ω)
Index,Frequency (Hz),Z' (Ω),-Z'' (Ω)
Index:Frequency (Hz):Z' (Ω):-Z'' (Ω)
Index Frequency (Hz) Z' (Ω) -Z'' (Ω)
```

For decimal-comma data, use a non-comma column delimiter such as semicolon, tab, colon, or space. Manual selection remains available for unusual or ambiguous instrument exports. Batch analysis uses the same automatic delimiter and decimal detection for every file.




## Finite diffusion and hybrid fitting

Version 1.7.1 keeps the finite-length diffusion update and fixes Nyquist zoom-out plus numerical overflow warnings in finite-diffusion/TLM calculations. Version 1.7.0 added finite-length diffusion and distributed-transport models for spectra where a simple semi-infinite or fractional Warburg tail underfits the low-frequency branch. The new predefined circuits include `Rₛ + (Rct ∥ CPE) + Wₒ`, `Rₛ + (Rct ∥ CPE) + Wₛ`, `Rₛ + [CPE ∥ (Rct + Wₒ)]`, `Rₛ + (R₁ ∥ CPE₁) + (R₂ ∥ CPE₂) + Wₒ`, Gerischer variants, TLM variants, and an optional `Rads ∥ Lads` inductive adsorption branch.

Use `Wₒ` when the low-frequency branch bends toward a near-vertical blocking response. Use `Wₛ` when the diffusion branch tends toward a finite resistive termination. Gerischer and TLM models are available for coupled reaction–diffusion and porous/thick-film distributed charging. These models can improve curvature reproduction, but they should only be interpreted mechanistically when parameter errors, bounds, correlations, residuals, and frequency-window coverage are acceptable.

The optimizer selector provides two modes:

- **Hybrid global + bounded LS:** differential evolution searches the broad bounded parameter space, then bounded least-squares refines the best candidates.
- **Bounded LS multistart only:** faster local fitting from data-derived and jittered starts.

The fit-quality table now reports warnings for parameters near bounds, large relative errors, strong parameter correlation, time constants outside the measured frequency window, structured residuals, and physically suspicious models.


## Normalized chi-square reporting

Version 1.6.0 replaces the old impedance-scale-dependent value previously labeled as reduced chi-square. The main fit-quality table now reports a dimensionless Z-modulus-normalized EIS pseudo chi-square:

```text
chi2_pseudo = sum(((dZreal)^2 + (dZimag)^2) / |Zmeasured|^2)
chi2_red    = chi2_pseudo / (N - k)
```

Here, `N` is the number of complex frequency points and `k` is the number of free circuit parameters. The software also reports the relative residual RMS percentage:

```text
relative_RMS_percent = 100 * sqrt(chi2_pseudo / N)
```

This definition is dimensionless and invariant to changing impedance units from ohms to kilo-ohms. It is calculated after optimization from ordinary squared complex residuals, so it remains directly interpretable even when a robust loss was used during fitting. It is intended for comparison with EIS programs that use the same Z-modulus normalization and `N - k` degrees-of-freedom convention. Exact numerical agreement is not guaranteed when another program uses different weighting, residual definitions, frequency selections, parameter constraints, or degrees of freedom.

The former quantity is retained transparently as **Legacy raw reduced variance / ohm^2** so older results can still be traced. The normalized value is a pseudo chi-square, not a formal statistical chi-square unless the normalization values represent measured standard deviations.

## Manual element values and locked fitting

The **Manual element values and locks** panel is synchronized with the selected circuit. Every parameter can be edited directly in scientific notation. This includes resistance, capacitance, CPE magnitude and exponent, inductance, ideal Warburg coefficient, and fractional-Warburg coefficient and exponent.

- Displayed values are used as optimizer starting guesses when **Use displayed values as fitting starts** is enabled.
- Check **Lock** beside a parameter to remove it from optimization and keep it fixed at the displayed value.
- **Estimate from data** restores data-derived starting guesses.
- **Use fitted values** copies the latest result back into the editor.
- **Preview manual curve** draws the impedance response without changing the fit result.
- The equivalent-circuit drawing updates with the edited numerical values.

Locked parameters are reported in the fit-quality table, workbook, CSV exports, audit log, and complete analysis package. If every parameter is locked, the software performs a direct manual-model evaluation with zero optimizer iterations.

## Visual circuit builder

Open the builder from the toolbar, **Circuit → Circuit composer**, the visualization panel, or `Ctrl+B`. Version 1.12 provides a freeform electrical-schematic workflow:

1. Drag a real `R`, `C`, `CPE`, `L`, diffusion, Gerischer, or TLM symbol from the **Element deck** onto a pulsing `+` portal in the **Live schematic workspace**.
2. Drop on the portal before/after a symbol or inside a branch to insert at that exact electrical location. The attached wires and parallel rails update immediately.
3. Move a placed symbol anywhere on the grid; its wires follow live. Release it near another glowing portal to rewire the underlying validated topology.
4. Use the mouse wheel to zoom, middle-drag to pan, **Fit circuit** to frame the drawing, or **Auto-layout** to clear free positions and restore a clean schematic arrangement.
5. Add branches, duplicate elements, start from an empty path, or use `Ctrl+Z`/`Ctrl+Y` to undo and redo topology or layout edits.
6. Select a symbol on the canvas to edit values and locks; the compact **Topology navigator** stays synchronized for scientific inspection and accessible editing.
7. Apply the validated circuit to the main fitting workspace.

Parallel blocks are drawn as explicit wired branches, and each branch can contain a series chain of elements. Custom circuits use the same complex nonlinear least-squares, robust-loss, residual, uncertainty, plot, and export tools as the built-in circuits. Circuit definitions can be saved to and loaded from JSON. The package includes `sample_manual_circuit.json` as a ready-to-load example. Custom-circuit JSON is also included in the complete export package. Empty branches and duplicate parameter names are rejected before fitting.

## Live circuit laboratory

Version 1.13 turns the schematic composer into a live EIS sandbox:

- Drag a luminous wire from an output terminal to another element's input terminal to form/reorder a series connection. Connecting matching terminal sides automatically creates a validated parallel block when both elements share a path.
- The dedicated right-panel Plot tab switches between Nyquist and Bode views, overlays loaded measurements, displays live RMSE, and provides a frequency cursor. The canvas Monitor button opens this tab; clicking a simulated curve point or moving the cursor updates sensitivity glow on the circuit symbols.
- Every parameter has a logarithmic or linear live slider based on its scientific bounds. **Fit measured** runs the current custom circuit directly against the loaded spectrum while respecting locked values.
- Symbol status markers screen fitted uncertainty, proximity to parameter bounds, and response sensitivity. Tooltips explain the evidence; red or amber states are diagnostics, not proof that a mechanism is invalid.
- The hypothesis panel screens diffusion, inductive response, multiple time constants, DRT peak candidates, structured mismatch, and poor CPE identifiability. These are explicitly hypotheses that require residual, uncertainty, and physical review.
- **DC global fit** loads multiple bias spectra and assigns each parameter as shared, independent, or smooth versus potential. The resulting parameter/DC table and trend plot can be exported, and shared/median values can be returned to the circuit.
- Professional tools include grid snapping, rubber-band selection, row/column alignment, copy/paste, annotations, templates, a minimap, and publication export to vector SVG/PDF or PNG.

## Clipboard and export

Every data table, parameter table, fit-quality table, model-ranking table and results table behaves like a spreadsheet-style grid. Numerical result cells are read-only; the Mott-Schottky bias table and `DC_potential_V` batch cells are intentionally editable:

- Press **Ctrl+C** to copy the selected cells as tab-delimited text for direct pasting into Excel, Origin, Prism or a text editor.
- Right-click for **Copy selected cells**, **Copy with headers**, **Copy selected rows**, **Copy entire table**, **Select all**, **Export selected cells**, or **Export complete table**.
- Table exports support `.xlsx`, comma-delimited `.csv`, and tab-delimited `.tsv`.

Each Nyquist, Bode, residual, DRT, calibration, and Mott-Schottky plot has toolbar buttons and a right-click menu for:

- copying the rendered plot image to the clipboard;
- saving publication-ready PNG, SVG, PDF, JPEG or TIFF files;
- copying every plotted series as tab-delimited long-form data;
- exporting plotted data to Excel, CSV or TSV.

The equivalent-circuit drawing can also be copied or exported as PNG, SVG or JPEG by right-clicking it.

Use **Export all** on the main toolbar, **Export → Complete analysis package**, or `Ctrl+Shift+E` to create one ZIP archive containing:

- a multi-sheet Excel workbook;
- separate CSV tables for imported data, manual values/locks, fitted spectra, residuals, parameters, quality metrics, model ranking, DRT, calibration and plotted series;
- each available plot as 300-dpi PNG, SVG and PDF;
- the equivalent-circuit image and, for user-built models, the reusable custom-circuit JSON;
- the source data file;
- the diagnostics/audit log and an export manifest.

## Input format

The program recognizes common column names. A simple file can use:

```text
frequency_Hz,Zreal_ohm,Zimag_ohm
100000,12.1,-0.5
...
```

If your potentiostat exports `-Zimag` or `-Z''`, the importer automatically converts it to the conventional complex-imaginary sign. The GUI also provides a manual “Invert imaginary sign” switch.

Potentiostat tables using this structure are also supported directly:

```text
Potential (V)    Frequency (Hz)    |Z| (ohms)    Zre (ohms)    Zim (ohms)
0.188445196      100000            5.627956662   4.826872826   2.893992901
```

Potential is retained as optional metadata and `Potential (mV)` is converted to volts, while `Zre` and `Zim` are mapped to real and imaginary impedance. A column named `Zim` keeps its supplied sign; only explicitly negated headers such as `-Zim` or `-Z''` trigger automatic sign conversion. Headerless three-column tables with a consistently positive third column are audited as the common Frequency/Z′/−Z″ convention and can still be reversed with **Invert imaginary sign**.


## Warburg and diffusion fitting

Version 1.1 adds three explicit diffusion choices:

- **CPE arc + ideal Warburg:** `Rs + (Rct || CPE) + W`, for a semicircle followed by an ideal 45° semi-infinite diffusion tail.
- **Classical Randles + Warburg:** `Rs + [CPE || (Rct + W)]`, where the Warburg element is in the faradaic branch.
- **CPE arc + fractional Warburg:** `Rs + (Rct || CPE) + Wβ`, where the fitted exponent `βW` describes the tail. `βW = 0.50` is ideal Warburg behavior; a fitted value away from 0.50 is reported as fractional or anomalous diffusion.

The auto-fit now examines the lowest-frequency Nyquist points, estimates their line angle and straightness, estimates a frequency-domain diffusion exponent, and uses this only as a small model-selection tie-breaker. A two-CPE fit is penalized when one parallel resistance becomes effectively infinite and the associated CPE is merely imitating a diffusion element. Information criteria and residual quality still dominate selection.

A visible 45° line is supportive but is not unique proof of diffusion. Always compare residuals, parameter uncertainty, frequency coverage, and the physical cell model.

## Batch calibration filenames

Include concentration in filenames, for example:

- `cholesterol_0.5mM.csv`
- `cholesterol_1mM.csv`
- `cholesterol_2.5mM.csv`

The first available resistance parameter, normally `Rct`, is used for a preliminary calibration plot. LOD and LOQ are reported as `3.3 × sy/x / slope` and `10 × sy/x / slope`. For a validated method, use replicate blanks or the calculation prescribed by your protocol.

## Sequential ST A/B Rct reports

The **Batch and ST A/B analysis** panel recognizes files named in this pattern:

- `ST1-A.txt`
- `ST1-B.txt`
- `ST2-A.txt`
- `ST2-B.txt`
- continuing as `ST3-A`, `ST3-B`, and so on

Spaces, underscores, leading zeros, CSV/Excel suffixes, and unusual text suffixes are also accepted, for example `ST02_B.tsv` or `ST2-A.tx,t`. Files are analyzed sequentially in natural ST order.

Use **Rct-compatible auto-fit for each file** to restrict automatic circuit selection to models that contain an explicit `Rct` parameter. This prevents a two-time-constant model from silently replacing the requested Rct with an ambiguous `R1` or `R2`. You may uncheck auto-fit and use the currently selected circuit for every file, provided that circuit contains `Rct`.

Click **Run ST A/B analysis + TXT reports**. The output folder contains:

- `Rct_results.txt` — one clean tab-delimited summary row for every ST number;
- `ST1-A_result.txt`, `ST1-B_result.txt`, etc. — one detailed result file for every source data file;
- `Rct_results.tsv` and `all_file_fit_results.tsv` — machine-readable companions.

The combined summary reports:

- `RctA` and `RctB` with fitted standard errors;
- the requested `RctA_minus_RctB_ohm = Rct(STn-A) − Rct(STn-B)`;
- propagated standard error of the difference, assuming independent fits;
- absolute difference, A/B ratio, and percent change relative to B;
- the selected model and RMSE for A and B;
- a warning when A and B were fitted using different equivalent circuits;
- missing-file or failed-fit status without stopping the remaining analyses.

Each per-file TXT report contains the import/sign audit, fitting settings, selected circuit, all parameters and uncertainties, quality statistics, Rct, consistency screening, diffusion diagnostics, auto-fit ranking, and the complete measured/fitted/residual spectrum. A uniquely labeled file that cannot be imported or fitted still receives its own error TXT. Duplicate ST labels are explicitly reported instead of being silently mixed into one pair.

For the strongest scientific comparison, fit A and B using the same physically justified circuit and verify that `Rct` represents the same electrochemical process in both spectra.

## Custom application icon

The supplied logo is included in `assets/1.png` and is used for the PySide6 application window, dialogs, taskbar entry, and packaged Windows application. A multi-resolution `assets/eis_gold_studio.ico` is included for the Windows executable itself. The EXE builder embeds the assets automatically for both one-folder and one-file builds. These branding assets are not copied into scientific data exports or analysis reports.

## Scientific caution

The included consistency checks are practical screening diagnostics, not a complete publication-grade Lin-KK implementation. The DRT module is a useful exploratory regularized inversion; the regularization parameter must be justified and sensitivity-tested. Equivalent circuits must be selected using electrochemical plausibility, residuals, uncertainty, frequency coverage and experimental context—not only the lowest error.

## Suggested next development steps

- Full Boukamp/Schönleber Lin-KK validation.
- Linked multi-spectrum fitting with shared parameters.
- Optional free-form node-and-wire canvas beyond the current structured series/parallel builder.
- Bootstrap confidence intervals and profile likelihoods.
- Instrument-specific import templates.
- Project database and audit trail.

## Supported potentiostat table format

The importer explicitly supports instrument tables with headers such as:

```text
Index    Frequency (Hz)    Z' (Ω)    -Z'' (Ω)    Z (Ω)    -Phase (°)    Time (s)
```

For this format:

- `Index` is retained for traceability but is not used in fitting.
- `Frequency (Hz)` becomes the frequency vector.
- `Z' (Ω)` becomes the real impedance.
- Positive values in `-Z'' (Ω)` are automatically converted to negative `Z''` values in the internal complex impedance.
- `Z (Ω)`, `-Phase (°)` and `Time (s)` are retained as optional metadata.
- The supplied magnitude and phase are checked against values recalculated from `Z'` and `Z''`; meaningful discrepancies are reported in the diagnostics log.
- Tab-delimited `.txt` or `.tsv`, comma-delimited `.csv`, and Excel files are accepted.

The manual **Invert imaginary sign** checkbox is only an override for incorrectly labeled or unusual files. It is reset whenever a new dataset is opened to prevent accidental double inversion.

The alternative `Potential (V) / Frequency (Hz) / |Z| (ohms) / Zre (ohms) / Zim (ohms)` layout is accepted in tab-delimited text, CSV, and Excel files. Potential is displayed in the Data tab and retained in exported data tables.

### Troubleshooting plot warnings

Version 1.7.1 removes the fixed Nyquist aspect ratio so the Matplotlib toolbar can zoom and pan normally. Bode plots use only positive frequency values because the x-axis is logarithmic. Finite-length Warburg and TLM elements use a stable complex hyperbolic-tangent limit for large diffusion arguments, preventing harmless but noisy overflow warnings during global optimization.
