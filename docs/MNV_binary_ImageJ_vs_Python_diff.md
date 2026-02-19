# MNV バイナリ作成：ImageJ マクロ vs Python 実装の相違点

参照ドキュメント: [ARIAKE_OCTA_MNV_binary_process_CLAHE_binarization.md](/Users/yy/git/ARIAKE_MNV_fresh/docs/ARIAKE_OCTA_MNV_binary_process_CLAHE_binarization.md)（外部リポジトリ・環境依存パス）  
Python 実装: `src/ariake_octa/mnv/`（mnv_pipeline, mnv_preprocessor, log_filter, tubeness_filter, filter_fusion, phansalkar_filter）

---

## 1. 全体フローの違い

| 項目 | ImageJ マクロ（MNV） | Python 実装 |
|------|----------------------|-------------|
| 前処理 | **CLAHE なし**。preproc() = Despeckle + setMinAndMax(0,177) のみ | **CLAHE あり**（blocksize=127, clip_limit=3）+ ガウシアン背景除去（sigma=5）+ 正規化 |
| 特徴抽出 | 2系統を**別々に**処理し、それぞれ**二値化**してから OR | LoG と Tubeness を**グレースケールのまま**融合し、**1回だけ二値化** |
| 最終バイナリ | binary.tif = **OR(mex_hat 二値, tubeness 二値)** | binary = **Phansalkar(融合画像)** |
| 後処理 | denoiseImproved(1) を各系統に、denoiseImproved(0) を最終に適用 | ノイズ除去・小粒子除去の**明示的ステップなし** |

これらを、ImageJマクロの実装に合わせ、CLAHE処理をデフォルトではスキップする設定に(後ほど必要に応じて機能をONにできるように引数などを設定する)

---

## 2. 前処理の相違

| 項目 | ImageJ（MNV） | Python |
|------|----------------|--------|
| CLAHE | **使用しない**（MNV バイナリ作成では呼ばれない） | **使用する**。`exposure.equalize_adapthist`（kernel_size=127, clip_limit=3/100） |
| Despeckle | preproc() で **Despeckle** を実行 | **未実装**（Despeckle に相当する処理なし） |
| 表示レンジ | setMinAndMax(70,255) の後 setMinAndMax(0,177)（表示のみ） | なし（前処理後は 0–255 に正規化） |
| 背景除去 | なし（preproc のみ） | **ガウシアンブラー**（sigma=5）で背景推定し、元画像から減算して正規化 |



**結論**: Python は VD 解析寄りの「CLAHE + 背景除去」を使っており、ImageJ の MNV フロー（CLAHE なし・Despeckle のみ）とは異なる。

前処理は、現在pythonで使用されているものをスキップする設定にする(後ほど必要に応じて機能をONにできるように引数などを設定する)


---

## 3. Mexican Hat / LoG 系統の相違

| 項目 | ImageJ（Mexican Hat） | Python（LoG） |
|------|------------------------|---------------|
| 入力 | mex_hat.tif（元画像コピー）→ preproc() のみ | **前処理済み画像**（CLAHE + 背景除去後） |
| オプション ガウシアン | checkbox_gaussian 時のみ。**sigma = width×gaussian_sigma/100**（例: gaussian_sigma=1 → 画像幅の 1%） | **なし**。LoG 内部のガウシアンは sigma=1 のみ（FeatureJ Laplacian 相当） |
| フィルタ | FeatureJ Laplacian、**sigma=1**（固定） | LoG（Laplacian of Gaussian）、**sigma=1**（同等） |
| 二値化 | **Make Binary**（閾値未設定 → ImageJ の自動閾値 Default 法） | この段階では二値化しない。**融合後に Phansalkar** |
| 後処理 | denoiseImproved(1)（Despeckle 反復 + 小粒子除去） | なし |

この段階で二値化を Phansalkar 法で行うように変更する（Python 側では ImageJ の Make Binary の代わりに Phansalkar で統一）。

---

## 4. Tubeness 系統の相違

| 項目 | ImageJ（Tubeness） | Python（Tubeness） |
|------|--------------------|---------------------|
| 入力 | tube.tif（元画像コピー） | **前処理済み画像**（CLAHE + 背景除去後） |
| スケール | **単一 sigma=1**（tubeness_filter_radius=1） | **マルチスケール sigma=[1, 2, 3]**（最大応答を採用） |
| 二値化 | **Auto Local Threshold (Sauvola)**。radius=15, parameter_1=0, parameter_2=0（プラグインのデフォルト k, R） | この段階では二値化しない。**融合後に Phansalkar** |
| 後処理 | denoiseImproved(1) | なし |

