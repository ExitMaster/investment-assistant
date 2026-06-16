// 브라우저용 실시간 시세 조회 + 티커 검색.
// 자체 Vercel 함수(/api/*)를 경유 → CORS 문제 없음.

export async function getQuotes(symbols) {
  if (!symbols || symbols.length === 0) return {};
  try {
    const q = symbols.map((s) => encodeURIComponent(s)).join(",");
    const res = await fetch(`/api/quotes?symbols=${q}`, { cache: "no-store" });
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};
  }
}

export async function getQuote(symbol) {
  const out = await getQuotes([symbol]);
  return out[symbol] ?? null;
}

// 한국 6자리 종목 → 한국어명 + 정식 TradingView 심볼 (TV 심볼검색, 캐시)
const _krCache = {};
export async function resolveKR(code) {
  if (code in _krCache) return _krCache[code];
  try {
    const res = await fetch(`/api/tv-search?q=${encodeURIComponent(code)}`);
    const json = await res.json();
    const list = json.quotes || [];
    const hit =
      list.find((q) => q.symbol === code && q.exchange === "KRX") ||
      list.find((q) => q.symbol === code) ||
      null;
    _krCache[code] = hit ? { name: hit.description, tvSymbol: hit.tvSymbol } : null;
  } catch {
    _krCache[code] = null;
  }
  return _krCache[code];
}

export async function searchTickers(query) {
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.quotes ?? [];
  } catch {
    return [];
  }
}
