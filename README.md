# For those who say it doesn't work, try the following:  
1. Run as administrator  
2. Don't give up after a few seconds; patiently wait about a minute after starting
3. Try disconnecting the controller
# ダウンロードリンク↓
## https://github.com/ppkk12/fortnite-automatic-lap/releases/download/v1.1/pk-auto5AB.exe (japanese/english/Español/Português/Русский)Recommended
＊Español/Português/Русскийこの３つの言語は動作確認してません。失敗の確率を下げたいのならば英語or日本語を推奨。
↑最新
<img width="1535" height="954" alt="image" src="https://github.com/user-attachments/assets/8844c270-6ce9-4a8b-95bc-cffc1628dd9c" />



https://github.com/user-attachments/assets/6692b13e-a1b9-44f3-8854-81173c506594



# 昔のバージョンのダウンロードリンク↓

https://github.com/ppkk12/fortnite-automatic-lap/releases/tag/v1.0(5-languages)/pk-auto5.exe (japanese/english/Español/Português/Русский)
＊Español/Português/Русскийこの３つの言語は動作確認してません。失敗の確率を下げたいのならば英語or日本語を推奨。

https://github.com/ppkk12/fortnite-automatic-lap/releases/download/v1.0/pk-auto.exe (japanese)

https://github.com/ppkk12/fortnite-automatic-lap/releases/download/v1.0(english)/pk-auto.exe (japanese/english)

# fortnite-automatic-lap
自動でプレイやロビーに戻るを押させるツール

# これは何？
ロビーの「プレイ」→ マッチ中の「続行」→ 結果画面の「スキップ」→
「ロビーに戻る」を自動でクリックして、周回を繰り返すツールです。
画面を見てボタンを探してクリックしているだけで、ゲームの内部データ
には一切触れていません。

# 使い方
1. pk-auto.exe をダブルクリックして起動します（exe 単体で動きます。
   他のファイルは不要です）管理者で実行しないと正常に動かない場合あり。
2. Fortnite を起動し、ロビー画面を表示しておきます。
3. pk-auto のウィンドウで「開始」を押します。
4. 止めたいときは「停止」ボタンか、F8 キー。

# 設定について
- しきい値スライダー：ボタンの認識精度です。反応しないときは少し
  下げてみてください（誤作動が増える場合は上げてください）。
- 「マッチ中 WASD ランダム長押し」：オンにすると、マッチ中に
  W/A/S/D のいずれかをランダムに一定時間押し続けます。間隔と長押し
  秒数は画面上で変更できます。
- 画面サイズやUIが違ってボタンを認識しない場合は、「画像を切り抜く」
  ボタンでご自分の画面から撮り直せます（exe の横に assets フォルダが
  作られ、そちらが優先されます）。

# 注意事項（必ずお読みください）
- 自動操作ツールの使用は Fortnite の利用規約・不正対策（Easy
  Anti-Cheat など）に違反する可能性があり、アカウント停止の対象に
  なり得ます。使用は完全に自己責任でお願いします。
- 初回起動時、Windows の SmartScreen や一部のウイルス対策ソフトが
  「発行元不明」「不審なファイル」として警告を出すことがあります。
  これは、個人開発の未署名ソフトではよくあることで、マウス・
  キーボードの自動操作やホットキー監視の仕組みが、マクロ系ツールと
  似た挙動として検知されやすいためです。心配な方は、ご自身で
  nordvpnfilecheckerなどにファイルをアップロードして確認してから実行して
  ください。
- 本ツールは配布者・作者が動作を保証するものではありません。自己
  責任の上でご利用ください。

# 連絡先・不具合報告
X (Twitter): @4z5pk

## 構造
```text
pk-auto/
├── assets/                  # テンプレート画像リソース
├── src/                     # メインソースコード
├── tests/                   # テスト
├── tools/                   # 補助スクリプト・ツール
├── .gitignore
├── build_exe_protected.bat  # ビルドスクリプト
├── pk-auto.spec             # PyInstaller 設定
├── requirements.txt         # 依存パッケージ
└── README.md
```