Tubeness filterをデフォルトでは単一 sigma =1にして(後ほど必要に応じて機能をONにできるように引数などを設定する)imageJに揃える。

---

## 5. 融合と最終二値化の相違

| 項目 | ImageJ | Python |
|------|--------|--------|
| 融合のタイミング | **二値画像同士**を OR | **グレースケール同士**を加重和（weighted_sum, 0.5:0.5） |
| 融合方法 | imageCalculator("OR create", mex_hat.tif, tubeness.tif) | fused = 0.5×LoG + 0.5×Tubeness（clip 0–255） |
| 最終二値化 | すでに OR で二値なので、**追加の閾値処理はなし**。続けて denoiseImproved(0) | **Phansalkar** を融合画像に 1 回適用（window_radius=15, k=0.25, r=0.5） |
| アルゴリズム | Mexican Hat: 自動閾値（Default）。Tubeness: **Sauvola** radius=15 | 融合画像に **Phansalkar**（式は Sauvola と同一: mean*(1+k*((std/r)-1))） |

**注意**: ImageJ の Tubeness 系統は Sauvola、Python は Phansalkar だが、閾値式は同じ。ImageJ は k/R=0 でプラグインのデフォルトに依存し、Python は k=0.25, r=0.5 を明示指定。

融合はimageJの方法に合わせる。

---

## 6. 二値化パラメータの対応

| パラメータ | ImageJ（MNV） | Python |
|------------|----------------|--------|
| Mexican Hat / LoG の閾値 | Make Binary（自動閾値 Default） | 使用しない（融合後に Phansalkar のみ） |
| 局所閾値の radius | Sauvola **radius=15**（固定） | Phansalkar **window_radius=15**（固定） |
| k | Sauvola parameter_1=**0**（デフォルト使用） | Phansalkar **k=0.25**（明示） |
| R | Sauvola parameter_2=**0**（デフォルト使用） | Phansalkar **r=0.5**（明示、uint8 の動的範囲に相当） |

---

## 7. 後処理（ノイズ除去）の相違

| 項目 | ImageJ | Python |
|------|--------|--------|
| denoiseImproved(1) | 各系統（mex_hat, tubeness）の二値画像に適用。Despeckle 反復 + **小粒子除去**（平均面積未満を黒で塗りつぶし） | **未実装** |
| denoiseImproved(0) | 最終 binary.tif に適用。Despeckle 反復のみ（小粒子除去なし） | **未実装** |

**再調査結果**: `src/core/preprocessing.py` に `BinaryPostProcessor` が存在し、`denoise_improved(binary_img, max_iterations, remove_small_particles)` および `despeckle`・`remove_small_particles_improved` が実装済み。ImageJ の denoiseImproved(0)/(1) に相当。MNV パイプライン変更時にこれを利用する。

---

## 8. まとめ（相違点一覧）

1. **前処理**: ImageJ は MNV で CLAHE を使わず Despeckle + setMinAndMax のみ。Python は CLAHE + 背景除去 + 正規化を使用。
2. **Mexican Hat 前のガウシアン**: ImageJ はオプションで sigma=画像幅/100。Python はなし。
3. **Tubeness スケール**: ImageJ は sigma=1 のみ。Python は [1, 2, 3] のマルチスケール。
4. **融合**: ImageJ は「二値 OR」。Python は「グレースケールの加重和」。
5. **二値化**: ImageJ は Mexican Hat=Make Binary（自動閾値）、Tubeness=Sauvola(radius=15) の 2 回。Python は融合画像に Phansalkar(radius=15) の 1 回。
6. **ノイズ除去**: ImageJ は denoiseImproved(1)/(0) あり。Python は現状デフォルトでは Despeckle・小粒子除去の明示ステップなし（本計画実施後は core の denoise_improved を利用）。
7. **パラメータ**: Python の Phansalkar は k=0.25, r=0.5 を固定。ImageJ の Sauvola は k/R=0 でプラグインのデフォルトに依存。

ImageJ マクロに合わせる場合は、上記の前処理（CLAHE 廃止・Despeckle 導入）、融合方法（二値 OR）、Tubeness 単一スケール、および denoiseImproved の再現を検討する必要がある。

---

## 9. Python 側変更の実装計画

変更方針（本文中の記載）に基づく実装タスクと手順。

### 9.1 前提・依存

