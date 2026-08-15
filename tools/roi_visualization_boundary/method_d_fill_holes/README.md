# Method D inward — fill holes + morphological close（パイロットのみ）

D inward（`ColorMask₁ ∩ user_roi`）の密度が ≈0.99 になる同語反復を、穴埋めとギャップ閉鎖で外せるか。  
**本番未接続。** Pass-2 なし。Method C なし。`method_d/` / `method_e/` / `method_f/` には書いていない。

実行:

```bash
.venv/bin/python tools/roi_visualization_boundary/method_d_fill_holes/compute_method_d_fill_holes.py
```

出力先: `tools/roi_visualization_boundary/method_d_fill_holes/`

| ファイル | 内容 |
|---|---|
| `compute_method_d_fill_holes.py` | 本スクリプト |
| `fill_holes_results.csv` | グレーダー × 症例 × gap_um（36行）。面積・密度・穴/ギャップ画素・RPD列 |
| `fill_holes_rpd.csv` | 症例 × gap の A / inward / fill / close / close+fill RPD |
| `device_check.json` | meta.json の機種・スケール |
| `qa/` | 36 PNG（ローカル）。`*_fill_only.png` と `*_g{um}um_overlay.png`（橙=close、黄=fill） |

`MNVPipeline.analyze` は回していない。面積は画素カウントのみ。ColorMask / inward はグレーダー×症例で1回。

---

## 1. 定義

```
inward            = ColorMask₁ ∩ user_roi          # D 半径 0
filled_only       = binary_fill_holes(inward)      # scipy.ndimage（4-連結 flood）
closed            = morph_close(inward, disk(r_px)) ∩ user_roi
closed_then_fill  = binary_fill_holes(closed) ∩ user_roi

r_px = round_half_up(gap_um × px_per_mm / 1000)
gap_um ∈ {0, 5, 10, 20, 30, 50}     # 0 = close なし

MNV  = mask px × (3 mm / width)²
Vsl  = (binary ∩ mask) px × 同じスケール     # filled は binary ∩ filled（未クリップ）
Dens = Vsl / MNV
```

`filled ∩ user_roi` は全6ランで `filled` と一致（穴の ROI 外は 0 px）。  
close / close+fill は必ず `∩ user_roi`（ハンド ROI の外へは伸ばさない）。

CIRRUS 150 px/mm の換算（D/E と同じ）:

| gap_um | gap_px |
|---|---|
| 0 | 0 |
| 5 | 1 |
| 10 | 2 |
| 20 | 3 |
| 30 | 5 |
| 50 | 8 |

使わないもの: Pass-2、ROIEnclosure、血管 CC の全 union、Accept/Undo、本番フラグ。

---

## 2. 結論（先に）

| 問い | 答え |
|---|---|
| fill holes だけで Density を 0.99 から外せるか | **部分的。** 5/6 ランが 0.961–0.981。abe 20260225 G2 は穴 0 で 0.996 のまま。下げ幅は 0.01–0.03 で、病変内密度としてはまだ同語反復に近い。 |
| 穴は実体か | **この3例では小さい。** 総 789 px（0.035 mm²）。ランあたり 0–236 px。B' の enclosed padding（総 768 px）と同規模。理論は正しいが、fill だけでは効かない。 |
| close+fill で tautology は直るか | **10 μm 以上で 6/6 が <0.99。** 5 μm ではまだ G2 abe 2/25 が 0.995。20–50 μm では 0.70–0.94 まで下がる。 |
| その代償 | **MNV/Vsl RPD はギャップとともに悪化。** 緩い G1 ROI 内の背景血管を close が橋渡しする（arcade-like uptake）。asai の fill だけの MNV 採用（19.7%）も close ≥5 μm で消える。 |
| 20% 採用するか | **しない。** fill のみ asai MNV が 19.7% で採用、Vsl は 20.5% のまま非採用。abe 2例はどの gap でも NA。close は採用を壊す。 |
| 本番 | 未配線。n=3・すべて CIRRUS 3 mm。交差検証なし。 |

---

## 3. Density（6ラン）

### 3.1 inward vs fill holes のみ

| 症例 | G | inward | filled | 穴 px | 穴内 Vsl | Dens が <0.99 |
|---|---|---|---|---|---|---|
| abe 20250409 | G1 | 0.9920 | 0.9709 | 236 | 8 | yes |
| abe 20250409 | G2 | 0.9933 | 0.9811 | 75 | 0 | yes |
| abe 20260225 | G1 | 0.9864 | 0.9696 | 183 | 8 | yes（inward 時点で既に 0.986） |
| abe 20260225 | G2 | 0.9961 | 0.9961 | **0** | 0 | **no** |
| asai 20230314 | G1 | 0.9924 | 0.9680 | 142 | 3 | yes |
| asai 20230314 | G2 | 0.9929 | 0.9608 | 153 | 3 | yes |
| **合計** | | | | **789** | **22** | 5/6 |

穴の 97% は無血管（Vsl 22 / 789）。想定どおり。最大 CC は 137 px（asai 両グレーダー）。  
B' の「ROI 境界に触れない padding」とは別定義だが、量はほぼ同じ（768 vs 789）。血管ループを全部埋めても、この3例ではポケットが小さい。

