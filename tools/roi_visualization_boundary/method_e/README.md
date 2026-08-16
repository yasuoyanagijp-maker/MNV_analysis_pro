# Method E（パイロット検証のみ）— 輪郭の局所ナッジで ColorMask へスナップ

ハンドドロー ROI の**各外部輪郭点**を、Pass-1 ColorMask に向かって局所法線方向に最大 `displacement_px` だけ動かす案。  
**本番未接続。** `intelligent_roi` / `enable_roi_refinement` / `schemas.py` / `mnv_wizard.py` / `mnv_pipeline.py` は未変更。手描き ROI が refinement をスキップする挙動も未変更。

Method D の成果物は読んで比較するだけ。`method_d/` には書いていない。

実行:

```bash
.venv/bin/python tools/roi_visualization_boundary/method_e/method_e_contour_snap.py
```

出力先: `tools/roi_visualization_boundary/method_e/`

| ファイル | 内容 |
|---|---|
| `method_e_contour_snap.py` | 本スクリプト |
| `phase0_record.md` | コード作成前の Phase 0（密度＋反転判定） |
| `phase0_contour_density.csv` | 6 マスクの SIMPLE/NONE 間隔 |
| `displacement_sweep_results.csv` | 症例 × 変位の MNV/Vsl RPD・移動量 |
| `device_check.json` | meta.json の機種・スケール |
| `qa/` | 4 層 QA + overlay + panel + vs Method D（324 PNG、ローカル） |

`MNVPipeline.analyze` は回していない。面積は画素カウントのみ。

本番フラグ名 **`enable_color_snap`** は文書だけ。schemas / pipeline には足していない。

---

## 0. Phase 0（コード作成前に記録）

詳細は `phase0_record.md`。

### A. 輪郭密度 → **密化する（YES）**

`CHAIN_APPROX_SIMPLE` の平均間隔は約 2 px だが、**最大 5.7–14 px**（38–93 μm）。5 μm（1 px）より広く、50 μm（8 px）も超える症例がある。疎な頂点のままナッジすると長い辺の中点が動かない。

`CHAIN_APPROX_NONE` は平均 1.14–1.18 px、最大 1.41 px。  
**採用**: NONE を取り、弧長 **1.0 px** に再サンプルしてからナッジする。

| グレーダー | 症例 | NONE 点 | SIMPLE 点 | SIMPLE 平均/最大 px | SIMPLE 最大 μm |
|---|---|---|---|---|---|
| G1 | abe 20250409 | 870 | 523 | 1.96 / 10.0 | 66.7 |
| G1 | abe 20260225 | 692 | 408 | 1.98 / 7.0 | 46.7 |
| G1 | asai 20230314 | 1342 | 814 | 1.92 / 14.0 | 93.3 |
| G2 | abe 20250409 | 214 | 115 | 2.13 / 11.0 | 73.3 |
| G2 | abe 20260225 | 103 | 67 | 1.82 / 5.7 | 37.7 |
| G2 | asai 20230314 | 263 | 160 | 1.95 / 6.0 | 40.0 |

上表は最大輪郭 1 本。export マスクは 2 値だが **外部輪郭 150–326 本**（ブラシ／血管トレース）。最大輪郭だけ `fillPoly` すると面積が潰れる（G1 abe 4/9: 16486 → 3404 px）。実装は**全外部輪郭**を密化・ナッジして union する。

### B. ROI_modify と符号反転 → **符号反転は使わない**

`ROIModifier`（`src/core/roi_manager.py`）:

- 輪郭は `CHAIN_APPROX_NONE`。重心で偏角ソート。
- 探索は**重心レイ**（重心→点）。局所法線ではない。
- 評価は**最小輝度**（暗い画素へ）。
- `fast_mode=True`（既定）: 1 反復、**5 点ごと**、`r ∈ [-search_radius, +search_radius]`（既定 2）。
- `fast_mode=False`: `iterations` 回、箱探索、`angle_threshold` でレイから外れた点を捨てる。
- その後 3 点移動平均、`fillPoly`。
- **手描き**: `analyze(..., roi_mask=...)` のとき refinement は走らない。この挙動は変えていない。

最小→最大輝度にしても探索は重心レイのまま。明るい血管は病変コア側にあるので、符号反転は**輪郭を内側へ縮める**。レイを外へ伸ばすと、同じ半径上のアーケードへ飛びうる。