- **denoise 利用**: `src/core/preprocessing.py` の `BinaryPostProcessor.denoise_improved` を利用する。`ariake_octa` から `core` を import する形でよい（既存の `src/core/mnv_pipeline.py` が ariake_octa を参照しているため、逆方向の依存は許容される想定）。別方針で ariake_octa 内に薄いラッパーを置く場合は、そのラッパーから `BinaryPostProcessor` を呼ぶ。
- **後方互換**: 「必要に応じて ON にできる」ため、既存挙動（CLAHE あり・加重和融合・マルチスケール Tubeness）は **引数で復元可能** にしておく。

---

### 9.2 タスク一覧

| # | タスク | 対象ファイル | 概要 |
|---|--------|--------------|------|
| 1 | 前処理のモード切替 | `mnv_preprocessor.py` | CLAHE/背景除去をスキップするモードを追加。Despeckle を追加。 |
| 2 | LoG 前のオプションガウシアン | `mnv_pipeline.py` | オプションで sigma=幅/100 のガウシアンを LoG の前に適用（process() 内で実施）。 |
| 3 | Tubeness のスケール切替 | `tubeness_filter.py` / `mnv_pipeline.py` | デフォルトを単一スケール [1.0] に。マルチスケールは引数で指定可能に。 |
| 4 | パイプラインの二値化フロー変更 | `mnv_pipeline.py` | LoG 系統・Tubeness 系統を「それぞれ二値化 → OR → 最終 denoise」に変更。 |
| 5 | 融合を二値 OR に変更 | `mnv_pipeline.py` + `filter_fusion.py` | 融合を「二値 OR」にし、最終は OR 結果に denoiseImproved(0) のみ適用。 |
| 6 | denoise の組み込み | `mnv_pipeline.py` | 各系統に denoise_improved(1)、最終に denoise_improved(0) を適用。 |
| 7 | 呼び出し側の引数 | `analyzer.py` / `app.py` 等 | MNVPipeline に渡すオプション（use_clahe, tubeness_scales 等）を必要に応じて追加。 |
| 8 | **Decasting（型の統一）** | `mnv_pipeline.py` | 二値画像をパイプライン内で uint8 0/255 に統一。Phansalkar 直後の bool→uint8 変換と、denoise/OR への渡し方を明示。 |

---

### 9.3 詳細手順

#### タスク 1: 前処理のモード切替（`mnv_preprocessor.py`）

- **追加する引数**
  - `use_clahe: bool = False`  
    - `False`（デフォルト）: ImageJ 相当。CLAHE と背景除去を行わない。
    - `True`: 従来どおり CLAHE + 背景除去 + 正規化。
- **ImageJ モード時（use_clahe=False）の処理**
  - 入力画像を uint8 に統一。
  - **Despeckle** を 1 回適用（3×3 メディアンフィルタで ImageJ Despeckle 相当。既存の `BinaryPostProcessor.despeckle` は二値用のため、グレースケール用は `cv2.medianBlur(image, 3)` または `ndimage.median_filter` で実装）。
  - setMinAndMax(0,177) は表示用のため、処理パイプライン上は省略してよい（必要なら `np.clip(img, 0, 177)` を 0–255 に正規化する程度で対応可能）。
- **戻り値**
  - いずれのモードも `(H×W uint8)` を返し、以降の LoG/Tubeness が同じインターフェースで受けられるようにする。

#### タスク 2: LoG 前のオプションガウシアン

- **追加する引数（パイプライン側）**
  - `use_gaussian_before_log: bool = False`
  - `gaussian_sigma_ratio: float = 0.01`（画像幅 × この値が sigma。ImageJ の 1% なら 0.01）
- **処理**
  - `use_gaussian_before_log` が True のとき、前処理済み画像に対し `sigma = max(1, int(width * gaussian_sigma_ratio))` でガウシアンブラーをかけてから LoG に入力する。
- 実装場所は **`mnv_pipeline.py`** の `process()` 内でよい（LoGFilter の前に 1 段挟む）。LoGFilter 自体は sigma=1 のまま変更不要。

#### タスク 3: Tubeness のスケール切替

- **TubenessFilter**
  - 既存の `scales: List[float] = [1.0, 2.0, 3.0]` を、**デフォルトを `[1.0]` に変更**（ImageJ 相当）。
  - 呼び出し元で `scales=[1.0, 2.0, 3.0]` を渡せば従来のマルチスケールに戻る。
- **MNVPipeline**
  - `__init__` で `tubeness_scales: Optional[List[float]] = None` を受け取り、`None` のとき `[1.0]`、指定時はそのリストを TubenessFilter に渡す。
  - 既存互換のため `tubeness_scales=[1.0, 2.0, 3.0]` を指定可能にしておく。

#### タスク 4: パイプラインの二値化フロー変更（`mnv_pipeline.py`）

