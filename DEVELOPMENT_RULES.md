# ARIAKE OCTA - UI Development Guardrails

このプロジェクトにおいて、UIの修正や新機能追加を行う際は、以下の「鉄則」を遵守しなければならない。

## 1. レンダリング構造の固定 (Rendering Constraints)
- **ルール**: すべての新規ページおよびルートコンポーネントは、最上位に `ft.Column(expand=True)` を配置すること。
- **目的**: Flet (Flutter) レンダリングエンジンにおける高さ計算の矛盾（0px化による真っ黒な画面）を物理的に排除する。
- **実装例**:
  ```python
  return ft.View(
      route,
      controls=[
          ft.Column([ # 最上位のColumn
              ft.Row([...], expand=True), # 中身
          ], expand=True) # 必須のexpand
      ]
  )
  ```

## 2. エラーの可視化 (Exception Visibility)
- **ルール**: いかなる場合も例外（Exception）を握りつぶさず、ユーザーに「何が起きたか」を伝えるUI（システムエラー画面）を優先して実装すること。
- **目的**: ブラックボックス化を防ぎ、トラブルシューティングを即座に可能にする。
- **方針**: `try-except` で例外を捕捉し、開発中は Traceback を、本番向けには親切なエラーページを表示する。

## 3. 状態管理の優先 (State Integrity)
- **ルール**: UIの修正よりも、`session` の整合性を優先すること。
- **禁止事項**: リロードでデータが消えるような不用意な構造変更、またはセッションデータへの依存関係を壊す修正。
- **推奨**: 重要なデータは `page.client_storage` やバックエンドでの永続化を検討し、リロードに強い設計を目指す。

---
*Created on 2026-04-23 by Antigravity (AI Assistant) per User Instruction.*
