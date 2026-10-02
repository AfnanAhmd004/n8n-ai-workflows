// @include llm
// Validate the score; if the model reply is unusable, use a transparent rule-based score.
const { lead } = $('Normalise & filter spam').first().json;
const r = extractJson(claudeText($input.first().json));
const ok = r && Number.isFinite(Number(r.score)) && Number(r.score) >= 0 && Number(r.score) <= 100;
let score;
let reason;
let segment;
if (ok) {
  score = Math.round(Number(r.score));
  reason = String(r.reason || '').slice(0, 300);
  segment = String(r.segment || 'unknown').slice(0, 50);
} else {
  const text = `${lead.role} ${lead.message}`.toLowerCase();
  score = 20 + 20 * ['head', 'director', 'vp', 'cto', 'manager', 'lead'].some((w) => text.includes(w)) +
    20 * ['robot', 'automation', 'inspection', 'warehouse', 'aerospace', 'drone'].some((w) => text.includes(w));
  reason = 'rule-based score (model reply invalid)';
  segment = 'unknown';
}
return [{ json: { ...lead, score, reason, segment, next_step: ok ? String(r.next_step || '') : 'manual review' } }];
