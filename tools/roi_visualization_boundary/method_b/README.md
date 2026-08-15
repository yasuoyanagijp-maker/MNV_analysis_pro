# Method B: RGB可視化差分による解析境界の再定義

3症例 × 2グレーダー（2026-08-15）で、ハンドドローROIの代わりに
ARIAKE RGB可視化から Fiji マクロと同じ差分抽出で ColorMask 相当を作り、
MNV Area / Vsl Area / Vsl Density のグレーダー間 RPD を比較した。

実行:

```bash
.venv/bin/python tools/roi_visualization_boundary/method_b/method_b_visualization_boundary.py
```

出力: `rpd_comparison.csv`。QA画像は `qa_masks/`（ローカル。コミットしない）。
採用再計算: `recompute_method_b_adoption.py` → `adoption/`。
B′: `prime/compute_method_b_prime.py`。

---

## 1. RGB可視化モジュール

`visualizer.py` というファイル名はリポジトリに無い。候補は次の3つ。

| モジュール | 役割 | 採用 |
|---|---|---|
| `src/ariake_octa/mnv/visualization_rgb.py` | ImageJ `createVisualizationRGB` 互換。グレースケール上に黄=通常血管・赤=拡張血管を減算合成 | **採用** |
| `src/ariake_octa/mnv/color_coded_binary.py` | 血管太さの JET ヒートマップ。背景は黒で、元画像との差分は「着色MNV」のアナログにならない | 不採用 |
| `src/ariake_octa/mnv/flow_deficit_visualizer.py` | Flow deficit のリング可視化 | 不採用 |

選定理由: 本番パイプライン（`src/core/mnv_pipeline.py` 656行付近）が帳票・QA用に呼ぶのが `VisualizationRGB.create_rgb_visualization` であり、手動赤/黄着色の直接の代替になる。

制約（実装上重要）: 着色減算は `lesion_mask`（ハンドドローROI）の内側にだけ適用される。ROI外は元のグレーのまま。したがって ColorMask は原理的に元ROIの外側へほとんど伸びない（Gaussian σ=1 の滲みのみ。実測 98–462 px）。

差分抽出ではスケールバー／テキストが着色画素として混入するため、`add_overlays=False` を追加してオフにした。

---

## 2. セグメンテーションの実行順序

**血管検出自体は全画像。ROIでクリップしてから検出しているのではない。**

`MNVPreprocessor.preprocess_mnv` は Mexican Hat / Tubeness を画像全体にかけ、コメントでも「ROIマスク適用は行わない」と明記している。ROIは集計時だけ使う。

```
vessel_area_pixels = np.sum((binary > 0) & (roi_mask > 0))
```

再実行でも、ROI外の血管画素は 8.4万–12.9万 px と大量に残っていた（3×3 mm 視野の背景血管全体）。一方 ColorMask のROI外画素は数百 px だけだった。

効果範囲:

- MNV Area: ColorMask が G1 の余白を削るので改善しうる（今回は3例とも RPD 低下）。
- Vsl Area: RGB着色がROI内限定のため、G2のタイトROIで集計から外れた血管は戻らない。改善は限定的（今回もその通り）。
- Vsl Density: 今回の改善対象ではない。Method B で悪化していないことだけ確認する。

---

## 3. 血管binaryの再現

指定フォルダに血管binaryは保存されていない。原画像（export/images、468×450）と ROI マスク（export/masks）から `preprocess_mnv`（`FILTER_PARAMS_SMALL`、幅 450 px < 800）を再実行した。

Method A の再計算値はバッチCSVと **6ランすべてで完全一致**（MNV / Vsl / Density の差 = 0）。血管binaryは再現できている。

G2の他バッチは Desktop 上に見つからなかった（`second_reader_output_2026_08_15` の同一3症例のみ）。タイトROIが「スタイル」か「質の問題」かは、この3例だけでは切れない。

---

