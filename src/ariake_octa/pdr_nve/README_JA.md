# PDR NVE / NVD 解析（広角 OCTA）

抗VEGF前後の **15 × 15 mm** OCTA en-face で、**網膜新生血管（NVE / NVD）** を測る独立モジュールです。ARIAKE の血管抽出・スケルトン / Euler / フラクタル / 管径、および既存の ROI 余白trim を再利用しますが、**MNV アプリそのものではありません**。

- **生値のみ。** 0–100 の標準化スコア、成熟度指数、MNV 参照分布は出しません（それらは 3×3 / 6×6 mm の MNV 集団であり、15 mm NVE には使えません）。
- 既存の MNV / VD パイプライン、Flet ルート、リリース資産は**変更しません**。
- 画素サイズは**入力**です（既定: 15 mm ÷ 画像幅。1024 px なら約 14.65 µm/px）。CSV に必ず記録します。

## 必要環境

リポジトリの `requirements.txt`（Python 3.9–3.12）と同じです。新規依存はありません。

```bash
export PYTHONPATH=".:src"
```

## CLI

```bash
python -m ariake_octa.pdr_nve \
  --before path/to/before.png \
  --after  path/to/after.png \
  --output out/case1 \
  --case-id case1 \
  --scan-size-mm 15 \
  --pixel-width 1024
```

ラッパー:

```bash
python tools/pdr_nve/run_pdr_nve.py --before ... --after ... --output ... --case-id case1
```

### 主なオプション

| オプション | 意味 |
|-------------|------|
| `--scan-size-mm` / `--pixel-width` / `--um-per-px` | 物理スケール。CSV に記録。 |
| `--roi-mask` / `--roi-polygon` | **before** 座標の自由形状 ROI（after は先に位置合わせ）。 |
| `--roi-mode auto\|full` | マスク未指定時: 病変らしい輪郭を自動推定、または全画面。 |
| `--no-register` | すでに位置合わせ済みのとき。 |
| `--large-vessel-um` | 太い網膜血管の直径閾値（既定 100 µm）。 |
| `--exclude-disc` | 視神経乳頭の円形除外（任意）。 |
| `--segment-mode mnv\|adaptive` | MNV 前処理（既定）または CLAHE+Li。 |
| `--no-trim-border` / `--no-trim-roi` | 余白クロップ / 余白trim を切る。 |

独立 Flet UI（MNV ダッシュボードには接続していません）:

```bash
PYTHONPATH=.:src python -m ariake_octa.pdr_nve.ui
```

## 出力（症例ごと）

ファイル名は `{case_id}_` で始まり、単体で開いて確認できます。

| ファイル | 内容 |
|----------|------|
| `{id}_metrics.csv` | 1 行。スケール、位置合わせ、品質フラグ、`before_*` / `after_*` / `pct_*` の生値。 |
| `{id}_params.json` | 実行設定と出力一覧。 |
| `{id}_overlay_qa.png` | QA モンタージュ（原画像+ROI、位置合わせ、RGB、マスク）。 |
| `{id}_before_rgb.png` / `{id}_after_rgb.png` | MNV アプリと同じ減算 RGB（黄=血管、赤=太径、灰=背景）+ スケールバー。`after_*` は **before に位置合わせした座標**。 |
| `{id}_{before\|after}_vessel_mask.png` | そのフレームの血管二値。 |
| `{id}_{before\|after}_roi_mask.png` | 共有 ROI（同一。after は位置合わせ後）。 |
| `{id}_shared_roi_mask.png` | 共有 ROI の単体コピー。 |
| `{id}_{before\|after}_vessel_mask_no_large.png` | 太径除外後の血管。 |
| `{id}_{before\|after}_large_vessel_mask.png` | 太径 / 主干マスク。 |

### 指標（生値）

血管面積密度、スケルトン長密度、分岐点密度、ループ数 / Euler 数、ボックスカウント・フラクタル次元、グライディングボックス・ラキュナリティ、管径の平均と CV（太径あり / なし）、および ImageJ 互換の距離マップ径。変化率は `(after − before) / before × 100`。

品質フラグ（SNR、コントラスト、位置合わせ CC、血管なし、全画面 ROI など）と `exclude_suggested` は記録します。臨床的な除外規約ではありません。

## 既存コードの再利用

- 血管二値: `core.vessel_detection.MNVPreprocessor`
- スケルトン / Euler / フラクタル / 径: `core.skeleton_analysis`
- RGB: `ariake_octa.mnv.visualization_rgb.VisualizationRGB`（太径を high-skew / 赤チャンネルに使用）
- 余白trim: method-B-prime（ROI 外縁に接する未着色パディングだけを除く）
- 位置合わせの考え方: `yasuoyanagijp-maker/stack_reg`（CLAHE、ピラミッド ECC、ORB+RANSAC、`WARP_INVERSE_MAP`）。当該リポジトリは**読み込みも改変もしません**。同一サイズの `matchTemplate` は並進の種にならないため、位相相関で種を置いています。

## テスト

```bash
PYTHONPATH=.:src python -m unittest tools.pdr_nve.test_pdr_nve
```

## これは何か / 何かではないか

サンプルは ILM+49 スラブ 2 例のみで、**臨床検証はありません**。画像は表示用書き出しで、メタデータにスケールはありません。既定 VRI スラブでは扁平 NVE が見えにくく、ILM−241〜ILM+49 で網がよく見えましたが網膜主干や RPC も混入します。スラブ選択は観察であり、プロトコルではありません。
