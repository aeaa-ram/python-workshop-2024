"""Mathcad Prime export: a calculation object as a live .mcdx worksheet.

Every input is defined with its unit (``d := 450 mm``) and every step is a Mathcad
definition with its result shown (``k := min(1 + √(200 mm / d), 2) = 1.67``), so the
worksheet recalculates in Mathcad like one written by hand.

Mathcad checks units, and several code expressions are empirical: in
``k = 1 + √(200/d)`` the number 200 is in millimetres, in ``v_min = 0.035 k^1.5 f_ck^0.5``
the strength is in MPa.  ``with_units`` therefore works out, for every formula, where
a unit must be attached to a number (200 mm), where a quantity must be made
dimensionless (f_ck/MPa) and where the result needs its unit back (·MPa), so that the
worksheet gives the same numbers as the knowledge base.

The written file is read back with ``mcad2py`` and evaluated before it is handed out
(``verify``).  It follows the structure of worksheets saved by Mathcad Prime 9; it has
not been opened in Mathcad itself in this environment.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import uuid
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape

from .. import expr as X
from .. import units as U
from ..kb.objects import KnowledgeBase
from ..notation import parts
from .calc import starting_values
from .style import Style

Dims = tuple

NAMED = {(1, -2): "MPa", (1, 0): "N", (0, 1): "mm", (0, 2): "mm^2", (0, 3): "mm^3", (0, 4): "mm^4",
         (1, 1): "N*mm", (1, -1): "N/mm", (1, -3): "N/mm^3", (0, -1): "1/mm"}


def _dims(unit: str) -> Dims:
    d = U.parse_unit(unit).dims
    return (Fraction(d[0]), Fraction(d[1]))


ZERO: Dims = (Fraction(0), Fraction(0))


def _add(a, b, k=1):
    return (a[0] + k * b[0], a[1] + k * b[1])


def _mul(a, p):
    return (a[0] * p, a[1] * p)


def _integral(d) -> bool:
    return d is not None and all(x.denominator == 1 for x in d)


def _unit_node(d: Dims) -> X.Node | None:
    name = NAMED.get((int(d[0]), int(d[1]))) if _integral(d) else None
    return None if name is None else _unit_tree(name)


def _unit_tree(text: str) -> X.Node:
    """'N/mm^2' or 'kN*m' -> a tree of unit literals."""
    text = text.replace("·", "*").replace("²", "^2").replace("³", "^3").replace("⁴", "^4")
    if text == "kNm":
        text = "kN*m"
    num, _, den = text.partition("/")

    def side(s):
        out = None
        for tok in [t for t in s.split("*") if t]:
            m = re.fullmatch(r"(.+?)\^(\d+)", tok)
            node = X.Unit(m.group(1)) if m else X.Unit(tok)
            if m:
                node = X.Bin("**", node, X.Num(int(m.group(2)), m.group(2)))
            out = node if out is None else X.Bin("*", out, node)
        return out

    top = side(num) if num not in ("", "1") else X.Num(1, "1")
    return X.Bin("/", top, side(den)) if den else top


class _Fitter:
    """Places units so that a canonical-unit formula is dimensionally consistent."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def sym_dims(self, s: str) -> Dims:
        return _dims(self.kb.unit(s))

    def natural(self, n: X.Node):
        """Dimensions of a subtree, None for a plain number, 'mixed' if inconsistent."""
        if isinstance(n, X.Num):
            return None
        if isinstance(n, X.Sym):
            return self.sym_dims(n.name)
        if isinstance(n, X.Unit):
            return _dims(n.name)
        if isinstance(n, X.Neg):
            return self.natural(n.arg)
        if isinstance(n, X.Bin) and n.op in "+-":
            a, b = self.natural(n.left), self.natural(n.right)
            if a is None:
                return b
            if b is None or a == b:
                return a
            return "mixed"
        if isinstance(n, X.Bin) and n.op in "*/":
            a, b = self.natural(n.left), self.natural(n.right)
            if "mixed" in (a, b):
                return "mixed"
            a, b = a or ZERO, b or ZERO
            out = _add(a, b, 1 if n.op == "*" else -1)
            return None if (out == ZERO and self.natural(n.left) is None and self.natural(n.right) is None) else out
        if isinstance(n, X.Bin) and n.op == "**":
            if not isinstance(n.right, X.Num):
                return ZERO
            a = self.natural(n.left)
            if a is None or a == "mixed":
                return a
            return _mul(a, Fraction(n.right.value).limit_denominator(1000))
        if isinstance(n, X.Call):
            if n.fn == "sqrt":
                a = self.natural(n.args[0])
                return a if a in (None, "mixed") else _mul(a, Fraction(1, 2))
            if n.fn in ("max", "min", "abs", "round", "floor", "ceil"):
                for a in n.args:
                    d = self.natural(a)
                    if d is not None:
                        return d
                return None
            return ZERO
        if isinstance(n, X.If):
            return self.natural(n.then) if self.natural(n.then) is not None else self.natural(n.other)
        return ZERO

    def fit(self, n: X.Node, want: Dims) -> X.Node:
        if isinstance(n, X.Num):
            u = _unit_node(want) if want != ZERO else None
            return n if u is None else X.Bin("*", n, u)
        if isinstance(n, X.Sym):
            d = self.sym_dims(n.name)
            if d == want:
                return n
            return self._convert(n, d, want)
        if isinstance(n, X.Str):
            return n
        if isinstance(n, X.Neg):
            return X.Neg(self.fit(n.arg, want))
        if isinstance(n, X.Bin) and n.op in "+-":
            return X.Bin(n.op, self.fit(n.left, want), self.fit(n.right, want))
        if isinstance(n, X.Bin) and n.op in "*/":
            return self._product(n, want)
        if isinstance(n, X.Bin) and n.op == "**":
            return self._power(n.left, n.right, want)
        if isinstance(n, X.Call):
            if n.fn == "sqrt":
                return self._power(n.args[0], X.Num(0.5, "0.5"), want, sqrt=True)
            if n.fn in ("max", "min", "abs", "round", "floor", "ceil"):
                return X.Call(n.fn, tuple(self.fit(a, want) for a in n.args))
            if n.fn == "pi":
                return n if want == ZERO else self._convert(n, ZERO, want)
            node = X.Call(n.fn, tuple(self.fit(a, ZERO) for a in n.args))
            return node if want == ZERO else self._convert(node, ZERO, want)
        if isinstance(n, X.If):
            return X.If(self.fit_cond(n.cond), self.fit(n.then, want), self.fit(n.other, want))
        return n

    def fit_cond(self, n: X.Node) -> X.Node:
        if isinstance(n, X.Cmp):
            d = self.natural(n.left)
            if d is None or d == "mixed":
                d = self.natural(n.right)
            d = ZERO if d in (None, "mixed") else d
            return X.Cmp(n.op, self.fit(n.left, d), self.fit(n.right, d))
        if isinstance(n, X.Logic):
            return X.Logic(n.op, tuple(self.fit_cond(a) for a in n.args))
        return n

    def _convert(self, node: X.Node, have: Dims, want: Dims) -> X.Node:
        """node / unit(have) * unit(want)."""
        out = node
        if have != ZERO:
            u = _unit_node(have)
            out = X.Bin("/", out, u) if u is not None else out
        if want != ZERO:
            u = _unit_node(want)
            out = X.Bin("*", out, u) if u is not None else out
        return out

    def _power(self, base: X.Node, exp: X.Node, want: Dims, sqrt: bool = False) -> X.Node:
        p = Fraction(exp.value).limit_denominator(1000) if isinstance(exp, X.Num) else None
        nb = self.natural(base)
        if p is not None and nb not in (None, "mixed") and _integral(_mul(nb, p)) and _mul(nb, p) == want:
            b = self.fit(base, nb)
            return X.Call("sqrt", (b,)) if sqrt else X.Bin("**", b, exp)
        if p is not None and p.denominator == 1 and _integral(_mul(want, 1 / p)):
            b = self.fit(base, _mul(want, 1 / p))
            return X.Call("sqrt", (b,)) if sqrt else X.Bin("**", b, exp)
        b = self.fit(base, ZERO)                       # empirical: the base must be a pure number
        node = X.Call("sqrt", (b,)) if sqrt else X.Bin("**", b, exp)
        return node if want == ZERO else self._convert(node, ZERO, want)

    def _product(self, n: X.Node, want: Dims) -> X.Node:
        """Fit a product, keeping its factors in the order they were written."""
        numer, denom = X.factors(n)
        flexible = lambda f: isinstance(f, (X.Num,)) or (isinstance(f, X.Bin) and f.op in "+-") or \
            isinstance(f, (X.Neg, X.If)) or (isinstance(f, X.Call) and f.fn in ("max", "min", "abs"))  # noqa: E731
        fitted: dict[int, X.Node] = {}
        total = ZERO
        for side, k in ((numer, 1), (denom, -1)):
            for f in side:
                if not flexible(f):
                    g, d = self._rigid(f)
                    fitted[id(f)] = g
                    total = _add(total, d, k)
        comps = [(f, 1) for f in numer if flexible(f) and not isinstance(f, X.Num)] + \
                [(f, -1) for f in denom if flexible(f) and not isinstance(f, X.Num)]
        extra_n, extra_d = [], []
        if len(comps) == 1 and _integral(_add(want, total, -1)):
            f, k = comps[0]
            fitted[id(f)] = self.fit(f, _mul(_add(want, total, -1), k))
            total = want
        else:
            for f, k in comps:
                d = self.natural(f)
                d = ZERO if d in (None, "mixed") else d
                fitted[id(f)] = self.fit(f, d)
                total = _add(total, d, k)
        diff = _add(want, total, -1)
        simple = ((1, -2), (0, 1), (1, 0), (0, 2))
        nums_n = [f for f in numer if isinstance(f, X.Num)]
        nums_d = [f for f in denom if isinstance(f, X.Num)]
        if diff != ZERO:
            if nums_n and diff in simple:
                fitted[id(nums_n[0])] = X.Bin("*", nums_n[0], _unit_node(diff))
            elif nums_d and _mul(diff, -1) in simple:
                fitted[id(nums_d[0])] = X.Bin("*", nums_d[0], _unit_node(_mul(diff, -1)))
            elif want == ZERO:
                for f in numer + denom:
                    if not isinstance(f, X.Num):
                        fitted[id(f)] = self._strip(fitted[id(f)])
            elif _unit_node(diff) is not None:
                extra_n.append(_unit_node(diff))
            elif _unit_node(_mul(diff, -1)) is not None:
                extra_d.append(_unit_node(_mul(diff, -1)))
        top = [fitted.get(id(f), f) for f in numer] + extra_n
        bottom = [fitted.get(id(f), f) for f in denom] + extra_d
        return X.product(top or [X.Num(1, "1")], bottom) if bottom else X.product(top)

    def _rigid(self, f: X.Node):
        """A factor fitted to its own dimensions (a fractional power of a unit becomes dimensionless)."""
        d = self.natural(f)
        if d in (None, "mixed") or not _integral(d):
            return self.fit(f, ZERO), ZERO
        return self.fit(f, d), d

    def _strip(self, g: X.Node) -> X.Node:
        d = self.natural(g)
        if d in (None, "mixed") or d == ZERO:
            return g
        u = _unit_node(d)
        return X.Bin("/", g, u) if u is not None else g


