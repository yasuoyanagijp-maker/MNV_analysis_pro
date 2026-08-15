# Method F（パイロット検証のみ）— 非対称ハイブリッド（D inward + E outward）

ハンドドロー ROI を **内側は無制限に ColorMask で削り、外側だけ Method E の有界ナッジ** で戻す案。

**本番未接続。** `intelligent_roi` / `enable_roi_refinement` / `schemas.py` / `mnv_wizard.py` / `mnv_pipeline.py` は未変更。

Method D / Method E の成果物は読んで比較するだけ。`method_d/` と `method_e/` には書いていない。

実行:

```bash
.venv/bin/python tools/roi_visualization_boundary/method_f/method_f_asymmetric_snap.py
```

出力先: `tools/roi_visualization_boundary/method_f/`

| ファイル | 内容 |
|---|---|
| `method_f_asymmetric_snap.py` | 本スクリプト |
| `displacement_sweep_results.csv` | 症例 × 変位の MNV/Vsl RPD。同 μm の D / E 列つき |
| `device_check.json` | meta.json の機種・スケール |
| `qa/` | 4 層 QA + overlay + panel + vs D/E（252 PNG、ローカル） |

`MNVPipeline.analyze` は回していない。面積は画素カウントのみ。n=3、すべて CIRRUS 3 mm / 150 px/mm。交差検証は未実施。

---

## 1. 定義（実装どおり）

```
user_roi          = ハンドドロー（多 CC）
binary            = preprocess_mnv（全画像。ROI クリップなし）
ColorMask₁        = Li(GaussianBlur(unweighted_mean(|raw-rgb₁|), σ=1.0))
                    rgb₁ は lesion_mask=user_roi, add_overlays=False
                    ※ Pass-2 なし
inward            = ColorMask₁ ∩ user_roi
                    ※ Method D 半径 0 と同じ。無制限 shrink。
                    ※ Pass-1 着色は ROI ゲートなので ColorMask ⊆ ROI
                      （Gaussian 滲みだけ ROI 外に 98–462 px）

contours          = inward の全 RETR_EXTERNAL（user_roi ではない）
                    NONE、弧長 1.0 px に密化
displacement_px   = round_half_up(displacement_um × px_per_mm / 1000)

各点: Method E と同じ。局所法線の ± 方向に t=1..displacement_px を見て
      最初に当たった ColorMask 画素へ移動（同 t なら内向き）
      既に ColorMask 上なら動かない
      |move| ≤ displacement_px

refined           = d=0  → inward（画素）
                    d>0  → union(fillPoly(ナッジした inward 輪郭))

outward-added     = refined − inward     （user_roi からは引かない）
MNV Area          = refined px × (fov_mm / width)²
Vsl Area          = (binary ∩ refined) px × 同じスケール
```

使わないもの: Pass-2 seed dilate、領域成長、ROIEnclosure を解析 ROI にする、血管 CC の全 union、本番フラグ。

引力は ColorMask のみ（E と同じ first-hit）。binary の thin-band は診断ログだけ（refined には使っていない）。

---

## 2. 機種チェック（単一機種。交差検証は未実施）

3 症例はすべて **CIRRUS / 3 mm / 150 px/mm**。D / E と同じ。

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

### 3.1 対照（A / B / D半径0 / E変位0 / F変位0）

| 症例 | 指標 | A | B | D r=0 | E d=0 | F d=0 |
|---|---|---|---|---|---|---|
| abe 20250409 | MNV | 64.0 | 50.6 | 54.3 | 64.0（=A） | **54.3（=D r=0）** |
| abe 20260225 | MNV | 96.5 | 78.7 | 84.5 | 96.5（=A） | **84.5（=D r=0）** |
| asai 20230314 | MNV | 46.8 | **18.2 採用** | 20.5 | 46.8（=A） | **20.5（=D r=0）** |

F の変位 0 は inward そのものなので、数値は Method D 半径 0 と一致する。E の変位 0 は手描きそのもの。

### 3.2 変位スイープ（F vs D vs E）

