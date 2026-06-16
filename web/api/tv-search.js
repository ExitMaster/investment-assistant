// Vercel Serverless: /api/tv-search?q=005930
// TradingView 심볼검색 프록시 — 한국어 종목명(description) + 정식 TV 심볼 매핑용.
// 한국 종목명을 한국어로 표시하는 데 사용한다. 실패 시 빈 배열.

export default async function handler(req, res) {
  const q = (req.query.q || "").trim();
  if (!q) { res.status(400).json({ error: "q required" }); return; }

  try {
    const url =
      `https://symbol-search.tradingview.com/symbol_search/?text=${encodeURIComponent(q)}` +
      `&hl=1&lang=ko&domain=production`;
    const r = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        Accept: "application/json",
        Origin: "https://www.tradingview.com",
        Referer: "https://www.tradingview.com/",
      },
    });
    if (!r.ok) { res.status(200).json({ quotes: [] }); return; }
    const raw = await r.json();
    const strip = (s) => (s || "").replace(/<\/?[^>]+>/g, "");
    const quotes = (Array.isArray(raw) ? raw : []).map((it) => ({
      symbol: strip(it.symbol),                         // 예: 005930
      exchange: it.exchange || "",                      // 예: KRX
      tvSymbol: `${it.exchange ? it.exchange + ":" : ""}${strip(it.symbol)}`,
      description: strip(it.description),                // 예: 삼성전자 (한국어)
      type: it.type || "",
    }));
    res.setHeader("Cache-Control", "s-maxage=86400, stale-while-revalidate=172800");
    res.status(200).json({ quotes });
  } catch (e) {
    res.status(200).json({ quotes: [] });
  }
}
