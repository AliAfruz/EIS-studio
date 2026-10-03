from pathlib import Path

import numpy as np
import pytest

from eis_studio.io_utils import read_eis


HEADERS = ["Index", "Frequency (Hz)", "Z' (Ω)", "-Z'' (Ω)", "Z (Ω)", "-Phase (°)", "Time (s)"]
ROWS = [
    [1, 1000.0, 25.0, 4.0, np.hypot(25.0, 4.0), np.degrees(np.arctan2(4.0, 25.0)), 1.0],
    [2, 100.0, 31.0, 8.0, np.hypot(31.0, 8.0), np.degrees(np.arctan2(8.0, 31.0)), 2.0],
    [3, 10.0, 47.0, 14.0, np.hypot(47.0, 14.0), np.degrees(np.arctan2(14.0, 47.0)), 3.0],
    [4, 1.0, 72.0, 28.0, np.hypot(72.0, 28.0), np.degrees(np.arctan2(28.0, 72.0)), 4.0],
]


def _number(value: float, decimal: str = ".") -> str:
    text = f"{value:.10g}"
    return text.replace(".", ",") if decimal == "," else text


def _write(path: Path, delimiter: str, decimal: str = ".", quoted_space_header: bool = False) -> None:
    if delimiter == " ":
        header = " ".join(f'"{item}"' for item in HEADERS) if quoted_space_header else " ".join(HEADERS)
    else:
        header = delimiter.join(HEADERS)
    lines = [header]
    for row in ROWS:
        lines.append(delimiter.join(_number(value, decimal) for value in row))
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.parametrize(
    "delimiter,name",
    [("\t", "tab"), (",", "comma"), (";", "semicolon"), (":", "colon"), (" ", "space")],
)
def test_auto_detects_supported_ascii_delimiters(tmp_path, delimiter, name):
    path = tmp_path / f"sample_{name}.txt"
    _write(path, delimiter)
    data = read_eis(path)
    assert len(data) == 4
    assert data["frequency_Hz"].to_numpy() == pytest.approx([1000.0, 100.0, 10.0, 1.0])
    assert data["Zreal_ohm"].to_numpy() == pytest.approx([25.0, 31.0, 47.0, 72.0])
    assert data["Zimag_ohm"].to_numpy() == pytest.approx([-4.0, -8.0, -14.0, -28.0])
    expected = "Space / whitespace" if delimiter == " " else {
        "\t": "Tab", ",": "Comma (,)", ";": "Semicolon (;)", ":": "Colon (:)"
    }[delimiter]
    assert data.attrs["import_format"]["delimiter_label"] == expected


def test_decimal_comma_with_semicolon_is_detected_without_column_confusion(tmp_path):
    path = tmp_path / "decimal_comma.txt"
    _write(path, ";", decimal=",")
    data = read_eis(path)
    assert data["Zreal_ohm"].iloc[-1] == pytest.approx(72.0)
    assert data["Zimag_ohm"].iloc[0] == pytest.approx(-4.0)
    assert data.attrs["import_format"]["delimiter"] == ";"
    assert data.attrs["import_format"]["decimal"] == ","


def test_manual_delimiter_and_decimal_override(tmp_path):
    path = tmp_path / "manual_colon.txt"
    _write(path, ":", decimal=",")
    data = read_eis(path, delimiter="colon", decimal="comma")
    assert len(data) == 4
    assert data.attrs["import_format"]["delimiter_mode"] == "manually selected"
    assert data.attrs["import_format"]["decimal_mode"] == "manually selected"


def test_potential_zre_zim_potentiostat_table_is_imported():
    path = Path(__file__).parents[1] / "sample_potential_zre_zim.txt"
    data = read_eis(path)

    assert len(data) == 21
    assert data.attrs["import_format"]["delimiter"] == "\t"
    assert data.attrs["source_columns"]["frequency_Hz"] == "Frequency (Hz)"
    assert data.attrs["source_columns"]["Zreal_ohm"] == "Zre (ohms)"
    assert data.attrs["source_columns"]["Zimag_ohm"] == "Zim (ohms)"
    assert data.attrs["source_columns"]["potential_V"] == "Potential (V)"
    assert not data.attrs["imaginary_sign_converted"]
    assert data["potential_V"].to_numpy() == pytest.approx([0.188445196] * 21)
    assert data["Zimag_ohm"].iloc[0] == pytest.approx(2.893992901)
    assert data["Zimag_ohm"].iloc[-1] == pytest.approx(-0.284101486)
    assert data["impedance_magnitude_ohm"].iloc[0] == pytest.approx(5.627956662)
