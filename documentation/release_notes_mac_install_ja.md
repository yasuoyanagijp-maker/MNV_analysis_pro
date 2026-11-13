<!-- Shared Mac install block for GitHub Releases (v1.2.5). Edit here, then sync release bodies. -->

## インストール（macOS 15 Sequoia 以降。Intel / Apple Silicon 共通）

1. お使いの Mac に合う ZIP をダウンロードする（**Apple M 系 → `ARIAKE_OCTA_mac*.zip`／Intel → `ARIAKE_OCTA_macOS_Intel_*.zip`**。チップが違う ZIP では起動しません）。
2. ZIP をダブルクリックで展開する。`ARIAKE_OCTA.app` と `インストール.command` が同じフォルダにあることを確認する。
3. 次の（A）または（B）で **`インストール.command`** を実行する。macOS 15 以降は（A）が確実です。`cd` は不要です。

**【（A）ターミナル方式（推奨・確実）】**

1. ターミナルを開く。  
2. `xattr -cr ` と入力する（**末尾に半角スペース**。まだ Enter は押さない）。  
3. Finder の展開フォルダをターミナルへドラッグ＆ドロップし、Enter。  
4. Finder に戻り、`インストール.command` をダブルクリックする。

**【（B）システム設定方式】**

1. `インストール.command` を一度ダブルクリックする（ブロックされます）。  
2. システム設定 → プライバシーとセキュリティ。  
3. ページ下部の **「このまま開く」** → 確認の **「開く」** → Mac のログインパスワード。

**macOS 14 以前**は、右クリック →「開く」でも起動できます。macOS 15 以降ではこの方法だけでは開かないことがあります。

4. 画面の案内どおり `/Applications` へ入れ、起動する。

同梱の `Macインストール手順.txt` にも同じ内容があります。

## ログインで「Connection Error: All connection attempts failed」

パスワードや施設コードの入力ミスではありません。同じ Mac 内の解析エンジンに届いていない状態です。

- **v1.2.4d 以降 / v1.2.5:** 上記（A）のあと **`インストール.command` をもう一度**実行して上書き。または展開フォルダの **`mac_adhoc_codesign.sh sign`** を `/Applications/ARIAKE_OCTA.app` に対して実行し、再起動。`codesign --deep` だけを繰り返さないでください（`shapely/.dylibs` で `bundle format unrecognized` になります）。
- **v1.2.4 / v1.2.4b / v1.2.4c:** `xattr -cr` のあと `codesign --force --deep --sign -`（`bundle format unrecognized` なら v1.2.4d / v1.2.5 へ入れ替え）。
- **v1.2.3-mac のみ:** ログイン後 Connection Error は既知不具合です。**v1.2.5 へ入れ替え**を推奨します。
