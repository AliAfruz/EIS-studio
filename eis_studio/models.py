from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
import numpy as np

Array = np.ndarray


def _omega(f: Array) -> Array:
    return 2.0 * np.pi * np.asarray(f, dtype=float)


def _jw(f: Array) -> Array:
    return 1j * _omega(f)


def z_r(f: Array, r: float) -> Array:
    return np.full_like(np.asarray(f, dtype=float), complex(r), dtype=complex)


def z_c(f: Array, c: float) -> Array:
    return 1.0 / (_jw(f) * c)


def z_l(f: Array, l: float) -> Array:
    return _jw(f) * l


def z_cpe(f: Array, q: float, alpha: float) -> Array:
    return 1.0 / (q * np.power(_jw(f), alpha))


def z_warburg(f: Array, sigma: float) -> Array:
    """Semi-infinite Warburg, ZW = sigma(1-j)/sqrt(omega)."""
    omega = np.maximum(_omega(f), np.finfo(float).tiny)
    return sigma * (1.0 - 1.0j) / np.sqrt(omega)


def z_fractional_warburg(f: Array, aw: float, beta: float) -> Array:
    """Generalized/fractional semi-infinite diffusion impedance."""
    return aw / np.power(_jw(f), beta)


def _sqrt_jwt(f: Array, tau: float) -> Array:
    tau = max(float(tau), np.finfo(float).tiny)
    return np.sqrt(_jw(f) * tau)


def _stable_tanh(x: Array, threshold: float = 40.0) -> Array:
    """Numerically stable tanh for complex diffusion arguments.

    np.tanh overflows for large complex arguments even though the physical
    finite-length diffusion limit is bounded: tanh(x) -> 1 when Re(x) is
    large and positive.  sqrt(jωτ) has a non-negative real part on the
    principal branch, so this clipping preserves the high-frequency limit
    while avoiding noisy RuntimeWarnings during global optimization.
    """
    x = np.asarray(x, dtype=complex)
    out = np.empty_like(x, dtype=complex)
    large_pos = np.real(x) > threshold
    large_neg = np.real(x) < -threshold
    middle = ~(large_pos | large_neg)
    out[large_pos] = 1.0 + 0.0j
    out[large_neg] = -1.0 + 0.0j
    out[middle] = np.tanh(x[middle])
    return out


def z_warburg_open(f: Array, rw: float, tau_d: float) -> Array:
    """Finite-length open/blocking diffusion.

    Z = Rw*coth(sqrt(jωτD))/sqrt(jωτD). At low frequency this approaches
    a blocking capacitive vertical branch plus Rw/3.
    """
    x = _sqrt_jwt(f, tau_d)
    # coth(x)=1/tanh(x).  The small floor avoids 0/0 for extremely low f.
    x = np.where(np.abs(x) < 1e-18, 1e-18 + 0j, x)
    tanh_x = _stable_tanh(x)
    return rw / (x * tanh_x)


def z_warburg_short(f: Array, rw: float, tau_d: float) -> Array:
    """Finite-length short/transmissive diffusion.

    Z = Rw*tanh(sqrt(jωτD))/sqrt(jωτD). At low frequency this tends to Rw.
    """
    x = _sqrt_jwt(f, tau_d)
    x = np.where(np.abs(x) < 1e-18, 1e-18 + 0j, x)
    tanh_x = _stable_tanh(x)
    return rw * tanh_x / x


def z_gerischer(f: Array, rg: float, tau_g: float) -> Array:
    """Gerischer reaction-diffusion impedance, Rg/sqrt(1+jωτG)."""
    tau_g = max(float(tau_g), np.finfo(float).tiny)
    return rg / np.sqrt(1.0 + _jw(f) * tau_g)


def z_tlm_open(f: Array, rion: float, q: float, alpha: float) -> Array:
    """Simple finite-length porous-electrode transmission line with blocking end.

    The normalized de Levie form uses a distributed ionic resistance and a
    distributed CPE admittance: Z = sqrt(Rion/Y)*coth(sqrt(Rion*Y)).
    """
    y = q * np.power(_jw(f), alpha)
    y = np.where(np.abs(y) < 1e-30, 1e-30 + 0j, y)
    x = np.sqrt(rion * y)
    x = np.where(np.abs(x) < 1e-18, 1e-18 + 0j, x)
    tanh_x = _stable_tanh(x)
    return np.sqrt(rion / y) / tanh_x


