from __future__ import annotations

import sys

from viewer_v0.app import run

if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except ValueError as exc:
        print(f"起動できません: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