**Method E の移動**: Pass-1 ColorMask（Method B 固定抽出。Pass-2 の seed dilate なし）を引力場にし、各点を局所法線の内向き／外向きに最大 `displacement_px` だけ動かす。同距離なら内向き優先。シード成長はしない（それは Method D）。

---

## 1. 定義（実装どおり）

```
user_roi          = ハンドドロー（多 CC）
binary            = preprocess_mnv（全画像。ROI クリップなし）
ColorMask₁        = Li(GaussianBlur(unweighted_mean(|raw-rgb₁|), σ=1.0))
                    rgb₁ は lesion_mask=user_roi, add_overlays=False
                    ※ Pass-2 なし

contours          = 全 RETR_EXTERNAL、NONE、弧長 1.0 px に密化
displacement_px   = round_half_up(displacement_um × px_per_mm / 1000)

各点: 局所外向き法線の ± 方向に t=1..displacement_px を見て
      最初に当たった ColorMask 画素へ移動（同 t なら内向き）
      既に ColorMask 上なら動かない
      |move| ≤ displacement_px（丸め後は ±1 px 程度）

refined           = union(fillPoly(各ナッジ輪郭))
                    変位 0 は user_roi そのもの（対照）

MNV Area          = refined px × (fov_mm / width)²
Vsl Area          = (binary ∩ refined) px × 同じスケール
```

使わないもの: 無制限 dilate、血管 CC の全 union、ROIEnclosure を解析 ROI にする、Method D の Pass-2、ナイーブな符号反転、本番フラグ。

---

## 2. 機種チェック（単一機種。交差検証は未実施）

3 症例はすべて **CIRRUS / 3 mm / 150 px/mm**。Method D と同じ。

| displacement_um | displacement_px |
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
Method A は `MNV_batch_20260815_094130`。Method D は `../method_d/radius_sweep_results.csv`。

### 3.1 対照（A / B / D半径0 / E変位0）

| 症例 | 指標 | A | B | D r=0 | E d=0 |
|---|---|---|---|---|---|
| abe 20250409 | MNV | 64.0 | 50.6 | 54.3 | **64.0**（=A） |
| abe 20260225 | MNV | 96.5 | 78.7 | 84.5 | **96.5**（=A） |
| asai 20230314 | MNV | 46.8 | **18.2 採用** | 20.5 | **46.8**（=A） |

E の変位 0 は手描きそのもの。D の半径 0 は `ColorMask ∩ user_roi` なので面積が小さい。

### 3.2 変位スイープ（Method E）と Method D

| 症例 | μm | px | E MNV RPD | E Vsl RPD | E 採用 | D MNV RPD | D 採用 | G1 E MNV | G2 E MNV |
|---|---|---|---|---|---|---|---|---|---|
| abe 20250409 | 0 | 0 | 64.0 | 55.0 | no | 54.3 | no | 0.733 | 0.377 |
| abe 20250409 | 5 | 1 | 67.8 | 57.6 | no | 41.3 | no | 0.655 | 0.323 |
| abe 20250409 | 10 | 2 | 66.2 | 57.3 | no | 24.4 | no | 0.623 | 0.313 |
| abe 20250409 | 20 | 3 | 67.2 | 58.0 | no | 22.6 | no | 0.634 | 0.315 |
| abe 20250409 | 30 | 5 | 67.5 | 58.6 | no | **14.9** | **yes** | 0.676 | 0.334 |
| abe 20250409 | 50 | 8 | 63.9 | 56.7 | no | **8.7** | **yes** | 0.752 | 0.388 |
| abe 20260225 | 0 | 0 | 96.5 | 84.7 | no | 84.5 | no | 0.695 | 0.243 |
| abe 20260225 | 5 | 1 | 100.4 | 87.6 | no | 64.4 | no | 0.629 | 0.209 |
| abe 20260225 | 10 | 2 | 98.3 | 86.7 | no | 45.7 | no | 0.604 | 0.206 |
| abe 20260225 | 20 | 3 | 97.8 | 86.7 | no | 35.1 | no | 0.607 | 0.208 |
| abe 20260225 | 30 | 5 | 97.7 | 86.0 | no | 22.8 | no | 0.643 | 0.221 |
| abe 20260225 | 50 | 8 | 99.3 | 86.6 | no | **17.1** | **yes** | 0.720 | 0.242 |
| asai 20230314 | 0 | 0 | 46.8 | 30.1 | no | 20.5 | no | 0.576 | 0.358 |
| asai 20230314 | 5 | 1 | 52.1 | 33.4 | no | **7.3** | **yes** | 0.556 | 0.326 |
| asai 20230314 | 10 | 2 | 57.3 | 34.8 | no | 8.7 | yes | 0.519 | 0.288 |
| asai 20230314 | 20 | 3 | 54.7 | 33.8 | no | 6.8 | yes | 0.496 | 0.283 |
| asai 20230314 | 30 | 5 | 51.9 | 32.1 | no | 6.8 | yes | 0.512 | 0.301 |
| asai 20230314 | 50 | 8 | 47.4 | 30.6 | no | 6.6 | yes | 0.551 | 0.340 |

