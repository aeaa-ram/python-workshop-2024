"""Lightweight dimensional-units engine for the master reviewer.

Not a full unit system (that's the planned ``pint`` integration) — just
enough to catch the "looks right but is completely wrong" class of error:
a value computed in one unit but labelled with another (e.g. a force that
comes out in N but is labelled kN — off by 1000).

Each unit maps to (dimension vector over [Force, Length], scale-to-canonical)
with canonical base = Newton (force) and millimetre (length). So:
    MPa = N/mm^2  -> dim (1,-2), scale 1
    kN            -> dim (1, 0), scale 1000
    kNm           -> dim (1, 1), scale 1e6   (kN * m = 1000 N * 1000 mm)
"""

from __future__ import annotations

import re

# dim = (force_exp, length_exp); scale converts 1 <unit> to canonical (N,mm)
_UNITS: dict[str, tuple[tuple[int, int], float]] = {
    "": ((0, 0), 1.0), "-": ((0, 0), 1.0), "1": ((0, 0), 1.0),
    "rad": ((0, 0), 1.0), "deg": ((0, 0), 1.0), "%": ((0, 0), 1.0),
    # length
    "mm": ((0, 1), 1.0), "cm": ((0, 1), 10.0), "m": ((0, 1), 1000.0),
    # area
    "mm2": ((0, 2), 1.0), "mm^2": ((0, 2), 1.0),
    "cm2": ((0, 2), 100.0), "cm^2": ((0, 2), 100.0),
    "m2": ((0, 2), 1e6), "m^2": ((0, 2), 1e6),
    # volume / section modulus (length^3)
    "mm3": ((0, 3), 1.0), "mm^3": ((0, 3), 1.0),
    "cm3": ((0, 3), 1e3), "cm^3": ((0, 3), 1e3),
    "m3": ((0, 3), 1e9), "m^3": ((0, 3), 1e9),
    # second moment of area (length^4)
    "mm4": ((0, 4), 1.0), "mm^4": ((0, 4), 1.0),
    "cm4": ((0, 4), 1e4), "cm^4": ((0, 4), 1e4),
    "m4": ((0, 4), 1e12), "m^4": ((0, 4), 1e12),
    # force
    "N": ((1, 0), 1.0), "kN": ((1, 0), 1e3), "MN": ((1, 0), 1e6),
    # stress / pressure / modulus
    "Pa": ((1, -2), 1e-6), "kPa": ((1, -2), 1e-3),
    "MPa": ((1, -2), 1.0), "GPa": ((1, -2), 1e3),
    "N/mm2": ((1, -2), 1.0), "N/mm^2": ((1, -2), 1.0),
    # moment
    "Nmm": ((1, 1), 1.0), "Nm": ((1, 1), 1e3),
    "kNm": ((1, 1), 1e6), "kNmm": ((1, 1), 1e3),
}


_SUPERSCRIPTS = str.maketrans({"²": "2", "³": "3", "⁴": "4", "⁻": "-",
                                "¹": "1"})


def parse_unit(unit: str):
    """Return (dim, scale) for a unit string, or None if unknown.

    Accepts the table spellings plus compounds such as ``kN/m``,
    ``kN/m^2``, ``kN·m/m`` or ``N/mm²``."""
    if unit is None:
        return None
    u = unit.strip().translate(_SUPERSCRIPTS)
    key = u.replace("·", "").replace(" ", "")
    if key in _UNITS:
        return _UNITS[key]
    # normalise common variants
    key2 = key.replace("^", "")
    if key2 in _UNITS:
        return _UNITS[key2]
    return _parse_compound(u)


def _parse_compound(unit: str):
    tokens = re.split(r"\s*([*/·])\s*", unit.replace(" ", "·"))
    if len(tokens) < 3:
        return None
    force = length = 0
    scale = 1.0
    sign = 1
    for tok in tokens:
        if tok in ("*", "·"):
            sign = 1
            continue
        if tok == "/":
            sign = -1
            continue
        m = re.fullmatch(r"([A-Za-z%µ]+)\^?(-?\d+)?", tok)
        if not m:
            return None
        base, exp = m.group(1), int(m.group(2) or 1)
        entry = _UNITS.get(base)
        if entry is None:
            return None
        (f, l), s = entry
        force += sign * f * exp
        length += sign * l * exp
        scale *= s ** (sign * exp)
    return ((force, length), scale)


def unit_for(dim: tuple, scale: float) -> str | None:
    """A table unit with this dimension and scale (e.g. force, 1 -> 'N')."""
    for name, (d, s) in _UNITS.items():
        if d == tuple(dim) and abs(s / scale - 1.0) < 1e-9 and "^" not in name \
                and name not in ("", "-", "1", "rad", "%"):
            return name
    return None


def known(unit: str) -> bool:
    return parse_unit(unit) is not None


def scale_of(unit: str) -> float | None:
    p = parse_unit(unit)
    return p[1] if p else None


def dim_of(unit: str):
    p = parse_unit(unit)
    return p[0] if p else None


_PREFIX = {1: "", 1e3: "k", 1e6: "M", 1e-3: "m", 1e-6: "µ"}


def nearest_power_of_ten(ratio: float) -> float | None:
    """If ratio is close to 10^k, return that power; else None."""
    import math

    if ratio <= 0:
        return None
    k = round(math.log10(ratio))
    p = 10.0 ** k
    if abs(ratio / p - 1.0) < 0.02:
        return p
    return None