| 症例 | μm | px | F MNV RPD | F Vsl RPD | F 採用 | D MNV RPD | D 採用 | E MNV RPD | E 採用 | G1 F MNV | G2 F MNV |
|---|---|---|---|---|---|---|---|---|---|---|---|
| abe 20250409 | 0 | 0 | 54.3 | 54.2 | no | 54.3 | no | 64.0 | no | 0.466 | 0.267 |
| abe 20250409 | 5 | 1 | 55.4 | 54.4 | no | 41.3 | no | 67.8 | no | 0.475 | 0.269 |
| abe 20250409 | 10 | 2 | 55.4 | 54.4 | no | 24.4 | no | 66.2 | no | 0.475 | 0.269 |
| abe 20250409 | 20 | 3 | 55.4 | 54.4 | no | 22.6 | no | 67.2 | no | 0.475 | 0.269 |
| abe 20250409 | 30 | 5 | 55.4 | 54.4 | no | **14.9** | **yes** | 67.5 | no | 0.475 | 0.269 |
| abe 20250409 | 50 | 8 | 55.4 | 54.4 | no | **8.7** | **yes** | 63.9 | no | 0.475 | 0.269 |
| abe 20260225 | 0 | 0 | 84.5 | 83.7 | no | 84.5 | no | 96.5 | no | 0.450 | 0.182 |
| abe 20260225 | 5 | 1 | 86.2 | 84.0 | no | 64.4 | no | 100.4 | no | 0.457 | 0.182 |
| abe 20260225 | 10 | 2 | 86.2 | 84.0 | no | 45.7 | no | 98.3 | no | 0.457 | 0.182 |
| abe 20260225 | 20 | 3 | 86.2 | 84.0 | no | 35.1 | no | 97.8 | no | 0.457 | 0.182 |
| abe 20260225 | 30 | 5 | 86.2 | 84.0 | no | 22.8 | no | 97.7 | no | 0.457 | 0.182 |
| abe 20260225 | 50 | 8 | 86.2 | 84.0 | no | **17.1** | **yes** | 99.3 | no | 0.457 | 0.182 |
| asai 20230314 | 0 | 0 | 20.5 | 20.5 | no | 20.5 | no | 46.8 | no | 0.245 | 0.199 |
| asai 20230314 | 5 | 1 | **19.8** | 20.5 | **MNV yes** | **7.3** | **yes** | 52.1 | no | 0.251 | 0.206 |
| asai 20230314 | 10 | 2 | **19.8** | 20.5 | **MNV yes** | 8.7 | yes | 57.3 | no | 0.251 | 0.206 |
| asai 20230314 | 20 | 3 | **19.8** | 20.5 | **MNV yes** | 6.8 | yes | 54.7 | no | 0.251 | 0.206 |
| asai 20230314 | 30 | 5 | **19.8** | 20.5 | **MNV yes** | 6.8 | yes | 51.9 | no | 0.251 | 0.206 |
| asai 20230314 | 50 | 8 | **19.8** | 20.5 | **MNV yes** | 6.6 | yes | 47.4 | no | 0.251 | 0.206 |

F は **5 μm で高原**。10–50 μm は 5 μm と画素単位で同一。D のように半径を上げても面積は増えない。E のように手描き近傍で横ばいにもならない（起点が inward のため）。

asai の Vsl RPD は 20.52% で、MNV だけが 20% をわずかに下回る。

---

## 4. 仮説の判定

### asai: inward で余白が落ち、小さい外向きで 20% を切るか

**d=0 は D0 どおり 20.5%。d≥5 で MNV 19.8% 採用。D の 7% には届かない。高原は即座。**

- 主仮説（余白除去 → D0 近傍）は支持。F d=0 = D r=0 = 20.5%。
- 「小さい外向きで 20% 未満」は **数値上は採用**（19.77%）。ただし動きの本体はナッジではなく、inward 外部輪郭の `fillPoly` 再構成（G1 +142 / G2 +153 px、点移動 0）。
- D が 5 μm で 7.3% になるのは Pass-2 領域成長。F はそれをしないので 7% 帯には入らない。
- E 単独（52.1 → 57.3 → 47.4）よりは明らかに使える。手描き余白を先に落とす効果が大きい。

### abe: 外向きは有界で、アーケードを飲み込まないか

**有界は保った。アーケード飲み込みは見えない。RPD は 20% 超のまま（安全だが不完全）。** 主仮説は支持。

