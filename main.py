from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from study_tracker.viewerpack import (
    MANUAL_URL,
    extract_viewer_archive,
    resolve_viewer_package_parent,
)


def _launch_viewer(zip_path: str | None, folder_path: str | None = None) -> int:
    from study_tracker.paths import (
        get_db_path,
        get_viewer_folder_path,
        get_viewer_pack_path,
    )

    db_path = get_db_path().expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError(
            f"StudyTracker本体の設定DBが見つかりません: {db_path}\n"
            f"まずStudyTracker本体を起動してください。導入手順: {MANUAL_URL}"
        )

    selected_folder = (
        Path(folder_path).expanduser()
        if folder_path
        else get_viewer_folder_path()
    )
    selected_zip = Path(zip_path).expanduser() if zip_path else get_viewer_pack_path()

    temp = None
    if selected_folder is not None and str(selected_folder).strip():
        package_parent = resolve_viewer_package_parent(selected_folder)
    else:
        if not selected_zip.is_file():
            raise FileNotFoundError(
                f"ViewerPack ZIPが見つかりません: {selected_zip}\n"
                "設定 > 使用ディレクトリ・ViewerPack設定 で ZIP または展開済みフォルダを指定してください。\n"
                f"導入手順: {MANUAL_URL}"
            )
        temp = tempfile.TemporaryDirectory(prefix="studytracker_viewerpack_")
        try:
            package_parent = extract_viewer_archive(selected_zip, temp.name)
        except Exception:
            temp.cleanup()
            raise

    sys.path.insert(0, str(package_parent))
    try:
        # The Viewer uses the shared DB path resolved by StudyTracker.
        sys.argv = [sys.argv[0]]
        from viewer_v0.app import run

        return run(database_path=db_path)
    finally:
        try:
            sys.path.remove(str(package_parent))
        except ValueError:
            pass
        # Avoid retaining imports whose source lived in a temporary directory.
        for module_name in tuple(sys.modules):
            if module_name == "viewer_v0" or module_name.startswith("viewer_v0."):
                sys.modules.pop(module_name, None)
        if temp is not None:
            temp.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="StudyTracker")
    parser.add_argument("--viewer", action="store_true", help="設定済みViewerPackを起動")
    parser.add_argument("--viewer-zip", help="ViewerPack ZIPのパスを指定して起動")
    parser.add_argument("--viewer-folder", help="展開済みViewerPackフォルダのパスを指定して起動")
    args = parser.parse_args()
    if args.viewer or args.viewer_zip or args.viewer_folder:
        try:
            return _launch_viewer(args.viewer_zip, args.viewer_folder)
        except Exception as exc:
            print(f"Viewerを起動できませんでした: {exc}\n導入マニュアル: {MANUAL_URL}", file=sys.stderr)
            return 2
    from study_tracker.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
