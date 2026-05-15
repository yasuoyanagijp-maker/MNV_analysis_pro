# ARIAKE OCTA 詳細ユーザーマニュアル V2 — 付録（ImageJ マクロ版 · 整理・要約）

## 目次（付録内リンク）

- [Appendix A: VD output details](#appendix-a-vd-output-details-macro-section-5)
- [Appendix B: MNV output tables](#appendix-b-mnv-output-tables-macro-section-61)
- [Appendix C: Network Complexity Score](#appendix-c-network-complexity-score-macro-detail)
- [Appendix D: Stability and radial profile score](#appendix-d-stability-and-radial-profile-score-macro-detail)
- [Appendix E: Constants and thresholds](#appendix-e-constants-and-thresholds-macro-section-7)
- [Appendix F: Troubleshooting](#appendix-f-troubleshooting-macro-section-8)
- [Appendix G: Algorithms summary](#appendix-g-algorithms-summary-macro-section-9)
- [Appendix H: Clinical notes](#appendix-h-clinical-notes-macro-section-10)
- [Appendix I: Advanced usage](#appendix-i-advanced-usage-macro-section-11)
- [Appendix J: Units and glossary](#appendix-j-units-and-glossary-macro-section-12)
- [Appendix K: FAQ](#appendix-k-faq-macro-section-13)
- [Appendix L: Support and disclaimer](#appendix-l-support-and-disclaimer-macro-sections-14-15)

本付録は **ImageJ マクロ版**「ARIAKE OCTA 詳細ユーザーマニュアル V2」（Team Yanagi, 2025年12月頃）の記述を、研究室内参照用に整理したものです。**Flet アプリ版の操作・画面・一部アルゴリズム差分**は、正本である **[ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md)** を優先してください。

---

## Appendix A: VD output details (macro section 5)

### A.1 Results-VD.csv の列定義

#### 基本情報

| 列名 | 単位 | 説明 | 算出方法 |
|------|------|------|----------|
| Patient ID | — | 患者識別子 | ファイル名から自動抽出 |
| Superficial Image ID | — | Superficial 層ファイル名 | — |
| Deep Image ID | — | Deep 層ファイル名 | — |

#### FAZ（Foveal Avascular Zone）パラメータ

| 列名 | 単位 | 説明 | 算出方法 |
|------|------|------|----------|
| FAZ (mm²) | mm² | 中心窩無血管領域の面積 | 二値化画像の中心部黒色領域を ROI 選択し面積測定 |
| Circularity | 0–1 | FAZ の真円度 | 4π×面積/(周囲長)² |

**解釈**

- **FAZ 面積**: 正常 0.2–0.4 mm²、拡大は虚血を示唆  
- **Circularity**: 1 に近いほど正円、&lt;0.7 で不整形  

#### 血管密度パラメータ（Superficial 層）

| 列名 | 単位 | 説明 | 算出方法 | 正常範囲（目安） |
|------|------|------|----------|------------------|
| Superficial | % | 全体の血管面積率 | (血管ピクセル数/総ピクセル数)×100 | 45–55% |
| Superior Area (Superficial) | % | 上方領域の血管面積率 | 上方扇形 ROI 内で同様に計算 | 40–50% |
| Temporal Area (Superficial) | % | 耳側領域の血管面積率 | 耳側扇形 ROI 内で同様に計算 | 40–50% |
| Nasal Area (Superficial) | % | 鼻側領域の血管面積率 | 鼻側扇形 ROI 内で同様に計算 | 40–50% |
| Inferior Area (Superficial) | % | 下方領域の血管面積率 | 下方扇形 ROI 内で同様に計算 | 40–50% |

**算出手順（概要）**

1. FAZ 周囲の円形 ROI を設定（半径 = 画像幅/2）  
2. 中心円（半径 = 画像幅/4）を除外  
3. 残りを 4 扇形に分割（対角線で分離）  
4. 各領域で血管ピクセル率を計算  

#### 血管密度パラメータ（Deep 層）

同様の指標が Deep 層についても計算されます。

### A.2 血管検出アルゴリズム（マクロ版記述）

**フィルタリングパイプライン**

1. **前処理**: CLAHE（Contrast Limited Adaptive Histogram Equalization）、背景減算（Gaussian σ=5.0）  
2. **Frangi Filter（血管中心強調）**: スケール 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0 — Hessian 固有値解析、各スケールの最大値を統合  
3. **Gabor Filter（血管方向強調）**: 6 方向（0°, 30°, 60°, 90°, 120°, 150°）、σ=2.0、wavelength=8.0、全方向の最大値を統合  
4. **フュージョン**: Frangi 40% + Gabor 40% + 元画像 20%  
5. **適応的二値化**: Phansalkar 法、局所半径 = 画像サイズの 3%（10–40 px）、k=0.1、R=0  

**品質管理（目安）**

- 平均輝度 &lt;5 → 警告（画像が暗すぎる）  
- SD &lt;10 → 警告（コントラスト不足）  
- 血管密度 &lt;5% または &gt;80% → 警告（異常範囲）  

---

## Appendix B: MNV output tables (macro section 6.1)

以下はマクロ版マニュアルの表構成に沿った説明です。**Flet 版の CSV 列名・順序**は `src/utils/mnv_imagej_csv.py` の `IMAGEJ_CSV_COLUMNS` が最終規約です（細動脈化列などが追加されています）。

### B.1 基本識別情報

| 列名 | 単位 | 説明 |
|------|------|------|
| ID | — | 患者 ID（ファイル名から抽出） |
| File | — | 元画像ファイル名 |
| Subtype | — | MNV パターン分類 |

### B.2 MNV 領域パラメータ

| 列名 | 単位 | 説明 | 算出方法 | 臨床的意義（例） |
|------|------|------|----------|------------------|
| MNV Area (mm²) | mm² | MNV 全体の面積 | ユーザー指定 ROI の面積 | 病変サイズ、進行評価 |
| Vsl Area (mm²) | mm² | 血管占有面積 | 二値化後の白色ピクセル面積 | 血管密度の絶対量 |
| Vsl Density (%) | % | 血管密度 | (Vsl Area / MNV Area)×100 | 血管化の程度 |

### B.3 血管形態パラメータ

| 列名 | 単位 | 説明 | 算出方法 | 正常範囲/解釈（目安） |
|------|------|------|----------|------------------------|
| Vsl Length (mm) | mm | 補正血管長 | スケルトン解析による総長 − ジャンクション補正 | 長いほど複雑 |
| Dilated vessel (%) | % | 拡張血管の割合 | (拡張セグメント長/総血管長)×100 | &gt;20% で動脈化疑い |
| Junction Density (n/mm) | 個/mm | 分岐点密度 | ジャンクション数/血管長 | 5–20 個/mm |
| End Pts Density (n/mm) | 個/mm | 終点密度 | 終点数/血管長 | 高値 = 未成熟 |
| Multi-Branch Pts Density (n/mm) | 個/mm | （マクロ版表記に準拠） | — | — |
| Branch Density (n/mm) | 個/mm | 分岐密度 | 分岐数/血管長 | 10–30 個/mm |

### B.4 血管径パラメータ

| 列名 | 単位 | 説明 | 算出方法 | 解釈（目安） |
|------|------|------|----------|--------------|
| (Skel) Vsl Diameter | μm | 平均血管径（骨格法） | Distance Map 平均値×2×mm_per_pixel×1000 | 成熟度指標 |
| NV Diameter (CV) | % | 血管径の変動係数 | (SD/mean)×100 | &lt;30% = 均一 |

### B.5 形態学的スコア

| 列名 | 単位 | 説明 | 算出方法 | 解釈（目安） |
|------|------|------|----------|--------------|
| Caliber Uniformity Score | 0–100 | 血管口径の均一性 | 複合スコア（6 指標の加重平均） | &gt;85 非常に均一 |
| Network Complexity Score | 0–100 | 血管網の構造的複雑性 | 複合スコア（7 指標の加重平均） | &gt;80 非常に複雑 |
| Maturity Index | 0–100 | 口径–複雑性バランス | 50 + (Caliber Uniformity − Network Complexity) / 2 | &gt;70 成熟優位 |

### B.6 信号強度パラメータ

| 列名 | 単位 | 説明 | 算出方法 | 臨床的意義（例） |
|------|------|------|----------|------------------|
| Vessel density index adjusted by signal intensity (aVDI) | — | 信号補正血管密度指標 | マクロ版マニュアル: 血管密度 × (平均輝度/最大輝度) × 100 | 強度を考慮した血管密度 |
| MNV Area adjusted by signal intensity (aMNV) | mm² | 信号補正 MNV 面積 | マクロ版マニュアル: (平均輝度/最大輝度)×血管面積 | 強度を考慮した血管面積 |
| MNV mean gray intensity (AU) | AU | MNV 領域平均輝度 | MNV 領域内平均グレー値 | 血流信号強度 |
| MNV intensity Variation (CV) | % | 輝度変動係数 | (SD/mean) × 100 | 信号の不均一性 |

**aVDI の詳細（マクロ版マニュアルより）**

- **目的**: 信号強度を考慮した血管密度評価  
- **マクロ版の例**: aVDI = 血管密度(%) × (MNV 領域の平均輝度 / 画像の最大輝度) × 100  
- **Flet アプリ版**: CSV に書かれる数値は ImageJ 互換の定義に従います。**コードを読まない場合の説明・aMNV の式**は正本 **[ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md) §6.1** を参照してください。

### B.7 フラクタル・屈曲度

| 列名 | 単位 | 説明 | 算出方法 | 解釈 |
|------|------|------|----------|------|
| Fractal Dim | — | 全体フラクタル次元 | Box-Counting（ボックスサイズ 2–128） | 1.0–2.0、高値 = 複雑 |
| Tortuosity | — | 加重平均屈曲度 | Σ(分岐長×屈曲度)/Σ分岐長 | — |

### B.8 Flow Deficit（FD）解析 — 3 リング法

| 列名 | 単位 | 説明 | 算出方法 |
|------|------|------|----------|
| FD% (R1/R2/R3) | % | 各リングの FD 面積率 | (黒色ピクセル面積/リング面積)×100 |
| FD Avg Area μm² (R1/R2/R3) | μm² | 平均 FD 面積 | 総 FD 面積/FD 数 |
| FD number (R1/R2/R3) | 個 | FD 個数 | Analyze Particles 相当 |
| FD density /mm² (R1/R2/R3) | 個/mm² | FD 密度 | FD 数/リング面積 |

**リング定義（マクロ版）**

- **R1**: MNV 中心から 0.2 mm  
- **R2**: 0.2 mm から 0.4 mm  
- **R3**: 0.4 mm から 0.6 mm  

### B.9 細動脈化（Arteriolarization）（マクロ §9.2 と整合する概念）

**理論的背景**: 新生血管の成熟過程で一部血管が動脈化（arteriolarization）し、太く滑らかな管腔を形成しうる。活動性・進行性の指標となりうる。

**検出アルゴリズム（マクロ版手順の要約）**

1. スケルトン上の血管径取得  
2. 閾値計算  
3. 閾値超過ピクセルのマスク作成  
4. スケルトンでマスク  
5. 各ピクセルを径に応じて膨張  
6. Gaussian Blur（σ=4）で連続化  
7. 再スケルトン化  
8. セグメント解析  

Flet 版では **CSV の ImageJ 互換列**（Arteriolarization Segment Count 等）および **Pathophysiology の Arteriolarized** 等に反映されます。

---

## Appendix C: Network Complexity Score (macro detail)

**構成要素（7 指標）と重み付け**

1. **Total Loops Score（30%）**  
   - 中心部と周辺部のループ数を合算。ループ数が多いほど高得点になるよう指数関数で変換。  
   - 基準: 0–200 個のループを想定。総ループ数 80 で約 63 点、160 で約 86 点に到達するスケール感（マクロ版マニュアル値）。  
   - **臨床的意味**: 血管同士の吻合が多いほど複雑な構造。  

2. **Euler Complexity Score（30%）**  
   - 中心部と周辺部の Euler 数を平均化。負の大きさ = メッシュ状の複雑さ → 符号反転して正の値にし指数得点化。  
   - Euler 複雑性 30 で約 63 点、60 で約 86 点（マクロ版マニュアル値）。  

3. **Trunk Distribution Score（20%）**  
   - **Centrality（40%）**: 主幹の偏心度が低いほど高得点（Medusa 型の特徴）。  
   - **Radiality（30%）**: 角度分布の変動係数が小さい（全方向均等）ほど高得点。  
   - **Diameter Uniformity（20%）**: 中心/周辺の血管径比が 1.0–1.5 付近で高得点。  
   - **Central Density Bonus（10%）**: 中心部の太い血管割合が 15% 以上でボーナス等。  

4. **Spatial Distribution Score（12%）**  
   - 中心と周辺のループ数比・分岐数比が 1.0（均等）に近いほど高得点。  

5. **Anastomotic Index（5%）**  
   - 総ループ数/総分岐数。0.3 以上で高吻合性。0.3 で約 63 点、0.6 で約 86 点（マクロ版マニュアル値）。  

6. **Branch Density Score（3%）**  
   - 分岐密度 5–30 個/mm を想定。15 個/mm で約 63 点、30 個/mm で約 86 点（マクロ版マニュアル値）。  

7. **Loop Density Score**  
   - ループ密度（内部計算用）。0–8 個/mm を想定。  

**最終統合**: Total Loops 30% + Euler 30% + Trunk 20% + 空間分布 12% + 吻合 5% + 分岐密度 3%。

**補正ロジック（マクロ版マニュアル記載の要約）**

- 超高ループ + 低分岐密度 → 複雑性スコア最低 80 点に引き上げ  
- 超高 Euler 複雑性 → 最低 80 点  
- Medusa 型 + 高ループ → 最低 85 点  
- Seafan 型 + 高ループ → 最低 75 点  
- 極端低複雑性（ループ極少 + 低 Euler）→ 最大 25 点に制限  

---

## Appendix D: Stability and radial profile score (macro detail)

マクロ版マニュアルでは **放射状径プロファイル（10 リング）** に基づく **6 指標**を重み付けして Stability を構成する説明があります。

**前処理**: MNV 領域を中心から 10 分割（ドーナツ状リング）、各リング内の平均血管径（Distance Map）を μm に換算した配列を作成。

**構成要素（6 指標）と重み付け**

1. **CV Score（20%）** — 10 径の変動係数から得点化（変動小 = 高得点）。  
2. **Exponential Score（15%）** — SD/mean を指数核にした得点。  
3. **Adjacent Change Score（20%）** — 隣接リング間の変化率の平均が小さいほど高得点。  
4. **Residual Score（20%）** — 線形トレンドに対する残差変動。  
5. **Reversal Score（15%）** — 外側が太くなる「逆行」の回数・最大変化率をペナルティ化。  
6. **Range Score（10%）** — 最大径と最小径の差を平均で正規化。  

**解釈ガイド（マクロ版）**

- **85 点以上**: 血管径が非常に安定 → Dead tree 型の特徴、成熟・不活性病変  
- **75–85**: 中等度の安定性  
- **75 未満**: 血管径が不安定 → 活動性・未成熟病変、不規則な径変化  

※ Flet 版 CSV では **Caliber Uniformity Score** 等の列名で出力されます。実装の数値は Python パイプラインに従います。

---

## Appendix E: Constants and thresholds (macro section 7)

### E.1 主要定数（マクロ版記載例）

**MNV**

- `MAX_DESPECKLE_ITERATIONS = 15`  
- `ROI_MOD_ITERATIONS = 5`  
- `PHANSALKAR_DESIRED_RADIUS_UM = 24`  
- `FD_NUM_RINGS = 3`  
- `FD_ENLARGE_STEP_MM = 0.2`  

**VD**

- `FRANGI_SCALES = [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0]`  
- `FILTER_ORIENTATIONS = [0, 30, 60, 90, 120, 150]`（度）  
- `GABOR_SIGMA = 2.0`  
- `GABOR_WAVELENGTH = 8.0`  
- `CLAHE_BLOCKSIZE = 127`  
- `CLAHE_MAX_SLOPE = 3`  

### E.2 閾値の医学的根拠（目安）

- **血管密度**: Superficial 45–55%、Deep 40–50%（Superficial より約 5% 低い）、FAZ 0.2–0.4 mm²  
- **MNV 血管径**: 正常毛細血管 8–12 μm、拡張閾値 = 平均+2SD または モード+1  
- **フラクタル次元**: 正常網膜 1.6–1.7、高値 (&gt;1.8) = 複雑・密集、低値 (&lt;1.5) = 単純・疎  

---

## Appendix F: Troubleshooting (macro section 8)

| 現象 | 原因 | 対処 |
|------|------|------|
| No VD files found | 命名規則不一致 | `1.tif` / `2.tif` で終わるか、大文字小文字（.TIF 可） |
| No MNV files found | MNV 画像なし | `_3` または `.tif` の存在、サブフォルダ誤配置 |
| Processing failed - Initial setup failed | 画像が開けない | 破損、ImageJ で直接開けるか、8-bit または RGB |
| Insufficient center pixels for analysis | ROI が過小など | ROI 拡大、画質確認、Low 信頼度として記録 |
| 画像が暗すぎる / コントラスト低い / 血管密度異常 | 撮影・前処理 | 設定・CLAHE・閾値の見直し |

**結果解釈の注意（マクロ版より）**

- **VD**: 左右差 &gt;10%、領域間差 &gt;15%、FAZ 拡大+低密度 等の組み合わせに注意  
- **MNV**: Complexity&gt;80 + Stability&lt;70 → 活動性病変の目安、Dilated vessel&gt;20% → 不安定性疑い  

---

## Appendix G: Algorithms summary (macro section 9)

- **ROI 自動修正**: 重心、角度ソート、反復修正、スムージング、重複点除去  
- **中心 vs 周辺**: `estimatedRadius = sqrt(MNV_Area/π)`、`centerRadius = estimatedRadius/3`、周辺はリング  
- **Box-Counting**: ボックス [2,4,8,16,32,64,128]、log-log 線形回帰、R²  
- **Euler Number**: `V - E + F` または 連結成分数 − ループ数 の理解で解釈  

---

## Appendix H: Clinical notes (macro section 10)

- **VD**: FAZ、層別密度、左右差のパターン読み  
- **MNV サブタイプ**: Dead tree / Tree in bud / Seafan / Medusa / Glomerular の一般的な「フォロー・治療強度」の考え方はマクロ版 §10.2 を参照（**最終判断は医師**）  

---

## Appendix I: Advanced usage (macro section 11)

- **バッチ最適化**: 時系列は `Study/Baseline`, `Month3` … のようにサブフォルダ分割  
- **低品質画像**: `CLAHE_MAX_SLOPE = 5`、`ADAPTIVE_THRESHOLD_PARAM1 = 0.15`、`MAX_DESPECKLE_ITERATIONS = 20` 等（マクロ定数変更例）  
- **高解像度**: Frangi スケール拡張、`PHANSALKAR_DESIRED_RADIUS_UM = 32` 等  
- **微小血管重視**: より細い Frangi スケール、`GABOR_WAVELENGTH = 6.0` 等  

※ Flet 版ではソース変更が必要。変更後は既知症例で検証すること。

---

## Appendix J: Units and glossary (macro section 12)

### J.1 単位換算表（抜粋）

| 測定項目 | 単位 | 換算 |
|----------|------|------|
| 面積 | mm² | 1 mm² = 1,000,000 μm² |
| 長さ | mm | 1 mm = 1000 μm |
| 密度（血管） | % | (面積/総面積)×100 |
| 密度（点） | n/mm | 個数/長さ |
| 血管径 | μm | Distance Map×2×スケール |
| 屈曲度 | 無次元 | 実長/直線距離 ≥1.0 |
| フラクタル次元 | 無次元 | Box-Counting 傾き 1.0–2.0 |

### J.2 略語一覧（抜粋）

| 略語 | 英語 | 日本語 |
|------|------|--------|
| OCT-A | Optical Coherence Tomography Angiography | 光干渉断層血管撮影 |
| VD | Vessel Density | 血管密度 |
| MNV | Macular Neovascularization | 黄斑新生血管 |
| FAZ | Foveal Avascular Zone | 中心窩無血管領域 |
| FD | Flow Deficit | 血流欠損 |
| CC | Choriocapillaris | 脈絡膜毛細血管板 |
| ROI | Region of Interest | 関心領域 |
| CV | Coefficient of Variation | 変動係数 |
| aVDI | adjusted Vessel Density Index | 信号補正血管密度指標 |
| aMNV | adjusted MNV Area | 信号補正 MNV 面積 |

---

## Appendix K: FAQ (macro section 13)

- **VD と MNV を別日に実行できるか** — 可能。出力フォルダを日付・解析種で分けること。  
- **複数時点の比較** — 時点ごとに別フォルダで解析し、統計ソフトで結合。  
- **スキャンが 6×6 mm でない** — 実寸を Image Width / **Image Scale (mm)** に入力。  
- **ROI が難しい** — 初回は粗く囲む → 自動修正を確認 → ROI 保存再利用 → 必要ならパイプライン段階保存で中間画像確認。  
- **異常値の扱い** — Quality、生理学的妥当性、可視化画像、統計的外れ値、感度分析。  
- **他施設との比較** — スキャンプロトコル、前処理、解析バージョン、命名規則、共通症例セットでの ICC 等を統一。  
- **治療効果のカットオフ例** — MNV Area ±0.5 mm²、Complexity ±15 点、Stability ±15 点など（**自施設で検証**すること）。  
- **カスタマイズ** — 定数のみ / フィルタ / アルゴリズム変更の三段階。変更後は文書化と妥当性確認。  

---

## Appendix L: Support and disclaimer (macro sections 14-15)

- **バグ報告（マクロ版テンプレ）**: OS、ImageJ 版、Java 版、マクロ `LIB_VERSION`、再現手順、入力仕様、Log 全文。  
- **本ソフトは医療機器ではない**、臨床判断の補助、Garbage in–garbage out、標準化、継続的検証。  

---

*出典は ImageJ マクロ版 V2 マニュアル。全文の一字一句の転載ではなく、表・手順の整理・要約を含みます。Flet アプリ版の差分は [ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md) を参照。*
