from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Callable
import math
import numpy as np
from scipy.optimize import least_squares, differential_evolution
from scipy.stats import linregress

from .models import CIRCUITS, CircuitSpec
from .diagnostics import diffusion_signature


@dataclass
class FitSettings:
    weighting: str = "modulus"  # unit, modulus, proportional
    max_nfev: int = 5000
    robust_loss: str = "soft_l1"
    multistart: int = 5
    optimizer: str = "least_squares"  # least_squares, hybrid
    de_maxiter: int = 24
    de_popsize: int = 7


@dataclass
class FitResult:
    model_key: str
    model_name: str
    params: dict[str, float]
    stderr: dict[str, float]
    success: bool
    message: str
    nfev: int
    rss: float
    rmse: float
    pseudo_chi2: float
    red_chi2: float
    raw_red_var: float
    relative_rmse_percent: float
    chi2_dof: int
    aic: float
    aicc: float
    bic: float
    residual_score: float
    physical_score: float
    rank_score: float
    z_fit: np.ndarray
    residual_complex: np.ndarray
    fixed_params: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    max_abs_correlation: float = float("nan")
    jacobian_condition: float = float("nan")
    optimizer_name: str = "least_squares"

    def summary_row(self) -> dict:
        row = {
            "model": self.model_name,
            "model_key": self.model_key,
            "success": self.success,
            "RMSE": self.rmse,
            "pseudo_chi2_Zmod": self.pseudo_chi2,
            "reduced_chi2_Zmod": self.red_chi2,
            "relative_RMSE_percent": self.relative_rmse_percent,
            "raw_reduced_variance_ohm2": self.raw_red_var,
            "chi2_degrees_of_freedom": self.chi2_dof,
            "AICc": self.aicc,
            "BIC": self.bic,
            "residual_score": self.residual_score,
            "physical_score": self.physical_score,
            "rank_score": self.rank_score,
            "fixed_parameters": ", ".join(self.fixed_params),
            "warnings": " | ".join(self.warnings),
            "max_abs_parameter_correlation": self.max_abs_correlation,
            "jacobian_condition": self.jacobian_condition,
            "optimizer": self.optimizer_name,
        }
        row.update(self.params)
        for k, v in self.stderr.items():
            row[f"SE_{k}"] = v
        return row


