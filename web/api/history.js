// Vercel Serverless Function: /api/history?ticker=QQQ&range=2y
// 브라우저 → 이 함수(같은 도메인) → Yahoo (서버간, CORS 없음) → 일봉 OHLCV 반환.
// 백테스트 시각화용. init-ath.js와 동일한 Yahoo chart 패턴.

const RANGE_OK = new Set(["6mo", "1y", "2y", "5y", "10y", "max"]);

export default async function handler(req, res) {
  const ticker = (req.query.ticker || "").trim();
  const range = RANGE_OK.has(req.query.range) ? req.query.range : "2y";
  if (!ticker) {
    res.status(400).json({ error: "ticker required" });
    return;
  }

  const isKR = /^\d{6}$/.test(ticker);
  const candidates = isKR ? [`${ticker}.KS`, `${ticker}.KQ`] : [ticker];

  const fetchOne = async (sym) => {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(
      sym
    )}?interval=1d&range=${range}`;
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
      res.status(404).json({ error: "no data for " + ticker });
      return;
    }

    const meta = result.meta || {};
    const ts = result.timestamp || [];
    const q = result.indicators?.quote?.[0] || {};
    const o = q.open || [], h = q.high || [], l = q.low || [], c = q.close || [], v = q.volume || [];

    const out = { time: [], open: [], high: [], low: [], close: [], volume: [] };
    for (let i = 0; i < ts.length; i++) {
      // 결측 봉 제외 (Yahoo는 일부 봉을 null로 채움)
      if (c[i] == null || c[i] <= 0 || o[i] == null || h[i] == null || l[i] == null) continue;
      const d = new Date(ts[i] * 1000);
      const iso = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(
        d.getUTCDate()
      ).padStart(2, "0")}`;
      out.time.push(iso);
      out.open.push(o[i]);
      out.high.push(h[i]);
      out.low.push(l[i]);
      out.close.push(c[i]);
      out.volume.push(v[i] ?? 0);
    }

    const name = meta.longName || meta.shortName || meta.symbol || ticker;
    res.setHeader("Cache-Control", "s-maxage=3600, stale-while-revalidate=7200");
    res.status(200).json({ ticker, name, ...out });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
}
