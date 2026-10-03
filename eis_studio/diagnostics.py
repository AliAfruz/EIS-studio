from __future__ import annotations

import numpy as np
from scipy.optimize import lsq_linear
from scipy.stats import linregress


def diffusion_signature(f: np.ndarray, z: np.ndarray) -> dict[str, float | str | bool]:
    """Screen the low-frequency region for a Warburg-like diffusion tail.

    This is a model-selection aid, not proof of a transport mechanism. It
    combines straightness in the Nyquist plane, tail angle, and the frequency
    dependence of -Z''. A 45° ideal Warburg has slope≈1 and beta≈0.5.
    """
    f = np.asarray(f, float)
    z = np.asarray(z, complex)
    mask = np.isfinite(f) & np.isfinite(z.real) & np.isfinite(z.imag) & (f > 0)
    f, z = f[mask], z[mask]
    if len(f) < 6:
        return {
            "detected": False, "classification": "insufficient data", "strength": 0.0,
            "tail_points": len(f), "nyquist_slope": np.nan, "nyquist_r2": np.nan,
            "tail_angle_deg": np.nan, "frequency_beta": np.nan,
            "note": "At least six valid frequencies are needed."
        }
    order = np.argsort(f)  # low to high
    f, z = f[order], z[order]
    n_tail = max(5, min(12, len(f) // 3))
    ft, zt = f[:n_tail], z[:n_tail]
    x, y = zt.real, -zt.imag

    try:
        xy = linregress(x, y)
        slope = float(xy.slope)
        r2 = float(xy.rvalue ** 2)
    except Exception:
        slope, r2 = np.nan, 0.0
    angle = float(np.degrees(np.arctan(slope))) if np.isfinite(slope) else np.nan

    positive = y > 0
    beta = np.nan
    beta_r2 = 0.0
    if np.count_nonzero(positive) >= 4:
        try:
            fr = linregress(np.log(2 * np.pi * ft[positive]), np.log(y[positive]))
            beta = float(-fr.slope)
            beta_r2 = float(fr.rvalue ** 2)
        except Exception:
            pass

    angle_score = max(0.0, 1.0 - abs(angle - 45.0) / 25.0) if np.isfinite(angle) else 0.0
    beta_score = max(0.0, 1.0 - abs(beta - 0.5) / 0.30) if np.isfinite(beta) else 0.0
    growth = float((y[0] - y[-1]) / (abs(y[0]) + 1e-15)) if len(y) else 0.0
    growth_score = float(np.clip(growth, 0.0, 1.0))
    strength = float(np.clip(0.42 * r2 + 0.28 * angle_score + 0.20 * beta_score + 0.10 * growth_score, 0.0, 1.0))

    if strength >= 0.78 and 0.38 <= beta <= 0.62:
        classification = "strong ideal-Warburg-like tail"
    elif strength >= 0.68:
        classification = "strong fractional/anomalous diffusion tail"
    elif strength >= 0.50:
        classification = "possible diffusion tail"
    else:
        classification = "weak or ambiguous diffusion signature"
    return {
        "detected": bool(strength >= 0.50), "classification": classification,
        "strength": strength, "tail_points": int(n_tail), "nyquist_slope": slope,
        "nyquist_r2": r2, "tail_angle_deg": angle, "frequency_beta": beta,
        "frequency_beta_r2": beta_r2,
        "note": "Visual 45° behavior supports diffusion but does not uniquely prove a Warburg mechanism."
    }


def consistency_checks(f: np.ndarray, z: np.ndarray) -> dict[str, float | bool | str]:
    """Practical pre-fit checks. These are diagnostics, not a formal Lin-KK proof."""
    f = np.asarray(f, float); z = np.asarray(z, complex)
    order = np.argsort(f)
    f, z = f[order], z[order]
    duplicate_fraction = 1.0 - len(np.unique(f)) / max(len(f), 1)
    monotonic = bool(np.all(np.diff(f) > 0))
    finite = bool(np.all(np.isfinite(f)) and np.all(np.isfinite(z.real)) and np.all(np.isfinite(z.imag)))
    positive_f = bool(np.all(f > 0))
    decades = float(np.log10(np.max(f) / np.min(f))) if positive_f and len(f) > 1 else 0.0
    dz = np.diff(z)
    smoothness = float(np.median(np.abs(np.diff(dz))) / (np.median(np.abs(dz)) + 1e-15)) if len(z) > 3 else np.nan
    hf_inductive = bool(z.imag[-1] > 0) if len(z) else False
    quality = "good"
    if not finite or not positive_f or duplicate_fraction > 0.05:
        quality = "poor"
    elif decades < 3 or (np.isfinite(smoothness) and smoothness > 2.0):
        quality = "caution"
    out = {
        "finite_values": finite, "positive_frequency": positive_f, "strictly_monotonic_frequency": monotonic,
        "duplicate_frequency_fraction": duplicate_fraction, "frequency_decades": decades,
        "smoothness_index": smoothness, "high_frequency_inductive_signature": hf_inductive,
        "overall": quality,
        "note": "Use a formal Kramers–Kronig/Lin-KK implementation for publication-grade validation.",
    }
    sig = diffusion_signature(f, z)
    out.update({f"diffusion_{k}": v for k, v in sig.items() if k != "note"})
    return out


def drt_tikhonov(f: np.ndarray, z: np.ndarray, n_tau: int = 90, lam: float = 1e-2,
                  nonnegative: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simple real-imag joint DRT inversion with first-derivative Tikhonov regularization."""
    f = np.asarray(f, float); z = np.asarray(z, complex)
    order = np.argsort(f)
    f, z = f[order], z[order]
    omega = 2 * np.pi * f
    tau = np.logspace(np.log10(1 / (2*np.pi*np.max(f))) - 1,
                      np.log10(1 / (2*np.pi*np.min(f))) + 1, n_tau)
    dln = np.mean(np.diff(np.log(tau)))
    kernel = dln / (1.0 + 1j * omega[:, None] * tau[None, :])
    A = np.block([
        [np.ones((len(f), 1)), kernel.real],
        [np.zeros((len(f), 1)), kernel.imag],
    ])
    b = np.r_[z.real, z.imag]
    D = np.zeros((n_tau - 1, n_tau + 1))
    for i in range(n_tau - 1):
        D[i, i + 1] = -1; D[i, i + 2] = 1
    Areg = np.vstack([A, np.sqrt(lam) * D])
    breg = np.r_[b, np.zeros(D.shape[0])]
    if nonnegative:
        lb = np.r_[-np.inf, np.zeros(n_tau)]
        ub = np.full(n_tau + 1, np.inf)
        sol = lsq_linear(Areg, breg, bounds=(lb, ub), max_iter=2000).x
    else:
        sol = np.linalg.lstsq(Areg, breg, rcond=None)[0]
    r_inf, gamma = sol[0], sol[1:]
    z_recon = r_inf + kernel @ gamma
    return tau, gamma, z_recon
