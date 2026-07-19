"""Mathcad Prime (.mcdx) parser — a real, best-effort implementation.

A .mcdx is an OPC (zip) container. The math lives in
``mathcad/worksheet.xml`` as Mathcad's ``ml:`` markup:

    <region top=".." left="..">
      <math><ml:define><ml:id>gamma_V</ml:id><ml:real>1.25</ml:real></ml:define></math>
    <region ..><math><ml:eval><ml:apply><ml:div/>..</ml:apply></ml:eval></math>

This parser walks the regions in worksheet order (top, then left) and:
- ``ml:define`` -> an input (numeric literal) or a derived formula
  (an operator tree that references other variables), by recursively
  translating the ``ml:apply`` operator tree into our expression syntax;
- ``ml:eval`` containing a comparison (``ml:lessThan`` / ``ml:greaterThan``)
  -> a check;
- text regions -> narrative (section intros / descriptions), pulled from
  the referenced XAML FlowDocument packages.

Units are display-only in our model, so unit identifiers are recorded but
stripped from expressions (Mathcad's automatic unit algebra is not
reproduced — a value-mismatch, matrix, or unresolved construct becomes a
human-in-the-loop clarification rather than a silent wrong number).

Consistent with the AI Grinder: anything that cannot be translated
faithfully is reported as a Clarification, never fabricated.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from src.ingestion.base import BaseParser
from src.models.calculation import Clarification, ParsedTool, ParsedVariable
from src.models.naming import symbol_to_latex  # noqa: F401 (kept for parity)

ML = "{http://schemas.mathsoft.com/math50}"          # ml: namespace
WS = "{http://schemas.mathsoft.com/worksheet50}"     # worksheet namespace

# greek unicode -> ascii name (identifiers must be valid Python)
_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ϴ": "theta", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho",
    "σ": "sigma", "τ": "tau", "φ": "phi", "ϕ": "phi", "χ": "chi", "ψ": "psi",
    "ω": "omega", "Δ": "Delta", "Σ": "Sigma", "Ω": "Omega", "Φ": "Phi",
    "Ø": "phi", "ø": "phi",
}


class _Untranslatable(Exception):
    """Raised deep in the tree when a construct can't be translated."""


