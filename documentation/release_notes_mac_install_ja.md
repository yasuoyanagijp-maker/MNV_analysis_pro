<!-- Shared Mac install block for GitHub Releases (v1.2.4+). Edit here, then sync release bodies. -->

## インストール（通常）

1. お使いの Mac に合う ZIP をダウンロードする（**Apple M 系 → `ARIAKE_OCTA_mac*.zip`／Intel → `ARIAKE_OCTA_macOS_Intel_*.zip`**。チップが違う ZIP では起動しません）。
2. ZIP をダブルクリックで展開する。
3. 展開フォルダ内の **`インストール.command`** を **右クリック →「開く」** で実行する（初回はダブルクリックだけだと macOS に止められることがあります）。
4. 画面の案内どおり `/Applications` へ入れ、起動する。

ブロックされた場合: **システム設定 → プライバシーとセキュリティ** の **「このまま開く」** も試してください。

## 手順B（ターミナル・うまくいかない場合）

`インストール.command` が開けない／「予期しない理由で終了」／ログイン前に落ちる場合は、展開フォルダで **次を一行ずつ** 実行してください（`cd` のパスは展開場所に合わせる。例はデスクトップ）。

```bash
cd ~/Desktop/ARIAKE_OCTA_mac_vVERSION
xattr -cr .
bash mac_adhoc_codesign.sh sign ARIAKE_OCTA.app
rm -rf /Applications/ARIAKE_OCTA.app
cp -R ARIAKE_OCTA.app /Applications/
bash mac_adhoc_codesign.sh sign /Applications/ARIAKE_OCTA.app
open /Applications/ARIAKE_OCTA.app
```

- `mac_adhoc_codesign.sh` は **この Mac 向けのアドホック再署名** です（Apple 公証は不要）。`shapely/.dylibs` を先に直してから署名します。ZIP に同梱されていない古い版では `codesign --force --deep --sign -` を使いますが、**`--deep` だけを繰り返さないでください**。
- パスワードを聞かれたら **Mac のログインパスワード** です（アプリの `ariake2024` ではありません）。
- 上記は **xattr →（補助スクリプトで）再署名 → コピー → 再署名 → 起動** の順です。

## ログインで「Connection Error: All connection attempts failed」

パスワードや施設コードの入力ミスではありません。同じ Mac 内の解析エンジンに届いていない状態です。

- **v1.2.4d 以降**: 上記手順Bの **`mac_adhoc_codesign.sh sign`** を `/Applications/ARIAKE_OCTA.app` に対して実行し、再起動。または **`インストール.command` をもう一度** 右クリック →「開く」で上書き。
- **v1.2.4 / v1.2.4b / v1.2.4c**: `xattr -cr` のあと `codesign --force --deep --sign -`（`bundle format unrecognized` なら v1.2.4d へ入れ替え）。
- **v1.2.3-mac のみ**: ログイン後 Connection Error は既知不具合です。**v1.2.4d-mac へ入れ替え** を推奨します。
