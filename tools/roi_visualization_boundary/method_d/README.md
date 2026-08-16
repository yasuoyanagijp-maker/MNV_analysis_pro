# Method D（パイロット検証のみ）— ColorMask への ROI スナップ

ハンドドロー ROI を、RGB 可視化の着色領域（ColorMask）にスナップする案。  
**本番未接続。フラグなし。`intelligent_roi` / `mnv_pipeline.py` / `schemas.py` / `mnv_wizard.py` は未変更。**

実行:

```bash
.venv/bin/python tools/roi_visualization_boundary/method_d/method_d_colormask_snap.py
```

出力先: `tools/roi_visualization_boundary/method_d/`

| ファイル | 内容 |
|---|---|
| `method_d_colormask_snap.py` | 本スクリプト |
| `radius_sweep_results.csv` | 症例 × 半径の MNV/Vsl RPD・孤立フラグメント集計 |
| `isolated_fragments.csv` | 孤立 CC 1行1件（case, grader, radius_um, cc_id, area_px, area_mm2） |
| `device_check.json` | meta.json の機種・スケール照合 |
| `qa/` | 4層 QA + 合成 overlay + 2×2 panel（216 PNG、ローカル） |

`MNVPipeline.analyze` は回していない。面積は画素カウントのみ。血管 binary はグレーダー×症例で1回、Pass-1 ColorMask はグレーダー×症例で1回、Pass-2 は半径>0 のときだけ。

---

## 1. 定義（実装どおり）

```
user_roi          = ハンドドロー
binary            = preprocess_mnv（全画像。ROI クリップなし）
ColorMask₁        = Li(GaussianBlur(unweighted_mean(|raw-rgb₁|), σ=1.0))
                    rgb₁ は lesion_mask=user_roi, add_overlays=False
inward            = ColorMask₁ ∩ user_roi
                    ※ Method B' の border-erase は使わない

radius_px         = round_half_up(radius_um × px_per_mm / 1000)   # 最小 0
seed              = disk-dilate(user_roi, radius_px)               # MORPH_ELLIPSE
ColorMask₂        = 同じ抽出。rgb₂ は lesion_mask=seed
outward_added     = (ColorMask₂ ∩ seed) − user_roi
                    ※ inward core ではなく user_roi を引く
refined           = ((ColorMask₁ ∩ user_roi) ∪ (ColorMask₂ ∩ seed)) ∩ seed

MNV Area          = refined px × (fov_mm / width)²
Vsl Area          = (binary ∩ refined) px × 同じスケール
Vsl Density       = Vsl / MNV     （報告する。ColorMask 単体を面積定義にはしない）
```

半径 0 は inward のみ（Pass-2 なし、outward 空）。Method B に近い対照だが、Method B の公式面積は ColorMask 全体、こちらは `ColorMask ∩ user_roi`。Gaussian 滲み分だけ違う。

使わないもの: 無制限 dilate、血管 CC の全 union、ROIEnclosure を解析 ROI にする、Method C、本番フラグ。

---

## 2. 機種チェック（単一機種。交差検証は未実施）

G1 / G2 の `export/meta/TEAM_YY/*.json` を6件すべて読んだ。

| 症例 | グレーダー | device | stratum | fov_mm | px_per_mm |
|---|---|---|---|---|---|
| abe 20250409 | G1, G2 | CIRRUS | small_3mm | 3.0 | 150 |
| abe 20260225 | G1, G2 | CIRRUS | small_3mm | 3.0 | 150 |
| asai 20230314 | G1, G2 | CIRRUS | small_3mm | 3.0 | 150 |

3症例は **すべて CIRRUS / 3 mm / 150 px/mm**。事前メタの通り。  
**他機種・他 FOV での検証はしていない。** 半径の px 換算は機種で変わる（例: 150 px/mm で 30 μm → 4.5 → 5 px）。

CIRRUS 3 mm での換算（round half up）:

| radius_um | radius_px |
|---|---|
| 0 | 0 |
| 5 | 1 |
| 10 | 2 |
| 20 | 3 |
| 30 | 5 |
| 50 | 8 |

---

## 3. 主結果 — MNV / Vsl Area RPD

採用閾値は従来どおり RPD ≤ 20%。  
Method A は `MNV_batch_20260815_094130`（統合 094445 と同じ3ペア）。  
Method B は `rpd_comparison.csv`（ColorMask を面積にした値）。

### 3.1 対照（A / B / D半径0）

| 症例 | 指標 | A | B | D r=0（inward のみ） |
|---|---|---|---|---|
| abe 20250409 | MNV | 64.0 | 50.6 NA | 54.3 NA |
| abe 20250409 | Vsl | 55.0 | 50.4 NA | 54.2 NA |
| abe 20260225 | MNV | 96.5 | 78.7 NA | 84.5 NA |
| abe 20260225 | Vsl | 84.7 | 77.8 NA | 83.7 NA |
| asai 20230314 | MNV | 46.8 | **18.2 採用** | 20.5 NA |
| asai 20230314 | Vsl | 30.1 | **18.1 採用** | 20.5 NA |