def z_tlm_short(f: Array, rion: float, q: float, alpha: float) -> Array:
    """Simple finite-length porous-electrode transmission line with transmissive end."""
    y = q * np.power(_jw(f), alpha)
    y = np.where(np.abs(y) < 1e-30, 1e-30 + 0j, y)
    x = np.sqrt(rion * y)
    x = np.where(np.abs(x) < 1e-18, 1e-18 + 0j, x)
    tanh_x = _stable_tanh(x)
    return np.sqrt(rion / y) * tanh_x


def parallel(*items: Array) -> Array:
    inv = np.zeros_like(items[0], dtype=complex)
    for item in items:
        inv += 1.0 / item
    return 1.0 / inv


@dataclass(frozen=True)
class ParamDef:
    name: str
    label: str
    unit: str
    low: float
    high: float
    scale: str = "log"


@dataclass(frozen=True)
class CircuitSpec:
    key: str
    name: str
    expression: str
    params: tuple[ParamDef, ...]
    function: Callable[..., Array]
    diagram: tuple
    description: str
    metadata: dict | None = None


def m_r(f: Array, rs: float) -> Array:
    return z_r(f, rs)


def m_rc_series(f: Array, rs: float, c: float) -> Array:
    return z_r(f, rs) + z_c(f, c)


def m_randles_c(f: Array, rs: float, rct: float, cdl: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_c(f, cdl))


def m_randles_cpe(f: Array, rs: float, rct: float, q: float, alpha: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha))


def m_randles_cpe_w(f: Array, rs: float, rct: float, q: float, alpha: float, sigma: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_warburg(f, sigma)


def m_classical_randles_w(f: Array, rs: float, rct: float, q: float, alpha: float, sigma: float) -> Array:
    return z_r(f, rs) + parallel(z_cpe(f, q, alpha), z_r(f, rct) + z_warburg(f, sigma))


def m_randles_cpe_w_fractional(
    f: Array, rs: float, rct: float, q: float, alpha: float, aw: float, beta: float
) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_fractional_warburg(f, aw, beta)


def m_two_cpe(f: Array, rs: float, r1: float, q1: float, a1: float, r2: float, q2: float, a2: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, r1), z_cpe(f, q1, a1)) + parallel(z_r(f, r2), z_cpe(f, q2, a2))


def m_l_cpe(f: Array, rs: float, l: float, rct: float, q: float, alpha: float) -> Array:
    return z_r(f, rs) + z_l(f, l) + parallel(z_r(f, rct), z_cpe(f, q, alpha))


