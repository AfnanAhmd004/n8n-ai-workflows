// @include llm
const { kpis, previous } = $input.first().json;
const system = 'You write a weekly operations summary for company leadership. Use ONLY the numbers provided; ' +
  'do not compute new ones. Five bullets maximum, plain language, end with one recommended action.';
const user = `This week: ${JSON.stringify(kpis)}\nLast week: ${JSON.stringify(previous)}`;
return [{ json: { body: claudeRequest(system, user, { maxTokens: 500 }) } }];
