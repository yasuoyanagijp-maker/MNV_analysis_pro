# Example 15 mm PDR OCTA pairs

Display-rendered ILM−241 to ILM+49 en-face exports (1024×1024, 8-bit).
No physical scale in the files; analysis assumes **15 mm / 1024 px**.

| Case | Files | Visual note (not a label) |
|------|--------|---------------------------|
| case1 | `cases/case1_before.png`, `cases/case1_after.png` | Dense NVE network largely gone after treatment |
| case2 | `cases/case2_before.png`, `cases/case2_after.png` | Smaller tufts; change is subtle |

Sample run products (CSV, QA overlay, ARIAKE RGB, binary masks) live in `sample_runs/`.
These two cases are for engineering QA only — not a clinical validation set.

Registration on these sample runs used the **ILM+49 analysis slab** (the only files attached). For real work, pass Retina / VRI+Retina Global / a mean of all slabs via `--register-before` / `--register-after` — the same average-stack idea as stack_reg Image 5. The sample CSVs therefore carry `registration_on_analysis_slab`.
