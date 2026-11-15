"""Stage 5/6 - the knowledge base: calculation objects and how they connect.

A *calculation object* is one quantity of a design code with its expression: as
small as possible (the size factor ``k`` is its own object and is reused by
``v_min`` and ``V_Rd,c``).  Objects refer to each other by id, so a larger
calculation is not written - it is *resolved*: asking for ``V_Rd,c`` pulls in
``k``, ``ρ_l``, ``C_Rd,c``, ``v_min`` and ``V_Rd,c,min`` and leaves the engineer
with the primary inputs only.

An object file has two parts:

* the design logic - formula, clause, unit, applicability checks, design
  background.  This is all a calculation, report, code block or spreadsheet uses.
* the evidence - how each source applied it, benchmarks, the independent
  reference check, the confidence that follows.  It is kept for review and never
  printed into a calculation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .. import expr as X
from .. import units as U
from ..notation import latex, mathml, omml, pretty


@dataclass
class Quantity:
    """A parameter: geometry, material grade, action or code coefficient."""
    id: str
    name: str
    var: str = ""
    symbol: str = ""
    unit: str = "-"
    kind: str = "input"                     # input | coefficient
    code: str | None = None
    topic: str = ""
    clause: str = ""
    value: float | None = None              # recommended value of a coefficient, canonical units
    example: float | None = None            # value calculators open with, canonical units
    choices: list = field(default_factory=list)       # [{value (canonical), label}]
    ndp: bool = False
    range: list | None = None               # canonical units
    seen: list = field(default_factory=list)          # [[value (canonical), count]] in the sources
    background: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return pretty(self.var or self.id, self.symbol)

    @property
    def ml(self) -> str:
        return mathml(self.var or self.id, self.symbol)

    @property
    def tex(self) -> str:
        return latex(self.var or self.id, self.symbol)

    @property
    def omml(self) -> str:
        return omml(self.var or self.id, self.symbol)

    @property
    def start(self):
        """Value to start a calculation with."""
        if self.kind == "coefficient" and self.value is not None:
            return self.value
        if self.example is not None:
            return self.example
        if self.value is not None:
            return self.value
        if self.range:
            return (self.range[0] + self.range[1]) / 2
        return None


@dataclass
class CalcObject:
    id: str
    name: str
    formula: str                            # Python syntax; symbols are object / quantity ids
    params: list[str] = field(default_factory=list)
    var: str = ""
    symbol: str = ""
    unit: str = "-"
    code: str = ""
    topic: str = ""
    topic_path: list = field(default_factory=list)
    clause: str = ""
    eq: str = ""
    basis: str = ""                         # code | mechanics | definition | sources
    ndp: bool = False
    sense: str = ""
    check: str = ""
    refs: list = field(default_factory=list)          # every code that uses the object
    fixed: dict = field(default_factory=dict)         # values this object's code fixes in its chain
    alternatives: list = field(default_factory=list)
    checks: list = field(default_factory=list)        # [{when, text, clause}]
    background: list = field(default_factory=list)    # [{kind, text, refs: [{id, at, text}]}]
    # ---- evidence (never printed into a calculation) ----------------------------------
    confidence: dict = field(default_factory=dict)    # {level, label, reasons}
    evidence: dict = field(default_factory=dict)      # {sources, variants, practice, values_seen}
    benchmarks: dict = field(default_factory=dict)
    reference: dict = field(default_factory=dict)
    version: str = ""

    def __post_init__(self):
        self._tree: X.Node | None = None

    @property
    def tree(self) -> X.Node:
        if self._tree is None:
            self._tree = X.parse(self.formula)
        return self._tree

    @property
    def text(self) -> str:
        return pretty(self.var or self.id, self.symbol)

    @property
    def ml(self) -> str:
        return mathml(self.var or self.id, self.symbol)

    @property
    def tex(self) -> str:
        return latex(self.var or self.id, self.symbol)

    @property
    def omml(self) -> str:
        return omml(self.var or self.id, self.symbol)

    @property
    def reference_text(self) -> str:
        bits = []
        if self.clause:
            bits.append(self.clause if self.clause.lower().startswith(("table", "fig")) else f"cl. {self.clause}")
        if self.eq:
            bits.append(f"expr. {self.eq}")
        return (f"{self.code} " + ", ".join(bits)).strip()

    @property
    def limitations(self) -> list[str]:
        """Short notes that belong next to a calculation (scope and limitations)."""
        return [b["text"] for b in self.background if b.get("kind") in ("scope", "limitation")]

    def fingerprint(self) -> str:
        """Identifies the design logic: formula, unit and checks.  Evidence does not change it."""
        payload = [self.id, self.formula, self.unit, sorted(self.fixed.items()),
                   [c.get("when") for c in self.checks]]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in ("", None, [], {}) and v is not False}


class ResolveError(Exception):
    pass


@dataclass
class Step:
    id: str
    value: float | str
    env: dict                # the values the formula was evaluated with


class KnowledgeBase:
    def __init__(self):
        self.objects: dict[str, CalcObject] = {}
        self.quantities: dict[str, Quantity] = {}
        self.meta: dict = {}
        self.codes: list = []                 # [{code, title, edition, values, topics: [...]}]
        self.sources: list = []
        self.references: dict = {}

    # ---- names ------------------------------------------------------------
    def item(self, sid: str):
        return self.objects.get(sid) or self.quantities.get(sid)

    def name(self, sid: str) -> str:
        item = self.item(sid)
        return item.text if item else pretty(sid.lstrip("~"))

    def ml(self, sid: str) -> str:
        item = self.item(sid)
        return item.ml if item else mathml(sid.lstrip("~"))

    def tex(self, sid: str) -> str:
        item = self.item(sid)
        return item.tex if item else latex(sid.lstrip("~"))

    def omml(self, sid: str) -> str:
        item = self.item(sid)
        return item.omml if item else omml(sid.lstrip("~"))

    def unit(self, sid: str) -> str:
        item = self.item(sid)
        return item.unit if item else "-"

    def var(self, sid: str) -> str:
        item = self.item(sid)
        return (item.var or item.id) if item else sid

    # ---- dependency resolution ---------------------------------------------
    def plan(self, target: str, given=()) -> tuple[list[str], list[str]]:
        """Objects to evaluate (in order) and the inputs they need.

        ``given`` lists quantities the user supplies directly even though an
        object exists for them (entering ``k`` by hand, say).  Values the
        object's code fixes (EN 1994-1-1 fixes α_cc = 1) are not inputs.
        """
        if target not in self.objects:
            raise ResolveError(f"no calculation object {target!r}")
        given = set(given)
        fixed = self.objects[target].fixed
        steps: list[str] = []
        inputs: list[str] = []
        state: dict[str, int] = {}

        def visit(oid: str, trail: tuple):
            if state.get(oid) == 2:
                return
            if oid in trail:
                raise ResolveError("objects refer to each other in a circle: " + " -> ".join(trail + (oid,)))
            for p in self.objects[oid].params:
                if p in fixed:
                    continue
                if p in self.objects and p not in given:
                    visit(p, trail + (oid,))
                elif p not in inputs:
                    inputs.append(p)
            state[oid] = 2
            steps.append(oid)

        visit(target, ())
        return steps, inputs

    def evaluate(self, target: str, values: dict, given=()) -> tuple[float | str, list[Step]]:
        """Evaluate an object and everything it depends on.  Values are canonical."""
        steps, inputs = self.plan(target, given)
        missing = [p for p in inputs if p not in values]
        if missing:
            raise ResolveError("no value for " + ", ".join(self.name(m) for m in missing))
        env = dict(values)
        env.update(self.objects[target].fixed)
        trace: list[Step] = []
        for oid in steps:
            obj = self.objects[oid]
            try:
                env[oid] = X.evaluate(obj.tree, env)
            except X.ExprError as exc:
                raise ResolveError(f"{obj.text}: {exc}") from exc
            trace.append(Step(oid, env[oid], {p: env[p] for p in obj.params}))
        return env[target], trace

    def defaults(self, target: str, given=()) -> dict:
        """A starting value for every input: recommended values of coefficients, else examples."""
        _, inputs = self.plan(target, given)
        out = {}
        for p in inputs:
            q = self.quantities.get(p)
            if q is not None and q.start is not None:
                out[p] = q.start
        return out

    def users_of(self, oid: str) -> list[str]:
        return [o.id for o in self.objects.values() if oid in o.params]

    def checks_for(self, target: str, env: dict, given=()) -> list[dict]:
        """Applicability checks of every object in the chain, evaluated with ``env``.

        A check may need a quantity outside the chain (σ_cp ≤ 0.2 f_cd needs f_cd);
        it is calculated from the values at hand, with recommended values for
        coefficients.  A check that cannot be evaluated is returned as a reminder.
        """
        steps, _ = self.plan(target, given)
        out = []
        local = dict(env)
        for oid in steps:
            for chk in self.objects[oid].checks:
                tree = X.parse(chk["when"])
                assumed = []
                ok = True
                for s in X.symbols(tree):
                    if s in local:
                        continue
                    val = self._derive(s, local, assumed)
                    if val is None:
                        ok = False
                        break
                    local[s] = val
                row = {"object": oid, "text": chk.get("text", chk["when"]), "clause": chk.get("clause", ""),
                       "when": chk["when"], "assumed": assumed}
                if not ok:
                    row["status"] = "not checked"
                else:
                    try:
                        row["status"] = "ok" if X.evaluate(tree, local) else "violated"
                    except X.ExprError:
                        row["status"] = "not checked"
                out.append(row)
        return out

    def _derive(self, s: str, env: dict, assumed: list, depth: int = 0):
        if s in env:
            return env[s]
        if depth > 10:
            return None
        if s in self.objects:
            obj = self.objects[s]
            vals = {}
            for p in obj.params:
                v = self._derive(p, env, assumed, depth + 1)
                if v is None:
                    return None
                vals[p] = v
            try:
                return X.evaluate(obj.tree, {**env, **vals})
            except X.ExprError:
                return None
        q = self.quantities.get(s)
        if q is not None and q.kind == "coefficient" and q.value is not None:
            assumed.append(f"{q.text} = {U.fmt(U.from_canonical(q.value, q.unit))} (recommended)")
            return q.value
        return None

    # ---- display units ------------------------------------------------------
    def to_display(self, sid: str, value, unit: str | None = None):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return U.from_canonical(value, unit or self.unit(sid))
        return value

    def from_display(self, sid: str, value, unit: str | None = None):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return U.to_canonical(value, unit or self.unit(sid))
        return value

    # ---- storage ------------------------------------------------------------
    def save(self, root: Path) -> None:
        root = Path(root)
        for sub in ("objects", "evidence"):
            (root / sub).mkdir(parents=True, exist_ok=True)
            for old in (root / sub).glob("*.*"):
                old.unlink()
        evidence_keys = ("confidence", "evidence", "benchmarks", "reference")
        for obj in self.objects.values():
            d = obj.to_dict()
            ev = {k: d.pop(k) for k in evidence_keys if k in d}
            (root / "objects" / f"{obj.id}.yaml").write_text(
                yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
            (root / "evidence" / f"{obj.id}.json").write_text(
                json.dumps(ev, indent=1, ensure_ascii=False), encoding="utf-8")
        index = {
            "meta": self.meta, "codes": self.codes, "sources": self.sources, "references": self.references,
            # 0 is a value (σ_cp = 0), so test for "empty" explicitly rather than with ``in``
            "quantities": {q.id: {k: v for k, v in asdict(q).items()
                                  if not (v is None or v is False or v == "" or v == [])}
                           for q in self.quantities.values()},
            "objects": [o.id for o in self.objects.values()],
        }
        (root / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, root: Path) -> "KnowledgeBase":
        root = Path(root)
        kb = cls()
        index_file = root / "index.json"
        if not index_file.exists():
            raise FileNotFoundError(f"no knowledge base at {root} (run `python -m ckb build` first)")
        index = json.loads(index_file.read_text(encoding="utf-8"))
        kb.meta, kb.codes, kb.sources = index.get("meta", {}), index.get("codes", []), index.get("sources", [])
        kb.references = index.get("references", {})
        for qid, q in index.get("quantities", {}).items():
            kb.quantities[qid] = Quantity(**q)
        for oid in index.get("objects", []):
            data = yaml.safe_load((root / "objects" / f"{oid}.yaml").read_text(encoding="utf-8"))
            ev = root / "evidence" / f"{oid}.json"
            if ev.exists():
                data.update(json.loads(ev.read_text(encoding="utf-8")))
            kb.objects[oid] = CalcObject(**data)
        return kb
