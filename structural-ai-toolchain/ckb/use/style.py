"""Presentation preferences shared by every output: decimals and units.

One small YAML file (or dict) sets how numbers look in the calculator, the Excel
calculator, the Mathcad worksheet and the reports:

    decimals: 2              # digits after the decimal point
    min_significant: 3       # small values keep at least this many significant digits,
                             # so ρ_l = 0.00467 is not shown as 0.00
    units:                   # display unit per quantity (default: the code's usual unit)
      V_Rd_c: kN
      d: m

The logic is never affected: inside, everything stays in N, mm, MPa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import units as U


@dataclass
class Style:
    decimals: int = 2
    min_significant: int = 3
    units: dict = field(default_factory=dict)

    @classmethod
    def load(cls, source=None) -> "Style":
        if source is None:
            return cls()
        if isinstance(source, Style):
            return source
        data = source if isinstance(source, dict) else yaml.safe_load(Path(source).read_text(encoding="utf-8")) or {}
        data = data.get("style", data)
        return cls(decimals=int(data.get("decimals", 2)), min_significant=int(data.get("min_significant", 3)),
                   units=dict(data.get("units") or {}))

    def unit(self, kb, sid: str) -> str:
        """Display unit of a quantity (checked to be compatible with its own unit)."""
        own = kb.unit(sid)
        want = self.units.get(sid)
        if want:
            try:
                if U.parse_unit(want).dims == U.parse_unit(own).dims:
                    return U.parse_unit(want).text
            except U.UnitError:
                pass
        return own

    def show(self, kb, sid: str, value):
        """Canonical value -> display value in this style's unit."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return U.from_canonical(value, self.unit(kb, sid))
        return value

    def digits(self, v: float) -> int:
        """Decimals for a value: the style's decimals, more for small values."""
        if not isinstance(v, (int, float)) or v == 0 or not math.isfinite(v):
            return self.decimals
        need = self.min_significant - 1 - int(math.floor(math.log10(abs(v))))
        return max(self.decimals, min(need, 12))

    def fmt(self, v) -> str:
        if isinstance(v, str):
            return v
        if v is None:
            return "–"
        if isinstance(v, bool):
            return "yes" if v else "no"
        if not math.isfinite(v):
            return "n/a"
        if v != 0 and (abs(v) >= 1e7 or abs(v) < 10 ** -(12)):
            return f"{v:.{max(self.min_significant - 1, 1)}e}".replace("e+0", "e").replace("e-0", "e-")
        return f"{v:.{self.digits(v)}f}"

    def excel_format(self, typical: float | None) -> str:
        """An Excel number format for values of this magnitude."""
        d = self.digits(typical) if typical else self.decimals
        if typical and abs(typical) < 10 ** -(self.min_significant + 2):
            return "0.00E+00"
        return "0" if d == 0 else "0." + "0" * d

    def to_dict(self) -> dict:
        return {"decimals": self.decimals, "min_significant": self.min_significant, "units": dict(self.units)}
