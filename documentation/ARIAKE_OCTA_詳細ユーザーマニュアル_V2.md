# ARIAKE OCTA 詳細ユーザーマニュアル（V2 · Flet アプリ版）

## 本書について

- **前身**: ImageJ マクロ版「ARIAKE OCTA 詳細ユーザーマニュアル V2」（2025年12月頃、Team Yanagi）の構成・用語・臨床的解釈を踏襲しています。
- **対象ソフトウェア**: 本リポジトリの **Flet + FastAPI** アプリケーション（`main_app.py` / `run_flet.sh` / 配布用 `ARIAKE_OCTA.app`）。解析コアは Python（`src/core`、`src/ariake_octa`）。
- **マクロ版との差分の要約**は次のとおりです。

| 項目 | ImageJ マクロ版 | 本アプリ（Flet 版） |
|------|-----------------|---------------------|
| UI | マクロのダイアログ・ImageJ Log | **ログイン → ダッシュボード → ROI / ウィザード → 結果**（[USER_MANUAL.md](../USER_MANUAL.md)） |
| 起動・配布 | ImageJ から実行 | **macOS**: `インストール.command` + `ARIAKE_OCTA.app` 等（[README.md](../README.md)） |
| VD サフィックス | 固定の `_1` / `_2` 想定が中心 | ダッシュボードの **VD sup. / deep suffix** で変更可能（既定 `1.tif` / `2.tif`） |
| MNV 混在フォルダ | 「Analysis Mode Selection」で Yes/No | **MNV フォルダバッチ**時、`*1/*2/*4` および `image1/2/4` パターンを除外した残りをキュー化。除外後ゼロ件なら **フォルダ内全画像**にフォールバック（`src/utils/batch_input_filter.py`） |
| バッチ後の QC | 各画像ごと「Yes / Quality is low」ダイアログ、`To_be_reanalyzed` への 4 倍拡大保存等 | **MNV フォルダバッチ**では解析直後に結果画面へ進み、**「OK — next image」「Redo ROI」「Stop Here」**でレビュー（`results_screen.py`）。**自動 4 倍拡大と専用サブフォルダ出力はマクロ版と同一ではない**場合があります。低品質時は **ROI のやり直し**、**結果画面の再解析**、必要なら **画像解像度の前処理**および **Image Scale (mm)** の見直しを推奨します。 |
| 細動脈化 | マニュアル §9.2 相当の説明 | **Arteriolarization** 指標を CSV に **ImageJ 互換列名**で出力（下記 §6.1 補足）。病態分類に **Arteriolarized** が現れることがあります。 |
| CSV / 式 | マクロの測定表 | **MNV 列順・一部派生指標**は `src/utils/mnv_imagej_csv.py` の実装が正。**aVDI / aMNV** 等はコードコメントに準拠し、マクロ版マニュアル中の数式と字面が異なる場合があります。 |
| Complexity / Caliber Uniformity | 7 成分／6 成分の加重（マクロ） | **層別 PCA**（`pattern_metrics.py` + `complexity_ref_*` / `stability_ref_*`）。定義は **§6.3** |

**操作手順の早見**は [USER_MANUAL.md](../USER_MANUAL.md)、開発者向けは [DEVELOPER.md](../DEVELOPER.md) を参照してください。

**マクロ版 V2 に基づく整理・要約（VD/MNV 列定義、旧マクロの Complexity・Stability 加重、定数一覧、FAQ 等）**は別紙 **[ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md)** に分離しています。

**重要（2026-08 時点）**: Flet 版の **Network Complexity Score** と **Caliber Uniformity Score** は、マクロ版の「7 成分／6 成分の単純加重」ではなく、層別参照 JSON に基づく **PCA 合成**です。定義・パラメータは本書 **§6.3** を正とし、付録 C/D のマクロ説明は歴史的参照として残しています。

---

## 1. 概要

### 1.1 目的