D の半径0は Method B よりやや悪い。ColorMask の ROI 外滲みを切るため。asai は B では採用、D r=0 では 20.5% でギリギリ非採用。

### 3.2 半径スイープ（Method D）

| 症例 | r μm | r px | MNV RPD | Vsl RPD | 採用 | G1 MNV | G2 MNV |
|---|---|---|---|---|---|---|---|
| abe 20250409 | 0 | 0 | 54.3 | 54.2 | no | 0.466 | 0.267 |
| abe 20250409 | 5 | 1 | 41.3 | 41.1 | no | 0.659 | 0.434 |
| abe 20250409 | 10 | 2 | 24.4 | 24.4 | no | 0.800 | 0.626 |
| abe 20250409 | 20 | 3 | 22.6 | 22.4 | no | 0.868 | 0.692 |
| abe 20250409 | **30** | 5 | **14.9** | **14.9** | **yes** | 0.917 | 0.790 |
| abe 20250409 | 50 | 8 | 8.7 | 8.7 | yes | 0.972 | 0.891 |
| abe 20260225 | 0 | 0 | 84.5 | 83.7 | no | 0.450 | 0.182 |
| abe 20260225 | 5 | 1 | 64.4 | 63.5 | no | 0.618 | 0.317 |
| abe 20260225 | 10 | 2 | 45.7 | 44.9 | no | 0.742 | 0.466 |
| abe 20260225 | 20 | 3 | 35.1 | 34.7 | no | 0.774 | 0.543 |
| abe 20260225 | 30 | 5 | 22.8 | 22.7 | no | 0.810 | 0.644 |
| abe 20260225 | **50** | 8 | **17.1** | **16.9** | **yes** | 0.893 | 0.752 |
| asai 20230314 | 0 | 0 | 20.5 | 20.5 | no | 0.245 | 0.199 |
| asai 20230314 | **5** | 1 | **7.3** | **7.2** | **yes** | 0.290 | 0.270 |
| asai 20230314 | 10 | 2 | 8.7 | 8.5 | yes | 0.304 | 0.332 |
| asai 20230314 | 20 | 3 | 6.8 | 6.9 | yes | 0.318 | 0.341 |
| asai 20230314 | 30 | 5 | 6.8 | 6.9 | yes | 0.325 | 0.348 |
| asai 20230314 | 50 | 8 | 6.6 | 6.7 | yes | 0.334 | 0.357 |

Vsl Density の RPD は全セル 0.04–1.0%。分母≈分子（refined ≈ 着色血管）なので Method B と同じく「病変内密度」としては読まない。悪化はしていない。

---

## 4. abe の事前予想は覆ったか

事前予想: abe 2例は G2 ROI が血管を切っているので、Method D でも MNV/Vsl RPD は大きく改善しない。

**30–50 μm では覆った。5–20 μm では覆っていない。**

根拠:

- G2 の outward 画素は G1 より多い（切れ血管の外側を Pass-2 が拾っている）。例: abe 20260225・50 μm で G1 outward 7,873 px、G2 11,809 px。
- abe 20250409 は **30 μm で初めて 20% 未満**（MNV 14.9 / Vsl 14.9）。
- abe 20260225 は 30 μm でも 22.8%（非採用）、**50 μm で 17.1 / 16.9 採用**。
- 一方 5–20 μm では abe 2例とも非採用のまま。小さい半径では「G2 が切った血管は戻らない」という Method B の限界が残る。

注意: 両グレーダーとも絶対面積は半径とともに増える。G1 も 50 μm では Method A のハンド ROI より大きい（abe 20250409: A 0.733 → D50 0.972）。RPD 低下は「同じ広い血管網への収束」でも起きうる。QA の橙（outward）が病変の続きか背景血管かは、次の目視校正の本題。

---

## 5. asai は採用のままか

- Method B: 採用（18.2 / 18.1）。
- Method D 半径 0: **非採用**（20.5 / 20.5）。inward = ColorMask ∩ ROI にした副作用。
- Method D **5 μm 以上: 採用を維持し、B より良い**（MNV 6.6–8.7%）。

asai は G1 の余白削減が主で、小さい半径で足りる。大きい半径を足しても RPD はほぼ横ばい（7% 前後）。

---

## 6. 孤立フラグメント（Change 3）

outward-added を 8-連結 CC に分割し、inward core を 1 px 膨張して重ならなければ孤立。  
**現行の refined（面積の公式）には孤立 CC も入っている。** フラグだけ。削除はしていない。