def with_units(kb: KnowledgeBase, oid: str) -> X.Node:
    """The object's formula with units placed for a units-aware worksheet."""
    return _Fitter(kb).fit(kb.objects[oid].tree, _dims(kb.unit(oid)))


# --------------------------------------------------------------------------
# math50 XML
# --------------------------------------------------------------------------
_SPAN = ('<Span xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
         'xmlns:pw="clr-namespace:Ptc.Wpf;assembly=Ptc.Core">{b}<pw:Subscript>{s}</pw:Subscript></Span>')
_FN = {"max": "max", "min": "min", "abs": "|x|", "sin": "sin", "cos": "cos", "tan": "tan", "cot": "cot",
       "asin": "asin", "acos": "acos", "atan": "atan", "exp": "exp", "ln": "ln", "log10": "log",
       "floor": "floor", "ceil": "ceil", "round": "round"}
_CMP = {"<": "lessThan", ">": "greaterThan", "<=": "lessOrEqual", ">=": "greaterOrEqual", "==": "equal",
        "!=": "notEqual"}
_UNIT_ID = {"°": "°", "deg": "°", "kNm": None}


def mathcad_names(kb: KnowledgeBase, ids) -> dict[str, tuple[str, str]]:
    """(base, subscript) per quantity, unique within the worksheet."""
    out, used = {}, set()
    for sid in ids:
        item = kb.item(sid)
        sym = item.symbol if item is not None else ""
        if sym and re.fullmatch(r"[^\s_{}−\-+*/()]+(_\{[^{}]*\})?", sym):
            m = re.fullmatch(r"([^_]+)(?:_\{([^}]*)\})?", sym)
            base, sub = m.group(1), m.group(2) or ""
        else:
            base, sub = parts(kb.var(sid) if item is not None else sid)
        sub = sub.replace(",", ".")
        name, n = (base, sub), 2
        while name in used:
            name, n = (base, (sub + "." if sub else "") + str(n)), n + 1
        used.add(name)
        out[sid] = name
    return out