def effective_capacitance_from_fit(result: FitResult) -> dict[str, object]:
    """Return an auditable capacitance candidate for batch Mott-Schottky use.

    Ideal C/Cdl parameters are returned directly. A CPE is converted only when
    its topology is a resistor directly in parallel with that CPE, using the
    Hsu-Mansfeld peak-frequency relation. The function intentionally refuses
    classical faradaic branches where R and diffusion are in series beneath a
    CPE because the same conversion is not generally valid there.
    """
    params = {str(key): float(value) for key, value in result.params.items()}
    model_key = str(getattr(result, "model_key", ""))

    for name in ("Cdl", "C"):
        value = params.get(name)
        if value is not None and np.isfinite(value) and value > 0:
            warning = (
                "Verify that fitted C is the semiconductor space-charge capacitance."
                if name == "Cdl"
                else "Series fitted C is a candidate only; verify its physical assignment."
            )
            return {
                "fit_capacitance_F": float(value),
                "fit_capacitance_component": name,
                "fit_capacitance_method": f"direct fitted {name}",
                "fit_capacitance_warning": warning,
            }

    custom_capacitors = sorted(
        (
            name for name in params
            if name.startswith("C") and name[1:].isdigit()
        ),
        key=lambda name: int(name[1:]),
    )
    for name in custom_capacitors:
        value = params[name]
        if np.isfinite(value) and value > 0:
            return {
                "fit_capacitance_F": float(value),
                "fit_capacitance_component": name,
                "fit_capacitance_method": f"direct fitted {name}",
                "fit_capacitance_warning": (
                    "Custom-circuit capacitance selected by element order; verify "
                    "that it represents the space-charge process."
                ),
            }

    candidates: list[tuple[str, str, str, str, str]] = []
    if "(R||CPE)" in model_key:
        candidates.append(("Q", "alpha", "Rct", "CPE arc", ""))
    if "(R||CPE)-(R||CPE)" in model_key:
        candidates.insert(
            0,
            (
                "Q1", "a1", "R1", "CPE1 high-frequency arc",
                "The first/high-frequency arc was selected; verify process assignment.",
            ),
        )
    if model_key.startswith("custom:"):
        for q_name in sorted(
            (
                name for name in params
                if name.startswith("Q") and name[1:].isdigit()
            ),
            key=lambda name: int(name[1:]),
        ):
            suffix = q_name[1:]
            candidates.append(
                (
                    q_name,
                    f"alpha{suffix}",
                    f"R{suffix}",
                    f"custom CPE{suffix} arc",
                    "Custom topology was inferred from parameter names; verify R||CPE wiring.",
                )
            )

    for q_name, alpha_name, resistance_name, component, warning in candidates:
        q = params.get(q_name)
        alpha = params.get(alpha_name)
        resistance = params.get(resistance_name)
        if q is None or alpha is None or resistance is None:
            continue
        if not (
            np.isfinite(q) and np.isfinite(alpha) and np.isfinite(resistance)
            and q > 0 and resistance > 0 and 0 < alpha <= 1.0
        ):
            continue
        log_capacitance = (
            np.log(q) + (1.0 - alpha) * np.log(resistance)
        ) / alpha
        capacitance = float(np.exp(log_capacitance))
        if np.isfinite(capacitance) and capacitance > 0:
            return {
                "fit_capacitance_F": capacitance,
                "fit_capacitance_component": component,
                "fit_capacitance_method": (
                    f"Hsu-Mansfeld from {q_name}, {alpha_name}, {resistance_name}"
                ),
                "fit_capacitance_warning": warning or (
                    "Effective CPE capacitance assumes a resolved parallel R||CPE arc."
                ),
            }

    return {
        "fit_capacitance_F": np.nan,
        "fit_capacitance_component": "not available",
        "fit_capacitance_method": (
            "fitted model has no supported space-charge capacitance candidate"
        ),
        "fit_capacitance_warning": (
            "Use a physically assigned C/R||CPE model or direct fixed-frequency data."
        ),
    }



def normalized_chi_square(
    z_measured: np.ndarray,
    z_fitted: np.ndarray,
    free_parameters: int = 0,
) -> tuple[float, float, float, int]:
    """Return Z-modulus-normalized pseudo chi-square statistics.

    The dimensionless complex residual at each frequency is normalized by the
    measured impedance modulus::

        q_i = ((dZ'_i)^2 + (dZ''_i)^2) / |Z_i|^2

    ``pseudo_chi2`` is ``sum(q_i)``.  ``reduced_chi2`` uses the EIS convention
    ``N - k`` for the degrees of freedom, where N is the number of complex
    frequency points and k is the number of free circuit parameters.  The
    relative RMS residual is ``100*sqrt(mean(q_i))``.

    This is a scale-independent *pseudo* chi-square.  It is not a formal
    statistical chi-square unless ``|Z|`` represents the experimental standard
    deviation at each frequency.
    """
    measured = np.asarray(z_measured, dtype=complex)
    fitted = np.asarray(z_fitted, dtype=complex)
    if measured.shape != fitted.shape:
        raise ValueError("Measured and fitted impedance arrays must have the same shape.")
    mask = (
        np.isfinite(measured.real) & np.isfinite(measured.imag) &
        np.isfinite(fitted.real) & np.isfinite(fitted.imag)
    )
    measured = measured[mask]
    fitted = fitted[mask]
    if measured.size == 0:
        return float("nan"), float("nan"), float("nan"), 0

    modulus = np.abs(measured)
    finite_positive = modulus[np.isfinite(modulus) & (modulus > 0)]
    reference = float(np.nanmedian(finite_positive)) if finite_positive.size else 1.0
    floor = max(reference * 1e-12, np.finfo(float).tiny)
    scale2 = np.maximum(modulus, floor) ** 2
    delta = fitted - measured
    q = (delta.real ** 2 + delta.imag ** 2) / scale2
    pseudo = float(np.sum(q))
    dof = max(int(measured.size) - int(free_parameters), 1)
    reduced = pseudo / dof
    rel_rms_percent = 100.0 * math.sqrt(max(float(np.mean(q)), 0.0))
    return pseudo, reduced, rel_rms_percent, dof

