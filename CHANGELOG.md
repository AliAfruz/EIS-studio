# Changelog

## 1.13.2 — Docked circuit monitor

- Moved the live Nyquist/Bode monitor from the schematic surface into a dedicated **Plot** tab in the right rail, leaving the circuit canvas completely unobstructed.
- Changed the canvas **Monitor** action to open the Plot tab directly while preserving live simulation, measured overlay, RMSE, fitting, and the frequency/sensitivity cursor.
- Added an expanding four-tab right rail—**Plot**, **Edit**, **Science**, and **Topology**—with no overflow controls at the reported 1370-pixel window width.
- Kept **Edit** as the initial tab so symbol selection and parameter tuning remain the default workflow.

## 1.13.1 — Responsive circuit-lab cleanup

- Rebuilt the overloaded right rail as focused **Inspect**, **Science**, and **Topology** tabs so property editing, hypotheses, and topology controls no longer collide vertically.
- Replaced the clipped five-column inspector with fixed compact parameter/value/unit/lock columns and a flexible live-control slider column.
- Fixed Windows overlay offset/clipping by removing the graphics effect from the canvas viewport; the floating monitor and minimap now remain native, correctly positioned child widgets.
- Made the live monitor a predictable compact size, added collapse/expand, and placed it in an open upper canvas region by default while preserving free dragging.
- Shortened secondary action labels, split view/lab controls into clean rows, wrapped hypothesis cards, compacted palette tiles, and simplified JSON/export actions.
- Improved initial circuit framing and verified the responsive layout at the reported 1536 × 1035 display size.

## 1.13.0 — Live circuit laboratory

- Added a movable floating EIS monitor directly over the schematic canvas with live Nyquist/Bode modes, measured-data overlay, RMSE feedback, and a draggable/clickable frequency cursor.
- Added live simulation across the measured frequency range (or a broad default range), logarithmic parameter sliders, and direct fitting of the current custom circuit to the measured overlay.
- Added frequency-specific finite-difference sensitivity glow so the elements dominating the selected response region are visible on the schematic.
- Added element-level identifiability screening from frequency-window response, parameter-bound proximity, and available fitted standard errors; warning/bad states appear on symbols with audited tooltips.
- Added conservative topology hypotheses from diffusion screening, inductive signatures, response peaks, DRT peak candidates, model mismatch, and weak CPE identifiability. Every hint is explicitly labelled as screening evidence rather than a mechanism conclusion.
- Added direct terminal-to-terminal luminous wire gestures: output-to-input creates/reorders series connections, same-side gestures automatically form a valid parallel block, and invalid graph operations are rejected.
- Added a DC-series global-fit laboratory supporting shared, independent, and smoothly potential-dependent parameters, editable bias values, parameter-trend plots, table export, and handoff of shared/median values to the composer.
- Added snap-to-grid, rubber-band multi-selection alignment, copy/paste, annotations, built-in circuit templates, a live minimap, and layout-aware undo/redo.
- Added publication schematic export as editable vector SVG, PDF, or high-resolution PNG.
- Regression verification: 40 tests pass, including live monitor/sensitivity, direct series and automatic-parallel terminal wiring, SVG/PDF export, identifiability mapping, global DC-series recovery, and all previous EIS/Mott-Schottky workflows.

## 1.12.0 — Live electrical-schematic canvas

- Replaced the tree-first wiring surface with a large XMind-style freeform schematic workspace; the compact topology tree remains as a synchronized scientific navigator.
- Added recognizable electrical symbols for resistor, capacitor, CPE, inductor, ideal/fractional/finite Warburg, Gerischer, open/short TLM, and parallel blocks in both the deck and canvas.
- Added live orthogonal wires that remain attached while symbols are moved freely, with saved visual positions and one-click automatic layout restoration.
- Added pulsing magnetic insertion portals. Dropping a palette symbol inserts it into that exact series/parallel slot; releasing an existing symbol near a portal rewires the validated model.
- Added mouse-wheel zoom, middle-button pan, rubber-band selection, fit-to-circuit, automatic layout, synchronized canvas/tree selection, and IN/OUT terminals.
- Preserved parameter editing, locking, undo/redo, duplication, JSON persistence, topology safety, impedance evaluation, and fit integration.
- Regression verification: 36 tests pass, including real Qt canvas drop, magnetic branch rewiring, free-position persistence, auto-layout, and finite-impedance evaluation.

## 1.11.0 — Cinematic drag-and-drop circuit composer

