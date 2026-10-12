from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from study_tracker.viewerpack import extract_viewer_archive, resolve_viewer_package_parent


def _make_pack(path: Path, *, unsafe_member: str | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("StudyTracker-ViewerPack-0.8.1/source/viewer_v0/__init__.py", "")
        archive.writestr(
            "StudyTracker-ViewerPack-0.8.1/source/viewer_v0/app.py",
            "def run(database_path=None):\n    return 0\n",
        )
        if unsafe_member:
            archive.writestr(unsafe_member, "unsafe")


def test_extracts_nested_github_tag_zip(tmp_path: Path) -> None:
    pack = tmp_path / "viewerpack.zip"
    output = tmp_path / "unpacked"
    _make_pack(pack)

    package_parent = extract_viewer_archive(pack, output)

    assert package_parent == output / "StudyTracker-ViewerPack-0.8.1" / "source"
    assert (package_parent / "viewer_v0" / "app.py").is_file()
    assert resolve_viewer_package_parent(output / "StudyTracker-ViewerPack-0.8.1") == package_parent
    assert resolve_viewer_package_parent(package_parent / "viewer_v0") == package_parent


def test_rejects_zip_path_traversal(tmp_path: Path) -> None:
    pack = tmp_path / "unsafe.zip"
    output = tmp_path / "unpacked"
    _make_pack(pack, unsafe_member="../escaped.txt")

    with pytest.raises(ValueError, match="安全でないパス"):
        extract_viewer_archive(pack, output)

    assert not (tmp_path / "escaped.txt").exists()