class MathcadParser(BaseParser):
    extensions = (".mcdx",)

    def parse(self, path: Path) -> ParsedTool:
        path = Path(path)
        tool = ParsedTool(
            title=path.stem.replace("_", " ").strip(),
            source_path=str(path),
            source_format="mcdx",
            interpreter="mcdx",
            unit_aware=True,   # Mathcad formulas carry units, no manual conv.
        )
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if not any("worksheet.xml" in n for n in names):
                    tool.warnings.append(
                        "Not a Mathcad Prime worksheet (no worksheet.xml); "
                        "may be a legacy binary .mcd/.xmcd — manual review.")
                    return tool
                xml = zf.read("mathcad/worksheet.xml")
                texts = _extract_text_regions(zf, names)
        except (zipfile.BadZipFile, FileNotFoundError, KeyError) as exc:
            tool.warnings.append(f"Could not open .mcdx container: {exc}")
            return tool

        self._walk(xml, texts, tool)
        if not tool.variables and not tool.checks:
            tool.warnings.append(
                "No math regions could be translated — the worksheet may be "
                "mostly text/graphics or use unsupported constructs.")
        return tool

    # -------------------------------------------------------------- #
    def _walk(self, xml: bytes, texts: dict, tool: ParsedTool) -> None:
        root = ET.fromstring(xml)
        regions = []
        for region in root.iter(f"{WS}region"):
            top = float(region.get("top", 0) or 0)
            left = float(region.get("left", 0) or 0)
            regions.append((top, left, region))
        regions.sort(key=lambda r: (round(r[0]), round(r[1])))

        used: set[str] = set()
        title_set = False
        pending_desc = ""       # text label to attach to the next math region
        for top, left, region in regions:
            tref = region.find(f"{WS}text")
            if tref is not None:
                txt = _clean_text(texts.get(tref.get("item-idref", ""), ""))
                if not txt:
                    continue
                if not title_set:
                    tool.title, ref = _split_title_ref(txt)
                    tool.reference = ref
                    title_set = True
                elif txt.lower().startswith("introduction"):
                    tool.description = _strip_prefix(txt, "introduction")
                elif len(txt) <= 80:
                    # a short label: parameter description or a heading
                    pending_desc = txt.rstrip(" :﻿")
                else:
                    if not tool.description:
                        tool.description = txt[:500]
                continue

            define = region.find(f".//{ML}define")
            if define is not None:
                self._handle_define(define, tool, used, pending_desc)
                pending_desc = ""
                continue
            ev = region.find(f".//{ML}eval")
            if ev is not None:
                self._handle_eval(ev, tool, used)
                pending_desc = ""

    def _handle_define(self, define, tool: ParsedTool, used: set,
                       description: str = "") -> None:
        children = list(define)
        if not children:
            return
        name = _ident_name(children[0])
        if not name:
            return
        name = _dedupe(name, used)
        value_node = children[1] if len(children) > 1 else None
        if value_node is None:
            return
        # matrix / vector input (e.g. D := [1420, 1720] mm — several load
        # cases or sizes). Take the first value as the governing scalar and
        # raise a clarification listing all of them, so downstream formulas
        # resolve for case 1 instead of failing.
        mat_vals, mat_unit = _matrix_values_and_unit(value_node)
        if mat_vals is not None and not _has_variable(value_node):
            tool.variables.append(ParsedVariable(
                name=name, value=mat_vals[0], unit=mat_unit, role="input",
                description=(description + f" (case 1 of {len(mat_vals)})").strip(),
                source_cell="mcdx"))
            if len(mat_vals) > 1:
                tool.clarifications.append(Clarification(
                    location=name, issue="multi-value-input",
                    question=(f"'{name}' is a vector {mat_vals} {mat_unit} "
                              f"({len(mat_vals)} load cases/sizes). Using the "
                              f"first ({mat_vals[0]}); confirm the governing "
                              "case or run a parametric study over all."),
                    options=[f"{v} {mat_unit}" for v in mat_vals],
                    context=str(mat_vals)))
            return
        # numeric literal (possibly with a unit) -> input
        literal, unit = _literal_and_unit(value_node)
        if literal is not None and not _has_variable(value_node):
            tool.variables.append(ParsedVariable(
                name=name, value=literal, unit=unit, role="input",
                description=description, source_cell="mcdx"))
            return
        # otherwise a formula -> derived
        try:
            expr = _translate(value_node)
            unit = unit or _result_unit(value_node)
            tool.variables.append(ParsedVariable(
                name=name, expression=expr, unit=unit, role="derived",
                description=description, source_cell="mcdx",
                source_formula=expr))
        except _Untranslatable as exc:
            tool.clarifications.append(Clarification(
                location=name, issue="mathcad-construct",
                question=(f"Definition of '{name}' uses a Mathcad construct "
                          f"that could not be translated ({exc}). Please "
                          "provide the intended formula."),
                context=str(exc)))

    def _handle_eval(self, ev, tool: ParsedTool, used: set) -> None:
        # only comparisons are meaningful to us as checks
        for op, sym in ((f"{ML}lessThan", "<="), (f"{ML}greaterThan", ">=")):
            cmp = ev.find(f".//{op}")
            if cmp is None:
                continue
            apply_node = _parent_apply(ev, op)
            if apply_node is None:
                continue
            operands = [c for c in apply_node if not c.tag.endswith("}"+op.split('}')[1])]
            operands = [c for c in apply_node if c.tag != op]
            if len(operands) < 2:
                continue
            try:
                lhs = _translate(operands[0])
                rhs = _translate(operands[1])
                tool.checks.append(f"{lhs} {sym} {rhs}")
            except _Untranslatable:
                pass
            return


