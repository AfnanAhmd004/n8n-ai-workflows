// Edit here: what to watch and how sensitive the alert is.
// PRICE_URL must return JSON like {"symbol": "XAUUSD", "price": 2345.6, "ts": "2026-10-02T12:00:00Z"}.
const PRICE_URL = 'https://your-data-provider.example.com/v1/quote?symbol=';
const SYMBOLS = ['XAUUSD', 'EURUSD', 'US500'];
return SYMBOLS.map((symbol) => ({ json: { symbol, url: PRICE_URL + encodeURIComponent(symbol) } }));