| 症例 | F 追加 px（G1+G2, d≥5） | D 追加 px（50 μm） | E 追加 px（50 μm） |
|---|---|---|---|
| abe 20250409 | 237 + 75 = **312** | 9,050 + 12,360 = 21,410 | 3,471 + 1,813 = 5,284 |
| abe 20260225 | 184 + 0 = **184** | 7,873 + 11,809 = 19,682 | 3,032 + 902 = 3,934 |
| asai 20230314 | 142 + 153 = **295** | 1,318 + 2,641 = 3,959 | 1,754 + 1,389 = 3,143 |

- 追加画素の inward からの最大距離は 2.3–3.3 px（上限 8 px 未満、アーケード規模ではない）。
- 点の平均移動はほぼ 0。abe 2/25 だけ 1–4 点が 0.71 px（対角 1 歩）。
- QA の `*_vs_de.png` で、D の橙は帯状に広い。F の橙は inward 輪郭のごく細い縁（fillPoly の食い違い）。
- G2 の切れ血管は戻らない（Pass-2 なし）。abe の RPD が下がらない理由は D / E と同じ。

### E の非単調（asai 52.1→51.9→47.4）と引力のちらつき

**F の mean/max move と add/remove は単調（0→5 で一段、以後平坦）。first-hit と「法線上の最近 ColorMask」の着地ずれは 0。**

E の非単調は、手描き輪郭を内外両方へ動かすため（小さい d では縮み、大きい d では戻り）。引力ターゲットのちらつきではない。F は起点がすでに ColorMask 上なので、E と同じ first-hit でもターゲットは変わらない。

binary fallback（ColorMask に外れ、同じ法線で血管 binary に当たる点）も **0**。診断のみ。refined には使っていない。

---

## 5. なぜ 5–50 μm が同一か（実装上の帰結）

`inward ⊆ ColorMask₁` なので、inward 輪郭点はほぼすべて「すでに ColorMask 上」→ E のスナップは動かさない。

d>0 の面積差は **密化輪郭の `fillPoly` と画素 inward の差** だけ。

| グレーダー | 症例 | inward px | fillPoly(inward) px | 差 | ColorMask の ROI 外 |
|---|---|---|---|---|---|
| G1 | abe 20250409 | 10,488 | 10,687 | +199 | 339 |
| G2 | abe 20250409 | 6,008 | 6,050 | +42 | 448 |
| G1 | abe 20260225 | 10,114 | 10,280 | +166 | 375 |
| G2 | abe 20260225 | 4,105 | 4,092 | −13 | 462 |
| G1 | asai 20230314 | 5,509 | 5,641 | +132 | 98 |
| G2 | asai 20230314 | 4,484 | 4,626 | +142 | 189 |

ROI 外の ColorMask（Gaussian 滲み 98–462 px）は存在するが、E ルール「既に ColorMask 上なら動かない」のため、法線の先にあっても使われない。外向き専用の「輪郭の外の ColorMask へだけ動く」変種は未試験。

領域成長なし。ROIEnclosure なし。血管 CC の全 union なし。

---

## 6. このパイロットで言えること / 言えないこと

言えること:

- F d=0 は D r=0 と一致する（inward = ColorMask ∩ ROI）。
- asai は inward だけで A 46.8% / E 47–57% から 20.5% まで落ち、fillPoly 一段で MNV 19.8% 採用。D の 7% にはならない。
- abe の外向きは有界（追加は数百 px、D の 1–2 万 px より 1–2 桁小さい）。アーケード飲み込みは 3 例の QA では見えない。
- E と同じ ColorMask first-hit を inward に掛けると、変位スイープは実質無効（点は動かない）。
- E の asai 非単調は引力ちらつきではない。F では mismatch 0、量は単調。
- 3 例は単一機種。交差検証はしていない。

言えないこと:

- 本番既定 ON。未配線。
- 他機種・他 FOV。
- 統計的有意。
- 「外向き専用スナップ」（既に ColorMask 上でも、輪郭の外の ColorMask / binary へ動かす）の効果。
- Vsl も 20% を安定して切ること（asai の Vsl は 20.52%）。

---

## 7. QA 画像

`qa/{grader}_{case}_d{um}um_{layer}.png`

4 層は D に合わせた:

1. `user_roi` 緑
2. `inward` シアン（ColorMask ∩ ROI。無制限 shrink）
3. `outward_added` 橙（refined − inward のみ）
4. `refined` マゼンタ

加えて `overlay` / `panel`（2×2） / `vs_de`（F 追加 | D outward-added、F refined | E refined、同 μm）。

例: `qa/g2_abe_20260225_d50um_vs_de.png`
