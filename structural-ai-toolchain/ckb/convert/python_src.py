"""Python scripts -> machine-readable statements.

A script is read twice.  Statically, with Python's own parser, to get every
formula as a tree; and by running it in a separate process, to get the value
each formula produces.  The two are then checked against each other.

Mathcad worksheets and Jupyter notebooks are converted to a Python script
first and then go through this same path.
"""
from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..ir import SourceDocument, Statement, file_sha256, recompute

RUNNER = Path(__file__).with_name("_runner.py")
_HEADING = re.compile(r"^\s*(?:[=\-#*~]{2,}|%%)\s*(.*?)\s*[=\-#*~]*\s*$")
_REF = r"\(?\d+(?:\.\d+)*(?:\.?[A-Za-z]{1,2}\b)?\)?(?:\s?\(\d+[a-z]?\))*"
_CLAUSE = re.compile(
    rf"(?:\b(EN\s*\d{{4}}(?:-\d+)*)\s*)?(?:\b(cl(?:ause)?\.?|eq(?:n|uation)?\.?|expr(?:ession)?\.?|"
    rf"table|fig(?:ure)?\.?)\s*|(§)\s*)?({_REF})", re.I)


class ConversionError(Exception):
    """The source cannot be converted; it is flagged and skipped."""


def find_clause(text: str) -> str:
    """Pick a code reference out of free text, e.g. 'EN 1992-1-1 cl. 6.2.2(1)'."""
    for m in _CLAUSE.finditer(text or ""):
        code, kw, par, ref = m.group(1), m.group(2) or m.group(3), m.group(3), m.group(4)
        if not (code or kw):
            continue
        ref = ref.strip()
        while ref.count(")") > ref.count("("):
            ref = ref[:-1]
        if ref.count("(") > ref.count(")"):
            ref += ")"
        code = " ".join(code.upper().replace("EN", "EN ").split()) if code else ""
        kw = (kw or "").lower()
        kw = {"clause": "cl.", "cl": "cl.", "eq": "eq.", "eqn": "eq.", "equation": "eq.", "expr": "expr.",
              "expression": "expr.", "fig": "fig.", "figure": "fig."}.get(kw.rstrip("."), kw)
        if kw.rstrip(".") in ("cl", "eq", "expr", "fig") and not kw.endswith("."):
            kw += "."
        return " ".join(x for x in (code, kw or ("cl." if code else ""), ref) if x)
    return ""


def run_script(source: str, timeout: int = 120) -> dict:
    """Execute a script in an isolated process and return the recorded values."""
    with tempfile.TemporaryDirectory(prefix="ckb_run_") as tmp:
        script, out = Path(tmp) / "source.py", Path(tmp) / "values.json"
        script.write_text(source, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-I", str(RUNNER), str(script), str(out)],
                                  cwd=tmp, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"script did not finish within {timeout} s") from exc
        if not out.exists():
            raise ConversionError("script could not be run: " + (proc.stderr or "").strip()[-400:])
        return json.loads(out.read_text(encoding="utf-8"))


def _comments(source: str) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = tok.string.lstrip("#").strip()
    except (tokenize.TokenError, IndentationError):
        pass
    return out


def _unit_of_ast(node: ast.AST, roots) -> str:
    """Text of a pure unit expression such as ``ureg.kN * ureg.m``."""
    try:
        tree = X.from_ast(node, unit_roots=roots)
    except X.ExprError:
        return ""
    try:
        probe = X.strip_units(X.Bin("*", X.Num(1, "1"), tree), lambda u: (1.0, U.parse_unit(u).text))
    except U.UnitError:
        return ""
    if not (isinstance(probe, X.Num) and probe.text.startswith("1")):
        return ""
    text = probe.text[1:].strip()
    try:
        return U.parse_unit(text).text
    except U.UnitError:
        return text


def _hint_unit(comment: str) -> tuple[str, str]:
    """Unit hint and remaining text of a trailing comment: ``# mm, effective depth``."""
    c = comment.strip()
    m = re.search(r"[\[(]\s*([^\[\]()]{1,12})\s*[\])]", c)
    if m and U.is_unit(m.group(1)):
        rest = (c[:m.start()] + c[m.end():]).strip(" ,;-:")
        return U.parse_unit(m.group(1)).text, rest
    m = re.match(r"^([^\s,;:]{1,10})(?:[\s,;:]+(.*))?$", c)
    if m and U.is_unit(m.group(1)) and m.group(1) not in ("s", "t", "h", "m", "N", "d", "-"):
        return U.parse_unit(m.group(1)).text, (m.group(2) or "").strip()
    if m and m.group(1) in ("m", "N") and not m.group(2):
        return m.group(1), ""
    return "", c


