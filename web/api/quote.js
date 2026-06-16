// Vercel Serverless Function: /api/quote?symbol=QQQ
// 브라우저 → 이 함수(같은 도메인) → Yahoo (서버간, CORS 없음) → 시세 반환.

export default async function handler(req, res) {
  const symbol = (req.query.symbol || "").trim();
  if (!symbol) {
    res.status(400).json({ error: "symbol required" });
    return;
  }

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

    // 전일 종가: 차트 데이터의 실제 확정 종가에서 직전 거래일 값을 사용.
    // meta.regularMarketPreviousClose는 장중에 부정확한 경우가 있어 보조 수단으로만 사용.
    const rawCloses = result.indicators?.quote?.[0]?.close ?? [];
    const validCloses = rawCloses.filter((c) => c != null && c > 0);
    const chartPrev = validCloses.length >= 2 ? validCloses[validCloses.length - 2] : null;
    let prevClose =
      chartPrev ??
      meta.regularMarketPreviousClose ??
      meta.previousClose ??
      null;

    // 종목명
    const name =
      meta.longName || meta.shortName || meta.symbol || symbol;

    res.setHeader("Cache-Control", "s-maxage=20, stale-while-revalidate=40");
    res.status(200).json({ symbol, name, price, prevClose });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
}
