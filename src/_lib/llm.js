// ---- shared helpers (inlined by the builder; n8n Code nodes cannot import files) ----
function claudeRequest(system, user, { model = 'claude-haiku-4-5-20251001', maxTokens = 1024 } = {}) {
  // Body for POST https://api.anthropic.com/v1/messages
  return { model, max_tokens: maxTokens, system, messages: [{ role: 'user', content: user }] };
}

function claudeText(response) {
  // Concatenate the text blocks of a Messages API response.
  const blocks = (response && response.content) || [];
  return blocks.filter((b) => b.type === 'text').map((b) => b.text).join('');
}

function extractJson(text) {
  // Models sometimes wrap JSON in prose or code fences: take the outermost {...} or [...].
  if (typeof text !== 'string') return null;
  const starts = [text.indexOf('{'), text.indexOf('[')].filter((i) => i >= 0);
  if (!starts.length) return null;
  const start = Math.min(...starts);
  const end = Math.max(text.lastIndexOf('}'), text.lastIndexOf(']'));
  if (end <= start) return null;
  try { return JSON.parse(text.slice(start, end + 1)); } catch (e) { return null; }
}
// ---- end shared helpers ----