def _id(base: str, sub: str, labels: str = "VARIABLE") -> str:
    body = _SPAN.format(b=escape(base), s=escape(sub)) if sub else escape(base)
    return f'<ml:id labels="{labels}" xml:space="preserve">{body}</ml:id>'


def to_xml(n: X.Node, names: dict) -> str:
    if isinstance(n, X.Num):
        v = n.value
        if v < 0:
            return f"<ml:apply><ml:neg />{to_xml(X.Num(-v), names)}</ml:apply>"
        return f"<ml:real>{X._fmt_num(v)}</ml:real>"
    if isinstance(n, X.Str):
        return f'<ml:str xml:space="preserve">{escape(n.value)}</ml:str>'
    if isinstance(n, X.Sym):
        b, s = names[n.name]
        return _id(b, s)
    if isinstance(n, X.Unit):
        return f'<ml:id labels="UNIT" xml:space="preserve">{escape(_UNIT_ID.get(n.name) or n.name)}</ml:id>'
    if isinstance(n, X.Neg):
        return f"<ml:apply><ml:neg />{to_xml(n.arg, names)}</ml:apply>"
    if isinstance(n, X.Bin):
        tag = {"+": "plus", "-": "minus", "*": "mult", "/": "div", "**": "pow"}[n.op]
        left, right = to_xml(n.left, names), to_xml(n.right, names)
        if n.op in "*/" and isinstance(n.left, X.Bin) and n.left.op in "+-":
            left = f"<ml:parens>{left}</ml:parens>"
        if n.op in "*/-" and isinstance(n.right, X.Bin) and n.right.op in "+-":
            right = f"<ml:parens>{right}</ml:parens>"
        if n.op == "**" and isinstance(n.left, X.Bin):
            left = f"<ml:parens>{left}</ml:parens>"
        return f"<ml:apply><ml:{tag} />{left}{right}</ml:apply>"
    if isinstance(n, X.Call):
        if n.fn == "pi":
            return '<ml:id labels="CONSTANT" xml:space="preserve">π</ml:id>'
        if n.fn == "sqrt":
            return f"<ml:apply><ml:nthRoot /><ml:placeholder />{to_xml(n.args[0], names)}</ml:apply>"
        if n.fn == "radians":
            return f'<ml:apply><ml:mult />{to_xml(n.args[0], names)}<ml:id labels="UNIT" xml:space="preserve">°</ml:id></ml:apply>'
        fn = _FN.get(n.fn, n.fn)
        head = f'<ml:id labels="FUNCTION" xml:space="preserve">{escape(fn)}</ml:id>'
        if len(n.args) == 1:
            return f"<ml:apply>{head}{to_xml(n.args[0], names)}</ml:apply>"
        return f"<ml:apply>{head}<ml:sequence>{''.join(to_xml(a, names) for a in n.args)}</ml:sequence></ml:apply>"
    if isinstance(n, X.If):
        other = to_xml(n.other, names)
        return (f"<ml:if><ml:test>{to_xml(n.cond, names)}</ml:test><ml:then><ml:program>{to_xml(n.then, names)}"
                f"</ml:program></ml:then><ml:else><ml:program>{other}</ml:program></ml:else></ml:if>")
    if isinstance(n, X.Cmp):
        return f"<ml:apply><ml:{_CMP[n.op]} />{to_xml(n.left, names)}{to_xml(n.right, names)}</ml:apply>"
    if isinstance(n, X.Logic):
        if n.op == "not":
            return f"<ml:apply><ml:not />{to_xml(n.args[0], names)}</ml:apply>"
        out = to_xml(n.args[0], names)
        for a in n.args[1:]:
            out = f"<ml:apply><ml:{n.op} />{out}{to_xml(a, names)}</ml:apply>"
        return out
    raise ValueError(f"cannot write {type(n).__name__} to Mathcad")


