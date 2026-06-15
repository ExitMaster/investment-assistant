// 브라우저용 실시간 시세 조회.
// 자체 Vercel 함수(/api/quote)를 경유 → CORS 문제 없음, 공개 프록시 의존 없음.

export async function getQuote(symbol) {
  try {
    const res = await fetch(`/api/quote?symbol=${encodeURIComponent(symbol)}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const json = await res.json();
    if (json && typeof json.price === "number") {
      return { price: json.price, prevClose: json.prevClose };
    }
    return null;
  } catch {
    return null;
  }
}

// 여러 심볼 병렬 조회
export async function getQuotes(symbols) {
  const out = {};
  await Promise.all(
    symbols.map(async (s) => {
      out[s] = await getQuote(s);
    })
  );
  return out;
}
