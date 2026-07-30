# Exclude worst-6 concordance cases (= existing top-40 subset)

**Date:** 2026-07-30  
**Question:** What if we exclude the 6 “bad” image cases?  
**Assumption here:** “bad” = **worst concordance** (ranks 41–46 in `icc_cases_ranked_by_concordance.csv`).

## Confirmation

Excluding these 6 cases is **identical** to the existing sensitivity analysis on the **top-40 most concordant** cases:

- Case list: `icc_subset40_case_list.csv`
- ICC report: `icc_multirater_results_subset40.md`

(`full n=46` − ranks 41–46 = ranks 1–40; case_id / File sets match exactly.)

If “ダメな6例” instead means **visually** poor images (not concordance rank), those IDs must be supplied separately — this note does not apply.

## Excluded 6 (ranks 41–46, highest discordance)

| Rank | case_id (short) | File | discordance_score |
|------|-----------------|------|-------------------|
| 41 | takako_fumiichi__60615911_…_20230724150518_OD | `takako_fumiichi__60615911_19431030_Unknown_Angiography 3x3 mm_20230724150518_OD_20260708195335 - ORCC.AngiographyEnface.jpg` | 1.463 |
| 42 | imazeki_humio__05041322_…_20260617115820_OS | `imazeki_humio__05041322_19500214_Unknown_Angiography 3x3 mm_20260617115820_OS_20260708203220 - ORCC.AngiographyEnface.jpg` | 1.509 |
| 43 | takako_fumiichi__60615911_…_20230329111258_OD | `takako_fumiichi__60615911_19431030_Unknown_Angiography 3x3 mm_20230329111258_OD_20260708195314 - ORCC.AngiographyEnface.jpg` | 1.547 |
| 44 | matuzaki_mineo__06260459_…_20260422105721_OS | `matuzaki_mineo__06260459_19410917_Male_Angiography 3x3 mm_20260422105721_OS_20260708183008 - ORCC.AngiographyEnface.jpg` | 1.554 |
| 45 | furukawa_hiroichi__06479278_…_20240529103158_OD | `furukawa_hiroichi__06479278_19430227_Male_Angiography 3x3 mm_20240529103158_OD_20260708210446 - ORCC.AngiographyEnface.jpg` | 1.563 |
| 46 | kobayashi_isao__06477207_…_20240424102817_OD | `kobayashi_isao__06477207_19440815_Male_Angiography 3x3 mm_20240424102817_OD_20260728191602 - ORCC.AngiographyEnface.jpg` | 1.826 |

Full `case_id` strings (exact join keys):

1. `takako_fumiichi__60615911_19431030_unknown_angiography 3x3 mm_20230724150518_od_20260708195335 - orcc.angiographyenface`
2. `imazeki_humio__05041322_19500214_unknown_angiography 3x3 mm_20260617115820_os_20260708203220 - orcc.angiographyenface`
3. `takako_fumiichi__60615911_19431030_unknown_angiography 3x3 mm_20230329111258_od_20260708195314 - orcc.angiographyenface`
4. `matuzaki_mineo__06260459_19410917_male_angiography 3x3 mm_20260422105721_os_20260708183008 - orcc.angiographyenface`
5. `furukawa_hiroichi__06479278_19430227_male_angiography 3x3 mm_20240529103158_od_20260708210446 - orcc.angiographyenface`
6. `kobayashi_isao__06477207_19440815_male_angiography 3x3 mm_20240424102817_od_20260728191602 - orcc.angiographyenface`

## ICC(2,1): n=46 (primary) vs n=40 (after excluding worst 6)

| Metric | n=46 | n=40 (exclude worst 6) | Δ |
|--------|------|------------------------|---|
| Area | 0.859 | 0.847 | −0.012 |
| Complexity | 0.807 | 0.822 | +0.014 |
| Caliber | 0.434 | 0.611 | +0.177 |
| Maturity | 0.659 | 0.777 | +0.118 |

Sources: `icc_multirater_results.md` (n=46), `icc_multirater_results_subset40.md` (n=40).

**Caveat:** n=40 is a concordance-based sensitivity / upper-bound analysis; it does not replace the primary n=46 ICC.
