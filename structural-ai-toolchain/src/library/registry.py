"""The atom registry — single source of truth for shared formulas,
with national-annex variants handled as a *sub-group*, not a new silo.

Two kinds of jurisdictional variation, both supported:

1. **Parameter override** (the common case). The formula is the same; a
   coefficient differs. e.g. crack-spacing k_3 = 3.4 (recommended / most
   NAs) but a National Annex sets a different value. Register the base
   atom once with ``params={"k_3": 3.4, ...}``; add a
   ``national_annex(concept, "EN-NO", {"k_3": 0.5})``. k_3 is still k_3
   and still fits the formula — nothing is duplicated.

2. **Different approach** (the rare case). The whole method changes — a
   different crack-width model with different inputs. Register a SEPARATE
   atom with the *same concept* but a different ``jurisdiction`` and its
   own expression/inputs. ``resolve(concept, jurisdiction)`` returns it
   when that jurisdiction is asked for, else falls back to the base.

An atom distinguishes **params** (code coefficients, have defaults, NA can
override) from **inputs** (everything else the user supplies).

Discovery: atoms carry a taxonomy (jurisdiction / code / chapter / clause)
so they can be browsed as a drill-down tree *and* free-text searched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sympy as sp

_REGISTRY: dict[str, "Atom"] = {}
# (concept, jurisdiction) -> {param: value, ...}
_ANNEX: dict[tuple[str, str], "NationalAnnex"] = {}

BASE_JURISDICTION = "EN"  # Eurocode recommended values


class AtomError(Exception):
    pass


def _parse(expression: str) -> sp.Expr:
    from src.knowledge_graph.fingerprint import parse_locals

    try:
        return sp.sympify(expression, locals=parse_locals(expression))
    except (sp.SympifyError, SyntaxError, TypeError) as exc:
        raise AtomError(f"Cannot parse {expression!r}: {exc}") from exc


@dataclass
class Atom:
    atom_id: str                 # unique dotted id, e.g. "ec2.crack.s_r_max"
    result: str                  # canonical result symbol
    expression: str              # sympy-parseable formula string
    clause: str = ""             # e.g. "EN 1992-1-1:2004 §7.3.4(3)"
    description: str = ""
    units: dict = field(default_factory=dict)        # symbol -> unit
    latex_names: dict = field(default_factory=dict)  # symbol -> LaTeX
    notes: str = ""
    # taxonomy / variants
    concept: str = ""            # shared id across jurisdictions/variants
    jurisdiction: str = BASE_JURISDICTION   # "EN", "EN-NO", "EN-DK", ...
    code: str = "EN 1992-1-1"    # the standard
    chapter: str = ""            # e.g. "7 Serviceability"
    params: dict = field(default_factory=dict)  # code coefficients + defaults

    def __post_init__(self) -> None:
        self._expr = _parse(self.expression)
        self.symbols = sorted(s.name for s in self._expr.free_symbols)
        if not self.concept:
            self.concept = self.atom_id
        bad = [p for p in self.params if p not in self.symbols]
        if bad:
            raise AtomError(
                f"{self.atom_id}: params {bad} are not in the expression "
                f"(symbols: {self.symbols})"
            )

    @property
    def inputs(self) -> list[str]:
        """Symbols the user must supply (everything that isn't a param)."""
        return [s for s in self.symbols if s not in self.params]

    # -------------------------------------------------------------- #
    def __call__(self, _params: dict | None = None, **values: float) -> float:
        """Evaluate: params auto-filled from defaults (override via
        ``_params``), inputs passed as keywords."""
        effective = dict(self.params)
        if _params:
            effective.update(_params)
        supplied = {**effective, **values}
        missing = [s for s in self.symbols if s not in supplied]
        if missing:
            raise AtomError(
                f"{self.atom_id} needs inputs {missing} "
                f"(inputs: {self.inputs}, params: {list(self.params)})"
            )
        subs = {sp.Symbol(k): sp.Float(v) for k, v in supplied.items()}
        out = sp.N(self._expr.xreplace(subs))
        if not out.is_number:
            raise AtomError(f"{self.atom_id} did not evaluate to a number")
        return float(out)

    def expression_for(self, subs: dict[str, str]) -> str:
        """Original expression string with symbols textually renamed
        (faithful — no sympy auto-simplification)."""
        bad = [k for k in subs if k not in self.symbols]
        if bad:
            raise AtomError(
                f"{self.atom_id} has no symbol(s) {bad}; "
                f"available: {self.symbols}"
            )
        for name in subs.values():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise AtomError(f"Invalid variable name {name!r}")
        if not subs:
            return self.expression

        def repl(match: re.Match) -> str:
            return subs.get(match.group(0), match.group(0))

        return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", repl, self.expression)

    def fingerprint(self) -> str:
        from src.knowledge_graph.fingerprint import fingerprint

        return fingerprint(self.expression)

    def path(self) -> list[str]:
        """Drill-down path: jurisdiction / code / chapter / clause."""
        return [self.jurisdiction, self.code,
                self.chapter or "(general)", self.clause or self.atom_id]


@dataclass
class NationalAnnex:
    concept: str
    jurisdiction: str
    param_overrides: dict
    clause: str = ""
    note: str = ""


# ------------------------------------------------------------------ #
@dataclass
class ResolvedAtom:
    """An atom resolved for a jurisdiction, with effective params."""

    atom: Atom
    jurisdiction: str
    params: dict            # effective coefficient values
    provenance: list[str]   # clauses applied (base + annex)

    @property
    def expression(self) -> str:
        return self.atom.expression

    def __call__(self, **values: float) -> float:
        return self.atom(_params=self.params, **values)


# ------------------------------------------------------------------ #
# Registration & lookup
# ------------------------------------------------------------------ #
def register(atom: Atom) -> Atom:
    if atom.atom_id in _REGISTRY:
        raise AtomError(f"Duplicate atom id: {atom.atom_id}")
    _REGISTRY[atom.atom_id] = atom
    return atom


def national_annex(
    concept: str,
    jurisdiction: str,
    param_overrides: dict,
    clause: str = "",
    note: str = "",
) -> NationalAnnex:
    """Register coefficient overrides for a concept in a jurisdiction."""
    na = NationalAnnex(concept, jurisdiction, param_overrides, clause, note)
    _ANNEX[(concept, jurisdiction)] = na
    return na


def get_atom(atom_id: str) -> Atom:
    if atom_id in _REGISTRY:
        return _REGISTRY[atom_id]
    candidates = [
        a for key, a in _REGISTRY.items()
        if key.rsplit(".", 1)[-1] == atom_id
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise AtomError(
            f"Ambiguous atom {atom_id!r}: {[a.atom_id for a in candidates]}"
        )
    raise AtomError(f"Unknown atom {atom_id!r}. Known: {sorted(_REGISTRY)}")


def atoms_for_concept(concept: str) -> list[Atom]:
    return [a for a in _REGISTRY.values() if a.concept == concept]


def resolve(concept: str, jurisdiction: str = BASE_JURISDICTION) -> ResolvedAtom:
    """Resolve the effective atom + coefficients for a jurisdiction.

    Picks a full-alternative atom if one is registered for this exact
    jurisdiction; otherwise the base atom. Then layers on any national
    annex parameter overrides.
    """
    candidates = atoms_for_concept(concept)
    if not candidates:
        # maybe an atom_id was passed instead of a concept
        try:
            atom = get_atom(concept)
            candidates = atoms_for_concept(atom.concept)
            concept = atom.concept
        except AtomError:
            raise AtomError(f"No atom for concept {concept!r}")

    exact = [a for a in candidates if a.jurisdiction == jurisdiction]
    base = [a for a in candidates if a.jurisdiction == BASE_JURISDICTION]
    atom = (exact or base or candidates)[0]

    params = dict(atom.params)
    provenance = [atom.clause] if atom.clause else []
    annex = _ANNEX.get((concept, jurisdiction))
    if annex:
        unknown = [p for p in annex.param_overrides if p not in params]
        if unknown:
            raise AtomError(
                f"National annex {jurisdiction} for {concept} overrides "
                f"unknown params {unknown} (params: {list(params)})"
            )
        params.update(annex.param_overrides)
        if annex.clause:
            provenance.append(annex.clause)
    return ResolvedAtom(atom, jurisdiction, params, provenance)


def all_atoms() -> list[Atom]:
    return list(_REGISTRY.values())


def all_annexes() -> list[NationalAnnex]:
    return list(_ANNEX.values())


class CustomNamespace:
    """Attribute-style access to atoms: ``custom.E_cm_t(...)``.

    Defaults to the base (EN) jurisdiction. For a national-annex value
    use ``library.resolve(concept, "EN-NO")``.
    """

    def __getattr__(self, name: str) -> Atom:
        try:
            return get_atom(name)
        except AtomError as exc:
            raise AttributeError(str(exc)) from exc

    def __getitem__(self, atom_id: str) -> Atom:
        return get_atom(atom_id)

    def __dir__(self):
        return sorted(key.rsplit(".", 1)[-1] for key in _REGISTRY)
