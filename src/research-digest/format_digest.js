// @include llm
// Join Claude's ratings with the papers. If the reply is unusable, fall back to keyword scores
// so the digest still goes out (and say so).
const MIN_RELEVANCE = 6;
const papers = $('Parse feed').all().map((i) => i.json);
const ratings = extractJson(claudeText($input.first().json));
let picked;
let note = '';
if (Array.isArray(ratings)) {
  const byId = Object.fromEntries(ratings.filter((r) => r && r.id).map((r) => [r.id, r]));
  picked = papers
    .filter((p) => byId[p.id] && Number(byId[p.id].relevance) >= MIN_RELEVANCE)
    .map((p) => ({ ...p, relevance: Number(byId[p.id].relevance), why: String(byId[p.id].why || '') }))
    .sort((a, b) => b.relevance - a.relevance);
} else {
  note = '_(ranking model unavailable: ordered by keyword match)_\n';
  picked = papers.filter((p) => p.keywordScore >= 2).slice(0, 5).map((p) => ({ ...p, relevance: null, why: '' }));
}
if (!picked.length) return [];
const lines = picked.map((p) => `• <${p.id}|${p.title}>${p.relevance !== null ? ` (${p.relevance}/10)` : ''}` +
  `\n   ${p.authors.join(', ')}${p.why ? `\n   _${p.why}_` : ''}`);
return [{ json: { text: `*Research digest: ${picked.length} paper(s)*\n${note}${lines.join('\n')}`, count: picked.length } }];
