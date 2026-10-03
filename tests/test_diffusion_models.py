"""Lightweight scientific regression checks for diffusion model selection."""
from __future__ import annotations

import numpy as np

from eis_studio.models import CIRCUITS
from eis_studio.fitting import FitSettings, auto_fit
from eis_studio.diagnostics import diffusion_signature


def synthetic_fractional_warburg(seed: int = 7):
    rng = np.random.default_rng(seed)
    f = np.logspace(5, -1, 48)
    p = [18.0, 260.0, 2.2e-5, 0.87, 75.0, 0.44]
    z = CIRCUITS["R-(R||CPE)-Wf"].function(f, *p)
    noise = rng.normal(0, 0.002, len(f)) + 1j * rng.normal(0, 0.002, len(f))
    return f, z * (1 + noise)


def test_fractional_diffusion_is_selected():
    f, z = synthetic_fractional_warburg()
    settings = FitSettings(weighting="modulus", max_nfev=10000, robust_loss="soft_l1", multistart=10)
    result = auto_fit(f, z, settings=settings)[0]
    assert result.model_key == "R-(R||CPE)-Wf"
    assert abs(result.params["beta"] - 0.44) < 0.05


def test_diffusion_screen_is_positive():
    f, z = synthetic_fractional_warburg()
    screen = diffusion_signature(f, z)
    assert screen["detected"]
    assert screen["strength"] > 0.5
