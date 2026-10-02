"""Build n8n workflow JSON from Python, with Code-node JavaScript kept in real .js files.

Keeping the JavaScript in files means it can be linted and unit-tested with Node,
and the exported JSON is regenerated (and checked for drift) instead of hand-edited.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
NS = uuid.UUID("6f1d2c3e-8a4b-4c5d-9e6f-0a1b2c3d4e5f")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_CRED = "Anthropic API key"  # n8n "Header Auth" credential: name x-api-key, value <your key>


def load_js(rel: str) -> str:
    """Read a Code-node source; ``// @include llm`` inlines the shared helpers."""
    code = (SRC / rel).read_text()
    if code.lstrip().startswith("// @include llm"):
        code = (SRC / "_lib" / "llm.js").read_text() + "\n" + code.split("\n", 1)[1]
    return code


class Workflow:
    def __init__(self, name: str, description: str, tags: list[str] | None = None):
        self.name, self.description, self.tags = name, description, tags or []
        self.nodes: list[dict] = []
        self.edges: list[tuple[str, str, int]] = []
        self.notes: list[dict] = []

    # -- generic -----------------------------------------------------------------------
    def node(self, name: str, type_: str, params: dict, version: float, **extra) -> str:
        if any(n["name"] == name for n in self.nodes):
            raise ValueError(f"duplicate node name {name!r}")
        n = {"parameters": params, "id": str(uuid.uuid5(NS, f"{self.name}/{name}")), "name": name,
             "type": type_, "typeVersion": version, "position": [0, 0], **extra}
        self.nodes.append(n)
        return name

    def connect(self, src: str, dst: str, output: int = 0) -> "Workflow":
        self.edges.append((src, dst, output))
        return self

    def chain(self, *names: str) -> "Workflow":
        for a, b in zip(names, names[1:]):
            self.connect(a, b)
        return self

    def note(self, text: str, width: int = 380, height: int = 260) -> None:
        self.notes.append({"text": text, "width": width, "height": height})

    # -- node helpers ----------------------------------------------------------------------
    def code(self, name: str, src: str) -> str:
        return self.node(name, "n8n-nodes-base.code", {"jsCode": load_js(src)}, 2)

    def schedule_cron(self, name: str, cron: str) -> str:
        return self.node(name, "n8n-nodes-base.scheduleTrigger",
                         {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}, 1.2)

    def schedule_minutes(self, name: str, minutes: int) -> str:
        return self.node(name, "n8n-nodes-base.scheduleTrigger",
                         {"rule": {"interval": [{"field": "minutes", "minutesInterval": minutes}]}}, 1.2)

    def webhook(self, name: str, path: str, respond_with_node: bool = False) -> str:
        params = {"httpMethod": "POST", "path": path, "options": {}}
        if respond_with_node:
            params["responseMode"] = "responseNode"
        return self.node(name, "n8n-nodes-base.webhook", params, 2, webhookId=str(uuid.uuid5(NS, f"{self.name}/{path}")))

    def http_get(self, name: str, url: str, query: dict | None = None, as_text: bool = False) -> str:
        params: dict = {"url": url, "options": {}}
        if query:
            params["sendQuery"] = True
            params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
        if as_text:
            params["options"] = {"response": {"response": {"responseFormat": "text"}}}
        return self.node(name, "n8n-nodes-base.httpRequest", params, 4.2,
                         retryOnFail=True, maxTries=3, waitBetweenTries=2000)

    def http_post_json(self, name: str, url: str, body_expr: str, credential: str | None = None) -> str:
        params = {"method": "POST", "url": url, "sendBody": True, "specifyBody": "json", "jsonBody": body_expr,
                  "options": {}}
        extra = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000}
        if credential:
            params.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
            extra["credentials"] = {"httpHeaderAuth": {"name": credential}}
        return self.node(name, "n8n-nodes-base.httpRequest", params, 4.2, **extra)

    def claude(self, name: str) -> str:
        """POST $json.body to the Anthropic Messages API (header-auth credential holds the key)."""
        params = {
            "method": "POST", "url": ANTHROPIC_URL,
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {"timeout": 60000},
        }
        return self.node(name, "n8n-nodes-base.httpRequest", params, 4.2,
                         credentials={"httpHeaderAuth": {"name": ANTHROPIC_CRED}},
                         retryOnFail=True, maxTries=3, waitBetweenTries=5000)

    def slack(self, name: str, channel: str, text_expr: str = "={{ $json.text }}") -> str:
        return self.node(name, "n8n-nodes-base.slack", {
            "select": "channel",
            "channelId": {"__rl": True, "value": channel, "mode": "name"},
            "text": text_expr, "otherOptions": {},
        }, 2.2, credentials={"slackApi": {"name": "Slack"}})

    def if_true(self, name: str, left_expr: str) -> str:
        """Branch on a boolean expression: output 0 = true, output 1 = false."""
        return self.node(name, "n8n-nodes-base.if", {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
            "conditions": [{"id": str(uuid.uuid5(NS, f"{self.name}/{name}/c")), "leftValue": left_expr,
                            "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and"}, "options": {}}, 2)

    # -- export ------------------------------------------------------------------------------
    def _layout(self) -> None:
        depth: dict[str, int] = {n["name"]: 0 for n in self.nodes}
        for _ in range(len(self.nodes)):  # longest-path layering (graphs are small DAGs)
            for a, b, _o in self.edges:
                depth[b] = max(depth[b], depth[a] + 1)
        rows: dict[int, int] = defaultdict(int)
        for n in self.nodes:
            d = depth[n["name"]]
            n["position"] = [240 + 260 * d, 300 + 180 * rows[d]]
            rows[d] += 1

    def to_dict(self) -> dict:
        self._layout()
        conns: dict = {}
        for a, b, out in self.edges:
            main = conns.setdefault(a, {"main": []})["main"]
            while len(main) <= out:
                main.append([])
            main[out].append({"node": b, "type": "main", "index": 0})
        nodes = list(self.nodes)
        for i, note in enumerate(self.notes):
            nodes.append({"parameters": {"content": note["text"], "height": note["height"], "width": note["width"]},
                          "id": str(uuid.uuid5(NS, f"{self.name}/note{i}")), "name": f"Note {i + 1}",
                          "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [-200, 120 + 300 * i]})
        return {"name": self.name, "nodes": nodes, "connections": conns, "active": False,
                "settings": {"executionOrder": "v1"}, "pinData": {},
                "meta": {"templateCredsSetupCompleted": False, "description": self.description},
                "tags": []}  # n8n tags need instance-specific ids, so they are left to the importer

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
