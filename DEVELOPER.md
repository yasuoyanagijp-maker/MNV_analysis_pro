# ARIAKE OCTA — 開発者向けガイド

エンドユーザ向けの操作は **[USER_MANUAL.md](USER_MANUAL.md)** を参照してください。本書は**実装・デバッグ・拡張**のためのメモです。

---

## 1. 技術スタックと制約

| 項目 | 内容 |
|------|------|
| Python | **3.9 互換**を維持（型ヒント・ジェネリクス等に注意） |
| UI | **Flet 0.28.3**（Web ブラウザ / ネイティブの両方を想定） |
| API | **FastAPI** + **httpx**（フロントは `BackendClient` 経由） |
| 主要エントリ | `main_app.py`（Flet）、`src/api/main.py`（API）、`run_flet.sh`（一体起動） |

---

## 2. リポジトリのざっくり地図

```
main_app.py          # Flet アプリ: ルーティング、AppContext、FilePicker
pages/               # 各画面: login, dashboard, results_screen, roi_selection, mnv_wizard, …
components/shared.py # テーマ色、AppContext、BackendClient、共有 UI
src/api/             # FastAPI: エンドポイント、スキーマ
src/core/            # MNV/VD パイプライン呼び出し
src/ariake_octa/     # 解析コア（画像処理多数）
src/utils/           # 共通ユーティリティ（mnv CSV、report_generator、cv2_path 等）
uploads/             # 実行時アップロード先（.gitignore 想定）
```

`scratch/` は実験用。本番同梱の前提で書かない。

---

## 3. 起動と環境変数

| 変数 | 既定 | 意味 |
|------|------|------|
| `FLET_USE_WEB` | `1` | `1` = ブラウザ（`AppView.WEB_BROWSER`）。`0` や `native` 等 = ネイティブウィンドウ（`FLET_APP`） |
| `FLET_PORT` | `8550` | Flet のポート（`main_app` と `run_flet.sh` の両方で使用） |
| `FLET_SERVER_IP` | `127.0.0.1`（`run_flet.sh` 既定） | Web 時の uvicorn バインド。`0.0.0.0` だと Flet が `http://0.0.0.0:…` を開き**ブラウザで白紙のまま**になることがある。LAN 向けに `0.0.0.0` を付ける場合は、同一マシンでは `http://127.0.0.1:FLET_PORT` を手動で開く。 |
| `DEV_MODE` | 未設定 | `1` のとき**ログイン無効**・テスト用セッション注入。**本番禁止** |
| `DEV_MODE` 以外 | — | バックエンド URL 等を変える場合は `components/shared.py` の `BackendClient` を確認 |

`run_flet.sh` は `FLET_USE_WEB` を `export` し、**`flet run --web` と素の `flet run` を切替**する。`python main_app.py` 直叩きの場合も `_flet_use_web()` が同じ変数を読む。

---

## 4. アーキテクチャ（Flet 側）

### 4.1 ルーティング

- `page.on_route_change` で `page.route` を解釈し、`get_*_view(ctx)` を差し替える。
- ルート例: `/login`, `/`, `/results`, `/roi`, `/mnv`（`main_app.py` を真実の情報源にする）。

### 4.2 `AppContext`（`components/shared.py`）

- `page`, `client`（`BackendClient`）、各種 `ft.Ref`、**FilePicker 3 種**、後から注入される `process_target_path` を保持。

### 4.3 セッション

