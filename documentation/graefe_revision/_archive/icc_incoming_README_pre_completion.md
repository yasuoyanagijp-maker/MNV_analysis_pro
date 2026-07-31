# Incoming multi-rater ICC data

Drop each observer’s score CSVs (and optional images) into the matching folder.

```
incoming/
  observer_YY/
  observer_A/
  observer_B/
```

## What to ask collaborators to send

For each of ~20 shared cases:

1. **Score CSV** (required) with columns:
   - `case_id` — must match the shared case list across observers
   - `area` — lesion / MNV area
   - `complexity` — Network Complexity score
   - `caliber_uniformity` — Caliber Uniformity score
   - `maturity` — Maturity Index
   - `observer` — e.g. `A` / `B` / `YY`
   - `date` — analysis date (`YYYY-MM-DD`)
2. **Optional:** OCTA images used, or Flet/run output folders (`uuid`) for audit

One combined `scores.csv` per observer is fine. Column name aliases (`MNV Area`, `Network Complexity`, etc.) are OK if documented.

## After drop

```bash
.venv/bin/python scripts/graefe_revision/compute_icc_multirater.py
```

Until CSVs are present for all three observers, the script exits with `awaiting incoming data`.