E は全セル非採用。RPD は A の近くで横ばい（abe 4/9 は 64–68%、abe 2/25 は 97–100%、asai は 47–57%）。D のように半径を上げても採用に届かない。

---

## 4. 仮説の判定

### asai: 小さい変位で収束するか

**しない。** Method D は 5 μm から採用（MNV 7.3%）で以後 6–9% の高原。Method E は 5 μm で 52% に悪化し、50 μm でも 47%（A と同じ）。

理由: G1 の余白は「1 本の外輪郭の内側」ではなく、多 CC のブラシ幅。各 CC を ColorMask に 1–8 px 寄せても、公式面積は手描きの塗り領域のまま。ColorMask 面積（Method B / D inward）にはならない。

### abe: 50 μm でも有界で、アーケードを飲み込まないか

**有界は保った。アーケード飲み込みは見えない。RPD は 20% 超のまま（安全だが不完全）。** 主仮説は支持。

根拠:

- 50 μm でも E の絶対面積は A に近い（abe 4/9: A 0.733/0.377 → E 0.752/0.388。D は 0.972/0.891）。
- 追加画素の user からの最大距離は 50 μm でも 3.7–4.6 px（上限 8 px 未満）。
- 点の平均移動は 50 μm でも 0.51–1.48 px。最大移動は 8.52–8.58 px（上限 8 ＋対角丸め）。
- QA の `*_vs_d.png` で、D の橙（outward）は帯状に広い。E の橙は輪郭の細い縁。
- G2 abe 20260225・50 μm: D は切れ血管の外側を大きく拾う。E の追加は 902 px（D outward は 11,809 px）。

abe の RPD が下がらないのは、Pass-1 ColorMask に切れ血管が入っていないため。局所ナッジでは G2 の切り口の先へ届かない。届けるのは Method D の Pass-2（seed 再着色）側。

---

## 5. 有界性

| 変位 μm | 上限 px | 最大点移動 px | 追加画素の最大距離 px | G1+G2 追加 px 合計（3 例） |
|---|---|---|---|---|
| 5 | 1 | 1.51 | 0.96–2.74 | 213 |
| 10 | 2 | 2.61 | 0.96–2.74 | 485 |
| 20 | 3 | 3.54 | 1.37–2.74 | 1,330 |
| 30 | 5 | 5.66 | 2.32–2.87 | 5,184 |
| 50 | 8 | 8.58 | 3.69–4.65 | 12,361 |

点移動は上限＋丸め。追加画素距離が 5 μm で 2.7 px まで出るのは、近接 CC の `fillPoly` が小さな凹を埋めるため。アーケード規模（数十 px）ではない。

領域成長なし。ROIEnclosure なし。血管 CC の全 union なし。

---

## 6. このパイロットで言えること / 言えないこと

言えること:

- 密化は必要（SIMPLE の隙間が変位より大きい）。
- 符号反転は使わない（重心レイ＋最大輝度はコアへ縮む／アーケードへ飛ぶ）。
- Method E は有界。50 μm でもアーケードを飲み込まない（この 3 例の QA）。
- asai は D のようには速く収束しない。abe の RPD は 20% 超で高原（不完全）。
- D の採用改善は Pass-2 の領域成長による。輪郭ナッジだけでは再現しない。
- 3 例は単一機種。交差検証はしていない。

言えないこと:

- 本番既定 ON。未配線。
- 他機種・他 FOV。
- 統計的有意。
- ハンドドローが単一塗りつぶしポリゴンのときの挙動（今回の export は多 CC）。

---

## 7. QA 画像

`qa/{grader}_{case}_d{um}um_{layer}.png`

- `user_roi` 緑 / `colormask` シアン / `nudge_added` 橙 / `nudge_removed` 赤 / `refined` マゼンタ
- `nudge_delta` 追加＋削除
- `overlay` 合成
- `panel` 2×2（Method D と同じ 4 層）
- `vs_d` Method D の同 μm outward / refined との並置

例: `qa/g2_abe_20260225_d50um_vs_d.png`
