from pathlib import Path

import numpy as np
import pytest

from eis_studio.fitting import FitSettings
from eis_studio.models import evaluate
from eis_studio.paired_batch import analyze_st_folder, parse_st_filename


def _write_eis(path: Path, rct: float) -> None:
    frequency = np.logspace(5, -1, 36)
    params = {"Rs": 40.0, "Rct": rct, "Q": 8e-6, "alpha": 0.88}
    impedance = evaluate("R-(R||CPE)", frequency, params)
    lines = ["Index\tFrequency (Hz)\tZ' (Ω)\t-Z'' (Ω)\tZ (Ω)\t-Phase (°)\tTime (s)"]
    for index, (f, z) in enumerate(zip(frequency, impedance), 1):
        lines.append(
            f"{index}\t{f:.14g}\t{z.real:.14g}\t{-z.imag:.14g}\t{abs(z):.14g}\t{-np.angle(z, deg=True):.14g}\t{index:.6g}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def test_parse_st_filename_accepts_normal_and_unusual_text_suffixes(tmp_path):
    normal = parse_st_filename(tmp_path / "ST1-A.txt")
    unusual = parse_st_filename(tmp_path / "ST02_B.tx,t")
    assert normal is not None and (normal.st_number, normal.replicate) == (1, "A")
    assert unusual is not None and (unusual.st_number, unusual.replicate) == (2, "B")
    assert parse_st_filename(tmp_path / "sample-A.txt") is None


def test_sequential_pair_analysis_writes_one_txt_per_file_and_rct_summary(tmp_path):
    source = tmp_path / "source"
    reports = tmp_path / "reports"
    source.mkdir()
    truth = {
        "ST1-A.txt": 300.0,
        "ST1-B.txt": 240.0,
        "ST2-A.tx,t": 510.0,
        "ST2-B.txt": 450.0,
    }
    for name, rct in truth.items():
        _write_eis(source / name, rct)

    bundle = analyze_st_folder(
        source,
        reports,
        settings=FitSettings(weighting="modulus", robust_loss="linear", multistart=2, max_nfev=3000),
        auto_select=False,
        model_key="R-(R||CPE)",
    )

    assert len(bundle.file_results) == 4
    assert len(bundle.rct_summary) == 2
    assert (reports / "Rct_results.txt").is_file()
    for sample in ("ST1-A", "ST1-B", "ST2-A", "ST2-B"):
        report = reports / f"{sample}_result.txt"
        assert report.is_file()
        text = report.read_text(encoding="utf-8")
        assert "FITTED PARAMETERS" in text
        assert "MEASURED AND FITTED SPECTRUM" in text
        assert "Rct / ohm" in text

    row1 = bundle.rct_summary.set_index("ST").loc[1]
    row2 = bundle.rct_summary.set_index("ST").loc[2]
    assert row1["RctA_ohm"] == pytest.approx(300.0, rel=2e-4)
    assert row1["RctB_ohm"] == pytest.approx(240.0, rel=2e-4)
    assert row1["RctA_minus_RctB_ohm"] == pytest.approx(60.0, rel=5e-4)
    assert row2["RctA_minus_RctB_ohm"] == pytest.approx(60.0, rel=5e-4)

    summary_text = (reports / "Rct_results.txt").read_text(encoding="utf-8")
    assert "RctA-RctB = Rct(STn-A) - Rct(STn-B)" in summary_text
    assert "RctA_minus_RctB_ohm" in summary_text
