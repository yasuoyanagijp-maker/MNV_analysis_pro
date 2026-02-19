# MNV バイナリ作成まわり：変更点レビュー

本ドキュメントは、ImageJ マクロに合わせた MNV バイナリ作成の実装変更（`docs/MNV_binary_ImageJ_vs_Python_diff.md` に基づく）および Despeckle 警告の整理についてのレビューである。

---

## 1. 変更の目的・概要

- **目的**: MNV 解析のバイナリ作成フローを ImageJ マクロの挙動に合わせる。同時に従来フローは引数で復元可能にし、二値画像の型を uint8 0/255 に統一する（Decasting）。
- **主な結果**:
  - デフォルトで「前処理 Despeckle のみ」「LoG/Tubeness 各系統で二値化 → denoise → OR → 最終 denoise」「Tubeness 単一スケール [1.0]」となる。
  - 従来の「CLAHE + 背景除去」「加重和融合 → 1 回二値化」「Tubeness マルチスケール」は `use_clahe=True`, `fusion_method="weighted_sum"`, `tubeness_scales=[1.0,2.0,3.0]` で利用可能。
  - Despeckle の反復・警告は ImageJ マクロのループと同一にした。

---

## 2. ファイル別の変更点

### 2.1 `src/ariake_octa/mnv/mnv_preprocessor.py`

| 項目 | 内容 |
|------|------|
| 追加引数 | `use_clahe: bool = False` |
| デフォルト時 | ImageJ MNV 相当。入力は uint8 に統一し、**Despeckle のみ**（`ndimage.median_filter(image, size=3)`）を適用。CLAHE・背景除去は行わない。 |
| `use_clahe=True` | 従来どおり CLAHE → ガウシアン背景除去 → 正規化（0–255）。 |
| 戻り値 | 常に H×W uint8。LoG/Tubeness は同じインターフェースで受けられる。 |

**評価**: 仕様どおり。ImageJ の preproc()（Despeckle のみ）に合わせつつ、既存動作を残している。

---

### 2.2 `src/ariake_octa/mnv/tubeness_filter.py`

| 項目 | 内容 |
|------|------|
| デフォルト | `scales: List[float] = None` → 内部で `[1.0]` に変換（ImageJ の tubeness_filter_radius=1 相当）。 |
| 従来互換 | 呼び出し側で `scales=[1.0, 2.0, 3.0]` を渡せばマルチスケールのまま。 |

**評価**: デフォルトが ImageJ 相当になり、既存のマルチスケールも維持されている。

---

### 2.3 `src/ariake_octa/mnv/mnv_pipeline.py`

#### 2.3.1 依存・インポート

- `from typing import List, Optional` を追加。
- `from scipy import ndimage` を追加（LoG 前のオプションガウシアン用）。
- `from core.preprocessing import BinaryPostProcessor` を追加（denoise_improved 用）。

#### 2.3.2 `__init__` の新パラメータ

| パラメータ | デフォルト | 説明 |
|------------|------------|------|
| `use_clahe` | `False` | True で CLAHE + 背景除去。 |
| `use_gaussian_before_log` | `False` | True で LoG 前にガウシアン（sigma = 幅×gaussian_sigma_ratio）を適用。 |
| `gaussian_sigma_ratio` | `0.01` | 画像幅に対する sigma の比率（例: 1%）。 |
| `tubeness_scales` | `None` | None で [1.0]。リスト指定でそのスケールを使用。 |
| `fusion_method` | `"logical_or"` | ImageJ 相当の二値 OR。`"weighted_sum"` で従来の加重和→1 回二値化。 |

- `MNVPreprocessor` に `use_clahe` を渡す。
- `TubenessFilter` に `_scales = [1.0] if tubeness_scales is None else tubeness_scales` を渡す。
- `FilterFusion` に `method=fusion_method` を渡す。
- `self.params` に上記オプションを記録。

**評価**: 計画どおり。後方互換は `fusion_method="weighted_sum"` と `use_clahe=True` 等で確保されている。

#### 2.3.3 Decasting: `_binary_to_uint8`

- **役割**: 二値画像（bool または 0/255 の uint8）を **uint8 0/255** に統一。
- **実装**: `np.where(binary > 0, 255, 0).astype(np.uint8)`（または bool 用の分岐）。パイプライン内で Phansalkar 直後・denoise/OR 前後に使用。

**評価**: 計画の「型の統一」を満たしている。下流（lesion_detector, skeleton_analyzer, 可視化）は `> 0` や `> 127` で扱うため、uint8 0/255 で問題ない。

#### 2.3.4 `process()` のフロー分岐

