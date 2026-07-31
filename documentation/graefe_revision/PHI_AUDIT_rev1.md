# PHI audit — Graefe rev1 submission packet (2026-07-31)

**Scope:** Files under `documentation/graefe_revision/` that could enter a journal zip or supplementary archive.  
**Method:** Pattern scan for patient-name-like OCTA filenames (`name__id_YYYYMMDD_…`), DOB-like `YYYYMMDD` tokens, absolute local paths (`/Users/…`), and email addresses.  
**Status:** Audit listing complete. **Anonymized `submission_safe/` copies not yet generated** — awaiting author decision on what enters the submission zip (see questions below / NOTES).

## Reader-facing manuscript / Response / Suppl prose

| File | PHI finding | Action |
|------|-------------|--------|
| `MNV_Analysis_YY_rev1.md` / `.docx` | Corresponding-author institutional email only (expected on title page) | Keep |
| `Response_to_Reviewers.md` / `.docx` (+ DRAFT) | Same corresponding-author email | Keep |
| `Supplementary_Table_S1.md` / `.docx` | None | Safe |
| `Supplementary_expert_agreement.md` / `.docx` | None (blind_id / aggregate only) | Safe |
| `Table2_raw_metrics.md` | None | Safe |

**Verdict:** Current rev1 / Response / Suppl **prose and tables do not embed patient names, DOBs, or local paths.**

## Grading CSVs

| File | Finding | Risk if zipped |
|------|---------|----------------|
| `grading/expert_grades_blind.csv` | `blind_id` only | **Low** — submission-safe as-is |
| `grading/expert_grades_locked.csv` | `blind_id` only | **Low** |
| `grading/agreement_stats*.csv` / `.md` | Aggregates only | **Low** |
| `grading/confusion_matrix*.csv` | Labels only | **Low** |
| `grading/automated_labels.csv` | Absolute `/Users/yy/…` paths; some `small_3mm`/`small` filenames with **name + ID + DOB** | **High** — do not zip raw |
| `grading/grading_manifest.csv` | Same (paths + PHI filenames) | **High** |
| `grading/grading_subset_meta.csv` | PHI filenames for small_3mm rows | **High** |
| `grading/regrade_queue.csv` / `regrade_log.csv` | Paths + PHI filenames | **High** |
| `grading/README.md` | Absolute local inputdata path | Medium (path disclosure) |

## ICC / analysis CSVs (internal)

| Pattern | Examples | Risk |
|---------|----------|------|
| Long/wide ICC + Caliber score tables | `icc/icc_intra_YY_long.csv`, `icc/icc_multirater_long.csv`, `icc/caliber_*_long.csv`, `icc/caliber_new_score_wide.csv`, … | **High** — `case_id` = full OCTA export name (name + ID + DOB) |
| Case lists / subsets | `icc/icc_subset*_case_list.csv`, `icc/icc_case_list.csv`, `icc/icc_cases_ranked_by_concordance.csv`, exclude lists | **High** |
| Raw observer batches | `icc/incoming/**`, `icc/_raw_from_downloads/**`, `icc/intra/**/*.csv` | **High** |
| Notes citing names | `icc/icc_exclude_worst6_note.md`, `icc/icc_multirater_results_exclude_worst6_names.md` | **High** if attached |
| Aggregate ICC result tables | `icc/*_icc_stats.csv`, `icc/*_results.md` (numeric ICC only, no case columns) | Generally **Low** if no case_id column — verify before zip |
| Primary batch data | `data/MNV_batch_*_small_3mm.csv`, `stats/table3_per_case_scores.csv` (small_3mm rows) | **High** for name-bearing File columns |

## Recommended remediation (pending zip contents decision)

1. **Default submission zip (recommended):** manuscript clean/marked Word, Response Word, Suppl S1 + expert-agreement Word/PDF, figures — **no** `grading/` raw manifests, **no** `icc/` long CSVs, **no** `data/` batch CSVs.
2. If journal requires agreement/ICC raw data: export **anonymized** copies into `documentation/graefe_revision/submission_safe/` with:
   - `case_id` / `File` → stable study codes (`ICC01`… / `B001`… / hash)
   - strip absolute paths
   - drop DOB / sex / name tokens from filenames
3. Keep original PHI-bearing CSVs local-only; do not commit anonymized maps that re-identify.

## Residual risk

- Even “large/########_IVF_…” style IDs may be institution-internal identifiers; prefer blind study codes if any case-level file is submitted.
- Desktop / `octa_images_jpg` paths appear in ICC READMEs — exclude READMEs from zip.
- Author email on title page is intentional, not a finding to remove.

## Open author question

**What exactly goes in the submission zip?** Until answered, no `submission_safe/` anonymization batch has been written (to avoid guessing the packet).