## 4. Method B の定義

```
ColorMask = Li(GaussianBlur(unweighted_mean(|raw - rgb_viz|), sigma=1.0))
MNV Area    = ColorMask px × (3 mm / 450)^2
Vsl Area    = (ColorMask ∩ vessel_binary) px × scale
Vsl Density = Vsl Area / MNV Area
```

- 8-bit化: 単純平均 `(R+G+B)/3`（輝度加重より Dice が高い）。
- Invert: しない。Invert すると非着色背景が前景になる。
- ColorMask vs `binary ∩ ROI` の Dice: 0.80–0.87。前景=着色血管で正しい。
- Method A の RPD は `MNV_integrated_20260815_094445` をそのまま使用（再計算しない）。Vsl Density の Method A RPD だけは recheck_list に無いため、同じ2本のバッチCSVから算出した。

---

## 5. RPD 比較（3症例 × 3指標）

| 症例 | 指標 | Method A RPD | Method B RPD | Δ (B−A) |
|---|---|---|---|---|
| abe 20250409 | MNV Area | 64.0% | 50.6% | −13.4 |
| abe 20250409 | Vsl Area | 55.0% | 50.4% | −4.5 |
| abe 20250409 | Vsl Density | 9.9% | 0.15% | −9.7 |
| abe 20260225 | MNV Area | 96.5% | 78.7% | −17.9 |
| abe 20260225 | Vsl Area | 84.7% | 77.8% | −6.9 |
| abe 20260225 | Vsl Density | 14.8% | 1.0% | −13.8 |
| asai 20230314 | MNV Area | 46.8% | 18.2% | −28.6 |
| asai 20230314 | Vsl Area | 30.1% | 18.1% | −11.9 |
| asai 20230314 | Vsl Density | 17.3% | 0.06% | −17.3 |

方向は3例とも Method B で RPD 低下。asai の面積系だけ 20% 閾値を下回った。abe 2例の面積系は改善しても採用圏外のまま。

### Vsl Density について（改善対象ではない）

Method A ですでに 9.9–17.3% で採用圏内。Method B では 0.06–1.0% まで下がったが、これは **改善というより定義の帰結** である。ColorMask が着色血管そのものなので、分母≈分子になり両グレーダーとも密度 ≈ 0.99 になる。臨床的な「病変内血管密度」としては解釈しない。悪化はしていない。

### Vsl Area の限界

残差の主因は「余白」ではなく、G2 ROI が血管本体を切っていること。RGB着色がROI内限定なので、Method B でもその画素は ColorMask に入らない。abe 20260225 では Vsl Area RPD が 84.7% → 77.8% と、改善幅が小さい。

---

## 6. 3症例だけで言えること / 言えないこと

言えること:

- この3ペアでは、RGB差分 ColorMask を分母にすると面積系 RPD は一貫して下がる。
- ただし2/3例は RPD>20% のままで、ROIスタイル差だけでは説明しきれない（血管の取りこぼしが残る）。
- 血管検出は全画像なので、ROI外の血管binaryは存在する。それを Method B に使うには、RGB着色の ROI ゲートを外す別設計が必要（今回は本番可視化の仕様に従った）。

言えないこと:

- 統計的有意差。n=3。
- G2 のタイトROIが全読影に一貫するスタイルなのか、このセッションの質の問題なのか。
- 本番パイプラインへの実装可否（密度の意味が変わる、面積が病変外形ではなく血管画素に近づく）。

---

## 7. Method C（ROIEnclosure）は却下

ColorMask を凸包＋スプラインで包む案は試したが採用しない。包絡は元 ROI の 4–9 倍に膨らみ、全画像検出の背景血管を飲み込む。RPD は下がるが、両グレーダーが同じ広い血管網に収束するだけで、グレーダー判断を測定から外す。比較対象は A（ハンドドロー ROI）と B（ColorMask 画素）のみ。
