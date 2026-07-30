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

Optional intra-observer supplement (YY test–retest on the same n=46 Files):

```bash
# Protocol + case list: icc/intra/README.md
# Drop Session2 CSV → icc/intra/incoming_session2/
.venv/bin/python scripts/graefe_revision/compute_icc_intra.py
```

Legacy Flet S1/S2 (`icc_session1.csv` / `compute_icc.py`) is a different image set — do not mix with n=46.

## Checklist — when collaborator data arrive

- [x] Receive score CSVs from observer A (Inoue) and B (Osada) and YY
- [x] Drop files under `incoming/observer_A/`, `incoming/observer_B/`, `incoming/observer_YY/` (+ clear-name aliases)
- [x] Confirm shared `case_id` set (**n = 46**; union = intersection; no dropouts)
- [x] Confirm metric units / score definitions match (same pipeline columns)
- [x] Run `compute_icc_multirater.py`
- [x] Fill Response letter Comment 4 with ICC(2,1) (+ CI) per metric
- [x] Methods note: ICC(2,1) primary; multilevel VC ICC reported
- [ ] Limitations: note intra-observer not completed; n=46 shared set

## Status

- [x] Protocol rewritten for 3-observer multi-rater ICC
- [x] `incoming/` drop folders scaffolded (+ Inoue/Osada aliases)
- [x] Incoming CSVs from YY, Inoue, Osada (n=46 matched)
- [x] Multi-rater ICC(2,1) + 95% CI per metric (`icc_multirater_results.md`)
- [x] Pairwise ICC + multilevel / ANOVA variance-component ICC
- [x] Response letter Comment 4 filled
- [ ] Optional: YY intra-observer Session 2 (n=46) → `icc/intra/` + `compute_icc_intra.py`

## Sensitivity subset (n=20 most concordant)

Optional upper-bound ICC on nested concordance subsets (n=20/30/35/40; lowest mean z-scored cross-rater range). See `icc_cases_ranked_by_concordance.csv`, `icc_multirater_concordance_ladder.md`, and `icc_multirater_results_subset*.md`. Does **not** replace primary n=46 Comment 4 numbers.
