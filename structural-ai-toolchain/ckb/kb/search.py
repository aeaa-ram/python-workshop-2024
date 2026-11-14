"""Finding an object, and placing a new calculation against the knowledge base.

``search`` answers "is there a module for this?" from a symbol, a clause
number or plain words.

``classify`` answers the question asked of every new source: for each formula
it contains, is this logic already in the knowledge base, is it an extension
of an object, does it disagree with one, or is it a new topic?  The same
check is what lets a modified copy of a calculator be fed back without it
simply looking "wrong".
"""
from __future__ import annotations

import re

from .. import expr as X
from ..distill.consolidate import Merger
from ..distill.decompose import LOCAL, decompose
from ..distill.taxonomy import Taxonomy
from ..ir import SourceDocument, close
from ..notation import symkey
from .objects import KnowledgeBase


def search(kb: KnowledgeBase, tax: Taxonomy, query: str, limit: int = 8) -> list[tuple[float, str, str]]:
    """Ranked (score, object id, why)."""
    q = query.strip()
    words = [w for w in re.split(r"[^\w.]+", q.lower()) if len(w) > 1]
    key = symkey(q)
    hits: dict[str, tuple[float, str]] = {}

    def add(oid: str, score: float, why: str):
        if oid in kb.objects and (oid not in hits or hits[oid][0] < score):
            hits[oid] = (score, why)

    m = tax.resolve(q, label=q)
    if m is not None:
        add(m.concept.id, 10.0, f"symbol or name ({m.how})")
    for o in kb.objects.values():
        c = tax.concepts.get(o.id)
        if key and c is not None and key in c.keys:
            add(o.id, 9.0, "symbol")
        if q and (q == o.clause or o.clause.startswith(q) or q == o.topic or o.eq.strip("()") == q.strip("()")):
            add(o.id, 6.0, "clause")
        text = " ".join([o.name, " ".join(o.topic_path), o.clause, o.eq] + (c.words if c else [])).lower()
        n = sum(w in text for w in words)
        if n:
            add(o.id, 1.0 + 4.0 * n / max(len(words), 1), "words in the name or topic")
        if any(symkey(p) == key or symkey(kb.name(p)) == key for p in o.params) and key:
            add(o.id, 2.0, "uses this quantity")
    ranked = sorted(((s, oid, why) for oid, (s, why) in hits.items()), key=lambda t: (-t[0], t[1]))
    return ranked[:limit]


def classify(doc: SourceDocument, kb: KnowledgeBase, tax: Taxonomy) -> dict:
    """Compare every formula of a new source with the knowledge base."""
    dec = decompose(doc, tax)
    merger = Merger(tax)
    name = lambda s: kb.name(s) if not s.startswith(LOCAL) else s[1:]      # noqa: E731
    rows = []
    for inst in dec.instances:
        if inst.kind != "formula":
            continue
        concept = tax.concepts[inst.concept]
        row = {"quantity": concept.text, "where": inst.loc, "formula": X.to_text(inst.formula, name),
               "value": inst.value, "unit": inst.unit}
        obj = kb.objects.get(inst.concept)
        if obj is None:
            row.update(verdict="new object", detail="a quantity of the taxonomy with no object yet")
        elif X.same(inst.formula, obj.tree):
            row.update(verdict="existing", detail=f"identical to {obj.text} (version {obj.version})")
        else:
            d_new, d_obj = [], []
            merged = merger.merge(inst.formula, obj.tree, d_new, d_obj)
            if merged is None:
                row.update(verdict="differs", detail=f"not a generalisation or special case of {obj.text}: "
                                                     "an engineer has to compare the two")
            elif not d_obj:
                row.update(verdict="existing", detail="a special case of the object: this source "
                           + "; ".join(d.describe(name) for d in d_new))
            else:
                row.update(verdict="extension", detail="adds to the object: the object "
                           + "; ".join(d.describe(name) for d in d_obj))
        if obj is not None and not inst.locals:
            env = {s: a["value"] for s, a in inst.args.items()}
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
                     "detail": "not a quantity the taxonomy knows: project-specific, or a topic to add"})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"source": doc.name, "summary": counts, "rows": rows, "conversion": doc.summary()}