- Rebuilt the visual circuit builder around a spacious three-stage composer: draggable element deck, wiring map, and animated live circuit/inspector stage.
- Added 12 glass element tiles for R, C, CPE, L, ideal/fractional/finite Warburg, Gerischer, open/short TLM, and parallel blocks.
- Added palette-to-topology drag/drop with branch-aware placement: drop on a series path to append or above/below a node to insert.
- Added drag/drop rewiring of existing elements and whole parallel blocks while preventing a block from being moved inside itself.
- Kept double-click quick-add and move buttons as accessible alternatives to dragging.
- Added duplicate-element, add-branch, start-empty, reset-template, remove, undo, redo, Delete, Ctrl+Z, and Ctrl+Y workflows.
- Added a cinematic composer header, live element/parameter status object, glass tile hover states, drop-focused topology styling, depth shadows, and a short opacity pulse after topology changes.
- Preserved the existing validated series/parallel tree, parameter bounds, values, locks, JSON compatibility, impedance evaluation, and fit integration.
- Regression verification: 34 tests pass, including add/move/undo/redo/parallel-block interaction tests and an off-screen composer/evaluation smoke test.

## 1.10.0 — Mott-Schottky semiconductor lab

- Added a dedicated cinematic **Mott-Schottky** workflow and results workspace.
- Added direct potential-capacitance import with automatic V/mV and F/mF/uF/nF/pF conversion, including areal-capacitance header hints.
- Added common-frequency extraction from a potential-stepped EIS table, a collected sequence of current EIS studies, or an editable multi-file/DC-potential table.
- Added parallel-admittance and series-impedance apparent-capacitance conversions with measured-frequency auditing and mismatch rejection.
- Added user-controlled depletion-region fitting, flat-band potential with optional kT/q correction, slope-sign n/p classification, apparent carrier density, OLS standard errors, and 95% confidence intervals.
- Added scientific guardrails for short/narrow/weakly linear regions, long flat-band extrapolation, frequency mismatch/dispersion, unresolved slope sign, and model assumptions.
- Added batch-fit handoff using direct fitted capacitance or topology-limited Hsu-Mansfeld R||CPE conversion; unsupported CPE/diffusion topologies are refused rather than silently converted.
- Added Mott-Schottky tables, plot data, statistics, figures, source files, and warnings to workbook and complete-package exports.
- Added `sample_mott_schottky.csv` and expanded regression coverage to 32 passing tests plus an off-screen end-to-end GUI calculation smoke check.

## 1.9.0 — Cinematic glass interface evolution

- Rebuilt the application shell around a translucent glass-card visual system.
- Added a timer-driven cinematic backdrop with drifting light volumes, technical grid depth, and subtle particles.
- Added an animated orbital EIS mark and a live workspace-status display for ready, loaded, fitting, and busy states.
- Added fade transitions for workflow, result, and plot pages.
- Added a persistent **Cinematic motion** toggle (`Ctrl+M`) so animation can be paused without affecting analysis.
- Refined dark and light palettes with luminous gold/cyan accents, layered controls, modern tabs, and depth shadows.
- Made cinematic dark mode the default for a fresh installation while preserving saved user preferences.
- Kept all numerical, fitting, import, batch, DRT, and export behavior unchanged.
- Regression verification: 22 tests passed plus off-screen GUI navigation, theme, motion, and data-loading smoke checks.

## 1.8.1 — Potential/Zre/Zim potentiostat import

- Added explicit support for tables headed `Potential (V)`, `Frequency (Hz)`, `|Z| (ohms)`, `Zre (ohms)`, and `Zim (ohms)`.
- Retained the potential column as `potential_V` for the data table and exports.
- Preserved signed `Zim` values exactly when the header is `Zim`; automatic sign conversion remains limited to headers that explicitly begin with a minus sign, such as `-Zim` or `-Z''`.
- Excluded potential/voltage columns from numeric fallback impedance mapping.
- Added a representative tab-delimited regression fixture and importer test.

## 1.8.0 — Workflow-focused GUI update

- Reorganized the left workspace into focused **Data**, **Fit**, **Circuit**, **Diagnostics**, and **Batch** pages.
- Moved optimizer, weighting, robust loss, evaluation limits, multistarts, and complex-model selection into collapsible advanced fitting settings.
- Added primary, secondary, and quiet button styles so the recommended next action is visually clear.
- Added state-aware controls and export actions that only become available when the required data or result exists.
- Made the activity and diagnostics log collapsible to preserve plotting space.
- Added a first-run plot empty state and drag-and-drop loading for supported EIS files.
- Split ordinary batch processing and paired ST A/B reporting into separate panels.
- Improved light-theme title contrast and added quieter help, file-summary, and empty-state styles.

