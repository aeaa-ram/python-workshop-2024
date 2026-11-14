"""Stage 5/6 - the knowledge base: calculation objects and how they connect.

A *calculation object* is one quantity of the code with its unified formula:
as small as possible (the size factor ``k`` is its own object and is reused by
``v_min`` and ``V_Rd,c``).  Objects refer to each other by id, so a larger
calculation is not written - it is *resolved*: asking for ``V_Rd,c`` pulls in
``k``, ``ρ_l``, ``C_Rd,c``, ``v_min`` and ``V_Rd,c,min`` and leaves the
engineer with the primary inputs only.

An object is stored as a small YAML file.  Everything else - the Python code
block, the web calculator, the Excel calculator, the printed equation - is
generated from that one file.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

from .. import expr as X
from .. import units as U
from ..notation import mathml, pretty


@dataclass
class Quantity:
    """A parameter: geometry, material grade, action or code coefficient."""
    id: str
    name: str
    var: str = ""
    symbol: str = ""
    unit: str = "-"
    kind: str = "input"
    topic: str = ""
    clause: str = ""
    typical: float | str | None = None      # canonical units
    range: list | None = None               # canonical units
    observed: int = 0                       # how many source values were seen

    @property
    def text(self) -> str:
        return pretty(self.var or self.id, self.symbol)

    @property
    def ml(self) -> str:
        return mathml(self.var or self.id, self.symbol)


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
    branch: str = ""
    topic: str = ""
    topic_path: list = field(default_factory=list)
    clause: str = ""
    eq: str = ""
    status: str = ""                        # consensus | unified | single source | disagreement
    support: dict = field(default_factory=dict)
    variants: list = field(default_factory=list)
    neutral: dict = field(default_factory=dict)
    benchmarks: dict = field(default_factory=dict)
    reference: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)      # what limits trust in the object itself
    findings: list = field(default_factory=list)      # what the object revealed about the sources
    examples: list = field(default_factory=list)
    check: str = ""
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
    def reference_text(self) -> str:
        bits = []
        if self.clause:
            bits.append(self.clause if self.clause.lower().startswith("table") else f"cl. {self.clause}")
        if self.eq:
            bits.append(f"expr. {self.eq}")
        return f"{self.code} " + ", ".join(bits) if bits else self.code

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([self.id, self.formula, self.unit], sort_keys=True).encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in ("", None, [], {})}


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
        self.topics: list = []
        self.sources: list = []

    # ---- names ------------------------------------------------------------
    def name(self, sid: str) -> str:
        item = self.objects.get(sid) or self.quantities.get(sid)
        return item.text if item else pretty(sid.lstrip("~"))

    def ml(self, sid: str) -> str:
        item = self.objects.get(sid) or self.quantities.get(sid)
        return item.ml if item else mathml(sid.lstrip("~"))

    def unit(self, sid: str) -> str:
        item = self.objects.get(sid) or self.quantities.get(sid)
        return item.unit if item else "-"

    def var(self, sid: str) -> str:
        item = self.objects.get(sid) or self.quantities.get(sid)
        return (item.var or item.id) if item else sid

    # ---- dependency resolution ---------------------------------------------
    def plan(self, target: str, given=()) -> tuple[list[str], list[str]]:
        """Objects to evaluate (in order) and the inputs they need.

        ``given`` lists quantities the user supplies directly even though an
        object exists for them (entering ``k`` by hand, say).
        """
        if target not in self.objects:
            raise ResolveError(f"no calculation object {target!r}")
        given = set(given)
        steps: list[str] = []
        inputs: list[str] = []
        state: dict[str, int] = {}

        def visit(oid: str, trail: tuple):
            if state.get(oid) == 2:
                return
            if oid in trail:
                raise ResolveError("objects refer to each other in a circle: " + " -> ".join(trail + (oid,)))
            for p in self.objects[oid].params:
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
        """A starting value for every input (typical value seen in the sources)."""
        _, inputs = self.plan(target, given)
        out = {}
        for p in inputs:
            q = self.quantities.get(p)
            if q is not None and q.typical is not None:
                out[p] = q.typical
            elif q is not None and q.range:
                out[p] = (q.range[0] + q.range[1]) / 2
            elif p in self.objects and self.objects[p].examples:
                out[p] = self.objects[p].examples[0].get("expected")
        return out

    def users_of(self, oid: str) -> list[str]:
        return [o.id for o in self.objects.values() if oid in o.params]

    # ---- display units ------------------------------------------------------
    def to_display(self, sid: str, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return U.from_canonical(value, self.unit(sid))
        return value

    def from_display(self, sid: str, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return U.to_canonical(value, self.unit(sid))
        return value

    # ---- storage ------------------------------------------------------------
    def save(self, root: Path) -> None:
        root = Path(root)
        (root / "objects").mkdir(parents=True, exist_ok=True)
        for old in (root / "objects").glob("*.yaml"):
            old.unlink()
        for obj in self.objects.values():
            (root / "objects" / f"{obj.id}.yaml").write_text(
                yaml.safe_dump(obj.to_dict(), sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
        index = {
            "meta": self.meta, "topics": self.topics, "sources": self.sources,
            "quantities": {q.id: {k: v for k, v in asdict(q).items() if v not in ("", None, [])}
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
        kb.meta, kb.topics, kb.sources = index.get("meta", {}), index.get("topics", []), index.get("sources", [])
        for qid, q in index.get("quantities", {}).items():
            kb.quantities[qid] = Quantity(**q)
        for oid in index.get("objects", []):
            data = yaml.safe_load((root / "objects" / f"{oid}.yaml").read_text(encoding="utf-8"))
            kb.objects[oid] = CalcObject(**data)
        return kb
