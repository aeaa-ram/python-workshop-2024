"""Independent reference: an open-source implementation as a second opinion.

Consensus between project files shows what engineers do; it does not prove it
is right.  Where an open-source library implements the same clause, the
unified logic is evaluated through its chain of objects from the primary
inputs and compared with the library over the whole parameter range.

The library used is ``structuralcodes`` (fib International, Apache-2.0).  An
adapter states which library function corresponds to an object and how its
arguments map.  No adapter, or no library installed: the object simply has
no reference.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .. import expr as X

SAMPLES = 200


@dataclass
class Adapter:
    function: str                           # shown to the engineer
    primaries: list                         # quantities sampled
    call: object                            # (p) -> reference value in canonical units
    fixed: dict = field(default_factory=dict)       # chain parameters set from the primaries
    ranges: dict = field(default_factory=dict)      # canonical ranges overriding the taxonomy
    constrain: object = None                # (p) -> p, to keep a sample physically meaningful
    neutral: dict = field(default_factory=dict)     # value of a primary the distilled logic does not have
    note: str = ""


def _adapters() -> dict:
    from structuralcodes.codes import ec2_2004 as ec
    from structuralcodes.codes.ec2_2004 import shear as sh

    def hc(p):
        p["d"] = p["h"] * (0.70 + 0.25 * p["_u1"])
        p["x_el"] = p["h"] * (0.10 + 0.50 * p["_u2"])
        return p

    def bond(p):                   # the library accepts the tabulated values only
        p["k_1_bond"] = 0.8 if p["_u1"] < 0.5 else 1.6
        return p

    def duration(p):
        p["k_t"] = 0.4 if p["_u1"] < 0.5 else 0.6
        return p

    return {
        "k": Adapter("shear._k(d)", ["d"], lambda p: sh._k(p["d"])),
        "rho_l": Adapter("shear._rho_L(Asl, bw, d)", ["A_sl", "b_w", "d"],
                         lambda p: sh._rho_L(p["A_sl"], p["b_w"], p["d"])),
        "v_min": Adapter("shear.vmin(fck, d)", ["f_ck", "d"], lambda p: sh.vmin(p["f_ck"], p["d"])),
        "nu": Adapter("shear.v(fck)", ["f_ck"], lambda p: sh.v(p["f_ck"])),
        "V_Rd_c_min": Adapter(
            "(shear.vmin(fck, d) + k1·σcp)·bw·d", ["f_ck", "d", "b_w", "k_1", "sigma_cp"],
            lambda p: (sh.vmin(p["f_ck"], p["d"]) + p["k_1"] * p["sigma_cp"]) * p["b_w"] * p["d"],
            ranges={"sigma_cp": (-1.0, 4.0)}),
        "V_Rd_c": Adapter(
            "VRdc(fck, d, Asl, bw, NEd, Ac, fcd, k1, gamma_c)",
            ["f_ck", "d", "A_sl", "b_w", "sigma_cp", "k_1", "gamma_C"],
            lambda p: ec.VRdc(p["f_ck"], p["d"], p["A_sl"], p["b_w"], NEd=p["sigma_cp"] * 1e6, Ac=1e6,
                              fcd=1e9, k1=p["k_1"], gamma_c=p["gamma_C"]),
            ranges={"sigma_cp": (-1.0, 4.0)},
            note="σ_cp passed as N_Ed/A_c; the library's cap σ_cp ≤ 0.2 f_cd is switched off for the comparison"),
        "f_cd": Adapter("fcd(fck, alpha_cc, gamma_c)", ["f_ck", "gamma_C", "alpha_cc"],
                        lambda p: ec.fcd(p["f_ck"], p["alpha_cc"], p["gamma_C"]),
                        neutral={"alpha_cc": 1.0}),
        "V_Rd_s": Adapter(
            "VRds(Asw, s, z, theta, fyk, alpha=90, gamma_s)", ["A_sw", "s", "z_V", "theta", "f_ywk", "gamma_S"],
            lambda p: ec.VRds(p["A_sw"], p["s"], p["z_V"], math.degrees(p["theta"]), p["f_ywk"], 90.0, p["gamma_S"]),
            ranges={"theta": (math.radians(22.0), math.radians(45.0))}),
        "V_Rd_max": Adapter(
            "VRdmax(bw, z, fck, theta, NEd=0, Ac, fcd)", ["b_w", "z_V", "f_ck", "theta", "gamma_C"],
            lambda p: ec.VRdmax(p["b_w"], p["z_V"], p["f_ck"], math.degrees(p["theta"]), 0.0, 1.0,
                                p["f_ck"] / p["gamma_C"]),
            fixed={"alpha_cw": lambda p: 1.0, "nu_1": lambda p: sh.v(p["f_ck"]),
                   "f_cd": lambda p: p["f_ck"] / p["gamma_C"]},
            ranges={"theta": (math.radians(22.0), math.radians(45.0))},
            note="compared for σ_cp = 0 (α_cw = 1), vertical links, ν_1 = 0.6(1 − f_ck/250) and α_cc = 1"),
        "V_Ed_max": Adapter("VEdmax_unreinf(bw, d, fck, fcd)", ["b_w", "d", "f_ck", "gamma_C", "alpha_cc"],
                            lambda p: ec.VEdmax_unreinf(p["b_w"], p["d"], p["f_ck"],
                                                        p["alpha_cc"] * p["f_ck"] / p["gamma_C"])),
        "f_yd": Adapter("fyd(fyk, gamma_s)", ["f_yk", "gamma_S"], lambda p: ec.fyd(p["f_yk"], p["gamma_S"])),
        "f_ctm": Adapter("fctm(fck)", ["f_ck"], lambda p: ec.fctm(p["f_ck"])),
        "f_cm": Adapter("fcm(fck)", ["f_ck"], lambda p: ec.fcm(p["f_ck"])),
        "E_cm": Adapter("Ecm(fcm(fck))", ["f_ck"], lambda p: ec.Ecm(ec.fcm(p["f_ck"]))),
        "alpha_cw": Adapter("shear.alpha_cw(NEd, Ac, fcd)", ["sigma_cp", "f_cd"],
                            lambda p: sh.alpha_cw(p["sigma_cp"] * 1e6, 1e6, p["f_cd"]),
                            ranges={"sigma_cp": (-2.0, 7.0), "f_cd": (8.0, 60.0)}),
        "h_c_ef": Adapter("hc_eff(h, d, x)", ["h", "d", "x_el"], lambda p: ec.hc_eff(p["h"], p["d"], p["x_el"]),
                          constrain=hc),
        "rho_p_eff": Adapter("rho_p_eff(As, xi1=0, Ap=0, Ac_eff)", ["A_s", "A_c_eff"],
                             lambda p: ec.rho_p_eff(p["A_s"], 0.0, 0.0, p["A_c_eff"])),
        "s_r_max": Adapter("sr_max_close(c, phi, rho_p_eff, k1, k2, k3, k4)",
                           ["c", "phi_bar", "rho_p_eff", "k_1_bond", "k_2", "k_3", "k_4"],
                           lambda p: ec.sr_max_close(p["c"], p["phi_bar"], p["rho_p_eff"], p["k_1_bond"],
                                                     p["k_2"], p["k_3"], p["k_4"]),
                           constrain=bond),
        "eps_sm_cm": Adapter("eps_sm_eps_cm(sigma_s, alpha_e, rho_p_eff, kt, fct_eff, Es)",
                             ["sigma_s", "alpha_e", "rho_p_eff", "k_t", "f_ct_eff", "E_s"],
                             lambda p: ec.eps_sm_eps_cm(p["sigma_s"], p["alpha_e"], p["rho_p_eff"], p["k_t"],
                                                        p["f_ct_eff"], p["E_s"]),
                             constrain=duration),
        "w_k": Adapter("wk(sr_max, eps_sm_eps_cm)", ["s_r_max", "eps_sm_cm"],
                       lambda p: ec.wk(p["s_r_max"], p["eps_sm_cm"])),
        "alpha_e": Adapter("alpha_e(Es, Ecm)", ["E_s", "E_cm"], lambda p: ec.alpha_e(p["E_s"], p["E_cm"])),
    }


def library() -> tuple[str, dict]:
    try:
        import structuralcodes
        return f"structuralcodes {structuralcodes.__version__}", _adapters()
    except Exception:                                            # noqa: BLE001 - optional dependency
        return "", {}


def _chain(cid: str, env: dict, formulas: dict, depth: int = 0):
    if depth > 12:
        raise X.ExprError("dependency too deep")
    for q in X.symbols(formulas[cid]):
        if q not in env:
            if q not in formulas:
                raise X.ExprError(f"no value for {q}")
            env[q] = _chain(q, env, formulas, depth + 1)
    return X.evaluate(formulas[cid], env)


def check(cid: str, formulas: dict, tax, seed: int = 11) -> dict:
    """Compare one object with the reference library.  Returns {} if there is none."""
    name, adapters = library()
    ad = adapters.get(cid)
    if not ad or cid not in formulas:
        return {}
    rng = random.Random(seed)
    worst, n_ok, n_fail, example = 0.0, 0, 0, None
    used: set[str] = set()

    def closure(c: str):
        for q in X.symbols(formulas[c]):
            if q not in used:
                used.add(q)
                if q in formulas and q not in ad.fixed:
                    closure(q)

    closure(cid)
    held = {q: v for q, v in ad.neutral.items() if q not in used}
    for _ in range(SAMPLES):
        p = {"_u1": rng.random(), "_u2": rng.random()}
        for q in ad.primaries:
            lo, hi = ad.ranges.get(q) or (tax.concepts[q].canonical_range if q in tax.concepts and
                                          tax.concepts[q].canonical_range else (0.5, 2.0))
            p[q] = held[q] if q in held else rng.uniform(lo, hi)
        if ad.constrain:
            p = ad.constrain(p)
        env = {k: v for k, v in p.items() if not k.startswith("_")}
        for k, fn in ad.fixed.items():
            env[k] = fn(p)
        try:
            ref = ad.call(p)
            ours = _chain(cid, dict(env), formulas)
        except (X.ExprError, ValueError, ZeroDivisionError):
            continue
        if isinstance(ours, str) or isinstance(ref, str):
            continue
        diff = abs(ours - ref) / max(abs(ref), 1e-12)
        if diff <= 1e-9:
            n_ok += 1
        else:
            n_fail += 1
            if example is None or diff > worst:
                example = {"inputs": {k: float(f"{v:.6g}") for k, v in env.items()},
                           "ours": ours, "reference": ref}
        worst = max(worst, diff)
    total = n_ok + n_fail
    if total == 0:
        return {}
    out = {"library": name, "function": ad.function, "samples": total,
           "max_relative_difference": float(f"{worst:.3g}"),
           "status": "agrees" if n_fail == 0 else "differs", "agreeing_samples": n_ok}
    notes = [ad.note] if ad.note else []
    for q, v in held.items():
        notes.append(f"the distilled formula has no {tax.concepts[q].text}; the reference was evaluated with {tax.concepts[q].text} = {v:g}")
    if notes:
        out["note"] = "; ".join(notes)
    if example and n_fail:
        out["example"] = example
    return out