## 1.7.2 — Nyquist padding and non-freezing advanced auto-fit

- Fixed Nyquist plot edge clipping by applying explicit finite-data axis limits with padding after plotting measured, preview, and fitted series.
- Kept Nyquist axes freely zoomable by preserving automatic aspect ratio rather than forcing fixed x/y scaling.
- Moved **Advanced auto-fit** to a background `QThread` so the GUI remains responsive during hybrid global + bounded least-squares model selection.
- Added an **Advanced auto-fit** progress bar in the fitting panel.
- Added per-candidate progress updates such as `Fitting model X/Y`, `Finished`, or `Skipped`.
- Extended the `auto_fit()` API with an optional progress callback while preserving existing batch and paired-analysis behavior.
- Regression tests: 21 passed.

## 1.7.1 — Plot zoom and finite-diffusion numerical stability fix

- Removed the fixed/equal Nyquist aspect ratio that made Matplotlib ignore toolbar zoom-out limits.
- Added numerically stable complex `tanh()` handling for finite Warburg and TLM elements to prevent overflow warnings during wide global searches.
- Skipped non-positive frequencies in Bode plots so the logarithmic x-axis no longer emits non-positive-limit warnings.
- Updated reset-view behavior so plot panels return to freely zoomable axes.

## 1.7.0 — Finite diffusion and hybrid fitting update

- Added finite-length Warburg open/blocking (`Wₒ`) and short/transmissive (`Wₛ`) impedance elements.
- Added Gerischer reaction–diffusion and simple porous-electrode transmission-line (`TLMₒ`, `TLMₛ`) elements.
- Added predefined circuits for CPE arc + `Wₒ`, CPE arc + `Wₛ`, two CPE arcs + `Wₒ`, classical Randles + `Wₒ`, Gerischer topologies, TLM topologies, and optional `Rads ∥ Lads` adsorption/inductive-loop branch.
- Extended the visual circuit builder to support finite Warburg, Gerischer, and TLM elements with editable/lockable parameters.
- Added a hybrid optimizer option using differential evolution for global search followed by bounded least-squares refinement.
- Kept bounded least-squares multistart available for faster screening and batch workflows.
- Improved low-, mid-, and high-frequency data-derived starting guesses for diffusion time constants, finite diffusion resistance, Gerischer parameters, TLM parameters, and adsorption inductance.
- Added model-selection warnings for parameters at bounds, large relative errors, strong correlations, time constants outside the measured window, structured residuals, weak identifiability, and unnecessary inductive-loop use.
- Added optimizer, maximum parameter correlation, Jacobian condition number, and warnings to result tables and exports.
- Expanded regression tests for finite-length diffusion behavior, clean-spectrum recovery, and manual-builder support for new diffusion elements.

## 1.6.0 — Normalized EIS chi-square

- Replaced the previously displayed raw residual variance with a dimensionless Z-modulus-normalized pseudo-chi-square.
- Added normalized reduced chi-square using the EIS convention `N - k`, where `N` is the number of complex frequency points and `k` is the number of free parameters.
- Added the unreduced normalized pseudo-chi-square, relative residual RMS percentage, and explicit chi-square degrees of freedom.
- Retained the former value as `Legacy raw reduced variance / ohm^2` for traceability.
- Updated the fit-quality table, auto-fit ranking export, workbooks, CSV/TSV files, and ST A/B detailed TXT reports.
- Added an in-app formula tooltip and documentation explaining that exact cross-software agreement requires identical weighting, data selection, circuit, constraints, and degrees-of-freedom conventions.
- Added regression tests for scale invariance, exact fits, known 1% relative residuals, and fitted-result reporting.

## 1.5.2 — Custom application and Windows EXE icon

- Added the user-supplied full logo as `assets/1.png`.
- Added a multi-resolution Windows icon as `assets/eis_gold_studio.ico`.
- Applied the icon to the QApplication and main window for title-bar and taskbar display.
- Added a stable Windows AppUserModelID to improve taskbar icon consistency.
- Updated PyInstaller builds to embed the icon and bundled assets in both one-folder and one-file modes.
- Kept icon assets out of scientific TXT, Excel, plot-data, and complete analysis exports.

## 1.5.0 — Flexible ASCII delimiter import

