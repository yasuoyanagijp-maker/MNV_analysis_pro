# MNV バイナリ作成：変更前・変更後（Streamlit / mainstreamer.py）の詳細検討

参照: [MNV_binary_ImageJ_vs_Python_diff.md](./MNV_binary_ImageJ_vs_Python_diff.md)、[ARIAKE_OCTA_MNV_binary_process_CLAHE_binarization.md](/Users/yy/git/ARIAKE_MNV_fresh/docs/ARIAKE_OCTA_MNV_binary_process_CLAHE_binarization.md)（ImageJ マクロ仕様）

Streamlit アプリ（mainstreamer.py）では、MNV 解析に **core.mnv_pipeline.MNVPipeline.analyze()** が使われ、その中で **ariake_octa.mnv.create_mnv_binary_for_core()** が呼ばれる。`create_mnv_binary_for_core` は `MNVPipeline(pixel_size_mm=...)` のみを渡して `process()` を実行するため、**現在は変更後（ImageJ 準拠）のデフォルト**（`use_clahe=False`, `fusion_method="logical_or"`）が適用されている。

---

## 1. MNV 解析のバイナリ画像を作るまでのプロセス（全体フロー）

### 1.1 変更前（従来フロー：加重和 + 1 回二値化）

| ステップ | 処理内容 |
|----------|----------|
| 1. 前処理 | **CLAHE**（blocksize=127, clip_limit=3）+ **ガウシアン背景除去**（sigma=5）+ 0–255 正規化 |
| 2. 特徴抽出 | LoG(sigma=1)、Tubeness(**マルチスケール** [1, 2, 3]、最大応答) を **グレースケールのまま** 計算 |
| 3. 融合 | **加重和** fused = 0.5×LoG + 0.5×Tubeness（0–255 にクリップ） |
| 4. 二値化 | 融合画像に **Phansalkar を 1 回だけ** 適用（window_radius=15, k=0.25, r=0.5） |
| 5. 後処理 | Despeckle・小粒子除去の **明示的ステップなし**（BinaryPostProcessor.denoise_improved は未使用） |

- **融合のタイミング**: グレースケール同士の融合 → 1 枚の「強調画像」に対して 1 回閾値。
- **二値化の回数**: 1 回（Phansalkar のみ）。
- **ImageJ マクロとの対応**: 前処理・融合・二値化のいずれも ImageJ MNV フローと異なる。

### 1.2 変更後（ImageJ 準拠フロー：二値 OR + 各系統で二値化）

| ステップ | 処理内容 |
|----------|----------|
| 1. 前処理 | **CLAHE なし**。**Despeckle のみ**（3×3 メディアンフィルタ）。setMinAndMax 相当の clip は省略可。 |
| 2. 特徴抽出 | LoG(sigma=1)、Tubeness(**単一スケール** [1.0]) をそれぞれ計算。 |
| 3. 各系統の二値化 | LoG 出力 → **Phansalkar** → **denoise_improved(remove_small_particles=True)** → binary_log。Tubeness 出力 → **Phansalkar** → **denoise_improved(remove_small_particles=True)** → binary_tubeness。 |
| 4. 融合 | **二値 OR** binary = binary_log \| binary_tubeness（0/255 の uint8）。 |
| 5. 後処理 | 最終 binary に **denoise_improved(remove_small_particles=False)** を 1 回適用。 |

- **融合のタイミング**: 二値画像同士の OR（ImageJ の `imageCalculator("OR create", mex_hat.tif, tubeness.tif)` 相当）。
- **二値化の回数**: 2 回（LoG 系統・Tubeness 系統それぞれに Phansalkar）。ImageJ では Mexican Hat=Make Binary（自動閾値）、Tubeness=Sauvola；Python では両系統とも Phansalkar に統一。
- **ImageJ マクロとの対応**: 前処理（CLAHE なし・Despeckle）、融合（二値 OR）、Tubeness 単一スケール、denoise の適用順が ImageJ に揃っている。

### 1.3 mainstreamer.py における経路の整理

- **mainstreamer.py** は `CoreMNVPipeline(scale_mm=..., save_stages=False, verbose=False, enable_roi_refinement=True)` を生成し、`pipeline.analyze(image_path=..., output_dir=..., flow_deficit_image_path=..., roi_mask=...)` を呼ぶ。
- **core/mnv_pipeline.py** の `analyze()` 内で、Step 2 として `create_mnv_binary_for_core(image, pixel_size_mm=scale_manager.mm_per_pixel)` を実行する。
- **create_mnv_binary_for_core** は `MNVPipeline(pixel_size_mm=pixel_size_mm)` のみを渡すため、**常に変更後フロー**（`use_clahe=False`, `fusion_method="logical_or"`, Tubeness scales=[1.0]）が使われる。mainstreamer から use_clahe や fusion_method を切り替える引数は現状ない。

---

## 2. 変更前の方がよかった点・悪かった点

### 2.1 変更前の方がよかった点

1. **コントラストの安定性**  
   CLAHE + 背景除去により、撮影条件や装置差による明るさ・コントラストのばらつきをある程度吸収でき、**見た目の「血管らしさ」が強調**されやすい。低コントラスト・フラットな画像でも、融合画像が 1 枚にまとまるため「どこを血管とみるか」が分かりやすい場合がある。

2. **マルチスケール Tubeness の利点**  
   スケール [1, 2, 3] の最大応答を使うため、**細い毛細血管とやや太い血管の両方**に応答しやすく、血管の「太さの多様性」を 1 枚の強調画像に集約できる。単一スケールより情報量が多い。

3. **実装・デバッグの単純さ**  
   融合が「グレースケール 2 枚の加重和」で、二値化は 1 回だけなので、**パイプラインの段階が少なく、途中結果の解釈が容易**。Phansalkar のパラメータも 1 セットで済む。

