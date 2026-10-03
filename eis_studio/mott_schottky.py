"""Mott-Schottky import, EIS extraction, fitting, and audit utilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy.constants import Boltzmann, elementary_charge, epsilon_0
from scipy.stats import t as student_t

from .io_utils import (
    FREQ_ALIASES,
    IMAG_ALIASES,
    REAL_ALIASES,
    _clean_label,
    _find_col,
    _read_table,
    read_eis,
)


POTENTIAL_ALIASES = (
    "potential", "potential v", "potential mv", "voltage", "voltage v", "voltage mv",
    "applied potential", "applied voltage", "dc potential", "dc bias", "bias",
    "electrode potential", "e v", "ewe", "ewe v", "working electrode potential",
)

CAPACITANCE_ALIASES = (
    "capacitance", "capacitance f", "capacitance mf", "capacitance uf",
    "capacitance µf", "capacitance nf", "capacitance pf", "c f", "c mf",
    "c uf", "c µf", "c nf", "c pf", "csc", "c sc", "space charge capacitance",
    "interfacial capacitance", "double layer capacitance", "capacitance f cm-2",
    "capacitance uf cm-2", "capacitance µf cm-2", "c f cm-2", "c uf cm-2",
    "c µf cm-2", "capacitance f/cm2", "capacitance uf/cm2", "c f/cm2",
)


@dataclass(frozen=True)
class MottSchottkyResult:
    data: pd.DataFrame
    statistics: dict[str, object]


def _header_has_token(header: object, patterns: tuple[str, ...]) -> bool:
    text = str(header).lower().replace("μ", "µ")
    return any(re.search(pattern, text) for pattern in patterns)


def _potential_scale(header: object) -> float:
    if _header_has_token(header, (r"\bmv\b", r"millivolt")):
        return 1e-3
    if _header_has_token(header, (r"\bkv\b", r"kilovolt")):
        return 1e3
    return 1.0


def _capacitance_scale(header: object) -> float:
    text = str(header).lower().replace("μ", "µ")
    for scale, patterns in (
        (1e-12, (r"\bpf\b", r"picofarad")),
        (1e-9, (r"\bnf\b", r"nanofarad")),
        (1e-6, (r"\b(?:µf|uf)\b", r"microfarad")),
        (1e-3, (r"\bmf\b", r"millifarad")),
    ):
        if any(re.search(pattern, text) for pattern in patterns):
            return scale
    return 1.0


def _capacitance_header_is_areal(header: object) -> bool:
    text = str(header).lower().replace("²", "2").replace("−", "-")
    return bool(re.search(r"(?:/|\bper\s*)\s*cm\s*(?:\^?\s*-?2|2\b)|cm\s*-2", text))


def _header_is_inverse_capacitance(header: object) -> bool:
    text = str(header).lower().replace("²", "2").replace("−", "-")
    compact = re.sub(r"\s+", "", text)
    return bool(
        "1/c" in compact
        or "inversecapacitance" in compact
        or re.search(r"(?<![a-z])c\s*\^?\s*-?2(?![a-z])", text)
    )


def _numeric_columns(raw: pd.DataFrame) -> list[object]:
    return [
        column for column in raw.columns
        if pd.to_numeric(raw[column], errors="coerce").notna().sum() >= 4
    ]


def read_mott_schottky(
    path: str | Path,
    delimiter: str | None = "auto",
    decimal: str | None = "auto",
) -> pd.DataFrame:
    """Read potential-capacitance or potential-impedance data."""
    source_path = Path(path)
    raw, import_format = _read_table(
        source_path,
        delimiter=delimiter,
        decimal=decimal,
        min_numeric_fields=2,
    )
    if raw.empty:
        raise ValueError("The selected Mott-Schottky file is empty.")

    used: set[object] = set()
    potential_col = _find_col(raw.columns, POTENTIAL_ALIASES, used)
    if potential_col is not None:
        used.add(potential_col)
    capacitance_col = _find_col(raw.columns, CAPACITANCE_ALIASES, used)
    if capacitance_col is not None:
        used.add(capacitance_col)
    frequency_col = _find_col(raw.columns, FREQ_ALIASES, used)
    if frequency_col is not None:
        used.add(frequency_col)
    real_col = _find_col(raw.columns, REAL_ALIASES, used)
    if real_col is not None:
        used.add(real_col)
    imag_col = _find_col(raw.columns, IMAG_ALIASES, used)

    numeric = _numeric_columns(raw)
    if potential_col is None and numeric:
        potential_col = numeric[0]
    remaining = [column for column in numeric if column != potential_col]
    if capacitance_col is None and real_col is None and imag_col is None:
        if len(remaining) == 1:
            capacitance_col = remaining[0]
        elif len(remaining) >= 3:
            frequency_col = frequency_col or remaining[0]
            real_col = real_col or remaining[1]
            imag_col = imag_col or remaining[2]

    if potential_col is None:
        raise ValueError(
            "Could not identify potential. Use a header such as Potential (V), "
            "Potential (mV), Voltage (V), or Ewe (V)."
        )
    if capacitance_col is None and not (real_col is not None and imag_col is not None):
        raise ValueError(
            "Could not identify capacitance or both Z real and Z imaginary columns. "
            "Detected headers: " + ", ".join(map(str, raw.columns))
        )
    if capacitance_col is not None and _header_is_inverse_capacitance(capacitance_col):
        raise ValueError(
            "The selected column appears to contain inverse capacitance (1/C^2). "
            "Import capacitance itself so units, area normalization, and fit-window "
            "transformations remain auditable."
        )

    out = pd.DataFrame({
        "potential_V": (
            pd.to_numeric(raw[potential_col], errors="coerce")
            * _potential_scale(potential_col)
        ),
    })
    if capacitance_col is not None:
        out["capacitance_F"] = (
            pd.to_numeric(raw[capacitance_col], errors="coerce")
            * _capacitance_scale(capacitance_col)
        )
    if frequency_col is not None:
        out["frequency_Hz"] = pd.to_numeric(raw[frequency_col], errors="coerce")
    if real_col is not None:
        out["Zreal_ohm"] = pd.to_numeric(raw[real_col], errors="coerce")
    imaginary_sign_converted = False
    if imag_col is not None:
        out["Zimag_ohm"] = pd.to_numeric(raw[imag_col], errors="coerce")
        imaginary_sign_converted = _clean_label(imag_col).lstrip().startswith("-")
        if imaginary_sign_converted:
            out["Zimag_ohm"] *= -1

    if "capacitance_F" in out:
        usable = out["capacitance_F"].notna()
    else:
        usable = out["Zreal_ohm"].notna() & out["Zimag_ohm"].notna()
    out = out[out["potential_V"].notna() & usable].copy()
    if "frequency_Hz" in out:
        out.loc[out["frequency_Hz"] <= 0, "frequency_Hz"] = np.nan
    out = out.sort_values("potential_V").reset_index(drop=True)
    if len(out) < 4:
        raise ValueError("At least four valid Mott-Schottky points are required.")

    out.attrs.update({
        "source_path": str(source_path),
        "source_kind": "prepared potential table",
        "source_columns": {
            "potential_V": str(potential_col),
            "capacitance_F": (
                str(capacitance_col) if capacitance_col is not None else None
            ),
            "frequency_Hz": str(frequency_col) if frequency_col is not None else None,
            "Zreal_ohm": str(real_col) if real_col is not None else None,
            "Zimag_ohm": str(imag_col) if imag_col is not None else None,
        },
        "potential_scale_to_V": _potential_scale(potential_col),
        "capacitance_scale_to_F": (
            _capacitance_scale(capacitance_col)
            if capacitance_col is not None else None
        ),
        "capacitance_is_areal_hint": (
            _capacitance_header_is_areal(capacitance_col)
            if capacitance_col is not None else False
        ),
        "imaginary_sign_converted": imaginary_sign_converted,
        "import_format": import_format,
    })
    return out


def prepare_mott_schottky_from_batch_results(
    batch_results: pd.DataFrame,
    *,
    minimum_distinct_potentials: int = 4,
) -> pd.DataFrame:
    """Use only audited equivalent-circuit capacitance from batch results."""
    required = {"file", "DC_potential_V", "fit_capacitance_F"}
    missing = sorted(required.difference(batch_results.columns))
    if missing:
        raise ValueError("Batch results are missing: " + ", ".join(missing))

    potential = pd.to_numeric(batch_results["DC_potential_V"], errors="coerce")
    capacitance = pd.to_numeric(batch_results["fit_capacitance_F"], errors="coerce")
    missing_potential = ~np.isfinite(potential)
    if missing_potential.any():
        names = [
            Path(value).name
            for value in batch_results.loc[missing_potential, "file"].astype(str)
        ]
        raise ValueError("Missing DC potential for: " + ", ".join(names))
    invalid_capacitance = ~(np.isfinite(capacitance) & (capacitance > 0))
    if invalid_capacitance.any():
        names = [
            Path(value).name
            for value in batch_results.loc[invalid_capacitance, "file"].astype(str)
        ]
        raise ValueError("Missing positive fitted capacitance for: " + ", ".join(names))
    if potential.nunique(dropna=True) < int(minimum_distinct_potentials):
        raise ValueError(
            f"At least {int(minimum_distinct_potentials)} distinct DC potentials are required."
        )

    out = pd.DataFrame({
        "potential_V": potential.to_numpy(float),
        "capacitance_F": capacitance.to_numpy(float),
        "source_file": batch_results["file"].astype(str).to_numpy(),
    })
    output_names = {
        "model": "batch_model",
        "model_key": "batch_model_key",
        "RMSE": "batch_fit_RMSE",
        "reduced_chi2_Zmod": "batch_fit_reduced_chi2_Zmod",
        "success": "batch_fit_success",
    }
    for column in (
        "DC_potential_source", "model", "model_key", "fit_capacitance_component",
        "fit_capacitance_method", "fit_capacitance_warning", "RMSE",
        "reduced_chi2_Zmod", "success",
    ):
        if column in batch_results.columns:
            out[output_names.get(column, column)] = batch_results[column].to_numpy()
    out = out.sort_values("potential_V").reset_index(drop=True)
    out.attrs.update({
        "source_kind": "batch fitted equivalent-circuit capacitance",
        "capacitance_origin": (
            "fit_capacitance_F from the batch equivalent-circuit engine; "
            "raw impedance was not converted at one selected frequency"
        ),
        "source_paths": out["source_file"].tolist(),
    })
    return out


def available_capacitance_methods(data: pd.DataFrame) -> tuple[str, ...]:
    methods: list[str] = []
    if "capacitance_F" in data.columns:
        methods.append("direct")
    if {"Zreal_ohm", "Zimag_ohm"}.issubset(data.columns):
        methods.extend(("parallel", "series"))
    return tuple(methods)


def _capacitance_from_data(
    data: pd.DataFrame,
    method: str,
    fixed_frequency_hz: float,
) -> tuple[np.ndarray, np.ndarray, str]:
    selected_method = str(method).lower()
    available = available_capacitance_methods(data)
    if selected_method == "auto":
        selected_method = "direct" if "direct" in available else "parallel"
    if selected_method not in available:
        raise ValueError(
            f"Capacitance method '{selected_method}' is unavailable for these columns."
        )

    if selected_method == "direct":
        return (
            data["capacitance_F"].to_numpy(float),
            np.full(len(data), np.nan),
            "Direct capacitance column",
        )
    if fixed_frequency_hz <= 0:
        raise ValueError("Target frequency must be greater than zero.")
    if "frequency_Hz" in data:
        frequency = data["frequency_Hz"].to_numpy(float)
        frequency = np.where(
            np.isfinite(frequency) & (frequency > 0),
            frequency,
            fixed_frequency_hz,
        )
    else:
        frequency = np.full(len(data), fixed_frequency_hz)
    omega = 2.0 * np.pi * frequency
    real = data["Zreal_ohm"].to_numpy(float)
    imag = data["Zimag_ohm"].to_numpy(float)
    if selected_method == "series":
        with np.errstate(divide="ignore", invalid="ignore"):
            capacitance = -1.0 / (omega * imag)
        label = "Series apparent C = -1/(2πfZ″)"
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            capacitance = np.imag(1.0 / (real + 1j * imag)) / omega
        label = "Parallel apparent C = Im(1/Z)/(2πf)"
    return capacitance, frequency, label


def _cluster_potential_rows(values: np.ndarray, tolerance_V: float) -> list[np.ndarray]:
    finite_indices = np.flatnonzero(np.isfinite(values))
    if not finite_indices.size:
        return []
    ordered = finite_indices[np.argsort(values[finite_indices])]
    tolerance = max(float(tolerance_V), 0.0)
    clusters: list[list[int]] = [[int(ordered[0])]]
    for index in ordered[1:]:
        center = float(np.median(values[clusters[-1]]))
        if abs(float(values[index]) - center) <= tolerance:
            clusters[-1].append(int(index))
        else:
            clusters.append([int(index)])
    return [np.asarray(cluster, dtype=int) for cluster in clusters]


def _nearest_frequency_row(
    data: pd.DataFrame,
    target_frequency_hz: float,
) -> tuple[pd.Series, float]:
    if target_frequency_hz <= 0:
        raise ValueError("Target frequency must be greater than zero.")
    frequency = data["frequency_Hz"].to_numpy(float)
    valid = np.isfinite(frequency) & (frequency > 0)
    if not np.any(valid):
        raise ValueError("No positive measured frequencies are available.")
    positions = np.flatnonzero(valid)
    distance = np.abs(np.log10(frequency[valid] / float(target_frequency_hz)))
    position = int(positions[int(np.argmin(distance))])
    row = data.iloc[position]
    error_percent = (
        100.0 * abs(float(row["frequency_Hz"]) - target_frequency_hz)
        / target_frequency_hz
    )
    return row, float(error_percent)


def extract_mott_schottky_study(
    data: pd.DataFrame,
    dc_potential_V: float,
    *,
    target_frequency_hz: float = 1000.0,
    max_frequency_deviation_percent: float = 35.0,
) -> pd.DataFrame:
    """Extract one common-frequency point from one ordinary EIS spectrum."""
    if not np.isfinite(dc_potential_V):
        raise ValueError("DC potential must be finite.")
    source = data.copy()
    source.attrs = dict(data.attrs)
    source["potential_V"] = float(dc_potential_V)
    point = extract_mott_schottky_from_eis(
        source,
        target_frequency_hz=target_frequency_hz,
        max_frequency_deviation_percent=max_frequency_deviation_percent,
        potential_group_tolerance_V=0.0,
        minimum_potentials=1,
    )
    point = point.copy()
    point["potential_source"] = "user-entered DC value"
    point.attrs.update({
        "source_kind": "single EIS study with user-entered DC value",
        "entered_dc_potential_V": float(dc_potential_V),
    })
    return point


def extract_mott_schottky_from_eis(
    data: pd.DataFrame,
    *,
    target_frequency_hz: float = 1000.0,
    max_frequency_deviation_percent: float = 35.0,
    potential_group_tolerance_V: float = 0.005,
    minimum_potentials: int = 4,
) -> pd.DataFrame:
    """Select the nearest common-frequency point for each DC-potential step."""
    required = {"potential_V", "frequency_Hz", "Zreal_ohm", "Zimag_ohm"}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(
            "Potential-stepped EIS data are missing: " + ", ".join(missing)
        )
    clusters = _cluster_potential_rows(
        data["potential_V"].to_numpy(float),
        potential_group_tolerance_V,
    )
    rows: list[dict[str, object]] = []
    rejected = 0
    for group_number, indices in enumerate(clusters, 1):
        subset = data.iloc[indices]
        try:
            selected, error_percent = _nearest_frequency_row(
                subset, target_frequency_hz
            )
        except ValueError:
            rejected += 1
            continue
        if (
            max_frequency_deviation_percent > 0
            and error_percent > max_frequency_deviation_percent
        ):
            rejected += 1
            continue
        values = subset["potential_V"].to_numpy(float)
        rows.append({
            "potential_V": float(np.nanmedian(values)),
            "frequency_Hz": float(selected["frequency_Hz"]),
            "Zreal_ohm": float(selected["Zreal_ohm"]),
            "Zimag_ohm": float(selected["Zimag_ohm"]),
            "frequency_target_Hz": float(target_frequency_hz),
            "frequency_match_error_percent": float(error_percent),
            "potential_group_points": int(len(subset)),
            "potential_group_span_mV": float(
                1000.0 * (np.nanmax(values) - np.nanmin(values))
            ),
            "potential_source": "EIS potential column",
            "potential_group": group_number,
        })
    result = (
        pd.DataFrame(rows).sort_values("potential_V").reset_index(drop=True)
        if rows else pd.DataFrame()
    )
    unique_potentials = (
        int(result["potential_V"].nunique()) if not result.empty else 0
    )
    if unique_potentials < int(minimum_potentials):
        raise ValueError(
            f"Only {unique_potentials} usable potential steps were found; "
            f"at least {int(minimum_potentials)} are required at a common frequency."
        )
    result.attrs.update({
        "source_kind": "loaded EIS potential series",
        "source_path": data.attrs.get("source_path"),
        "target_frequency_Hz": float(target_frequency_hz),
        "max_frequency_deviation_percent": float(max_frequency_deviation_percent),
        "potential_group_tolerance_V": float(potential_group_tolerance_V),
        "rejected_potential_groups": int(rejected),
        "source_potential_steps": int(len(clusters)),
    })
    return result


def potential_from_filename(path: str | Path) -> float | None:
    """Extract a final potential token such as -0.20V or +150mV."""
    text = Path(path).stem.replace("−", "-").replace(",", ".")
    matches = list(re.finditer(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(mV|V)(?![A-Za-z])",
        text,
        re.IGNORECASE,
    ))
    if not matches:
        return None
    match = matches[-1]
    value = float(match.group(1))
    return value * 1e-3 if match.group(2).lower() == "mv" else value


def read_eis_potential_series(
    paths: list[str | Path] | tuple[str | Path, ...],
    *,
    potential_values_V: list[float | None] | tuple[float | None, ...] | None = None,
    target_frequency_hz: float = 1000.0,
    max_frequency_deviation_percent: float = 35.0,
    potential_group_tolerance_V: float = 0.005,
    delimiter: str | None = "auto",
    decimal: str | None = "auto",
    minimum_potentials: int = 4,
    preserve_input_order: bool = True,
) -> pd.DataFrame:
    """Build a potential series from multiple ordinary EIS files."""
    source_paths = [Path(path) for path in paths]
    if not source_paths:
        raise ValueError("Select at least one EIS file.")
    if potential_values_V is None:
        potential_values: list[float | None] = [None] * len(source_paths)
    else:
        if len(potential_values_V) != len(source_paths):
            raise ValueError("Provide one DC-potential entry per selected file.")
        potential_values = [
            None if value is None or not np.isfinite(float(value)) else float(value)
            for value in potential_values_V
        ]

    frames: list[pd.DataFrame] = []
    failures: list[str] = []
    for order, (path, manual_potential) in enumerate(
        zip(source_paths, potential_values), 1
    ):
        try:
            eis = read_eis(path, delimiter=delimiter, decimal=decimal)
            if manual_potential is not None:
                frame = extract_mott_schottky_study(
                    eis,
                    manual_potential,
                    target_frequency_hz=target_frequency_hz,
                    max_frequency_deviation_percent=max_frequency_deviation_percent,
                )
                frame["potential_source"] = "DC file table"
            elif "potential_V" in eis and eis["potential_V"].notna().any():
                frame = extract_mott_schottky_from_eis(
                    eis,
                    target_frequency_hz=target_frequency_hz,
                    max_frequency_deviation_percent=max_frequency_deviation_percent,
                    potential_group_tolerance_V=potential_group_tolerance_V,
                    minimum_potentials=1,
                )
            else:
                potential = potential_from_filename(path)
                if potential is None:
                    raise ValueError(
                        "no potential column and no filename token such as -0.20V or 200mV"
                    )
                frame = extract_mott_schottky_study(
                    eis,
                    potential,
                    target_frequency_hz=target_frequency_hz,
                    max_frequency_deviation_percent=max_frequency_deviation_percent,
                )
                frame["potential_source"] = "filename"
            frame = frame.copy()
            frame["source_file"] = str(path)
            frame["input_order"] = int(order)
            frame["within_file_order"] = np.arange(1, len(frame) + 1)
            frames.append(frame)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")

    if not frames:
        raise ValueError(
            "No selected EIS files could be used.\n" + "\n".join(failures[:12])
        )
    result = pd.concat(frames, ignore_index=True)
    if preserve_input_order:
        result = result.sort_values(
            ["input_order", "within_file_order"]
        ).reset_index(drop=True)
    else:
        result = result.sort_values("potential_V").reset_index(drop=True)
    distinct = int(result["potential_V"].nunique())
    if distinct < int(minimum_potentials):
        details = "\n".join(failures[:8])
        suffix = f"\nSkipped files:\n{details}" if details else ""
        raise ValueError(
            f"Only {distinct} distinct potentials were recovered; "
            f"at least {int(minimum_potentials)} are required.{suffix}"
        )
    result.attrs.update({
        "source_kind": "multiple EIS files",
        "source_paths": [str(path) for path in source_paths],
        "target_frequency_Hz": float(target_frequency_hz),
        "max_frequency_deviation_percent": float(max_frequency_deviation_percent),
        "potential_group_tolerance_V": float(potential_group_tolerance_V),
        "potential_values_from_table": int(
            sum(value is not None for value in potential_values)
        ),
        "skipped_files": failures,
    })
    return result


def calculate_mott_schottky(
    data: pd.DataFrame,
    *,
    method: str = "auto",
    fixed_frequency_hz: float = 1000.0,
    electrode_area_cm2: float = 1.0,
    relative_permittivity: float = 10.0,
    temperature_K: float = 298.15,
    fit_min_V: float | None = None,
    fit_max_V: float | None = None,
    input_capacitance_is_areal: bool = False,
    use_area_normalized_plot: bool = True,
    apply_thermal_correction: bool = True,
    confidence_level: float = 0.95,
) -> MottSchottkyResult:
    """Fit a user-selected depletion region and calculate apparent N and Efb."""
    if "potential_V" not in data:
        raise ValueError("Mott-Schottky input requires potential_V.")
    if electrode_area_cm2 <= 0:
        raise ValueError("Electrode area must be greater than zero.")
    if relative_permittivity <= 0:
        raise ValueError("Relative permittivity must be greater than zero.")
    if temperature_K <= 0:
        raise ValueError("Temperature must be greater than zero kelvin.")
    if not 0 < confidence_level < 1:
        raise ValueError("Confidence level must lie between zero and one.")

    potential = data["potential_V"].to_numpy(float)
    capacitance_input, frequency, method_label = _capacitance_from_data(
        data, method, fixed_frequency_hz
    )
    area_m2 = float(electrode_area_cm2) * 1e-4
    if input_capacitance_is_areal:
        capacitance_areal_F_m2 = capacitance_input * 1e4
        capacitance_total_F = capacitance_areal_F_m2 * area_m2
    else:
        capacitance_total_F = capacitance_input
        capacitance_areal_F_m2 = capacitance_total_F / area_m2

    with np.errstate(divide="ignore", invalid="ignore"):
        inverse_total = 1.0 / np.square(capacitance_total_F)
        inverse_areal = 1.0 / np.square(capacitance_areal_F_m2)
    ordinate = inverse_areal if use_area_normalized_plot else inverse_total
    fit_min = (
        float(np.nanmin(potential)) if fit_min_V is None else float(fit_min_V)
    )
    fit_max = (
        float(np.nanmax(potential)) if fit_max_V is None else float(fit_max_V)
    )
    if fit_min > fit_max:
        fit_min, fit_max = fit_max, fit_min
    selected = (
        np.isfinite(potential)
        & np.isfinite(capacitance_total_F)
        & np.isfinite(capacitance_areal_F_m2)
        & np.isfinite(ordinate)
        & (capacitance_total_F > 0)
        & (potential >= fit_min)
        & (potential <= fit_max)
    )
    point_count = int(np.count_nonzero(selected))
    if point_count < 3:
        raise ValueError(
            "The fit window contains fewer than three valid positive-capacitance points."
        )

    x_fit = potential[selected]
    y_fit = ordinate[selected]
    design = np.column_stack((x_fit, np.ones_like(x_fit)))
    coefficients, _, rank, _ = np.linalg.lstsq(design, y_fit, rcond=None)
    if rank < 2:
        raise ValueError("Selected points do not span a usable potential range.")
    slope, intercept = map(float, coefficients)
    if not np.isfinite(slope) or abs(slope) <= np.finfo(float).tiny:
        raise ValueError("The fitted slope is zero or non-finite.")

    fitted = design @ coefficients
    residuals = y_fit - fitted
    ss_res = float(np.sum(np.square(residuals)))
    ss_tot = float(np.sum(np.square(y_fit - np.mean(y_fit))))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rmse = float(np.sqrt(np.mean(np.square(residuals))))
    dof = point_count - 2
    covariance = np.full((2, 2), np.nan)
    slope_se = intercept_se = np.nan
    critical = np.nan
    if dof > 0:
        covariance = (ss_res / dof) * np.linalg.inv(design.T @ design)
        slope_se = float(np.sqrt(max(float(covariance[0, 0]), 0.0)))
        intercept_se = float(np.sqrt(max(float(covariance[1, 1]), 0.0)))
        critical = float(
            student_t.ppf(0.5 + float(confidence_level) / 2.0, dof)
        )

    slope_ci = (
        float(slope - critical * slope_se),
        float(slope + critical * slope_se),
    ) if np.isfinite(critical) else (np.nan, np.nan)
    intercept_ci = (
        float(intercept - critical * intercept_se),
        float(intercept + critical * intercept_se),
    ) if np.isfinite(critical) else (np.nan, np.nan)

    if use_area_normalized_plot:
        density_constant = 2.0 / (
            elementary_charge * relative_permittivity * epsilon_0
        )
        fit_basis = "1/(C/A)^2 using C/A in F m^-2"
        fit_unit = "m^4 F^-2"
    else:
        density_constant = 2.0 / (
            elementary_charge * relative_permittivity * epsilon_0 * area_m2 ** 2
        )
        fit_basis = "1/C^2 using total capacitance in F"
        fit_unit = "F^-2"
    density_m3 = float(density_constant / abs(slope))
    density_se_m3 = (
        float(density_m3 * abs(slope_se / slope))
        if np.isfinite(slope_se) else np.nan
    )
    density_ci_m3 = (np.nan, np.nan)
    if np.all(np.isfinite(slope_ci)) and slope_ci[0] * slope_ci[1] > 0:
        abs_bounds = sorted((abs(slope_ci[0]), abs(slope_ci[1])))
        density_ci_m3 = (
            float(density_constant / abs_bounds[1]),
            float(density_constant / abs_bounds[0]),
        )

    x_intercept = float(-intercept / slope)
    if np.all(np.isfinite(covariance)):
        gradient = np.array([intercept / slope ** 2, -1.0 / slope])
        x_intercept_se = float(
            np.sqrt(max(float(gradient @ covariance @ gradient.T), 0.0))
        )
    else:
        x_intercept_se = np.nan
    x_intercept_ci = (
        float(x_intercept - critical * x_intercept_se),
        float(x_intercept + critical * x_intercept_se),
    ) if np.isfinite(critical) else (np.nan, np.nan)
    thermal_voltage = float(Boltzmann * temperature_K / elementary_charge)
    correction = thermal_voltage if apply_thermal_correction else 0.0
    flat_band = float(x_intercept - correction)
    flat_band_ci = (
        float(x_intercept_ci[0] - correction),
        float(x_intercept_ci[1] - correction),
    )

    warnings: list[str] = []
    if point_count < 6:
        warnings.append(
            "Only a small number of points defines the line; uncertainty may be unstable."
        )
    fit_span = float(np.ptp(x_fit))
    if fit_span < 0.10:
        warnings.append(
            "The selected potential span is below 0.10 V; slope and intercept may be sensitive."
        )
    if np.isfinite(r_squared) and r_squared < 0.95:
        warnings.append(
            "The selected region has R² below 0.95 and may not represent a linear depletion region."
        )
    if flat_band < float(np.min(x_fit)) - fit_span or flat_band > float(np.max(x_fit)) + fit_span:
        warnings.append(
            "Flat-band potential is a long extrapolation beyond the selected fit region."
        )
    if "apparent C" in method_label:
        warnings.append(
            "Single-frequency impedance conversion yields apparent interfacial capacitance; "
            "verify frequency independence or an equivalent-circuit space-charge capacitance."
        )
    finite_frequency = frequency[np.isfinite(frequency) & (frequency > 0)]
    if finite_frequency.size and np.max(finite_frequency) / np.min(finite_frequency) > 1.10:
        warnings.append(
            "Selected frequencies vary by more than 10 percent across potential steps."
        )
    if np.all(np.isfinite(slope_ci)) and slope_ci[0] * slope_ci[1] <= 0:
        warnings.append(
            "The slope confidence interval crosses zero; semiconductor type and density are unresolved."
        )
    warnings.append(
        "Reported carrier density is apparent and assumes a planar depletion layer, known "
        "permittivity, and negligible Helmholtz/surface-state capacitance."
    )

    calculated = data.copy()
    calculated["capacitance_method"] = method_label
    calculated["frequency_used_Hz"] = frequency
    calculated["capacitance_total_F"] = capacitance_total_F
    calculated["capacitance_areal_F_m2"] = capacitance_areal_F_m2
    calculated["inverse_C2_F_minus2"] = inverse_total
    calculated["inverse_areal_C2_m4_F_minus2"] = inverse_areal
    calculated["fit_selected"] = selected
    calculated["mott_schottky_y"] = ordinate
    calculated["mott_schottky_fit_y"] = slope * potential + intercept
    calculated["mott_schottky_residual"] = np.where(
        selected,
        ordinate - (slope * potential + intercept),
        np.nan,
    )

    stats: dict[str, object] = {
        "semiconductor_type_from_slope": "n-type" if slope > 0 else "p-type",
        "capacitance_method": method_label,
        "fit_basis": fit_basis,
        "fit_y_unit": fit_unit,
        "slope": slope,
        "slope_standard_error": slope_se,
        "slope_confidence_interval_low": slope_ci[0],
        "slope_confidence_interval_high": slope_ci[1],
        "intercept": intercept,
        "intercept_standard_error": intercept_se,
        "intercept_confidence_interval_low": intercept_ci[0],
        "intercept_confidence_interval_high": intercept_ci[1],
        "confidence_level": float(confidence_level),
        "r_squared": float(r_squared),
        "rmse": rmse,
        "fit_points": point_count,
        "fit_min_V": float(np.min(x_fit)),
        "fit_max_V": float(np.max(x_fit)),
        "x_intercept_V": x_intercept,
        "x_intercept_standard_error_V": x_intercept_se,
        "thermal_voltage_kT_over_q_V": thermal_voltage,
        "thermal_correction_applied": bool(apply_thermal_correction),
        "flat_band_potential_V": flat_band,
        "flat_band_potential_standard_error_V": x_intercept_se,
        "flat_band_confidence_interval_low_V": flat_band_ci[0],
        "flat_band_confidence_interval_high_V": flat_band_ci[1],
        "carrier_density_m_minus3": density_m3,
        "carrier_density_standard_error_m_minus3": density_se_m3,
        "carrier_density_confidence_interval_low_m_minus3": density_ci_m3[0],
        "carrier_density_confidence_interval_high_m_minus3": density_ci_m3[1],
        "carrier_density_cm_minus3": density_m3 / 1e6,
        "carrier_density_standard_error_cm_minus3": density_se_m3 / 1e6,
        "carrier_density_confidence_interval_low_cm_minus3": density_ci_m3[0] / 1e6,
        "carrier_density_confidence_interval_high_cm_minus3": density_ci_m3[1] / 1e6,
        "electrode_area_cm2": float(electrode_area_cm2),
        "relative_permittivity": float(relative_permittivity),
        "temperature_K": float(temperature_K),
        "input_capacitance_is_areal_F_cm_minus2": bool(input_capacitance_is_areal),
        "warnings": tuple(warnings),
        "reference_scale_note": (
            "Flat-band potential remains on the imported reference-electrode scale."
        ),
    }
    if finite_frequency.size:
        stats["selected_frequency_min_Hz"] = float(np.min(finite_frequency))
        stats["selected_frequency_max_Hz"] = float(np.max(finite_frequency))
        stats["selected_frequency_mean_Hz"] = float(np.mean(finite_frequency))
    for key in (
        "source_kind", "target_frequency_Hz", "max_frequency_deviation_percent",
        "potential_group_tolerance_V", "rejected_potential_groups",
        "source_potential_steps", "capacitance_origin",
    ):
        if key in data.attrs:
            stats[key] = data.attrs[key]
    if "frequency_match_error_percent" in data:
        mismatch = pd.to_numeric(
            data["frequency_match_error_percent"], errors="coerce"
        ).to_numpy(float)
        mismatch = mismatch[np.isfinite(mismatch)]
        if mismatch.size:
            stats["maximum_frequency_match_error_percent"] = float(np.max(mismatch))
            stats["mean_frequency_match_error_percent"] = float(np.mean(mismatch))
    return MottSchottkyResult(calculated, stats)
