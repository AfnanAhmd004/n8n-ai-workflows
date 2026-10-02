"""The workflows in this repo, defined with the builder. ``python -m n8nkit build`` writes workflows/*.json."""
from __future__ import annotations

from .builder import Workflow

SETUP_CLAUDE = ("## Setup\n1. Create a **Header Auth** credential named `Anthropic API key` "
                "(header name `x-api-key`, value = your key).\n")


def research_digest() -> Workflow:
    w = Workflow("Research digest (arXiv → Claude → Slack)",
                 "Weekday digest of new robotics / AI-agent / quant papers, ranked for relevance by Claude.",
                 ["research", "llm"])
    w.schedule_cron("Weekdays 07:00", "0 7 * * 1-5")
    w.http_get("Fetch arXiv", "https://export.arxiv.org/api/query", {
        "search_query": "cat:cs.RO OR cat:cs.AI OR cat:q-fin.TR OR cat:cs.CV",
        "sortBy": "submittedDate", "sortOrder": "descending", "max_results": "100"}, as_text=True)
    w.code("Parse feed", "research-digest/parse_feed.js")
    w.code("Build ranking prompt", "research-digest/build_prompt.js")
    w.claude("Rank with Claude")
    w.code("Format digest", "research-digest/format_digest.js")
    w.slack("Post to Slack", "#research")
    w.chain("Weekdays 07:00", "Fetch arXiv", "Parse feed", "Build ranking prompt", "Rank with Claude",
            "Format digest", "Post to Slack")
    w.note(SETUP_CLAUDE + "2. Create a **Slack** credential and pick the channel.\n3. Edit `TOPICS` in *Parse feed*.\n\n"
           "Papers already sent are remembered (workflow static data), so nothing is posted twice. "
           "If Claude's reply is unusable, the digest falls back to keyword ranking and says so.")
    return w


def market_move_alert() -> Workflow:
    w = Workflow("Market move alert (EWMA z-score)",
                 "Every 15 minutes: alert on returns that are unusual relative to recent volatility, with a cooldown.",
                 ["quant", "alerts"])
    w.schedule_minutes("Every 15 min", 15)
    w.code("Config", "market-move-alert/config.js")
    w.http_get("Fetch price", "={{ $json.url }}")
    w.code("Detect unusual moves", "market-move-alert/detect_moves.js")
    w.slack("Alert #trading", "#trading-alerts")
    w.chain("Every 15 min", "Config", "Fetch price", "Detect unusual moves", "Alert #trading")
    w.note("## Setup\n1. In *Config*, set `PRICE_URL` to your data source and the `SYMBOLS`.\n"
           "2. Create a **Slack** credential.\n\nVolatility is an EWMA (λ = 0.94); a move must exceed 3σ, and each "
           "symbol has a 2-hour cooldown. Bad ticks are ignored. Information only, not trading advice.")
    return w


def robot_fault_triage() -> Workflow:
    w = Workflow("Robot fault triage (webhook → Claude work order → ticket)",
                 "Turns robot fault events into validated work orders; safety-critical faults page on-call.",
                 ["robotics", "operations", "llm"])
    w.webhook("Fault event", "robot-fault", respond_with_node=True)
    w.code("Validate & enrich", "robot-fault-triage/validate_enrich.js")
    w.claude("Draft work order (Claude)")
    w.code("Guardrails", "robot-fault-triage/check_output.js")
    w.if_true("Safety critical?", "={{ $json.safety_critical }}")
    w.slack("Page on-call", "#robot-oncall",
            "=:warning: *SAFETY* {{ $json.robot_id }} {{ $json.code }}: {{ $json.title }} (priority {{ $json.priority }})")
    w.http_post_json("Create ticket", "https://tickets.example.com/api/work-orders",
                     "={{ JSON.stringify($('Guardrails').first().json) }}", credential="Ticketing API")
    w.node("Respond", "n8n-nodes-base.respondToWebhook", {
        "respondWith": "json",
        "responseBody": "={{ JSON.stringify({ ok: true, ticket: $json.id || null, "
                        "priority: $('Guardrails').first().json.priority }) }}",
        "options": {}}, 1.1)
    w.chain("Fault event", "Validate & enrich", "Draft work order (Claude)", "Guardrails", "Safety critical?")
    w.connect("Safety critical?", "Page on-call", 0).connect("Page on-call", "Create ticket")
    w.connect("Safety critical?", "Create ticket", 1).connect("Create ticket", "Respond")
    w.note(SETUP_CLAUDE + "2. **Ticketing API**: Header Auth credential for your CMMS; replace the URL.\n"
           "3. **Slack** credential for paging.\n\nGuardrails: the model may *raise* priority but never lower it "
           "below the rule floor for the fault code; safety is flagged if the rules *or* the model say so; "
           "an unusable model reply falls back to a rule-based work order. The operator note is passed as "
           "untrusted data.", height=320)
    return w


