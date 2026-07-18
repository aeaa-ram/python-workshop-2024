# /repository — Single Source of Truth

Every converted tool lives here as a folder written by The Grinder:

```
<tool_slug>/
  <tool_slug>.py     # executable CalcSheet builder — THE tool
  <tool_slug>.md     # standardized doc (see docs/TOOL_TEMPLATE.md)
  manifest.json      # metadata consumed by the knowledge graph
  source/<original>  # legacy file kept for provenance
  reports/           # generated reports (rebuild with `python main.py render <slug>`)
```

Rules:

1. Never hand-edit numbers in a `.md` — change the `.py` and re-render.
2. New tools enter only through The Grinder (`python main.py grind ...`)
   so the Gatekeeper can veto duplicates.
3. `status` in the manifest/front matter tracks review state:
   `converted-unreviewed → in-review → approved`.