- **現状**: 前処理 → LoG → Tubeness → 融合(加重和) → Phansalkar 1 回 → binary。
- **変更後（ImageJ 準拠・デフォルト）**:
  1. 前処理（use_clahe=False なら Despeckle のみ相当）。
  2. （オプション）ガウシアン → LoG(sigma=1) → **Phansalkar** → `binary_log` → **denoise_improved(remove_small_particles=True)**。
  3. Tubeness(scales=[1.0]) → **Phansalkar** → `binary_tubeness` → **denoise_improved(remove_small_particles=True)**。
  4. **binary = binary_log | binary_tubeness**（論理和、uint8 で 0/255 に正規化）。
  5. **denoise_improved(binary, remove_small_particles=False)** で最終 binary。
- **二値化**: 変更方針どおり、LoG 系統・Tubeness 系統ともに **Phansalkar**（window_radius=15, k=0.25, r=0.5）を使用。ImageJ の Make Binary / Sauvola の違いは、Python では両系統とも Phansalkar に統一してよい。
- **互換モード**: `fusion_method="weighted_sum"` のときは従来フロー（LoG と Tubeness をグレースケールで加重和 → 融合画像に Phansalkar 1 回）にし、既存動作を残す。前処理の CLAHE 有無は独立に指定可能。

#### タスク 5: 融合を二値 OR に変更

- **FilterFusion**: 既存の `method="logical_or"` と `_logical_or()` で、二値画像（0/255）の OR は実装済み。`method` はコンストラクタで指定するため、パイプラインでは「二値 OR フロー」用に `FilterFusion(method="logical_or")` をインスタンス化するか、`fusion_method` に応じてインスタンスを切り替える。
- **MNVPipeline**
  - デフォルトで「二値 OR フロー」を使うようにし、`binary_log` と `binary_tubeness` を 0/255 の uint8 にしたうえで、`method="logical_or"` の fusion インスタンスで `fusion.fuse(binary_log_uint8, binary_tubeness_uint8)` を実行。
  - 互換モード時のみ、従来どおり `method="weighted_sum"` の fusion でグレースケールの LoG/Tubeness を融合し、その 1 枚に Phansalkar をかける。

#### タスク 6: denoise の組み込み

- **利用する API**: `from core.preprocessing import BinaryPostProcessor` の `BinaryPostProcessor.denoise_improved(binary_img, max_iterations=15, remove_small_particles=...)`。
- **適用箇所**
  - `binary_log` に対して: `denoise_improved(binary_log, max_iterations=15, remove_small_particles=True)`。入力は 0/255 の uint8 に変換して渡す（bool の場合は `(img.astype(np.uint8)) * 255` など）。
  - `binary_tubeness` に対して: 同様に `remove_small_particles=True`。
  - OR で得た最終 binary に対して: `denoise_improved(binary, max_iterations=15, remove_small_particles=False)`（ImageJ の denoiseImproved(0) 相当）。
- 反復回数 15 は ImageJ の MAX_DESPECKLE_ITERATIONS に合わせる。

#### タスク 7: 呼び出し側の引数

- **MNVPipeline.__init__** に追加するパラメータ案:
  - `use_clahe: bool = False`
  - `use_gaussian_before_log: bool = False`
  - `tubeness_scales: Optional[List[float]] = None`（None なら [1.0]）
  - `fusion_method: str = "logical_or"`（`"weighted_sum"` で従来フロー）
- **process(image)** のシグネチャはそのままでよい。オプションはすべてコンストラクタで指定。
- **analyzer.py / app.py**: MNVPipeline を生成する箇所で、必要に応じて `use_clahe=True` や `tubeness_scales=[1.0, 2.0, 3.0]` を渡せるようにする。デフォルトのままなら ImageJ 準拠フローになる。

---

### 9.4 実装順序の推奨

1. **タスク 1**（前処理モード）→ 単体で preprocess の出力を確認。
2. **タスク 3**（Tubeness スケール）→ 既存テストで regressions がないか確認。
3. **タスク 8**（Decasting）→ `_binary_to_uint8` ヘルパーを用意し、「二値は uint8 0/255 に統一する」方針をコード・コメントに明記。
4. **タスク 6**（denoise 利用）→ `core.preprocessing` の import と、二値画像（uint8 0/255）に対する denoise_improved の呼び出しをパイプラインに追加。
5. **タスク 4 と 5**（フロー変更・二値 OR）→ パイプラインを「2 系統それぞれ二値化 → bool→uint8 変換 → denoise → OR → 最終 denoise」に書き換え。互換用に `fusion_method="weighted_sum"` の分岐を残す。
6. **タスク 2**（LoG 前ガウシアン）→ オプションとして組み込み。
7. **タスク 7**（呼び出し側）→ 必要箇所に引数を追加し、ドキュメント・コメントを更新。

