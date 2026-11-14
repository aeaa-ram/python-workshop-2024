"""Units.

Inside the knowledge base every number is in one consistent set of units:
N, mm, MPa (= N/mm2), radians, seconds.  A formula written in those units
needs no conversion factors at all, which is why two sources that hide
their factors differently (``... * 1000 * d / 1000`` in a spreadsheet,
``200 mm / d`` in Mathcad) end up as the same formula.

Units are only attached at the boundary: when a source is read, and when a
result is shown to an engineer.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# dimension exponents: (force, length, time, temperature)
Dims = tuple[int, int, int, int]
NONE: Dims = (0, 0, 0, 0)

_BASE: dict[str, tuple[float, Dims]] = {
    # force
    "N": (1.0, (1, 0, 0, 0)), "kN": (1e3, (1, 0, 0, 0)), "MN": (1e6, (1, 0, 0, 0)),
    # length
    "mm": (1.0, (0, 1, 0, 0)), "cm": (10.0, (0, 1, 0, 0)), "dm": (100.0, (0, 1, 0, 0)),
    "m": (1e3, (0, 1, 0, 0)), "km": (1e6, (0, 1, 0, 0)), "μm": (1e-3, (0, 1, 0, 0)),
    # stress
    "Pa": (1e-6, (1, -2, 0, 0)), "kPa": (1e-3, (1, -2, 0, 0)),
    "MPa": (1.0, (1, -2, 0, 0)), "GPa": (1e3, (1, -2, 0, 0)),
    # time
    "s": (1.0, (0, 0, 1, 0)), "min": (60.0, (0, 0, 1, 0)), "h": (3600.0, (0, 0, 1, 0)),
    "day": (86400.0, (0, 0, 1, 0)), "year": (31557600.0, (0, 0, 1, 0)),
    # mass (kg = N s2/m)
    "g": (1e-6, (1, -1, 2, 0)), "kg": (1e-3, (1, -1, 2, 0)), "t": (1.0, (1, -1, 2, 0)),
    # temperature
    "K": (1.0, (0, 0, 0, 1)), "°C": (1.0, (0, 0, 0, 1)),
    # dimensionless
    "rad": (1.0, NONE), "°": (math.pi / 180, NONE), "%": (0.01, NONE), "‰": (0.001, NONE),
    "-": (1.0, NONE),
}

_ALIASES = {
    "deg": "°", "degree": "°", "degrees": "°", "radian": "rad", "radians": "rad",
    "newton": "N", "kilonewton": "kN", "meganewton": "MN",
    "millimeter": "mm", "millimetre": "mm", "centimeter": "cm", "meter": "m", "metre": "m",
    "pascal": "Pa", "kilopascal": "kPa", "megapascal": "MPa", "gigapascal": "GPa",
    "second": "s", "sec": "s", "minute": "min", "hour": "h", "hr": "h",
    "days": "day", "yr": "year", "kilogram": "kg", "tonne": "t", "ton": "t",
    "kelvin": "K", "degC": "°C", "um": "μm", "micron": "μm", "percent": "%", "permille": "‰",
    "dimensionless": "-", "": "-", "–": "-", "—": "-",
}
# compound spellings written without a separator
_COMPOUND = {"kNm": "kN·m", "Nmm": "N·mm", "Nm": "N·m", "MNm": "MN·m", "kNmm": "kN·mm",
             "kNcm": "kN·cm"}
_LOWER = {k.lower(): k for k in list(_BASE) + list(_ALIASES) + list(_COMPOUND)
          if k not in ("MN", "Pa")}
_LOWER.update({"mpa": "MPa", "gpa": "GPa", "kpa": "kPa", "kn": "kN", "knm": "kNm", "mn": "MN"})


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class UnitInfo:
    text: str        # tidy display text, e.g. "kN/m"
    factor: float    # multiply a value in this unit by `factor` to get canonical units
    dims: Dims


def _atom(tok: str) -> tuple[float, Dims, str]:
    tok = tok.strip()
    tok = _ALIASES.get(tok, tok)
    if tok in _COMPOUND:
        info = parse_unit(_COMPOUND[tok])
        return info.factor, info.dims, tok
    if tok in _BASE:
        f, d = _BASE[tok]
        return f, d, tok
    low = _LOWER.get(tok.lower()) if len(tok) > 1 else None     # "k" is not kelvin
    if low and low != tok:
        return _atom(low)
    raise UnitError(f"unknown unit {tok!r}")


def parse_unit(text: str) -> UnitInfo:
    """Parse unit text as engineers write it: ``kN/m``, ``mm2/m``, ``Mpa``, ``kNm``."""
    raw = (text or "").strip()
    s = raw.replace("²", "^2").replace("³", "^3").replace("⁴", "^4").replace("**", "^")
    s = s.replace("⋅", "·").replace("*", "·").replace("×", "·").strip("[]() ")
    if s in ("", "-", "–", "—"):
        return UnitInfo("-", 1.0, NONE)
    factor, dims, shown = 1.0, [0, 0, 0, 0], []
    for i, part in enumerate(s.split("/")):
        sign = 1 if i == 0 else -1
        for tok in re.split(r"[·\s.]+", part.strip()):
            if not tok:
                continue
            if tok == "1":
                continue
            m = re.fullmatch(r"(.+?)\^?(-?\d+)?", tok)
            name, power = m.group(1), int(m.group(2) or 1)
            if m.group(2) and name not in _BASE and name.lower() not in _LOWER and name not in _ALIASES:
                raise UnitError(f"unknown unit {tok!r}")
            f, d, disp = _atom(name)
            p = sign * power
            factor *= f ** p
            for k in range(4):
                dims[k] += d[k] * p
            sup = {1: "", 2: "²", 3: "³", 4: "⁴"}.get(power, f"^{power}")
            shown.append((sign, f"{disp}{sup}"))
    top = "·".join(t for sg, t in shown if sg > 0) or "1"
    bot = "/".join(t for sg, t in shown if sg < 0)
    tidy = (top + ("/" + bot if bot else "")).replace("kN·m", "kNm").replace("N·mm", "Nmm")
    return UnitInfo(tidy, factor, tuple(dims))


def is_unit(text: str) -> bool:
    try:
        parse_unit(text)
        return bool((text or "").strip())
    except UnitError:
        return False


def to_canonical(value: float, unit: str) -> float:
    return value * parse_unit(unit).factor


def from_canonical(value: float, unit: str) -> float:
    return value / parse_unit(unit).factor


_DEFAULT_DISPLAY = {
    (1, 0, 0, 0): "kN", (0, 1, 0, 0): "mm", (1, 1, 0, 0): "kNm", (1, -2, 0, 0): "MPa",
    (0, 2, 0, 0): "mm²", (0, 3, 0, 0): "mm³", (0, 4, 0, 0): "mm⁴", (1, -1, 0, 0): "kN/m",
    (1, -3, 0, 0): "kN/m³", (0, 1, -0, 0): "mm", NONE: "-", (0, 0, 1, 0): "s",
    (0, -1, 0, 0): "1/mm", (1, 2, 0, 0): "kN·m²",
}


def display_unit_for(dims: Dims) -> str:
    """The unit an engineer would normally read a quantity of this dimension in."""
    return _DEFAULT_DISPLAY.get(tuple(dims), canonical_text(dims))


def canonical_text(dims: Dims) -> str:
    names = ("N", "mm", "s", "K")
    top = [f"{n}{_sup(p)}" for n, p in zip(names, dims) if p > 0]
    bot = [f"{n}{_sup(-p)}" for n, p in zip(names, dims) if p < 0]
    return ("·".join(top) or "1") + ("/" + "/".join(bot) if bot else "") if (top or bot) else "-"


def _sup(p: int) -> str:
    return {1: "", 2: "²", 3: "³", 4: "⁴"}.get(p, f"^{p}")


def si_to_canonical(magnitude: float, mass: float, length: float, time: float) -> float:
    """Convert a value in SI base units (kg, m, s) to canonical units (N, mm, s)."""
    return magnitude * (1e-3 ** mass) * (1e3 ** length)


def si_dims_to_dims(mass: float, length: float, time: float, temperature: float = 0) -> Dims:
    """Dimension exponents in (kg, m, s) expressed in (force, length, time)."""
    return (int(round(mass)), int(round(length - mass)), int(round(time + 2 * mass)),
            int(round(temperature)))


def fmt(v, sig: int = 5) -> str:
    """Format a number for an engineer: significant digits, no float noise."""
    if isinstance(v, str):
        return v
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v != v:
        return "n/a"
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 10 ** sig:
        return f"{v:.0f}"
    if a < 1e-4:
        return f"{v:.{sig - 2}e}".replace("e-0", "e-").replace("e+0", "e")
    digits = max(0, sig - 1 - int(math.floor(math.log10(a))))
    s = f"{v:.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
