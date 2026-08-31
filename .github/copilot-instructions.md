# プロジェクト概要

- 眼科領域（網膜疾患：VD/MNV）の画像解析支援アプリケーションである。
- フレームワークは **Flet (Python)** である。
- 文体ルール: ドキュメントや解説は **「である」調**で統一する。

# コーディング規約

- **UI コンポーネント**は `components/` に、**ビジネスロジック**は `src/core/` に分離する。
- グラフや解析結果の表示には、**一貫した配色（BioRender 風）**を意識する。
- 複雑なロジックには、**数式による説明を添える**（LaTeX は使わずプレーンテキストで記述する）。

# ワークフロー

- リファクタリング時は必ず **`src/utils/` の既存ツール**が再利用できないか確認すること。
- **UI の修正**は **`fix-ui` ブランチ**で行う。

# 配布・ログイン問い合わせ（Mac Connection Error）

- 「Connection Error: All connection attempts failed」は **パスワード誤りではない**。ログイン UI は出ても、同じ PC 内の FastAPI に届いていない。
- **Mac（M1 等）の第一仮説は病院ネットワークではない。** 公開 `v1.2.3-mac` は ad-hoc + Hardened Runtime のため Connection Error になりうる。**v1.2.4-mac**（PR #43）では Hardened Runtime なし + スレッド起動 + `インストール.command` 再署名。
- 返信は `documentation/配布依頼メールテンプレート.txt` の **「Connection Error（Mac・第一返信）」** を使う。v1.2.3 相手には新 ZIP を約束しない。v1.2.4 再送可。他施設名を書かない。
- 案内するコマンド（既存アプリのまま）:
  `xattr -cr /Applications/ARIAKE_OCTA.app` のあと `codesign --force --deep --sign - /Applications/ARIAKE_OCTA.app`。`xattr` だけでは直らない。
- Windows 電子カルテ端末のときだけ「病院Windows」ひな型。詳細は `documentation/配布ユーザー管理・応先手順書.md` の 4-F。
