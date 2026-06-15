// Vercel Serverless Function: /api/quote?symbol=QQQ
// 브라우저 → 이 함수(같은 도메인) → Yahoo (서버간, CORS 없음) → 시세 반환.
// 공개 프록시 의존을 제거하기 위한 자체 프록시.

export default async function handler(req, res) {
  const symbol = (req.query.symbol || "").trim();
  if (!symbol) {
    res.status(400).json({ error: "symbol required" });
    return;
  }

  // 한국 종목: 6자리 숫자면 Yahoo 형식으로 변환 (.KS 코스피 → 실패 시 .KQ 코스닥)
  const isKR = /^\d{6}$/.test(symbol);
  const candidates = isKR ? [`${symbol}.KS`, `${symbol}.KQ`] : [symbol];

  const fetchOne = async (sym) => {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(
      sym
    )}?interval=1d&range=5d`;
    const r = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        Accept: "application/json",
      },
    });
    if (!r.ok) return null;
    const json = await r.json();
    return json?.chart?.result?.[0] || null;
  };

  try {
    let result = null;
    for (const cand of candidates) {
      result = await fetchOne(cand);
      if (result) break;
    }
    if (!result) {
      res.status(404).json({ error: "no data" });
      return;
    }
    const meta = result.meta || {};
    const price = meta.regularMarketPrice ?? null;
    const prevClose = meta.chartPreviousClose ?? meta.previousClose ?? null;
    res.setHeader("Cache-Control", "s-maxage=20, stale-while-revalidate=40");
    res.status(200).json({ symbol, price, prevClose });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
}
