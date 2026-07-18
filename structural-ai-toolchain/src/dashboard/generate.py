"""Central dashboard — a human-readable, self-contained HTML view of the
toolchain for people who don't live in Git/GitLab.

Shows, without metadata overload:
- every hosted tool: title, where it came from (converted vs native),
  review status, who last edited it (from git), and a link to its report
- what each tool REUSES (library atoms) — the "recycled" view
- the digested formula library as a drill-down tree + live search box
- which projects a tool has been used in (from the manifest, if present)

Generated as one self-contained .html so it opens in any browser now and
is a natural stepping stone to the future web-hosted version.
"""

from __future__ import annotations

import html as _html
import json
import subprocess
from pathlib import Path

from src.library import all_atoms, catalog


def _git_last_edit(path: Path, repo_root: Path) -> tuple[str, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1",
             "--format=%an\t%ar", "--", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            who, when = out.stdout.strip().split("\t", 1)
            return who, when
    except Exception:
        pass
    return "—", "—"


def _load_tools(repo_dir: Path, repo_root: Path) -> list[dict]:
    tools = []
    for manifest in sorted(repo_dir.glob("*/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = data.get("tool_id", manifest.parent.name)
        who, when = _git_last_edit(manifest.parent, repo_root)
        reused = [f["match"] for f in data.get("formula_analysis", [])
                  if f.get("status") == "matches_atom" and f.get("match")]
        report = manifest.parent / "reports" / f"{slug}.html"
        tools.append({
            "slug": slug,
            "title": data.get("title", slug),
            "source_format": data.get("source_format", "?"),
            "status": data.get("status", "?"),
            "reference": data.get("reference", ""),
            "n_inputs": sum(1 for v in data.get("variables", [])
                            if v.get("role") == "input"),
            "n_formulas": sum(1 for v in data.get("variables", [])
                              if v.get("role") == "derived"),
            "reused_atoms": sorted(set(reused)),
            "projects": data.get("projects", []),
            "edited_by": who,
            "edited_when": when,
            "report": str(report.relative_to(repo_dir.parent))
            if report.exists() else "",
        })
    return tools


def _source_badge(fmt: str) -> str:
    native = fmt == "native"
    label = "NATIVE" if native else f"CONVERTED · {fmt.upper()}"
    color = "#6b46c1" if native else "#0f766e"
    return f'<span class="badge" style="background:{color}">{label}</span>'


def _status_badge(status: str) -> str:
    colors = {"approved": "#1E7D32", "in-review": "#b7791f",
              "native-unreviewed": "#b7791f",
              "converted-unreviewed": "#c05621"}
    color = colors.get(status, "#4a5568")
    return f'<span class="badge" style="background:{color}">{_html.escape(status)}</span>'


_CSS = """
*{box-sizing:border-box}body{font-family:"Segoe UI",Helvetica,Arial,sans-serif;
margin:0;background:#f5f7fa;color:#1a202c}
.top{background:#0033A0;color:#fff;padding:16px 28px}
.top h1{margin:0;font-size:20px}.top p{margin:4px 0 0;opacity:.85;font-size:13px}
.wrap{max-width:1100px;margin:0 auto;padding:20px 28px}
.search{width:100%;padding:11px 14px;font-size:15px;border:1px solid #cbd5e0;
border-radius:8px;margin:14px 0}
h2.sec{font-size:15px;text-transform:uppercase;letter-spacing:.6px;color:#0033A0;
margin:26px 0 10px;border-bottom:2px solid #e2e8f0;padding-bottom:6px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;
margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.card h3{margin:0 0 6px;font-size:16px}.card h3 a{color:#0033A0;text-decoration:none}
.badge{display:inline-block;color:#fff;font-size:11px;font-weight:700;padding:2px 8px;
border-radius:4px;margin-right:6px;letter-spacing:.4px}
.meta{font-size:12.5px;color:#5a6472;margin-top:6px}
.reuse{margin-top:8px;font-size:12.5px}
.chip{display:inline-block;background:#EEF2F8;color:#0033A0;border-radius:12px;
padding:2px 10px;margin:2px 4px 2px 0;font-size:11.5px}
.tree{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px 16px;
font-size:13px}
.tree details{margin-left:10px}.tree summary{cursor:pointer;padding:2px 0}
.tree .atom{margin-left:26px;color:#334155;padding:1px 0}
.tree .atom code{color:#0f766e}
.muted{color:#7a828e}
.stat{display:inline-block;margin-right:20px;font-size:13px}
.stat b{font-size:20px;color:#0033A0;display:block}
"""


def generate_dashboard(repo_dir: str | Path, out_path: str | Path | None = None) -> Path:
    repo_dir = Path(repo_dir)
    repo_root = repo_dir.parent
    while not (repo_root / ".git").exists() and repo_root != repo_root.parent:
        repo_root = repo_root.parent
    tools = _load_tools(repo_dir, repo_root)
    atoms = all_atoms()
    esc = _html.escape

    p: list[str] = ["<!DOCTYPE html><html><head><meta charset='utf-8'>",
                    "<title>Structural AI Toolchain — Dashboard</title>",
                    f"<style>{_CSS}</style></head><body>"]
    p.append('<div class="top"><h1>Structural AI Toolchain — Dashboard</h1>'
             '<p>What is hosted, what is recycled, and where it came from.</p></div>')
    p.append('<div class="wrap">')

    n_reuse = sum(len(t["reused_atoms"]) for t in tools)
    p.append('<div class="card">'
             f'<span class="stat"><b>{len(tools)}</b>hosted tools</span>'
             f'<span class="stat"><b>{len(atoms)}</b>library formulas (atoms)</span>'
             f'<span class="stat"><b>{n_reuse}</b>reuse links</span>'
             f'<span class="stat"><b>{sum(1 for t in tools if t["status"].startswith("approved"))}</b>approved</span>'
             "</div>")

    p.append('<input class="search" id="q" placeholder="Search tools and '
             'formulas… (title, code clause, symbol)" '
             'oninput="filt()">')

    # ---- Tools ----
    p.append('<h2 class="sec">Hosted tools</h2>')
    for t in tools:
        report_link = (f'<a href="{esc(t["report"])}">open report</a>'
                       if t["report"] else '<span class="muted">no report yet</span>')
        reuse = ""
        if t["reused_atoms"]:
            chips = "".join(f'<span class="chip">♻ {esc(a)}</span>'
                            for a in t["reused_atoms"])
            reuse = f'<div class="reuse"><b>Recycles:</b> {chips}</div>'
        projects = ""
        if t["projects"]:
            projects = ' · Projects: ' + ", ".join(esc(x) for x in t["projects"])
        search_blob = esc(" ".join([t["title"], t["slug"], t["reference"],
                                    " ".join(t["reused_atoms"])]).lower())
        p.append(
            f'<div class="card tool" data-s="{search_blob}">'
            f'<h3><a href="{esc(t["report"])}">{esc(t["title"])}</a></h3>'
            f'{_source_badge(t["source_format"])}{_status_badge(t["status"])}'
            f'<div class="meta">{esc(t["reference"] or "—")} · '
            f'{t["n_inputs"]} inputs · {t["n_formulas"]} formulas · '
            f'last edit by <b>{esc(t["edited_by"])}</b> {esc(t["edited_when"])}'
            f'{projects} · {report_link}</div>'
            f'{reuse}</div>'
        )

    # ---- Atom library tree ----
    p.append('<h2 class="sec">Digested formula library</h2>')
    p.append('<div class="tree">')
    tree = catalog()
    atom_by_id = {a.atom_id: a for a in atoms}
    for juris in sorted(tree):
        p.append(f"<details open><summary><b>{esc(juris)}</b></summary>")
        for code in sorted(tree[juris]):
            p.append(f"<details><summary>{esc(code)}</summary>")
            for chapter in sorted(tree[juris][code]):
                p.append(f"<details><summary>{esc(chapter)}</summary>")
                for clause in sorted(tree[juris][code][chapter]):
                    for aid in sorted(tree[juris][code][chapter][clause]):
                        a = atom_by_id.get(aid)
                        if not a:
                            continue
                        blob = esc(f"{aid} {a.description} {a.clause} {a.result}".lower())
                        p.append(
                            f'<div class="atom" data-s="{blob}">'
                            f'<code>{esc(a.result)} = {esc(a.expression)}</code> '
                            f'<span class="muted">— {esc(a.description)} '
                            f'[{esc(a.clause or a.code)}]</span></div>'
                        )
                p.append("</details>")
            p.append("</details>")
        p.append("</details>")
    p.append("</div>")

    p.append("</div>")  # wrap
    p.append("""<script>
function filt(){var q=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('.tool,.atom').forEach(function(e){
 e.style.display = (!q||e.dataset.s.indexOf(q)>=0)?'':'none';});}
</script>""")
    p.append("</body></html>")

    out = Path(out_path) if out_path else repo_dir / "dashboard.html"
    out.write_text("\n".join(p), encoding="utf-8")
    return out
