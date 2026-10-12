# StudyTracker

StudyTracker 本体と、外部 ViewerPack を利用する Python / PySide6 アプリです。

## 起動

```powershell
python -m pip install -r requirements.txt
python .\\main.py
```

パッケージとして編集可能インストールする場合（Windowsメディア情報取得の追加依存関係を含む）:

```powershell
python -m pip install -e ".[windows-media]"
```

プロジェクトのパッケージ設定では `study_tracker` のみを配布対象にし、実行時データ用の `user_data` はパッケージ探索から除外しています。

Viewer を起動する場合:

```powershell
python .\\main.py --viewer
python .\\main.py --viewer-zip E:\\path\\StudyTrackerViewerPack_v0.8.1-StudyViewer.zip
python .\\main.py --viewer-folder E:\\path\\extracted-viewer-pack
```

`--viewer-zip` は追加パッケージ ZIP のパスを検証し、ZIP 内の Viewer を一時ディレクトリに展開して起動します。Viewer は StudyTracker 本体の `%APPDATA%/StudyTracker/config.json` の `db_path` に完全に従います。

## 保存形式

SQLite のテーブル構造、`segments.row_json` の正規キー、日時形式、互換キー、バックアップ方法は [保存形式リファレンス](docs/保存形式リファレンス.md) を参照してください。

## バージョン

StudyTracker 本体: **3.5.7** / 外部 ViewerPack: **0.8.1**

学習中の時計表示は「日本標準時」「カレント勉強時間」「合計勉強時間」から選択できます。待機画面では学習内容とスタンプ入力・履歴を中央にまとめて余白を抑え、アナログ時計とスリープ防止のチェックボックスを隣接配置しています。状態ボタンの色で ACTIVE / PASSIVE を確認できます。全画面表示ではスタンプ入力欄と再生状態を確認でき、暗転中は時計モード選択欄を含む全UIを隠します。


## プリセット登録の注意

学習単位エイリアスは、**Docstringが空欄のままでは登録できません**。各エイリアスの意味を Docstring に記入してください。


## 使用ディレクトリと ViewerPack

「設定」→「使用ディレクトリ・ViewerPack設定」で、SQLite DB、ログ、エクスポート先、ViewerPackPath を確認・変更できます。アプリ本体のルートは実行場所に固定ですが、設定ディレクトリも含め、DB・ログ・エクスポート先・ViewerPackPath を編集できます。設定ディレクトリを移動しても、標準の設定場所にブートストラップ設定を残して次回起動時に追跡します。

ViewerPack は StudyTracker 本体とは別の追加パッケージです。既定のZIPパスは `user_data/packages/StudyTrackerViewerPack_v0.8.1-StudyViewer.zip` です。命名形式は `StudyTrackerViewerPack_vx.x.x-<description>.zip` を推奨します。GitHubのタグZIPでは `viewer_v0/` がラッパーディレクトリの下に入りますが、入れ子の階層を自動検出します。ZIPの代わりに展開済みフォルダを指定することもできます。

```powershell
python .\main.py --viewer
python .\main.py --viewer-zip "E:\path\StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
```

Viewer は StudyTracker 本体の設定 `db_path` を読み取り、独自の DB パス設定を使用しません。ZIP版のViewerPackは起動時に一時ディレクトリへ展開されます。展開済みフォルダを設定した場合は直接読み込むため、高速に起動できます。StudyTracker本体の配布物には `viewer_v0/` を含めません。


### ViewerPack の導入