def m_randles_cpe_wo(f: Array, rs: float, rct: float, q: float, alpha: float, rw: float, tau_d: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_warburg_open(f, rw, tau_d)


def m_randles_cpe_ws(f: Array, rs: float, rct: float, q: float, alpha: float, rw: float, tau_d: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_warburg_short(f, rw, tau_d)


def m_two_cpe_wo(
    f: Array, rs: float, r1: float, q1: float, a1: float, r2: float, q2: float, a2: float, rw: float, tau_d: float
) -> Array:
    return (
        z_r(f, rs) + parallel(z_r(f, r1), z_cpe(f, q1, a1))
        + parallel(z_r(f, r2), z_cpe(f, q2, a2)) + z_warburg_open(f, rw, tau_d)
    )


def m_classical_randles_wo(f: Array, rs: float, rct: float, q: float, alpha: float, rw: float, tau_d: float) -> Array:
    return z_r(f, rs) + parallel(z_cpe(f, q, alpha), z_r(f, rct) + z_warburg_open(f, rw, tau_d))


def m_randles_cpe_g(f: Array, rs: float, rct: float, q: float, alpha: float, rg: float, tau_g: float) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_gerischer(f, rg, tau_g)


def m_classical_randles_g(f: Array, rs: float, rct: float, q: float, alpha: float, rg: float, tau_g: float) -> Array:
    return z_r(f, rs) + parallel(z_cpe(f, q, alpha), z_r(f, rct) + z_gerischer(f, rg, tau_g))


def m_tlm_open(f: Array, rs: float, rion: float, qtlm: float, alpha_t: float) -> Array:
    return z_r(f, rs) + z_tlm_open(f, rion, qtlm, alpha_t)


def m_randles_tlm_open(
    f: Array, rs: float, rct: float, q: float, alpha: float, rion: float, qtlm: float, alpha_t: float
) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_tlm_open(f, rion, qtlm, alpha_t)


def m_randles_tlm_short(
    f: Array, rs: float, rct: float, q: float, alpha: float, rion: float, qtlm: float, alpha_t: float
) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + z_tlm_short(f, rion, qtlm, alpha_t)


def m_adsorption_inductive(
    f: Array, rs: float, rct: float, q: float, alpha: float, rads: float, lads: float
) -> Array:
    return z_r(f, rs) + parallel(z_r(f, rct), z_cpe(f, q, alpha)) + parallel(z_r(f, rads), z_l(f, lads))


P_R = lambda n, l: ParamDef(n, l, "Ω", 1e-9, 1e12)
P_C = lambda n, l: ParamDef(n, l, "F", 1e-15, 10.0)
P_Q = lambda n, l: ParamDef(n, l, "S·s^α", 1e-15, 10.0)
P_A = lambda n, l: ParamDef(n, l, "", 0.20, 1.0, "linear")
P_W = lambda n, l: ParamDef(n, l, "Ω·s⁻¹ᐟ²", 1e-12, 1e12)
P_WF = lambda n, l: ParamDef(n, l, "Ω·s⁻ᵝ", 1e-12, 1e12)
P_B = lambda n, l: ParamDef(n, l, "", 0.25, 0.75, "linear")
P_L = lambda n, l: ParamDef(n, l, "H", 1e-12, 1e6)
P_TAU = lambda n, l: ParamDef(n, l, "s", 1e-12, 1e12)
P_QT = lambda n, l: ParamDef(n, l, "S·s^α", 1e-15, 10.0)


def E(kind: str, label: str, *params: str) -> tuple:
    """Annotated element used by the visual circuit renderer."""
    return ("element", kind, label, tuple(params))


CIRCUITS: dict[str, CircuitSpec] = {
    "R": CircuitSpec(
        "R", "Series resistance", "Rₛ", (P_R("Rs", "Rₛ"),), m_r,
        (E("R", "Rₛ", "Rs"),), "Single ohmic resistance. Useful as a baseline or diagnostic model."
    ),
    "R-C": CircuitSpec(
        "R-C", "Series R–C", "Rₛ + C", (P_R("Rs", "Rₛ"), P_C("C", "C")), m_rc_series,
        (E("R", "Rₛ", "Rs"), E("C", "C", "C")), "Series resistor and ideal capacitor."
    ),
    "R-(R||C)": CircuitSpec(
        "R-(R||C)", "Randles RC", "Rₛ + (Rct ∥ Cdl)",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_C("Cdl", "Cdl")), m_randles_c,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("C", "Cdl", "Cdl"))),
        "Classical one-time-constant Randles response."
    ),
    "R-(R||CPE)": CircuitSpec(
        "R-(R||CPE)", "Randles CPE", "Rₛ + (Rct ∥ CPE)",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α")), m_randles_cpe,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha"))),
        "One depressed semicircle using a constant-phase element."
    ),
    "R-(R||CPE)-W": CircuitSpec(
        "R-(R||CPE)-W", "CPE arc + ideal Warburg", "Rₛ + (Rct ∥ CPE) + W",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"), P_W("sigma", "σW")), m_randles_cpe_w,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("W", "W", "sigma")),
        "A depressed charge-transfer arc followed by an ideal 45° semi-infinite Warburg tail."
    ),
    "R-(CPE||(R+W))": CircuitSpec(
        "R-(CPE||(R+W))", "Classical Randles + Warburg", "Rₛ + [CPE ∥ (Rct + W)]",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"), P_W("sigma", "σW")), m_classical_randles_w,
        (E("R", "Rₛ", "Rs"), ("parallel", E("CPE", "CPE", "Q", "alpha"), ("series", E("R", "Rct", "Rct"), E("W", "W", "sigma")))),
        "Classical Randles diffusion topology, with Warburg in series with Rct inside the faradaic branch."
    ),
    "R-(R||CPE)-Wf": CircuitSpec(
        "R-(R||CPE)-Wf", "CPE arc + fractional Warburg", "Rₛ + (Rct ∥ CPE) + Wᵦ",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_WF("Aw", "Aᵂ"), P_B("beta", "βW")), m_randles_cpe_w_fractional,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("Wβ", "Wβ", "Aw", "beta")),
        "Generalized diffusion. β=0.50 is ideal Warburg; β≠0.50 indicates anomalous/distributed diffusion."
    ),
    "R-(R||CPE)-Wo": CircuitSpec(
        "R-(R||CPE)-Wo", "CPE arc + finite Warburg open", "Rₛ + (Rct ∥ CPE) + Wₒ",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rw", "Rᴡ"), P_TAU("tauD", "τD")), m_randles_cpe_wo,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("Wo", "Wₒ", "Rw", "tauD")),
        "Finite-length blocking/open diffusion. Useful when the low-frequency branch bends toward a near-vertical line."
    ),
    "R-(R||CPE)-Ws": CircuitSpec(
        "R-(R||CPE)-Ws", "CPE arc + finite Warburg short", "Rₛ + (Rct ∥ CPE) + Wₛ",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rw", "Rᴡ"), P_TAU("tauD", "τD")), m_randles_cpe_ws,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("Ws", "Wₛ", "Rw", "tauD")),
        "Finite-length transmissive/short diffusion. The low-frequency response tends toward a resistive termination."
    ),
    "R-(CPE||(R+Wo))": CircuitSpec(
        "R-(CPE||(R+Wo))", "Classical Randles + finite Warburg open", "Rₛ + [CPE ∥ (Rct + Wₒ)]",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rw", "Rᴡ"), P_TAU("tauD", "τD")), m_classical_randles_wo,
        (E("R", "Rₛ", "Rs"), ("parallel", E("CPE", "CPE", "Q", "alpha"), ("series", E("R", "Rct", "Rct"), E("Wo", "Wₒ", "Rw", "tauD")))),
        "Finite-length blocking diffusion inside the faradaic branch."
    ),
    "R-(R||CPE)-G": CircuitSpec(
        "R-(R||CPE)-G", "CPE arc + Gerischer", "Rₛ + (Rct ∥ CPE) + G",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rg", "Rᴳ"), P_TAU("tauG", "τG")), m_randles_cpe_g,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("G", "G", "Rg", "tauG")),
        "Gerischer impedance for coupled reaction–diffusion behavior."
    ),
    "R-(CPE||(R+G))": CircuitSpec(
        "R-(CPE||(R+G))", "Classical Randles + Gerischer", "Rₛ + [CPE ∥ (Rct + G)]",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rg", "Rᴳ"), P_TAU("tauG", "τG")), m_classical_randles_g,
        (E("R", "Rₛ", "Rs"), ("parallel", E("CPE", "CPE", "Q", "alpha"), ("series", E("R", "Rct", "Rct"), E("G", "G", "Rg", "tauG")))),
        "Gerischer reaction–diffusion branch placed in the faradaic path."
    ),
    "R-TLMo": CircuitSpec(
        "R-TLMo", "Porous TLM open", "Rₛ + TLMₒ",
        (P_R("Rs", "Rₛ"), P_R("Rion", "Rion"), P_QT("Qtlm", "Qtlm"), P_A("alphaT", "αT")), m_tlm_open,
        (E("R", "Rₛ", "Rs"), E("TLMo", "TLMₒ", "Rion", "Qtlm", "alphaT")),
        "Distributed porous-electrode transmission line with a blocking end."
    ),
    "R-(R||CPE)-TLMo": CircuitSpec(
        "R-(R||CPE)-TLMo", "CPE arc + porous TLM open", "Rₛ + (Rct ∥ CPE) + TLMₒ",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rion", "Rion"), P_QT("Qtlm", "Qtlm"), P_A("alphaT", "αT")), m_randles_tlm_open,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("TLMo", "TLMₒ", "Rion", "Qtlm", "alphaT")),
        "Arc plus distributed charging/ion transport through a porous or thick-film electrode."
    ),
    "R-(R||CPE)-TLMs": CircuitSpec(
        "R-(R||CPE)-TLMs", "CPE arc + porous TLM short", "Rₛ + (Rct ∥ CPE) + TLMₛ",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rion", "Rion"), P_QT("Qtlm", "Qtlm"), P_A("alphaT", "αT")), m_randles_tlm_short,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")), E("TLMs", "TLMₛ", "Rion", "Qtlm", "alphaT")),
        "Arc plus distributed porous-electrode transmission line with transmissive termination."
    ),
    "R-(R||CPE)-(R||CPE)": CircuitSpec(
        "R-(R||CPE)-(R||CPE)", "Two time constants", "Rₛ + (R₁ ∥ CPE₁) + (R₂ ∥ CPE₂)",
        (P_R("Rs", "Rₛ"), P_R("R1", "R₁"), P_Q("Q1", "Q₁"), P_A("a1", "α₁"),
         P_R("R2", "R₂"), P_Q("Q2", "Q₂"), P_A("a2", "α₂")), m_two_cpe,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "R₁", "R1"), E("CPE", "CPE₁", "Q1", "a1")),
         ("parallel", E("R", "R₂", "R2"), E("CPE", "CPE₂", "Q2", "a2"))),
        "Two distributed relaxation processes."
    ),
    "R-(R||CPE)-(R||CPE)-Wo": CircuitSpec(
        "R-(R||CPE)-(R||CPE)-Wo", "Two CPE arcs + finite Warburg open", "Rₛ + (R₁ ∥ CPE₁) + (R₂ ∥ CPE₂) + Wₒ",
        (P_R("Rs", "Rₛ"), P_R("R1", "R₁"), P_Q("Q1", "Q₁"), P_A("a1", "α₁"),
         P_R("R2", "R₂"), P_Q("Q2", "Q₂"), P_A("a2", "α₂"), P_R("Rw", "Rᴡ"), P_TAU("tauD", "τD")), m_two_cpe_wo,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "R₁", "R1"), E("CPE", "CPE₁", "Q1", "a1")),
         ("parallel", E("R", "R₂", "R2"), E("CPE", "CPE₂", "Q2", "a2")), E("Wo", "Wₒ", "Rw", "tauD")),
        "Two distributed relaxation processes followed by finite-length blocking diffusion."
    ),
    "R-L-(R||CPE)": CircuitSpec(
        "R-L-(R||CPE)", "Inductive Randles", "Rₛ + L + (Rct ∥ CPE)",
        (P_R("Rs", "Rₛ"), P_L("L", "L"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α")), m_l_cpe,
        (E("R", "Rₛ", "Rs"), E("L", "L", "L"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha"))),
        "Includes a high-frequency inductive lead contribution."
    ),
    "R-(R||CPE)-(R||Lads)": CircuitSpec(
        "R-(R||CPE)-(R||Lads)", "CPE arc + adsorption inductive loop", "Rₛ + (Rct ∥ CPE) + (Rads ∥ Lads)",
        (P_R("Rs", "Rₛ"), P_R("Rct", "Rct"), P_Q("Q", "Q"), P_A("alpha", "α"),
         P_R("Rads", "Rads"), P_L("Lads", "Lads")), m_adsorption_inductive,
        (E("R", "Rₛ", "Rs"), ("parallel", E("R", "Rct", "Rct"), E("CPE", "CPE", "Q", "alpha")),
         ("parallel", E("R", "Rads", "Rads"), E("L", "Lads", "Lads"))),
        "Optional adsorption/relaxation inductive branch. Use only when the spectrum contains a genuine inductive loop."
    ),
}


_ELEMENT_DEFAULTS = {
    "R": {"value": 100.0},
    "C": {"value": 1e-6},
    "L": {"value": 1e-6},
    "CPE": {"Q": 1e-6, "alpha": 0.90},
    "W": {"sigma": 10.0},
    "Wβ": {"Aw": 10.0, "beta": 0.50},
    "Wo": {"Rw": 100.0, "tauD": 1.0},
    "Ws": {"Rw": 100.0, "tauD": 1.0},
    "G": {"Rg": 100.0, "tauG": 1.0},
    "TLMo": {"Rion": 100.0, "Qtlm": 1e-5, "alphaT": 0.90},
    "TLMs": {"Rion": 100.0, "Qtlm": 1e-5, "alphaT": 0.90},
}


def custom_element_param_names(kind: str, element_id: str) -> list[str]:
    suffix = "".join(ch for ch in str(element_id) if ch.isdigit()) or str(element_id)
    if kind == "R":
        return [f"R{suffix}"]
    if kind == "C":
        return [f"C{suffix}"]
    if kind == "L":
        return [f"L{suffix}"]
    if kind == "CPE":
        return [f"Q{suffix}", f"alpha{suffix}"]
    if kind == "W":
        return [f"sigma{suffix}"]
    if kind == "Wβ":
        return [f"Aw{suffix}", f"beta{suffix}"]
    if kind in {"Wo", "Ws"}:
        return [f"Rw{suffix}", f"tauD{suffix}"]
    if kind == "G":
        return [f"Rg{suffix}", f"tauG{suffix}"]
    if kind in {"TLMo", "TLMs"}:
        return [f"Rion{suffix}", f"Qtlm{suffix}", f"alphaT{suffix}"]
    raise ValueError(f"Unsupported circuit element: {kind}")



def _element_param_names(element: dict) -> list[str]:
    explicit = element.get("params")
    if explicit:
        return [str(name) for name in explicit]
    return custom_element_param_names(element["kind"], element["id"])

def custom_param_def(kind: str, name: str, element_label: str) -> ParamDef:
    if kind == "R":
        return P_R(name, element_label)
    if kind == "C":
        return P_C(name, element_label)
    if kind == "L":
        return P_L(name, element_label)
    if kind == "W":
        return P_W(name, element_label)
    if kind == "Wβ":
        return P_WF(name, "Aᵂ") if name.startswith("Aw") else P_B(name, "βW")
    if kind in {"Wo", "Ws"}:
        return P_R(name, "Rᴡ") if name.startswith("Rw") else P_TAU(name, "τD")
    if kind == "G":
        return P_R(name, "Rᴳ") if name.startswith("Rg") else P_TAU(name, "τG")
    if kind in {"TLMo", "TLMs"}:
        if name.startswith("Rion"):
            return P_R(name, "Rion")
        if name.startswith("Qtlm"):
            return P_QT(name, "Qtlm")
        return P_A(name, "αT")
    if kind == "CPE":
        return P_Q(name, "Q") if name.startswith("Q") else P_A(name, "α")
    raise ValueError(f"Unsupported circuit element: {kind}")


def _walk_custom_elements(tree: dict):
    for child in tree.get("children", []):
        if child.get("type") == "element":
            yield child
        elif child.get("type") == "parallel":
            for branch in child.get("branches", []):
                yield from _walk_custom_elements(branch)


def custom_tree_params(tree: dict) -> tuple[ParamDef, ...]:
    params: list[ParamDef] = []
    for element in _walk_custom_elements(tree):
        kind = element["kind"]
        element_id = element["id"]
        names = _element_param_names(element)
        for name in names:
            params.append(custom_param_def(kind, name, element_id))
    if len({p.name for p in params}) != len(params):
        raise ValueError("Each element must have a unique identifier.")
    return tuple(params)


def _custom_element_impedance(kind: str, f: Array, names: list[str], values: dict[str, float]) -> Array:
    if kind == "R":
        return z_r(f, values[names[0]])
    if kind == "C":
        return z_c(f, values[names[0]])
    if kind == "L":
        return z_l(f, values[names[0]])
    if kind == "CPE":
        return z_cpe(f, values[names[0]], values[names[1]])
    if kind == "W":
        return z_warburg(f, values[names[0]])
    if kind == "Wβ":
        return z_fractional_warburg(f, values[names[0]], values[names[1]])
    if kind == "Wo":
        return z_warburg_open(f, values[names[0]], values[names[1]])
    if kind == "Ws":
        return z_warburg_short(f, values[names[0]], values[names[1]])
    if kind == "G":
        return z_gerischer(f, values[names[0]], values[names[1]])
    if kind == "TLMo":
        return z_tlm_open(f, values[names[0]], values[names[1]], values[names[2]])
    if kind == "TLMs":
        return z_tlm_short(f, values[names[0]], values[names[1]], values[names[2]])
    raise ValueError(f"Unsupported circuit element: {kind}")


def evaluate_custom_tree(tree: dict, f: Array, values: dict[str, float]) -> Array:
    f = np.asarray(f, dtype=float)

    def eval_series(container: dict) -> Array:
        result = np.zeros_like(f, dtype=complex)
        for child in container.get("children", []):
            if child.get("type") == "element":
                names = _element_param_names(child)
                result = result + _custom_element_impedance(child["kind"], f, names, values)
            elif child.get("type") == "parallel":
                branch_values = [eval_series(branch) for branch in child.get("branches", [])]
                if len(branch_values) < 2:
                    raise ValueError("A parallel block requires at least two branches.")
                result = result + parallel(*branch_values)
            else:
                raise ValueError("Invalid item in custom circuit.")
        return result

    return eval_series(tree)


def custom_tree_to_diagram(tree: dict) -> tuple:
    def series_items(container: dict) -> tuple:
        output = []
        for child in container.get("children", []):
            if child.get("type") == "element":
                names = tuple(_element_param_names(child))
                output.append(E(child["kind"], child["id"], *names))
            elif child.get("type") == "parallel":
                branches = []
                for branch in child.get("branches", []):
                    items = series_items(branch)
                    branches.append(items[0] if len(items) == 1 else ("series", *items))
                output.append(("parallel", *branches))
        return tuple(output)

    return series_items(tree)


def custom_tree_expression(tree: dict) -> str:
    def series_text(container: dict) -> str:
        chunks = []
        for child in container.get("children", []):
            if child.get("type") == "element":
                chunks.append(child["id"])
            elif child.get("type") == "parallel":
                branches = [series_text(branch) for branch in child.get("branches", [])]
                chunks.append("(" + " ∥ ".join(branches) + ")")
        return " + ".join(chunks) or "empty"

    return series_text(tree)



def validate_custom_tree(tree: dict) -> None:
    """Validate the supported visual-builder topology.

    The builder supports a series root containing elements and parallel blocks;
    each parallel branch is a non-empty series path.
    """
    if not isinstance(tree, dict) or tree.get("type") != "series":
        raise ValueError("A custom circuit must have a series root.")

    def check_series(container: dict, location: str):
        children = container.get("children", [])
        if not children:
            raise ValueError(f"{location} is empty. Add at least one electrical element.")
        for child in children:
            child_type = child.get("type")
            if child_type == "element":
                if child.get("kind") not in {"R", "C", "CPE", "L", "W", "Wβ", "Wo", "Ws", "G", "TLMo", "TLMs"}:
                    raise ValueError(f"Unsupported element in {location}: {child.get('kind')}")
            elif child_type == "parallel":
                branches = child.get("branches", [])
                if len(branches) < 2:
                    raise ValueError("A parallel block requires at least two branches.")
                for index, branch in enumerate(branches, 1):
                    check_series(branch, f"Parallel branch {index}")
            else:
                raise ValueError(f"Invalid circuit item in {location}.")

    check_series(tree, "The main series circuit")

def make_custom_circuit(tree: dict, name: str = "Manual visual circuit", key: str = "CUSTOM") -> CircuitSpec:
    tree_copy = deepcopy(tree)
    validate_custom_tree(tree_copy)
    params = custom_tree_params(tree_copy)
    if not params:
        raise ValueError("Add at least one electrical element to the custom circuit.")

    def function(f: Array, *args: float) -> Array:
        values = {p.name: float(value) for p, value in zip(params, args)}
        return evaluate_custom_tree(tree_copy, f, values)

    expression = custom_tree_expression(tree_copy)
    return CircuitSpec(
        key=key,
        name=name,
        expression=expression,
        params=params,
        function=function,
        diagram=custom_tree_to_diagram(tree_copy),
        description="User-built series/parallel circuit created in the visual circuit builder.",
        metadata={"custom": True, "tree": tree_copy},
    )


def default_custom_values(tree: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for element in _walk_custom_elements(tree):
        kind = element["kind"]
        names = _element_param_names(element)
        defaults = _ELEMENT_DEFAULTS[kind]
        if kind in {"R", "C", "L"}:
            values[names[0]] = defaults["value"]
        elif kind == "CPE":
            values[names[0]] = defaults["Q"]
            values[names[1]] = defaults["alpha"]
        elif kind == "W":
            values[names[0]] = defaults["sigma"]
        elif kind == "Wβ":
            values[names[0]] = defaults["Aw"]
            values[names[1]] = defaults["beta"]
        elif kind in {"Wo", "Ws"}:
            values[names[0]] = defaults["Rw"]
            values[names[1]] = defaults["tauD"]
        elif kind == "G":
            values[names[0]] = defaults["Rg"]
            values[names[1]] = defaults["tauG"]
        elif kind in {"TLMo", "TLMs"}:
            values[names[0]] = defaults["Rion"]
            values[names[1]] = defaults["Qtlm"]
            values[names[2]] = defaults["alphaT"]
    return values


def evaluate(key: str, f: Array, values: dict[str, float] | list[float] | tuple[float, ...]) -> Array:
    spec = CIRCUITS[key]
    if isinstance(values, dict):
        args = [values[p.name] for p in spec.params]
    else:
        args = list(values)
    return spec.function(np.asarray(f, dtype=float), *args)