ARIAKE OCTA は、光干渉断層血管撮影（OCT-A）画像から **血管密度（VD）** と **黄斑新生血管（MNV）** の定量的解析を行い、血管特徴に基づく **カラーコード表示**（RGB 可視化）等で MNV を評価するためのソフトウェアです。マクロ版は ImageJ 上で動作しましたが、**本版の操作 UI は主に Flet で実装**されています。

### 1.2 主要機能

- **VD Analysis**: 網膜血管密度の定量評価  
  - 血管抽出（Frangi / Gabor 等のパイプライン）  
  - FAZ（中心窩無血管領域）の自動検出  
  - 血管密度の領域別測定  
- **MNV Analysis**: 黄斑新生血管の形態・構造解析  
  - MNV パターン分類（例: Dead tree, Tree in bud, Glomerular, Seafan, Medusa）、**Maturity Index** 等  
  - **Flow Deficit 解析**（脈絡膜毛細血管板 CC と MNV のペア画像がある場合）  
  - フラクタル次元・トルチュオシティ解析  
  - **細動脈化（Arteriolarization）** 指標（高歪度セグメントに基づく定量化）  
- **Both / 統合フロー**: 施設のワークフローに応じ、VD と MNV を続けて扱うモード（ダッシュボードの解析タイプに依存）

### 1.3 事前準備

#### 1. 画像ファイルの命名規約（推奨・マクロ版と同趣旨）

**VD 解析用**

- 表層: `患者ID_1.tif`（例: `Patient001_1.tif`）  
- 深層: `患者ID_2.tif`（例: `Patient001_2.tif`）  

**MNV 解析用**

- MNV 画像: `患者ID_3.tif`（例: `Patient001_3.tif`）  
- Flow Deficit 用（CC）: `患者ID_4.tif`（例: `Patient001_4.tif`）  

**重要**: サフィックス（`_1` … `_4`）が規約と一致しないと、**標準ロジック**ではファイルが正しくペアリングされないことがあります。本アプリでは **VD 用サフィックスを UI で変更**できますが、研究内で命名を統一することを強く推奨します。

#### 2. フォルダ構成（推奨）

```text
入力フォルダ/
├── Patient001_1.tif
├── Patient001_2.tif
├── Patient001_3.tif
├── Patient001_4.tif
├── Patient002_1.tif
├── Patient002_2.tif
└── ...
```

---

## 2. 解析の種類と選択（Flet UI への対応）

### 2.1 起動時の設定項目（マクロのダイアログ → ダッシュボード）

マクロ版では「ARIAKE OCTA Analysis Parameters」ダイアログでした。Flet 版では **ホーム（ダッシュボード）** で同等の情報を指定します。

| マクロの設定 | Flet 版での扱い |
|--------------|----------------|
| Input directory | **フォルダ／画像の選択**、**手動パス**、または Web 時はサーバ側パス探索（[USER_MANUAL.md](../USER_MANUAL.md) §8） |
| Results Output directory | **出力フォルダ**の指定（セッションにより `output_folder` / 入力隣接の `output_folder_YYYY_MM_DD` 等） |
| Analysis Type | **解析タイプ**（MNV / VD / バッチ / 統合 等、ダッシュボードのコントロール） |
| Side (VD only) | **右眼 / 左眼**（VD 関連の設定） |
| Image Width = mm | **Image Scale (mm)**（OCT-A のスキャン幅。正確な値が重要） |
| Save Pipeline Stages? | デバッグ用の中間保存は **実装・ビルドにより異なる**場合があります。詳細は開発者向けドキュメントまたはログを参照 |

### 2.2 Analysis Mode Selection（マクロ）と Flet の MNV フォルダバッチ

マクロでは「MNV のみ解析するか（Yes）／標準の `_3`/`_4` ロジックか（No）」を尋ねていました。

**Flet 版（MNV フォルダバッチ）のざっくりした挙動**

