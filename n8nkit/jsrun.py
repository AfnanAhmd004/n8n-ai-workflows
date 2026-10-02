"""Run a Code node's JavaScript under Node.js with mocked n8n globals (for tests)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .builder import load_js

HARNESS = Path(__file__).resolve().parent.parent / "tests" / "js" / "harness.mjs"


def node_available() -> bool:
    return shutil.which("node") is not None


def run_code(src: str, input: list[dict], nodes: dict | None = None, static: dict | None = None) -> dict:
    req = {"code": load_js(src), "input": input, "nodes": nodes or {}, "static": static or {}}
    proc = subprocess.run(["node", str(HARNESS)], input=json.dumps(req), capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)
