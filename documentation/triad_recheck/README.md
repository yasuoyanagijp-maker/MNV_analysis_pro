# 最終読影者によるRECHECK再解析とトライアッド中央値確定

G1/G2の二重読影でRPDが採用基準を超えNA（RECHECK）となった主要指標セルを、
最終読影者（Final Reader）が再読影し、**median(G1, G2, 最終読影者) を確定値として採用**する
ワークフローの実装ドキュメントです。

## 実装前確認事項の結果（3点）

### 1. 既存のG1/G2ログイン・ロール管理の実装方式

- ロールは **DBテーブル・enumではなく、`src/utils/second_reader.py` の文字列定数と
  `READER_ROLE_OPTIONS` リスト**（`(コード, 表示名)` タプル）で管理。
- ログイン画面（`src/flet_ui/pages/login.py`）のドロップダウンはこのリストから生成され、
  選択値は Flet セッション（`reader_role`）と client_storage に保存されるのみ
  （サーバー側のロール認証はなし・パスワードは共通）。
- したがって「最終読影者」の追加は **新テーブル/enum不要**で、以下のみ:
  - `ROLE_FINAL_READER = "FINAL"` 定数 + `READER_ROLE_OPTIONS` へ1タプル追加
  - `login.py` の永続値バリデーションに `FINAL` を追加
  - `is_final_reader(session)` ヘルパー（既存 `is_second_reader` と同型）
- 開発用バイパス: `DEV_MODE=1 ARIAKE_READER_ROLE=FINAL`（`main_app.py`）。

### 2. 既存のNA/採用判定に使われているRPD閾値

**全数値列共通の単一閾値 20% です。パラメータ種別（area系/density系等）による
閾値の違いはありません。**

| シンボル | 場所 | 値 |
|---|---|---|
| `DEFAULT_RPD_PCT` | `tools/reading_center_rpd/compute_adopted_from_dual_csv.py` | `20.0` |
| `RPD_THRESHOLD_PCT` | `src/utils/dual_grader_merge.py`（上記の再エクスポート） | 20.0 |
| `RPD_REVIEW_THRESHOLD_PCT` | `src/utils/triad_median_resolver.py`（本機能・上記の再エクスポート） | 20.0 |

- RPD定義: `|A − B| / ((|A| + |B|) / 2) × 100`（`rpd_pct`）
- 採用ルール（`adopt_pair`）: 欠損→`NA`(MISSING)、RPD>20%→`NA`(RECHECK)、それ以外→算術平均
- パラメータ種別で異なるのは閾値ではなく、RECHECKリスト対象の**主要指標の選定**
  （`MAJOR_METRICS` 8項目: MNV Area (mm2) / Vsl Area (mm2) /
  Vsl Density (Vessel Area/MNV (%)) / Caliber Uniformity Score (U2) /
  Maturity Index (U2) / Network Complexity Score / Fractal Dim / Tortuosity）のみ。
- **要レビュー判定はこの既存20%をそのままインポートして流用**しています
  （`RPD_REVIEW_THRESHOLD_PCT = DEFAULT_RPD_PCT`）。新しい閾値の決め打ち追加はありません。
  テスト `tools/test_triad_median_resolver.py::TestThresholdReuse` で同一性を検証。

### 3. 症例画像ファイル名 → 内部IDの逆引き

逆引きロジックは既存で、2系統あります。

- **アプリ内統合（G1×G2マージ）**: `dual_grader_merge.match_stem()` —
  `102-001_Week04.png` → 正規化stemキー `102-001_week04`
  （拡張子除去・記号→`_`・小文字化）。adopted/recheck の行はこのキーで突合されている。
- **中央読影CLI**: `extract_case_from_text` / `normalize_visit` —
  `102-001_Week04.png` → `MatchKey(case="102-001", visit="Week04")`
  （`W4`→`Week04` ゼロ埋め正規化あり）。
- 注意: バッチCSVの `ID` 列は連番であり症例IDではない。症例・Visit情報は `File` 列にのみ存在。
- 本機能のトライアッド突合には、**adopted/recheck 生成と同一の `match_stem` キー**を使用
  （整合性が保証されるため）。CLI形式のrecheck_list（Case/Visit列）にも対応。

## ワークフロー

1. ログイン画面で Role「最終読影者（RECHECK再読影・トライアッド確定）」を選択
2. ダッシュボードの最終読影者カードから **RECHECK対象MD（`*_summary.md`）をファイル選択**
   （毎回手動選択。フォルダを確定した場合は最新の `*_summary.md` を自動選択）
3. MDをパースし「症例画像 × パラメータ」の対象リストを取得
   - **未知のパラメータ表記があれば処理を中止して報告**（サイレント無視しない）
   - MD記載の件数と解析結果の不一致は警告として表示（処理は継続）