class _Functions:
    """Functions defined in the script, inlined where they are called."""

    def __init__(self, roots):
        self.defs: dict[str, ast.FunctionDef] = {}
        self.roots = roots
        self.depth = 0

    def add(self, node: ast.FunctionDef):
        self.defs[node.name] = node

    def hook(self, fn, args, kwargs):
        node = self.defs.get(fn)
        if node is None:
            return None
        if self.depth > 20:
            raise X.ExprError(f"recursive function {fn}()")
        a = node.args
        if a.vararg or a.kwarg or a.kwonlyargs:
            raise X.ExprError(f"{fn}(): *args/**kwargs not supported")
        names = [p.arg for p in a.args]
        env: dict[str, X.Node] = {}
        defaults = a.defaults or []
        for p, d in zip(names[len(names) - len(defaults):], defaults):
            env[p] = self.tree(d)
        for p, v in zip(names, args):
            env[p] = v
        for k, v in kwargs.items():
            if k not in names:
                raise X.ExprError(f"{fn}() has no parameter {k!r}")
            env[k] = v
        missing = [p for p in names if p not in env]
        if missing:
            raise X.ExprError(f"{fn}(): missing argument {missing[0]!r}")
        self.depth += 1
        try:
            out = self.body(node.body, env)
        finally:
            self.depth -= 1
        if out is None:
            raise X.ExprError(f"{fn}() has no return value")
        return out

    def tree(self, node: ast.AST, env: dict | None = None) -> X.Node:
        t = X.from_ast(node, unit_roots=self.roots, call_hook=self.hook)
        return X.substitute(t, env) if env else t

    def body(self, stmts: list, env: dict) -> X.Node | None:
        """Turn straight-line code with if/return into one expression."""
        env = dict(env)
        for i, st in enumerate(stmts):
            if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
                continue                                        # docstring
            if isinstance(st, ast.Return):
                if st.value is None:
                    return None
                return self.tree(st.value, env)
            if isinstance(st, (ast.Assign, ast.AnnAssign)):
                targets = st.targets if isinstance(st, ast.Assign) else [st.target]
                if st.value is None or len(targets) != 1 or not isinstance(targets[0], ast.Name):
                    raise X.ExprError("unsupported assignment inside a function")
                env[targets[0].id] = self.tree(st.value, env)
                continue
            if isinstance(st, ast.If):
                cond = self.tree(st.test, env)
                rest = stmts[i + 1:]
                then = self.body(list(st.body) + rest, env)
                other = self.body(list(st.orelse) + rest, env)
                if then is None and other is None:
                    return None
                return X.If(cond, then if then is not None else X.Str("undefined"),
                            other if other is not None else X.Str("undefined"))
            if isinstance(st, ast.Pass):
                continue
            raise X.ExprError(f"unsupported statement in a function: {type(st).__name__}")
        return None


