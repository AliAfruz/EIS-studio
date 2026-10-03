import numpy as np

from eis_studio.fitting import normalized_chi_square, fit_model, FitSettings
from eis_studio.models import CIRCUITS


def test_normalized_chi_square_is_scale_invariant():
    measured = np.array([3 + 4j, 6 + 8j, 5 - 12j], dtype=complex)
    fitted = measured * (1.0 + 0.01)

    p1, r1, rel1, dof1 = normalized_chi_square(measured, fitted, free_parameters=0)
    p2, r2, rel2, dof2 = normalized_chi_square(measured * 1000, fitted * 1000, free_parameters=0)

    assert np.isclose(p1, p2, rtol=1e-13, atol=1e-15)
    assert np.isclose(r1, r2, rtol=1e-13, atol=1e-15)
    assert np.isclose(rel1, rel2, rtol=1e-13, atol=1e-15)
    assert dof1 == dof2 == 3


def test_one_percent_complex_relative_error_gives_expected_value():
    measured = np.array([3 + 4j, 6 + 8j, 5 - 12j, 8 + 15j], dtype=complex)
    fitted = measured * 1.01

    pseudo, reduced, relative_rms_percent, dof = normalized_chi_square(
        measured, fitted, free_parameters=0
    )

    assert np.isclose(pseudo, len(measured) * 1e-4, rtol=1e-12)
    assert np.isclose(reduced, 1e-4, rtol=1e-12)
    assert np.isclose(relative_rms_percent, 1.0, rtol=1e-12)
    assert dof == len(measured)


def test_exact_fit_returns_zero():
    measured = np.array([10 - 2j, 20 - 5j], dtype=complex)
    pseudo, reduced, relative_rms_percent, dof = normalized_chi_square(
        measured, measured.copy(), free_parameters=1
    )
    assert pseudo == 0.0
    assert reduced == 0.0
    assert relative_rms_percent == 0.0
    assert dof == 1


def test_fit_result_reports_dimensionless_normalized_chi_square():
    f = np.logspace(5, -1, 50)
    spec = CIRCUITS["R-(R||CPE)"]
    z_exact = spec.function(f, 15.0, 220.0, 2.5e-5, 0.88)
    # Deterministic 0.3% complex multiplicative perturbation.
    z_measured = z_exact * 1.003

    result = fit_model(
        f,
        z_measured,
        "R-(R||CPE)",
        settings=FitSettings(weighting="modulus", robust_loss="linear", multistart=2),
    )

    assert np.isfinite(result.pseudo_chi2)
    assert np.isfinite(result.red_chi2)
    assert np.isfinite(result.raw_red_var)
    assert np.isfinite(result.relative_rmse_percent)
    assert result.red_chi2 >= 0.0
    assert result.chi2_dof == len(f) - len(spec.params)
