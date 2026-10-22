## Mac v1.2.4b

v1.2.4 に、起動ウィザードの **3 mm (Optovue)** と **3 mm (Zeiss HD)** を入れた版です。Mac の再署名が `shapely/.dylibs` で止まる問題も、インストール時に直します。アプリ一式の入れ替えです。

| ZIP | 対象 |
|-----|------|
| `ARIAKE_OCTA_mac_v1.2.4b.zip` | Apple Silicon（M1/M2/M3/M4） |
| `ARIAKE_OCTA_macOS_Intel_v1.2.4b.zip` | Intel Mac |

手順は次のとおりです。

1. ARIAKE OCTA を終了する。
2. お使いの Mac に合う ZIP をダブルクリックで解凍する。
3. 「インストール.command」を右クリック →「開く」。初回はダブルクリックだと macOS に止められることがあります。
4. Applications に古い ARIAKE OCTA があるときは、上書きの確認で Enter を押す。終わるとアプリが開きます。

ターミナルで `codesign --deep` だけを繰り返さないでください。`shapely/.dylibs` で `bundle format unrecognized` になります。

ボタンは起動ウィザードの Step 2 に出ます。数値の Image Scale (mm) 一覧の 3.0 は Zeiss HD のままです。

すでに v1.2.4 だけが入っていて、アプリ一式を入れ替えない場合は、これまでどおり `v1.2.4-optovue-3mm-patch` のパッチでも同じ画面を足せます。Windows（v1.2.3）はこの v1.2.4b の対象外です。