1. フォルダ内の画像を列挙したうえで、**ファイル名が `*1.*` / `*2.*` / `*4.*`（拡張子 tif/tiff/png/jpg/jpeg）に該当するもの**および **`image1` / `image2` / `image4` を含む名前**を **MNV キューから除外**します（VD 用・FD 用スロットとみなす）。  
2. 除外の結果、**キューが空になる**場合は、**フォルダ内の全画像**を MNV 対象に戻します（マクロの「MNV のみ・拡張子多数決」に近い救済）。

混在フォルダで意図しないファイルが入った場合は、**サブフォルダ分け**や **命名規約の整理**を推奨します。

### 2.3 実行開始

ROI・ウィザード上の **Confirm & Start Analysis** 等で解析を開始します（単枚／バッチで画面遷移が異なります）。

---

## 3. MNV 解析時の Quality Control（品質管理）

### 3.1 マクロ版との違い（重要）

マクロ版では各画像処理後に **「Is the analysis appropriate?（Yes / Quality is low）」** が出て、Quality is low 時に **4 倍拡大画像を `To_be_reanalyzed` に保存**する流れでした。

**Flet 版（MNV フォルダバッチ）**では、各画像の解析後に **結果画面の上部バナー**で次を選びます。

- **OK — next image**（最後の画像では **OK — open final report**）: この結果をバッチに取り込み、次の画像の ROI へ進む。  
- **Redo ROI**: 同じファイルで ROI からやり直す。  
- **Stop Here**（最終画像以外）: ここまでの結果だけでサマリーへ進む。

**CSV の「Quality of analysis」**は、パイプラインの `quality_control` / `qc_status` 等に基づき **Pass / Fail** 等が付く設計です（`src/core/mnv_pipeline.py`、`mnv_imagej_csv.py`）。統計解析前に **Fail を除外または再解析**する運用は、マクロ版と同様に推奨されます。

### 3.2 「低品質」と判断すべき状況の目安（マクロ版と共通）

以下では **Redo ROI**、**再解析**、または **画像の前処理・スケール入力の見直し**を検討してください。

**視覚的な問題**

- ROI が不適切（MNV 全体を囲めていない、背景が多い、幹が切れている）  
- 血管抽出の明らかな失敗（ノイズ主体、血管以外の構造物）  

**スコアの異常（例）**

- Caliber Uniformity（UI: Uniformity）や Complexity が極端、または計算不能に近い値  
- **Uniformity が厳密に 25.0** — 結果画面が再解析を勧める（§6.3.3）。ROI・画質を見直す  
- 解像度不足を示唆するログ・警告  

### 3.3 技術的な警告（ログ）

マクロ版と同様、以下に注意してください（例）。

- `Insufficient center pixels` 等の中心部ピクセル不足  
- CC 画像が見つからない場合の Flow Deficit スキップ  
- ROI インデックス不正  

### 3.4 再解析

- **同一結果のやり直し**: 結果画面の **再解析（Re-analyze）** から元画像パスが残っている症例を ROI に戻せます（`results_screen.py`）。  
- **マクロ版の「4 倍拡大を自動保存して再投入」**に相当する専用フローは **必ずしも同じではありません**。必要に応じて **外部でリサンプリング**し、**Image Scale (mm)** を物理サイズに合わせて修正してください。

### 3.5 CSV における QC

`Quality of analysis` 列を用いて、**Fail 行の扱い**（除外・再解析後の置換）を統計計画に含めてください。

---

## 4. データフォルダ構造

### 4.1 入力フォルダの要件

マクロ版 §4.1 と同様の構成を推奨します（VD: `_1` / `_2`、MNV: `_3`、CC: `_4`）。Flet 版では **VD サフィックスを UI で変更可能**です。

### 4.2 出力フォルダ構造

マクロの `[Input_Folder名]_VD` / `_MNV` のような **固定サブフォルダ名**ではなく、**セッションで指定した出力先**、または **入力隣接の日付付きフォルダ**、**Web 時のダウンロード**等のパスになります。重要なのは **CSV・画像エクスポート・PDF** を、研究プロトコルに沿って **バックアップ可能な場所**に集約することです。

