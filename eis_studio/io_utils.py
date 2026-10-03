from __future__ import annotations

from pathlib import Path
from collections import Counter
import csv
import io
import re
import shlex
import numpy as np
import pandas as pd

# Column aliases used by common potentiostat exports. Unicode prime/minus symbols
# are normalized before matching, so Z′, Z″ and −Z″ are also recognized.
FREQ_ALIASES = (
    "frequency", "frequency hz", "freq", "freq hz", "f hz", "hz"
)
REAL_ALIASES = (
    "zreal", "z real", "z'", "z' ohm", "z prime", "z prime ohm",
    "re(z)", "real", "zre", "real impedance"
)
IMAG_ALIASES = (
    "zimag", "z imag", "z''", "im(z)", "imag", "zim", "imaginary impedance",
    "-zimag", "-z''"
)
MAG_ALIASES = (
    "z", "z ohm", "|z|", "|z| ohm", "z magnitude", "impedance magnitude", "modulus", "mod z"
)
PHASE_ALIASES = (
    "phase", "phase angle", "-phase", "minus phase"
)
TIME_ALIASES = (
    "time", "time s", "elapsed time", "seconds"
)
POTENTIAL_ALIASES = (
    "potential", "potential v", "potential mv", "voltage", "voltage v", "voltage mv",
    "applied potential", "applied voltage", "dc potential", "dc potential v", "dc bias",
    "bias", "bias v", "electrode potential", "e v", "ewe", "ewe v",
    "working electrode potential", "we potential", "bias potential", "edc", "edc v",
)
INDEX_ALIASES = (
    "index", "point", "point number", "row", "no", "number"
)

_TRANSLATION = str.maketrans({
    "−": "-",  # mathematical minus
    "–": "-",
    "—": "-",
    "′": "'",  # prime
    "’": "'",
    "″": "''",  # double prime
    "“": '"',
    "”": '"',
})


DELIMITER_LABELS = {
    "\t": "Tab",
    " ": "Space / whitespace",
    ",": "Comma (,)",
    ";": "Semicolon (;)",
    ":": "Colon (:)",
}

_DELIMITER_ALIASES = {
    None: "auto",
    "": "auto",
    "auto": "auto",
    "detect": "auto",
    "automatic": "auto",
    "tab": "\t",
    "\\t": "\t",
    "\t": "\t",
    "space": " ",
    "whitespace": " ",
    "white space": " ",
    " ": " ",
    "comma": ",",
    ",": ",",
    "semicolon": ";",
    "semi-colon": ";",
    ";": ";",
    "colon": ":",
    ":": ":",
}

_DECIMAL_ALIASES = {
    None: "auto",
    "": "auto",
    "auto": "auto",
    "detect": "auto",
    "dot": ".",
    "period": ".",
    ".": ".",
    "comma": ",",
    ",": ",",
}


def _clean_label(value: str) -> str:
    return str(value).strip().lower().translate(_TRANSLATION)


def _norm(value: str) -> str:
    """Normalize a column label while retaining impedance primes and minus signs."""
    text = _clean_label(value)
    text = text.replace("ohms", "ohm").replace("ω", "ohm").replace("Ω", "ohm")
    return re.sub(r"[^a-z0-9'|\-]+", "", text)


def _find_col(columns, aliases, used: set | None = None):
    used = used or set()
    available = [c for c in columns if c not in used]
    normalized = {_norm(c): c for c in available}

    # Exact normalized matches are safest.
    for alias in aliases:
        key = _norm(alias)
        if key and key in normalized:
            return normalized[key]

    # Then allow descriptive aliases to occur inside a longer header such as
    # "Frequency (Hz)". Very short aliases are intentionally excluded here.
    fuzzy_aliases = [_norm(a) for a in aliases if len(_norm(a)) >= 3]
    for column in available:
        key = _norm(column)
        if any(alias and alias in key for alias in fuzzy_aliases):
            return column
    return None


def _potential_scale_to_volts(header: object) -> float:
    """Return the multiplier required to convert a potential header to volts."""
    text = _clean_label(header).replace("μ", "µ")
    if re.search(r"\bmv\b|millivolt", text):
        return 1e-3
    if re.search(r"\bkv\b|kilovolt", text):
        return 1e3
    return 1.0


