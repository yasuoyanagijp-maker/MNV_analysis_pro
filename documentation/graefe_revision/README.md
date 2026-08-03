# Graefe major revision — local working tree

**Do not push this branch to remote** (`graefe/major-revision-analyses` stays local unless you explicitly ask to push).

Author navigation map for `documentation/graefe_revision/` (tidied **2026-08-03** after journal submission). Analyses for Comment 2 / 4 / 5 and rev1 packet are **complete**. **`submission_package_20260731/` is the frozen submission snapshot — do not reshape it for cleanliness.**

## Quick start / どこに何があるか

| Need / 用途 | Go here / 場所 |
|------|---------|
| **提出スナップショット（触らない）** | [`submission_package_20260731/`](submission_package_20260731/) — see `README_提出内容.txt` |
| **初回提出原稿・図表（original）** | [`original_submission/`](original_submission/) |
| **改訂作業ミラー (rev1)** | Root: `MNV_Analysis_YY_rev1.*`, `Response_to_Reviewers.*`, `Supplementary_*.*`（提出物と同期） |
| **内部メモ・変更履歴** | [`working/`](working/) — NOTES / CHANGELOG / PHI audit / Table2 helper / ref renumber map |
| ICC (inter + intra) | [`icc/`](icc/) — **COMPLETED** |
| Expert grading / κ | [`grading/`](grading/) — **COMPLETED** |
| Table 3 ε² | [`stats/`](stats/) — **COMPLETED** |
| Batch CSV source | [`data/`](data/) |
| Fig3 working + intermediates | [`figures/`](figures/) |
| Superseded drafts / old snapshots | [`_archive/`](_archive/) |

## Journal vs internal

| For journal / zip | Internal only (do not submit) |
|-------------------|-------------------------------|
| `submission_package_20260731/**` (**frozen**; leave layout alone) | `icc/`, `grading/`, `data/`, `stats/` (CSVs may contain PHI-like filenames) |
| Root mirrors of MS / tables / legends / Response / Suppl / figures | `working/**`, `_archive/**`, `original_submission/**` |
| | `figures/_fig3_runs/`, `figures/_fig3_rebuild_furukawa/`, `icc/_raw_from_downloads/`, `grading/previews/` |

Reader-facing Caliber term: **Standardized Caliber Uniformity Score** (device-/stratum-locked = **default**). **PCA-based Caliber Uniformity Score (legacy)** = sensitivity only. Do not use “U2” in manuscript / Response prose (internal paths may still say `caliber_u2_*`).

## Folder map (post-tidy 2026-08-03)

```
documentation/graefe_revision/
├── README.md                          ← this map（日英）
├── submission_package_20260731/       ← FROZEN journal pack（中身は整理しない）
├── original_submission/               ← 初回提出の原本
├── MNV_Analysis_YY_rev1.*             ← File 3 作業ミラー（package と同期）
├── MNV_Analysis_YY_rev1_manuscript_changes_marked.docx  ← File 2 ミラー
├── MNV_Analysis_YY_rev1_tables.*      ← Tables 1–5 ミラー
├── MNV_Analysis_YY_rev1_figure_legends.*
├── Response_to_Reviewers.*            ← File 1 ミラー（DRAFT は _archive）
├── Supplementary_*.*
├── working/                           ← NOTES / CHANGELOG / PHI / helpers / ref map
├── figures/                           ← Fig3 + _fig3_* intermediates
├── icc/                               ← ICC 解析アーカイブ（完了）
├── grading/                           ← 盲検 grading + κ（完了）
├── data/                              ← 回収バッチ CSV
├── stats/                             ← Table3 ε²
└── _archive/                          ← DRAFT Response・旧 clean スナップ・古いチェックリスト
```

## Original vs rev1 vs submission（見分け方）

| Layer | What | Where |
|-------|------|-------|
| **Original submission** | First journal manuscript + tables + Fig1/Fig2 | `original_submission/` |
| **Rev1 working mirrors** | Same bytes as submitted File 1–3 / tables / Suppl where applicable | Root `*_rev1*` + `Response_*` + `figures/` |
| **Journal pack** | **Frozen** upload copies | `submission_package_20260731/` — **do not reorganize**; sync *from* pack *to* root if parent drifts |
| **Internal working notes** | Author decisions, changelog, PHI audit | `working/` |

## Status by workstream

| Area | Status | Key outputs |
|------|--------|-------------|
| WS1 Inter ICC (3×n=46) | **Done** | `icc/icc_multirater_results.md` + device-locked Caliber in `icc/caliber_u2_device_std_icc_results.md`; default Caliber ICC 0.770; also in **Table 1** |
| WS1 Intra ICC (YY n=46) | **Done** | `icc/icc_intra_YY_results.md`; Caliber 0.925; also in **Table 1** |
| WS2 Expert–algorithm κ | **Done** | `grading/agreement_stats.md`; κ 0.507 (n=54) |
| WS4 Effect sizes | **Done** | `stats/table3_effect_sizes.md` |
| Rev1 + Response + Suppl | **Submitted** | Frozen in `submission_package_20260731/`; root mirrors synced 2026-08-03 |

## Root files (brief)

| File | Role |
|------|------|
| `MNV_Analysis_YY_rev1.md` / `.docx` | Revised manuscript **clean** = journal File 3 mirror |
| `MNV_Analysis_YY_rev1_manuscript_changes_marked.docx` | Journal **File 2** mirror (Word Compare redline) |
| `MNV_Analysis_YY_rev1_tables.md` / `.docx` | Tables 1–5 mirror |
| `MNV_Analysis_YY_rev1_figure_legends.md` / `.docx` | Figure 1–3 legends (separate file) |
| `Response_to_Reviewers.md` / `.docx` | Point-by-point response (**File 1**) |
| `Supplementary_*.*` | Suppl Table S1 + expert agreement |

## `working/` (internal)

| File | Role |
|------|------|
| `MNV_Analysis_YY_rev1_NOTES.md` | Author decisions / figure notes |
| `MNV_Analysis_YY_rev1_CHANGELOG.md` | Rev1 diff log |
| `PHI_AUDIT_rev1.md` | PHI scan notes before zip |
| `Table2_raw_metrics.md` | Internal Table 2 helper |
| `_ref_renumber_map_20260803.txt` | Reference renumber map (copy; package keeps its own) |

## Subfolder READMEs

| Path | Role |
|------|------|
| [`original_submission/`](original_submission/) | Original manuscript + Fig1/Fig2 |
| [`working/`](working/) | Internal notes / helpers |
| [`icc/README.md`](icc/README.md) | Inter/intra ICC index — **COMPLETED** |
| [`grading/README.md`](grading/README.md) | Blind grading — **COMPLETED** |
| [`data/README.md`](data/README.md) | Recovered batch CSVs |
| [`figures/README.md`](figures/README.md) | Fig3 working assets |
| [`submission_package_20260731/README_提出内容.txt`](submission_package_20260731/README_提出内容.txt) | What is in the journal packet |
| [`_archive/README.md`](_archive/README.md) | Superseded drafts / snapshots |

## Archive

Superseded checklist, DRAFT Response twins, and redundant `*_clean.docx` snapshot live under [`_archive/`](_archive/). Prefer this file over anything there.