### 6.1 半径ごとの合計（3症例 × G1+G2）

| r μm | 孤立 CC 数 | 孤立面積 px | 孤立面積 mm² |
|---|---|---|---|
| 0 | 0 | 0 | 0 |
| 5 | 282 | 517 | 0.023 |
| 10 | 402 | 2,310 | 0.103 |
| 20 | 383 | 3,066 | 0.136 |
| 30 | 423 | 4,186 | 0.186 |
| 50 | 543 | 5,909 | 0.263 |

全スイープで 2,033 CC。大半は小さい。

| サイズ (px) | CC 数 | 合計 px |
|---|---|---|
| 1 | 422 | 422 |
| 2 | 283 | 566 |
| 3–5 | 503 | 2,001 |
| 6–10 | 386 | 2,946 |
| 11–20 | 265 | 3,831 |
| 21–50 | 150 | 4,548 |
| 51–100 | 21 | 1,302 |
| ≥101 | 3 | 372 |

中央値はランにより 1–15 px。最大は abe 20250409 G1・50 μm の 146 px。  
50 μm での孤立面積は refined の roughly 5–7%（abe 2例・asai とも同程度）。

### 6.2 パターン

- 半径を上げると CC 数も面積も増える。5 μm はほぼ 1–2 px の点。
- abe 2例のほうが asai より孤立が多い（病変周囲の背景血管が seed に入る）。
- G2 のほうが outward は多いが、孤立の中央値もやや大きい（切れ端の外側に別 CC が立つ）。
- QA では橙の「本体に接する帯」と、本体から離れた点在が共存。後者が孤立リスト。
- outward の大半は core に隣接している（abe 20250409・30 μm で孤立は outward の約 10%）。スナップ自体は効いている。

---

## 7. 半径の所見（この3例に限る）

| 半径 | 採用 | 孤立 | コメント |
|---|---|---|---|
| 0 | asai も落ちる | なし | B の対照。採用判定は B より厳しい |
| 5 | asai のみ | 小さい点が多い | asai には十分。abe は不足 |
| 10–20 | asai のみ | 増え始める | abe 20250409 は 20% 寸前（22%）まで来る |
| 30 | asai + abe 4/9 | 中程度 | 2/3 採用。abe 2/25 は 22.8% で未達 |
| 50 | **3/3** | 最多（543 CC） | abe 予想を覆す唯一の半径。FP リスクも最大 |

このパイロットだけで「既定半径」は決めない。候補は:

- **30 μm**: 偽陽性を抑えめ。abe 20260225 は再計測のまま。
- **50 μm**: 3例とも面積系が採用。孤立 CC を落とすかどうかを先に決めるべき。

---

## 8. 次の dual-read 校正で見るべきこと

1. **橙（outward）の目視** — 特に abe 20260225 の 30 vs 50 μm。G2 が切った病変血管の続きか、背景の網状血管か。
2. **孤立 CC を refined から除くか** — 除くと RPD がどう動くか。今は面積に入っている。
3. **密度の意味** — 0.99 近傍のまま。面積系の採用改善を密度改善と呼んではいけない。
4. **絶対面積の上方ドリフト** — RPD が下がっても、両者が同じ広い網に寄っているだけなら測定として不採用。Method C（Enclosure）で却下した理由と同じ点検。
5. **機種横断** — 未実施。CIRRUS 3 mm 以外で `radius_um → radius_px` が変わる。
6. **n=3** — 統計は言えない。G2 のタイト ROI がスタイルか、このセッションの質かも未決。
7. **asai の半径0** — B 採用が D inward で落ちる。本番に載せるなら「B の ColorMask 面積」と「D の ColorMask ∩ ROI」のどちらを公式にするかを先に固定する。

---

## 9. このパイロットで言えること / 言えないこと

言えること:

- 限られた半径の ColorMask 再着色は、G2 が切った血管を戻しうる。abe の「D では大して効かない」予想は 30–50 μm で覆った。
- asai は 5 μm 以上で採用を維持し、B より RPD が低い。
- 孤立 CC は数は多いが面積は小さく、大半は 1–20 px。
- 3例は単一機種。交差検証はしていない。

言えないこと:

- 本番既定 ON。未配線。
- 50 μm を既定にしてよいか（背景血管の飲み込み）。
- 他機種・他 FOV。
- 統計的有意。

---

## 10. QA 画像

`qa/{grader}_{case}_r{radius}um_{layer}.png`

- `user_roi` 緑 / `inward` シアン / `outward_added` 橙 / `refined` マゼンタ
- `overlay` 4層合成（緑=user、シアン=inward、橙=outward、マゼンタ輪郭=refined）
- `panel` 2×2

例: `qa/g2_abe_20260225_r50um_overlay.png`
