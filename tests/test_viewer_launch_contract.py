from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_viewer_launch_passes_host_database_path() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run"
    ]
    assert any(
        any(keyword.arg == "database_path" for keyword in node.keywords)
        for node in calls
    )


def test_duplicate_data_location_menu_and_dialog_removed() -> None:
    ui_source = (ROOT / "study_tracker/ui.py").read_text(encoding="utf-8")
    dialogs_source = (ROOT / "study_tracker/dialogs.py").read_text(encoding="utf-8")
    assert 'settings.addAction("データ保存場所")' not in ui_source
    assert "def open_data_location(" not in ui_source
    assert "class DataLocationDialog" not in dialogs_source
    assert '"db_path", "SQLiteデータベース"' in dialogs_source


def test_viewer_pack_no_longer_has_own_database_config() -> None:
    project = ROOT.parent / "viewerpack"
    ui_source = (project / "viewer_v0/ui.py").read_text(encoding="utf-8")
    assert "from .config import load_config, save_config" not in ui_source
    assert 'save_config({"db_path": str(path)})' not in ui_source
    assert not (project / "viewer_v0/config.py").exists()


def test_viewer_run_accepts_database_path_keyword() -> None:
    project = ROOT.parent / "viewerpack"
    source = (project / "viewer_v0/app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    run = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    assert any(arg.arg == "database_path" for arg in run.args.args)


def test_viewer_window_requires_host_database_path() -> None:
    project = ROOT.parent / "viewerpack"
    source = (project / "viewer_v0/ui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    viewer_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ViewerWindow"
    )
    initializer = next(
        node for node in viewer_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assert any(arg.arg == "database_path" for arg in initializer.args.args)