4. 対象症例画像**のみ**が通常の ROI描画 → 解析キューに投入される（既存ワークフロー再利用）
5. 結果画面で Save CSV →「トライアッド確定」ボタン
6. **dry-run プレビュー**（全セルの G1/G2/最終読影者/median/CV%/要レビューを表示、書き込みなし）
7. 「本確定を実行」で3ファイルを書き出し

## 確定ロジック（`src/utils/triad_median_resolver.py`）

| フィールド | 内容 |
|---|---|
| `final_value` | `median(G1, G2, 最終読影者)`。G1/G2の一方がMISSINGの場合は2値の中央値（=平均） |
| `needs_review` | `RPD(median, 最終読影者値) > 20%`（既存閾値流用）のとき `true`。値は確定・処理は継続 |
| `g1_value` / `g2_value` / `final_reader_value` | 監査用に3値とも保持 |
| `cv_percent` | 3値の CV% = SD/平均×100（標本SD, ddof=1）。トライアッドの再現性報告（CV%/ICC）に使用 |

- RECHECK指定**外**のセルは、最終読影者が同じ画像を読影していても一切使用・上書きしない
  （テストで最終読影者の非対象値がリークしないことを検証済み）。
- 最終読影者CSVにも既存パイプラインと同じ **U2再計算**を適用してから突合する。
  値の参照は素の既定列 / `… (U2)` / `Standardized …` の等価列名を順に試すため、
  再計算が失敗した場合やビルド間の列名差があっても解決できる。
- 最終読影者の値が無いセル・G1/G2が両方欠損のセルは `UNRESOLVED` として報告し、
  adopted 側は `NA` のまま（処理は継続）。

## 出力ファイル（元の統合CSVと同じフォルダに新規作成）

| ファイル | 内容 |
|---|---|
| `{prefix}_triad_resolved_cells.csv` | セル別監査レコード（上表の全フィールド + RPD + 状態） |
| `{prefix}_triad_adopted_values.csv` | adopted CSV のコピーに RECHECK セルのみ median を適用したもの + `Triad Needs Review (metrics)` 列 |
| `{prefix}_triad_summary.md` | ルール・集計・セル別テーブル |

**元の `{prefix}_adopted_values.csv` / `{prefix}_recheck_list.csv` は一切変更しません。**

## dry-runモードの実装可否についての所見

**実装済み（推奨どおり2段階フロー）。** 実装コストは低いと判断しました。理由:

- 確定出力は元CSVのin-place書き換えではなく新規ファイルのため、resolver に `dry_run`
  フラグを1つ持たせるだけで「計算のみ→プレビュー→本確定」が実現できる
  （`resolve_triad_recheck(..., dry_run=True)` は同一のsummaryを返しファイルを書かない）。
- 臨床データ確定という性質上、最終読影者が全セルを目視確認してから書き出す価値が
  コストを大きく上回る。
- dry-run がファイルを書かないことはテストで担保
  （`test_dry_run_writes_nothing`）。

## RECHECK MDフォーマットと表記ゆれ対応（`src/utils/recheck_md_parser.py`）

想定フォーマット:

```markdown
## RECHECK

- 主要指標セル: 3 件（対象症例 2 件）
- 症例別（NA となった主要指標）:
  - 102-001_Week04.png: Vsl Area (mm2)
  - 102-002_Week04.png: MNV Area (mm2), Caliber Uniformity Score
```

- 全角/半角の括弧・コロン・カンマ、箇条書き記号（`-` `*` `・` `•` 番号付き等）、
  見出しレベル（`##`/`###`）、`対象症例`/`対象ファイル` 表記の揺れに対応（NFKC正規化）。
- パラメータ名マッピング表: `MAJOR_METRICS` の正式名に加え、
  Caliber / Maturity は **素の既定列名を正**とし、`… (U2)` / `Standardized …` を
  同一指標の別名として等価扱い（`column_candidates` が CSV 側の実列名に
  フォールバック）。`Vsl Density`→`Vsl Density (Vessel Area/MNV (%))`、
  `Fractal Dimension`→`Fractal Dim` 等の略記エイリアスも許容。
  **マッピング不能な表記は `UnknownParameterError` で処理を中止**。
- `dual_grader_merge` の summary MD ライターも拡張し、統合時に
  「症例別（NA となった主要指標）」リストを自動出力するようにした
  （ライター→パーサーのラウンドトリップをテストで検証）。

## テスト

```bash
python3 -m unittest tools.test_recheck_md_parser tools.test_triad_median_resolver
```

31テスト（パーサー16 + リゾルバー15）。既存の
`tools/reading_center_rpd/test_compute_adopted.py` / `tools/test_second_reader_fov.py`
も回帰なしを確認済み。