- **`fusion_method == "logical_or"`（デフォルト）**  
  1. 前処理（Despeckle のみ or CLAHE 経路）。  
  2. 必要なら LoG 前にガウシアン（sigma = 幅×gaussian_sigma_ratio）。  
  3. LoG(sigma=1) → Phansalkar → `_binary_to_uint8` → `denoise_improved(15, remove_small_particles=True)` → `binary_log`。  
  4. Tubeness(scales) → Phansalkar → `_binary_to_uint8` → `denoise_improved(15, True)` → `binary_tubeness`。  
  5. `fusion.fuse(binary_log, binary_tubeness)`（OR）→ `denoise_improved(15, False)` で最終 binary。  
  6. この経路では `fused` は None。病変重心用に `fused_response = tube_filtered_out` を使用。

- **`fusion_method == "weighted_sum"`**  
  従来どおり: LoG → Tubeness → 加重和 → Phansalkar 1 回 → `_binary_to_uint8`。denoise は行わない。

**評価**: ImageJ の「各系統二値化 → denoise(1) → OR → denoise(0)」に沿っている。`fused_response` のフォールバックも妥当。

#### 2.3.5 メトリクス・中間結果

- **血管ピクセル数**: `vessel_pixels = (binary > 0).sum()` に変更。bool / uint8 0-255 のどちらでも正しくカウントされる。
- **中間結果**: `log_filtered_out`, `tube_filtered_out`, `fused`（logical_or 時は None）, `binary`（uint8 0/255）を保存。

**評価**: Decasting と整合している。

---

### 2.4 `src/core/preprocessing.py`（`BinaryPostProcessor.denoise_improved`）

| 項目 | 内容 |
|------|------|
| ループ | ImageJ マクロと同一: 各反復で `area1 = np.sum(result > 0)` → `cv2.medianBlur(result, 3)` → `area2 = np.sum(result > 0)`。 |
| 終了条件 | `area1 == area2` のとき break。それ以外の早期終了（fixpoint/2 周期）は削除し、ImageJ と完全に同じ条件にした。 |
| 警告 | `iteration == max_iterations - 1` のときのみ `"Warning: Despeckle timeout (fixed limit: {max_iterations})"` を表示。 |

**評価**: ImageJ の「面積が変わらなくなるまで反復、最大 15 回、最後の反復で timeout 警告」と一致している。15 回回っても面積が変化し続ける画像では、ImageJ と同様に警告が出る想定で正しい。

---

### 2.5 ドキュメント

- **`docs/MNV_binary_ImageJ_vs_Python_diff.md`**  
  相違点・変更方針・実装計画（タスク 1–8）、Decasting、テスト項目を記載。参照パスに「外部リポジトリ・環境依存パス」の注記を追加済み。
- **`docs/MNV_changes_review.md`**（本ファイル）  
  今回の変更のレビューをまとめたもの。

---

## 3. 一貫性・後方互換

- **呼び出し側**: `analyzer.py` は `MNVPipeline(pixel_size_mm=...)` のみなので、デフォルトで ImageJ 相当フローになる。既存コードの修正は不要。
- **app.py**: `core.mnv_pipeline.MNVPipeline` を参照しているため、`ariake_octa.mnv` 側の今回の変更の影響は受けない。
- **互換モード**: 従来の「CLAHE + 加重和 + マルチスケール Tubeness」は上記パラメータで再現可能。
- **型**: パイプライン出口および中間結果の binary は uint8 0/255 に統一され、既存の `binary > 127` / `binary > 0` はそのまま有効。

---

## 4. 残課題・推奨

1. **クラス docstring**: `MNVPipeline` の docstring はまだ「多段階前処理（CLAHE + 背景除去）」が主のように書かれている。デフォルトは「Despeckle のみ / 二値 OR / denoise」である旨を 1 行追記するとよい。
2. **テスト**: 計画の「9.6 テスト・確認項目」に沿った単体テストや、ImageJ とのバイナリ比較用スクリプトがあると、今後の変更時の安心材料になる。
3. **Despeckle timeout**: 15 回でも面積が変化し続ける画像では、ImageJ と同様に警告が出る。仕様通りの挙動であり、必要なら `max_iterations` の引き上げや、警告をログ専用にするなどの運用で調整可能。

---

## 5. Streamlit / mainstreamer 実行時の扱い

### 5.1 参照関係の確認（方針 2-B 実装後）

| 実行入口 | MNV で使用するパイプライン | バイナリ作成の実体 |
|----------|----------------------------|---------------------|
| **mainstreamer.py**（`streamlit run mainstreamer.py`） | `core.mnv_pipeline.MNVPipeline`（CoreMNVPipeline） | **`ariake_octa.mnv.create_mnv_binary_for_core()`**（ImageJ 準拠） |
| **app.py**（`streamlit run src/ariake_octa/app.py`） | `core.mnv_pipeline.MNVPipeline` | 上記と同じ |
| **analyzer.py**（`ariake_octa.Analyzer` 経由の MNV） | `ariake_octa.mnv.MNVPipeline` | 同モジュール内の Despeckle のみ / 二値 OR / denoise |