---

## 5. VD 解析の出力データ詳細

マクロ版マニュアル §5 の列定義・正常範囲・血管検出パイプライン（FAZ、扇形領域、Frangi/Gabor/Phansalkar 等）は **原則として本アプリの VD 解析でも同趣旨**です。

**詳細表・アルゴリズム段階（整理版）** → [付録・Appendix A](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-a-vd-output-details-macro-section-5)

列名や追加列は **エクスポート CSV のヘッダ**を最終確認してください。

**品質管理の目安（マクロ版より）**

- 平均輝度が極端に低い、SD が極端に小さい、血管密度が異常範囲、等 → 撮影条件・ROI・前処理を再確認  

---

## 6. MNV 解析の出力データ詳細

### 6.1 主要パラメータ一覧

マクロ版 §6.1 の表（ID、File、Subtype、MNV 面積、血管密度、形態スコア、信号強度補正、aVDI、aMNV、フラクタル、トルチュオシティ、FD 3 リング法 …）は **本アプリの MNV CSV（ImageJ 互換列セット）** に対応します。

**詳細表・FD リング定義・細動脈化アルゴリズム手順（整理版）** → [付録・Appendix B](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-b-mnv-output-tables-macro-section-61)

列の完全な一覧と**出力される順序**は、実際にアプリから書き出した **MNV の CSV ファイルの 1 行目（ヘッダ行）** を見るのがもっとも確実です。列名は従来の ImageJ マクロ版の測定表と揃えるため、英語のまま長い名称になっていることがあります。開発者向けの一覧名としてリポジトリ内では `IMAGEJ_CSV_COLUMNS` と呼ばれています。

**aVDI / aMNV について（コードを読まずに理解するための説明）**

マクロ版の解説書には、「信号の強さも考慮した血管密度」などを **かけ算や比で表した式** が書かれていることがあります。本アプリでも **同じ列名（aVDI、aMNV など）** で CSV に書き出しますが、**数式の形が文献や旧マニュアルの 1 行と字面どおり一致しない場合があります**。そのときは、次の「ソフトが内部で行っている考え方」を正としてください。

1. **MNV 領域の平均輝度（CSV では `MNV mean gray intensity (AU)` 付近）**  
   指定した MNV の ROI の中で、**平均の明るさを、ROI 内で一番明るい値で割った比**として計算します（最大が 0 のときは 0 とみなします）。値は **0 に近いほど全体的に暗い／1 に近いほど平均がピークに近い**、という読み方になります。

2. **血管密度（`Vsl Density` と対応する内部の「比率」）**  
   **血管として検出された面積**を、**MNV の ROI 全体の面積**で割ったものです（0 = 血管がほとんどない、1 = 全面が血管、に近いイメージの小数）。画面上の「％」表示は、この小数に 100 をかけたものと考えて差し支えありません。

3. **aVDI（`Vessel density index adjusted by signal intensity`）**  
   上記の **血管密度の比率** に、上記 **1 の輝度の比** をかけ、さらに **100** をかけた指標です。  
   **読み方の例**: 血管の占め方は同じでも、MNV 内の信号が弱く平均輝度の比が下がると aVDI も下がります。逆に、信号が良好で比が高いと、aVDI は血管密度だけのときより大きくなりやすくなります。**画質低下で見かけ上の血管密度だけが下がったのか、血流信号が弱いのか**を切り分けるときに、`MNV mean gray intensity` や画像所見とあわせて見る、という使い方を想定しています。

4. **aMNV（`MNV Area adjusted by signal intensity`）**  
   **aVDI を用いて、血管面積（mm²）を補正した値**として CSV に書きます。具体的には、**血管面積 × (1 − aVDI÷100)** です（aVDI が大きいほど乗じる係数は小さくなります）。  
   旧マニュアルにあった「平均輝度×面積」のような **別の形の式**と字面が違っても、**本アプリが出力する CSV の数値はこの定義に従います**。他施設のデータや旧マクロの結果と数値を直接比較する場合は、定義の差に注意してください。

