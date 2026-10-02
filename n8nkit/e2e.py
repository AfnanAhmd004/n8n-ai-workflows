"""End-to-end check inside a real n8n instance, with external services stubbed.

Every trigger becomes a manual trigger followed by a fixture, and every node that
talks to the outside world (HTTP, Slack, email, webhook response) is replaced by a
Code node that returns a canned response. The workflow's own Code nodes, IF nodes,
expressions and wiring then run in n8n's real runtime.

    N8N_BIN=/path/to/node_modules/.bin/n8n python -m n8nkit.e2e
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .catalog import ALL

EXTERNAL = {"n8n-nodes-base.httpRequest", "n8n-nodes-base.slack", "n8n-nodes-base.emailSend",
            "n8n-nodes-base.respondToWebhook"}
TRIGGERS = {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.webhook"}


def _claude(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def fixtures() -> dict[str, dict[str, object]]:
    now = datetime.now(timezone.utc)
    iso = lambda h: (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    atom = ("<feed>" + "".join(
        f"<entry><id>http://arxiv.org/abs/{i}</id><published>{iso(i + 1)}</published><title>{t}</title>"
        f"<summary>{s}</summary><author><name>A. Author</name></author></entry>"
        for i, (t, s) in enumerate([("Robust LiDAR SLAM for drones", "robot slam lidar uav"),
                                    ("LLM agents for robot manipulation", "agent language model robot manipulat")]))
            + "</feed>")
    return {
        "research-digest": {
            "Fetch arXiv": {"data": atom},
            "Rank with Claude": _claude('[{"id": "http://arxiv.org/abs/0", "relevance": 9, "why": "field-ready SLAM"},'
                                        '{"id": "http://arxiv.org/abs/1", "relevance": 4, "why": "early"}]'),
        },
        "market-move-alert": {"Fetch price": {"symbol": "XAUUSD", "price": 2345.6, "ts": iso(0)}},
        "robot-fault-triage": {
            "Fault event": {"body": {"robot_id": "arm-07", "code": "E-217", "message": "nearly hit a person"}},
            "Draft work order (Claude)": _claude('{"priority": "low", "title": "Gearbox check", "steps": ["inspect"], '
                                                 '"parts": [], "safety_concern": false}'),
            "Create ticket": {"id": "WO-1001"},
        },
        "lead-qualification": {
            "Form submission": {"body": {"email": "cto@acme-aero.com", "name": "Sam", "role": "CTO",
                                         "message": "Drone inspection for our MRO hangar"}},
            "Qualify with Claude": _claude('{"score": 84, "segment": "aerospace", "reason": "clear use case", '
                                           '"next_step": "book demo"}'),
            "Create HubSpot contact": {"id": "c-1"},
        },
        "fleet-kpi-report": {
            "Fetch fleet events": {"robots": ["r1", "r2"], "events": [
                {"robot_id": "r1", "code": "E-217", "start": "2026-09-28T10:00:00Z", "end": "2026-09-28T14:00:00Z"},
                {"robot_id": "r2", "code": "E-310", "start": "2026-09-30T10:00:00Z", "end": "2026-09-30T16:00:00Z"}]},
            "Summarise with Claude": _claude("- Availability was 97% with 2 failures."),
        },
    }


def stubbed(slug: str) -> dict:
    wf = json.loads(ALL[slug]().to_json())
    fx = fixtures()[slug]
    out_nodes, extra = [], []
    for n in wf["nodes"]:
        if n["type"] in TRIGGERS:
            start = f"Start {n['name']}"
            extra.append({"parameters": {}, "id": str(uuid.uuid4()), "name": start, "type": "n8n-nodes-base.manualTrigger",
                          "typeVersion": 1, "position": [n["position"][0] - 200, n["position"][1]]})
            wf["connections"][start] = {"main": [[{"node": n["name"], "type": "main", "index": 0}]]}
            n = {**n, "type": "n8n-nodes-base.code", "typeVersion": 2,
                 "parameters": {"jsCode": f"return [{{ json: {json.dumps(fx.get(n['name'], {}))} }}];"}}
            n.pop("webhookId", None)
        elif n["type"] in EXTERNAL:
            body = (f"return $input.all().map(() => ({{ json: {json.dumps(fx[n['name']])} }}));" if n["name"] in fx
                    else "return $input.all();")
            n = {k: v for k, v in n.items() if k not in ("credentials", "retryOnFail", "maxTries", "waitBetweenTries")}
            n.update(type="n8n-nodes-base.code", typeVersion=2, parameters={"jsCode": body})
        out_nodes.append(n)
    wf["nodes"] = out_nodes + extra
    wf["name"] = f"[e2e] {wf['name']}"
    wf["id"] = uuid.uuid5(uuid.NAMESPACE_URL, slug).hex[:16]
    return wf


def run_all(n8n_bin: str) -> dict[str, dict]:
    home = tempfile.mkdtemp(prefix="n8n-e2e-")
    env = {**os.environ, "N8N_USER_FOLDER": home, "N8N_DIAGNOSTICS_ENABLED": "false"}
    results = {}
    for slug in ALL:
        wf = stubbed(slug)
        path = Path(home) / f"{slug}.json"
        path.write_text(json.dumps(wf))
        subprocess.run([n8n_bin, "import:workflow", f"--input={path}"], env=env, check=True, capture_output=True,
                       timeout=600)
        proc = subprocess.run([n8n_bin, "execute", f"--id={wf['id']}", "--rawOutput"], env=env, capture_output=True,
                              text=True, timeout=600)
        text = proc.stdout
        try:
            data = json.loads(text[text.index("{"):])
        except ValueError:
            data = {"error": (proc.stderr or text)[-500:]}
        results[slug] = data
    return results


def last_items(run: dict) -> dict[str, list]:
    """{node name: output items} from an n8n execution result."""
    rd = run.get("data", {}).get("resultData", {}).get("runData", {})
    return {name: [i["json"] for i in runs[-1].get("data", {}).get("main", [[]])[0] or []]
            for name, runs in rd.items() if runs}


if __name__ == "__main__":
    res = run_all(os.environ.get("N8N_BIN", "n8n"))
    ok = True
    for slug, run in res.items():
        err = run.get("data", {}).get("resultData", {}).get("error") or run.get("error")
        nodes = last_items(run) if not err else {}
        ok &= not err
        print(f"{'✓' if not err else '✗'} {slug}: {len(nodes)} nodes ran" + (f"  ERROR {err}" if err else ""))
        for name, items in nodes.items():
            if name.startswith("Start") or not items:
                continue
            print(f"    {name:<28} {json.dumps(items[0])[:110]}")
    sys.exit(0 if ok else 1)
