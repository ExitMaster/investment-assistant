// Vercel Serverless: /api/quotes?symbols=QQQ,SPY,^GSPC
// 배치 시세 조회 — 여러 심볼을 한 번에 요청하여 API 호출 최소화.
// 국내 지수/종목(KOSPI·KOSDAQ·^KS11·^KQ11·6자리코드)은 네이버(공식 등락률 직접 제공),
// 그 외(미국·환율 등)는 Yahoo. 반환: { price, prevClose, name[, changePct] }

import { naverKind, naverQuote } from "../lib/naver.js";

async function fetchOne(sym) {
  if (naverKind(sym)) return naverQuote(sym);   // 국내 → 네이버
  try {                                          // 그 외 → Yahoo
    // range=1d 의 chartPreviousClose 가 정확히 직전 세션 종가.
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=1d`;
    const r = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        Accept: "application/json",
      },
    });
    if (!r.ok) return null;
    const json = await r.json();
    const meta = json?.chart?.result?.[0]?.meta;
    const price = meta?.regularMarketPrice ?? null;
    if (!price) return null;
    const prevClose = meta.chartPreviousClose ?? meta.regularMarketPreviousClose ?? meta.previousClose ?? null;
    const name = meta.longName || meta.shortName || meta.symbol || sym;
    return { price, prevClose, name };
  } catch {
    return null;
  }
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