**論文・申請書に書くとき**は、少なくとも **使用したソフトウェア名（ARIAKE OCTA 等）、版またはビルド日、aVDI・aMNV をどの列の定義として報告したか** を本文または付表で明記してください。数値の再現には、**実際の CSV のヘッダと同じ列名**を引用するのが安全です。

### 6.1 補足 · 細動脈化（Arteriolarization）— Flet 版で強化された出力

スケルトン上の管径（距離変換）分布から **高歪度（high skew）** を推定し、細動脈化様の血管をセグメント化して定量化します（`src/ariake_octa/arteriolarization.py`、`src/core/skeleton_analysis.py` 等）。

**CSV 列名の例（ImageJ 互換）**

| 列名 | 説明 |
|------|------|
| Arteriolarization Segment Count | 高歪度セグメント数 |
| Arteriolarization Total Length (mm) | 該当スケルトン長の合計 |
| Arteriolarization Max Segment Length (mm) | 最大セグメント長 |
| Arteriolarization Density (/mm²) | ROI 面積あたり密度 |
| Arteriolarization Connectivity Index (mm/segment) | 接続性 |
| Local Diameter Variation (max CV%) | 局所径変動 |
| Dilated vessel (%) | 拡張（高歪度）血管の割合（パイプライン定義） |

**カラーコード（RGB）**

- **黄**: 正常血管（二値化血管に相当）  
- **赤**: 拡張血管（高歪度／細動脈化相当成分）  
- **グレー系**: 背景  

詳細は `src/ariake_octa/mnv/visualization_rgb.py` を参照してください。

### 6.2 MNV サブタイプ分類（マクロ版 §6.2）

以下はマクロ版の解釈ガイドの要約です。**Pathophysiology** として **Arteriolarized** 等が出力される場合があります（`src/core/pattern_classifier.py`）。

| パターン | Complexity / 分布の目安 | 特徴の一例 |
|----------|-------------------------|------------|
| Dead tree | 低複雑・高安定性 | 成熟・不活性寄り |
| Tree in bud | 中程度の複雑性 | 分岐発達中 |
| Seafan | 高複雑・偏心性 | 一方向への進展傾向 |
| Medusa | 非常に高複雑・中心性 | 全方向放射状 |
| Glomerular | 高複雑・均衡分布 | 糸球体様 |

**臨床応用の一般論**はマクロ版 §10.2 と同様ですが、**診断はソフトウェア出力のみで行わず**、画像所見および施設基準に従ってください。

スコアの**現行定義（PCA・パラメータ）**は次節 **§6.3** を参照してください。

**（参考）マクロ版の 7 成分 Complexity / 6 成分 Stability の整理** → [付録・Appendix C](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-c-network-complexity-score) · [Appendix D](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-d-caliber-uniformity-score)

### 6.3 Network Complexity / Caliber Uniformity（現行 Flet 版 · 正）

結果画面のタイル名と CSV 列名の対応は次のとおりです。

| UI（結果画面） | CSV 列名（ImageJ 互換） | 内部キー | 意味（高いほど） |
|----------------|-------------------------|----------|------------------|
| **Complexity** | Network Complexity Score | `complexity_score` | 血管網の構造的複雑性 |
| **Uniformity** | Caliber Uniformity Score | `stability_score` | 口径の均一性（旧称 Stability） |
| Maturity Index | Maturity Index | `maturity_index` | 口径均一 − 複雑性のバランス |

実装の正本: `src/core/pattern_metrics.py`（`calculate_complexity_pca` / `calculate_stability_score`）、呼出は `src/core/mnv_pipeline.py` のパターン分類。参照統計は `resources/reference_metrics/complexity_ref_*.json` および `stability_ref_*.json`（層別、2026-05-28 再構築）。

#### 6.3.1 層（size_class）の決め方

