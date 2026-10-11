from __future__ import annotations
import argparse
import re
import shutil
import sqlite3
from pathlib import Path


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', s).strip().rstrip('.')
    return s or 'Subject'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--exe', required=True)
    ap.add_argument('--destination', required=True)
    args = ap.parse_args()

    exe = Path(args.exe)
    if not exe.exists():
        raise SystemExit(f'Executable not found: {exe}')
    con = sqlite3.connect(args.db)
    rows = con.execute("SELECT title FROM presets WHERE kind='subject' ORDER BY sort_order,id").fetchall()
    con.close()
    dest = Path(args.destination)
    dest.mkdir(parents=True, exist_ok=True)

    for (subject,) in rows:
        out = dest / f'StudyTracker - {safe_name(subject)}.exe'
        shutil.copy2(exe, out)
        print(out)

    if not rows:
        print('No subject presets found.')


if __name__ == '__main__':
    main()
