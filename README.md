# ARIAKE OCTA Analysis

OCTA 画像を用いた **MNV（脈絡膜新生血管）解析**および **VD（血管密度）解析**向けのアプリケーションです。従来の **ImageJ マクロ（ARIAKE OCTA／カラーコード版）** の解析思想を踏まえつつ、**操作画面は主に Flet（Python）で構築**したデスクトップ／ブラウザ UI です。

## 文書の位置づけ

- **操作の詳細**（起動モード、ログイン、ダッシュボード、トラブルシューティング）は **[USER_MANUAL.md](USER_MANUAL.md)** を参照してください。
- **ARIAKE 向けマニュアル一式**（詳細版・付録・簡易版・PDF 印刷の案内）は **[documentation/README.md](documentation/README.md)** を参照してください。
- 旧 RTF のみをお持ちの場合は、その内容と **[documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md](documentation/ARIAKE_OCTA_詳細ユーザーマニュアル_V2.md)** および付録を突合してください。

---

## マクロ版からの主な変更

| 項目 | マクロ（ImageJ）中心のイメージ | 本アプリ |
|------|-------------------------------|----------|
| UI | ImageJ 上のダイアログ・マクロ実行 | **Flet** によるウィザード型 UI（ログイン、ダッシュボード、ROI、MNV ウィザード、結果画面）。バックエンドは **FastAPI**。 |
| 起動 | ImageJ + マクロ | 配布版: `ARIAKE_OCTA.app`＋`インストール.command`。開発版: `run_flet.sh` 等（詳細は USER_MANUAL）。 |
| 解析ロジック | マクロ／プラグイン | Python パイプライン（`src/ariake_octa`、`src/core`）。**ImageJ 互換の測定列名**で CSV 出力する設計があります（`src/utils/mnv_imagej_csv.py`）。 |

---

## カラーコード（RGB 可視化）

MNV 解析結果の **RGB 合成表示**は、ImageJ 版の減算方式と整合する想定です。

| 表示の目安 | 意味 |
|------------|------|
| **黄** | 正常血管（二値化血管に相当。R+G が支配的） |
| **赤** | **拡張血管（高歪度／細動脈化に相当する成分）** |
| **グレー系** | 背景（元画像の輝度） |

実装の根拠は `src/ariake_octa/mnv/visualization_rgb.py` を参照してください。

---

## 細動脈化（Arteriolarization）解析

マクロ版の説明に加え、本アプリでは **スケルトン上の管径分布（距離変換）から高歪度（high skew）を推定し、細動脈化様の血管セグメントを定量化**します。ImageJ の `performHighSkewnessAnalysis` / `analyzeArteriolarizationSegments` に相当する処理の移植に近い実装です（`src/ariake_octa/arteriolarization.py`、`src/core/skeleton_analysis.py` 等）。

### 出力 CSV に含まれる主な列（ImageJ 互換名）

- **Arteriolarization Segment Count** — セグメント数  
- **Arteriolarization Total Length (mm)** — 該当スケルトンの合計長（高歪度寄与分）  
- **Arteriolarization Max Segment Length (mm)** — 最大セグメント長  
- **Arteriolarization Density (/mm²)** — ROI 面積あたりのセグメント密度  
- **Arteriolarization Connectivity Index (mm/segment)** — 接続性の指標  
- **Local Diameter Variation (max CV%)** — 局所径変動（CV%）  
- **Dilated vessel (%)** — 高歪度の割合（パイプライン定義に従う）

分類ロジックでは、病態パターンに **「Arteriolarized」** が現れる場合があります（`src/core/pattern_classifier.py`）。

---

## macOS へのインストール（配布用）

1. 配布フォルダ（または DMG 内）に **`ARIAKE_OCTA.app`** と **`インストール.command`** が**同じ階層**にあることを確認します。  
2. **`インストール.command` をダブルクリック**します。  
3. 初回のみ macOS の警告が出る場合は、**右クリック →「開く」**などで許可します。  
4. スクリプトが `xattr` のクリア、`/Applications` へのコピー、初回起動まで行います。  
5. 以降は **アプリケーション**フォルダの **ARIAKE_OCTA** から起動します。

ZIP で渡す場合も、上記 2 ファイルを**同じフォルダに入れたまま**圧縮してください。DMG にまとめる場合も同様に、マウント後に両方が見える構成にします。

---

## 開発者・ソースから実行する場合

仮想環境の作成、`requirements.txt` のインストール、**`./run_flet.sh`** による起動などは **[USER_MANUAL.md](USER_MANUAL.md)** の「セットアップ」「起動方法」を参照してください。

実装・アーキテクチャは **[DEVELOPER.md](DEVELOPER.md)** を参照してください。

---

## 注意事項

- 本ソフトの出力の**医学的・診断的解釈**は、施設の方針と専門家の判断に従ってください。  
- **個人情報・医療情報**の取り扱いは、各施設の情報セキュリティおよび研究倫理に準拠してください。  
- 未公証のバイナリ配布では、利用者の macOS で Gatekeeper のメッセージが出ることがあります。研究室内配布で問題が多い場合は、署名・公証（Apple Developer）の検討をしてください。

---

## ライセンス・引用

本リポジトリのソースコードは **[MIT License](LICENSE)** で提供されています（無保証）。臨床・診断への適合性や安全性は保証されません。施設の方針に従い、必要なら別途契約・同意文書を整えてください。

先行研究やマクロ版マニュアルを論文等で引用する場合は、**各施設・著者の指定する引用形式**に従ってください。
