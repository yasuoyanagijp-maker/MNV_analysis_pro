# 対話式グレーディング／ICC Session2 プロトコル

チャットでエージェントと進めます。空の CSV を一人で埋めない。

## 許可サブタイプ（表記厳守）

`Dead tree` / `Tree in bud` / `Glomerular` / `Seafan` / `Medusa`

## 盲検グレーディング（先に完了）

**主手段: ドロップダウン UI**（テキスト入力不要）

```bash
scripts/graefe_revision/run_grade_ui.sh
# または: .venv/bin/python scripts/graefe_revision/grade_ui.py
```

UI にプレビュー・`blind_id`・stratum・サブタイプ Select（上記5つ）・Save & Next / Skip / Open full-res / Status (X/54) がある。Save は `expert_grades_blind.csv` に `interactive_grade.py` と同じ規則で書き込む。自動ラベルは表示しない。

## 再評価（discordance / UI 暴走疑い）

`regrade_queue.csv` のみ巡回。自動ラベルを表示し、blind + locked 両方を更新。変更は `regrade_log.csv` に記録。

```bash
scripts/graefe_revision/run_regrade_ui.sh
# http://127.0.0.1:8766/
```

完了後（κ はユーザー指示まで再計算しない）:

```bash
.venv/bin/python scripts/graefe_revision/compute_agreement.py
```

チャット経由の代替（CLI）:

1. エージェントがプレビュー画像（`previews/Bxxx.png`）を見せる
2. ユーザーは次のいずれかで返答:
   - `B001 Glomerular`
   - 文脈が明確ならサブタイプのみ（例: `Glomerular`）
3. エージェントが記録:
   ```bash
   .venv/bin/python scripts/graefe_revision/interactive_grade.py --set B001 "Glomerular"
   ```
4. 次の未評価例へ。必要なら Preview で原寸:
   ```bash
   .venv/bin/python scripts/graefe_revision/interactive_grade.py --next --open
   ```
5. **54/54 完了後**: CSV をロック → `compute_agreement.py`  
   グレーディング中は `automated_labels.csv` / `grading_subset_meta.csv` を開かない

## ICC Session2（グレーディング後、1例ずつ）

1. エージェントが `--next`（**Session1 スコアは表示しない**）
2. `./run_flet.sh` で画像を開き、新規 freehand ROI（FOV: large/small=6mm, small_3mm=3mm）
3. 自動解析後、メトリクスをエージェントへ伝える → `--set` で記録
4. 30/30 完了後: ロック → `compute_icc.py`

## 禁止

- グレーディング中の自動ラベル閲覧・アンブラインド
- ICC ROI 前に Session1 スコアを見ること
- このリビジョンブランチの `git push`
