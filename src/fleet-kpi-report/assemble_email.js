// @include llm
// Anti-hallucination check: every number in the narrative must appear in the KPI data;
// otherwise the email uses a plain template instead of the model's text.
const { kpis, previous } = $('Compute KPIs').first().json;
const narrative = claudeText($input.first().json).trim();
const allowed = new Set();
const collect = (v) => {
  if (v === null || v === undefined) return;
  if (typeof v === 'number') { allowed.add(String(v)); allowed.add(String(Math.round(v))); return; }
  if (typeof v === 'string') { (v.match(/\d+(\.\d+)?/g) || []).forEach((n) => allowed.add(n)); return; }
  Object.values(v).forEach(collect);
};
collect(kpis);
collect(previous);
const numbers = narrative.match(/\d+(\.\d+)?/g) || [];
const unsupported = numbers.filter((n) => !allowed.has(n));
const grounded = narrative.length > 0 && unsupported.length === 0;
const fallback = `Availability ${kpis.availability_pct}% across ${kpis.robots} robots, ${kpis.failures} failures, ` +
  `MTBF ${kpis.mtbf_h} h, MTTR ${kpis.mttr_h} h.`;
const rows = [['Availability', `${kpis.availability_pct}%`, previous ? `${previous.availability_pct}%` : '-'],
  ['Failures', kpis.failures, previous ? previous.failures : '-'],
  ['MTBF (h)', kpis.mtbf_h, previous ? previous.mtbf_h : '-'],
  ['MTTR (h)', kpis.mttr_h, previous ? previous.mttr_h : '-']];
const table = '<table border="1" cellpadding="4"><tr><th>KPI</th><th>This week</th><th>Last week</th></tr>' +
  rows.map((r) => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join('') + '</table>';
const body = `<p>${(grounded ? narrative : fallback).replace(/\n/g, '<br>')}</p>${table}` +
  (grounded ? '' : `<p><small>Model summary withheld: unsupported numbers ${unsupported.join(', ') || '(empty reply)'}.</small></p>`);
return [{ json: { subject: `Fleet weekly: availability ${kpis.availability_pct}%`, html: body, grounded, unsupported } }];