1. [ViewerPack ブランチ](https://github.com/OArikui/StudyTracker/tree/ViewerPack)を開き、利用するバージョンのタグを選びます。
2. タグページから **Source code (zip)** をダウンロードします。ZIPは user_data/packages/ に置くか、「設定」→「使用ディレクトリ・ViewerPack設定」で保存先を指定します。
3. GitHubのソースZIPはリポジトリ名などのフォルダが追加され、viewer_v0/ がZIP直下にない構造になります。本体はこの入れ子を自動認識します。
4. すでに展開している場合は同じ設定画面で「展開済みViewerPackフォルダ」を指定できます。cloneしたリポジトリ内のフォルダも指定できます。
5. 「ツール」→「学習記録ビューアー」から起動します。ViewerPackの形式や場所に問題がある場合は、表示されるリンクからこの手順を確認してください。

コマンドから起動する場合:

```powershell
python .\\main.py --viewer
python .\\main.py --viewer-zip "E:\\path\\StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
python .\\main.py --viewer-folder "E:\\path\\extracted-viewer-pack"
```

### user_data とバックアップ

既定ではStudyTrackerルートの user_data/ に config/（設定）、records/（SQLite学習記録）、logs/（ログ）、exports/（エクスポート）、packages/（追加パッケージ）を作成します。このディレクトリはGit管理対象外です。設定画面から各保存先は個別に変更できます。設定ディレクトリを移動した場合に備え、起動時の設定位置を追跡するため %APPDATA%/StudyTracker/config.json にブートストラップ用コピーを保持します。

ログはアプリの起動ごとに study_tracker_YYYYMMDD_HHMMSS.log 形式で新規作成され、以前の起動ログを上書きしません。定期バックアップの保存先は user_data/ や元のDBと異なる場所、できれば別ドライブを指定してください。

### バックアップ / エクスポートの読み込み

「ツール」→「バックアップ / エクスポートを読み込む」からSQLiteバックアップ（.sqlite3 / .db / .sqlite）、CSV、XLSXを読み込めます。

- SQLiteバックアップの復元では、現在のDBを別名のバックアップとして保存してから置き換えます。復元確認ダイアログに表示される保存先を確認してください。
- CSV/XLSXは既存データを置き換えず、読み込み可能な学習記録を追加します。XLSX内の「学習単位エイリアス」シートも重複を避けて取り込みます。
- 開始時刻・終了時刻が未設定または不正な行は、誤った時刻を作らず読み飛ばし、結果ダイアログに理由を表示します。

### カレント学習内容を編集・適用する

編集画面の「同期して適用」は、最後に編集したテキストまたはテーブルをもう一方へ同期し、検証に通った内容を適用します。未登録プリセットがある場合は「未登録プリセットをクイック登録」から登録できます。学習単位エイリアスには説明（Docstring）が必要です。

### DBパスの設定

DBパスの変更入口は「設定」→「使用ディレクトリ・ViewerPack設定」の「SQLiteデータベース」に一本化しました。旧「データ保存場所」メニューは廃止しています。ViewerPack 側には独立した DB 選択・設定を持たせず、本体が解決した `db_path` を起動引数として渡します。


## Windowsメディア操作

「設定」→「Windowsメディア操作」で任意に有効化できます。再生/一時停止、前後のメディア、システム音量操作、グローバルショートカット、優先メディアセッションの選択に対応します。学習中はメディア情報の変化を既存の events テーブルへ記録します。詳細は [Windows メディア操作](docs/windows-media-operations.md) を参照してください。

メディア情報の列挙・セッション指定操作を使う場合は、任意依存関係をインストールしてください。

```powershell
python -m pip install -e ".[windows-media]"
```

任意依存関係をインストールしない場合、標準Windowsメディアキーによる操作は利用できますが、GSMTCメタデータ取得は無効になります。


## 全画面時計・タイマー・メディア操作

メインの学習画面はデジタル時計を標準表示し、Current（カレント学習時間）とTotal（選択中の科目・教材の累計時間）を同時に表示します。全画面表示ボタンは中央にあります。アナログ時計を表示する場合はチェックボックスで切り替えられ、文字盤は5分単位の目盛りです。

学習中の「全画面表示」では、画面中央にデジタル時計を大きく表示します。下部にWindowsメディアの再生／一時停止・前後移動と再生位置バーを配置します。対応するWindowsメディアセッションでは、バーをドラッグして再生位置を変更できます。画面内のタイマーは分単位で設定でき、一時停止・再開・リセットに対応します。全画面中も「スタンプ」から学習位置を記録できます。メディア操作ボタンのラベルは操作内容を優先して表示し、再生状態は色とツールチップで区別します。履歴はポップアップ内の「履歴を表示」で必要なときだけ表示され、ポップアップ外をクリックすると閉じます。全画面中は「画面を暗転」または **B** キーで表示を完全な黒にし、もう一度Bで戻せます。**Esc** キーで全画面表示を終了します。
