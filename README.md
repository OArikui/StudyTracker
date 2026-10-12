# StudyTracker

StudyTracker 本体と、外部 ViewerPack を利用する Python / PySide6 アプリです。

## 起動

```powershell
python -m pip install -r requirements.txt
python .\\main.py
```

Viewer を起動する場合:

```powershell
python .\\main.py --viewer
python .\\main.py --viewer-zip E:\\path\\StudyTrackerViewerPack_v0.8.1-StudyViewer.zip
```

`--viewer-zip` は追加パッケージ ZIP のパスを検証し、ZIP 内の Viewer を一時ディレクトリに展開して起動します。Viewer は StudyTracker 本体の `%APPDATA%/StudyTracker/config.json` の `db_path` に完全に従います。

## 保存形式

SQLite のテーブル構造、`segments.row_json` の正規キー、日時形式、互換キー、バックアップ方法は [保存形式リファレンス](docs/保存形式リファレンス.md) を参照してください。

## バージョン

StudyTracker 本体: **3.4.0** / 外部 ViewerPack: **0.8.1**


## プリセット登録の注意

学習単位エイリアスは、**Docstringが空欄のままでは登録できません**。各エイリアスの意味を Docstring に記入してください。


## 使用ディレクトリと ViewerPack

「設定」→「使用ディレクトリ・ViewerPack設定」で、SQLite DB、ログ、エクスポート先、ViewerPackPath を確認・変更できます。アプリ本体のルートは実行場所に固定ですが、設定ディレクトリも含め、DB・ログ・エクスポート先・ViewerPackPath を編集できます。設定ディレクトリを移動しても、標準の設定場所にブートストラップ設定を残して次回起動時に追跡します。

ViewerPack は StudyTracker 本体とは別 ZIP です。既定パスは StudyTracker root の `StudyTrackerViewerPack_v0.8.1-StudyViewer.zip` です。命名形式は `StudyTrackerViewerPack_vx.x.x-<description>.zip` とし、ZIP 内に `viewer_v0/` が含まれることが必要です。

```powershell
python .\main.py --viewer
python .\main.py --viewer-zip "E:\path\StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
```

Viewer は StudyTracker 本体の設定 `db_path` を読み取り、独自の DB パス設定を使用しません。ViewerPack は起動時に一時ディレクトリへ展開され、StudyTracker 配布 ZIP には `viewer_v0/` を含めません。


### DBパスの設定

DBパスの変更入口は「設定」→「使用ディレクトリ・ViewerPack設定」の「SQLiteデータベース」に一本化しました。旧「データ保存場所」メニューは廃止しています。ViewerPack 側には独立した DB 選択・設定を持たせず、本体が解決した `db_path` を起動引数として渡します。


## Windowsメディア操作

「設定」→「Windowsメディア操作」で任意に有効化できます。再生/一時停止、前後のメディア、システム音量操作、グローバルショートカット、優先メディアセッションの選択に対応します。学習中はメディア情報の変化を既存の events テーブルへ記録します。詳細は [Windows メディア操作](docs/windows-media-operations.md) を参照してください。

メディア情報の列挙・セッション指定操作を使う場合は、任意依存関係をインストールしてください。

```powershell
python -m pip install -e ".[windows-media]"
```

任意依存関係をインストールしない場合、標準Windowsメディアキーによる操作は利用できますが、GSMTCメタデータ取得は無効になります。
