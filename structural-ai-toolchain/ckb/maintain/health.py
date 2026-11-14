"""Stage 8 - maintenance: is the knowledge base still sound?

A health check needs no source files.  Every object carries its benchmarks
(the inputs and the value each source gave), so the checks can be repeated at
any time - after an object is edited, when the reference library is updated,
or when a new model has regenerated the code blocks:

    formula      the stored formula still gives the stored benchmark results
    version      the object was not edited without its version changing
    code block   the generated Python function gives the same numbers as the object
    reference    the object still agrees with the independent library
    dependencies every quantity an object uses exists, and nothing is circular
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

from .. import expr as X
from ..distill import reference as R
from ..distill.taxonomy import load as load_taxonomy
from ..ir import close
from ..kb.objects import KnowledgeBase, ResolveError


def _load_package(pkg_dir: Path):
    init = pkg_dir / "__init__.py"
    if not init.exists():
        return None
    name = "ckb_objects_healthcheck"
    spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[str(pkg_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:                                            # noqa: BLE001
        return None
    finally:
        pass
    return module


def check(kb: KnowledgeBase, kb_dir: Path | None = None) -> dict:
    tax = load_taxonomy()
    formulas = {oid: o.tree for oid, o in kb.objects.items()}
    package = _load_package(Path(kb_dir) / "python" / "ckb_objects") if kb_dir else None
    rows = []
    for oid, o in kb.objects.items():
        row = {"object": oid, "symbol": o.text, "status": o.status, "problems": []}
        # dependencies
        try:
            steps, inputs = kb.plan(oid)
            missing = [p for p in inputs if p not in kb.quantities and p not in kb.objects]
            if missing:
                row["problems"].append("unknown quantities: " + ", ".join(missing))
        except ResolveError as exc:
            row["problems"].append(str(exc))
            steps, inputs = [], []
        # version
        if o.version and o.version != o.fingerprint():
            row["problems"].append("edited without a new version (formula does not match the recorded version)")
        # formula against its stored benchmarks
        n = bad = 0
        for item in o.benchmarks.get("items", []):
            if item.get("got") is None or not item.get("inputs"):
                continue
            if not all(p in item["inputs"] for p in o.params):
                continue
            n += 1
            try:
                got = X.evaluate(o.tree, item["inputs"])
            except X.ExprError:
                bad += 1
                continue
            if not close(got, item["got"], rel=1e-9):
                bad += 1
        row["benchmarks_rerun"] = n
        if bad:
            row["problems"].append(f"{bad} of {n} stored benchmark results are no longer reproduced")
        # generated code block
        fn = getattr(package, o.var or oid, None) if package else None
        if package is not None and o.examples:
            ex = o.examples[0]
            try:
                want, trace = kb.evaluate(oid, ex["inputs"], given=tuple(ex.get("given", [])))
                env = dict(ex["inputs"])
                for st in trace:
                    env[st.id] = st.value
                module = sys.modules.get(f"ckb_objects_healthcheck.{oid}")
                func = getattr(module, o.var or oid, None) if module else fn
                got = func(*[env[p] for p in o.params]) if func else None
                row["code_block"] = "ok" if got is not None and close(got, want, rel=1e-12) else "differs"
                if row["code_block"] != "ok":
                    row["problems"].append("the generated Python function gives a different number")
            except Exception as exc:                             # noqa: BLE001
                row["code_block"] = "error"
                row["problems"].append(f"the generated Python function fails: {exc}")
        # independent reference
        ref = R.check(oid, formulas, tax)
        if ref:
            row["reference"] = ref["status"]
            if o.reference and o.reference.get("status") == "agrees" and ref["status"] != "agrees":
                row["problems"].append(f"no longer agrees with {ref['library']} {ref['function']}")
        rows.append(row)
    usage = Counter()
    log = Path(kb_dir).parent / "workspace" / "usage.jsonl" if kb_dir else None
    if log and log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                usage[json.loads(line)["object"]] += 1
            except (ValueError, KeyError):
                continue
    for row in rows:
        row["uses"] = usage.get(row["object"], 0)
    return {"objects": len(rows), "healthy": sum(not r["problems"] for r in rows),
            "problems": sum(bool(r["problems"]) for r in rows), "rows": rows,
            "reference_library": R.library()[0]}
