"""Static checks for n8n workflow JSON: structure, references, secrets and LLM guardrails."""
from __future__ import annotations

import re
from collections import defaultdict

TRIGGERS = {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.webhook", "n8n-nodes-base.manualTrigger",
            "n8n-nodes-base.cron"}
NOTE = "n8n-nodes-base.stickyNote"
SECRET_PATTERNS = {
    "Anthropic key": r"sk-ant-[A-Za-z0-9_-]{10,}",
    "OpenAI-style key": r"\bsk-[A-Za-z0-9]{20,}",
    "Slack token": r"xox[abposr]-[A-Za-z0-9-]{10,}",
    "bearer token": r"Bearer\s+[A-Za-z0-9._-]{20,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{20,}",
    "AWS access key": r"AKIA[0-9A-Z]{16}",
}
NODE_REF = re.compile(r"""\$\(\s*['"]([^'"]+)['"]\s*\)""")


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _is_llm_call(node: dict) -> bool:
    return node["type"] == "n8n-nodes-base.httpRequest" and "api.anthropic.com" in str(node["parameters"].get("url", ""))


def validate(wf: dict) -> list[str]:
    errs: list[str] = []
    nodes = [n for n in wf.get("nodes", []) if n["type"] != NOTE]
    names = [n["name"] for n in nodes]
    by_name = {n["name"]: n for n in nodes}
    if len(names) != len(set(names)):
        errs.append("duplicate node names")
    succ: dict[str, list[str]] = defaultdict(list)
    pred: dict[str, list[str]] = defaultdict(list)
    for src, outs in wf.get("connections", {}).items():
        if src not in by_name:
            errs.append(f"connection from unknown node {src!r}")
            continue
        for branch in outs.get("main", []):
            for c in branch:
                if c["node"] not in by_name:
                    errs.append(f"{src!r} connects to unknown node {c['node']!r}")
                else:
                    succ[src].append(c["node"])
                    pred[c["node"]].append(src)

    triggers = [n["name"] for n in nodes if n["type"] in TRIGGERS]
    if not triggers:
        errs.append("no trigger node")
    seen, stack = set(), list(triggers)
    while stack:
        n = stack.pop()
        if n not in seen:
            seen.add(n)
            stack.extend(succ[n])
    for n in names:
        if n not in seen:
            errs.append(f"node {n!r} is not reachable from a trigger")

    def ancestors(name: str) -> set[str]:
        out, st = set(), list(pred[name])
        while st:
            p = st.pop()
            if p not in out:
                out.add(p)
                st.extend(pred[p])
        return out

    for node in nodes:
        for s in _strings(node["parameters"]):
            for ref in NODE_REF.findall(s):
                if ref not in by_name:
                    errs.append(f"{node['name']!r} references unknown node {ref!r}")
                elif ref not in ancestors(node["name"]):
                    errs.append(f"{node['name']!r} references {ref!r}, which does not run before it")
            for label, pat in SECRET_PATTERNS.items():
                if re.search(pat, s):
                    errs.append(f"{node['name']!r} contains what looks like a hard-coded {label}")
        if node["type"] == "n8n-nodes-base.httpRequest" and not node.get("retryOnFail"):
            errs.append(f"HTTP node {node['name']!r} has no retry policy")
        if node["parameters"].get("authentication") == "genericCredentialType" and not node.get("credentials"):
            errs.append(f"{node['name']!r} uses credential auth but names no credential")
        if _is_llm_call(node):
            nxt = succ[node["name"]]
            if not nxt or any(by_name[x]["type"] != "n8n-nodes-base.code" for x in nxt):
                errs.append(f"LLM call {node['name']!r} must feed a Code node that validates its output")
        if node["type"] == "n8n-nodes-base.webhook" and node["parameters"].get("responseMode") == "responseNode":
            reach, st = set(), [node["name"]]
            while st:
                x = st.pop()
                if x not in reach:
                    reach.add(x)
                    st.extend(succ[x])
            if not any(by_name[x]["type"] == "n8n-nodes-base.respondToWebhook" for x in reach):
                errs.append(f"webhook {node['name']!r} waits for a Respond node that is never reached")
    return errs
