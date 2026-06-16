// Vercel Serverless: /api/search?q=TSLA
// Yahoo Finance 검색 프록시 — 티커 자동완성용

export default async function handler(req, res) {
  const q = (req.query.q || "").trim();
  if (!q) { res.status(400).json({ error: "q required" }); return; }

  try {
    const url =
      `https://query1.finance.yahoo.com/v1/finance/search` +
      `?q=${encodeURIComponent(q)}&quotesCount=8&newsCount=0&enableFuzzyQuery=false`;
    const r = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        Accept: "application/json",
      },
    });
    if (!r.ok) { res.status(502).json({ error: "upstream" }); return; }
    const json = await r.json();
    const raw = json?.finance?.result?.[0]?.quotes ?? json?.quotes ?? [];
    const quotes = raw.map((item) => ({
      symbol: item.symbol,
      name: item.longname || item.shortname || item.symbol,
      type: item.quoteType,
      exchange: item.exchange,
    }));
    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=120");
    res.status(200).json({ quotes });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
}