# --------------------------------------------------------------------------
# package
# --------------------------------------------------------------------------
_NS = ('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
       'xmlns:ve="http://schemas.openxmlformats.org/markup-compatibility/2006" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:ws="http://schemas.mathsoft.com/worksheet50" xmlns:ml="http://schemas.mathsoft.com/math50" '
       'xmlns:u="http://schemas.mathsoft.com/units10" xmlns:p="http://schemas.mathsoft.com/provenance10" '
       'xmlns="http://schemas.mathsoft.com/worksheet50"')

_XAML = ('<Section xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xml:space="preserve" '
         'TextAlignment="Left" FontFamily="Segoe UI" FontSize="{size}" Foreground="#FF000000">'
         '<Paragraph Margin="0,0,0,0"><Run FontWeight="{weight}">{text}</Run></Paragraph></Section>')


def _xaml_package(text: str, size: float = 13.3333333333333, weight: str = "Normal") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/content-types"><Default Extension="xaml" ContentType="application/'
                   'vnd.ms-wpf.xaml+xml" /><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
                   'package.relationships+xml" /></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Type="http://schemas.microsoft.com/'
                   f'wpf/2005/10/xaml/entry" Target="/Xaml/Document.xaml" Id="R{uuid.uuid4().hex[:16]}" />'
                   '</Relationships>')
        z.writestr("Xaml/Document.xaml", _XAML.format(text=escape(text), size=size, weight=weight))
    return buf.getvalue()


