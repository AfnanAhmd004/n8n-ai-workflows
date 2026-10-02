// Parse the arXiv Atom feed, drop papers already sent, pre-score by keywords.
const TOPICS = ['robot', 'manipulat', 'slam', 'lidar', 'event camera', 'neuromorphic', 'reinforcement',
  'agent', 'language model', 'vision-language', 'trading', 'portfolio', 'spacecraft', 'uav', 'drone'];
const MAX_AGE_HOURS = 36;
const KEEP = 15;

const xml = $input.first().json.data || '';
const unescape = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
const tag = (block, name) => {
  const m = block.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? unescape(m[1]).replace(/\s+/g, ' ').trim() : '';
};

const seen = $getWorkflowStaticData('global');
seen.ids = seen.ids || [];
const now = Date.now();
const papers = [];
for (const block of xml.split('<entry>').slice(1)) {
  const id = tag(block, 'id');
  const published = tag(block, 'published');
  const ageH = (now - Date.parse(published)) / 36e5;
  if (!id || seen.ids.includes(id) || !(ageH <= MAX_AGE_HOURS)) continue;
  const title = tag(block, 'title');
  const summary = tag(block, 'summary');
  const authors = [...block.matchAll(/<name>([\s\S]*?)<\/name>/g)].map((m) => m[1].trim());
  const text = `${title} ${summary}`.toLowerCase();
  const keywordScore = TOPICS.filter((t) => text.includes(t)).length;
  papers.push({ id, title, summary: summary.slice(0, 900), authors: authors.slice(0, 4), published, keywordScore });
}
papers.sort((a, b) => b.keywordScore - a.keywordScore);
const top = papers.slice(0, KEEP);
seen.ids = [...seen.ids, ...top.map((p) => p.id)].slice(-2000);
return top.map((p) => ({ json: p }));
