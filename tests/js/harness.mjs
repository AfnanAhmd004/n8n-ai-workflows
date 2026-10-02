// Run an n8n Code node ("Run once for all items") outside n8n.
// stdin: {"code": str, "input": [json...], "nodes": {"Node name": [json...]}, "static": {...}}
// stdout: {"items": [json...], "static": {...}}
import { readFileSync } from 'node:fs';

const req = JSON.parse(readFileSync(0, 'utf8'));
const wrap = (arr) => arr.map((json) => ({ json }));
const inputItems = wrap(req.input || []);
const $input = { all: () => inputItems, first: () => inputItems[0], last: () => inputItems[inputItems.length - 1] };
const $ = (name) => {
  if (!(name in (req.nodes || {}))) throw new Error(`node ${name} has no output in this test`);
  const items = wrap(req.nodes[name]);
  return { all: () => items, first: () => items[0], last: () => items[items.length - 1] };
};
const staticData = req.static || {};
const $getWorkflowStaticData = () => staticData;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fn = new AsyncFunction('$input', '$', '$getWorkflowStaticData', req.code);
try {
  const out = await fn($input, $, $getWorkflowStaticData);
  if (!Array.isArray(out)) throw new Error('Code node must return an array of items');
  process.stdout.write(JSON.stringify({ items: out.map((i) => i.json), static: staticData }));
} catch (e) {
  process.stdout.write(JSON.stringify({ error: String(e && e.message || e) }));
}
