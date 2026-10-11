from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIALOGS = (ROOT / "study_tracker" / "dialogs.py").read_text(encoding="utf-8")


def test_material_uses_subject_parent():
    assert '"material": "subject"' in DIALOGS


def test_quick_register_does_not_autofill_alias_docstring():
    assert 'self.db.add_alias(value, value)' not in DIALOGS
    assert 'Docstringが空欄のままでは登録できません' in (ROOT / "README.md").read_text(encoding="utf-8")


def test_quick_register_requires_alias_docstring():
    assert 'if invalid_aliases:' in DIALOGS
    assert '"Docstringが必要です"' in DIALOGS


def test_dependent_sidebar_exists():
    assert 'self.parent_list = QListWidget()' in DIALOGS
    assert 'self.parent_list.currentItemChanged.connect(self._parent_changed)' in DIALOGS
    assert 'self.parent_edit_button = QPushButton("親を編集")' in DIALOGS
