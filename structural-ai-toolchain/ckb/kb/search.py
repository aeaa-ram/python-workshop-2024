"""Finding an object, and placing a new calculation against the knowledge base.

``search`` answers "is there a module for this?" from a symbol, a clause number or
plain words.  It is a word search: every word of the query has to appear in what
is known about an object (its name, symbol, clause, the titles and keywords of its
chapter, the code's title, the words the registry lists for it); a word may be the
start of a longer one ("reinf" finds "reinforcement").  "concrete shear" therefore
finds the shear objects of EN 1992-1-1, whose title is "Design of concrete
structures".  The web calculator runs the same index with the same rules.

``classify`` answers the question asked of every new source: for each formula it
contains, is it the code expression, a simplification of it, something else, or a
quantity the knowledge base does not hold yet?
"""
from __future__ import annotations

import re

from .. import expr as X
from ..distill.baseline import compare
from ..distill.decompose import LOCAL, decompose
from ..distill.taxonomy import Taxonomy
from ..ir import SourceDocument, close
from ..notation import symkey
from .objects import KnowledgeBase

_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")


def words(text: str) -> list[str]:
    """Lower-case words; clause numbers (6.2.2) stay whole."""
    return _WORD.findall(text.lower().replace("_", " "))


def _stem(w: str) -> str:
    for suffix in ("ing", "es", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


FIELDS = (("name", 3.0), ("chapter", 2.0), ("other", 1.0), ("weak", 0.4))


def index(kb: KnowledgeBase, tax: Taxonomy | None = None) -> dict:
    """What the search looks at, per object: {id: {keys, rank, name, chapter, other, weak}}.

    ``name``: the object's name and symbol.  ``chapter``: titles and keywords of its
    chapter.  ``other``: clause, code and code title, words the registry lists.
    ``weak``: the design background.  ``keys``: symbol spellings.  ``rank``: 1 for
    results checked against an action (V_Rd,c, w_k), which come before the
    intermediate quantities when the words fit both equally.
    """
    codes = {c["code"]: c for c in kb.codes}
    out = {}
    for o in kb.objects.values():
        code = codes.get(o.code, {})
        topics = {t["id"]: t for t in code.get("topics", [])}
        chapter = list(o.topic_path)
        for tid in topics:
            if o.topic == tid or o.topic.startswith(tid + "."):
                chapter += [topics[tid].get("title", "")] + list(topics[tid].get("keywords", []))
        c = tax.concepts.get(o.id) if tax is not None else None
        keys = {symkey(o.id), symkey(o.var or o.id), symkey(o.text)} | (c.keys if c else set())
        # the same keys with Greek letters as typed (ρ_l), for the web calculator's search
        keys |= {re.sub(r"[\s_.,;:{}\\'’`\-−]+", "", t) for t in [o.text] + list(c.aliases if c else [])}
        keys = sorted(k for k in keys if k)
        other = ([o.clause, o.eq, o.code, code.get("title", "")] + list(c.words if c else [])
                 + [codes.get(r["code"], {}).get("title", "") + " " + r["code"] for r in o.refs])
        weak = [b.get("text", "") for b in o.background]
        out[o.id] = {"keys": keys, "rank": 1 if o.check else 0,
                     **{f: " ".join(dict.fromkeys(words(" ".join(t))))
                        for f, t in (("name", [o.name, o.text]), ("chapter", chapter), ("other", other),
                                     ("weak", weak))}}
    return out


def _hit(token: str, vocab: list[str]) -> bool:
    t = _stem(token)
    for w in vocab:
        if w == token or w.startswith(t) or (len(w) > 3 and t.startswith(_stem(w)) and len(t) - len(w) <= 3):
            return True
    return False


def search(kb: KnowledgeBase, tax: Taxonomy | None, query: str, limit: int = 8,
           idx: dict | None = None) -> list[tuple[float, str, str]]:
    """Ranked (score, object id, why).  Objects that contain every word come first."""
    idx = idx or index(kb, tax)
    q = query.strip()
    if not q:
        return []
    key = symkey(q)
    tokens = [t for t in words(q) if len(t) > 1 or t.isdigit()]
    hits = []
    for oid, entry in idx.items():
        o = kb.objects[oid]
        if key and key in entry["keys"]:
            hits.append((100.0, oid, "symbol"))
            continue
        if q.strip("() ") and (q == o.clause or q.strip("()") == o.eq.strip("()")):
            hits.append((90.0, oid, "clause"))
            continue
        if not tokens:
            continue
        score, found, in_weak = 0.0, 0, False
        for t in tokens:
            for f, w in FIELDS:
                if _hit(t, entry[f].split()):
                    score += w
                    found += 1
                    in_weak |= f == "weak"
                    break
        if not found:
            continue
        score = score / len(tokens) + (20.0 if found == len(tokens) else 5.0 * found / len(tokens)) + 1.5 * entry["rank"]
        why = "all words" if found == len(tokens) else f"{found} of {len(tokens)} words"
        hits.append((score, oid, why + (" (partly in the design background)" if in_weak else "")))
    hits.sort(key=lambda t: (-t[0], t[1]))
    if hits and hits[0][0] >= 90:
        hits = [h for h in hits if h[0] >= 90]          # a symbol or clause: show just that
    elif hits and hits[0][0] >= 20:
        hits = [h for h in hits if h[0] >= 20]          # every word found: drop partial matches
    return hits[:limit]


def classify(doc: SourceDocument, kb: KnowledgeBase, tax: Taxonomy) -> dict:
    """Compare every formula of a new source with the knowledge base."""
    dec = decompose(doc, tax)
    name = lambda s: kb.name(s) if not s.startswith(LOCAL) else s[1:]      # noqa: E731
    observed: dict = {}
    for inst in dec.instances:
        for s, a in inst.args.items():
            if isinstance(a.get("value"), (int, float)):
                observed.setdefault(s, []).append(a["value"])
    rows = []
    for inst in dec.instances:
        if inst.kind != "formula":
            continue
        concept = tax.concepts[inst.concept]
        row = {"quantity": concept.text, "where": inst.loc, "formula": X.to_text(inst.formula, name),
               "value": inst.value, "unit": inst.unit}
        obj = kb.objects.get(inst.concept)
        if obj is None:
            row.update(verdict="new object", detail="a quantity of the registry with no object yet")
        else:
            rel, missing, extra = compare(obj.tree, inst.formula, tax, observed)
            if rel == "as code":
                row.update(verdict="as code", detail=f"the expression of {obj.text} (version {obj.version})")
            elif rel == "simplified":
                row.update(verdict="simplified", detail="a special case: " + "; ".join(d.describe(name) for d in missing))
            elif rel == "project-specific":
                row.update(verdict="project-specific", detail="uses quantities the registry does not know")
            else:
                row.update(verdict="differs", detail=("adds " + "; ".join(d.describe(name) for d in extra)) if extra
                           else f"not a special case of {obj.text}: an engineer has to compare the two")
        if obj is not None and not inst.locals:
            env = {s: a["value"] for s, a in inst.args.items()}
            env.update(obj.fixed)
            if all(p in env for p in obj.params):
                try:
                    got = X.evaluate(obj.tree, env)
                    row["object_value"] = got
                    row["reproduced"] = close(got, inst.value, rel=1e-6)
                except X.ExprError:
                    pass
        rows.append(row)
    for st in dec.unmapped:
        rows.append({"quantity": st.name, "where": st.loc, "formula": st.raw[:80], "value": st.best_value(),
                     "unit": st.unit, "verdict": "new topic",
                     "detail": "not a quantity the registry knows: project-specific, or a topic to add"})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"source": doc.name, "summary": counts, "rows": rows, "conversion": doc.summary()}
