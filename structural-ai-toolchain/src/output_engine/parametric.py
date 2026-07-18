"""Parametric studies — run one calculation over many cases, tabulate.

The workflow you described: sometimes you want the full detailed
breakdown, sometimes just ``E_c = 30000 MPa``, and sometimes you run the
same check for 10 different inputs and want a single table with every
varying input and result plus a green OK / red NOT OK column — with a
full detailed breakdown for the critical case only.

``ParametricStudy`` reuses ``CalcSheet.recompute`` so the same formulas
drive every case. ``critical_index`` finds the governing case (first
failing, else the worst utilisation) so a report can show that one in
full and the rest as a compact table.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field

from src.models.calculation import CalcSheet, fmt_number


@dataclass
class CaseResult:
    label: str
    inputs: dict
    results: dict
    passed: bool | None

    def verdict(self) -> str:
        if self.passed is None:
            return "—"
        return "OK" if self.passed else "NOT OK"


@dataclass
class ParametricStudy:
    sheet: CalcSheet
    cases: list[dict]                       # list of input-override dicts
    labels: list[str] = field(default_factory=list)

    def run(self) -> list[CaseResult]:
        out: list[CaseResult] = []
        for i, case in enumerate(self.cases):
            r = self.sheet.recompute(case)
            label = self.labels[i] if i < len(self.labels) else f"Case {i + 1}"
            out.append(CaseResult(label, case, r["results"], r["passed"]))
        return out

    def varying_inputs(self) -> list[str]:
        """Input names whose value differs across cases."""
        keys = set().union(*[set(c) for c in self.cases]) if self.cases else set()
        varying = []
        for k in sorted(keys):
            seen = {c.get(k) for c in self.cases}
            if len(seen) > 1:
                varying.append(k)
        return varying

    def critical_index(self, util_var: str | None = None) -> int:
        """Governing case: first failing; else max of ``util_var`` if given,
        else the last case. Used to pick which case to show in full."""
        results = self.run()
        for i, r in enumerate(results):
            if r.passed is False:
                return i
        if util_var:
            return max(range(len(results)),
                       key=lambda i: results[i].results.get(util_var, 0))
        return len(results) - 1

    # -------------------------------------------------------------- #
    def summary_markdown(self, result_vars: list[str] | None = None,
                         inputs: list[str] | None = None) -> str:
        rows = self.run()
        cols_in = inputs if inputs is not None else self.varying_inputs()
        cols_out = result_vars or [c.name for c in self.sheet.checks_result_vars()]
        header = ["Case", *cols_in, *cols_out, "Verdict"]
        lines = ["| " + " | ".join(header) + " |",
                 "|" + "---|" * len(header)]
        for r in rows:
            cells = [r.label]
            cells += [fmt_number(r.inputs.get(k, self.sheet.values.get(k, "")))
                      if isinstance(r.inputs.get(k, self.sheet.values.get(k)), (int, float))
                      else str(r.inputs.get(k, "")) for k in cols_in]
            cells += [fmt_number(r.results.get(v, float("nan"))) for v in cols_out]
            badge = "✅ OK" if r.passed else ("❌ NOT OK" if r.passed is False else "—")
            cells.append(badge)
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)

    def summary_html(self, result_vars: list[str] | None = None,
                    inputs: list[str] | None = None) -> str:
        rows = self.run()
        cols_in = inputs if inputs is not None else self.varying_inputs()
        cols_out = result_vars or [c.name for c in self.sheet.checks_result_vars()]
        esc = _html.escape
        p = ['<table class="inputs summary"><thead><tr>',
             "<th>Case</th>"]
        for k in cols_in:
            p.append(f"<th>{esc(k)}</th>")
        for v in cols_out:
            p.append(f"<th>{esc(v)}</th>")
        p.append("<th>Verdict</th></tr></thead><tbody>")
        for r in rows:
            p.append(f"<tr><td>{esc(r.label)}</td>")
            for k in cols_in:
                val = r.inputs.get(k, self.sheet.values.get(k, ""))
                p.append(f"<td>{fmt_number(val) if isinstance(val,(int,float)) else esc(str(val))}</td>")
            for v in cols_out:
                p.append(f"<td>{fmt_number(r.results.get(v, float('nan')))}</td>")
            if r.passed is None:
                cell = '<td>—</td>'
            else:
                cls = "ok" if r.passed else "no"
                label = "OK" if r.passed else "NOT OK"
                cell = (f'<td><span class="verdict {cls}-inline">{label}'
                        f'</span></td>')
            p.append(cell + "</tr>")
        p.append("</tbody></table>")
        return "\n".join(p)
