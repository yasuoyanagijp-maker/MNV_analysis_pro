# Graefe major revision — local working tree

**Do not push this branch to remote** (`graefe/major-revision-analyses` stays local unless you explicitly ask to push).

Author navigation map for `documentation/graefe_revision/` (2026-08-01). Analyses for Comment 2 / 4 / 5 and rev1 packet are **complete**; remaining work is packaging / journal upload, not re-opening ICC or grading.

## Quick start / どこに何があるか

| Need / 用途 | Go here / 場所 |
|------|---------|
| **初回提出原稿・図表（original）** | [`original_submission/`](original_submission/) |
| **提出物（雑誌用 / journal pack）** | [`submission_package_20260731/`](submission_package_20260731/) — see `README_提出内容.txt` |
| **改訂作業原本 (rev1)** | Root: `MNV_Analysis_YY_rev1.*`, `Response_to_Reviewers.*`, `Supplementary_*.*` |
| ICC (inter + intra) | [`icc/`](icc/) — **COMPLETED** |
| Expert grading / κ | [`grading/`](grading/) — **COMPLETED** |
| Table 3 ε² | [`stats/`](stats/) — **COMPLETED** |
| Batch CSV source | [`data/`](data/) |
| Fig3 working + intermediates | [`figures/`](figures/) |
| Historical WIP checklist | [`_archive/`](_archive/) |

## Journal vs internal

| For journal / zip | Internal only (do not submit) |
|-------------------|-------------------------------|
| `submission_package_20260731/**` | `icc/`, `grading/`, `data/`, `stats/` (CSVs may contain PHI-like filenames) |
| Rev1 manuscript + **tables** + **figure legends** + Response + Suppl + figures | `*_NOTES.md`, `*_CHANGELOG.md`, `PHI_AUDIT_rev1.md`, `Table2_raw_metrics.md` |
| | `Response_to_Reviewers_DRAFT.*`, `original_submission/**` |
| | `_archive/`, `figures/_fig3_runs/`, `figures/_fig3_rebuild_furukawa/`, `icc/_raw_from_downloads/`, `grading/previews/` |

Reader-facing Caliber term: **Standardized Caliber Uniformity Score** (device-/stratum-locked = **default**). **PCA-based Caliber Uniformity Score (legacy)** = sensitivity only. Do not use “U2” in manuscript / Response prose (internal paths may still say `caliber_u2_*`).

## Folder map

```
documentation/graefe_revision/
├── README.md                          ← this map（日英）
├── original_submission/               ← 初回提出の原本（moved; not duplicated into package）
│   ├── MNV_Analysis_YY.docx
│   ├── manuscript_text.txt
│   ├── MNV_analysis_tables_original.docx
│   └── figures/                       ← original Fig1 + Fig2 (png/tiff)
├── submission_package_20260731/       ← 提出用コピー（中身のパスは触らない；再コピーで更新）
├── MNV_Analysis_YY_rev1.*             ← 改訂原稿（作業原本）
├── MNV_Analysis_YY_rev1_tables.*      ← Tables 1–5（Table 1: Variable | Description | ICC）
├── MNV_Analysis_YY_rev1_figure_legends.*
├── Response_to_Reviewers.*            ← 査読応答（提出版；DRAFT は作業同期）
├── Supplementary_*.*
├── figures/                           ← Fig3 + caption/legend + _fig3_* intermediates
├── icc/                               ← ICC 解析アーカイブ（完了）
├── grading/                           ← 盲検 grading + κ（完了）
├── data/                              ← 回収バッチ CSV
├── stats/                             ← Table3 ε²
└── _archive/                          ← 古いチェックリスト等
```

**Nested path note:** No mistaken nest such as `documentation/graefe_revision/Users/yy/MNV_analysis_pro/...` was present (2026-08-01 check). If one reappears, flatten contents up and remove empty directories.

## Original vs rev1 vs submission（見分け方）

| Layer | What | Where |
|-------|------|-------|
| **Original submission** | First journal manuscript + tables + Fig1/Fig2 | `original_submission/` |
| **Rev1 working** | Edited manuscript, tables (with ICC in Table 1), Response, Suppl, Fig3 | Root `*_rev1*` + `Response_*` + `figures/` |
| **Journal pack** | Frozen copies for upload | `submission_package_20260731/` (sync by copy from root; do not rewrite paths inside the pack) |

## Status by workstream

| Area | Status | Key outputs |
|------|--------|-------------|
| WS1 Inter ICC (3×n=46) | **Done** | `icc/icc_multirater_results.md` + device-locked Caliber in `icc/caliber_u2_device_std_icc_results.md`; default Caliber ICC 0.770; also in **Table 1** |
| WS1 Intra ICC (YY n=46) | **Done** | `icc/icc_intra_YY_results.md`; Caliber 0.925; also in **Table 1** |
| WS2 Expert–algorithm κ | **Done** | `grading/agreement_stats.md`; κ 0.507 (n=54) |
| WS4 Effect sizes | **Done** | `stats/table3_effect_sizes.md` |
| Rev1 + Response + Suppl | **Done for packet** | Root files + `submission_package_20260731/` |

## Root files (brief)

| File | Role |
|------|------|
| `MNV_Analysis_YY_rev1.md` / `.docx` | Revised manuscript **clean** = journal File 3 (cites Tables/Figures; no embedded Table 1–5 grids) |
| `MNV_Analysis_YY_rev1_manuscript_changes_marked.docx` | Journal **File 2** — Word Compare redline (original vs rev1 clean); also in submission package |
| `MNV_Analysis_YY_rev1_tables.md` / `.docx` | Tables 1–5 (Table 1: Variable \| Description \| Inter-rater ICC(2,1) \| Intra-rater ICC(2,1)) |
| `MNV_Analysis_YY_rev1_figure_legends.md` / `.docx` | Figure 1–3 legends (separate file) |
| `MNV_Analysis_YY_rev1_clean.docx` | Clean Word variant (snapshot) |
| `MNV_Analysis_YY_rev1_NOTES.md` | Author decisions / open figure notes |
| `MNV_Analysis_YY_rev1_CHANGELOG.md` | Rev1 diff log |
| `PHI_AUDIT_rev1.md` | PHI scan notes before zip |
| `Response_to_Reviewers.md` / `.docx` | Point-by-point response (**submit this**, not DRAFT) |
| `Response_to_Reviewers_DRAFT.*` | Synced working twin of final — prefer non-DRAFT for submit |
| `Supplementary_*.*` | Suppl Table S1 + expert agreement |
| `Table2_raw_metrics.md` | Internal Table 2 helper |

## Subfolder READMEs

| Path | Role |
|------|------|
| [`original_submission/`](original_submission/) | Original manuscript + Fig1/Fig2 |
| [`icc/README.md`](icc/README.md) | Inter/intra ICC index — **COMPLETED** |
| [`grading/README.md`](grading/README.md) | Blind grading — **COMPLETED** |
| [`data/README.md`](data/README.md) | Recovered batch CSVs |
| [`figures/README.md`](figures/README.md) | Fig3 working assets |
| [`submission_package_20260731/README_提出内容.txt`](submission_package_20260731/README_提出内容.txt) | What is in the journal packet |

## Archive

Superseded checklist and pre-completion incoming README live under [`_archive/`](_archive/). Prefer this file over anything there.