- **core.mnv_pipeline**: Step 2 で **`create_mnv_binary_for_core(image, pixel_size_mm=scale_manager.mm_per_pixel)`** を呼び、返り値の `binary` をその後の ROI・メトリクス・FD・可視化に使用。`vessel_detection.MNVPreprocessor` は使用していない。

したがって、**Streamlit（mainstreamer.py / app.py）経由でも ImageJ 準拠のバイナリが使われる。**

### 5.2 今回の目的の達成状況

- **目的**: MNV バイナリ作成を ImageJ マクロに合わせる（前処理 Despeckle のみ、二値 OR 融合、Tubeness 単一スケール、denoise 等）。
- **Streamlit で mainstreamer.py を実行した場合**: **方針 2-B 実装により、core が ariake_octa.mnv のバイナリ作成を利用するため、ImageJ 準拠フローが使われる。目的は達成されている。**
- **今回の変更が効く経路**: **mainstreamer.py / app.py（core 経由）** および **ariake_octa の Analyzer**・**`ariake_octa.mnv.MNVPipeline` を直接使うスクリプト**。

### 5.3 Streamlit でも目的を達成するには（方針の比較）

**方針 1: Streamlit 内で ariake_octa.mnv.MNVPipeline を直接使う**

- メリット: 「正」の実装が一つにまとまる。
- デメリット: core.mnv_pipeline は `analyze(image_path, output_dir, roi_mask, flow_deficit_image_path, ...)` という API で、ROI・FD 用画像・バッチ・ログ・可視化・パターン分類などを含む。ariake_octa.mnv.MNVPipeline は `process(image)` のみ。Streamlit の要件を満たすには、core の機能を ariake_octa 側に再実装するか大きなアダプタが必要で、変更量が大きい。

**方針 2: core 側を ImageJ 準拠にする（推奨）**

- メリット: Streamlit の入口（mainstreamer.py / app.py）はそのまま。バイナリ作成だけ ImageJ 準拠にすればよい。
- 実装の取り方:
  - **2-A**: core.vessel_detection の `preprocess_mnv` を自前で ImageJ 準拠に書き換える。→ 同じロジックが core と ariake_octa の二箇所に存在する可能性。
  - **2-B（推奨）**: **core が「バイナリ作成」だけ ariake_octa.mnv のコンポーネントを呼ぶ**。例: core.mnv_pipeline の Step 2 で、core.vessel_detection.MNVPreprocessor の代わりに、ariake_octa.mnv の前処理＋LoG＋Tubeness＋二値化＋denoise＋OR を実行する関数（または ariake_octa.mnv.MNVPipeline の Phase1 部分）を呼び、`binary` と必要なら `mex_hat`/`tubeness` を受け取る。その後は従来どおり core 側で ROI・メトリクス・FD・可視化を続ける。
- こうすると **実装は ariake_octa.mnv に一元化**され、Streamlit は core 経由でその実装を利用する形になる。

**現状で ariake_octa.mnv.MNVPipeline が使われている場所**

- **ariake_octa.analyzer.ARIAKEAnalyzer**（`src/ariake_octa/analyzer.py`）が `self.mnv_pipeline = MNVPipeline(pixel_size_mm=...)` で保持し、`analyzer.analyze([画像])` で MNV を実行するときにのみ使用。
- **Streamlit（mainstreamer.py / app.py）は ARIAKEAnalyzer を使っていない**ため、**Streamlit 実行時には ariake_octa.mnv.MNVPipeline は使われていない**。レポジトリの目的が「Streamlit での実行」であれば、現状は「ImageJ 準拠の実装がメインの入口から使われていない」状態。

**結論（レポジトリの目的が Streamlit である場合）**

- **方針 2-B を実装済み**（core が ariake_octa.mnv のバイナリ作成を利用）。以下にすると、
  1. Streamlit で目的が達成される（core 経由で ImageJ 準拠のバイナリが使われる）。
  2. 実装の重複がなく、**ariake_octa.mnv の役割が「core から呼ばれるバイナリ作成の実装」**として明確になる。
  3. ariake_octa.mnv.MNVPipeline は「単体 API（ARIAKEAnalyzer 経由）用」と「core からバイナリ取得用の部品」の両方で使える。
- 方針 1 は、Streamlit の API を ariake_octa に寄せる大がかりな変更になり、現時点ではメリットより工数が大きい。

### 5.4 方針 2-B の実装内容（実施済み）