_PRESENTATION = ('<?xml version="1.0" encoding="utf-8"?><presentation xmlns:ws="http://schemas.mathsoft.com/'
                 'worksheet50" xmlns="http://schemas.ptc.com/mathcad/settings/presentation10"><pageModel '
                 'paper-code="A4" grid-size="Fine" orientation="Portrait" margin-type="Normal" show-grid="false" '
                 'show-page-frame="true" show-header-frame="true" spell-check-enabled="false" /><mathRendering>'
                 '<ws:results><general precision="{p}" show-trailing-zeros="true" radix="dec" zero-threshold="15" '
                 'imaginary-value="i" exponential-threshold="6" xmlns="http://schemas.mathsoft.com/worksheet50" />'
                 '<ws:unit simplify-units="false" /></ws:results></mathRendering></presentation>')
_CALCULATION = ('<?xml version="1.0" encoding="utf-8"?><calculation cache-worksheet="false" xmlns="http://schemas.'
                'ptc.com/mathcad/settings/calculation10"><builtInVariables array-origin="0" convergence-tolerance='
                '"0.001" constraint-tolerance="0.001" prn-col-width="8" prn-precision="4" random-seed="1" />'
                '<calculationBehavior automatic-recalculation="true" strings-use-origin="false" matrix-strict-'
                'singularity-check="true" exact-boolean="false" units-in-symbolics="false" constants-in-symbolics='
                '"false" symbolic-engine="axiom" /><units><currentUnitSystem name="si" /></units></calculation>')


