"""Variable naming convention + symbol -> LaTeX rendering.

Convention (chosen so every name stays a valid Python/sympy identifier,
so the calculation logic never breaks):

    base_sub                first '_' separates base from subscript
    base_sub__sub2          '__' (double underscore) = comma in subscript
    base_sub_sub2           a further single '_' also reads as a comma
    greekname               spelled-out greek -> the greek letter

Examples:
    E_cm        -> E_{cm}
    f_c__k      -> f_{c,k}
    sigma_Rd__max -> \\sigma_{Rd,max}
    epsilon_sm  -> \\varepsilon_{sm}
    k_1         -> k_{1}

Synonyms: some symbols mean the same physical quantity written different
ways (E_c / E_cm / Ec = concrete modulus). ``canonical_concept`` maps
them to one concept id so the QA layer can flag "you used two names for
the same thing — merge them".
"""

from __future__ import annotations

import re

_GREEK = {
    "alpha": r"\alpha", "beta": r"\beta", "gamma": r"\gamma",
    "delta": r"\delta", "Delta": r"\Delta", "epsilon": r"\varepsilon",
    "eps": r"\varepsilon", "zeta": r"\zeta", "eta": r"\eta",
    "theta": r"\theta", "Theta": r"\Theta", "iota": r"\iota",
    "kappa": r"\kappa", "lambda": r"\lambda", "Lambda": r"\Lambda",
    "mu": r"\mu", "nu": r"\nu", "xi": r"\xi", "Xi": r"\Xi",
    "pi": r"\pi", "Pi": r"\Pi", "rho": r"\rho", "sigma": r"\sigma",
    "Sigma": r"\Sigma", "tau": r"\tau", "upsilon": r"\upsilon",
    "phi": r"\phi", "Phi": r"\Phi", "varphi": r"\varphi",
    "chi": r"\chi", "psi": r"\psi", "Psi": r"\Psi",
    "omega": r"\omega", "Omega": r"\Omega",
}


def _greek(token: str) -> str:
    return _GREEK.get(token, token)


def symbol_to_latex(name: str) -> str:
    """Render an engineering variable name to LaTeX per the convention."""
    if not name:
        return ""
    # normalize: all underscores after the first become part of subscript
    if "_" in name:
        base, rest = name.split("_", 1)
    else:
        base, rest = name, ""
    base_tex = _greek(base)
    if len(base_tex) == 1 and base_tex.isalpha():
        base_tex = base_tex  # single latin letter, leave as-is
    if not rest:
        return base_tex
    # subscript groups: any run of underscores separates comma parts
    parts = [p for p in re.split(r"_+", rest) if p != ""]
    sub = ",".join(_greek(p) for p in parts)
    return f"{base_tex}_{{{sub}}}"


# ------------------------------------------------------------------ #
# Synonyms — "these names mean the same quantity"
# ------------------------------------------------------------------ #
# concept id -> set of interchangeable symbol names
SYNONYM_GROUPS: dict[str, set[str]] = {
    "concrete_elastic_modulus": {"E_c", "E_cm", "Ec", "Ecm", "E_concrete"},
    "steel_elastic_modulus": {"E_s", "Es", "E_steel"},
    "concrete_char_strength": {"f_ck", "f_c__k", "fck", "f_ck_cyl"},
    "concrete_mean_strength": {"f_cm", "fcm", "f_c__m"},
    "steel_yield_strength": {"f_yk", "fyk", "f_y__k", "f_y"},
    "bar_diameter": {"phi", "dia", "d_bar", "phi_bar"},
    "bending_moment": {"M", "M_Ed", "M_ed", "MEd"},
    "effective_depth": {"d", "d_eff"},
}

_NAME_TO_CONCEPT = {
    name: concept for concept, names in SYNONYM_GROUPS.items()
    for name in names
}


def canonical_concept(name: str) -> str | None:
    """Return the shared concept id for a symbol, or None if unknown."""
    return _NAME_TO_CONCEPT.get(name)


def find_synonym_clashes(names: list[str]) -> list[tuple[str, list[str]]]:
    """Group the given names by concept where >1 name shares a concept.

    Returns ``[(concept, [names...]), ...]`` — each entry is a set of
    variables that mean the same thing and should be merged.
    """
    by_concept: dict[str, list[str]] = {}
    for name in names:
        concept = canonical_concept(name)
        if concept:
            by_concept.setdefault(concept, []).append(name)
    return [
        (concept, sorted(set(ns)))
        for concept, ns in by_concept.items()
        if len(set(ns)) > 1
    ]