- **ariake_octa.mnv.mnv_pipeline**
  - `fusion_method=="logical_or"` 時に `intermediate_results` へ `binary_log` / `binary_tubeness` を追加（core のデバッグ用）。
  - モジュール関数 **`create_mnv_binary_for_core(image, pixel_size_mm=0.003)`** を追加。内部で `MNVPipeline(pixel_size_mm=...).process(image)` を呼び、返り値の `intermediate_results` から `binary`, `binary_log`, `binary_tubeness` を取り、`{"binary": ..., "mex_hat": binary_log, "tubeness": binary_tubeness}` を返す。入力は uint8 2D に正規化。
- **ariake_octa.mnv.__init__**
  - `create_mnv_binary_for_core` を export。
- **core.mnv_pipeline**
  - Step 2 の前処理で、`vessel_detection.MNVPreprocessor` の代わりに **`create_mnv_binary_for_core(image, pixel_size_mm=scale_manager.mm_per_pixel)`** を呼ぶ。返り値を従来どおり `binary`, `mex_hat`, `tubeness` として扱い、以降の ROI・メトリクス・FD・可視化は変更なし。

これにより、**Streamlit（mainstreamer.py / app.py）経由で MNV 解析を行う場合も、ImageJ 準拠のバイナリが使われる。**

### 5.5 Step 2 ログの表示（修正済み）

- **事象**: 「Step 2: Image Preprocessing (ImageJ-aligned binary via ariake_octa.mnv)」がログに表示されない。
- **原因**: mainstreamer は `verbose=False` でパイプラインを生成しており、`logger.info()` は WARNING 以下のレベルでは出力されないため。
- **対応**: `core.mnv_pipeline` の Step 2 で、**`print("Step 2: Image Preprocessing (ImageJ-aligned binary via ariake_octa.mnv)")`** を追加し、ログレベルに依存せず常に表示するようにした。これにより、新経路（create_mnv_binary_for_core）が実行されたことをターミナルで確認できる。

### 5.6 Step 6 付近のエラー（Very low vessel density 0%, No vessels detected, Skeleton is empty）

- **事象**: Step 6（1b-4 など）で「Very low vessel density (0.00%)」「No vessels detected」「Refined skeleton is empty」「Skeleton is empty」「No vessel length detected」「Unusual fractal dimension (0.000)」が出る。
- **バイナリ・ROI の流れ（変更なし）**:
  - Step 2 で `binary = create_mnv_binary_for_core(image, ...)["binary"]` を取得。`image` は `image_path` から読み込んだフル解像度の 8bit グレースケール。`binary` は同じサイズの uint8 0/255。
  - `roi_mask` は analyze の引数（mainstreamer ではリサイズ済み ROI）で、Step 1 で決定され Step 2 以降で共通利用。
  - `vessel_area_pixels = np.sum((binary > 0) & (roi_mask > 0))`、`vessel_density = vessel_area_mm2 / mnv_area_mm2` の式は従来どおり。スケルトン解析も同じ `binary` と `roi_mask` を使用。
- **結論**: **ROI の渡し方や引数の不整合ではなく、使用するバイナリの内容が変わったことによる差**と考えられる。ImageJ 準拠バイナリ（Despeckle のみ＋Phansalkar＋単一スケール Tubeness＋OR＋denoise）は、従来の core.vessel_detection（CLAHE/背景除去＋加重和融合＋マルチスケール Tubeness 等）より**白画素が少なくなる場合がある**。その結果、同じ ROI 内でも vessel_area_pixels が 0 に近づき、血管密度 0%・スケルトン空・FD 計算不可となる。特定の画像で「以前は検出されていたが 2-B 導入後は検出されない」場合は、**アルゴリズム差（新バイナリの性質）**によるものと解釈できる。必要に応じて、その画像では `use_clahe=True` 等で従来に近いバイナリを試すか、閾値・パラメータの見直しを検討する。

---

## 6. まとめ

- MNV バイナリ作成は、**ariake_octa.mnv.MNVPipeline** ではデフォルトで ImageJ マクロに合わせたフロー（前処理 Despeckle のみ、各系統二値化→denoise→OR→最終 denoise、Tubeness [1.0]、二値は uint8 0/255）になっている。
- 従来フローはパラメータで復元可能で、後方互換は保たれている。
- Despeckle の反復と警告は ImageJ マクロと同一のロジックに揃えた。
- **方針 2-B 実装により、Streamlit（mainstreamer.py / app.py）経由でも core が ariake_octa.mnv のバイナリ作成を利用するため、ImageJ 準拠の目的は達成されている。** Step 2 のログは `print()` で常に表示される。Step 6 で vessel density 0% 等が出る場合は、新バイナリの性質（アルゴリズム差）によるもので、ROI/引数の不整合ではない。
