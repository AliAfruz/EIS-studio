from __future__ import annotations

import numpy as np

from eis_studio.models import CIRCUITS, evaluate, make_custom_circuit
from eis_studio.fitting import FitSettings, fit_model


def test_finite_open_warburg_low_frequency_is_more_vertical_than_short():
    f = np.logspace(3, -3, 80)
    wo = evaluate("R-(R||CPE)-Wo", f, {"Rs": 5, "Rct": 80, "Q": 2e-5, "alpha": 0.9, "Rw": 60, "tauD": 3})
    ws = evaluate("R-(R||CPE)-Ws", f, {"Rs": 5, "Rct": 80, "Q": 2e-5, "alpha": 0.9, "Rw": 60, "tauD": 3})
    assert abs(wo.imag[-1]) > 10 * abs(ws.imag[-1])
    assert np.isclose(ws.real[-1], 5 + 80 + 60, rtol=0.15)


def test_fit_recovers_finite_open_warburg_clean_spectrum():
    f = np.logspace(5, -2, 72)
    truth = {"Rs": 12.0, "Rct": 220.0, "Q": 1.8e-5, "alpha": 0.86, "Rw": 95.0, "tauD": 2.5}
    z = evaluate("R-(R||CPE)-Wo", f, truth)
    result = fit_model(
        f,
        z,
        "R-(R||CPE)-Wo",
        FitSettings(weighting="modulus", max_nfev=12000, robust_loss="linear", multistart=4),
    )
    assert result.success
    assert abs(result.params["Rs"] - truth["Rs"]) / truth["Rs"] < 0.05
    assert abs(result.params["tauD"] - truth["tauD"]) / truth["tauD"] < 0.15
    assert result.red_chi2 < 1e-8


def test_manual_builder_supports_new_diffusion_elements():
    tree = {
        "type": "series",
        "children": [
            {"type": "element", "kind": "R", "id": "Rs", "params": ["Rs"]},
            {"type": "element", "kind": "Wo", "id": "Wo1", "params": ["Rw1", "tauD1"]},
            {"type": "element", "kind": "G", "id": "G1", "params": ["Rg1", "tauG1"]},
        ],
    }
    spec = make_custom_circuit(tree, name="custom finite diffusion", key="CUSTOM_DIFFUSION")
    f = np.array([1000.0, 1.0])
    z = spec.function(f, 4.0, 30.0, 1.2, 50.0, 0.8)
    assert z.shape == f.shape
    assert np.all(np.isfinite(z.real))
    assert np.all(np.isfinite(z.imag))