def _normalize_delimiter(value: str | None) -> str:
    key = value if value in _DELIMITER_ALIASES else str(value).strip().lower()
    if key not in _DELIMITER_ALIASES:
        raise ValueError(
            "Unsupported delimiter. Choose Auto, Space, Tab, Comma, Semicolon, or Colon."
        )
    return _DELIMITER_ALIASES[key]


def _normalize_decimal(value: str | None) -> str:
    key = value if value in _DECIMAL_ALIASES else str(value).strip().lower()
    if key not in _DECIMAL_ALIASES:
        raise ValueError("Unsupported decimal separator. Choose Auto, Dot, or Comma.")
    return _DECIMAL_ALIASES[key]


def _decode_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # latin-1 always succeeds, but retain a defensive fallback.
    return raw.decode("latin-1", errors="replace"), "latin-1"


def _meaningful_lines(text: str, limit: int = 120) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip("\ufeff\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _split_delimited_line(line: str, delimiter: str) -> list[str]:
    if delimiter == " ":
        try:
            return shlex.split(line, comments=False, posix=True)
        except ValueError:
            return re.split(r"\s+", line.strip())
    return next(csv.reader([line], delimiter=delimiter, skipinitialspace=True))


def _as_number(token: str, decimal: str) -> float | None:
    value = str(token).strip().strip('"').strip("'")
    value = value.replace("\u00a0", "").replace(" ", "")
    if not value:
        return None
    # Permit decimal-comma scientific notation. Thousands separators are not
    # guessed because doing so can silently alter impedance values.
    if decimal == ",":
        if value.count(",") == 1:
            value = value.replace(",", ".")
        elif "," in value:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def _detect_decimal(lines: list[str], delimiter: str) -> str:
    # A comma cannot safely be both an unquoted column delimiter and decimal
    # separator. In comma-delimited files, default to the decimal point.
    if delimiter == ",":
        return "."

    dot_count = 0
    comma_count = 0
    for line in lines:
        fields = _split_delimited_line(line, delimiter)
        for field in fields:
            token = str(field).strip()
            if re.fullmatch(r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?", token):
                dot_count += 1
            if re.fullmatch(r"[-+]?\d+,\d+(?:[eE][-+]?\d+)?", token):
                comma_count += 1
    return "," if comma_count > dot_count else "."


def _delimiter_score(
    lines: list[str], delimiter: str, min_numeric_fields: int = 3
) -> tuple[float, str, int]:
    if not lines:
        return float("-inf"), ".", 0
    decimal = _detect_decimal(lines, delimiter)
    parsed = [_split_delimited_line(line, delimiter) for line in lines]

    data_rows: list[tuple[int, int]] = []
    for row_index, fields in enumerate(parsed):
        if len(fields) < min_numeric_fields:
            continue
        numeric_count = sum(_as_number(field, decimal) is not None for field in fields)
        if (
            numeric_count >= min_numeric_fields
            and numeric_count >= int(np.ceil(0.45 * len(fields)))
        ):
            data_rows.append((row_index, len(fields)))
    if len(data_rows) < 2:
        return float("-inf"), decimal, 0

    counts = Counter(field_count for _, field_count in data_rows)
    mode_fields, mode_hits = counts.most_common(1)[0]
    consistency = mode_hits / len(data_rows)
    first_data_index = data_rows[0][0]
    header_match = 0.0
    for row in parsed[max(0, first_data_index - 3):first_data_index]:
        if len(row) == mode_fields and any(_as_number(x, decimal) is None for x in row):
            header_match = 1.0
            break

    score = 5.0 * len(data_rows) + 45.0 * consistency + min(mode_fields, 14) + 22.0 * header_match

    # Decimal-comma values can make a semicolon-delimited file look like a
    # comma-delimited file. Penalize comma when most commas sit between digits
    # and another structural separator is visibly present.
    if delimiter == ",":
        sample = "\n".join(lines)
        comma_total = sample.count(",")
        decimal_like = len(re.findall(r"(?<=\d),(?=\d)", sample))
        other_separators = sum(sample.count(ch) for ch in ("\t", ";", ":"))
        if comma_total and decimal_like / comma_total > 0.70 and other_separators:
            score -= 80.0

    # Prefer an explicit tab over generic whitespace when both parse equally.
    if delimiter == "\t" and any("\t" in line for line in lines):
        score += 8.0
    if delimiter == " " and any("\t" in line for line in lines):
        score -= 8.0
    return score, decimal, mode_fields


def _detect_delimiter(lines: list[str], min_numeric_fields: int = 3) -> tuple[str, str]:
    candidates = ("\t", ";", ":", ",", " ")
    ranked = []
    for delimiter in candidates:
        score, decimal, mode_fields = _delimiter_score(
            lines, delimiter, min_numeric_fields
        )
        ranked.append((score, delimiter, decimal, mode_fields))
    ranked.sort(key=lambda item: item[0], reverse=True)
    best = ranked[0]
    if not np.isfinite(best[0]):
        raise ValueError(
            "Could not determine the text-file delimiter. Select Space, Tab, Comma, "
            "Semicolon, or Colon manually in the Data panel."
        )
    return best[1], best[2]


_SPACE_HEADER_PATTERNS = (
    r"Index",
    r"Frequency\s*\([^)]*\)",
    r"-?\s*Z\s*''\s*\([^)]*\)",
    r"Z\s*'\s*\([^)]*\)",
    r"(?<!['\w])Z\s*\([^)]*\)",
    r"-?\s*Phase\s*\([^)]*\)",
    r"Time\s*\([^)]*\)",
)


def _known_space_headers(line: str) -> list[str]:
    matches: list[tuple[int, int, str]] = []
    for pattern in _SPACE_HEADER_PATTERNS:
        for match in re.finditer(pattern, line, flags=re.IGNORECASE):
            matches.append((match.start(), match.end(), match.group(0).strip()))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected: list[tuple[int, int, str]] = []
    for candidate in matches:
        if any(candidate[0] < end and candidate[1] > start for start, end, _ in selected):
            continue
        selected.append(candidate)
    selected.sort(key=lambda item: item[0])
    return [text for _, _, text in selected]


def _read_space_table(
    text: str, decimal: str, min_numeric_fields: int = 3
) -> pd.DataFrame:
    lines = _meaningful_lines(text, limit=100000)
    rows = [_split_delimited_line(line, " ") for line in lines]
    data_candidates = []
    for index, fields in enumerate(rows):
        numeric_count = sum(_as_number(field, decimal) is not None for field in fields)
        if (
            len(fields) >= min_numeric_fields
            and numeric_count >= min_numeric_fields
            and numeric_count >= int(np.ceil(0.6 * len(fields)))
        ):
            data_candidates.append((index, len(fields)))
    if not data_candidates:
        raise ValueError("No numeric whitespace-delimited EIS rows were found.")
    mode_fields = Counter(count for _, count in data_candidates).most_common(1)[0][0]
    first_data = next(index for index, count in data_candidates if count == mode_fields)

    headers: list[str] | None = None
    for header_index in range(first_data - 1, max(-1, first_data - 5), -1):
        line = lines[header_index]
        known = _known_space_headers(line)
        if len(known) == mode_fields:
            headers = known
            break
        split = rows[header_index]
        if len(split) == mode_fields and any(_as_number(x, decimal) is None for x in split):
            headers = split
            break
    if headers is None:
        headers = [f"Column {index + 1}" for index in range(mode_fields)]
        header_detected = False
    else:
        header_detected = True

    body = []
    for fields in rows[first_data:]:
        if len(fields) != mode_fields:
            continue
        if (
            sum(_as_number(field, decimal) is not None for field in fields)
            < min_numeric_fields
        ):
            continue
        body.append(fields)
    if not body:
        raise ValueError("No consistent whitespace-delimited data rows were found.")
    frame = pd.DataFrame(body, columns=headers)
    frame.attrs["header_detected"] = header_detected
    return frame


def _read_text_table(
    text: str, delimiter: str, decimal: str, min_numeric_fields: int = 3
) -> pd.DataFrame:
    if delimiter == " ":
        return _read_space_table(text, decimal, min_numeric_fields)

    lines = _meaningful_lines(text)
    first_fields = _split_delimited_line(lines[0], delimiter) if lines else []
    first_numeric = sum(_as_number(field, decimal) is not None for field in first_fields)
    header_detected = not (
        len(first_fields) >= min_numeric_fields
        and first_numeric >= min_numeric_fields
        and first_numeric >= int(np.ceil(0.75 * len(first_fields)))
    )
    frame = pd.read_csv(
        io.StringIO(text),
        sep=delimiter,
        engine="python",
        comment="#",
        decimal=decimal,
        skipinitialspace=True,
        header="infer" if header_detected else None,
    )
    if not header_detected:
        frame.columns = [f"Column {index + 1}" for index in range(frame.shape[1])]
    frame.attrs["header_detected"] = header_detected
    return frame


def _read_table(
    path: Path,
    delimiter: str | None = "auto",
    decimal: str | None = "auto",
    min_numeric_fields: int = 3,
) -> tuple[pd.DataFrame, dict]:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path), {
            "file_format": "Excel",
            "delimiter": None,
            "delimiter_mode": "not applicable",
            "decimal": None,
            "decimal_mode": "not applicable",
            "encoding": None,
        }

    requested_delimiter = _normalize_delimiter(delimiter)
    requested_decimal = _normalize_decimal(decimal)
    text, encoding = _decode_text(path)
    lines = _meaningful_lines(text)
    if requested_delimiter == "auto":
        selected_delimiter, detected_decimal = _detect_delimiter(
            lines, min_numeric_fields
        )
        delimiter_mode = "auto-detected"
    else:
        selected_delimiter = requested_delimiter
        detected_decimal = _detect_decimal(lines, selected_delimiter)
        delimiter_mode = "manually selected"

    if requested_decimal == "auto":
        selected_decimal = detected_decimal
        decimal_mode = "auto-detected"
    else:
        selected_decimal = requested_decimal
        decimal_mode = "manually selected"

    raw = _read_text_table(
        text, selected_delimiter, selected_decimal, min_numeric_fields
    )
    return raw, {
        "file_format": "ASCII text",
        "delimiter": selected_delimiter,
        "delimiter_label": DELIMITER_LABELS[selected_delimiter],
        "delimiter_mode": delimiter_mode,
        "decimal": selected_decimal,
        "decimal_label": "Comma (,)" if selected_decimal == "," else "Dot (.)",
        "decimal_mode": decimal_mode,
        "encoding": encoding,
        "header_detected": bool(raw.attrs.get("header_detected", True)),
    }


def _is_index_like(raw: pd.DataFrame, column) -> bool:
    if _find_col([column], INDEX_ALIASES) is not None:
        return True
    series = pd.to_numeric(raw[column], errors="coerce").dropna()
    if len(series) < 3:
        return False
    values = series.to_numpy(float)
    sequential_zero = np.allclose(values, np.arange(len(values)), rtol=0, atol=1e-9)
    sequential_one = np.allclose(values, np.arange(1, len(values) + 1), rtol=0, atol=1e-9)
    return bool(sequential_zero or sequential_one)


def _fallback_core_columns(
    raw: pd.DataFrame, fcol, rcol, icol, additional_excluded=None
):
    """Conservative numeric fallback that avoids known non-core fields."""
    used = {c for c in (fcol, rcol, icol) if c is not None}
    excluded = set(used)
    excluded.update(c for c in (additional_excluded or ()) if c is not None)
    for aliases in (INDEX_ALIASES, TIME_ALIASES, PHASE_ALIASES, MAG_ALIASES):
        candidate = _find_col(raw.columns, aliases)
        if candidate is not None:
            excluded.add(candidate)

    numeric = []
    for column in raw.columns:
        converted = pd.to_numeric(raw[column], errors="coerce")
        if converted.notna().sum() >= 4 and column not in excluded and not _is_index_like(raw, column):
            numeric.append(column)

    if fcol is None and numeric:
        fcol = numeric.pop(0)
    if rcol is None and numeric:
        rcol = numeric.pop(0)
    if icol is None and numeric:
        icol = numeric.pop(0)
    return fcol, rcol, icol


def _relative_median_error(reference: np.ndarray, observed: np.ndarray) -> float:
    scale = np.maximum(np.abs(reference), np.finfo(float).eps)
    return float(np.nanmedian(np.abs(observed - reference) / scale))


def read_eis(
    path: str | Path,
    delimiter: str | None = "auto",
    decimal: str | None = "auto",
) -> pd.DataFrame:
    """Read and standardize an EIS file.

    Canonical output uses the electrochemical complex convention
    ``Z = Zreal + j*Zimag``. Therefore, an instrument column labeled ``-Z''``
    is multiplied by -1 during import. Optional magnitude, phase, time and
    potential, source-index columns are retained when available. ASCII text files support
    automatic or manual Space, Tab, Comma, Semicolon, and Colon delimiters, plus
    automatic/manual dot or comma decimal separators.
    """
    path = Path(path)
    raw, import_format = _read_table(path, delimiter=delimiter, decimal=decimal)
    if raw.empty:
        raise ValueError("The selected file is empty.")

    used: set = set()
    potential_col = _find_col(raw.columns, POTENTIAL_ALIASES, used)
    if potential_col is not None:
        used.add(potential_col)
    fcol = _find_col(raw.columns, FREQ_ALIASES, used)
    if fcol is not None:
        used.add(fcol)
    rcol = _find_col(raw.columns, REAL_ALIASES, used)
    if rcol is not None:
        used.add(rcol)
    icol = _find_col(raw.columns, IMAG_ALIASES, used)

    if not all((fcol, rcol, icol)):
        fcol, rcol, icol = _fallback_core_columns(
            raw, fcol, rcol, icol, additional_excluded=(potential_col,)
        )
    if not all((fcol, rcol, icol)):
        headers = ", ".join(map(str, raw.columns))
        raise ValueError(
            "Could not identify frequency, Z real and Z imaginary columns. "
            f"Detected headers: {headers}"
        )

    optional_used = {fcol, rcol, icol}
    idx_col = _find_col(raw.columns, INDEX_ALIASES, optional_used)
    if idx_col is not None:
        optional_used.add(idx_col)
    mag_col = _find_col(raw.columns, MAG_ALIASES, optional_used)
    if mag_col is not None:
        optional_used.add(mag_col)
    phase_col = _find_col(raw.columns, PHASE_ALIASES, optional_used)
    if phase_col is not None:
        optional_used.add(phase_col)
    time_col = _find_col(raw.columns, TIME_ALIASES, optional_used)

    out = pd.DataFrame({
        "frequency_Hz": pd.to_numeric(raw[fcol], errors="coerce"),
        "Zreal_ohm": pd.to_numeric(raw[rcol], errors="coerce"),
        "Zimag_ohm": pd.to_numeric(raw[icol], errors="coerce"),
    })

    imaginary_sign_converted = _clean_label(icol).lstrip().startswith("-")
    imaginary_sign_assumption = None
    if imaginary_sign_converted:
        out["Zimag_ohm"] *= -1
    elif not import_format.get("header_detected", True) and raw.shape[1] == 3:
        zi = out["Zimag_ohm"].to_numpy(float)
        finite = zi[np.isfinite(zi)]
        if finite.size and np.mean(finite >= 0) >= 0.95 and np.nanmax(finite) > 0:
            out["Zimag_ohm"] *= -1
            imaginary_sign_converted = True
            imaginary_sign_assumption = (
                "Headerless three-column table interpreted as Frequency, Z real, -Z imaginary"
            )

    if idx_col is not None:
        out["source_index"] = pd.to_numeric(raw[idx_col], errors="coerce")
    if mag_col is not None:
        out["impedance_magnitude_ohm"] = pd.to_numeric(raw[mag_col], errors="coerce")
    if phase_col is not None:
        phase_values = pd.to_numeric(raw[phase_col], errors="coerce")
        phase_sign_converted = _clean_label(phase_col).lstrip().startswith("-")
        out["phase_deg"] = -phase_values if phase_sign_converted else phase_values
    else:
        phase_sign_converted = False
    if time_col is not None:
        out["time_s"] = pd.to_numeric(raw[time_col], errors="coerce")
    if potential_col is not None:
        out["potential_V"] = (
            pd.to_numeric(raw[potential_col], errors="coerce")
            * _potential_scale_to_volts(potential_col)
        )

    # Only the three required columns determine whether a row is usable.
    out = out.dropna(subset=["frequency_Hz", "Zreal_ohm", "Zimag_ohm"])
    out = out[out["frequency_Hz"] > 0]
    if "potential_V" in out.columns and out["potential_V"].notna().sum() >= 2:
        out = out.sort_values(
            ["potential_V", "frequency_Hz"], ascending=[True, False]
        ).reset_index(drop=True)
    else:
        out = out.sort_values("frequency_Hz", ascending=False).reset_index(drop=True)
    if len(out) < 4:
        raise ValueError("The file contains too few valid EIS points.")

    warnings: list[str] = []
    z = out["Zreal_ohm"].to_numpy(float) + 1j * out["Zimag_ohm"].to_numpy(float)

    if "impedance_magnitude_ohm" in out:
        observed = out["impedance_magnitude_ohm"].to_numpy(float)
        valid = np.isfinite(observed)
        if valid.any():
            error = _relative_median_error(np.abs(z[valid]), observed[valid])
            if error > 0.02:
                warnings.append(
                    f"Supplied |Z| differs from values calculated from Z' and Z'' "
                    f"(median relative difference {100 * error:.2f}%)."
                )

    if "phase_deg" in out:
        observed_phase = out["phase_deg"].to_numpy(float)
        calculated_phase = np.angle(z, deg=True)
        valid = np.isfinite(observed_phase)
        if valid.any():
            phase_error = float(np.nanmedian(np.abs(observed_phase[valid] - calculated_phase[valid])))
            if phase_error > 2.0:
                warnings.append(
                    "Supplied phase differs from phase calculated from Z' and Z'' "
                    f"(median absolute difference {phase_error:.2f}°)."
                )

    out.attrs.update({
        "source_path": str(path),
        "source_columns": {
            "frequency_Hz": str(fcol),
            "Zreal_ohm": str(rcol),
            "Zimag_ohm": str(icol),
            "source_index": str(idx_col) if idx_col is not None else None,
            "impedance_magnitude_ohm": str(mag_col) if mag_col is not None else None,
            "phase_deg": str(phase_col) if phase_col is not None else None,
            "time_s": str(time_col) if time_col is not None else None,
            "potential_V": str(potential_col) if potential_col is not None else None,
        },
        "potential_scale_to_V": (
            _potential_scale_to_volts(potential_col)
            if potential_col is not None else None
        ),
        "imaginary_sign_converted": imaginary_sign_converted,
        "imaginary_sign_assumption": imaginary_sign_assumption,
        "phase_sign_converted": phase_sign_converted,
        "import_warnings": warnings,
        "import_format": import_format,
    })
    return out


def import_audit_text(data: pd.DataFrame) -> list[str]:
    """Return concise, user-facing audit messages for a standardized dataset."""
    attrs = getattr(data, "attrs", {})
    mapping = attrs.get("source_columns", {})
    lines = []
    import_format = attrs.get("import_format", {})
    if import_format:
        if import_format.get("file_format") == "ASCII text":
            lines.append(
                "ASCII import: "
                f"{import_format.get('delimiter_label')} delimiter "
                f"({import_format.get('delimiter_mode')}); "
                f"{import_format.get('decimal_label')} decimal separator "
                f"({import_format.get('decimal_mode')}); "
                f"encoding {import_format.get('encoding')}."
            )
        else:
            lines.append(f"Import format: {import_format.get('file_format', 'table')}.")
    if mapping:
        core = (
            f"Frequency ← {mapping.get('frequency_Hz')}; "
            f"Z′ ← {mapping.get('Zreal_ohm')}; "
            f"Z″ ← {mapping.get('Zimag_ohm')}"
        )
        lines.append("Column mapping: " + core)
    if attrs.get("imaginary_sign_converted"):
        if attrs.get("imaginary_sign_assumption"):
            lines.append(
                "Headerless 3-column assumption: interpreted columns as Frequency, Z′, -Z″ "
                "and converted the third column to negative Z″. Use Invert imaginary sign if "
                "this export already stores conventional Z″."
            )
        else:
            lines.append("Converted the instrument's -Z″ values to negative Z″ for complex fitting.")
    if attrs.get("phase_sign_converted"):
        lines.append("Converted -Phase values to conventional negative phase angles.")
    optional = [
        label for key, label in (
            ("source_index", "Index"),
            ("impedance_magnitude_ohm", "|Z|"),
            ("phase_deg", "Phase"),
            ("time_s", "Time"),
            ("potential_V", "Potential"),
        ) if key in data.columns
    ]
    if optional:
        lines.append("Retained optional fields: " + ", ".join(optional) + ".")
    lines.extend("Import warning: " + item for item in attrs.get("import_warnings", []))
    return lines


def extract_concentration(filename: str, pattern: str = r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mM|uM|µM|nM|M)"):
    m = re.search(pattern, filename, flags=re.IGNORECASE)
    if not m:
        return None, None
    return float(m.group("value")), m.group("unit")


def save_fit_workbook(path: str | Path, data: pd.DataFrame, fit_df: pd.DataFrame,
                      parameters: pd.DataFrame, ranking: pd.DataFrame | None = None):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        data.to_excel(writer, index=False, sheet_name="Data and fit")
        parameters.to_excel(writer, index=False, sheet_name="Parameters")
        fit_df.to_excel(writer, index=False, sheet_name="Residuals")
        if ranking is not None and not ranking.empty:
            ranking.to_excel(writer, index=False, sheet_name="Model ranking")