- Added automatic detection of space/whitespace, tab, comma, semicolon, and colon column delimiters.
- Added manual delimiter selection in the Data panel for ambiguous instrument exports.
- Added automatic and manual dot/comma decimal-separator handling.
- Added protection against misreading decimal-comma values as comma-separated columns.
- Added whitespace-file parsing that can reconstruct common multiword EIS headers such as `Frequency (Hz)` and `-Phase (°)`.
- Added import-audit reporting for delimiter, decimal separator, encoding, and whether each option was auto-detected or manually selected.
- Expanded single-file and general batch discovery to DAT, ASC, and DTA ASCII extensions and uppercase variants.
- Added regression tests for all five delimiter types, decimal-comma semicolon files, and manual delimiter/decimal overrides.

## 1.4.0 — Sequential ST A/B Rct reporting

- Added filename recognition for `ST1-A`, `ST1-B`, `ST2-A`, `ST2-B`, and subsequent numbered pairs.
- Added permissive suffix handling for TXT, TSV, CSV, Excel, and unusual instrument text suffixes.
- Added sequential one-by-one fitting in a worker thread with independent progress reporting.
- Added Rct-compatible auto-fit restricted to circuit models with an explicit `Rct` parameter.
- Added one detailed TXT result for every detected source file, including import audit, parameters, uncertainties, fit metrics, consistency checks, diffusion screening, model ranking, and full fitted spectrum.
- Added `Rct_results.txt` with `RctA`, `RctB`, `RctA − RctB`, propagated difference uncertainty, ratio, percent change, model identity, RMSE, status, and comparability warnings.
- Added TSV companions for machine-readable file-level and pair-level results.
- Added missing-pair, duplicate-label, and per-file failure reporting without aborting the remaining sequence.
- Added an **ST Rct A−B** results table and **Open reports folder** action.
- Included paired TXT/TSV reports in complete ZIP analysis exports.
- Added regression tests for flexible ST filename parsing, sequential report generation, and Rct-difference accuracy.

## 1.3.0 — Manual parameters and visual circuit builder

- Added editable numerical values for every electrical element parameter.
- Added optional per-parameter locking; locked values are removed from the optimizer and reported explicitly.
- Added manual-curve preview on Nyquist and Bode plots without overwriting fit results.
- Added data-derived guess reset and fitted-value transfer controls.
- Added live numerical labels to the equivalent-circuit visualization.
- Added a visual series/parallel circuit builder with R, C, CPE, L, ideal Warburg, and fractional-Warburg elements.
- Added explicit parallel branches, branch addition/removal, element ordering, and live wiring preview.
- Added custom circuit JSON save/load and inclusion in complete ZIP exports.
- Added custom-circuit evaluation and nonlinear fitting through the existing fitting engine.
- Added validation for empty branches, unsupported elements, and duplicate parameter names.
- Added regression tests for custom circuits, partially locked fitting, and fully locked manual evaluation.

## 1.2.1 — Protected option scrolling

- Disabled mouse-wheel value changes application-wide for spin boxes, combo boxes, sliders, and dials.
- Protected model, weighting, robust-loss, optimization, and DRT settings even when a control has focus.
- Preserved normal scrolling in the controls panel and normal Matplotlib plot interaction.
- Kept keyboard, button, direct-entry, and explicit drop-down selection available.

## 1.2.0 — Clipboard and complete export

- Added `Ctrl+C` copying to every table using an Excel-compatible tab-delimited layout.
- Added table right-click menus for selected cells, headers, complete rows, whole-table copy and select-all.
- Added selected-area and full-table export to XLSX, CSV and TSV.
- Added plot clipboard copying, image export, and plotted-series export from toolbar and right-click menus.
- Added PNG, SVG, PDF, JPEG and TIFF plot output.
- Added copy/export support for equivalent-circuit diagrams.
- Added a complete ZIP analysis package with a multi-sheet workbook, per-table CSV files, all figures, plot data, source data, circuit image, audit log and manifest.
- Added persistent DRT reconstruction and calibration tables so they are included in later exports.
- Added an Export menu and `Ctrl+Shift+E` shortcut for complete package export.

## 1.1.0 — Diffusion-aware auto-fitting

- Added a fractional/generalized Warburg model with fitted diffusion exponent βW.
- Added the classical Randles topology `Rs + [CPE || (Rct + W)]`.
- Corrected the ideal Warburg implementation to the common `σ(1−j)/√ω` convention.
- Added low-frequency diffusion screening using Nyquist-tail slope, angle, linearity and frequency scaling.
- Improved Warburg initial guesses from the measured low-frequency points.
- Improved arc-diameter and characteristic-frequency initial estimates.
- Added a physical-identifiability penalty for two-CPE fits with effectively infinite branch resistance.
- Reduced inappropriate random perturbation of bounded exponents during multistart fitting.
- Added nested series-branch circuit visualization and a `Wβ` symbol.
- Added scientific regression tests for diffusion-model selection.
