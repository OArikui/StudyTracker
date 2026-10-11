# versionDiff.md

## v3.3.2 — 2026-10-11

### 修正
- Viewer の起動時に本体が渡す `database_path` を `run()` と `ViewerWindow` が受け取るよう修正し、`TypeError: unexpected keyword argument` を解消。
- ViewerPack から独立 DB 設定ファイル・DB 選択ボタンを除去し、StudyTracker 本体の `db_path` だけを DB の参照元に統一。
- 重複していた「データ保存場所」メニューとダイアログを廃止し、DB パス編集を「使用ディレクトリ・ViewerPack設定」に一本化。
- ViewerPack を 0.8.1 に更新し、既定 ZIP 名を `StudyTrackerViewerPack_v0.8.1-StudyViewer.zip` に更新。
- Viewer 起動契約と重複設定撤去のテストを追加。

StudyTracker のバージョンごとの変更点を記録します。

## v3.3.1 — 2026-10-11

### 追加・変更
- 「使用ディレクトリ・ViewerPack設定」画面を追加し、DB、ログ、エクスポート先、ViewerPackPath を一括確認・編集可能にした。
- ViewerPackPath の既定値を StudyTracker root 配下の `StudyTrackerViewerPack_v0.8.0-StudyViewer.zip` に設定。
- `--viewer` は設定済み ViewerPackPath を、`--viewer-zip` は明示指定 ZIP を起動するように変更。
- ViewerPack は一時ディレクトリに展開し、StudyTracker 本体の DB 設定を渡して起動する。
- StudyTracker 本体 ZIP から `viewer_v0/` と旧内蔵 Viewer 実装を除外し、ViewerPack を別 ZIP に分離。
- ログと CSV/XLSX 出力の既定先を設定画面のパス設定に連動。
- パス設定・ViewerPackPath のテストを追加。

### 検証
- Python compileall 成功。
- pytest: 26件成功。

## v3.2.1 — 2026-10-11

### 修正
- Active/Passiveの切替時に学習中画面を再生成しないように変更。
- 入力途中のタイムスタンプ位置が切替操作でリセットされず、再びActiveにしたときも入力欄に残るように修正。
- 切替後も状態ボタン・タイムスタンプ入力欄の有効状態・スリープ抑止・時計と履歴表示が現在の状態に同期するように変更。

### 変更しない動作
- Active/Passiveの切替時に学習区間を保存する動作は維持。
- 既に保存されたタイムスタンプとタイムスタンプ履歴は変更・削除しない。
- Passive中はタイムスタンプ入力欄を無効化し、記録を受け付けない。

## v3.2.0 — 2026-10-11

- 学習時間表示の大型化、全画面表示、今日の学習区間を示すアナログ時計を追加。
- タイムスタンプ入力欄と履歴を左右分割し、予定範囲外・実施済み位置の警告と予定範囲完了時のセクション終了を追加。
- 未登録プリセットのクイック登録、入力保持による修正・再試行、エラーバナーとログエクスポートを追加。


## v3.2.2 — 2026-10-11

### 修正
- `QIntValidator` を `PySide6.QtGui` からインポートするよう変更。これにより `PySide6.QtWidgets` に存在しない名前を読み込んで起動時に失敗する問題を修正。
- `VERSION`、`pyproject.toml`、`study_tracker/__init__.py`、画面タイトル、README を `3.2.2` に更新。