4. **後処理の負荷**  
   denoise_improved を各系統・最終に複数回かけないため、**計算時間が短く、小粒子除去による「血管の切れ」のリスクが理論上はない**（その代わり、ノイズがそのまま残る）。

### 2.2 変更前の方が悪かった点

1. **ImageJ マクロとの非対応**  
   ImageJ で確立した MNV 解析プロトコル（CLAHE なし・二値 OR・単一スケール Tubeness・denoise あり）と異なるため、**同一症例を ImageJ と Python で処理した場合、バイナリや面積率が一致しにくい**。論文・既存ワークフローとの互換性が低い。

2. **前処理の過剰な強調**  
   CLAHE と背景除去は **VD 解析向け**の設計に近く、MNV 病変部の微細血管では **過強調・ノイズ増幅** になりやすい場合がある。ImageJ の MNV フローは意図的に CLAHE を使っていない。

3. **融合方法の違い**  
   グレースケールの加重和は「中間的な強度」を多く含むため、その後の 1 回の Phansalkar では **LoG 寄りと Tubeness 寄りの情報が混ざった閾値** になる。ImageJ のように「各系統で独立に二値化して OR」すると、**どちらか一方で検出されれば血管として残る** という明確な論理になる。

4. **後処理の欠如**  
   ImageJ では各系統に denoise_improved(1)（Despeckle + 小粒子除去）、最終に denoise_improved(0) をかけている。変更前は **ノイズや小粒子がそのまま残り**、面積率やスケルトン解析にバイアスを与える可能性がある。

---

## 3. 変更後の方がよかった点・悪かった点

### 3.1 変更後の方がよかった点

1. **ImageJ との互換性**  
   前処理（Despeckle のみ）、融合（二値 OR）、Tubeness 単一スケール、denoise の順序・有無が ImageJ MNV マクロに揃っている。**同一画像で ImageJ と Python の結果を比較・検証しやすく**、既存のプロトコルや論文との整合が取りやすい。

2. **MNV 向けの前処理**  
   CLAHE を使わないことで、**病変部の微細血管が過強調されすぎず**、元のコントラストに近い情報で LoG/Tubeness がかかる。ImageJ の設計意図（MNV では preproc のみ）に沿っている。

3. **二値 OR の解釈の明確さ**  
   「LoG で血管とみなされた領域」と「Tubeness で血管とみなされた領域」の **合併** として最終バイナリが決まる。系統ごとに閾値を決めるため、**どちらの特徴が効いているか** が分かりやすく、デバッグやパラメータ調整にも向く。

4. **ノイズ・小粒子の抑制**  
   各系統の二値画像に denoise_improved(1)（小粒子除去あり）、最終に denoise_improved(0) をかけることで、ImageJ と同様に **孤立点や細かいノイズが減り**、血管面積・スケルトン指標が安定しやすい。

5. **再現性・ドキュメントとの一致**  
   MNV_binary_ImageJ_vs_Python_diff.md や ARIAKE_OCTA_MNV_binary_process_CLAHE_binarization.md に書いた「ImageJ に合わせる」方針と実装が一致し、**後から仕様を追いかけやすい**。

### 3.2 変更後の方が悪かった点

1. **低コントラスト画像での弱さ**  
   CLAHE をかけないため、**元画像が暗い・フラットな場合**、Despeckle だけでは十分なコントラストが得られず、LoG/Tubeness の応答が弱く、**血管検出が不足**することがある。変更前のように「強めの前処理」を選べるオプションがないと、そうした症例では不利になりうる。

2. **単一スケール Tubeness の限界**  
   sigma=1 のみだと、**太めの血管** の応答が相対的に弱く、LoG に依存しがちになる。マルチスケールなら拾えた血管が、変更後では細い血管中心になりうる。

3. **処理ステップと計算量の増加**  
   二値化が 2 回、denoise_improved が 3 回（LoG 系統・Tubeness 系統・最終）入るため、**パイプラインが長く、計算時間は変更前より増える**。また、パラメータ（Phansalkar の k/r、denoise の反復回数・小粒子除去の有無）が増え、チューニングの余地が広がる。

4. **小粒子除去の副作用リスク**  
   denoise_improved(remove_small_particles=True) で「平均面積未満の粒子を黒で塗りつぶす」ため、**本当に細い血管の断片** が消える可能性がある。ImageJ と同じロジックだが、症例によっては血管のつながりが欠けることがある。

---

## 4. まとめと運用上の提案

- **変更後（現在の mainstreamer / create_mnv_binary_for_core）** は、**ImageJ MNV プロトコルとの互換性・再現性・ドキュメントとの一致** を重視した設計になっている。一方で、**低コントラスト画像** や **太い血管も含めたマルチスケール** では、変更前の方が有利な面がある。
- **運用上の提案**  
  - 通常運用は **変更後（ImageJ 準拠）のまま** とし、論文・既存 ImageJ 結果との比較を主目的にする。  
  - **低コントラストや結果が不満足な症例** 向けに、mainstreamer または core の呼び出しオプションで **use_clahe=True** や **fusion_method="weighted_sum"**、**tubeness_scales=[1.0, 2.0, 3.0]** を選べるようにすると、変更前相当の「強化モード」を必要時だけ使える。  
  - その場合も、**デフォルトは変更後（use_clahe=False, fusion_method="logical_or", tubeness_scales=[1.0]）** にしておき、互換性を主、強化を従とするのがよい。

以上が、Streamlit（mainstreamer.py）における「変更前の MNV バイナリ作成フロー」と「変更後（ImageJ 準拠）フロー」の違い、および変更前の方がよかった点・悪かった点、変更後の方がよかった点・悪かった点の詳細検討である。