Image Scale (mm) と画像幅から参照 JSON を切り替えます（`mnv_pipeline` と同一ロジック）。

| 条件 | size_class | 参照ファイル接尾辞 |
|------|-------------|-------------------|
| スケール ≈ **3.0 mm** | `small_3mm` | `_small_3mm` |
| 画像幅 **> 800 px**、またはスケール **≥ 6.0 mm** | `large` | `_large` |
| それ以外 | `small` | `_small` |

他施設・他装置と比較するときは、**同じ size_class（同じスケール設定）同士**で比べてください。

#### 6.3.2 Network Complexity Score（0–100）

**何をもとにしているか（入力 4 特徴量）**

| 内部名 | 定義 |
|--------|------|
| `euler_total_inv` | −(中心 Euler + 周辺 Euler)。メッシュ状ほど大きくなりやすい |
| `loop_total` | 中心ループ数 + 周辺ループ数 |
| `junction_density` | (中心+周辺の分岐点数) / 総血管長 (mm) |
| `FD_global` | スケルトン全体のフラクタル次元 |

**計算の流れ**

1. 各特徴量を層別の μ / σ で **Z スコア化**（参照 JSON）。  
2. 層別の **PC1 / PC2 ローディング**で主成分生値を算出。  
3. PC1・PC2 を参照の `score_min`/`score_max`・`PC2_min`/`PC2_max` で **0–100 の線形スケール**（クリップ）。  
4. **Trunk Distribution** 生スコア（下表）を、`complexity_ref` の `trunk_scale_correction`（層別 min / median / max、median→50 の区分線形）で 0–100 に正規化。  
5. 最終合成（重みは **explained variance ratio**。JSON の `final_weights` 0.7/0.2/0.1 は Complexity では使わない）:

\[
\mathrm{Complexity}
= w_{\mathrm{PC1}}\cdot\mathrm{PC1}_{0\text{–}100}
+ w_{\mathrm{PC2}}\cdot\mathrm{PC2}_{0\text{–}100}
+ w_{\mathrm{Trunk}}\cdot\mathrm{Trunk}_{norm}
\]

\(w_{\mathrm{Trunk}}=\max(0,\,1-w_{\mathrm{PC1}}-w_{\mathrm{PC2}})\)。

**層別の最終合成ウェイト（EVR）**

| size_class | \(w_{\mathrm{PC1}}\) | \(w_{\mathrm{PC2}}\) | \(w_{\mathrm{Trunk}}\) | 参照 n |
|------------|----------------------|----------------------|------------------------|--------|
| small | 0.634 | 0.265 | ≈0.102 | 34 |
| large | 0.663 | 0.226 | ≈0.111 | 49 |
| small_3mm | 0.633 | 0.301 | ≈0.066 | 30 |

**Trunk Distribution 生スコアの内訳**（Complexity / Caliber Uniformity 共通）

| 成分 | 重み | 概要 |
|------|------|------|
| Centrality | 0.40 | \(100\times(1-\mathrm{trunk\_eccentricity})\) |
| Radiality | 0.30 | \(100\times\exp(-2\cdot\mathrm{angular\_CV})\) |
| Diameter Uniformity | 0.20 | 中心/周辺径比が 1.0–1.5 付近で高得点 |
| Central Density Bonus | 0.10 | 中心の太い血管割合に応じた加点 |

**解釈の目安（研究用・施設で検証すること）**: 高値ほど吻合・ループ・分岐が多く構造が複雑。マクロ版の「7 成分加重＋特殊補正（最低 80 点など）」は **現行パイプラインでは適用されません**。

#### 6.3.3 Caliber Uniformity Score（0–100）

UI では **Uniformity**、CSV では **Caliber Uniformity Score**。内部変数名は歴史的経緯で `stability_score` です。

**何をもとにしているか**

1. MNV ROI を病変中心から **放射状に 10 bin** に分割し、各 bin の平均血管径（μm、距離変換に基づく）を算出。  
2. その 10 点プロファイルから次の **4 指標**を計算:

