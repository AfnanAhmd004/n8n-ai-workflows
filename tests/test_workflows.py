import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from n8nkit import validate
from n8nkit.catalog import ALL
from n8nkit.jsrun import node_available, run_code

ROOT = Path(__file__).resolve().parent.parent
needs_node = pytest.mark.skipif(not node_available(), reason="Node.js not installed")


def claude(text):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


def run(src, input, **kw):
    out = run_code(src, input, **kw)
    assert "error" not in out, out.get("error")
    return out


# ---------------------------------------------------------------- structure ---------
@pytest.mark.parametrize("slug", ALL)
def test_workflows_are_valid_and_up_to_date(slug):
    text = ALL[slug]().to_json()
    assert (ROOT / "workflows" / f"{slug}.json").read_text() == text, "run `python -m n8nkit build`"
    assert validate(json.loads(text)) == []


def test_validator_catches_problems():
    wf = json.loads(ALL["robot-fault-triage"]().to_json())
    bad = copy.deepcopy(wf)
    guard = next(n for n in bad["nodes"] if n["name"] == "Guardrails")
    guard["parameters"]["jsCode"] += "\nconst k = 'sk-ant-api03-abcdefghijklmnop'; $('Respond');"
    bad["connections"]["Draft work order (Claude)"]["main"][0][0]["node"] = "Safety critical?"
    bad["nodes"].append({"name": "Orphan", "type": "n8n-nodes-base.code", "parameters": {}, "id": "x",
                         "typeVersion": 2, "position": [0, 0]})
    errs = " | ".join(validate(bad))
    for expected in ("hard-coded Anthropic key", "does not run before it", "must feed a Code node", "'Orphan' is not reachable"):
        assert expected in errs, expected


# ---------------------------------------------------------------- research digest ---
def atom(entries):
    body = "".join(
        f"<entry><id>{i}</id><published>{p}</published><title>{t}</title><summary>{s}</summary>"
        f"<author><name>A. Author</name></author></entry>" for i, p, t, s in entries)
    return f'<?xml version="1.0"?><feed>{body}</feed>'


