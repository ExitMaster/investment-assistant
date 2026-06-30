// Vercel Serverless Function: /api/quote?symbol=QQQ
// 브라우저 → 이 함수(같은 도메인) → Yahoo (서버간, CORS 없음) → 시세 반환.

// 현재가 날짜(거래소 로컬)보다 이전인 마지막 유효 일봉 종가 = 전일 종가.
// gmtoffset(초)으로 거래소 로컬 '일(day) 인덱스'를 계산해 비교한다.
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

    // 전일 종가: 현재가(regularMarketTime) "거래소 날짜"보다 하루 이상 이전인 마지막 일봉 종가.
    // gmtoffset(거래소 UTC 오프셋, 초)으로 거래소 로컬 날짜 인덱스를 계산해 비교한다.
    // 단순히 close 배열의 '마지막-1'을 쓰면, 장중 진행 봉이 배열에 없는 거래소(한국 등)에서
    // 전일 종가가 하루 더 과거로 밀려 전일대비가 어긋난다.
    let prevClose = closePrevTradingDay(result, meta);
    prevClose = prevClose ?? meta.regularMarketPreviousClose ?? meta.previousClose ?? null;

    // 종목명
    const name =
      meta.longName || meta.shortName || meta.symbol || symbol;

    res.setHeader("Cache-Control", "s-maxage=20, stale-while-revalidate=40");
    res.status(200).json({ symbol, name, price, prevClose });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
}