| 内部名 | 意味 |
|--------|------|
| `stab_cv` | 10 bin 径の変動係数 (%) = (SD/mean)×100 |
| `stab_mean_adjacent_change` | 隣接 bin 間の相対変化率の平均 (%) |
| `stab_residual_cv` | 線形トレンドに対する残差の CV (%) |
| `stab_range_percent` | (max−min)/mean × 100 |

3. 層別 `stability_ref_*.json` で Z → PC1 / PC2。**PC1 は不安定性軸**のため、スコア化では **−PC1** を用いる。  
4. −PC1 と PC2 をそれぞれ区分線形（median→50）で 0–100 に写像。  
5. 最終合成（全 size_class で共通。JSON `final_weights`）:

\[
\mathrm{CaliberUniformity}
= 0.7\cdot(-\mathrm{PC1})_{0\text{–}100}
+ 0.2\cdot\mathrm{PC2}_{0\text{–}100}
+ 0.1\cdot\mathrm{Trunk}_{norm}
\]

Trunk 正規化は Complexity と同じく **`complexity_ref` の `trunk_scale_correction`** を使用します。

**特殊ケース**

| 条件 | 返り値 |
|------|--------|
| 径プロファイルが空 | 0 |
| 10 bin の SD = 0（完全一定） | **100** |
| 参照 JSON 欠落 | 旧 6 成分加重へフォールバック（通常の配布ビルドでは起きない） |

**結果画面の「Uniformity = 25.0」警告**: 値が厳密に 25.0 のとき再解析を勧める UI フラグです。スコア計算側が 25 をセンチネルとして代入する処理はありません（偶然 25.0 になる場合と、旧マクロ由来の運用慣習を含む）。

**解釈の目安**: 高値ほど中心〜周辺の口径が均一（成熟・不活性寄りに読まれることが多い）。低値は径のばらつき・急峻な動径変化。

#### 6.3.4 Maturity Index

\[
\mathrm{Maturity}
= \mathrm{clip}\bigl(50 + (\mathrm{CaliberUniformity} - \mathrm{NetworkComplexity})/2,\; 0,\; 100\bigr)
\]

口径が均一で複雑性が低いほど高くなりやすい、というバランス指標です。

#### 6.3.5 論文・施設間比較での記載例

- ソフトウェア: ARIAKE OCTA（Flet 版）、Complexity / Caliber Uniformity は **層別 PCA**（参照 JSON 再構築日 2026-05-28）。  
- 報告する列名: `Network Complexity Score` / `Caliber Uniformity Score` / `Maturity Index`。  
- 併記推奨: **Image Scale (mm)**、画像幅（px）、推定 size_class。  
- マクロ版や他施設の旧スコアと数値を直接比較しないこと。

---

## 7. 解析パラメータの理解

マクロ内定数の一覧・医学的閾値の目安は **付録 E** に抜粋しています。**実際の数値**は Python 実装の定数・設定ファイルを参照してください。

→ [付録・Appendix E](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-e-constants-and-thresholds-macro-section-7)

---

## 8. トラブルシューティング

| 現象 | 確認 |
|------|------|
| VD ペアが見つからない | サフィックス、`Side`、拡張子、ファイルが API から見えるパスか |
| MNV ファイルが認識されない | `_3` / 命名、MNV フォルダバッチの除外ルール（§2.2） |
| 解析失敗・初期化エラー | 画像が破損していないか、8-bit / 形式、ログ（`backend.log` 等） |
| 中心部ピクセル不足 | ROI サイズ、血管抽出結果 |

マクロ版のエラーメッセージ対応表（整理版）→ [付録・Appendix F](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-f-troubleshooting-macro-section-8)

ブラウザ（`FLET_USE_WEB=1`）では **OS のフォルダピッカーが使えない**場合があります。ネイティブ起動（`FLET_USE_WEB=0`）や手動パスを試してください（[USER_MANUAL.md](../USER_MANUAL.md)）。

