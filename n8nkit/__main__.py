"""python -m n8nkit build   -> regenerate workflows/*.json from n8nkit/catalog.py and src/
python -m n8nkit check   -> validate workflows/*.json and fail if they are out of date
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .catalog import ALL
from .validate import validate

OUT = Path(__file__).resolve().parent.parent / "workflows"


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "check"
    OUT.mkdir(exist_ok=True)
    problems = 0
    for slug, make in ALL.items():
        wf = make()
        text = wf.to_json()
        path = OUT / f"{slug}.json"
        if cmd == "build":
            path.write_text(text)
        elif not path.exists() or path.read_text() != text:
            print(f"✗ {path.name}: out of date, run `python -m n8nkit build`")
            problems += 1
        errs = validate(json.loads(text))
        problems += len(errs)
        status = "✓" if not errs else "✗"
        print(f"{status} {path.name}: {len([n for n in wf.nodes])} nodes" + "".join(f"\n    - {e}" for e in errs))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
