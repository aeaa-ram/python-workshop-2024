"""Notation: turning the many ways engineers write a symbol into one.

``VRd.c``, ``V_Rd,c``, ``V_Rd.c`` and ``VRdc`` are the same quantity.  This
module reduces a name to a comparison key, splits a spreadsheet label such as
``VRd.c (kN/m)`` into symbol, unit and description, and renders a symbol the
way it is printed in a calculation (subscripts, Greek letters).
"""
from __future__ import annotations

import re
import unicodedata

from .units import is_unit, parse_unit

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "eps", "ϵ": "eps",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ϑ": "theta", "κ": "kappa", "λ": "lambda",
    "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau",
    "φ": "phi", "ϕ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
    "Δ": "Delta", "Σ": "Sigma", "Φ": "Phi", "Ω": "Omega", "Ψ": "Psi", "Θ": "Theta",
    "Λ": "Lambda", "Γ": "Gamma", "∅": "phi", "Ø": "phi", "ø": "phi",
}
_GREEK_NAMES = {v: k for k, v in GREEK.items() if k not in ("ϵ", "ϑ", "ϕ", "∅", "Ø", "ø")}
_GREEK_NAMES.update({"epsilon": "ε", "eps": "ε", "phi": "φ", "theta": "θ", "varphi": "φ"})
_GREEK_WORDS = sorted(set(_GREEK_NAMES) | {"epsilon"}, key=len, reverse=True)
_SUBDIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _latin(text: str) -> str:
    out = []
    for ch in text.translate(_SUBDIGITS):
        out.append(GREEK.get(ch, ch))
    return "".join(out)


def symkey(raw: str) -> str:
    """Comparison key of a symbol: separators removed, Greek spelled out.

    Case is kept: ``V`` (force) and ``v`` (stress) are different quantities.
    """
    s = _latin(unicodedata.normalize("NFKC", raw or ""))
    s = s.replace("epsilon", "eps")
    s = re.sub(r"[\s_.,;:{}\\'’`\-−]+", "", s)
    return s


def ident(raw: str) -> str:
    """A Python identifier for a raw source name: ``V_Rd.c`` -> ``V_Rd_c``."""
    s = _latin(unicodedata.normalize("NFKC", raw or "")).strip()
    s = re.sub(r"[.,;:\s\-−/]+", "_", s)
    s = re.sub(r"[^0-9A-Za-z_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "x"
    if s[0].isdigit():
        s = "x" + s
    return s


_UNIT_PAREN = re.compile(r"[\(\[]\s*([^()\[\]]{1,14})\s*[\)\]]")


def split_label(text: str) -> tuple[str, str, str]:
    """Split a label into (symbol text, unit, description).

    ``"VRd.c (kN/m)"`` -> ``("VRd.c", "kN/m", "")``;
    ``"VEd (kN) - crane only"`` -> ``("VEd", "kN", "crane only")``;
    ``"perimeter u (m)"`` -> ``("perimeter u", "m", "")``.
    """
    s = " ".join((text or "").replace("\n", " ").split())
    unit = ""
    for m in reversed(list(_UNIT_PAREN.finditer(s))):
        cand = m.group(1).strip()
        if is_unit(cand) and not re.fullmatch(r"\d+", cand):
            unit = parse_unit(cand).text
            s = (s[:m.start()] + " " + s[m.end():]).strip()
            break
    desc = ""
    m = re.match(r"^(.*?)\s+[-–—]\s+(.*)$", s)
    if m:
        s, desc = m.group(1).strip(), m.group(2).strip()
    s = s.rstrip(":=").strip()
    # "fcd (αcc = 1)", "Asl(tensile)": a symbol followed by a remark in brackets
    m = re.match(r"^(\S{1,12}?)\s*\(([^()]*)\)$", s)
    if m and looks_like_symbol(m.group(1)):
        s, desc = m.group(1), (m.group(2) + (" " + desc if desc else "")).strip()
    return s, unit, desc


def looks_like_symbol(text: str) -> bool:
    """True for ``d``, ``VRd.c``, ``σcp``, ``k1`` - not for ``Utilization``."""
    s = (text or "").strip()
    if not s or len(s) > 14 or " " in s.strip():
        return False
    if any(ch in GREEK for ch in s):
        return True
    if re.search(r"[0-9_.,]", s) and re.match(r"^[A-Za-z]", s):
        return True
    if len(s) <= 3:
        return True
    # camel-style symbols such as VRd, NEd, fck, Asl, bw
    return bool(re.fullmatch(r"[A-Za-z]{1,2}[a-z]{0,2}[A-Z]?[a-z]{0,3}", s)) and len(s) <= 5


# --------------------------------------------------------------------------
# display
# --------------------------------------------------------------------------
def parts(name: str) -> tuple[str, str]:
    """(base, subscript) of a canonical name or of a raw source name."""
    s = unicodedata.normalize("NFKC", name or "").translate(_SUBDIGITS)
    if "_" in s:
        base, _, sub = s.partition("_")
        sub = sub.replace("_", ",").replace(".", ",")
    elif looks_like_symbol(s) and len(s) > 1 and s[0].isalpha() and not s[1:].startswith("."):
        # a compact source name: VRd.c -> V_Rd,c ; σcp -> σ_cp ; fck -> f_ck
        base, sub = s[0], s[1:].replace(".", ",").replace(" ", ",")
    else:
        base, sub = s, ""
    for word in _GREEK_WORDS:                       # Deltaepsilon -> Δε
        if word in base and not base.isupper():
            base = re.sub(word, _GREEK_NAMES.get(word, word), base)
    sub = ",".join(_GREEK_NAMES.get(p, p) for p in sub.split(","))
    return base, sub


def pretty(name: str, display: str = "") -> str:
    """Plain-text rendering: ``V_Rd,c``."""
    if display:
        return display.replace("{", "").replace("}", "")
    base, sub = parts(name)
    return f"{base}_{sub}" if sub else base


def mathml(name: str, display: str = "") -> str:
    """MathML rendering with an upright subscript."""
    if display:
        m = re.fullmatch(r"([^_]+)(?:_\{?([^}]*)\}?)?", display)
        base, sub = (m.group(1), m.group(2) or "") if m else (display, "")
    else:
        base, sub = parts(name)
    base_ml = f"<mi>{_esc(base)}</mi>"
    if not sub:
        return base_ml
    return f'<msub>{base_ml}<mi mathvariant="normal">{_esc(sub)}</mi></msub>'


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------
# cases: a heading that names one of several parallel calculations
# --------------------------------------------------------------------------
CASE_WORDS = ("load case", "lc", "case", "phase", "stage", "step", "situation", "scenario", "combination",
              "span", "support", "member", "zone", "option", "alternative")
_CASE = re.compile(r"\b(" + "|".join(w.replace(" ", r"\s*") for w in CASE_WORDS) + r")\s*[-:#]?\s*"
                   r"(\d+[a-z]?|[A-Z])(?![.\w])", re.I)


def case_of(heading: str) -> str:
    """``"Phase 2 - temporary works"`` -> ``"phase 2"``; ``"Load case 3"`` -> ``"load case 3"``; else ``""``."""
    m = _CASE.search(heading or "")
    if not m:
        return ""
    word = " ".join(m.group(1).lower().split())
    return f"{word} {m.group(2)}"


def is_case_label(text: str) -> bool:
    """A case name that says nothing about the project (safe to keep in an anonymous knowledge base)."""
    return bool(text) and case_of(text).lower() == text.lower().strip()
