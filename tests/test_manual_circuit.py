import numpy as np
import pytest

from eis_studio.models import CIRCUITS, evaluate, make_custom_circuit
from eis_studio.fitting import FitSettings, fit_model


def custom_tree():
    return {
        "type": "series",
        "children": [
            {"type": "element", "kind": "R", "id": "R1", "params": ["R1"]},
            {
                "type": "parallel",
                "branches": [
                    {"type": "series", "children": [
                        {"type": "element", "kind": "R", "id": "R2", "params": ["R2"]}
                    ]},
                    {"type": "series", "children": [
                        {"type": "element", "kind": "CPE", "id": "CPE1", "params": ["Q1", "alpha1"]}
                    ]},
                ],
            },
            {"type": "element", "kind": "Wβ", "id": "Wf1", "params": ["Aw1", "beta1"]},
        ],
    }


def test_custom_circuit_fit_with_locked_parameter():
    spec = make_custom_circuit(custom_tree(), "Custom regression")
    CIRCUITS["CUSTOM"] = spec
    frequency = np.logspace(5, -1, 50)
    truth = {"R1": 25.0, "R2": 300.0, "Q1": 2e-5, "alpha1": 0.87, "Aw1": 55.0, "beta1": 0.46}
    impedance = evaluate("CUSTOM", frequency, truth)

    result = fit_model(
        frequency,
        impedance,
        "CUSTOM",
        FitSettings(weighting="modulus", robust_loss="linear", multistart=4),
        initial=truth,
        fixed={"R1": truth["R1"]},
    )

    assert result.success
    assert result.fixed_params == ("R1",)
    assert result.stderr["R1"] == 0.0
    assert result.rmse < 1e-8
    for name, value in truth.items():
        assert result.params[name] == pytest.approx(value, rel=1e-6)


def test_all_parameters_can_be_manually_locked():
    spec = make_custom_circuit(custom_tree(), "All fixed regression")
    CIRCUITS["CUSTOM"] = spec
    frequency = np.logspace(4, -1, 35)
    truth = {"R1": 20.0, "R2": 180.0, "Q1": 4e-6, "alpha1": 0.91, "Aw1": 40.0, "beta1": 0.50}
    impedance = evaluate("CUSTOM", frequency, truth)
    result = fit_model(frequency, impedance, "CUSTOM", fixed=truth)
    assert result.success
    assert result.nfev == 0
    assert set(result.fixed_params) == set(truth)
    assert result.rmse < 1e-8


def test_empty_parallel_branch_is_rejected():
    tree = custom_tree()
    tree["children"][1]["branches"].append({"type": "series", "children": []})
    with pytest.raises(ValueError, match="empty"):
        make_custom_circuit(tree)