def _weights(z: np.ndarray, mode: str) -> np.ndarray:
    if mode == "unit":
        return np.ones_like(z.real)
    mag = np.abs(z)
    floor = max(np.nanmedian(mag) * 1e-6, 1e-12)
    if mode == "proportional":
        return 1.0 / np.maximum(np.abs(z.real) + np.abs(z.imag), floor)
    return 1.0 / np.maximum(mag, floor)


def _arc_and_diffusion_guesses(f: np.ndarray, z: np.ndarray) -> dict[str, float]:
    """Estimate Rs, arc diameter, characteristic frequency, and diffusion terms."""
    order = np.argsort(f)[::-1]
    f, z = f[order], z[order]
    zr = z.real
    y = -z.imag
    rs = max(float(np.nanmedian(zr[: max(2, min(4, len(zr)))])), 1e-6)
    total_span = max(float(np.nanmax(zr) - np.nanmin(zr)), max(rs, 1.0))

    # Find a high/mid-frequency arc peak while excluding the lowest-frequency
    # quarter, then find the following valley where diffusion begins to rise.
    cutoff = max(5, int(round(0.75 * len(f))))
    peak = int(np.nanargmax(y[:cutoff])) if cutoff > 0 else int(np.nanargmax(y))
    if peak + 2 < len(f):
        valley = peak + int(np.nanargmin(y[peak:]))
    else:
        valley = min(len(f) - 1, peak + 1)
    rct = float(zr[valley] - rs)
    if not np.isfinite(rct) or rct <= 0:
        rct = total_span * 0.35
    rct = max(rct, 1e-6)
    fc = max(float(f[peak]), 1e-12)
    c_est = 1.0 / max(2 * np.pi * fc * rct, 1e-20)

    sig = diffusion_signature(f, z)
    beta = float(sig.get("frequency_beta", np.nan))
    if not np.isfinite(beta):
        beta = 0.5
    beta = float(np.clip(beta, 0.28, 0.72))

    n_tail = max(5, min(12, len(f) // 3))
    low = np.argsort(f)[:n_tail]
    omega = 2 * np.pi * f[low]
    yim = np.maximum(-z.imag[low], 1e-15)
    # Common ideal-Warburg convention: -Z'' = sigma/sqrt(omega).
    sigma = float(np.nanmedian(yim * np.sqrt(omega)))
    # Fractional W: -Z'' = Aw*sin(beta*pi/2)/omega^beta.
    sine = max(float(np.sin(np.pi * beta / 2.0)), 1e-6)
    aw = float(np.nanmedian(yim * np.power(omega, beta) / sine))
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = max(total_span * np.sqrt(2 * np.pi * np.min(f)), 1e-6)
    if not np.isfinite(aw) or aw <= 0:
        aw = max(total_span * np.power(2 * np.pi * np.min(f), beta), 1e-6)

    fmin = max(float(np.nanmin(f)), 1e-12)
    fmax = max(float(np.nanmax(f)), fmin)
    tau_low = 1.0 / max(2 * np.pi * fmin, 1e-30)
    tau_mid = 1.0 / max(2 * np.pi * max(fc, fmin), 1e-30)
    low_span = float(np.nanmax(zr[low]) - np.nanmin(zr[low])) if len(low) else total_span * 0.3
    rw = max(low_span, total_span * 0.15, 1e-6)
    rg = max(rw, total_span * 0.25, 1e-6)
    rion = max(total_span * 0.6, rct * 0.5, 1e-6)
    qtlm = max(c_est * 2.0, 1e-15)

    return {
        "Rs": rs, "Rct": rct, "R1": rct, "R2": max(total_span - rct, rct * 0.5),
        "C": c_est, "Cdl": c_est, "Q": c_est, "Q1": c_est, "Q2": c_est * 3,
        "alpha": 0.88, "a1": 0.88, "a2": 0.75, "alphaT": 0.88,
        "sigma": sigma, "Aw": aw, "beta": beta,
        "Rw": rw, "tauD": max(tau_low, tau_mid), "Rg": rg, "tauG": max(tau_mid, tau_low * 0.1),
        "Rion": rion, "Qtlm": qtlm,
        "L": max(abs(z.imag[0]) / max(2 * np.pi * f[0], 1e-12), 1e-9),
        "Lads": max(abs(z.imag[0]) / max(2 * np.pi * f[0], 1e-12), 1e-9),
        "Rads": max(rct * 0.3, 1e-6),
    }


def _initial_guess(spec: CircuitSpec, f: np.ndarray, z: np.ndarray) -> np.ndarray:
    defaults = _arc_and_diffusion_guesses(f, z)
    x0 = []
    for p in spec.params:
        name = p.name
        val = defaults.get(name)
        if val is None:
            lower_name = name.lower()
            if name.startswith("Rw"):
                val = defaults["Rw"]
            elif name.startswith("Rg"):
                val = defaults["Rg"]
            elif name.startswith("Rion"):
                val = defaults["Rion"]
            elif name.startswith("Rads"):
                val = defaults["Rads"]
            elif name.startswith("R"):
                val = defaults["Rct"]
            elif name.startswith("Qtlm"):
                val = defaults["Qtlm"]
            elif name.startswith("C") or name.startswith("Q"):
                val = defaults["Q"]
            elif name.startswith("Aw"):
                val = defaults["Aw"]
            elif lower_name.startswith("alphat"):
                val = defaults["alphaT"]
            elif lower_name.startswith("alpha") or (lower_name.startswith("a") and lower_name[1:].isdigit()):
                val = defaults["alpha"]
            elif lower_name.startswith("sigma"):
                val = defaults["sigma"]
            elif lower_name.startswith("beta"):
                val = defaults["beta"]
            elif lower_name.startswith("taud"):
                val = defaults["tauD"]
            elif lower_name.startswith("taug"):
                val = defaults["tauG"]
            elif name.startswith("Lads"):
                val = defaults["Lads"]
            elif name.startswith("L"):
                val = defaults["L"]
            else:
                val = math.sqrt(p.low * p.high) if p.scale == "log" else (p.low + p.high) / 2.0
        x0.append(float(np.clip(val, p.low * 1.001, p.high * 0.999)))
    return np.array(x0, dtype=float)


def initial_guess_values(f: np.ndarray, z: np.ndarray, model_key: str) -> dict[str, float]:
    """Return data-derived physical starting values for a circuit model."""
    spec = CIRCUITS[model_key]
    values = _initial_guess(spec, np.asarray(f, float), np.asarray(z, complex))
    return {p.name: float(v) for p, v in zip(spec.params, values)}


def _encode(spec: CircuitSpec, x_physical: np.ndarray) -> np.ndarray:
    return np.asarray([np.log10(x) if p.scale == "log" else x for p, x in zip(spec.params, x_physical)])


def _decode(spec: CircuitSpec, x_opt: np.ndarray) -> np.ndarray:
    return np.asarray([10.0 ** x if p.scale == "log" else x for p, x in zip(spec.params, x_opt)])


def _bounds(spec: CircuitSpec) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = [], []
    for p in spec.params:
        if p.scale == "log":
            lo.append(np.log10(p.low)); hi.append(np.log10(p.high))
        else:
            lo.append(p.low); hi.append(p.high)
    return np.asarray(lo), np.asarray(hi)


def _residual_structure(resid: np.ndarray) -> float:
    # Lower is better. Combines lag-1 autocorrelation and mean bias.
    scores = []
    for y in (resid.real, resid.imag):
        if len(y) < 3 or np.std(y) == 0:
            scores.append(0.0)
        else:
            ac = np.corrcoef(y[:-1], y[1:])[0, 1]
            scores.append(abs(float(np.nan_to_num(ac))))
        scores.append(abs(float(np.mean(y))) / (float(np.std(y)) + 1e-15))
    return float(np.mean(scores))


def _physical_score(spec: CircuitSpec, values: np.ndarray, z: np.ndarray, f: np.ndarray | None = None) -> float:
    """Penalize boundary solutions and non-identifiable pseudo-elements."""
    score = 0.0
    vals = {p.name: float(v) for p, v in zip(spec.params, values)}
    data_scale = max(float(np.ptp(z.real)), float(np.nanmedian(np.abs(z))), 1.0)
    tau_min = tau_max = None
    if f is not None and len(f):
        f = np.asarray(f, float)
        good = f[np.isfinite(f) & (f > 0)]
        if good.size:
            tau_min = 1.0 / (2 * np.pi * float(np.nanmax(good)))
            tau_max = 1.0 / (2 * np.pi * float(np.nanmin(good)))
    for p, v in zip(spec.params, values):
        if not np.isfinite(v) or v <= p.low * 1.0001 or v >= p.high * 0.9999:
            score += 2.0
        lname = p.name.lower()
        if lname.startswith("a") or p.name in {"alpha", "beta"}:
            if not p.low <= v <= p.high:
                score += 2.0
        if p.name.startswith("R") and p.name != "Rs" and v > 1000.0 * data_scale:
            score += 3.0
        if lname.startswith("tau") and tau_min is not None and tau_max is not None:
            if v < tau_min / 100.0 or v > tau_max * 100.0:
                score += 2.0

    # A two-CPE branch with an effectively infinite parallel resistance is a
    # CPE in series. If its exponent is near 0.5, it is mathematically acting
    # as fractional diffusion and should not masquerade as a second arc.
    if spec.key == "R-(R||CPE)-(R||CPE)":
        for rname, aname in (("R1", "a1"), ("R2", "a2")):
            if vals.get(rname, 0.0) > 100.0 * data_scale:
                score += 3.0
                if 0.30 <= vals.get(aname, 1.0) <= 0.70:
                    score += 2.0
    return score


def _fit_warnings(
    spec: CircuitSpec, values: np.ndarray, stderr: dict[str, float], f: np.ndarray,
    residual_score: float, physical_score: float, success: bool, max_corr: float,
    jac_cond: float, start_spread: float, z: np.ndarray
) -> tuple[str, ...]:
    warnings: list[str] = []
    vals = {p.name: float(v) for p, v in zip(spec.params, values)}
    for p, v in zip(spec.params, values):
        if not np.isfinite(v):
            warnings.append(f"{p.name} is non-finite.")
            continue
        if v <= p.low * 1.01 or v >= p.high * 0.99:
            warnings.append(f"{p.name} is close to its bound.")
        se = stderr.get(p.name, np.nan)
        if np.isfinite(se) and abs(v) > 0 and abs(se / v) > 1.0:
            warnings.append(f"{p.name} has >100% relative standard error.")

    good_f = f[np.isfinite(f) & (f > 0)]
    if good_f.size:
        tau_min = 1.0 / (2 * np.pi * float(np.nanmax(good_f)))
        tau_max = 1.0 / (2 * np.pi * float(np.nanmin(good_f)))
        for name, value in vals.items():
            if name.lower().startswith("tau") and np.isfinite(value):
                if value < tau_min / 10.0 or value > tau_max * 10.0:
                    warnings.append(
                        f"{name} is outside the measured time-window by more than one decade."
                    )

    if np.isfinite(max_corr) and max_corr > 0.98:
        warnings.append(f"Strong parameter correlation detected (max |r|={max_corr:.3f}).")
    if np.isfinite(jac_cond) and jac_cond > 1e10:
        warnings.append("Jacobian is ill-conditioned; parameters may not be identifiable.")
    if start_spread > 1.0:
        warnings.append("Different optimizer starts produced materially different parameter sets.")
    if residual_score > 0.75:
        warnings.append("Residuals remain structured; the circuit may still underfit the data.")
    if physical_score >= 4.0:
        warnings.append("Fit contains physically suspicious or weakly identifiable parameters.")
    if "Lads" in vals and not np.any(np.asarray(z).imag > 0):
        warnings.append("Adsorption inductive branch was fitted although no positive-imaginary loop is obvious.")
    if not success:
        warnings.append("Optimizer did not report formal convergence.")
    return tuple(dict.fromkeys(warnings))


def fit_model(f: np.ndarray, z: np.ndarray, model_key: str, settings: FitSettings | None = None,
              initial: dict[str, float] | None = None, fixed: dict[str, float] | None = None) -> FitResult:
    """Fit a circuit with optional manual starts and fixed parameters.

    ``initial`` supplies physical starting values. ``fixed`` removes named
    parameters from the optimizer and holds them at the supplied physical values.
    """
    settings = settings or FitSettings()
    f = np.asarray(f, dtype=float)
    z = np.asarray(z, dtype=complex)
    order = np.argsort(f)[::-1]
    f, z = f[order], z[order]
    mask = np.isfinite(f) & np.isfinite(z.real) & np.isfinite(z.imag) & (f > 0)
    f, z = f[mask], z[mask]
    spec = CIRCUITS[model_key]

    fixed = dict(fixed or {})
    valid_names = {p.name for p in spec.params}
    unknown = sorted(set(fixed) - valid_names)
    if unknown:
        raise ValueError(f"Unknown fixed parameter(s): {', '.join(unknown)}")

    free_count = len(spec.params) - len(fixed)
    if len(f) * 2 <= free_count + 1:
        raise ValueError("Not enough data points for the number of free parameters.")

    x0_ph = _initial_guess(spec, f, z)
    if initial:
        for i, p in enumerate(spec.params):
            if p.name in initial:
                x0_ph[i] = np.clip(float(initial[p.name]), p.low * 1.001, p.high * 0.999)
    for i, p in enumerate(spec.params):
        if p.name in fixed:
            value = float(fixed[p.name])
            if not (p.low <= value <= p.high):
                raise ValueError(f"Fixed value {p.name}={value:g} is outside [{p.low:g}, {p.high:g}].")
            x0_ph[i] = value

    x0_all = _encode(spec, x0_ph)
    lo_all, hi_all = _bounds(spec)
    free_indices = [i for i, p in enumerate(spec.params) if p.name not in fixed]
    fixed_names = tuple(p.name for p in spec.params if p.name in fixed)
    w = _weights(z, settings.weighting)

    def assemble(x_free: np.ndarray) -> np.ndarray:
        x_all = x0_all.copy()
        if free_indices:
            x_all[np.asarray(free_indices, dtype=int)] = x_free
        return x_all

    def fun_free(x_free: np.ndarray) -> np.ndarray:
        vals = _decode(spec, assemble(x_free))
        calc = spec.function(f, *vals)
        r = (calc - z) * w
        return np.r_[r.real, r.imag]

    start_solutions: list[tuple[float, np.ndarray]] = []
    optimizer_name = settings.optimizer
    if free_indices:
        x0 = x0_all[free_indices]
        lo = lo_all[free_indices]
        hi = hi_all[free_indices]
        best = None
        rng = np.random.default_rng(20260720)
        starts = [x0]
        free_params = [spec.params[i] for i in free_indices]

        def objective(x_free: np.ndarray) -> float:
            r = fun_free(np.asarray(x_free, dtype=float))
            if not np.all(np.isfinite(r)):
                return 1e300
            return float(np.dot(r, r))

        # Optional global search: broad differential-evolution scan in the same
        # encoded parameter space used by least_squares, then local refinement.
        if settings.optimizer == "hybrid" and len(free_indices) >= 2:
            try:
                de_budget = max(5, min(int(settings.de_maxiter), max(5, settings.max_nfev // 350)))
                de = differential_evolution(
                    objective, list(zip(lo, hi)), maxiter=de_budget, popsize=settings.de_popsize,
                    polish=False, seed=20260720, tol=1e-4, updating="immediate", workers=1,
                )
                if np.all(np.isfinite(de.x)):
                    starts.insert(0, np.clip(de.x, lo + 1e-8, hi - 1e-8))
            except Exception:
                optimizer_name = "least_squares_after_failed_global_search"

        for _ in range(max(0, settings.multistart - 1)):
            jitter = np.asarray([
                rng.normal(0, 0.45) if p.scale == "log" else rng.normal(0, 0.07)
                for p in free_params
            ])
            starts.append(np.clip(x0 + jitter, lo + 1e-8, hi - 1e-8))
        for start_values in starts:
            result = least_squares(
                fun_free, start_values, bounds=(lo, hi), max_nfev=settings.max_nfev,
                loss=settings.robust_loss, x_scale="jac"
            )
            residual_vector = fun_free(result.x)
            score = float(np.dot(residual_vector, residual_vector))
            start_solutions.append((score, assemble(result.x)))
            if best is None or score < best[0]:
                best = (score, result)
        assert best is not None
        _, opt = best
        x_final = assemble(opt.x)
        success = bool(opt.success)
        message = str(opt.message)
        nfev = int(opt.nfev)
    else:
        opt = None
        x_final = x0_all
        success = True
        message = "Manual evaluation: all circuit parameters were locked."
        nfev = 0

    vals = _decode(spec, x_final)
    z_fit = spec.function(f, *vals)
    resid = z_fit - z
    rss = float(np.sum(resid.real ** 2 + resid.imag ** 2))
    n = 2 * len(f)
    k = len(free_indices)
    rmse = math.sqrt(rss / n)
    pseudo_chi2, red, relative_rmse_percent, chi2_dof = normalized_chi_square(
        z, z_fit, free_parameters=k
    )
    raw_red_var = rss / max(n - k, 1)
    aic = n * math.log(max(rss / n, 1e-300)) + 2 * k
    aicc = aic + (2 * k * (k + 1)) / max(n - k - 1, 1)
    bic = n * math.log(max(rss / n, 1e-300)) + k * math.log(n)

    stderr = {p.name: (0.0 if p.name in fixed else float("nan")) for p in spec.params}
    max_abs_correlation = float("nan")
    jacobian_condition = float("nan")
    if opt is not None and opt.jac is not None and opt.jac.size and n > k and k > 0:
        try:
            jt_j = opt.jac.T @ opt.jac
            cov_opt = np.linalg.pinv(jt_j) * (2 * opt.cost / max(n - k, 1))
            se_opt = np.sqrt(np.maximum(np.diag(cov_opt), 0))
            denom = np.outer(se_opt, se_opt)
            if denom.size and np.all(np.isfinite(denom)):
                corr = np.divide(cov_opt, denom, out=np.zeros_like(cov_opt), where=denom > 0)
                if corr.shape[0] > 1:
                    off_diag = corr[~np.eye(corr.shape[0], dtype=bool)]
                    max_abs_correlation = float(np.nanmax(np.abs(off_diag))) if off_diag.size else 0.0
            try:
                jacobian_condition = float(np.linalg.cond(opt.jac))
            except Exception:
                jacobian_condition = float("nan")
            for local_i, param_i in enumerate(free_indices):
                p = spec.params[param_i]
                if p.scale == "log":
                    stderr[p.name] = float(np.log(10.0) * vals[param_i] * se_opt[local_i])
                else:
                    stderr[p.name] = float(se_opt[local_i])
        except np.linalg.LinAlgError:
            pass

    start_spread = 0.0
    if start_solutions:
        best_score = min(score for score, _x in start_solutions)
        near = [_decode(spec, x_all) for score, x_all in start_solutions if score <= best_score * 1.05 + 1e-18]
        if len(near) >= 2:
            arr = np.asarray(near, float)
            spreads = []
            for i, p in enumerate(spec.params):
                col = arr[:, i]
                if p.name in fixed or not np.all(np.isfinite(col)):
                    continue
                if p.scale == "log":
                    spreads.append(float(np.nanmax(np.log10(col)) - np.nanmin(np.log10(col))))
                else:
                    spreads.append(float(np.nanmax(col) - np.nanmin(col)) / max(abs(float(np.nanmedian(col))), 1e-15))
            start_spread = max(spreads or [0.0])

    params = {p.name: float(v) for p, v in zip(spec.params, vals)}
    residual_score = _residual_structure(resid)
    physical_score = _physical_score(spec, vals, z, f)
    warnings = _fit_warnings(
        spec, vals, stderr, f, residual_score, physical_score, success,
        max_abs_correlation, jacobian_condition, start_spread, z
    )
    rank_score = aicc + 10 * residual_score + 8 * physical_score + 3.0 * len(warnings)
    return FitResult(
        model_key, spec.name, params, stderr, success, message, nfev,
        rss, rmse, pseudo_chi2, red, raw_red_var, relative_rmse_percent,
        chi2_dof, aic, aicc, bic, residual_score, physical_score,
        rank_score, z_fit, resid, fixed_names, warnings, max_abs_correlation,
        jacobian_condition, optimizer_name
    )


def auto_fit(f: np.ndarray, z: np.ndarray, model_keys: Iterable[str] | None = None,
             settings: FitSettings | None = None,
             progress: Callable[[int, str], None] | None = None) -> list[FitResult]:
    keys = list(model_keys or CIRCUITS.keys())
    results: list[FitResult] = []
    total = max(len(keys), 1)
    if progress is not None:
        progress(0, "Starting advanced auto-fit")
    for index, key in enumerate(keys, 1):
        spec = CIRCUITS.get(key)
        label = spec.name if spec is not None else key
        if progress is not None:
            progress(int((index - 1) / total * 100), f"Fitting {label} ({index}/{total})")
        try:
            results.append(fit_model(f, z, key, settings=settings))
            if progress is not None:
                progress(int(index / total * 100), f"Finished {label} ({index}/{total})")
        except Exception as exc:
            if progress is not None:
                progress(int(index / total * 100), f"Skipped {label}: {exc}")
            continue
    if not results:
        raise RuntimeError("No candidate model could be fitted.")
    min_aicc = min(r.aicc for r in results)
    min_bic = min(r.bic for r in results)
    signature = diffusion_signature(np.asarray(f, float), np.asarray(z, complex))
    diffusion_strength = float(signature.get("strength", 0.0))
    tail_angle = float(signature.get("tail_angle_deg", np.nan))
    vertical_tail = bool(np.isfinite(tail_angle) and tail_angle >= 65.0 and diffusion_strength >= 0.45)

    for r in results:
        da = r.aicc - min_aicc
        db = r.bic - min_bic
        uncertainty_penalty = 0.0
        for name, value in r.params.items():
            se = r.stderr.get(name, np.nan)
            if np.isfinite(se) and value != 0:
                uncertainty_penalty += min(abs(se / value), 10.0)
            else:
                uncertainty_penalty += 1.0
        score = (
            0.55 * da + 0.25 * db + 5.0 * r.residual_score
            + 4.0 * r.physical_score + uncertainty_penalty + 2.0 * len(r.warnings)
        )
        # Evidence-based tie-breakers: when the low-frequency data are diffusion-like,
        # prefer explicit diffusion or distributed-transport models over a degenerate
        # second CPE. Information criteria and residual quality still dominate.
        diffusion_model = any(token in r.model_key for token in ("-W", "(R+W", "Wo", "Ws", "-G", "(R+G", "TLM"))
        if diffusion_model:
            score -= 2.5 * diffusion_strength
        if vertical_tail and any(token in r.model_key for token in ("Wo", "TLMo")):
            score -= 2.0 * diffusion_strength
        if vertical_tail and r.model_key in {"R-(R||CPE)-W", "R-(R||CPE)-Wf"}:
            score += 1.0 * diffusion_strength
        if "Lads" in r.model_key and not np.any(np.asarray(z).imag > 0):
            score += 8.0
        r.rank_score = score

    sorted_results = sorted(results, key=lambda x: x.rank_score)
    best = sorted_results[0]
    best_k = len(CIRCUITS[best.model_key].params) - len(best.fixed_params)
    simpler_close = [
        r for r in sorted_results[1:]
        if (len(CIRCUITS[r.model_key].params) - len(r.fixed_params)) < best_k and (r.aicc - best.aicc) <= 2.0
    ]
    if simpler_close:
        best.warnings = best.warnings + (
            f"A simpler model is within ΔAICc≤2 ({simpler_close[0].model_name}); avoid over-interpreting extra elements.",
        )
    return sorted_results


def calibration(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 3:
        raise ValueError("At least three calibration points are required.")
    lr = linregress(x, y)
    pred = lr.intercept + lr.slope * x
    syx = float(np.sqrt(np.sum((y - pred) ** 2) / max(len(x) - 2, 1)))
    slope_abs = abs(float(lr.slope))
    lod = 3.3 * syx / slope_abs if slope_abs else float("inf")
    loq = 10.0 * syx / slope_abs if slope_abs else float("inf")
    return {
        "slope": float(lr.slope), "intercept": float(lr.intercept), "r": float(lr.rvalue),
        "r2": float(lr.rvalue ** 2), "p": float(lr.pvalue), "slope_stderr": float(lr.stderr),
        "syx": syx, "LOD_3.3syx_slope": lod, "LOQ_10syx_slope": loq,
    }
