"""Expression language shared by every stage.

Every formula that enters the system - a Mathcad region, an Excel cell, a line
of a Python script - is turned into the same small tree.  From that one tree
the system evaluates the formula, compares it with other formulas, and prints
it as Python, JavaScript, an Excel formula, plain text or MathML.  Keeping a
single representation is what makes a distilled object traceable: the code
block, the web calculator, the Excel calculator and the equation printed in
the report are all printed from the same tree.

The tree keeps the order in which the engineer wrote the terms, so a printed
equation reads like the source and like the code clause.
"""
from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Union


# --------------------------------------------------------------------------
# nodes
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Num:
    value: float
    text: str = field(default="", compare=False)    # literal as written ("200 mm")
    conv: bool = field(default=False, compare=False)  # introduced by a unit conversion


@dataclass(frozen=True)
class Sym:
    name: str


@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Unit:
    """A unit literal in a source expression (``ureg.mm``); removed on conversion."""
    name: str


@dataclass(frozen=True)
class Bin:
    op: str            # + - * / **
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Neg:
    arg: "Node"


@dataclass(frozen=True)
class Call:
    fn: str
    args: tuple


@dataclass(frozen=True)
class If:
    cond: "Node"
    then: "Node"
    other: "Node"


@dataclass(frozen=True)
class Cmp:
    op: str            # < <= > >= == !=
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Logic:
    op: str            # and or not
    args: tuple


Node = Union[Num, Sym, Str, Unit, Bin, Neg, Call, If, Cmp, Logic]


class ExprError(Exception):
    """The expression cannot be parsed or evaluated."""


# --------------------------------------------------------------------------
# functions known to the language
# --------------------------------------------------------------------------
def _cot(x):
    return 1.0 / math.tan(x)


def _round(x, n=0):
    # engineering rounding (half away from zero), as Excel and Mathcad do
    q = 10 ** int(n)
    return math.floor(abs(x) * q + 0.5) / q * (1 if x >= 0 else -1)


FUNCS: dict[str, Callable] = {
    "max": max, "min": min, "abs": abs, "sqrt": math.sqrt,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "cot": _cot,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "exp": math.exp, "ln": math.log, "log10": math.log10,
    "radians": math.radians, "degrees": math.degrees,
    "round": _round, "ceil": math.ceil, "floor": math.floor,
    "pi": lambda: math.pi,
}

# spellings met in source files -> canonical function name
_FN_ALIASES = {
    "mc_max": "max", "mc_min": "min", "fabs": "abs", "log": "ln",
    "arcsin": "asin", "arccos": "acos", "arctan": "atan",
    "maximum": "max", "minimum": "min",
}


# --------------------------------------------------------------------------
# parsing (Python expression syntax is the storage syntax)
# --------------------------------------------------------------------------
_BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**"}
_CMPOPS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
           ast.Eq: "==", ast.NotEq: "!="}


