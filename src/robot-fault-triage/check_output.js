// @include llm
// Guardrails on the model's work order: it may raise priority, never lower it below the rule floor;
// safety is flagged if either the rules or the model say so; invalid output falls back to rules.
const ORDER = ['low', 'medium', 'high', 'critical'];
const ctx = $('Validate & enrich').first().json;
const draft = extractJson(claudeText($input.first().json));
const valid = draft && ORDER.includes(draft.priority) && typeof draft.title === 'string' && Array.isArray(draft.steps);

const floor = ORDER.indexOf(ctx.rule.floor);
const priority = valid ? ORDER[Math.max(floor, ORDER.indexOf(draft.priority))] : ctx.rule.floor;
const safetyCritical = Boolean(ctx.safety || (valid && draft.safety_concern === true));
const order = {
  robot_id: ctx.event.robot_id,
  code: ctx.event.code,
  priority: safetyCritical && ORDER.indexOf(priority) < 2 ? 'high' : priority,
  title: valid ? draft.title.slice(0, 120) : `${ctx.event.code} on ${ctx.event.robot_id}: ${ctx.rule.meaning}`,
  steps: valid ? draft.steps.slice(0, 10).map(String) : ['Inspect per maintenance manual for ' + ctx.event.code],
  parts: valid && Array.isArray(draft.parts) ? draft.parts.slice(0, 10).map(String) : [],
  safety_critical: safetyCritical,
  drafted_by: valid ? 'llm+rules' : 'rules (llm output invalid)',
};
return [{ json: order }];
