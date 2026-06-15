// 브라우저용 실시간 시세 조회.
// Yahoo quote 엔드포인트는 CORS로 직접 호출이 막히는 경우가 있어,
// 공개 CORS 프록시를 경유하는 폴백을 둔다. (시세 조회는 공개정보)

const QUOTE_HOSTS = [
  // 직접 시도 (일부 환경에서 동작)
  (sym) => `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=1d`,
  // 폴백: CORS 프록시 경유
  (sym) =>
    `https://corsproxy.io/?url=${encodeURIComponent(
      `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=1d`
    )}`,
];

function parseChart(json) {
  try {
    const r = json.chart.result[0];
    const price = r.meta.regularMarketPrice;
    const prevClose = r.meta.chartPreviousClose ?? r.meta.previousClose;
    return { price, prevClose };
  } catch {
    return null;
  }
}

export async function getQuote(symbol) {
  for (const build of QUOTE_HOSTS) {
    try {
      const res = await fetch(build(symbol), { cache: "no-store" });
      if (!res.ok) continue;
      const json = await res.json();
      const parsed = parseChart(json);
      if (parsed && typeof parsed.price === "number") return parsed;
    } catch {
      // 다음 호스트 시도
    }
  }
  return null;
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
