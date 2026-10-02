// Alert when the latest return is unusual relative to recent volatility (EWMA z-score),
// with a cooldown so one move does not page people every 15 minutes.
const Z_THRESHOLD = 3.0;
const LAMBDA = 0.94;          // EWMA decay (RiskMetrics-style)
const MIN_HISTORY = 20;       // returns needed before alerting
const COOLDOWN_MIN = 120;

const state = $getWorkflowStaticData('global');
state.series = state.series || {};
const alerts = [];
for (const item of $input.all()) {
  const { symbol, price, ts } = item.json;
  if (!symbol || !(price > 0)) continue;           // bad tick: ignore, never alert on it
  const s = state.series[symbol] || { last: null, var: null, n: 0, lastAlert: 0 };
  if (s.last !== null) {
    const r = Math.log(price / s.last);
    if (s.var !== null && s.n >= MIN_HISTORY) {
      const z = r / Math.sqrt(s.var);
      const now = Date.parse(ts) || Date.now();
      if (Math.abs(z) >= Z_THRESHOLD && now - s.lastAlert >= COOLDOWN_MIN * 60e3) {
        alerts.push({ symbol, price, ts, returnPct: +(100 * r).toFixed(3), z: +z.toFixed(2) });
        s.lastAlert = now;
      }
    }
    s.var = s.var === null ? r * r : LAMBDA * s.var + (1 - LAMBDA) * r * r;  // update after testing
    s.n += 1;
  }
  s.last = price;
  state.series[symbol] = s;
}
return alerts.map((a) => ({
  json: { ...a, text: `:rotating_light: *${a.symbol}* moved ${a.returnPct > 0 ? '+' : ''}${a.returnPct}% ` +
    `(${a.z}σ vs recent volatility) to ${a.price} at ${a.ts}` },
}));