---

### 9.5 Decasting（型・二値表現の統一）

パイプライン内で二値画像が **bool** と **uint8 (0/255)** のどちらで流れるかを決め、必要な箇所で明示的にキャストする方針を定める。

#### 現状のずれ

- **PhansalkarBinarizer.binarize()**: 戻り値は **bool**（`binary.astype(bool)`）。
- **BinaryPostProcessor.denoise_improved()**: 入力は `binary_img.copy()` と `np.sum(result > 0)` で利用。`cv2.medianBlur(result, 3)` は uint8 を前提とするため、**uint8 0/255 で渡すのが安全**（bool や 0/1 だと medianBlur の結果が 0/1 になり、後続の「255 を血管」とみなすコードと食い違う可能性がある）。
- **下流**（lesion_detector, skeleton_analyzer, regional_analyzer, fd_ring_analyzer, visualization）: 多くは `binary_image > 127` で二値化しているため、**0/255 の uint8 も bool も受け付け可能**。ただし「0 でない」と「255」を区別する実装はないので、**統一して 0 と 255 にしておく**と安全。
- **FilterFusion._logical_or()**: 入力は `> 127` で bool 化して OR し、出力は `(fused_binary.astype(np.uint8)) * 255` で **uint8 0/255**。

#### 方針（推奨）

1. **パイプライン内部の「二値」の正規型**: **uint8、値は 0 または 255** に統一する。
   - Phansalkar の直後で **bool → uint8 0/255** に変換するヘルパーを 1 箇所用意する（例: `_binary_to_uint8(binary)` → `np.where(binary, 255, 0).astype(np.uint8)`）。
   - `binary_log` / `binary_tubeness` / 最終 `binary` はすべて **uint8 0/255** で保持し、denoise_improved や OR、`intermediate_results` に渡す。
2. **denoise_improved の入出力**: 常に **uint8 0/255** で渡し、返り値も uint8 0/255 として扱う（core の実装は `result > 0` で白を判定しているため、255 である必要はないが、他モジュールとの整合のため 255 に揃える）。
3. **process() の返り値の binary**: `metrics["intermediate_results"]["binary"]` および可視化・保存用の `binary` は **uint8 0/255** で返す。既存コードが `binary > 127` や `binary_vessel > 0` で使っているため、そのままでよい。
4. **明示キャストの挿入箇所**
   - Phansalkar 適用直後: `binary_log = _binary_to_uint8(self.binarizer.binarize(log_filtered))` のように **bool → uint8 0/255**。
   - denoise_improved に渡す前: すでに uint8 0/255 にしていれば追加の cast は不要。万が一 bool が入る経路があれば、その手前で `_binary_to_uint8` をかける。
   - OR の入力: 両方とも uint8 0/255 にしておく。FilterFusion の `_logical_or` は `> 127` で bool 化するため、0/255 で渡せば正しく動く。
5. **ドキュメント**: 「MNV パイプライン内の二値画像は、denoise および OR の前後で uint8 0/255 に統一する」ことを docstring またはコメントで明記する。

#### タスク一覧への反映

- **タスク 4 の補足**: 各系統の二値化直後に `_binary_to_uint8` を適用し、以降は uint8 0/255 のみで扱う。
- **タスク 6 の補足**: `denoise_improved` には必ず uint8 0/255 を渡す。Phansalkar の戻り値（bool）をそのまま渡さない。

これにより、**decasting（どの段階でどの型に揃えるか）** を計画に含め、実装時の型不整合を防ぐ。

---

### 9.6 テスト・確認項目

- ImageJ モード（use_clahe=False, tubeness_scales=[1.0], fusion_method="logical_or"）で、同一画像を ImageJ と Python で処理したとき、バイナリの見た目・面積率が近いこと（完全一致は難しいため、定性的比較と面積率の差が許容範囲であること）。
- 互換モード（use_clahe=True, tubeness_scales=[1.0, 2.0, 3.0], fusion_method="weighted_sum"）で、変更前のパイプラインと同等の結果が得られること。
- `denoise_improved` に 0/255 の二値画像を渡したとき、core 側が正しく処理するか（必要なら core の実装が uint8 0/255 を前提としているか確認）。
- **Decasting**: パイプライン全体で binary が uint8 0/255 で一貫しており、lesion_detector / skeleton_analyzer / 可視化が期待どおり動作すること。bool が混在する経路がないこと。
