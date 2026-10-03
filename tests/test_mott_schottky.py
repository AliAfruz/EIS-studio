from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy.constants import Boltzmann, elementary_charge, epsilon_0

from eis_studio.fitting import effective_capacitance_from_fit
from eis_studio.mott_schottky import (
    calculate_mott_schottky,
    read_mott_schottky,
)


def test_direct_capacitance_recovers_density_flat_band_and_confidence_interval():
    area_cm2 = 0.42
    epsilon_r = 31.0
    temperature = 298.15
    density_cm3 = 2.4e18
    density_m3 = density_cm3 * 1e6
    flat_band = -0.46
    thermal = Boltzmann * temperature / elementary_charge
    slope = 2.0 / (elementary_charge * epsilon_r * epsilon_0 * density_m3)
    potential = np.linspace(-0.25, 0.45, 30)
    inverse_areal_c2 = slope * (potential - flat_band - thermal)
    capacitance_areal = 1.0 / np.sqrt(inverse_areal_c2)
    capacitance_total = capacitance_areal * area_cm2 * 1e-4
    data = pd.DataFrame({
        "potential_V": potential,
        "capacitance_F": capacitance_total,
    })

    result = calculate_mott_schottky(
        data,
        method="direct",
        electrode_area_cm2=area_cm2,
        relative_permittivity=epsilon_r,
        temperature_K=temperature,
    )

    assert result.statistics["semiconductor_type_from_slope"] == "n-type"
    assert np.isclose(
        result.statistics["carrier_density_cm_minus3"], density_cm3, rtol=1e-12
    )
    assert np.isclose(
        result.statistics["flat_band_potential_V"], flat_band, atol=1e-12
    )
    assert np.isclose(
        result.statistics["flat_band_confidence_interval_low_V"],
        flat_band,
        atol=1e-12,
    )
    assert np.isclose(
        result.statistics["flat_band_confidence_interval_high_V"],
        flat_band,
        atol=1e-12,
    )
    assert result.statistics["r_squared"] == 1.0


def test_parallel_impedance_conversion_recovers_capacitance():
    potential = np.linspace(-0.2, 0.4, 12)
    capacitance = np.linspace(2e-6, 5e-6, len(potential))
    frequency = np.full(len(potential), 1000.0)
    resistance = 3000.0
    admittance = 1.0 / resistance + 1j * 2 * np.pi * frequency * capacitance
    impedance = 1.0 / admittance
    data = pd.DataFrame({
        "potential_V": potential,
        "frequency_Hz": frequency,
        "Zreal_ohm": impedance.real,
        "Zimag_ohm": impedance.imag,
    })
    result = calculate_mott_schottky(
        data,
        method="parallel",
        fixed_frequency_hz=1000.0,
        fit_min_V=-0.2,
        fit_max_V=0.4,
    )
    assert np.allclose(
        result.data["capacitance_total_F"], capacitance, rtol=1e-12, atol=0
    )
    assert any("apparent" in warning for warning in result.statistics["warnings"])


def test_import_converts_millivolts_microfarads_and_detects_areal_hint(tmp_path):
    path = tmp_path / "mott.csv"
    path.write_text(
        "Potential (mV),Capacitance (uF/cm2)\n"
        "-200,2.0\n-100,2.2\n0,2.5\n100,2.9\n200,3.4\n",
        encoding="utf-8",
    )
    data = read_mott_schottky(path)
    assert np.isclose(data.loc[0, "potential_V"], -0.2)
    assert np.isclose(data.loc[0, "capacitance_F"], 2.0e-6)
    assert data.attrs["capacitance_is_areal_hint"] is True


def test_headerless_two_column_import_keeps_first_point(tmp_path):
    path = tmp_path / "headerless.txt"
    path.write_text(
        "-0.2 2.0e-6\n-0.1 2.2e-6\n0.0 2.5e-6\n"
        "0.1 2.9e-6\n0.2 3.4e-6\n",
        encoding="utf-8",
    )
    data = read_mott_schottky(path)
    assert len(data) == 5
    assert np.isclose(data.iloc[0]["potential_V"], -0.2)


def test_pretransformed_inverse_capacitance_is_rejected(tmp_path):
    path = tmp_path / "inverse.csv"
    path.write_text(
        "Potential (V),1/C^2\n"
        "-0.2,1e10\n-0.1,2e10\n0.0,3e10\n0.1,4e10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="inverse capacitance"):
        read_mott_schottky(path)


def test_effective_capacitance_uses_supported_parallel_cpe_only():
    supported = SimpleNamespace(
        model_key="R-(R||CPE)",
        params={"Rs": 5.0, "Rct": 800.0, "Q": 3e-5, "alpha": 0.86},
    )
    derived = effective_capacitance_from_fit(supported)
    expected = (3e-5 * 800.0 ** (1.0 - 0.86)) ** (1.0 / 0.86)
    assert np.isclose(derived["fit_capacitance_F"], expected, rtol=1e-14)
    assert "Hsu-Mansfeld" in derived["fit_capacitance_method"]

    unsupported = SimpleNamespace(
        model_key="R-(CPE||(R+W))",
        params={
            "Rs": 5.0, "Rct": 800.0, "Q": 3e-5,
            "alpha": 0.86, "sigma": 2.0,
        },
    )
    refused = effective_capacitance_from_fit(unsupported)
    assert np.isnan(refused["fit_capacitance_F"])