# ------------------------------------------------------------------ #
# ml: operator-tree translation
# ------------------------------------------------------------------ #
def _translate(node) -> str:
    tag = _local(node.tag)
    if tag == "real":
        return (node.text or "0").strip()
    if tag == "id":
        nm = _ident_name(node)
        if nm == "pi" or (node.get("labels") == "CONSTANT" and nm in ("pi",)):
            return "pi"
        if node.get("labels") == "UNIT":
            return "1"  # units stripped from the numeric expression
        return nm
    if tag == "str":
        raise _Untranslatable("string literal")
    if tag in ("matrix", "sequence"):
        raise _Untranslatable("matrix/vector")
    if tag == "placeholder":
        raise _Untranslatable("empty placeholder")
    if tag == "parens":
        return f"({_translate(node[0])})"
    if tag == "eval":
        # inline evaluation ("expr = result"): translate the expression part
        return _translate(node[0])
    if tag == "apply":
        return _translate_apply(node)
    if tag in ("unitOverride", "scale"):
        # value carrying a display unit -> translate the value part only
        return _translate(node[0])
    # unknown leaf
    raise _Untranslatable(f"<{tag}>")


def _translate_apply(node) -> str:
    kids = list(node)
    if not kids:
        raise _Untranslatable("empty apply")
    op = _local(kids[0].tag)
    args = kids[1:]

    def t(i):
        return _translate(args[i])

    if op == "mult":
        return "*".join(f"{t(i)}" for i in range(len(args)))
    if op == "div":
        return f"({t(0)})/({t(1)})"
    if op == "plus":
        return "+".join(t(i) for i in range(len(args)))
    if op == "minus":
        if len(args) == 1:
            return f"-({t(0)})"
        return f"({t(0)})-({t(1)})"
    if op == "neg":
        return f"-({t(0)})"
    if op == "pow":
        return f"({t(0)})**({t(1)})"
    if op == "nthRoot":
        # nthRoot(index, radicand) -> radicand**(1/index)
        if len(args) == 2:
            return f"({t(1)})**(1/({t(0)}))"
        return f"sqrt({t(0)})"
    if op == "sqrt":
        return f"sqrt({t(0)})"
    if op == "absval":
        return f"abs({t(0)})"
    if op in ("parens",):
        return f"({t(0)})"
    if op in ("scale", "unitOverride"):
        return t(0)
    # function application: <apply><ml:id>min</ml:id><ml:sequence>a,b</...>
    if op == "id":
        fname = _slug("".join(kids[0].itertext())).lower()
        fargs = _flatten_args(args)
        _FUNC = {"min": "min", "max": "max", "abs": "abs", "sqrt": "sqrt",
                 "round": "", "floor": "floor", "ceil": "ceiling",
                 "trunc": "", "sin": "sin", "cos": "cos", "tan": "tan"}
        if fname in _FUNC:
            inner = ",".join(_translate(a) for a in fargs)
            py = _FUNC[fname]
            return f"({inner})" if py == "" else f"{py}({inner})"
    raise _Untranslatable(f"operator <{op}>")


def _flatten_args(args):
    """Expand <ml:sequence> argument lists into individual operands."""
    out = []
    for a in args:
        if _local(a.tag) == "sequence":
            out.extend(list(a))
        else:
            out.append(a)
    return out


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ident_name(node) -> str:
    """Extract an identifier name from an <ml:id>, resolving subscripts and
    transliterating greek so the result is a valid Python identifier."""
    if node is None:
        return ""
    if _local(node.tag) != "id":
        # sometimes the LHS is wrapped; search for the first id
        inner = node.find(f".//{ML}id")
        if inner is not None:
            node = inner
        else:
            return ""
    base = "".join(node.itertext())
    # <pw:Subscript>V</pw:Subscript> becomes _V; detect via child tags
    sub = ""
    for el in node.iter():
        if _local(el.tag) == "Subscript" and el.text:
            sub = el.text
    # build "base_sub"
    if sub:
        # base text includes the subscript text (itertext); strip trailing sub
        if base.endswith(sub):
            base = base[: -len(sub)]
        name = f"{base}_{sub}"
    else:
        name = base
    return _slug(name)


