# Graefe major revision — local working tree

**Do not push this branch to remote** (`graefe/major-revision-analyses` stays local unless you explicitly ask to push).

Author navigation map for `documentation/graefe_revision/` (tidied **2026-08-03**; parent decluttered same day). Analyses for Comment 2 / 4 / 5 and rev1 packet are **complete**. **`submission_package_20260731/` is the frozen submission snapshot — do not reshape it for cleanliness.**

## Quick start / どこに何があるか

| Need / 用途 | Go here / 場所 |
|------|---------|
| **提出スナップショット（触らない）** | [`submission_package_20260731/`](submission_package_20260731/) — see `README_提出内容.txt`；**提出用 docx はここだけ** |
| **本番クエリ再アップ用（2026-08-07）** | [`production_fixes_20260807/`](production_fixes_20260807/) — ESM PDF / Figure1 / Table5 引用 / 返信ドラフト |
| **初回提出原稿・図表（original）** | [`original_submission/`](original_submission/) |
| **改訂作業 SoT (rev1 markdown)** | Root: `MNV_Analysis_YY_rev1.md`, `Response_to_Reviewers.md`, `Supplementary_*.md`, tables / legends `.md` |
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
| `submission_package_20260731/**` (**frozen**; leave layout alone) — **all submitted `.docx`** | `icc/`, `grading/`, `data/`, `stats/` (CSVs may contain PHI-like filenames) |
| Root **markdown** SoT (MS / Response / tables / legends / Suppl) | `working/**`, `_archive/**`, `original_submission/**` |
| | `figures/_fig3_runs/`, `figures/_fig3_rebuild_furukawa/`, `icc/_raw_from_downloads/`, `grading/previews/` |

Reader-facing Caliber term: **Standardized Caliber Uniformity Score** (device-/stratum-locked = **default**). **PCA-based Caliber Uniformity Score (legacy)** = sensitivity only. Do not use “U2” in manuscript / Response prose (internal paths may still say `caliber_u2_*`).

## Folder map (post-declutter 2026-08-03)

```
documentation/graefe_revision/
├── README.md                          ← this map（日英）
├── submission_package_20260731/       ← FROZEN journal pack（docx + md 提出コピー；中身は整理しない）
├── production_fixes_20260807/         ← 本番クエリ再アップ用（ESM PDF / Fig1 / Table5 引用）
├── original_submission/               ← 初回提出の原本
├── MNV_Analysis_YY_rev1.md            ← File 3 編集 SoT（docx は package のみ）
├── MNV_Analysis_YY_rev1_tables.md     ← Tables 1–5 SoT
├── MNV_Analysis_YY_rev1_figure_legends.md
├── Response_to_Reviewers.md           ← File 1 SoT（DRAFT は _archive）
├── Supplementary_Table_S1.md
├── Supplementary_expert_agreement.md
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
| **Rev1 editable SoT** | Markdown sources for MS / Response / tables / Suppl / legends | Root `*.md` listed above |
| **Journal pack** | **Frozen** upload copies (`.docx` + synced `.md`) | `submission_package_20260731/` — **do not reorganize** |
| **Internal working notes** | Author decisions, changelog, PHI audit | `working/` |

Parent no longer keeps duplicate **docx** mirrors (byte-identical to package as of declutter). Edit markdown at root; regenerate/sync Word into the package only when preparing a resubmission.

## Status by workstream

| Area | Status | Key outputs |
|------|--------|-------------|
| WS1 Inter ICC (3×n=46) | **Done** | `icc/icc_multirater_results.md` + device-locked Caliber in `icc/caliber_u2_device_std_icc_results.md`; default Caliber ICC 0.770; also in **Table 1** |
| WS1 Intra ICC (YY n=46) | **Done** | `icc/icc_intra_YY_results.md`; Caliber 0.925; also in **Table 1** |
| WS2 Expert–algorithm κ | **Done** | `grading/agreement_stats.md`; κ 0.507 (n=54) |
| WS4 Effect sizes | **Done** | `stats/table3_effect_sizes.md` |
| Rev1 + Response + Suppl | **Submitted** | Frozen in `submission_package_20260731/`; root markdown SoT retained |

## Root files (brief)

| File | Role |
|------|------|
| `MNV_Analysis_YY_rev1.md` | Revised manuscript **clean** — editable SoT (journal File 3 **docx** → package) |
| `MNV_Analysis_YY_rev1_tables.md` | Tables 1–5 SoT |
| `MNV_Analysis_YY_rev1_figure_legends.md` | Figure 1–3 legends SoT |
| `Response_to_Reviewers.md` | Point-by-point response SoT (**File 1** docx → package) |
| `Supplementary_Table_S1.md` / `Supplementary_expert_agreement.md` | Suppl SoT |
| *(no root `.docx`)* | Submitted Word files live only under `submission_package_20260731/` (incl. File 2 marked MS) |

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
