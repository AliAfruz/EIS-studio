from pathlib import Path

import numpy as np
import pandas as pd

from eis_studio.io_utils import read_eis
from eis_studio.mott_schottky import (
    extract_mott_schottky_from_eis,
    potential_from_filename,
    read_eis_potential_series,
)


def _potential_series() -> pd.DataFrame:
    rows = []
    for potential, capacitance in zip(
        np.linspace(-0.3, 0.3, 7),
        np.linspace(2e-6, 5e-6, 7),
    ):
        for offset_mv, frequency in (
            (-0.4, 100.0), (-0.2, 300.0), (0.0, 1000.0), (0.5, 10000.0)
        ):
            admittance = 1.0 / 2500.0 + 1j * 2 * np.pi * frequency * capacitance
            impedance = 1.0 / admittance
            rows.append({
                "potential_V": potential + offset_mv * 1e-3,
                "frequency_Hz": frequency,
                "Zreal_ohm": impedance.real,
                "Zimag_ohm": impedance.imag,
            })
    return pd.DataFrame(rows)


def test_extracts_one_common_frequency_point_per_potential():
    extracted = extract_mott_schottky_from_eis(
        _potential_series(),
        target_frequency_hz=1000.0,
        potential_group_tolerance_V=0.002,
    )
    assert len(extracted) == 7
    assert np.allclose(extracted["frequency_Hz"], 1000.0)
    assert np.max(extracted["potential_group_span_mV"]) <= 1.0
    assert extracted.attrs["source_potential_steps"] == 7


def test_multiple_files_recover_filename_potentials(tmp_path: Path):
    paths = []
    base = _potential_series()
    for potential, group in base.groupby(np.round(base["potential_V"], 1)):
        path = tmp_path / f"sample_{float(potential):+.1f}V.csv"
        group[["frequency_Hz", "Zreal_ohm", "Zimag_ohm"]].to_csv(
            path, index=False
        )
        paths.append(path)
    result = read_eis_potential_series(paths, target_frequency_hz=1000.0)
    assert result["potential_V"].nunique() == 7
    assert set(result["potential_source"]) == {"filename"}


def test_filename_parser_ignores_frequency_tokens():
    assert potential_from_filename("electrode_-0.25V.csv") == -0.25
    assert potential_from_filename("electrode_+150mV.txt") == 0.15
    assert potential_from_filename("electrode_1000Hz.csv") is None


def test_eis_import_converts_embedded_potential_millivolts(tmp_path: Path):
    path = tmp_path / "potential_mv.csv"
    path.write_text(
        "Potential (mV),Frequency (Hz),Zreal (ohm),Zimag (ohm)\n"
        "-200,10000,10,-1\n-200,1000,20,-4\n"
        "-100,10000,11,-1.2\n-100,1000,22,-4.5\n",
        encoding="utf-8",
    )
    data = read_eis(path)
    assert sorted(data["potential_V"].unique().tolist()) == [-0.2, -0.1]