def _slug(text: str) -> str:
    for uni, ascii_name in _GREEK.items():
        text = text.replace(uni, ascii_name)
    text = text.strip()
    # keep underscores; collapse other separators
    text = re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")
    if not text:
        return ""
    if text[0].isdigit():
        text = "v_" + text
    return text


def _dedupe(name: str, used: set) -> str:
    out, i = name, 2
    while out in used:
        out = f"{name}_{i}"
        i += 1
    used.add(out)
    return out


def _literal_and_unit(node):
    """(number, unit) if the node is a real, or a real*unit product."""
    tag = _local(node.tag)
    if tag == "real":
        try:
            return float(node.text), ""
        except (TypeError, ValueError):
            return None, ""
    if tag in ("scale", "unitOverride") and len(node):
        return _literal_and_unit(node[0])
    if tag == "apply":
        kids = list(node)
        if kids and _local(kids[0].tag) == "mult":
            reals = [k for k in kids[1:] if _local(k.tag) == "real"]
            units = [k for k in kids[1:]
                     if _local(k.tag) == "id" and k.get("labels") == "UNIT"]
            others = [k for k in kids[1:]
                      if _local(k.tag) not in ("real",)
                      and not (_local(k.tag) == "id"
                               and k.get("labels") == "UNIT")]
            if len(reals) == 1 and not others:
                unit = "".join(u.text or "" for u in units)
                try:
                    return float(reals[0].text), unit
                except (TypeError, ValueError):
                    return None, ""
    return None, ""


def _matrix_values_and_unit(node):
    """(list-of-floats, unit) if the node is a matrix/vector of reals
    (optionally scaled by a unit / transposed), else (None, '')."""
    unit = ""
    n = node
    # unwrap scale (value * unit) and transpose wrappers
    for _ in range(4):
        tag = _local(n.tag)
        if tag in ("scale", "unitOverride") and len(n):
            # a UNIT id sibling gives the unit
            for c in n:
                if _local(c.tag) == "id" and c.get("labels") == "UNIT":
                    unit = "".join(c.itertext()).strip()
            n = n[0]
            continue
        if tag == "apply" and len(n) >= 2 and _local(n[0].tag) in (
                "transpose", "scale"):
            if _local(n[0].tag) == "scale":
                for c in n[1:]:
                    if _local(c.tag) == "id" and c.get("labels") == "UNIT":
                        unit = "".join(c.itertext()).strip()
            n = n[1]
            continue
        # matrix multiplied by a scalar/unit: dig into the mult operand that
        # holds the matrix (e.g. M_Ed := [4323.8, 7439.8] kNm).
        if tag == "apply" and len(n) >= 2 and _local(n[0].tag) == "mult":
            matrix_operand = None
            for c in n[1:]:
                if any(_local(e.tag) == "matrix" for e in c.iter()):
                    matrix_operand = c
                elif _local(c.tag) == "id" and c.get("labels") == "UNIT":
                    unit = "".join(c.itertext()).strip()
            if matrix_operand is not None:
                n = matrix_operand
                continue
        break
    if _local(n.tag) == "matrix":
        vals = []
        for r in n.iter(f"{ML}real"):
            try:
                vals.append(float(r.text))
            except (TypeError, ValueError):
                return None, ""
        if vals:
            return vals, unit
    return None, ""


def _has_variable(node) -> bool:
    for el in node.iter(f"{ML}id"):
        if el.get("labels") == "VARIABLE":
            return True
    return False


def _result_unit(node) -> str:
    """Display unit of a result, e.g. 'cm^2' — keep the exponent (a
    <ml:pow><ml:id>cm</ml:id><ml:real>2</ml:real></ml:pow> means cm^2)."""
    uo = node.find(f".//{ML}unitOverride")
    if uo is None:
        return ""
    pow_node = uo.find(f".//{ML}pow")
    if pow_node is not None and len(pow_node) == 2:
        base = "".join(pow_node[0].itertext()).strip()
        exp = "".join(pow_node[1].itertext()).strip()
        return f"{base}^{exp}" if base and exp else base
    return "".join(uo.itertext()).strip()