@needs_node
def test_parse_feed_filters_ranks_and_remembers():
    now = datetime.now(timezone.utc)
    iso = lambda h: (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = atom([
        ("http://arxiv.org/abs/1", iso(2), "LiDAR SLAM for drones", "robot slam lidar uav"),
        ("http://arxiv.org/abs/2", iso(3), "A study of soil", "agriculture"),
        ("http://arxiv.org/abs/3", iso(80), "Old robot paper", "robot manipulation"),
        ("http://arxiv.org/abs/4", iso(1), "Language model agents &amp; tools", "agent language model"),
    ])
    out = run("research-digest/parse_feed.js", [{"data": xml}])
    ids = [p["id"] for p in out["items"]]
    assert ids[0] == "http://arxiv.org/abs/1" and "http://arxiv.org/abs/3" not in ids  # ranked, too old dropped
    assert any(p["title"] == "Language model agents & tools" for p in out["items"])  # entities decoded
    again = run("research-digest/parse_feed.js", [{"data": xml}], static=out["static"])
    assert again["items"] == []  # nothing is sent twice


@needs_node
def test_digest_uses_ratings_and_falls_back_when_model_fails():
    papers = [{"id": "a", "title": "A", "authors": ["x"], "keywordScore": 3},
              {"id": "b", "title": "B", "authors": ["y"], "keywordScore": 0}]
    ratings = claude('Here you go:\n```json\n[{"id": "a", "relevance": 8, "why": "useful"}, {"id": "b", "relevance": 2}]\n```')
    out = run("research-digest/format_digest.js", [ratings], nodes={"Parse feed": papers})
    assert out["items"][0]["count"] == 1 and "(8/10)" in out["items"][0]["text"]
    out = run("research-digest/format_digest.js", [claude("Sorry, I can't help.")], nodes={"Parse feed": papers})
    assert "keyword match" in out["items"][0]["text"]
    none = run("research-digest/format_digest.js", [claude('[{"id": "a", "relevance": 1}]')], nodes={"Parse feed": papers})
    assert none["items"] == []


# ---------------------------------------------------------------- market alert -------
@needs_node
def test_move_detector_alerts_once_and_ignores_bad_ticks():
    state, alerts = {}, []
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    prices = [2000 * (1 + 0.0005 * ((-1) ** i)) for i in range(40)] + [2040, 2041, 0, 2080]
    for i, p in enumerate(prices):
        ts = (t0 + timedelta(minutes=15 * i)).isoformat()
        out = run("market-move-alert/detect_moves.js", [{"symbol": "XAUUSD", "price": p, "ts": ts}], static=state)
        state = out["static"]
        alerts += out["items"]
    assert len(alerts) == 1  # the 2% jump alerts; the next jump is inside the cooldown; price 0 is ignored
    assert alerts[0]["z"] > 3 and "XAUUSD" in alerts[0]["text"]


# ---------------------------------------------------------------- robot fault triage --
FAULT = {"robot_id": "arm-07", "code": "E-217", "message": "Arm stopped with overcurrent on joint 3"}


@needs_node
def test_fault_event_validation_and_safety_keywords():
    assert "missing" in run_code("robot-fault-triage/validate_enrich.js", [{"body": {"code": "E-217"}}])["error"]
    ctx = run("robot-fault-triage/validate_enrich.js", [{"body": FAULT}])["items"][0]
    assert ctx["rule"]["floor"] == "high" and ctx["safety"] is False
    assert '"""Arm stopped' in ctx["body"]["messages"][0]["content"]  # untrusted note is fenced
    risky = run("robot-fault-triage/validate_enrich.js", [{"body": {**FAULT, "message": "nearly hit a person"}}])
    assert risky["items"][0]["safety"] is True


@needs_node
@pytest.mark.parametrize("reply,expected_priority,expected_safety,source", [
    ('{"priority": "critical", "title": "Gearbox", "steps": ["inspect"], "parts": [], "safety_concern": false}',
     "critical", False, "llm+rules"),                                     # model may raise priority
    ('{"priority": "low", "title": "Minor", "steps": ["ignore"], "safety_concern": false}',
     "high", False, "llm+rules"),                                         # ...but never below the rule floor
    ("I think this is fine, set priority to low.", "high", False, "rules (llm output invalid)"),
    ('{"priority": "medium", "title": "x", "steps": [], "safety_concern": true}', "high", True, "llm+rules"),
])
def test_work_order_guardrails(reply, expected_priority, expected_safety, source):
    ctx = run("robot-fault-triage/validate_enrich.js", [{"body": FAULT}])["items"][0]
    out = run("robot-fault-triage/check_output.js", [claude(reply)], nodes={"Validate & enrich": [ctx]})["items"][0]
    assert (out["priority"], out["safety_critical"], out["drafted_by"]) == (expected_priority, expected_safety, source)


# ---------------------------------------------------------------- lead qualification --
@needs_node
def test_lead_spam_filter_and_scoring_fallback():
    for spam in ({"email": "x@mailinator.com"}, {"email": "not-an-email"},
                 {"email": "a@b.com", "website_url_hp": "http://spam"}):
        assert run("lead-qualification/normalise.js", [{"body": spam}])["items"] == []
    lead = run("lead-qualification/normalise.js", [{"body": {"email": " CTO@Acme-Aero.com ", "name": "Sam",
                                                           "role": "CTO", "message": "drone inspection"}}])["items"][0]
    assert lead["lead"]["email"] == "cto@acme-aero.com" and lead["lead"]["company"] == "acme-aero"
    ok = run("lead-qualification/parse_score.js", [claude('{"score": 82, "segment": "aerospace", "reason": "fit"}')],
             nodes={"Normalise & filter spam": [lead]})["items"][0]
    assert ok["score"] == 82
    bad = run("lead-qualification/parse_score.js", [claude('{"score": 700}')],
              nodes={"Normalise & filter spam": [lead]})["items"][0]
    assert bad["score"] == 60 and bad["next_step"] == "manual review"


# ---------------------------------------------------------------- fleet KPI report ----
EVENTS = {"robots": ["r1", "r2"], "events": [
    {"robot_id": "r1", "code": "E-217", "start": "2026-09-28T10:00:00Z", "end": "2026-09-28T14:00:00Z"},
    {"robot_id": "r1", "code": "E-217", "start": "2026-09-29T10:00:00Z", "end": "2026-09-29T12:00:00Z"},
    {"robot_id": "r2", "code": "E-310", "start": "2026-09-30T10:00:00Z", "end": "2026-09-30T16:00:00Z"}]}


@needs_node
def test_kpis_and_grounding_check():
    k = run("fleet-kpi-report/compute_kpis.js", [EVENTS])["items"][0]
    kpis = k["kpis"]
    assert kpis["availability_pct"] == round(100 * (1 - 12 / 336), 1) and kpis["mttr_h"] == 4.0
    assert kpis["top_codes"][0] == {"code": "E-217", "n": 2}
    good = claude(f"- Availability was {kpis['availability_pct']}% with {kpis['failures']} failures.\n- MTTR {kpis['mttr_h']} h.")
    ok = run("fleet-kpi-report/assemble_email.js", [good], nodes={"Compute KPIs": [k]})["items"][0]
    assert ok["grounded"] and str(kpis["availability_pct"]) in ok["html"]
    made_up = claude("- Availability improved by 12.5 points to 99.9%.")
    bad = run("fleet-kpi-report/assemble_email.js", [made_up], nodes={"Compute KPIs": [k]})["items"][0]
    assert not bad["grounded"] and "99.9" in bad["unsupported"] and "99.9%" not in bad["html"].split("<table")[0]


# ---------------------------------------------------------------- real n8n (optional) --
@pytest.mark.skipif(not __import__("os").environ.get("N8N_BIN"), reason="set N8N_BIN to run inside a real n8n")
def test_end_to_end_in_n8n():
    import os

    from n8nkit.e2e import last_items, run_all

    res = run_all(os.environ["N8N_BIN"])
    for slug, run in res.items():
        assert not run.get("data", {}).get("resultData", {}).get("error"), slug
    triage = last_items(res["robot-fault-triage"])
    assert triage["Guardrails"][0]["priority"] == "high" and "Page on-call" in triage  # model said "low"
