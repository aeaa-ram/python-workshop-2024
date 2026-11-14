"""Excel formula text -> expression tree.

A small recursive-descent parser for the formula language of a calculation
sheet: arithmetic, comparisons, cell references, ranges inside aggregate
functions, and the usual maths and logic functions.  Excel's own rules are
kept where they differ from Python: unary minus binds tighter than ``^`` and
``^`` associates to the left.
"""
from __future__ import annotations

import re
from typing import Callable

from .. import expr as X

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<err>\#(?:REF!|N/A|VALUE!|DIV/0!|NAME\?|NUM!|NULL!))
  | (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<sheet>(?:'(?:[^']|'')+'|\[\d+\][^!'\s(),]*|[A-Za-z_][\w.]*)!)
  | (?P<cell>\$?[A-Za-z]{1,3}\$?\d+(?![\w.(]))
  | (?P<name>[A-Za-z_\\][\w.\\]*)
  | (?P<op><=|>=|<>|[-+*/^&=<>%(),:;])
""", re.X)


class FormulaError(X.ExprError):
    pass


def tokenize(text: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise FormulaError(f"unexpected character {text[pos]!r} in formula")
        pos = m.end()
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group(kind)))
    return out


class Parser:
    """``ref(sheet, cell)`` returns the tree for a cell reference (usually a
    Sym), or None for an empty cell.  ``sheet`` is None for the formula's own
    sheet."""

    def __init__(self, text: str, ref: Callable[[str | None, str], X.Node | None],
                 name: Callable[[str], X.Node | None] | None = None):
        if text.startswith("="):
            text = text[1:]
        self.toks = tokenize(text)
        self.i = 0
        self.ref = ref
        self.name = name

    # ---- token helpers ----------------------------------------------------
    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else ("end", "")

    def take(self, value: str | None = None):
        kind, val = self.peek()
        if value is not None and val != value:
            raise FormulaError(f"expected {value!r}, found {val!r}")
        self.i += 1
        return kind, val

    def at(self, *values: str) -> bool:
        kind, val = self.peek()
        return kind == "op" and val in values

    # ---- grammar ----------------------------------------------------------
    def parse(self) -> X.Node:
        node = self.comparison()
        if self.peek()[0] != "end":
            raise FormulaError(f"unexpected {self.peek()[1]!r}")
        return node

    def comparison(self) -> X.Node:
        left = self.concat()
        while self.at("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]
            right = self.concat()
            left = X.Cmp({"=": "==", "<>": "!="}.get(op, op), left, right)
        return left

    def concat(self) -> X.Node:
        left = self.additive()
        if self.at("&"):
            raise FormulaError("text concatenation (&) is not a calculation")
        return left

    def additive(self) -> X.Node:
        left = self.term()
        while self.at("+", "-"):
            op = self.take()[1]
            left = X.Bin(op, left, self.term())
        return left

    def term(self) -> X.Node:
        left = self.power()
        while self.at("*", "/"):
            op = self.take()[1]
            left = X.Bin(op, left, self.power())
        return left

    def power(self) -> X.Node:
        left = self.unary()
        while self.at("^"):
            self.take()
            left = X.Bin("**", left, self.unary())
        return left

    def unary(self) -> X.Node:
        if self.at("-"):
            self.take()
            arg = self.unary()
            if isinstance(arg, X.Num):
                return X.Num(-arg.value, text="-" + (arg.text or str(arg.value)))
            return X.Neg(arg)
        if self.at("+"):
            self.take()
            return self.unary()
        return self.postfix()

    def postfix(self) -> X.Node:
        node = self.primary()
        while self.at("%"):
            self.take()
            node = X.Bin("/", node, X.Num(100, "100"))
        return node

    def primary(self) -> X.Node:
        kind, val = self.take()
        if kind == "num":
            v = float(val)
            return X.Num(int(v) if v.is_integer() and "." not in val and "e" not in val.lower() else v, text=val)
        if kind == "str":
            return X.Str(val[1:-1].replace('""', '"'))
        if kind == "err":
            raise FormulaError(f"formula contains the error {val}")
        if kind == "op" and val == "(":
            node = self.comparison()
            self.take(")")
            return node
        if kind == "sheet":
            sheet = val[:-1]
            if sheet.startswith("["):
                raise FormulaError("reference to another workbook")
            if sheet.startswith("'"):
                sheet = sheet[1:-1].replace("''", "'")
                if sheet.startswith("["):
                    raise FormulaError("reference to another workbook")
            k2, cell = self.take()
            if k2 != "cell":
                raise FormulaError("unsupported sheet reference")
            return self.cell(sheet, cell)
        if kind == "cell":
            return self.cell(None, val)
        if kind == "name":
            if self.at("("):
                return self.call(val.upper())
            up = val.upper()
            if up == "TRUE":
                return X.Num(1, "TRUE")
            if up == "FALSE":
                return X.Num(0, "FALSE")
            if self.name:
                hit = self.name(val)
                if hit is not None:
                    return hit
            raise FormulaError(f"defined name {val!r} cannot be resolved")
        raise FormulaError(f"unexpected {val!r}")

    def cell(self, sheet, cell) -> X.Node:
        if self.at(":"):
            raise FormulaError("a cell range is only supported inside SUM, MIN, MAX, AVERAGE")
        node = self.ref(sheet, cell.replace("$", "").upper())
        return node if node is not None else X.Num(0, "0")

    def args(self) -> list:
        """Arguments of a call; a range argument becomes a list of trees."""
        self.take("(")
        out = []
        if self.at(")"):
            self.take()
            return out
        while True:
            out.append(self.arg())
            if self.at(",", ";"):
                self.take()
                continue
            self.take(")")
            return out

    def arg(self):
        # range?  [sheet!]A1:B2
        save = self.i
        sheet = None
        kind, val = self.peek()
        if kind == "sheet":
            sheet = val[:-1].strip("'")
            self.i += 1
            kind, val = self.peek()
        if kind == "cell" and self.i + 2 < len(self.toks) + 1 and self.toks[self.i + 1:self.i + 2] == [("op", ":")]:
            first = val
            self.i += 2
            k2, last = self.take()
            if k2 != "cell":
                raise FormulaError("unsupported range")
            return ("range", [self.ref(sheet, c) for c in _expand(first, last)])
        self.i = save
        return self.comparison()

    def call(self, fn: str) -> X.Node:
        raw = self.args()
        flat: list[X.Node] = []
        for a in raw:
            if isinstance(a, tuple):
                flat.extend(x for x in a[1] if x is not None)
            else:
                flat.append(a)
        if any(isinstance(a, tuple) for a in raw) and fn not in ("SUM", "MIN", "MAX", "AVERAGE", "PRODUCT", "COUNT"):
            raise FormulaError(f"{fn}() with a cell range is not supported")
        n = len(flat)

        def need(*counts):
            if n not in counts:
                raise FormulaError(f"{fn}() with {n} argument(s) is not supported")

        simple = {"ABS": "abs", "SQRT": "sqrt", "SIN": "sin", "COS": "cos", "TAN": "tan",
                  "ASIN": "asin", "ACOS": "acos", "ATAN": "atan", "EXP": "exp", "LN": "ln",
                  "LOG10": "log10", "RADIANS": "radians", "DEGREES": "degrees"}
        if fn in simple:
            need(1)
            return X.Call(simple[fn], (flat[0],))
        if fn in ("MIN", "MAX"):
            if n == 0:
                raise FormulaError(f"{fn}() of nothing")
            return flat[0] if n == 1 else X.Call(fn.lower(), tuple(flat))
        if fn == "PI":
            need(0)
            return X.Call("pi", ())
        if fn == "IF":
            need(2, 3)
            return X.If(flat[0], flat[1], flat[2] if n == 3 else X.Num(0, "FALSE"))
        if fn in ("AND", "OR"):
            return X.Logic(fn.lower(), tuple(flat))
        if fn == "NOT":
            need(1)
            return X.Logic("not", (flat[0],))
        if fn == "POWER":
            need(2)
            return X.Bin("**", flat[0], flat[1])
        if fn == "SUM":
            if n == 0:
                return X.Num(0, "0")
            out = flat[0]
            for a in flat[1:]:
                out = X.Bin("+", out, a)
            return out
        if fn == "PRODUCT":
            need(*range(1, 60))
            return X.product(flat)
        if fn == "AVERAGE":
            need(*range(1, 200))
            total = flat[0]
            for a in flat[1:]:
                total = X.Bin("+", total, a)
            return X.Bin("/", total, X.Num(n, str(n)))
        if fn == "COUNT":
            return X.Num(n, str(n))
        if fn == "ROUND":
            need(1, 2)
            return X.Call("round", tuple(flat))
        if fn in ("ROUNDUP", "ROUNDDOWN"):
            need(1, 2)
            f = "ceil" if fn == "ROUNDUP" else "floor"
            if n == 1 or flat[1] == X.Num(0):
                return X.Call(f, (flat[0],))
            scale = X.Bin("**", X.Num(10, "10"), flat[1])
            return X.Bin("/", X.Call(f, (X.Bin("*", flat[0], scale),)), scale)
        if fn == "INT":
            need(1)
            return X.Call("floor", (flat[0],))
        if fn in ("CEILING", "FLOOR", "CEILING.MATH", "FLOOR.MATH", "MROUND"):
            need(1, 2)
            f = {"C": "ceil", "F": "floor", "M": "round"}[fn[0]]
            if n == 1:
                return X.Call(f, (flat[0],))
            return X.Bin("*", X.Call(f, (X.Bin("/", flat[0], flat[1]),)), flat[1])
        if fn == "LOG":
            need(1, 2)
            if n == 1:
                return X.Call("log10", (flat[0],))
            return X.Bin("/", X.Call("ln", (flat[0],)), X.Call("ln", (flat[1],)))
        if fn == "MOD":
            need(2)
            return X.Bin("-", flat[0], X.Bin("*", flat[1], X.Call("floor", (X.Bin("/", flat[0], flat[1]),))))
        if fn == "SIGN":
            need(1)
            return X.If(X.Cmp(">", flat[0], X.Num(0)), X.Num(1),
                        X.If(X.Cmp("<", flat[0], X.Num(0)), X.Num(-1), X.Num(0)))
        if fn == "SQRTPI":
            need(1)
            return X.Call("sqrt", (X.Bin("*", flat[0], X.Call("pi", ())),))
        raise FormulaError(f"function {fn}() is not supported")


def _col_index(col: str) -> int:
    n = 0
    for ch in col.upper():
        n = n * 26 + ord(ch) - 64
    return n


def col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _expand(first: str, last: str) -> list[str]:
    a = re.fullmatch(r"\$?([A-Za-z]+)\$?(\d+)", first)
    b = re.fullmatch(r"\$?([A-Za-z]+)\$?(\d+)", last)
    c1, c2 = sorted((_col_index(a.group(1)), _col_index(b.group(1))))
    r1, r2 = sorted((int(a.group(2)), int(b.group(2))))
    if (c2 - c1 + 1) * (r2 - r1 + 1) > 5000:
        raise FormulaError("cell range too large")
    return [f"{col_letter(c)}{r}" for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


def parse_formula(text: str, ref, name=None) -> X.Node:
    return Parser(text, ref, name).parse()
