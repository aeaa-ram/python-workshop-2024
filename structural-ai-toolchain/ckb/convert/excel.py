"""Excel workbooks -> machine-readable statements.

A calculation sheet has no variable names, only cells.  The converter

1. parses every formula into an expression tree and re-evaluates it from
   the values Excel cached in the file (so a formula that was not understood
   is detected, cell by cell);
2. gives each cell a name by reading the sheet the way an engineer does:
   the text to the left of a value is its label (``VRd.c (kN/m)``), an
   optional second text cell is its symbol (``Eff. depth | d | 342.5``), the
   unit is in brackets or in the next cell, the text above a column is the
   load case, and label-column text without a value is a heading;
3. keeps numbers exactly as the sheet has them and records the unit, so the
   conversion to consistent units is a separate, visible step.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..ir import SourceDocument, Statement, file_sha256, recompute
from ..notation import looks_like_symbol, split_label
from .excel_formula import FormulaError, _col_index, col_letter, parse_formula
from .python_src import ConversionError, find_clause

_MAX_SKIP_EMPTY = 2      # empty cells allowed between a value and its label
_MAX_SCAN_LEFT = 60
_MAX_SCAN_UP = 80


class _Sheet:
    def __init__(self, index: int, ws_f, ws_v):
        self.index = index
        self.title = ws_f.title
        self.formula: dict[tuple[int, int], str] = {}
        self.const: dict[tuple[int, int], object] = {}
        self.cached: dict[tuple[int, int], object] = {}
        for row in ws_f.iter_rows():
            for c in row:
                v = c.value
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                key = (c.row, c.column)
                if isinstance(v, str) and v.startswith("="):
                    self.formula[key] = v
                elif isinstance(v, (int, float, str)) and not isinstance(v, bool):
                    self.const[key] = v
                elif hasattr(v, "text") and isinstance(getattr(v, "text", None), str) and v.text.startswith("="):
                    self.formula[key] = v.text                    # array formula
        for row in ws_v.iter_rows():
            for c in row:
                if c.value is not None and (c.row, c.column) in self.formula:
                    self.cached[(c.row, c.column)] = c.value
        # a merged block shows its top-left value in every cell
        self.merged: dict[tuple[int, int], tuple[int, int]] = {}
        for rng in ws_f.merged_cells.ranges:
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    if (r, c) != (rng.min_row, rng.min_col):
                        self.merged[(r, c)] = (rng.min_row, rng.min_col)

    def text(self, r: int, c: int) -> str | None:
        """Text shown in a cell, or None when it is empty or a number."""
        key = self.merged.get((r, c), (r, c))
        v = self.const.get(key)
        if isinstance(v, str) and key not in self.formula:
            return v
        return None

    def is_value(self, r: int, c: int) -> bool:
        key = (r, c)
        return key in self.formula or isinstance(self.const.get(key), (int, float))

    def is_empty(self, r: int, c: int) -> bool:
        key = self.merged.get((r, c), (r, c))
        return key not in self.formula and key not in self.const


def _is_unit_cell(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t) <= 8 and U.is_unit(t) and t not in ("s", "t", "h", "d", "N", "m", "-") \
        or t in ("m", "N")


def _label_cells(sh: _Sheet, r: int, c: int) -> tuple[list[tuple[int, int, str]], bool]:
    """Text cells to the left of (r, c): nearest first.  Also says whether the
    scan had to pass over other values (i.e. this is one of several case columns)."""
    out, empties, passed_values = [], 0, False
    cc = c - 1
    while cc >= 1 and c - cc <= _MAX_SCAN_LEFT:
        t = sh.text(r, cc)
        if t is not None and t.strip():
            out.append((r, cc, t))
            # an adjacent second text cell (description | symbol | value)
            t2 = sh.text(r, cc - 1) if cc > 1 else None
            if t2 is not None and t2.strip():
                out.append((r, cc - 1, t2))
            return out, passed_values
        if sh.is_value(r, cc):
            passed_values, empties = True, 0
        elif sh.is_empty(r, cc):
            empties += 1
            if empties > _MAX_SKIP_EMPTY and not passed_values:
                break
            if empties > 6:
                break
        cc -= 1
    return out, passed_values


def _describe(sh: _Sheet, r: int, c: int) -> dict:
    """Name, label, unit, section and case of the value at (r, c)."""
    cells, _ = _label_cells(sh, r, c)
    label_row = r
    if not cells and r > 1:
        # the value sits one row below its label (label row holds a note)
        above = sh.text(r - 1, c)
        if above is not None or sh.is_empty(r - 1, c):
            cells, _ = _label_cells(sh, r - 1, c)
            label_row = r - 1
            if cells and sh.is_value(r - 1, c):
                cells = []
    info = {"name": "", "label": "", "unit": "", "desc": "", "label_col": None}
    if cells:
        texts = [t for _, _, t in cells]
        info["label_col"] = cells[-1][1]
        nearest = texts[0]
        if len(texts) == 2 and _is_unit_cell(nearest):
            info["unit"] = U.parse_unit(nearest.strip()).text
            texts = texts[1:]
            nearest = texts[0]
        if len(texts) == 2:
            sym, unit, _ = split_label(nearest)
            desc, unit2, extra = split_label(texts[1])
            info["name"] = sym
            info["label"] = " ".join(texts[1].split())
            info["unit"] = info["unit"] or unit or unit2
            info["desc"] = extra
        else:
            sym, unit, extra = split_label(nearest)
            info["label"] = " ".join(nearest.split())
            info["unit"] = info["unit"] or unit
            info["desc"] = extra
            info["name"] = sym
    # a unit in the cell to the right of the value
    if not info["unit"]:
        right = sh.text(r, c + 1)
        if right is not None and _is_unit_cell(right):
            info["unit"] = U.parse_unit(right.strip()).text
    # a note held in the value's own column on the label row (e.g. "B16/200")
    if label_row != r:
        note = sh.text(label_row, c)
        if note:
            info["desc"] = (info["desc"] + " " if info["desc"] else "") + " ".join(note.split())

    # headings: text in the label column, above, on rows without a value here
    heads, clause_head = [], ""
    lc = info["label_col"]
    if lc is not None:
        rr = label_row - 1
        while rr >= 1 and label_row - rr <= _MAX_SCAN_UP and len(heads) < 2:
            t = sh.text(rr, lc)
            if t is not None and t.strip() and sh.is_empty(rr, c) and not any(
                    not sh.is_empty(rr, k) for k in range(lc + 1, c)):
                t = " ".join(t.split())
                if len(t) <= 90:
                    if not heads or find_clause(t):
                        heads.append(t)
                    if not clause_head and find_clause(t):
                        clause_head = find_clause(t)
            rr -= 1
        if not clause_head:
            while rr >= 1 and label_row - rr <= _MAX_SCAN_UP:
                t = sh.text(rr, lc)
                if t and find_clause(t) and sh.is_empty(rr, c):
                    clause_head = find_clause(t)
                    break
                rr -= 1
    info["section"] = [sh.title.strip()] + list(reversed(heads[:1]))
    info["clause"] = find_clause(info["label"]) or clause_head

    # case: header text above the value column (rows whose label column is empty)
    case, rr = [], r - 1
    while rr >= 1 and r - rr <= _MAX_SCAN_UP:
        t = sh.text(rr, c)
        if t is not None and t.strip():
            has_label = lc is not None and sh.text(rr, lc) is not None and lc != c
            if not has_label:
                case.insert(0, " ".join(t.split()))
                if len(case) == 2:
                    break
            elif case:
                break
        elif case and sh.is_empty(rr, c):
            break
        rr -= 1
    info["case"] = " / ".join(x for x in case if len(x) <= 80)
    return info


def convert_excel(path: Path) -> SourceDocument:
    path = Path(path)
    try:
        import openpyxl
    except ImportError as exc:                                   # pragma: no cover
        raise ConversionError("openpyxl is not installed") from exc
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb_f = openpyxl.load_workbook(path, data_only=False)
            wb_v = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:                                     # noqa: BLE001
        raise ConversionError(f"workbook cannot be opened: {exc}") from exc

    doc = SourceDocument(name=path.name, kind="excel", sha256=file_sha256(path),
                         converter=f"openpyxl {openpyxl.__version__} + formula parser")
    sheets: list[_Sheet] = []
    for i, ws in enumerate(wb_f.worksheets, 1):
        sheets.append(_Sheet(i, ws, wb_v[ws.title]))
    by_title = {s.title: s for s in sheets}
    doc.meta["sheets"] = [{"index": s.index, "title": s.title, "formulas": len(s.formula)} for s in sheets]
    doc.meta["units"] = "declared"

    def sid(sh: _Sheet, r: int, c: int) -> str:
        return f"{sh.index}!{col_letter(c)}{r}"

    # ---- pass 1: parse formulas, find which constants they use -------------
    trees: dict[str, X.Node] = {}
    errors: dict[str, str] = {}
    used_consts: set[tuple[int, int, int]] = set()

    for sh in sheets:
        for (r, c), text in sh.formula.items():
            def ref(sheet_name, cell, _sh=sh):
                target = _sh if sheet_name is None else by_title.get(sheet_name)
                if target is None:
                    raise FormulaError(f"sheet {sheet_name!r} not found")
                m = re.fullmatch(r"([A-Z]+)(\d+)", cell)
                rr, cc = int(m.group(2)), _col_index(m.group(1))
                rr, cc = target.merged.get((rr, cc), (rr, cc))
                if (rr, cc) in target.formula:
                    return X.Sym(sid(target, rr, cc))
                if (rr, cc) in target.const:
                    used_consts.add((target.index, rr, cc))
                    return X.Sym(sid(target, rr, cc))
                return None                                     # empty cell counts as 0

            try:
                trees[sid(sh, r, c)] = parse_formula(text, ref)
            except X.ExprError as exc:
                errors[sid(sh, r, c)] = str(exc)

    # ---- pass 2: statements -------------------------------------------------
    cells = []
    for sh in sheets:
        for (r, c) in sh.formula:
            cells.append((sh, r, c))
        for (r, c), v in sh.const.items():
            if (sh.index, r, c) in used_consts:
                cells.append((sh, r, c))
    statements: dict[str, Statement] = {}
    for sh, r, c in cells:
        key = sid(sh, r, c)
        info = _describe(sh, r, c)
        name = info["name"]
        st = Statement(id=key, name=name or info["label"] or f"{col_letter(c)}{r}",
                       label=info["label"] + (f" ({info['desc']})" if info["desc"] else ""),
                       unit=info["unit"], clause=info["clause"], section=info["section"],
                       case=info["case"], group=f"{sh.index}:{col_letter(c)}",
                       loc=f"sheet {sh.index} '{sh.title.strip()}' cell {col_letter(c)}{r}")
        if (r, c) in sh.formula:
            st.raw = sh.formula[(r, c)]
            st.kind = "calc"
            cached = sh.cached.get((r, c))
            if isinstance(cached, bool):
                cached = float(cached)
            if isinstance(cached, (int, float, str)):
                st.value = cached
            if key in trees:
                st.expr = trees[key]
                if not X.symbols(st.expr):
                    st.kind = "input"            # a number typed as arithmetic: =0.95*1.45
            else:
                st.note = f"formula not converted: {errors[key]}"
                doc.issues.append(f"{st.loc}: {errors[key]}")
        else:
            v = sh.const[(r, c)]
            st.kind = "input"
            st.value = v
            st.raw = repr(v) if isinstance(v, str) else str(v)
            st.expr = X.Str(v) if isinstance(v, str) else X.Num(v, text=st.raw)
        statements[key] = st

    # ---- order: dependencies first, otherwise down the columns --------------
    order: list[str] = []
    state: dict[str, int] = {}

    def pos(k: str):
        s, cell = k.split("!")
        m = re.fullmatch(r"([A-Z]+)(\d+)", cell)
        return int(s), _col_index(m.group(1)), int(m.group(2))

    def visit(k: str):
        stack = [(k, iter(sorted((d for d in statements[k].refs if d in statements), key=pos)))]
        state[k] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                order.append(node)
                stack.pop()
            elif state.get(nxt, 0) == 0:
                state[nxt] = 1
                stack.append((nxt, iter(sorted((d for d in statements[nxt].refs if d in statements), key=pos))))
            elif state[nxt] == 1:
                doc.issues.append(f"circular reference through {nxt}")

    for k in sorted(statements, key=pos):
        if state.get(k, 0) == 0:
            visit(k)
    doc.statements = [statements[k] for k in order]

    has_cached = any(s.value is not None for s in doc.statements if s.kind == "calc" and s.expr is not None)
    if not has_cached and any(s.kind == "calc" for s in doc.statements):
        doc.issues.append("the workbook holds no calculated values (saved without calculating); "
                          "values were computed here and could not be compared with Excel's")
    recompute(doc, chained=not has_cached)
    if not has_cached:
        for s in doc.statements:
            if s.value is None and s.recomputed is not None:
                s.value = s.recomputed
    doc.python = to_python(doc)
    return doc


def to_python(doc: SourceDocument) -> str:
    """The workbook re-expressed as a plain Python script (one line per cell)."""
    from ..notation import ident
    names: dict[str, str] = {}
    for st in doc.statements:
        cell = st.id.replace("!", "_")
        base = ident(st.name) if looks_like_symbol(st.name) else ""
        names[st.id] = f"{base}_s{cell}" if base else f"cell_s{cell}"
    out = [f'"""Converted from {doc.name!r} - one assignment per spreadsheet cell.',
           "Numbers are in the units of the sheet (see the comment on each line).", '"""',
           "from math import sqrt, pi, sin, cos, tan, asin, acos, atan, exp, radians, degrees, floor, ceil",
           "from math import log as ln, log10", "", ""]
    last_group = None
    for st in doc.statements:
        if st.group != last_group:
            out.append("")
            out.append(f"# --- {' / '.join(st.section)}" + (f" - {st.case}" if st.case else "")
                       + f" (column {st.group.split(':')[-1]}) ---")
            last_group = st.group
        if st.expr is None:
            rhs = repr(st.value)
        else:
            rhs = X.to_python(st.expr, lambda s: names.get(s, s))
        shown = st.value if st.value is not None else st.recomputed
        tail = f"  # {st.label}" if st.label else "  #"
        if st.unit:
            tail += f" [{st.unit}]"
        if st.kind == "calc" and shown is not None:
            tail += f" -> {U.fmt(shown, 6) if not isinstance(shown, str) else repr(shown)}"
        out.append(f"{names[st.id]} = {rhs}{tail}")
    return "\n".join(out) + "\n"
