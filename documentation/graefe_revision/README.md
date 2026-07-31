# Graefe major revision — local working tree

**Do not push this branch to remote** (`graefe/major-revision-analyses` stays local unless you explicitly ask to push).

Author navigation map for `documentation/graefe_revision/` (2026-07-31). Analyses for Comment 2 / 4 / 5 and rev1 packet are **complete**; remaining work is packaging / journal upload, not re-opening ICC or grading.

## Quick start

| Need | Go here |
|------|---------|
| **提出物（雑誌用）** | [`submission_package_20260731/`](submission_package_20260731/) — see `README_提出内容.txt` |
| Working rev1 / Response / Suppl (edit here, then re-copy to package) | Root `MNV_Analysis_YY_rev1.*`, `Response_to_Reviewers.*`, `Supplementary_*.*` |
| ICC (inter + intra) | [`icc/`](icc/) — **COMPLETED** |
| Expert grading / κ | [`grading/`](grading/) — **COMPLETED** |
| Table 3 ε² | [`stats/`](stats/) — **COMPLETED** |
| Batch CSV source | [`data/`](data/) |
| Historical WIP checklist | [`_archive/`](_archive/) |

## Journal vs internal

| For journal / zip | Internal only (do not submit) |
|-------------------|-------------------------------|
| `submission_package_20260731/**` | `icc/`, `grading/`, `data/`, `stats/` (CSVs may contain PHI-like filenames) |
| Rev1 manuscript + **tables** + **figure legends** + Response + Suppl + figures | `*_NOTES.md`, `*_CHANGELOG.md`, `PHI_AUDIT_rev1.md`, `Table2_raw_metrics.md` |
| | `Response_to_Reviewers_DRAFT.*`, original `MNV_Analysis_YY.docx`, `manuscript_text.txt`, `MNV_analysis_tables_original.docx` |
| | `_archive/`, `figures/_fig3_runs/`, `icc/_raw_from_downloads/`, `grading/previews/` |

Reader-facing Caliber term: **Standardized Caliber Uniformity Score** (device-/stratum-locked = **default**). **PCA-based Caliber Uniformity Score (legacy)** = sensitivity only. Do not use “U2” in manuscript / Response prose (internal paths may still say `caliber_u2_*`).

## Folder map

```
documentation/graefe_revision/
├── README.md                          ← this map
├── submission_package_20260731/       ← 提出用コピー（触らない中身；再コピーで更新）
├── MNV_Analysis_YY_rev1.*             ← 改訂原稿（作業原本）
├── Response_to_Reviewers.*            ← 査読応答（提出版；DRAFT は作業残骸）
├── Supplementary_Table_S1.*
├── Supplementary_expert_agreement.*
├── Figure*.png/.tiff                    ← Fig1/Fig2 作業コピー（パッケージにも同梱）
├── figures/                           ← Fig3 + caption + _fig3_runs（中間）
├── icc/                               ← ICC 解析アーカイブ（完了）
│   ├── README.md
│   ├── incoming/                      ← 3観察者 CSV
│   ├── intra/                         ← YY test–retest（完了）
│   └── _raw_from_downloads/           ← 画像ミラー等
├── grading/                           ← 盲検 grading + κ（完了）
├── data/                              ← 1e5d202 回収バッチ CSV
├── stats/                             ← Table3 ε²
└── _archive/                          ← 古いチェックリスト等
```

## Status by workstream

| Area | Status | Key outputs |
|------|--------|-------------|
| WS1 Inter ICC (3×n=46) | **Done** | `icc/icc_multirater_results.md`; default Caliber ICC 0.770 |
| WS1 Intra ICC (YY n=46) | **Done** | `icc/icc_intra_YY_results.md`; Caliber 0.925 |
| WS2 Expert–algorithm κ | **Done** | `grading/agreement_stats.md`; κ 0.507 (n=54) |
| WS4 Effect sizes | **Done** | `stats/table3_effect_sizes.md` (default Caliber narrative in Response Comment 5) |
| Rev1 + Response + Suppl | **Done for packet** | Root files + `submission_package_20260731/` |
| Fig3 freehand polish | Optional | Current draft from auto-ROI; see NOTES |

## Root files (brief)

| File | Role |
|------|------|
| `MNV_Analysis_YY_rev1.md` / `.docx` | Revised manuscript (cites Tables/Figures; no embedded Table 1–5 grids) |
| `MNV_Analysis_YY_rev1_tables.md` / `.docx` | Tables 1–5 (same role as original `MNV_analysis_tables.docx`) |
| `MNV_Analysis_YY_rev1_figure_legends.md` / `.docx` | Figure 1–3 legends (separate file) |
| `MNV_Analysis_YY_rev1_clean.docx` | Clean Word variant (snapshot) |
| `MNV_Analysis_YY_rev1_NOTES.md` | Author decisions / open figure notes |
| `MNV_Analysis_YY_rev1_CHANGELOG.md` | Rev1 diff log |
| `PHI_AUDIT_rev1.md` | PHI scan notes before zip |
| `Response_to_Reviewers.md` / `.docx` | Point-by-point response (**submit this**, not DRAFT) |
| `Response_to_Reviewers_DRAFT.*` | Snapshot; same content as final at last sync — prefer non-DRAFT |
| `Supplementary_*.*` | Suppl Table S1 + expert agreement |
| `Table2_raw_metrics.md` | Internal Table 2 helper |
| `MNV_analysis_tables_original.docx` | Local copy of original tables file |
| `MNV_Analysis_YY.docx`, `manuscript_text.txt` | Original submission text |

## Subfolder READMEs

| Path | Role |
|------|------|
| [`icc/README.md`](icc/README.md) | Inter/intra ICC index — **COMPLETED** |
| [`icc/intra/README.md`](icc/intra/README.md) | YY test–retest — **COMPLETED** |
| [`icc/incoming/README.md`](icc/incoming/README.md) | Drop folders — data received; pointer only |
| [`grading/README.md`](grading/README.md) | Blind grading — **COMPLETED** |
| [`data/README.md`](data/README.md) | Recovered batch CSVs |
| [`submission_package_20260731/README_提出内容.txt`](submission_package_20260731/README_提出内容.txt) | What is in the journal packet |

## Archive

Superseded checklist and pre-completion incoming README live under [`_archive/`](_archive/). Prefer this file over anything there.