def export_worksheet(kb: KnowledgeBase, target: str, path: Path, values: dict | None = None, given=(),
                     style: Style | None = None) -> Path:
    style = style or Style()
    obj = kb.objects[target]
    steps, inputs = kb.plan(target, given)
    if values is None:
        values, _ = starting_values(kb, target, given)
    all_ids = list(inputs) + list(obj.fixed) + steps
    names = mathcad_names(kb, all_ids)
    regions, rels, xaml = [], [], {}
    y = 20.0
    rid = 0

    def text(t: str, top: float, left: float = 10.0, size: float = 13.3333333333333, weight: str = "Normal"):
        nonlocal rid
        key = f"R{uuid.uuid4().hex[:16]}"
        part = f"mathcad/xaml/FlowDocument{len(xaml)}.XamlPackage"
        xaml[part] = _xaml_package(t, size, weight)
        rels.append((key, "/" + part))
        regions.append(f'<region region-id="{rid}" width="420" top="{top:.3f}" left="{left:.3f}"><text '
                       f'item-idref="{key}" /></region>')
        rid += 1

    def math(body: str, top: float, left: float = 330.0):
        nonlocal rid
        regions.append(f'<region region-id="{rid}" top="{top:.3f}" left="{left:.3f}"><math>{body}</math></region>')
        rid += 1

    def unit_override(sid: str) -> str:
        u = style.unit(kb, sid)
        if u in ("-", ""):
            return "<ml:unitOverride><ml:placeholder /></ml:unitOverride>"
        return f"<ml:unitOverride>{to_xml(_unit_tree(u), names)}</ml:unitOverride>"

    text(f"{obj.text} - {obj.name}", y, size=18.6666666666667, weight="Bold")
    y += 34
    text(obj.reference_text, y)
    y += 40
    text("Input", y, weight="Bold")
    y += 30
    for sid in list(inputs) + list(obj.fixed):
        item = kb.item(sid)
        v = obj.fixed.get(sid, values.get(sid))
        shown = style.show(kb, sid, v)
        u = style.unit(kb, sid)
        text(item.name if item else sid, y)
        value = to_xml(X.Num(round(shown, 10)), names) if isinstance(shown, (int, float)) else to_xml(X.Str(str(shown)), names)
        if u not in ("-", ""):
            value = f"<ml:apply><ml:mult />{value}{to_xml(_unit_tree(u), names)}</ml:apply>"
        b, s = names[sid]
        math(f"<ml:define>{_id(b, s)}{value}</ml:define>", y)
        y += 30
    y += 14
    text("Calculation", y, weight="Bold")
    y += 30
    for sid in steps:
        o = kb.objects[sid]
        text(f"{o.name} ({o.reference_text.replace(o.code + ' ', '')})", y)
        b, s = names[sid]
        body = to_xml(with_units(kb, sid), names)
        math(f"<ml:define>{_id(b, s)}<ml:eval>{body}{unit_override(sid)}</ml:eval></ml:define>", y)
        y += 56
    worksheet = f'<?xml version="1.0" encoding="utf-8"?><worksheet {_NS}><regions>{"".join(regions)}</regions></worksheet>'
    marker = json.dumps({"ckb": target, "version": obj.version, "names": {k: list(v) for k, v in names.items()}})
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types"><Default Extension="xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'mathprocessingml.mathcad.main+xml" /><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
            'package.relationships+xml" /><Default Extension="XamlPackage" ContentType="application/zip" />'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-'
            'properties+xml" /><Override PartName="/docProps/app.xml" ContentType="application/mathcad.extended-'
            'properties+xml" /><Override PartName="/mathcad/settings/presentation.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.mathprocessingml.mathcad.settings.presentation+xml" /><Override PartName='
            '"/mathcad/settings/calculation.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'mathprocessingml.mathcad.settings.calculation+xml" /><Override PartName="/mathcad/result.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.mathprocessingml.mathcad.result+xml" />'
            '<Override PartName="/mathcad/integration.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.mathprocessingml.mathcad.integration+xml" /></Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="/mathcad/worksheet.xml" Id="Rws" /><Relationship Type="http://'
            'schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="/docProps/'
            'core.xml" Id="Rcore" /><Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/extended-properties" Target="/docProps/app.xml" Id="Rapp" /></Relationships>'),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="utf-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
            'package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>'
            f'{escape(obj.text + " - " + obj.name)}</dc:title><dc:description>{escape(marker)}</dc:description>'
            f'<dc:creator>calculation knowledge base</dc:creator><cp:revision>1</cp:revision></cp:coreProperties>'),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="utf-8"?><properties xmlns="http://schemas.mathsoft.com/extended-'
            'properties"><appVersion>9.0.0.0</appVersion><engineVersion>9.0.0.17</engineVersion></properties>'),
        "mathcad/worksheet.xml": worksheet,
        "mathcad/_rels/worksheet.xml.rels": (
            '<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships">' + "".join(
                f'<Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                f'flowDocument" Target="{t}" Id="{k}" />' for k, t in rels) + "</Relationships>"),
        "mathcad/settings/presentation.xml": _PRESENTATION.replace("{p}", str(style.decimals)),
        "mathcad/settings/calculation.xml": _CALCULATION,
        "mathcad/result.xml": ('<?xml version="1.0" encoding="utf-8"?><resultsList xmlns:ml="http://schemas.'
                               'mathsoft.com/math50" xmlns:u="http://schemas.mathsoft.com/units10" xmlns="http://'
                               'schemas.mathsoft.com/result10" />'),
        "mathcad/integration.xml": '<?xml version="1.0" encoding="utf-8"?><regions xmlns="http://schemas.ptc.com/integration10" />',
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
        for name, data in xaml.items():
            z.writestr(name, data)
    return path


def read_marker(path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(path) as z:
            core = z.read("docProps/core.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile, OSError):
        return None
    m = re.search(r"<dc:description>(.*?)</dc:description>", core, re.S)
    if not m:
        return None
    from xml.sax.saxutils import unescape
    try:
        data = json.loads(unescape(m.group(1), {"&quot;": '"'}))
    except ValueError:
        return None
    return data if "ckb" in data else None


def verify(kb: KnowledgeBase, path: Path) -> dict:
    """Read the worksheet back with mcad2py, run it, and compare every step with the knowledge base."""
    from ..convert.mathcad import convert_mathcad
    marker = read_marker(path)
    if marker is None:
        return {"ok": False, "reason": "not a worksheet generated from the knowledge base"}
    target = marker["ckb"]
    if target not in kb.objects:
        return {"ok": False, "reason": f"object {target} is not in this knowledge base"}
    obj = kb.objects[target]
    doc = convert_mathcad(Path(path))
    by_name = {}
    for st in doc.statements:
        by_name[st.name] = st
    names = {k: tuple(v) for k, v in marker["names"].items()}
    raw = {sid: (f"{b}_{s}" if s else b) for sid, (b, s) in names.items()}
    values = {}
    steps, inputs = kb.plan(target)
    for sid in inputs:
        st = by_name.get(raw[sid])
        if st is not None and isinstance(st.value, (int, float)):
            values[sid] = st.value
    out = {"object": target, "version_in_file": marker["version"], "version_now": obj.version,
           "same_version": marker["version"] == obj.version, "issues": doc.issues}
    try:
        _, trace = kb.evaluate(target, values)
    except Exception as exc:                                     # noqa: BLE001
        out.update(ok=False, reason=f"inputs not read back: {exc}")
        return out
    rows = []
    for step in trace:
        st = by_name.get(raw[step.id])
        got = st.value if st is not None else None
        ok = isinstance(got, (int, float)) and abs(got - step.value) <= 1e-9 * max(1.0, abs(step.value))
        rows.append({"id": step.id, "mathcad": got, "knowledge_base": step.value, "agree": ok})
    out["rows"] = rows
    out["ok"] = out["same_version"] and all(r["agree"] for r in rows) and not doc.issues
    return out
