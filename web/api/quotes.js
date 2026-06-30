// Vercel Serverless: /api/quotes?symbols=QQQ,SPY,^GSPC
// 배치 시세 조회 — 여러 심볼을 한 번에 요청하여 API 호출 최소화

const isKR = (sym) => /^\d{6}$/.test(sym);

async function fetchOne(sym) {
  const candidates = isKR(sym) ? [`${sym}.KS`, `${sym}.KQ`] : [sym];
  for (const cand of candidates) {
    try {
      // range=1d 로 받으면 meta.chartPreviousClose 가 정확히 '직전 세션 종가'가 된다.
      // (range=5d 의 일봉 close 배열은 일부 지수에서 null/오류 값이 섞여 전일대비가 깨졌음.
      //  국내 티커는 regularMarketPreviousClose 메타도 None 이라 chartPreviousClose 가 유일하게 신뢰 가능.)
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(cand)}?interval=1d&range=1d`;
      const r = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
          Accept: "application/json",
        },
      });
      if (!r.ok) continue;
      const json = await r.json();
      const result = json?.chart?.result?.[0];
      if (!result) continue;
      const meta = result.meta || {};
      const price = meta.regularMarketPrice ?? null;
      if (!price) continue;
      const prevClose =
        meta.chartPreviousClose ??
        meta.regularMarketPreviousClose ??
        meta.previousClose ??
        null;
      const name = meta.longName || meta.shortName || meta.symbol || sym;
      return { price, prevClose, name };
    } catch {}
  }
  return null;
}

export default async function handler(req, res) {
  const raw = (req.query.symbols || "").trim();
  if (!raw) return res.status(400).json({ error: "symbols required" });
  const symbols = raw.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 30);

  const results = await Promise.all(symbols.map(fetchOne));
  const out = {};
  symbols.forEach((s, i) => { if (results[i]) out[s] = results[i]; });

  res.setHeader("Cache-Control", "s-maxage=8, stale-while-revalidate=15");
  res.status(200).json(out);
}
