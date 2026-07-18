"""Atomic formula library — the single source of truth for shared math.

Call any formula directly (base / Eurocode-recommended values):

    >>> from src.library import custom
    >>> custom.E_cm_t(E_cm=33000, f_cm_t=30.3, f_cm=38)
    30845.3...

Resolve a national-annex variant (parameter override, same formula):

    >>> from src.library import resolve
    >>> r = resolve("crack.max_spacing", "EN-NO")
    >>> r.params["k_3"]            # effective coefficient for Norway

Find formulas — drill-down tree or free-text search:

    >>> from src.library import catalog, search
    >>> search("crack width")[0].atom.atom_id
    'ec2.crack.w_k'

Reuse inside a tool (never re-type shared math):

    sheet.apply("s_r_max", "ec2.crack.s_r_max", jurisdiction="EN-NO")
"""

from src.library.registry import (
    Atom,
    AtomError,
    CustomNamespace,
    NationalAnnex,
    ResolvedAtom,
    all_annexes,
    all_atoms,
    atoms_for_concept,
    get_atom,
    national_annex,
    register,
    resolve,
)
from src.library.discovery import catalog, catalog_lines, search
from src.library import atoms_ec2  # noqa: F401 — registers the seed atoms

custom = CustomNamespace()

__all__ = [
    "Atom",
    "AtomError",
    "NationalAnnex",
    "ResolvedAtom",
    "register",
    "national_annex",
    "get_atom",
    "resolve",
    "atoms_for_concept",
    "all_atoms",
    "all_annexes",
    "catalog",
    "catalog_lines",
    "search",
    "custom",
]
