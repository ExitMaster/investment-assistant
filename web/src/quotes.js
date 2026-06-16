// 브라우저용 실시간 시세 조회 + 티커 검색.
// 자체 Vercel 함수(/api/*)를 경유 → CORS 문제 없음.

export async function getQuote(symbol) {
  try {
    const res = await fetch(`/api/quote?symbol=${encodeURIComponent(symbol)}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const json = await res.json();
    if (json && typeof json.price === "number") {
      return { price: json.price, prevClose: json.prevClose, name: json.name };
    }
    return null;
  } catch {
    return null;
  }
}

export async function getQuotes(symbols) {
  const out = {};
  await Promise.all(
    symbols.map(async (s) => {
      out[s] = await getQuote(s);
    })
  );
  return out;
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
