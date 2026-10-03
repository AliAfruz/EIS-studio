from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import math
import re
from typing import Callable

import numpy as np
import pandas as pd

from .diagnostics import consistency_checks, diffusion_signature
from .fitting import FitResult, FitSettings, auto_fit, fit_model
from .io_utils import import_audit_text, read_eis
from .models import CIRCUITS


# Accepts normal names such as ST1-A.txt and ST002_B.csv.  The extension is
# deliberately permissive so instrument exports with unusual text suffixes can
# still be processed by the delimiter-detecting importer.
_ST_FILE_RE = re.compile(
    r"^\s*ST[\s_-]*0*(?P<number>\d+)[\s_-]*(?P<replicate>[AB])(?:\..*)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class STFile:
    st_number: int
    replicate: str
    path: Path

    @property
    def sample_id(self) -> str:
        return f"ST{self.st_number}-{self.replicate}"


@dataclass
class PairedAnalysisBundle:
    file_results: pd.DataFrame
    rct_summary: pd.DataFrame
    output_dir: Path
    warnings: list[str]
    report_files: list[Path]


def parse_st_filename(path: str | Path) -> STFile | None:
    """Parse ST<number>-A/B filenames without requiring a particular suffix."""
    path = Path(path)
    match = _ST_FILE_RE.match(path.name)
    if match is None:
        return None
    return STFile(
        st_number=int(match.group("number")),
        replicate=match.group("replicate").upper(),
        path=path,
    )


def discover_st_files(folder: str | Path) -> tuple[list[STFile], list[str]]:
    """Return uniquely named ST files in natural ST/A/B order.

    Duplicate labels are not silently chosen.  The first path is retained for
    processing and a warning lists every duplicate so the result remains
    auditable.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"Input folder does not exist: {folder}")

    found: list[STFile] = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        parsed = parse_st_filename(path)
        if parsed is not None:
            found.append(parsed)

    if not found:
        raise ValueError(
            "No ST A/B files were found. Expected names such as ST1-A.txt and ST1-B.txt."
        )

    unique: dict[tuple[int, str], STFile] = {}
    duplicate_paths: dict[tuple[int, str], list[Path]] = {}
    for item in found:
        key = (item.st_number, item.replicate)
        if key in unique:
            duplicate_paths.setdefault(key, [unique[key].path]).append(item.path)
        else:
            unique[key] = item

    warnings: list[str] = []
    for (st_number, replicate), paths in sorted(duplicate_paths.items()):
        names = ", ".join(path.name for path in paths)
        warnings.append(
            f"Duplicate label ST{st_number}-{replicate}: {names}. "
            f"Only {unique[(st_number, replicate)].path.name} was analyzed."
        )

    ordered = sorted(unique.values(), key=lambda item: (item.st_number, item.replicate))
    labels = {(item.st_number, item.replicate) for item in ordered}
    for st_number in sorted({item.st_number for item in ordered}):
        missing = [rep for rep in ("A", "B") if (st_number, rep) not in labels]
        if missing:
            warnings.append(f"ST{st_number} is missing replicate(s): {', '.join(missing)}.")
    return ordered, warnings


def rct_compatible_model_keys() -> list[str]:
    """Built-in/current circuit keys that expose an explicit Rct parameter."""
    keys: list[str] = []
    for key, spec in CIRCUITS.items():
        if any(param.name == "Rct" for param in spec.params):
            keys.append(key)
    return keys


def _fmt(value, digits: int = 10) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (bool, np.bool_)):
        return "yes" if bool(value) else "no"
    if isinstance(value, str):
        return value
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(value):
        return "NA"
    return f"{value:.{digits}g}"


def _safe_report_stem(item: STFile) -> str:
    return item.sample_id.replace(" ", "_")


def _parameter_unit(model_key: str, name: str) -> str:
    spec = CIRCUITS.get(model_key)
    if spec is None:
        return ""
    for param in spec.params:
        if param.name == name:
            return param.unit
    return ""


def _result_row(item: STFile, data: pd.DataFrame, result: FitResult) -> dict:
    row = {
        "ST": item.st_number,
        "replicate": item.replicate,
        "sample_id": item.sample_id,
        "source_file": str(item.path),
        "status": "success" if result.success else "fit_warning",
        "points": len(data),
        "frequency_max_Hz": float(data["frequency_Hz"].max()),
        "frequency_min_Hz": float(data["frequency_Hz"].min()),
        **result.summary_row(),
    }
    row["Rct_ohm"] = result.params.get("Rct", np.nan)
    row["SE_Rct_ohm"] = result.stderr.get("Rct", np.nan)
    return row


def _error_row(item: STFile, error: Exception) -> dict:
    return {
        "ST": item.st_number,
        "replicate": item.replicate,
        "sample_id": item.sample_id,
        "source_file": str(item.path),
        "status": "error",
        "error": f"{type(error).__name__}: {error}",
        "Rct_ohm": np.nan,
        "SE_Rct_ohm": np.nan,
    }


def _detailed_report_text(
    item: STFile,
    data: pd.DataFrame,
    result: FitResult,
    ranking: list[FitResult],
    settings: FitSettings,
    selection_mode: str,
) -> str:
    f = data["frequency_Hz"].to_numpy(float)
    z = data["Zreal_ohm"].to_numpy(float) + 1j * data["Zimag_ohm"].to_numpy(float)
    spec = CIRCUITS[result.model_key]
    checks = consistency_checks(f, z)
    diffusion = diffusion_signature(f, z)
    audit = import_audit_text(data)

    lines: list[str] = [
        "EIS GOLD STUDIO — DETAILED ST FILE RESULT",
        "=" * 72,
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Sample ID: {item.sample_id}",
        f"ST number: {item.st_number}",
        f"Replicate: {item.replicate}",
        f"Source file: {item.path}",
        f"Valid EIS points: {len(data)}",
        f"Frequency range / Hz: {_fmt(np.max(f))} to {_fmt(np.min(f))}",
        "",
        "IMPORT AUDIT",
        "-" * 72,
    ]
    lines.extend(audit or ["No additional import transformations were reported."])
    for warning in data.attrs.get("import_warnings", []):
        lines.append("Warning: " + str(warning))

    lines.extend([
        "",
        "ANALYSIS SETTINGS",
        "-" * 72,
        f"Model selection: {selection_mode}",
        f"Weighting: {settings.weighting}",
        f"Robust loss: {settings.robust_loss}",
        f"Maximum function evaluations: {settings.max_nfev}",
        f"Multistart count: {settings.multistart}",
        "",
        "SELECTED EQUIVALENT CIRCUIT",
        "-" * 72,
        f"Model: {result.model_name}",
        f"Model key: {result.model_key}",
        f"Expression: {spec.expression}",
        f"Description: {spec.description}",
        f"Fit success: {_fmt(result.success)}",
        f"Optimizer message: {result.message}",
        f"Function evaluations: {result.nfev}",
        "",
        "FITTED PARAMETERS",
        "-" * 72,
        "Parameter\tValue\tStandard_error\tRelative_SE_percent\tUnit",
    ])
    for param in spec.params:
        value = result.params.get(param.name, np.nan)
        se = result.stderr.get(param.name, np.nan)
        rse = 100.0 * se / abs(value) if np.isfinite(se) and value else np.nan
        lines.append(
            "\t".join([
                param.name, _fmt(value), _fmt(se), _fmt(rse), param.unit or "dimensionless"
            ])
        )

    lines.extend([
        "",
        "FIT QUALITY",
        "-" * 72,
        f"RSS / ohm^2: {_fmt(result.rss)}",
        f"RMSE / ohm: {_fmt(result.rmse)}",
        f"Normalized pseudo chi-square (Zmod): {_fmt(result.pseudo_chi2)}",
        f"Normalized reduced chi-square (Zmod): {_fmt(result.red_chi2)}",
        f"Relative residual RMS / percent: {_fmt(result.relative_rmse_percent)}",
        f"Chi-square degrees of freedom (N-k): {_fmt(result.chi2_dof)}",
        f"Legacy raw reduced variance / ohm^2: {_fmt(result.raw_red_var)}",
        "Definition: sum(((dZreal)^2 + (dZimag)^2)/|Zmeasured|^2) / (N-k)",
        "Note: this is a dimensionless EIS pseudo chi-square; exact agreement with another program requires the same weighting, points, model, and degrees-of-freedom convention.",
        f"AIC: {_fmt(result.aic)}",
        f"AICc: {_fmt(result.aicc)}",
        f"BIC: {_fmt(result.bic)}",
        f"Residual-structure score: {_fmt(result.residual_score)}",
        f"Physical-plausibility penalty: {_fmt(result.physical_score)}",
        f"Auto-fit rank score: {_fmt(result.rank_score)}",
        "",
        "Rct RESULT",
        "-" * 72,
        f"Rct / ohm: {_fmt(result.params.get('Rct', np.nan))}",
        f"SE(Rct) / ohm: {_fmt(result.stderr.get('Rct', np.nan))}",
        "",
        "CONSISTENCY SCREENING",
        "-" * 72,
    ])
    for key, value in checks.items():
        lines.append(f"{key}: {_fmt(value)}")

    lines.extend(["", "DIFFUSION SIGNATURE", "-" * 72])
    for key, value in diffusion.items():
        lines.append(f"{key}: {_fmt(value)}")

    if ranking:
        lines.extend([
            "",
            "AUTO-FIT CANDIDATE RANKING",
            "-" * 72,
            "Rank\tModel\tModel_key\tRMSE_ohm\tAICc\tBIC\tRank_score\tRct_ohm",
        ])
        for rank, candidate in enumerate(ranking, 1):
            lines.append("\t".join([
                str(rank), candidate.model_name, candidate.model_key,
                _fmt(candidate.rmse), _fmt(candidate.aicc), _fmt(candidate.bic),
                _fmt(candidate.rank_score), _fmt(candidate.params.get("Rct", np.nan)),
            ]))

    order = np.argsort(f)[::-1]
    lines.extend([
        "",
        "MEASURED AND FITTED SPECTRUM",
        "-" * 72,
        "Frequency_Hz\tZreal_measured_ohm\tminus_Zimag_measured_ohm\t"
        "Zreal_fit_ohm\tminus_Zimag_fit_ohm\tresidual_real_ohm\tresidual_imag_ohm",
    ])
    for idx in order:
        residual = result.residual_complex[idx]
        lines.append("\t".join([
            _fmt(f[idx]), _fmt(z[idx].real), _fmt(-z[idx].imag),
            _fmt(result.z_fit[idx].real), _fmt(-result.z_fit[idx].imag),
            _fmt(residual.real), _fmt(residual.imag),
        ]))

    lines.extend([
        "",
        "INTERPRETATION NOTE",
        "-" * 72,
        "Rct values are directly comparable only when the same physical process and a compatible circuit definition are used for A and B.",
        "Auto-selection is restricted to circuits containing an explicit Rct parameter when Rct-safe mode is enabled.",
        "",
    ])
    return "\n".join(lines)


def _error_report_text(item: STFile, error: Exception) -> str:
    return "\n".join([
        "EIS GOLD STUDIO — ST FILE ANALYSIS ERROR",
        "=" * 72,
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Sample ID: {item.sample_id}",
        f"Source file: {item.path}",
        f"Error type: {type(error).__name__}",
        f"Error message: {error}",
        "",
        "No Rct value was reported for this file.",
        "Check the delimiter, column headers, numerical data, and selected circuit model.",
        "",
    ])


def build_rct_summary(file_results: pd.DataFrame, warnings: list[str] | None = None) -> pd.DataFrame:
    """Create one row per ST number with RctA − RctB and uncertainty."""
    warnings = warnings or []
    columns = [
        "ST", "file_A", "model_A", "RctA_ohm", "SE_RctA_ohm", "RMSE_A_ohm",
        "file_B", "model_B", "RctB_ohm", "SE_RctB_ohm", "RMSE_B_ohm",
        "RctA_minus_RctB_ohm", "SE_difference_ohm", "absolute_difference_ohm",
        "A_over_B_ratio", "percent_change_A_vs_B", "same_model", "status", "note",
    ]
    if file_results.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict] = []
    for st_number in sorted(pd.to_numeric(file_results["ST"], errors="coerce").dropna().astype(int).unique()):
        group = file_results[file_results["ST"] == st_number]
        reps = {str(row["replicate"]): row for _, row in group.iterrows()}
        a = reps.get("A")
        b = reps.get("B")

        def get(row, key, default=np.nan):
            if row is None:
                return default
            value = row.get(key, default)
            return value

        rcta = pd.to_numeric(pd.Series([get(a, "Rct_ohm")]), errors="coerce").iloc[0]
        rctb = pd.to_numeric(pd.Series([get(b, "Rct_ohm")]), errors="coerce").iloc[0]
        sea = pd.to_numeric(pd.Series([get(a, "SE_Rct_ohm")]), errors="coerce").iloc[0]
        seb = pd.to_numeric(pd.Series([get(b, "SE_Rct_ohm")]), errors="coerce").iloc[0]
        valid = np.isfinite(rcta) and np.isfinite(rctb)
        difference = float(rcta - rctb) if valid else np.nan
        se_difference = float(np.sqrt(sea ** 2 + seb ** 2)) if np.isfinite(sea) and np.isfinite(seb) else np.nan
        ratio = float(rcta / rctb) if valid and rctb != 0 else np.nan
        pct = float(100.0 * difference / rctb) if valid and rctb != 0 else np.nan
        model_a = str(get(a, "model", "")) if a is not None else ""
        model_b = str(get(b, "model", "")) if b is not None else ""
        same_model = bool(model_a and model_b and model_a == model_b)

        notes: list[str] = []
        if a is None:
            notes.append("A file missing")
        elif str(get(a, "status", "")) == "error":
            notes.append("A analysis failed")
        if b is None:
            notes.append("B file missing")
        elif str(get(b, "status", "")) == "error":
            notes.append("B analysis failed")
        if valid and not same_model:
            notes.append("A and B selected different circuit models; compare Rct cautiously")
        if not valid and not notes:
            notes.append("Rct unavailable")

        rows.append({
            "ST": int(st_number),
            "file_A": Path(str(get(a, "source_file", ""))).name if a is not None else "",
            "model_A": model_a,
            "RctA_ohm": rcta,
            "SE_RctA_ohm": sea,
            "RMSE_A_ohm": get(a, "RMSE"),
            "file_B": Path(str(get(b, "source_file", ""))).name if b is not None else "",
            "model_B": model_b,
            "RctB_ohm": rctb,
            "SE_RctB_ohm": seb,
            "RMSE_B_ohm": get(b, "RMSE"),
            "RctA_minus_RctB_ohm": difference,
            "SE_difference_ohm": se_difference,
            "absolute_difference_ohm": abs(difference) if np.isfinite(difference) else np.nan,
            "A_over_B_ratio": ratio,
            "percent_change_A_vs_B": pct,
            "same_model": same_model,
            "status": "complete" if valid else "incomplete",
            "note": "; ".join(notes),
        })
    return pd.DataFrame(rows, columns=columns)


def rct_summary_text(
    summary: pd.DataFrame,
    input_folder: Path,
    output_folder: Path,
    warnings: list[str],
    selection_mode: str,
    settings: FitSettings,
) -> str:
    lines = [
        "EIS GOLD STUDIO — ST A/B Rct SUMMARY",
        "=" * 100,
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Input folder: {input_folder}",
        f"Output folder: {output_folder}",
        f"Analysis mode: {selection_mode}",
        f"Weighting: {settings.weighting}; robust loss: {settings.robust_loss}; multistart: {settings.multistart}",
        "Definition: RctA-RctB = Rct(STn-A) - Rct(STn-B), in ohms.",
        "SE_difference assumes independent fitted Rct estimates: sqrt(SE_A^2 + SE_B^2).",
        "",
        "WARNINGS",
        "-" * 100,
    ]
    lines.extend(warnings or ["None."])
    lines.extend([
        "",
        "Rct RESULTS (tab-delimited; directly pasteable into Excel/Origin)",
        "-" * 100,
    ])
    if summary.empty:
        lines.append("No paired results were available.")
    else:
        lines.append("\t".join(summary.columns))
        for _, row in summary.iterrows():
            lines.append("\t".join(_fmt(row[column]) for column in summary.columns))
    lines.extend([
        "",
        "IMPORTANT COMPARABILITY NOTE",
        "-" * 100,
        "The RctA-RctB difference is most defensible when A and B are fitted with the same circuit topology and represent the same interfacial process.",
        "Rows with different selected models are retained but flagged in the note column.",
        "",
    ])
    return "\n".join(lines)


def analyze_st_folder(
    input_folder: str | Path,
    output_folder: str | Path,
    settings: FitSettings | None = None,
    *,
    auto_select: bool = True,
    model_key: str = "R-(R||CPE)",
    rct_safe_auto: bool = True,
    progress: Callable[[int, str], None] | None = None,
) -> PairedAnalysisBundle:
    """Sequentially fit ST A/B files and write one detailed TXT per file.

    A combined ``Rct_results.txt`` is always written.  Processing continues if
    one file fails, and that file receives its own clean error report.
    """
    settings = settings or FitSettings()
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    files, warnings = discover_st_files(input_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    if auto_select:
        candidate_keys = rct_compatible_model_keys() if rct_safe_auto else list(CIRCUITS.keys())
        if not candidate_keys:
            raise ValueError("No equivalent-circuit models with an explicit Rct parameter are available.")
        selection_mode = (
            "Rct-compatible auto-fit for each file"
            if rct_safe_auto else "unrestricted auto-fit for each file"
        )
    else:
        if model_key not in CIRCUITS:
            raise ValueError(f"Unknown selected circuit model: {model_key}")
        if not any(param.name == "Rct" for param in CIRCUITS[model_key].params):
            raise ValueError(
                f"Selected model '{CIRCUITS[model_key].name}' has no explicit Rct parameter. "
                "Choose an Rct circuit or enable Rct-compatible auto-fit."
            )
        candidate_keys = []
        selection_mode = f"fixed selected model for all files: {CIRCUITS[model_key].name}"

    rows: list[dict] = []
    report_files: list[Path] = []
    total = max(len(files), 1)
    for index, item in enumerate(files, 1):
        if progress is not None:
            progress(int((index - 1) / total * 100), item.path.name)
        report_path = output_folder / f"{_safe_report_stem(item)}_result.txt"
        try:
            data = read_eis(item.path)
            f = data["frequency_Hz"].to_numpy(float)
            z = data["Zreal_ohm"].to_numpy(float) + 1j * data["Zimag_ohm"].to_numpy(float)
            if auto_select:
                ranking = auto_fit(f, z, model_keys=candidate_keys, settings=settings)
                result = ranking[0]
            else:
                result = fit_model(f, z, model_key, settings=settings)
                ranking = [result]
            rows.append(_result_row(item, data, result))
            report_path.write_text(
                _detailed_report_text(item, data, result, ranking, settings, selection_mode),
                encoding="utf-8",
            )
        except Exception as error:
            rows.append(_error_row(item, error))
            report_path.write_text(_error_report_text(item, error), encoding="utf-8")
            warnings.append(f"{item.sample_id} failed: {type(error).__name__}: {error}")
        report_files.append(report_path)

    file_results = pd.DataFrame(rows).sort_values(["ST", "replicate"]).reset_index(drop=True)
    rct_summary = build_rct_summary(file_results, warnings)
    summary_path = output_folder / "Rct_results.txt"
    summary_path.write_text(
        rct_summary_text(
            rct_summary, input_folder, output_folder, warnings, selection_mode, settings
        ),
        encoding="utf-8",
    )
    report_files.insert(0, summary_path)

    # Machine-readable companions are useful but TXT remains the primary output.
    file_results.to_csv(output_folder / "all_file_fit_results.tsv", sep="\t", index=False)
    rct_summary.to_csv(output_folder / "Rct_results.tsv", sep="\t", index=False)
    if progress is not None:
        progress(100, "Complete")
    return PairedAnalysisBundle(
        file_results=file_results,
        rct_summary=rct_summary,
        output_dir=output_folder,
        warnings=warnings,
        report_files=report_files,
    )