---

## 9. 詳細アルゴリズム解説（マクロ版 §9 対応）

**ROI 自動修正**、**細動脈化**、**中心 vs 周辺**、**Box-Counting**、**Euler 数** の段落説明は付録 G を参照してください。実装の詳細はソースが正とします。

→ [付録・Appendix G](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-g-algorithms-summary-macro-section-9)

---

## 10. 臨床応用ガイド

→ [付録・Appendix H](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-h-clinical-notes-macro-section-10)

**本ソフトは医療機器ではなく研究用ツールである**という位置づけは変わりません。

---

## 11. 高度な使用方法

→ [付録・Appendix I](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-i-advanced-usage-macro-section-11)

---

## 12. 付録（単位・略語・参考値）

→ [付録・Appendix J](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-j-units-and-glossary-macro-section-12)

値の閾値は **施設データで検証**してください。

---

## 13. FAQ（抜粋・Flet 版向け補足）

マクロ版 FAQ の拡張版（抜粋・整理。別日実行、時点比較、ROI のコツ、異常値、他施設比較、カットオフ例、カスタマイズ段階など）→ [付録・Appendix K](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-k-faq-macro-section-13)

**Flet 版特有の補足**

- **VD と MNV を別日に実行できるか** — はい。出力先フォルダを分けることを推奨します。  
- **スキャンサイズが 6 mm でない場合** — **Image Scale (mm)** に実スキャン幅を入力してください。  
- **論文の Methods に書く文** — 「ImageJ マクロ」とだけ書かず、**ARIAKE OCTA Analysis（Flet/Python 実装、バージョン）**、**Git コミットまたはビルド ID**、**aVDI/aMNV の定義ソース**を明記してください。  
- **Q7（マクロ版）の記載例** — 本アプリでは **Flet + FastAPI + Python パイプライン**に置き換えて記述します。

---

## 14. サポートとアップデート

バグ報告時は **OS、アプリ版またはコミットハッシュ、再現手順、入力画像の仕様（サイズ・命名）、ログ**を添えてください。ImageJ マクロ版の報告テンプレートは **付録 L** を参照（Flet 版では Java/ImageJ の欄は不要）。

→ [付録・Appendix L](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md#appendix-l-support-and-disclaimer-macro-sections-14-15)

---

## 15. 文書情報

- **マクロ版**: Team Yanagi (2025)、V2。  
- **本書（Flet 版）**: マクロ版 V2 を基に、リポジトリの UI・パイプライン実装に合わせて改訂。  
- **免責**: 本ソフトウェアは現状有姿（AS IS）で提供されます。医療判断は医師の総合評価に基づいて行ってください。

### 15.1 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-07 | **§6.3** 新設: Network Complexity / Caliber Uniformity の現行定義（層別 PCA・入力特徴量・EVR／0.7·(−PC1)+0.2·PC2+0.1·Trunk・size_class・Trunk 正規化・Maturity・Uniformity=25.0 警告）。冒頭差分表・§3.2・文書情報を更新。操作マニュアル側の施設コード／Export Metadata と整合。 |
| 2026-08-07 | 付録 B.5／C／D を「現行 PCA」＋「マクロ版（歴史）」に再編するよう指示（詳細は付録の変更履歴）。 |
| （既往） | マクロ版 V2 構成を Flet＋FastAPI 実装に合わせて移植（起動差分、VD サフィックス、MNV バッチ QC、aVDI／aMNV、細動脈化 CSV 等）。 |

---

*詳細な操作手順: [USER_MANUAL.md](../USER_MANUAL.md) · 概要とインストール: [README.md](../README.md) · 開発者向け: [DEVELOPER.md](../DEVELOPER.md) · マクロ版整理付録: [ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md](ARIAKE_OCTA_詳細ユーザーマニュアル_V2_付録_マクロ本文.md) · Complexity/Uniformity 正本: 本書 §6.3*
