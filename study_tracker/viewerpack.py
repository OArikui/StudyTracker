"""ViewerPack discovery and safe extraction helpers."""

from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

MANUAL_URL = "https://github.com/OArikui/StudyTracker/blob/main/README.md#viewerpack-の導入"


def _is_viewer_package(path: Path) -> bool:
    return path.is_dir() and (path / "app.py").is_file() and (
        (path / "__init__.py").is_file() or (path / "app.py").is_file()
    )


def resolve_viewer_package_parent(folder: str | Path) -> Path:
    """Resolve a selected extraction/clone folder to the parent of viewer_v0/."""
    selected = Path(folder).expanduser().resolve()
    if not selected.is_dir():
        raise FileNotFoundError(
            f"展開済みViewerフォルダが見つかりません: {selected}\n"
            f"READMEの導入手順を確認してください: {MANUAL_URL}"
        )

    candidates: set[Path] = set()
    if selected.name == "viewer_v0" and _is_viewer_package(selected):
        candidates.add(selected)
    child = selected / "viewer_v0"
    if _is_viewer_package(child):
        candidates.add(child)

    # Support GitHub's tag-source ZIP layout, which adds wrapper directories.
    if not candidates:
        for app_file in selected.glob("*/viewer_v0/app.py"):
            package = app_file.parent
            if _is_viewer_package(package):
                candidates.add(package)
        for app_file in selected.glob("*/*/viewer_v0/app.py"):
            package = app_file.parent
            if _is_viewer_package(package):
                candidates.add(package)
        for app_file in selected.glob("*/*/*/viewer_v0/app.py"):
            package = app_file.parent
            if _is_viewer_package(package):
                candidates.add(package)

    if len(candidates) != 1:
        reason = "ViewerPack内の viewer_v0/app.py を特定できません。" if not candidates else (
            "ViewerPack候補が複数あります。viewer_v0 を含むフォルダを直接指定してください。"
        )
        raise ValueError(f"{reason}\n選択先: {selected}\nREADME: {MANUAL_URL}")
    return next(iter(candidates)).parent


def _archive_package_prefix(archive: zipfile.ZipFile) -> tuple[str, ...]:
    prefixes: set[tuple[str, ...]] = set()
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        parts = PurePosixPath(name).parts
        for index, part in enumerate(parts):
            if part == "viewer_v0" and index + 1 < len(parts) and parts[index + 1] == "app.py":
                prefixes.add(tuple(parts[:index]))
    if len(prefixes) != 1:
        reason = "ViewerPack ZIP内に viewer_v0/app.py がありません。" if not prefixes else (
            "ZIP内に複数の viewer_v0 パッケージがあります。公式タグの ZIP を選択してください。"
        )
        raise ValueError(f"{reason}\nREADME: {MANUAL_URL}")
    return next(iter(prefixes))


def extract_viewer_archive(zip_path: str | Path, destination: str | Path) -> Path:
    """Safely extract a ViewerPack and return the parent of its viewer_v0 package."""
    source = Path(zip_path).expanduser().resolve()
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise FileNotFoundError(
            f"ViewerPack ZIPが見つからないか、ZIP形式ではありません: {source}\n"
            f"READMEの導入手順を確認してください: {MANUAL_URL}"
        )
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source) as archive:
        prefix = _archive_package_prefix(archive)
        for info in archive.infolist():
            raw_name = info.filename.replace("\\", "/")
            pure = PurePosixPath(raw_name)
            parts = pure.parts
            mode = info.external_attr >> 16
            if (
                pure.is_absolute()
                or not parts
                or ".." in parts
                or any(":" in part for part in parts)
                or raw_name.startswith("//")
                or stat.S_ISLNK(mode)
            ):
                raise ValueError(
                    f"ZIP内に安全でないパスがあります: {info.filename}\nREADME: {MANUAL_URL}"
                )
            target = root.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source_file, target.open("wb") as target_file:
                shutil.copyfileobj(source_file, target_file)

    package = root.joinpath(*prefix, "viewer_v0")
    if not _is_viewer_package(package):
        raise ValueError(
            f"ViewerPackを展開しましたが viewer_v0/app.py が見つかりません: {package}\n"
            f"README: {MANUAL_URL}"
        )
    return package.parent
