// Weekly fleet KPIs from fault events. Events: {robot_id, start, end} downtime intervals plus {code}.
const WEEK_H = 7 * 24;
const events = $input.first().json.events || [];
const robots = $input.first().json.robots || [...new Set(events.map((e) => e.robot_id))];
const down = {};
const codes = {};
for (const e of events) {
  const h = Math.max(0, (Date.parse(e.end) - Date.parse(e.start)) / 36e5);
  down[e.robot_id] = (down[e.robot_id] || 0) + h;
  codes[e.code] = (codes[e.code] || 0) + 1;
}
const totalDown = Object.values(down).reduce((a, b) => a + b, 0);
const fleetHours = robots.length * WEEK_H;
const kpis = {
  robots: robots.length,
  failures: events.length,
  availability_pct: +(100 * (1 - totalDown / fleetHours)).toFixed(1),
  mtbf_h: events.length ? +((fleetHours - totalDown) / events.length).toFixed(1) : null,
  mttr_h: events.length ? +(totalDown / events.length).toFixed(1) : null,
  top_codes: Object.entries(codes).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([code, n]) => ({ code, n })),
  worst_robot: Object.entries(down).sort((a, b) => b[1] - a[1]).map(([id, h]) => ({ id, down_h: +h.toFixed(1) }))[0] || null,
};
const state = $getWorkflowStaticData('global');
const previous = state.lastWeek || null;
state.lastWeek = kpis;
return [{ json: { kpis, previous } }];
