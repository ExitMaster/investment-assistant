// Vercel Serverless: /api/quotes?symbols=QQQ,SPY,^GSPC
// 배치 시세 조회 — 여러 심볼을 한 번에 요청하여 API 호출 최소화

const isKR = (sym) => /^\d{6}$/.test(sym);

// 현재가 날짜(거래소 로컬)보다 이전인 마지막 유효 일봉 종가 = 전일 종가.
// gmtoffset(초)으로 거래소 로컬 '일(day) 인덱스'를 계산해 비교한다. 장중 진행 봉이
// 배열에 없는 거래소(한국 등)에서 '마지막-1' 방식이 전일 종가를 하루 더 밀어내는 문제 방지.
function closePrevTradingDay(result, meta) {
  const ts = result.timestamp || [];
  const closes = result.indicators?.quote?.[0]?.close ?? [];
  const tz = meta.gmtoffset ?? 0; // 거래소 UTC 오프셋(초)
  const dayIdx = (epochSec) => Math.floor((epochSec + tz) / 86400);
  const refDay = meta.regularMarketTime != null ? dayIdx(meta.regularMarketTime) : null;
  for (let i = ts.length - 1; i >= 0; i--) {
    const c = closes[i];
    if (c == null || c <= 0) continue;
    if (refDay != null && dayIdx(ts[i]) >= refDay) continue; // 현재가와 같은(또는 이후) 날 봉은 제외
    return c;
  }
  return null;
}

async function fetchOne(sym) {
  const candidates = isKR(sym) ? [`${sym}.KS`, `${sym}.KQ`] : [sym];
  for (const cand of candidates) {
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(cand)}?interval=1d&range=5d`;
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
        closePrevTradingDay(result, meta) ??
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
