"""The agent's case file — durable working memory for one ingestion.

Everything the agentic workflow learns, decides and asks lives here:
fragments (the atomised pieces of the source tool), the dependency graph,
every question asked and every answer given, a timestamped journal of each
stage, verification and reflection results per iteration. It is saved next
to the delivered tool (``casefile.json`` + ``JOURNAL.md``) so a reviewer
can audit exactly how the conversion was derived — no black box.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FUNCS = {"sqrt", "min", "max", "abs", "exp", "log", "ln", "pi", "sin",
          "cos", "tan", "cot", "sec", "csc", "asin", "acos", "atan",
          "floor", "ceiling"}


@dataclass
class Fragment:
    """One atomised piece of the source tool."""

    fid: str
    kind: str                 # input|derived|check|text|image|noise
    name: str = ""
    expression: str = ""
    value: object = None      # literal / cached source value
    unit: str = ""
    description: str = ""
    source_ref: str = ""      # cell / region provenance
    clause: str = ""          # researched code clause
    clause_confidence: str = ""   # 'cited' | 'atom' | 'llm' | ''
    atom_id: str = ""         # matched library atom
    status: str = "kept"      # kept | discarded | unresolved | deferred
    repetitive_of: str = ""   # fid of an identical-structure fragment
    evidence: list = field(default_factory=list)
    image_b64: str = ""
    image_mime: str = "image/png"

    def depends_on(self) -> set[str]:
        if not self.expression:
            return set()
        return set(_IDENT.findall(self.expression)) - _FUNCS


@dataclass
class Decision:
    qid: str
    stage: str
    prompt: str
    options: list
    answer: str
    answered_by: str          # 'user' | 'default' | 'script'
    context: str = ""


@dataclass
class CaseFile:
    source_path: str
    source_format: str
    title: str = ""
    reference: str = ""
    description: str = ""
    fragments: list = field(default_factory=list)     # [Fragment]
    decisions: list = field(default_factory=list)     # [Decision]
    journal: list = field(default_factory=list)       # [str]
    iterations: int = 0
    verification: dict = field(default_factory=dict)  # last verify result
    reflection: list = field(default_factory=list)    # [str] final checklist
    final_result: str = ""    # the governing quantity (e.g. 'UR')
    layout: str = "detailed"  # user's presentation choice

    # -------------------------------------------------------------- #
    def log(self, stage: str, message: str) -> None:
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.journal.append(f"[{stamp}] {stage:11} | {message}")

    def frag(self, name_or_fid: str):
        for f in self.fragments:
            if f.fid == name_or_fid or f.name == name_or_fid:
                return f
        return None

    def kept(self, kind: str | None = None) -> list:
        out = [f for f in self.fragments if f.status == "kept"]
        return [f for f in out if f.kind == kind] if kind else out

    def names(self) -> set[str]:
        return {f.name for f in self.fragments if f.name}

    def add(self, fragment: Fragment) -> Fragment:
        self.fragments.append(fragment)
        return fragment

    def next_fid(self, prefix: str) -> str:
        return f"{prefix}{sum(1 for f in self.fragments if f.fid.startswith(prefix)) + 1:02d}"

    # -------------------------------------------------------------- #
    def unresolved(self) -> list:
        return [f for f in self.fragments if f.status == "unresolved"]

    def dependency_errors(self) -> list[str]:
        """Kept derived/check fragments whose dependencies are missing."""
        available = {f.name for f in self.kept() if f.name} | set()
        errors = []
        for f in self.kept():
            if f.kind in ("derived", "check"):
                missing = f.depends_on() - available
                if missing:
                    errors.append(
                        f"'{f.name or f.expression}' needs {sorted(missing)}")
        return errors

    # -------------------------------------------------------------- #
    def save(self, tool_dir: str | Path) -> None:
        tool_dir = Path(tool_dir)
        tool_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        # strip image payloads from the JSON record (fingerprints only)
        for f in payload["fragments"]:
            if f.get("image_b64"):
                f["image_b64"] = f"<{len(f['image_b64'])} b64 chars>"
        (tool_dir / "casefile.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8")
        lines = [f"# Ingestion journal — {self.title or self.source_path}",
                 "", f"Source: `{self.source_path}` ({self.source_format})",
                 f"Iterations to convergence: {self.iterations}", ""]
        lines += ["## Stage log", ""] + [f"- {e}" for e in self.journal]
        if self.decisions:
            lines += ["", "## Decisions (questions asked during the build)", ""]
            for d in self.decisions:
                lines += [f"**[{d.stage}] {d.prompt}**",
                          f"→ `{d.answer}` ({d.answered_by})", ""]
        if self.reflection:
            lines += ["", "## Self-reflection checklist", ""]
            lines += [f"- {r}" for r in self.reflection]
        (tool_dir / "JOURNAL.md").write_text("\n".join(lines),
                                             encoding="utf-8")
