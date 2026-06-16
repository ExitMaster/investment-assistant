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