- 解析対象パス: `page.session`（例: `target_path`）、結果: `last_result` / `batch_results` 等。  
- **リロードで消える**前提。永続化が必要なら API か `client_storage` を検討（[§6](#6-ui-開発上のガードレール)）。

### 4.4 FilePicker と `page.web`

- **Web** では Flet の **`get_directory_path` は事実上使えない**（公式制限）。`pages/dashboard.py` は `getattr(page, "web", False)` により、Web 時は**サーバ側 `list_dir` ベースのエクスプローラ**等へ分岐。
- **ネイティブ**（`FLET_USE_WEB=0`）では OS ダイアログが使える想定。

### 4.5 ナビゲーション

- 標準 `NavigationRail` 等は **Python 3.9 環境で問題が出たため**、**カスタムサイドバー**に置き換え済み。新 UI でも同方針を踏襲する。

---

## 5. バックエンド（API）

- 実装: `src/api/main.py`。解析は `src/core` / `src/ariake_octa` に委譲。
- フロントの呼び出し: `BackendClient`（`httpx`、既定 `http://127.0.0.1:8000`）。**ローカル API には `trust_env=False`**（大学ネットの `HTTP_PROXY` が 127.0.0.1 を吸い上げて "All connection attempts failed" になるのを防ぐ）。GakuNin 通信は別クライアントでプロキシを使う。
- 新エンドポイント追加時: **スキーマ**（`src/api/schemas.py`）と **Client メソッド**の両方を更新すると安全。

---

## 6. UI 開発上のガードレール

以下は既存方針の要約（ブラック画面・原因不明障害の防止）。

### 6.1 レイアウト

- 新規ページの最上位は、可能な限り **`ft.Column(expand=True)` 等、親から高さが取れる構造**にする。Flet/Flutter では**高さ 0 になり真っ黒**になる事象に注意。

### 6.2 例外

- 例外を飲み込まず、ログとユーザー向けメッセージ（または既存のエラーダイアログ）に繋ぐ。`main_app` では `route_change` 周りの失敗を捕捉している。

### 6.3 セッション整合性

- `session` のキー名や意味を変える前に、**全ルート**での利用箇所を棚卸しする。

### 6.4 新しい画面の追加手順（目安）

1. `pages/<name>.py` に `async def get_<name>_view(ctx: AppContext)` を定義。  
2. `main_app.py` の `route_change` に `elif` を追加。  
3. 必要ならサイドバーに遷移ボタンを追加。  
4. Web/ネイティブ両方で**最小操作**（パス通過・戻る）を確認。

---

## 7. デバッグ

- ターミナルに **`print(..., flush=True)`** や Flet/バックエンドのログを残す。Web の FilePicker は **`Picker attached` ログだけでは不十分**な場合があり、`page.web` の分岐を常に意識する。
- バックエンド単体: `python src/api/main.py`、フロント単体: `flet run` または `python main_app.py`。
- **画像パスに日本語やスペースが含まれる**と `cv2.imread` が `None` を返すことがある。`src/utils/cv2_path.py` の `imread_bgr` / `imread_grayscale`（`read_bytes` + `imdecode`、必要時 **Pillow**）を使う。ROI 画面では `Path.is_file()` の**事前**チェックをしない（`d967a9d` で入れた条件が原因で、以前と比べ失敗しやすくなっていた例がある）。OneDrive オンラインのみは引き続き注意。
- **macOS `PermissionError` / `Operation not permitted`（exists は True、read_bytes だけ失敗）**: `Library/CloudStorage/.../OneDrive` 等で、**TCC により Python／ターミナルに読取権限がない**と発生。コード変更だけでは解消しない。**システム設定 → プライバシーとセキュリティ → フルディスクアクセス**（または**ファイルとフォルダ**）で、**実際に起動に使ったアプリ**（`Terminal.app` / `iTerm` / `Cursor` / `python` 等）を追加する。午前に動いて午後に失敗する場合は、**起動元ターミナルが違う**、設定変更後の再起動、が典型。代替: 画像を `uploads/` 等プロジェクト下へコピーして指定。

---

## 8. セキュリティ

- **`DEV_MODE=1` は研究・本番では使わない**（ログイン無効化とモック注入）。手順書に載せる場合は「開発専用」と明記済み（USER_MANUAL）。

---

## 9. 参考リンク

- [Flet FilePicker ドキュメント](https://flet.dev/docs/services/filepicker/)（Web 制限の記述あり）
- 利用者向け: **[USER_MANUAL.md](USER_MANUAL.md)**

---

## 10. macOS 配布ビルド（v1.2.4 以降）

| 項目 | 内容 |
|------|------|
| ビルド | `./build_mac.sh --skip-notarize --arm64`（Apple Silicon）または `--intel`（**x86_64 Python 3.9**） |
| pip メタデータ | `collect_all` の `*.dist-info` / `*.egg-info` を spec で除外し、ビルド後 `tools/strip_mac_codesign_poison.sh` |
| codesign 検証 | `tools/verify_mac_codesign_ready.sh` — Frameworks に dist-info が無いこと + `codesign --verify` |
| アーキ検証 | `tools/verify_mac_app_arch.sh dist/ARIAKE_OCTA.app arm64`（または `x86_64`）。fat/universal や逆アーキ混入で **fail** |
| venv 検証 | `tools/require_mac_python_arch.sh .venv/bin/python x86_64` — `--intel` 前に必須 |
| ZIP 同梱 | `./package_mac_release.sh --arm64 --version 1.2.4` → `dist/ARIAKE_OCTA_mac.zip` |
| Intel ZIP | `./package_mac_release.sh --intel --version 1.2.4` → `dist/ARIAKE_OCTA_macOS_Intel_v1.2.4.zip` |
| CI | `.github/workflows/build-mac.yml`（`v*-mac` タグ = arm64 / `workflow_dispatch` x86_64 = **macos-15-intel**） |
| 署名 | 研究配布は ad-hoc（`-`）。**Hardened Runtime を付けない**（Connection Error 防止） |
| インストール | 同梱 `インストール.command` が xattr + ad-hoc 再署名を実行 |
| 公証 | 研究配布は不要（`--skip-notarize`） |

**v1.2.3-mac の既知問題（v1.2.4 で修正）:**

1. **起動前 SIGKILL（前原型）:** `Contents/Frameworks/*.dist-info`（例: `fastapi-0.110.0.dist-info`）が codesign `--deep` を壊し、署名無効のまま CODESIGNING Invalid Page。既インストールなら `v1.2.3_Mac再署名.command`。新配布は v1.2.4 ZIP。
2. **ログイン後 Connection Error（瀧澤型・Intel 木住野型）:** Hardened Runtime + multiprocessing spawn（PR #43 で thread 起動・HR なし ad-hoc）。**新しい zip が必要**（再署名だけでは足りない）。

アーキ混在は **なし**（v1.2.3-mac arm64: 624 本 / x86_64 0）。flet-macos.tar.gz 内 Flet.app は universal2（正常）。

Linux のクラウドエージェントでは `.app` を作れない。Intel zip は **ローカル Mac** か **GitHub Actions `macos-15-intel`**。

### 10.1 Intel v1.2.4 zip（木住野先生向け）

成果物: `dist/ARIAKE_OCTA_macOS_Intel_v1.2.4.zip`。前提: `main` 最新（#43/#44/#45/#47 以降）。公証不要。

venv も PyInstaller も **すべて x86_64 Python 3.9**。arm64 の Homebrew Python だと Intel zip にならない（`IncompatibleBinaryArchError` / `verify_mac_app_arch` で arm64 検出）。

#### A. Intel Mac（MacBook Pro 2020 など）

```bash
# python.org の macOS 64-bit Python 3.9（/usr/local/bin/python3.9 等）
file "$(which python3.9)"    # → Mach-O 64-bit x86_64

git pull origin main
python3.9 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt -r requirements-build.txt

chmod +x build_mac.sh package_mac_release.sh tools/*.sh
./build_mac.sh --skip-notarize --clean --intel
./package_mac_release.sh --intel --version 1.2.4

tools/verify_mac_app_arch.sh dist/ARIAKE_OCTA.app x86_64
ls -lh dist/ARIAKE_OCTA_macOS_Intel_v1.2.4.zip
```

#### B. Apple Silicon（M1/M2/M3）— Rosetta + Intel Python 3.9

```bash
softwareupdate --install-rosetta --agree-to-license   # 初回のみ
# python.org 3.9.x macOS 64-bit Intel インストーラを Rosetta 下で:
#   arch -x86_64 installer -pkg ~/Downloads/python-3.9.*-macos11.pkg -target /
file /usr/local/bin/python3.9   # x86_64 であること

cd MNV_analysis_pro
git pull origin main
rm -rf .venv-intel
arch -x86_64 /usr/local/bin/python3.9 -m venv .venv-intel
arch -x86_64 .venv-intel/bin/pip install -U pip
arch -x86_64 .venv-intel/bin/pip install -r requirements.txt -r requirements-build.txt

mv .venv .venv-arm64 2>/dev/null || true
ln -sfn .venv-intel .venv   # build_mac.sh は .venv を参照する

chmod +x build_mac.sh package_mac_release.sh tools/*.sh
arch -x86_64 ./build_mac.sh --skip-notarize --clean --intel
arch -x86_64 ./package_mac_release.sh --intel --version 1.2.4
arch -x86_64 ./tools/verify_mac_app_arch.sh dist/ARIAKE_OCTA.app x86_64
file dist/ARIAKE_OCTA.app/Contents/MacOS/ARIAKE_OCTA   # x86_64

# arm64 用 venv を戻す（任意）
rm .venv
mv .venv-arm64 .venv 2>/dev/null || ln -sfn .venv-intel .venv
```

所要時間の目安: pip 初回 5〜15 分 + PyInstaller/codesign 10〜25 分（合計 20〜40 分）。M1+Rosetta は Intel 実機より遅いことが多い。

#### C. GitHub Actions（macos-15-intel）

Actions → **Build macOS release** → Run workflow:

| 入力 | 値 |
|------|-----|
| Branch | `main`（本変更マージ後）またはこの PR ブランチ |
| `target_arch` | **x86_64** |
| `app_version` | `1.2.4` |
| `attach_to_release` | true（既存 `v1.2.4-mac` に asset 追加。tag 打ち直し不要） |

`macos-14` で `x86_64` を選ぶと失敗する（arm64 Python）。

#### 失敗しやすい点

| 症状 | 原因 |
|------|------|
| `IncompatibleBinaryArchError` | venv が arm64 のまま `--intel` した |
| `verify_mac_app_arch` で arm64 検出 | 同上 |
| codesign `fastapi-*.dist-info` | 古い main。`git pull` で #44 以降を確認 |
| Intel Mac で `incorrect executable format` | arm64 zip を送った |

配布: `open dist/` → `ARIAKE_OCTA_macOS_Intel_v1.2.4.zip`。木住野先生向けは右クリック →「開く」で `インストール.command`。

---

*本書はリポジトリ内の慣行を反映したもので、大規模リファクタの際は更新してください。*

ローカルに **`DEVELOPMENT_RULES.md`**（UI ガードレールのみの旧メモ）がある場合、**§6 と重複する内容は本書を正**とし、整理・削除してかまいません。