### 3.2 close / close+fill

| 症例 | G | cf 0 | cf 5 | cf 10 | cf 20 | cf 50 |
|---|---|---|---|---|---|---|
| abe 20250409 | G1 | 0.971 | 0.953 | 0.912 | 0.883 | 0.829 |
| abe 20250409 | G2 | 0.981 | 0.978 | 0.965 | 0.942 | 0.913 |
| abe 20260225 | G1 | 0.970 | 0.941 | 0.858 | 0.837 | 0.807 |
| abe 20260225 | G2 | **0.996** | **0.995** | 0.983 | 0.970 | 0.941 |
| asai 20230314 | G1 | 0.968 | 0.961 | 0.907 | 0.812 | 0.703 |
| asai 20230314 | G2 | 0.961 | 0.958 | 0.927 | 0.909 | 0.830 |
| 6/6 <0.99 | | no | no | **yes** | yes | yes |

close 単独でも 10 μm で 6/6 <0.99。close のあと fill が足す分は、10–20 μm で一部ランに 34–478 px。30–50 μm では close が先にギャップを埋めるので fill 追加は 0。

**tautology が全ランで外れる最初の半径は 10 μm（2 px）。**

---

## 4. ギャップ追加と arcade-like uptake

close 追加画素（`closed − inward`、すべて user_roi 内）:

| gap | abe 4/9 G1/G2 | abe 2/25 G1/G2 | asai G1/G2 | close 内 Vsl 割合（6ラン） |
|---|---|---|---|---|
| 5 | 116 / 36 | 174 / 11 | 69 / 45 | 14–45% |
| 10 | 959 / 214 | 1315 / 89 | 548 / 264 | 15–36% |
| 20 | 1780 / 521 | 2206 / 194 | 1341 / 519 | 19–37% |
| 50 | 4634 / 1538 | 4146 / 723 | 4023 / 1685 | 28–63% |

G1（緩い ROI）の close 追加は常に G2 の数倍。緩い余白の中の近傍血管を楕円 close が橋渡しする。  
50 μm の asai G1 では close 4023 px のうち Vsl 1237 px（31%）。Density が下がる主因は「無血管ポケット」ではなく、**ROI 内の背景・アーケード血管の取り込み**。

QA: 緑=user、シアン=inward、橙=close 追加、黄=close 後の fill。例: `qa/g1_abe_20260225_g20um_overlay.png`。

---

## 5. グレーダー間 RPD（採用 ≤20%）

Method A は 094130 CSV。inward は D 半径 0 と同じ。

### 5.1 MNV Area RPD

| 症例 | A | inward | fill | close 5 | cf 5 | close 10 | cf 10 | cf 20 | cf 50 |
|---|---|---|---|---|---|---|---|---|---|
| abe 20250409 | 64.0 | 54.3 NA | 55.2 NA | 54.8 NA | 57.1 NA | 59.1 NA | 60.5 NA | 61.8 NA | 66.8 NA |
| abe 20260225 | 96.5 | 84.5 NA | 86.0 NA | 85.7 NA | 88.5 NA | 92.6 NA | 95.8 NA | 97.2 NA | 98.8 NA |
| asai 20230314 | 46.8 | **20.5 NA** | **19.7 採用** | 20.8 NA | 20.4 NA | 24.2 NA | 24.2 NA | 36.3 NA | 42.8 NA |

asai の inward 20.5% は fill で 19.7% に下がり、MNV だけ採用。close を足すとすぐ 20% を超えて非採用に戻る。abe はどの gap でも NA、しかも悪化。

### 5.2 Vsl Area / Density RPD

- Vsl RPD は inward と fill でほぼ同じ（asai 20.47 → 20.45、まだ非採用）。close で悪化（asai cf50 で 26.7%）。
- Density RPD は inward 0.05–1.0%。fill で 0.7–2.7%。close が大きいほど Dens RPD も開く（asai cf50 で 16.6%）。分母に余白・背景血管が入るため。

20% 採用を「close+fill で稼ぐ」ことは、この3例ではできない。

---

## 6. このパイロットで言えること / 言えないこと

言えること:

- fill holes の理論（閉じた無血管ポケットを MNV に入れる）は正しい。穴はほぼ無血管。
- ただしこの3例の穴は小さく、Density は 0.96–0.98 にしか下がらない。1ランは穴ゼロ。
- close ≥10 μm なら Density の 0.99 同語反復は外れる。同時に MNV/Vsl RPD は悪化し、緩い ROI 側が背景血管を飲む。
- asai MNV の 20.5% は fill だけで 19.7%（採用）。close はその採用を壊す。
- 3例はすべて CIRRUS / 3 mm / 150 px/mm。

言えないこと:

- 本番既定 ON。未配線。
- 他機種・他 FOV（`gap_um → gap_px` が変わる）。
- 統計的有意。n=3。
- close で下がった Density を「病変内灌流」として読んでよいか（arcade 取り込みが混ざる）。

---

## 7. QA

`qa/{grader}_{case}_fill_only.png` — 黄 = fill holes のみ。  
`qa/{grader}_{case}_g{05,10,20,30,50}um_overlay.png` — 橙 = close 追加、黄 = close 後の fill。
