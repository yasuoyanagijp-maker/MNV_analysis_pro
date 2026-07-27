# Multi-rater ICC (WS1) — inter-observer reproducibility

## Confirmed design (2026-07-27)

| Item | Decision |
|------|----------|
| Observers | **3 independent operators**: YY + 2 external examiners (email replies received) |
| n | **≈ 20 cases** (stratified subset; images + CSVs to be received from collaborators) |
| Primary analysis | **Multi-rater / multilevel ICC** (not pairwise Session1 vs Session2) |
| Metrics | Lesion area, Network Complexity, Caliber Uniformity, Maturity Index |
| Intra-observer (old Flet S1/S2 plan) | **Deprioritized** — optional supplement only if Session 2 data allow; not the primary ICC for the paper |

Legacy same-operator Session1/Session2 files (`icc_session1.csv`, `icc_session2*.csv`, `icc_case_list.csv`, `compute_icc.py`) remain on disk as optional intra-observer material. Do **not** treat them as the primary revision analysis.

## Incoming data layout

Drop collaborator outputs here:

```
documentation/graefe_revision/icc/incoming/
  README.md                 ← schema + drop instructions
  observer_YY/              ← YY scores (+ optional images)
  observer_A/               ← external examiner A
  observer_B/               ← external examiner B
```

Expected contents per observer folder:

- **Required:** one or more CSVs with scores (see columns below)
- **Optional:** source OCTA images or run folders (for audit / re-processing)

Preferred filenames (flexible; script will glob `*.csv`):

- `scores.csv` — long or wide format with required columns
- Or one CSV per case, as long as columns are present

## Required CSV columns

| Column | Description |
|--------|-------------|
| `case_id` | Shared case identifier across observers (must match) |
| `area` | Lesion / MNV area (same units across observers) |
| `complexity` | Network Complexity (standardized score or raw — document which) |
| `caliber_uniformity` | Caliber Uniformity score |
| `maturity` | Maturity Index |
| `observer` | Observer id (`YY`, `A`, `B`, or folder name) |
| `date` | Analysis / ROI date (ISO `YYYY-MM-DD` preferred) |

Aliases accepted by the analysis stub (when implemented):  
`MNV Area` → `area`; `Network Complexity` → `complexity`; `Caliber Uniformity` → `caliber_uniformity`; `Maturity` / `Maturity Index` → `maturity`; `icc_id` / `File` → `case_id`.

Optional helpful columns: `stratum` (`large` / `small` / `small_3mm`), `image_key`, `file_name`, `uuid`, `output_path`, `scale_mm`.

## Primary analysis — multi-rater ICC

**Primary (for paper):** classical **Shrout & Fleiss ICC(2,1)** — two-way **random** effects, **absolute agreement**, **single measures** — for **3 raters × ≈20 cases**, reported **per metric** (area, complexity, caliber uniformity, maturity), each with **95% CI**.

Also report ICC(2,k) (average of k=3 raters) as a secondary column if useful for Methods clarity; primary claim remains ICC(2,1).

### “Multilevel ICC” framing (reviewer-acceptable)

State both approaches in Methods; prefer A when libraries allow:

**Option A — linear mixed model variance components (preferred if feasible)**  
Fit a linear mixed model with random case + random observer (e.g. `statsmodels` MixedLM, or R `lme4` via `rpy2` if available):

\[
Y_{ij} = \mu + u_{\mathrm{case},i} + v_{\mathrm{observer},j} + \varepsilon_{ij}
\]

Report:

\[
\mathrm{ICC}_{\mathrm{case}} = \frac{\sigma^2_{\mathrm{case}}}{\sigma^2_{\mathrm{case}} + \sigma^2_{\mathrm{observer}} + \sigma^2_{\varepsilon}}
\]

(If the model omits a random observer and observers are fixed, use case / (case + residual) and disclose that choice.)

**Option B — classical multi-rater ICC**  
ICC(2,1) / ICC(2,k) via ANOVA mean squares (or `pingouin.intraclass_corr` with `targets=case_id`, `raters=observer`, `ratings=<metric>`).

**Reporting rule for this revision:**

1. **Primary:** multi-rater **ICC(2,1)** + 95% CI per metric (Option B; implementable in numpy/scipy or pingouin).
2. **If** `pingouin` and/or `statsmodels` / `rpy2` are available: also report **multilevel variance-component ICC** (Option A) as sensitivity / Methods supplement.
3. Do **not** claim completion until ≥3 observers × shared `case_id`s are locked.

## Compute (when data arrive)

```bash
.venv/bin/python scripts/graefe_revision/compute_icc_multirater.py
```

- No / incomplete incoming CSVs → prints `awaiting incoming data` and exits (no claim of completion).
- When ready → writes `icc/multirater_icc_stats.csv` and `.md` (paths TBD when schema locked).

Optional intra-observer supplement (legacy):

```bash
.venv/bin/python scripts/graefe_revision/compute_icc.py   # Session1 vs Session2; only if S2 filled
```

## Checklist — when collaborator data arrive

- [ ] Receive images + score CSVs from observer A and B (and YY if not already local)
- [ ] Drop files under `incoming/observer_A/`, `incoming/observer_B/`, `incoming/observer_YY/`
- [ ] Confirm shared `case_id` set (n ≈ 20; note any missing cases per observer)
- [ ] Confirm metric units / score definitions match across observers (same pipeline / scale)
- [ ] Confirm each row has `observer` + `date`
- [ ] Lock incoming folders (no further edits) → run `compute_icc_multirater.py`
- [ ] Fill Response letter Comment 4 placeholders with ICC(2,1) (+ CI) per metric
- [ ] Methods: state ICC(2,1) primary; add multilevel VC ICC if computed
- [ ] Limitations: note intra-observer as optional / not primary if S2 not completed; note n≈20 stratified subset

## Status

- [x] Protocol rewritten for 3-observer multi-rater ICC (n≈20)
- [x] `incoming/` drop folders scaffolded
- [x] `compute_icc_multirater.py` stub (awaits data)
- [ ] Incoming CSVs from collaborators
- [ ] Multi-rater ICC(2,1) + 95% CI per metric
- [ ] Optional multilevel VC ICC (if libraries allow)
- [ ] Fill Response letter placeholders
- [ ] Optional: legacy Session 2 / intra-observer supplement
