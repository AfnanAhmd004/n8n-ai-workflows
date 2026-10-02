// @include llm
// One request for all candidate papers: cheaper than one call per paper.
const papers = $input.all().map((i) => i.json);
const system = 'You triage research papers for a team working on robotics, AI agents and quantitative trading. ' +
  'Be strict: most papers are not relevant. Reply with JSON only.';
const user = 'Rate each paper 0-10 for relevance and give a one-sentence reason a practitioner would care.\n' +
  'Return a JSON array of {"id": string, "relevance": number, "why": string}.\n\n' +
  JSON.stringify(papers.map((p) => ({ id: p.id, title: p.title, abstract: p.summary })));
return [{ json: { body: claudeRequest(system, user, { maxTokens: 2000 }), count: papers.length } }];