def parse(text: str) -> Node:
    """Parse a formula written in Python expression syntax."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"cannot parse {text!r}: {exc.msg}") from exc
    return from_ast(tree.body, text)


def from_ast(node: ast.AST, source: str = "", unit_roots: Iterable[str] = ("ureg", "u", "units"),
             call_hook: Callable | None = None) -> Node:
    """Convert a Python AST expression into an expression tree.

    ``call_hook(name, args, kwargs)`` may resolve calls to functions defined in
    the source itself; it returns a tree, or None when the name is not its own.
    """
    roots = tuple(unit_roots)

    def conv(n: ast.AST) -> Node:
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool):
                return Num(1.0 if n.value else 0.0, text=str(n.value))
            if isinstance(n.value, (int, float)):
                seg = ast.get_source_segment(source, n) if source else None
                return Num(n.value, text=seg or _num_text(n.value))
            if isinstance(n.value, str):
                return Str(n.value)
            raise ExprError(f"unsupported constant {n.value!r}")
        if isinstance(n, ast.Name):
            if n.id == "pi":
                return Call("pi", ())
            return Sym(n.id)
        if isinstance(n, ast.Attribute):
            if isinstance(n.value, ast.Name):
                if n.value.id in roots:
                    return Unit(n.attr)
                if n.attr == "pi":
                    return Call("pi", ())
            raise ExprError(f"unsupported attribute {ast.unparse(n)}")
        if isinstance(n, ast.BinOp):
            op = _BINOPS.get(type(n.op))
            if op is None:
                raise ExprError(f"unsupported operator {type(n.op).__name__}")
            return Bin(op, conv(n.left), conv(n.right))
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.USub):
                arg = conv(n.operand)
                if isinstance(arg, Num):
                    return Num(-arg.value, text="-" + (arg.text or _num_text(arg.value)))
                return Neg(arg)
            if isinstance(n.op, ast.UAdd):
                return conv(n.operand)
            if isinstance(n.op, ast.Not):
                return Logic("not", (conv(n.operand),))
            raise ExprError("unsupported unary operator")
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                fn = n.func.id
            elif isinstance(n.func, ast.Attribute):
                fn = n.func.attr          # math.sqrt, np.sqrt
            else:
                raise ExprError("unsupported call")
            fn = _FN_ALIASES.get(fn, fn)
            args = tuple(conv(a) for a in n.args)
            if call_hook is not None:
                hit = call_hook(fn, args, {k.arg: conv(k.value) for k in n.keywords if k.arg})
                if hit is not None:
                    return hit
            if n.keywords:
                raise ExprError(f"keyword arguments not supported in {fn}()")
            if fn in ("nth_root", "root") and len(args) == 2:
                if args[1] == Num(2):
                    return Call("sqrt", (args[0],))
                return Bin("**", args[0], Bin("/", Num(1, "1"), args[1]))
            if fn in ("power", "pow") and len(args) == 2:
                return Bin("**", args[0], args[1])
            if fn == "float" and len(args) == 1:
                return args[0]
            if fn not in FUNCS:
                raise ExprError(f"unknown function {fn}()")
            return Call(fn, args)
        if isinstance(n, ast.IfExp):
            return If(conv(n.test), conv(n.body), conv(n.orelse))
        if isinstance(n, ast.Compare):
            parts, left = [], conv(n.left)
            for op, comp in zip(n.ops, n.comparators):
                sym = _CMPOPS.get(type(op))
                if sym is None:
                    raise ExprError("unsupported comparison")
                right = conv(comp)
                parts.append(Cmp(sym, left, right))
                left = right
            return parts[0] if len(parts) == 1 else Logic("and", tuple(parts))
        if isinstance(n, ast.BoolOp):
            return Logic("and" if isinstance(n.op, ast.And) else "or",
                         tuple(conv(v) for v in n.values))
        raise ExprError(f"unsupported syntax: {type(n).__name__}")

    return conv(node)


def _num_text(v: float) -> str:
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e15):
        return str(int(v))
    return repr(float(v)) if abs(v) >= 1e-4 else f"{v:.6g}"


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------
def evaluate(node: Node, env: dict):
    """Evaluate a tree.  ``env`` maps symbol names to numbers or strings."""
    try:
        return _ev(node, env)
    except ExprError:
        raise
    except KeyError as exc:
        raise ExprError(f"no value for {exc.args[0]!r}") from exc
    except (ZeroDivisionError, ValueError, OverflowError, TypeError) as exc:
        raise ExprError(f"cannot evaluate: {exc}") from exc


def _ev(n: Node, env: dict):
    if isinstance(n, Num):
        return n.value
    if isinstance(n, Sym):
        return env[n.name]
    if isinstance(n, Str):
        return n.value
    if isinstance(n, Unit):
        raise ExprError(f"unit literal {n.name!r} left in expression")
    if isinstance(n, Bin):
        a, b = _ev(n.left, env), _ev(n.right, env)
        if n.op == "+":
            return a + b
        if n.op == "-":
            return a - b
        if n.op == "*":
            return a * b
        if n.op == "/":
            return a / b
        r = a ** b
        if isinstance(r, complex):
            raise ValueError("negative base with fractional exponent")
        return r
    if isinstance(n, Neg):
        return -_ev(n.arg, env)
    if isinstance(n, Call):
        return FUNCS[n.fn](*[_ev(a, env) for a in n.args])
    if isinstance(n, If):
        return _ev(n.then, env) if _ev(n.cond, env) else _ev(n.other, env)
    if isinstance(n, Cmp):
        a, b = _ev(n.left, env), _ev(n.right, env)
        sa, sb = isinstance(a, str), isinstance(b, str)
        if sa and sb:
            a, b = a.strip().lower(), b.strip().lower()
        elif sa or sb:
            # spreadsheet rule: any text sorts above any number
            if n.op in ("==", "!="):
                return n.op == "!="
            a, b = (1, 0) if sa else (0, 1)
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b,
                "==": a == b, "!=": a != b}[n.op]
    if isinstance(n, Logic):
        if n.op == "not":
            return not _ev(n.args[0], env)
        vals = (_ev(a, env) for a in n.args)
        return all(vals) if n.op == "and" else any(vals)
    raise ExprError(f"cannot evaluate {type(n).__name__}")


# --------------------------------------------------------------------------
# traversal helpers
# --------------------------------------------------------------------------
def children(n: Node) -> tuple:
    if isinstance(n, Bin) or isinstance(n, Cmp):
        return (n.left, n.right)
    if isinstance(n, Neg):
        return (n.arg,)
    if isinstance(n, (Call, Logic)):
        return tuple(n.args)
    if isinstance(n, If):
        return (n.cond, n.then, n.other)
    return ()


def rebuild(n: Node, kids: tuple) -> Node:
    if isinstance(n, Bin):
        return Bin(n.op, kids[0], kids[1])
    if isinstance(n, Cmp):
        return Cmp(n.op, kids[0], kids[1])
    if isinstance(n, Neg):
        return Neg(kids[0])
    if isinstance(n, Call):
        return Call(n.fn, tuple(kids))
    if isinstance(n, Logic):
        return Logic(n.op, tuple(kids))
    if isinstance(n, If):
        return If(kids[0], kids[1], kids[2])
    return n


def transform(n: Node, fn: Callable[[Node], Node | None]) -> Node:
    """Bottom-up rewrite: ``fn`` may return a replacement for a node, or None."""
    kids = children(n)
    if kids:
        n = rebuild(n, tuple(transform(k, fn) for k in kids))
    out = fn(n)
    return n if out is None else out


def symbols(n: Node) -> list[str]:
    """Symbol names in order of first appearance."""
    seen: list[str] = []

    def walk(x: Node):
        if isinstance(x, Sym):
            if x.name not in seen:
                seen.append(x.name)
        for k in children(x):
            walk(k)

    walk(n)
    return seen


def substitute(n: Node, mapping: dict) -> Node:
    """Replace symbols.  ``mapping`` values may be nodes, names or numbers."""
    def rep(x: Node):
        if isinstance(x, Sym) and x.name in mapping:
            v = mapping[x.name]
            if isinstance(v, str):
                return Sym(v)
            if isinstance(v, (int, float)):
                return Num(v)
            return v
        return None

    return transform(n, rep)


def has_units(n: Node) -> bool:
    return isinstance(n, Unit) or any(has_units(k) for k in children(n))


# --------------------------------------------------------------------------
# products and sums as flat lists (used by folding and by consolidation)
# --------------------------------------------------------------------------
def factors(n: Node) -> tuple[list, list]:
    """Flatten a chain of * and / into (numerator factors, denominator factors)."""
    if isinstance(n, Bin) and n.op == "*":
        n1, d1 = factors(n.left)
        n2, d2 = factors(n.right)
        return n1 + n2, d1 + d2
    if isinstance(n, Bin) and n.op == "/":
        n1, d1 = factors(n.left)
        n2, d2 = factors(n.right)
        return n1 + d2, d1 + n2
    return [n], []


def product(numer: list, denom: list | None = None) -> Node:
    def chain(items):
        out = items[0]
        for it in items[1:]:
            out = Bin("*", out, it)
        return out

    denom = denom or []
    top = chain(numer) if numer else Num(1, "1")
    return Bin("/", top, chain(denom)) if denom else top


def terms(n: Node) -> list[tuple[int, Node]]:
    """Flatten a chain of + and - into signed terms."""
    if isinstance(n, Bin) and n.op == "+":
        return terms(n.left) + terms(n.right)
    if isinstance(n, Bin) and n.op == "-":
        return terms(n.left) + [(-s, t) for s, t in terms(n.right)]
    if isinstance(n, Neg):
        return [(-s, t) for s, t in terms(n.arg)]
    return [(1, n)]


def total(items: list[tuple[int, Node]]) -> Node:
    if not items:
        return Num(0, "0")
    sign, out = items[0]
    if sign < 0:
        out = Neg(out)
    for sign, t in items[1:]:
        out = Bin("+" if sign > 0 else "-", out, t)
    return out


# --------------------------------------------------------------------------
# unit literals and conversion factors
# --------------------------------------------------------------------------
def strip_units(n: Node, factor_of: Callable[[str], tuple[float, str]]) -> Node:
    """Replace unit literals by their factor to canonical units.

    ``200 * ureg.mm / d`` becomes ``200 / d`` (the literal remembers that it
    was written as "200 mm"); ``f_ck / ureg.MPa`` becomes ``f_ck``.
    ``factor_of(name)`` returns (factor to canonical units, display text).
    """
    def pure(x: Node):
        """(factor, text) when the subtree holds only units, else None."""
        if isinstance(x, Unit):
            return factor_of(x.name)
        if isinstance(x, Bin) and x.op in "*/":
            a, b = pure(x.left), pure(x.right)
            if a and b:
                if x.op == "*":
                    return a[0] * b[0], f"{a[1]}·{b[1]}"
                return a[0] / b[0], f"{a[1]}/{b[1]}"
        if isinstance(x, Bin) and x.op == "**" and isinstance(x.right, Num):
            a = pure(x.left)
            if a:
                p = x.right.value
                sup = {2: "²", 3: "³", 4: "⁴"}.get(p, f"^{_num_text(p)}")
                return a[0] ** p, f"{a[1]}{sup}"
        return None

    def one(f: float, text: str) -> Node:
        return Num(f, text=f"1 {text}")

    def walk(x: Node) -> Node:
        if isinstance(x, Unit):                 # a bare unit used as a value
            return one(*factor_of(x.name))
        if isinstance(x, Bin) and x.op in "*/":
            pl, pr = pure(x.left), pure(x.right)
            if pl and pr:
                return one(*pure(x))
            if pr:
                f, text = pr
                left = walk(x.left)
                if isinstance(left, Num) and not left.conv:
                    lit = left.text or _num_text(left.value)
                    has_unit = " " in lit or lit.endswith(("°", "%", "‰"))
                    if x.op == "*":
                        sep = "·" if has_unit else ("" if text in ("°", "%", "‰") else " ")
                        return Num(left.value * f, text=f"{lit}{sep}{text}")
                    return Num(left.value / f, text=f"{lit}/{text}" if has_unit else f"{lit} 1/{text}")
                if x.op == "/":
                    f = 1.0 / f
                if math.isclose(f, 1.0, rel_tol=1e-12):
                    return left
                return Bin("*", left, Num(f, conv=True))
            if pl:
                f, _ = pl
                right = walk(x.right)
                if x.op == "*":
                    if math.isclose(f, 1.0, rel_tol=1e-12):
                        return right
                    return Bin("*", right, Num(f, conv=True))
                return Bin("/", Num(f, conv=True), right)
        kids = children(x)
        return rebuild(x, tuple(walk(k) for k in kids)) if kids else x

    return walk(n)


def fold(n: Node) -> Node:
    """Cancel conversion factors: ``x * 1000 * d / 1000`` becomes ``x * d``.

    Only products that contain a conversion factor, or a literal that appears
    both above and below the fraction bar, are rewritten.  Everything else is
    left exactly as the engineer wrote it.
    """
    def rep(x: Node):
        if isinstance(x, Bin) and x.op == "+" and x.right == Num(0) and x.right.conv:
            return x.left
        if isinstance(x, Bin) and x.op == "**" and x.right == Num(1):
            return x.left
        if not (isinstance(x, Bin) and x.op in "*/"):
            return None
        numer, denom = factors(x)
        lit_n = [f for f in numer if isinstance(f, Num)]
        lit_d = [f for f in denom if isinstance(f, Num)]
        has_conv = any(f.conv for f in lit_n + lit_d)
        pairs = [(a, b) for a in lit_n for b in lit_d
                 if not a.conv and not b.conv and math.isclose(a.value, b.value, rel_tol=1e-12)]
        if not has_conv and not pairs:
            return None
        conv = 1.0
        keep_n, keep_d = [], []
        for f in numer:
            if isinstance(f, Num) and f.conv:
                conv *= f.value
            else:
                keep_n.append(f)
        for f in denom:
            if isinstance(f, Num) and f.conv:
                conv /= f.value
            else:
                keep_d.append(f)

        def take(lst, pred):
            for i, f in enumerate(lst):
                if isinstance(f, Num) and not f.conv and pred(f.value):
                    return lst.pop(i)
            return None

        # literal pairs equal above and below the bar
        for f in list(keep_n):
            if isinstance(f, Num) and not f.conv:
                hit = take(keep_d, lambda v, fv=f.value: math.isclose(v, fv, rel_tol=1e-12))
                if hit is not None:
                    keep_n.remove(f)
        # the conversion factor against a literal the author wrote
        if not math.isclose(conv, 1.0, rel_tol=1e-12):
            if take(keep_d, lambda v: math.isclose(v, conv, rel_tol=1e-9)) is not None:
                conv = 1.0
            elif take(keep_n, lambda v: math.isclose(v * conv, 1.0, rel_tol=1e-9)) is not None:
                conv = 1.0
        if not math.isclose(conv, 1.0, rel_tol=1e-12):
            if conv >= 1:
                keep_n.append(Num(_tidy(conv), conv=True))
            else:
                keep_d.append(Num(_tidy(1.0 / conv), conv=True))
        if not keep_n and not keep_d:
            return Num(1, "1")
        return product(keep_n, keep_d)

    return transform(n, rep)


def _tidy(v: float) -> float:
    r = round(v)
    return float(r) if abs(v - r) < 1e-9 * max(1.0, abs(v)) else v


# --------------------------------------------------------------------------
# printing - precedence
# --------------------------------------------------------------------------
_PREC = {"if": 1, "or": 2, "and": 3, "not": 4, "cmp": 5, "+": 6, "-": 6,
         "*": 7, "/": 7, "neg": 8, "**": 9}


def _prec(n: Node) -> int:
    if isinstance(n, Bin):
        return _PREC[n.op]
    if isinstance(n, Neg):
        return _PREC["neg"]
    if isinstance(n, Num) and n.value < 0:
        return _PREC["neg"]
    if isinstance(n, If):
        return _PREC["if"]
    if isinstance(n, Cmp):
        return _PREC["cmp"]
    if isinstance(n, Logic):
        return _PREC[n.op]
    return 10


def _fmt_num(v: float) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


def _infix(n: Node, emit: Callable[[Node], str], ops: dict, right_assoc_pow: bool = True) -> str:
    """Shared infix printer for Python-like targets."""
    p = _PREC[n.op]
    left, right = emit(n.left), emit(n.right)
    lp, rp = _prec(n.left), _prec(n.right)
    if n.op == "**":
        if lp <= p:
            left = f"({left})"
        if rp < p or isinstance(n.right, Bin):
            right = f"({right})"
    else:
        if lp < p:
            left = f"({left})"
        if rp < p or (rp == p and n.op in "-/"):
            right = f"({right})"
    return f"{left}{ops[n.op]}{right}"


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------
def to_python(n: Node, name: Callable[[str], str] = lambda s: s) -> str:
    ops = {"+": " + ", "-": " - ", "*": " * ", "/": " / ", "**": " ** "}

    def emit(x: Node) -> str:
        if isinstance(x, Num):
            return _fmt_num(x.value)
        if isinstance(x, Sym):
            return name(x.name)
        if isinstance(x, Str):
            return repr(x.value)
        if isinstance(x, Unit):
            return f"ureg.{x.name}"
        if isinstance(x, Bin):
            return _infix(x, emit, ops)
        if isinstance(x, Neg):
            inner = emit(x.arg)
            return f"-({inner})" if _prec(x.arg) < _PREC["neg"] else f"-{inner}"
        if isinstance(x, Call):
            if x.fn == "pi":
                return "pi"
            return f"{x.fn}({', '.join(emit(a) for a in x.args)})"
        if isinstance(x, If):
            other = emit(x.other)
            then = emit(x.then)
            if isinstance(x.then, If):
                then = f"({then})"
            return f"{then} if {emit(x.cond)} else {other}"
        if isinstance(x, Cmp):
            return f"{emit(x.left)} {x.op} {emit(x.right)}"
        if isinstance(x, Logic):
            if x.op == "not":
                return f"not ({emit(x.args[0])})"
            return f" {x.op} ".join(f"({emit(a)})" if _prec(a) <= _PREC[x.op] else emit(a)
                                    for a in x.args)
        raise ExprError(type(x).__name__)

    return emit(n)


# --------------------------------------------------------------------------
# JavaScript
# --------------------------------------------------------------------------
_JS_FN = {"max": "Math.max", "min": "Math.min", "abs": "Math.abs", "sqrt": "Math.sqrt",
          "sin": "Math.sin", "cos": "Math.cos", "tan": "Math.tan", "asin": "Math.asin",
          "acos": "Math.acos", "atan": "Math.atan", "exp": "Math.exp", "ln": "Math.log",
          "log10": "Math.log10", "ceil": "Math.ceil", "floor": "Math.floor"}


def to_js(n: Node, name: Callable[[str], str] = lambda s: s) -> str:
    ops = {"+": " + ", "-": " - ", "*": " * ", "/": " / "}

    def emit(x: Node) -> str:
        if isinstance(x, Num):
            return _fmt_num(x.value)
        if isinstance(x, Sym):
            return name(x.name)
        if isinstance(x, Str):
            return '"' + x.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(x, Bin):
            if x.op == "**":
                return f"Math.pow({emit(x.left)}, {emit(x.right)})"
            return _infix(x, emit, ops)
        if isinstance(x, Neg):
            return f"-({emit(x.arg)})"
        if isinstance(x, Call):
            a = [emit(k) for k in x.args]
            if x.fn == "pi":
                return "Math.PI"
            if x.fn == "cot":
                return f"(1 / Math.tan({a[0]}))"
            if x.fn == "radians":
                return f"(({a[0]}) * Math.PI / 180)"
            if x.fn == "degrees":
                return f"(({a[0]}) * 180 / Math.PI)"
            if x.fn == "round":
                d = a[1] if len(a) > 1 else "0"
                return f"(Math.sign({a[0]}) * Math.floor(Math.abs({a[0]}) * Math.pow(10, {d}) + 0.5) / Math.pow(10, {d}))"
            return f"{_JS_FN[x.fn]}({', '.join(a)})"
        if isinstance(x, If):
            return f"(({emit(x.cond)}) ? ({emit(x.then)}) : ({emit(x.other)}))"
        if isinstance(x, Cmp):
            op = {"==": "===", "!=": "!=="}.get(x.op, x.op)
            l, r = emit(x.left), emit(x.right)
            if isinstance(x.left, Str) or isinstance(x.right, Str):
                l, r = f"String({l}).trim().toLowerCase()", f"String({r}).trim().toLowerCase()"
            return f"({l} {op} {r})"
        if isinstance(x, Logic):
            if x.op == "not":
                return f"!({emit(x.args[0])})"
            return "(" + (" && " if x.op == "and" else " || ").join(emit(a) for a in x.args) + ")"
        raise ExprError(type(x).__name__)

    return emit(n)


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------
_XL_FN = {"max": "MAX", "min": "MIN", "abs": "ABS", "sqrt": "SQRT", "sin": "SIN",
          "cos": "COS", "tan": "TAN", "asin": "ASIN", "acos": "ACOS", "atan": "ATAN",
          "exp": "EXP", "ln": "LN", "log10": "LOG10", "radians": "RADIANS",
          "degrees": "DEGREES", "round": "ROUND", "floor": "ROUNDDOWN", "ceil": "ROUNDUP"}


def to_excel(n: Node, ref: Callable[[str], str]) -> str:
    """Excel formula text (without the leading '=')."""
    ops = {"+": "+", "-": "-", "*": "*", "/": "/", "**": "^"}

    def emit(x: Node) -> str:
        if isinstance(x, Num):
            return _fmt_num(x.value) if x.value >= 0 else f"({_fmt_num(x.value)})"
        if isinstance(x, Sym):
            return ref(x.name)
        if isinstance(x, Str):
            return '"' + x.value.replace('"', '""') + '"'
        if isinstance(x, Bin):
            if x.op == "**":
                # Excel: unary minus binds tighter than ^ and ^ is left-associative
                return f"({emit(x.left)})^({emit(x.right)})"
            return _infix(x, emit, ops)
        if isinstance(x, Neg):
            return f"-({emit(x.arg)})"
        if isinstance(x, Call):
            a = [emit(k) for k in x.args]
            if x.fn == "pi":
                return "PI()"
            if x.fn == "cot":
                return f"(1/TAN({a[0]}))"
            if x.fn in ("floor", "ceil", "round") and len(a) == 1:
                a.append("0")
            return f"{_XL_FN[x.fn]}({','.join(a)})"
        if isinstance(x, If):
            return f"IF({emit(x.cond)},{emit(x.then)},{emit(x.other)})"
        if isinstance(x, Cmp):
            op = {"==": "=", "!=": "<>"}.get(x.op, x.op)
            return f"{emit(x.left)}{op}{emit(x.right)}"
        if isinstance(x, Logic):
            if x.op == "not":
                return f"NOT({emit(x.args[0])})"
            return f"{x.op.upper()}({','.join(emit(a) for a in x.args)})"
        raise ExprError(type(x).__name__)

    return emit(n)


# --------------------------------------------------------------------------
# plain text (terminal, search index)
# --------------------------------------------------------------------------
def to_text(n: Node, name: Callable[[str], str] = lambda s: s,
            values: dict | None = None, fmt: Callable[[float], str] | None = None) -> str:
    ops = {"+": " + ", "-": " − ", "*": " · ", "/": " / ", "**": "^"}
    fmt = fmt or (lambda v: f"{v:.4g}")

    def emit(x: Node) -> str:
        if isinstance(x, Num):
            if values is not None:
                return _fmt_num(x.value) if not x.conv else fmt(x.value)
            return x.text or _fmt_num(x.value)
        if isinstance(x, Sym):
            if values is not None and x.name in values:
                v = values[x.name]
                s = fmt(v) if isinstance(v, (int, float)) else f'"{v}"'
                return f"({s})" if s.startswith("-") else s
            return name(x.name)
        if isinstance(x, Str):
            return f'"{x.value}"'
        if isinstance(x, Unit):
            return x.name
        if isinstance(x, Bin):
            return _infix(x, emit, ops)
        if isinstance(x, Neg):
            inner = emit(x.arg)
            return f"−({inner})" if _prec(x.arg) < _PREC["neg"] else f"−{inner}"
        if isinstance(x, Call):
            if x.fn == "pi":
                return "π"
            if x.fn == "sqrt":
                return f"√({emit(x.args[0])})"
            return f"{x.fn}({', '.join(emit(a) for a in x.args)})"
        if isinstance(x, If):
            return f"{emit(x.then)} if {emit(x.cond)} else {emit(x.other)}"
        if isinstance(x, Cmp):
            op = {"<=": "≤", ">=": "≥", "!=": "≠", "==": "="}.get(x.op, x.op)
            return f"{emit(x.left)} {op} {emit(x.right)}"
        if isinstance(x, Logic):
            if x.op == "not":
                return f"not ({emit(x.args[0])})"
            return f" {x.op} ".join(emit(a) for a in x.args)
        raise ExprError(type(x).__name__)

    return emit(n)


# --------------------------------------------------------------------------
# MathML (reports and the web calculator)
# --------------------------------------------------------------------------
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_mathml(n: Node, sym: Callable[[str], str], values: dict | None = None,
              fmt: Callable[[float], str] | None = None, slots: bool = False) -> str:
    """MathML for a tree.

    With ``values`` the symbols are replaced by their numbers (the
    "substituted" line of a self-documenting calculation).  With ``slots``
    each symbol becomes an empty ``<mn data-s="name">`` that the web
    calculator fills in as the user types.
    """
    fmt = fmt or (lambda v: f"{v:.4g}")

    def number(v: float) -> str:
        s = fmt(v)
        if s.startswith("-"):
            return f"<mrow><mo>(</mo><mo>&#x2212;</mo><mn>{_esc(s[1:])}</mn><mo>)</mo></mrow>"
        return f"<mn>{_esc(s)}</mn>"

    def paren(inner: str) -> str:
        return f'<mrow><mo fence="true">(</mo>{inner}<mo fence="true">)</mo></mrow>'

    def emit(x: Node) -> str:
        if isinstance(x, Num):
            if values is not None or slots:
                v = x.value
                if v < 0:
                    return f"<mrow><mo>(</mo><mo>&#x2212;</mo><mn>{_esc(_short(-v))}</mn><mo>)</mo></mrow>"
                return f"<mn>{_esc(_short(v))}</mn>"
            text = x.text or _fmt_num(x.value)
            if x.conv:
                text = _short(x.value)
            neg = text.startswith("-")
            if neg:
                text = text[1:]
            head, _, unit = text.partition(" ")
            if head.endswith(("°", "%", "‰")):
                head, unit = head[:-1], head[-1]
                out = f"<mn>{_esc(head)}</mn><mtext>{_esc(unit)}</mtext>"
            else:
                out = f"<mn>{_esc(head)}</mn>"
                if unit:
                    out += f"<mtext>&#x2009;{_esc(unit)}</mtext>"
            if neg:
                out = f"<mo>&#x2212;</mo>{out}"
            return f"<mrow>{out}</mrow>" if (unit or neg) else out
        if isinstance(x, Sym):
            if slots:
                return f'<mn class="slot" data-s="{_esc(x.name)}"></mn>'
            if values is not None and x.name in values:
                v = values[x.name]
                if isinstance(v, str):
                    return f"<mtext>&#x201C;{_esc(v)}&#x201D;</mtext>"
                return number(v)
            return sym(x.name)
        if isinstance(x, Str):
            return f"<mtext>&#x201C;{_esc(x.value)}&#x201D;</mtext>"
        if isinstance(x, Bin):
            if x.op == "/":
                return f"<mfrac><mrow>{emit(x.left)}</mrow><mrow>{emit(x.right)}</mrow></mfrac>"
            if x.op == "**":
                base = emit(x.left)
                if x.right in (Num(0.5), Bin("/", Num(1), Num(2))):
                    return f"<msqrt>{base}</msqrt>"
                if not isinstance(x.left, (Sym, Num)) or (isinstance(x.left, Num) and x.left.value < 0) \
                        or ((values is not None or slots) and isinstance(x.left, Sym)
                            and isinstance((values or {}).get(x.left.name, 0), (int, float))
                            and (values or {}).get(x.left.name, 0) < 0):
                    base = paren(base)
                return f"<msup>{base}<mrow>{emit(x.right)}</mrow></msup>"
            p = _PREC[x.op]
            left, right = emit(x.left), emit(x.right)
            if _prec(x.left) < p:
                left = paren(left)
            if _prec(x.right) < p or (_prec(x.right) == p and x.op == "-"):
                right = paren(right)
            sign = {"+": "+", "-": "&#x2212;", "*": "&#x22C5;"}[x.op]
            return f"<mrow>{left}<mo>{sign}</mo>{right}</mrow>"
        if isinstance(x, Neg):
            inner = emit(x.arg)
            if _prec(x.arg) < _PREC["neg"]:
                inner = paren(inner)
            return f"<mrow><mo>&#x2212;</mo>{inner}</mrow>"
        if isinstance(x, Call):
            if x.fn == "pi":
                return "<mi>&#x3C0;</mi>"
            if x.fn == "sqrt":
                return f"<msqrt>{emit(x.args[0])}</msqrt>"
            if x.fn == "abs":
                return f'<mrow><mo fence="true">|</mo>{emit(x.args[0])}<mo fence="true">|</mo></mrow>'
            args = "<mo>,</mo>".join(emit(a) for a in x.args)
            return f'<mrow><mi mathvariant="normal">{x.fn}</mi><mo>&#x2061;</mo>{paren(args)}</mrow>'
        if isinstance(x, If):
            rows, node = [], x
            while isinstance(node, If):
                rows.append((emit(node.then), emit(node.cond)))
                node = node.other
            body = "".join(
                f"<mtr><mtd>{v}</mtd><mtd><mtext>if&#x2002;</mtext>{c}</mtd></mtr>" for v, c in rows)
            body += f"<mtr><mtd>{emit(node)}</mtd><mtd><mtext>otherwise</mtext></mtd></mtr>"
            return ('<mrow><mo fence="true">{</mo><mtable columnalign="left left" '
                    f'columnspacing="1em">{body}</mtable></mrow>')
        if isinstance(x, Cmp):
            op = {"<": "&lt;", ">": "&gt;", "<=": "&#x2264;", ">=": "&#x2265;",
                  "!=": "&#x2260;", "==": "="}[x.op]
            return f"<mrow>{emit(x.left)}<mo>{op}</mo>{emit(x.right)}</mrow>"
        if isinstance(x, Logic):
            if x.op == "not":
                return f"<mrow><mo>&#xAC;</mo>{paren(emit(x.args[0]))}</mrow>"
            sep = f"<mtext>&#x2002;{x.op}&#x2002;</mtext>"
            return f"<mrow>{sep.join(emit(a) for a in x.args)}</mrow>"
        raise ExprError(type(x).__name__)

    return emit(n)


def _short(v: float) -> str:
    """A literal number for display: no float noise, no loss of digits."""
    if float(v).is_integer() and abs(v) < 1e15:
        return str(int(v))
    s = f"{v:.10g}"
    return s


# --------------------------------------------------------------------------
# comparison keys
# --------------------------------------------------------------------------
def key(n: Node):
    """A structural key that ignores the order of terms and factors.

    Two formulas with the same key are the same formula written differently
    (``a*b`` and ``b*a``; ``x**0.5`` and ``sqrt(x)``).
    """
    if isinstance(n, Num):
        return ("n", round(float(n.value), 12))
    if isinstance(n, Sym):
        return ("s", n.name)
    if isinstance(n, Str):
        return ("t", n.value.strip().lower())
    if isinstance(n, Call) and n.fn == "sqrt":
        return key(Bin("**", n.args[0], Num(0.5)))
    if isinstance(n, Bin) and n.op in "+-" or isinstance(n, Neg):
        items = sorted(((s, key(t)) for s, t in terms(n)), key=repr)
        return ("+", tuple(items))
    if isinstance(n, Bin) and n.op in "*/":
        nu, de = factors(n)
        coef = 1.0
        kn, kd = [], []
        for f in nu:
            if isinstance(f, Num):
                coef *= f.value
            else:
                kn.append(key(f))
        for f in de:
            if isinstance(f, Num):
                coef /= f.value
            else:
                kd.append(key(f))
        return ("*", round(coef, 12), tuple(sorted(kn, key=repr)), tuple(sorted(kd, key=repr)))
    if isinstance(n, Bin):
        exp = n.right
        try:
            if not symbols(exp):
                exp = Num(float(evaluate(exp, {})))
        except ExprError:
            pass
        return ("^", key(n.left), key(exp))
    if isinstance(n, Call):
        args = [key(a) for a in n.args]
        if n.fn in ("max", "min"):
            args = sorted(args, key=repr)
        return ("f", n.fn, tuple(args))
    if isinstance(n, If):
        return ("if", key(n.cond), key(n.then), key(n.other))
    if isinstance(n, Cmp):
        return ("c", n.op, key(n.left), key(n.right))
    if isinstance(n, Logic):
        return ("l", n.op, tuple(key(a) for a in n.args))
    return ("?", repr(n))


def same(a: Node, b: Node) -> bool:
    return key(a) == key(b)


# --------------------------------------------------------------------------
# JSON (statements and objects are stored as JSON / YAML)
# --------------------------------------------------------------------------
def to_json(n: Node):
    if isinstance(n, Num):
        d = {"n": n.value}
        if n.text:
            d["t"] = n.text
        if n.conv:
            d["c"] = 1
        return d
    if isinstance(n, Sym):
        return {"s": n.name}
    if isinstance(n, Str):
        return {"str": n.value}
    if isinstance(n, Unit):
        return {"u": n.name}
    if isinstance(n, Bin):
        return {"op": n.op, "a": [to_json(n.left), to_json(n.right)]}
    if isinstance(n, Neg):
        return {"neg": to_json(n.arg)}
    if isinstance(n, Call):
        return {"fn": n.fn, "a": [to_json(a) for a in n.args]}
    if isinstance(n, If):
        return {"if": [to_json(n.cond), to_json(n.then), to_json(n.other)]}
    if isinstance(n, Cmp):
        return {"cmp": n.op, "a": [to_json(n.left), to_json(n.right)]}
    if isinstance(n, Logic):
        return {"logic": n.op, "a": [to_json(a) for a in n.args]}
    raise ExprError(type(n).__name__)


def from_json(d) -> Node:
    if "n" in d:
        return Num(d["n"], text=d.get("t", ""), conv=bool(d.get("c")))
    if "s" in d:
        return Sym(d["s"])
    if "str" in d:
        return Str(d["str"])
    if "u" in d:
        return Unit(d["u"])
    if "op" in d:
        return Bin(d["op"], from_json(d["a"][0]), from_json(d["a"][1]))
    if "neg" in d:
        return Neg(from_json(d["neg"]))
    if "fn" in d:
        return Call(d["fn"], tuple(from_json(a) for a in d["a"]))
    if "if" in d:
        c, t, o = d["if"]
        return If(from_json(c), from_json(t), from_json(o))
    if "cmp" in d:
        return Cmp(d["cmp"], from_json(d["a"][0]), from_json(d["a"][1]))
    if "logic" in d:
        return Logic(d["logic"], tuple(from_json(a) for a in d["a"]))
    raise ExprError(f"bad expression JSON: {d!r}")
