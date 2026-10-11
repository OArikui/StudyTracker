from __future__ import annotations

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def _launch_viewer(zip_path: str | None) -> int:
    from study_tracker.paths import get_db_path, get_viewer_pack_path
    db_path = get_db_path().expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"StudyTracker本体の設定DBが見つかりません: {db_path}")
    addon = Path(zip_path).expanduser().resolve() if zip_path else get_viewer_pack_path().expanduser().resolve()
    if not addon.is_file() or not zipfile.is_zipfile(addon):
        raise FileNotFoundError(
            f"ViewerPack ZIPが見つかりません: {addon}\n"
            "設定 > 使用ディレクトリ・ViewerPack設定 でViewerPackPathを指定してください。"
        )
    temp = tempfile.TemporaryDirectory(prefix="studytracker_viewerpack_")
    root = Path(temp.name).resolve()
    with zipfile.ZipFile(addon) as archive:
        names = archive.namelist()
        package_names = [n for n in names if n.startswith("viewer_v0/")]
        if not package_names:
            temp.cleanup()
            raise ValueError("ViewerPack ZIP内に viewer_v0/ パッケージがありません。")
        for name in names:
            item = PurePosixPath(name)
            if item.is_absolute() or ".." in item.parts:
                temp.cleanup()
                raise ValueError(f"ZIP内に安全でないパスがあります: {name}")
        archive.extractall(root)
    sys.path.insert(0, str(root))
    try:
        sys.argv = [sys.argv[0]]
        from viewer_v0.app import run
        return run(database_path=db_path)
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        temp.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="StudyTracker")
    parser.add_argument("--viewer", action="store_true", help="設定済みViewerPackを起動")
    parser.add_argument("--viewer-zip", help="ViewerPack ZIPのパスを指定して起動")
    args = parser.parse_args()
    if args.viewer or args.viewer_zip:
        return _launch_viewer(args.viewer_zip)
    from study_tracker.app import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