def convert_source(source: str, name: str, kind: str = "python", *, sha256: str = "",
                   converter: str = "python ast", annotate=None, run: bool = True) -> SourceDocument:
    """Convert Python source text.

    ``annotate(line, comments)`` may supply label / raw name / section / clause
    / loc for the assignment at ``line`` (the Mathcad path uses it to read the
    region markers); by default they are taken from the comments.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ConversionError(f"not valid Python (line {exc.lineno}): {exc.msg}") from exc
    doc = SourceDocument(name=name, kind=kind, sha256=sha256, converter=converter)
    comments = _comments(source)
    lines = source.splitlines()

    # unit registries in use: ureg = pint.UnitRegistry(), from x import ureg ...
    roots = {"ureg", "u", "units"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and \
                "UnitRegistry" in ast.unparse(node.value.func):
            roots |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    roots = tuple(sorted(roots))
    funcs = _Functions(roots)

    values: dict[int, dict] = {}
    if run:
        result = run_script(source)
        for rec in result["records"]:
            values[rec["line"]] = rec
        for err in result["errors"]:
            doc.issues.append(f"line {err['line']}: did not run ({err['error']})")

    # heading comments anywhere in the file: "# --- Shear ---", "# === Shear ===", "# %% Shear"
    headings = sorted((no, m.group(1)) for no, c in comments.items()
                      if lines[no - 1].lstrip().startswith("#") and (m := _HEADING.match(c)) and m.group(1))
    latest: dict[str, str] = {}          # variable name -> id of its latest statement
    counts: dict[str, int] = {}
    display: dict[str, str] = {}         # statement id -> display unit from print(disp(x, unit))
    section: list[str] = []
    embedded_units = False

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.add(node)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Pass)):
            continue
        if isinstance(node, ast.Expr):
            call = node.value
            # print(disp(x, unit)) tells us in which unit the source shows x
            if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "print" and call.args:
                inner = call.args[0]
                if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "disp" and inner.args \
                        and isinstance(inner.args[0], ast.Name) and inner.args[0].id in latest:
                    sid = latest[inner.args[0].id]
                    display[sid] = _unit_of_ast(inner.args[1], roots) if len(inner.args) > 1 else "-"
            continue
        if isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        else:
            doc.issues.append(f"line {node.lineno}: {type(node).__name__} block not converted "
                              "(only straight-line calculations are)")
            continue
        if value is None or len(targets) != 1 or not isinstance(targets[0], ast.Name):
            doc.issues.append(f"line {node.lineno}: assignment form not converted")
            continue
        var = targets[0].id
        if isinstance(value, ast.Call) and "UnitRegistry" in ast.unparse(value.func):
            continue
        rec = values.get(node.lineno, {})
        raw_line = ast.get_source_segment(source, node) or ""

        # comments: trailing one on the same line, and the block directly above
        above, ln = [], node.lineno - 1
        while ln >= 1 and ln in comments and lines[ln - 1].lstrip().startswith("#"):
            above.insert(0, comments[ln])
            ln -= 1
        info = annotate(node.lineno, above) if annotate else None
        if info is None:
            info = {}
            heads = [text for ln_no, text in headings if ln_no < node.lineno]
            if heads:
                section = [heads[-1]]
            text = [c for c in above if not _HEADING.match(c)]
            trailing = comments.get(node.end_lineno or node.lineno, "") \
                if not lines[(node.end_lineno or node.lineno) - 1].lstrip().startswith("#") else ""
            unit, rest = _hint_unit(trailing) if trailing else ("", "")
            info["label"] = " ".join(text + ([rest] if rest else [])).strip()
            info["unit"] = unit
            info["section"] = list(section)
        counts[var] = counts.get(var, 0) + 1
        sid = var if counts[var] == 1 else f"{var}~{counts[var]}"
        st = Statement(id=sid, name=info.get("name") or var, raw=raw_line,
                       label=info.get("label", ""), clause=info.get("clause", ""),
                       section=info.get("section", []), case=info.get("case", ""),
                       group=info.get("group", ""), loc=info.get("loc") or f"line {node.lineno}",
                       unit=info.get("unit", ""))
        if not st.clause:
            st.clause = find_clause(st.label)
        try:
            tree_expr = funcs.tree(value)
            had_units = X.has_units(tree_expr)
            embedded_units = embedded_units or had_units
            tree_expr = X.strip_units(tree_expr, _unit_factor)
            tree_expr = X.fold(X.substitute(tree_expr, dict(latest)))
            unknown = [s for s in X.symbols(tree_expr) if s not in doc.by_id()]
            if unknown:
                raise X.ExprError(f"refers to {unknown[0]!r}, which is not a value in this script")
            st.expr = tree_expr
        except (X.ExprError, U.UnitError) as exc:
            st.note = f"formula not converted: {exc}"
            doc.issues.append(f"{st.loc}: {var}: {exc}")
        if "v" in rec:
            v = rec["v"]
            if "dims" in rec and not isinstance(v, str):
                d = rec["dims"]
                v = U.si_to_canonical(v, d.get("[mass]", 0), d.get("[length]", 0), d.get("[time]", 0))
                if not st.unit:
                    dims = U.si_dims_to_dims(d.get("[mass]", 0), d.get("[length]", 0),
                                             d.get("[time]", 0), d.get("[temperature]", 0))
                    try:
                        st.unit = U.parse_unit(rec.get("unit", "")).text
                    except U.UnitError:
                        st.unit = U.display_unit_for(dims)
            st.value = v
        elif rec.get("skip"):
            st.note = (st.note + "; " if st.note else "") + f"value is a {rec['skip']}, not a number"
        if st.expr is not None and isinstance(st.expr, (X.Num, X.Str)):
            st.kind = "input"
            if isinstance(st.expr, X.Num) and " " in st.expr.text and not st.unit:
                st.unit = st.expr.text.split(" ", 1)[1]
        elif st.expr is None and st.value is None:
            continue                               # nothing usable (e.g. a plot object)
        doc.statements.append(st)
        latest[var] = sid

    for st in doc.statements:
        if st.id in display and display[st.id] and display[st.id] != "-":
            st.unit = display[st.id]
        if not st.unit and st.kind == "input" and isinstance(st.expr, X.Num):
            m = re.search(r"(°|%|‰)$", st.expr.text)
            if m:
                st.unit = m.group(1)
    doc.meta["units"] = "embedded" if embedded_units else "declared"
    for st in doc.statements:
        st.canonical = embedded_units
    doc.python = source
    recompute(doc)
    return doc


def _unit_factor(name: str) -> tuple[float, str]:
    info = U.parse_unit(name)
    return info.factor, info.text


def convert_python(path: Path) -> SourceDocument:
    source = Path(path).read_text(encoding="utf-8", errors="replace")
    return convert_source(source, Path(path).name, "python", sha256=file_sha256(path),
                          converter=f"python {sys.version_info.major}.{sys.version_info.minor} ast + isolated run")