def _parent_apply(root, op_tag):
    for apply_node in root.iter(f"{ML}apply"):
        kids = list(apply_node)
        if kids and kids[0].tag == op_tag:
            return apply_node
    return None


# ------------------------------------------------------------------ #
# text region extraction (XAML FlowDocument packages)
# ------------------------------------------------------------------ #
def _extract_text_regions(zf: zipfile.ZipFile, names: list) -> dict:
    """Map text region item-idref -> plain text, by resolving the rels and
    unzipping each referenced XamlPackage."""
    out: dict[str, str] = {}
    rels = {}
    try:
        rel_xml = zf.read("mathcad/_rels/worksheet.xml.rels").decode("utf-8", "replace")
        # attribute order varies (Target before Id), so parse per element
        for rel in re.findall(r"<Relationship\b[^>]*/>", rel_xml):
            rid = re.search(r'Id="([^"]+)"', rel)
            target = re.search(r'Target="([^"]+)"', rel)
            if rid and target:
                rels[rid.group(1)] = target.group(1)
    except KeyError:
        pass
    for rid, target in rels.items():
        if "XamlPackage" not in target:
            continue
        member = "mathcad/" + target.lstrip("/") if not target.startswith("mathcad") \
            else target
        member = member.replace("mathcad/mathcad/", "mathcad/")
        try:
            data = zf.read(member)
            out[rid] = _text_from_xaml_package(data)
        except KeyError:
            continue
    return out


def _text_from_xaml_package(data: bytes) -> str:
    """A XamlPackage is itself a zip of XAML; pull visible Run text out."""
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            parts = []
            for nm in inner.namelist():
                if nm.lower().endswith((".xaml", ".xml")) or "/" not in nm:
                    try:
                        xaml = inner.read(nm).decode("utf-8", "replace")
                    except Exception:
                        continue
                    parts.append(_runs_from_xaml(xaml))
            return " ".join(p for p in parts if p).strip()
    except zipfile.BadZipFile:
        return _runs_from_xaml(data.decode("utf-8", "replace"))


def _runs_from_xaml(xaml: str) -> str:
    runs = re.findall(r'Text="([^"]*)"', xaml)
    if runs:
        return re.sub(r"\s+", " ", " ".join(runs)).strip()
    # fall back to element text content
    text = re.sub(r"<[^>]+>", " ", xaml)
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(text: str) -> str:
    return text.replace("﻿", "").strip()


def _split_title_ref(text: str) -> tuple[str, str]:
    """Split a heading like 'Appendix D.2.1 - ... . Acc. to EN 1994-1-1'
    into (title, code reference)."""
    m = re.search(r"(?:Acc\.?\s*to\s*|according to\s*)(EN[\s\d\-:.]+)", text, re.I)
    ref = ""
    if m:
        ref = _clean_code_ref(m.group(1))
        text = text[: m.start()].strip(" .-")
    else:
        m2 = re.search(r"(EN\s?\d{3,4}[\s\d\-:.]*)", text)
        if m2:
            ref = _clean_code_ref(m2.group(1))
    return text.strip(" .-")[:120], ref


def _clean_code_ref(ref: str) -> str:
    """'EN 199 4 -1-1' -> 'EN 1994-1-1' (XAML often splits the digits)."""
    ref = re.sub(r"\s+", " ", ref).strip(" .")
    ref = re.sub(r"(?<=\d)\s+(?=\d)", "", ref)     # join split digits
    ref = re.sub(r"\s*-\s*", "-", ref)             # tighten dashes
    return ref


def _strip_prefix(text: str, prefix: str) -> str:
    out = re.sub(rf"^{prefix}\s*[:\-–]?\s*", "", text, flags=re.I).strip()
    return out[:600]