def lead_qualification() -> Workflow:
    w = Workflow("Inbound lead qualification (form → Claude → HubSpot)",
                 "Filters spam, scores fit with Claude (with a rule-based fallback), routes good leads to sales.",
                 ["sales", "crm", "llm"])
    w.webhook("Form submission", "inbound-lead")
    w.code("Normalise & filter spam", "lead-qualification/normalise.js")
    w.claude("Qualify with Claude")
    w.code("Validate score", "lead-qualification/parse_score.js")
    w.node("Score ≥ 60?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
        "conditions": [{"id": "score-threshold", "leftValue": "={{ $json.score }}", "rightValue": 60,
                        "operator": {"type": "number", "operation": "gte"}}],
        "combinator": "and"}, "options": {}}, 2)
    w.http_post_json("Create HubSpot contact", "https://api.hubapi.com/crm/v3/objects/contacts",
                     "={{ JSON.stringify({ properties: { email: $json.email, firstname: $json.name, "
                     "company: $json.company, jobtitle: $json.role } }) }}", credential="HubSpot private app")
    w.slack("Notify sales", "#sales",
            "=New qualified lead ({{ $('Validate score').first().json.score }}/100): "
            "{{ $('Validate score').first().json.name }} at {{ $('Validate score').first().json.company }}. "
            "{{ $('Validate score').first().json.reason }}")
    w.slack("Log for nurture", "#marketing-nurture",
            "=Nurture: {{ $json.company }} ({{ $json.score }}/100) {{ $json.reason }}")
    w.chain("Form submission", "Normalise & filter spam", "Qualify with Claude", "Validate score", "Score ≥ 60?")
    w.connect("Score ≥ 60?", "Create HubSpot contact", 0).connect("Create HubSpot contact", "Notify sales")
    w.connect("Score ≥ 60?", "Log for nurture", 1)
    w.note(SETUP_CLAUDE + "2. **HubSpot private app**: Header Auth credential, header `Authorization`, "
           "value `Bearer <token>`.\n3. **Slack** credential.\n\nAdd a hidden `website_url_hp` field to your form "
           "as a honeypot: bots fill it, people do not.")
    return w


def fleet_kpi_report() -> Workflow:
    w = Workflow("Weekly fleet KPI report (with grounded LLM summary)",
                 "Monday report: availability, MTBF, MTTR and top faults; the LLM summary is rejected if it "
                 "contains any number not in the data.",
                 ["robotics", "reporting", "llm"])
    w.schedule_cron("Mondays 08:00", "0 8 * * 1")
    w.http_get("Fetch fleet events", "https://fleet.example.com/api/events", {"since": "7d"})
    w.code("Compute KPIs", "fleet-kpi-report/compute_kpis.js")
    w.code("Build summary prompt", "fleet-kpi-report/build_prompt.js")
    w.claude("Summarise with Claude")
    w.code("Grounding check & email", "fleet-kpi-report/assemble_email.js")
    w.node("Send email", "n8n-nodes-base.emailSend", {
        "fromEmail": "fleet-reports@example.com", "toEmail": "leadership@example.com",
        "subject": "={{ $json.subject }}", "html": "={{ $json.html }}", "options": {}},
        2.1, credentials={"smtp": {"name": "SMTP"}})
    w.chain("Mondays 08:00", "Fetch fleet events", "Compute KPIs", "Build summary prompt", "Summarise with Claude",
            "Grounding check & email", "Send email")
    w.note(SETUP_CLAUDE + "2. Point *Fetch fleet events* at your fleet API; it should return "
           "`{robots: [...], events: [{robot_id, code, start, end}]}`.\n3. **SMTP** credential and recipients.\n\n"
           "Every number in the model's summary must exist in the KPI data or the email falls back to a template.")
    return w


ALL = {
    "research-digest": research_digest,
    "market-move-alert": market_move_alert,
    "robot-fault-triage": robot_fault_triage,
    "lead-qualification": lead_qualification,
    "fleet-kpi-report": fleet_kpi_report,
}
