// Vercel Serverless: POST /api/init-ath
// 티커 추가 시 즉시 ATH ratchet 계산 → ath_state upsert

// Python engine의 build_ath_from_history와 동일한 로직:
// 기간 내 최고가를 ATH 기준으로 삼음 (ratchet 전체 적용 시 상승장에서 ATH 고정 버그 방지)
function buildAthFromHistory(closes, resetPct = 10) {
  const valid = closes.filter((c) => c != null && c > 0);
  if (!valid.length) return null;
  const ath = Math.max(...valid);
  const last = valid[valid.length - 1];
  return {
    ath,
    running_high: last,
    exceeded_threshold: last >= ath * (1 + resetPct / 100),
  };
}

const RANGE_MAP = {
  "1y": "1y", "2y": "2y", "3y": "5y", "4y": "5y", "5y": "5y",
  "6y": "10y", "7y": "10y", "8y": "10y", "9y": "10y", "10y": "10y",
  "52w": "1y", "all": "max",
};

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();

  const { ticker, resetPct = 10, lookback = "5y" } = req.body ?? {};
  const auth = req.headers.authorization;
  if (!ticker || !auth) return res.status(400).json({ error: "missing params" });

  const SUPABASE_URL  = process.env.VITE_SUPABASE_URL  || process.env.SUPABASE_URL;
  const SUPABASE_ANON = process.env.VITE_SUPABASE_PUBLISHABLE_KEY || process.env.VITE_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY;
  if (!SUPABASE_URL || !SUPABASE_ANON)
    return res.status(500).json({ error: "supabase config missing" });

  // 1. JWT 검증 → user_id 확인
  const uRes = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { apikey: SUPABASE_ANON, Authorization: auth },
  });
  if (!uRes.ok) return res.status(401).json({ error: "unauthorized" });
  const { id: uid } = await uRes.json();

  // 2. Yahoo Finance 히스토리 조회
  const range = RANGE_MAP[lookback] ?? "5y";
  const isKR  = /^\d{6}$/.test(ticker);
  const syms  = isKR ? [`${ticker}.KS`, `${ticker}.KQ`] : [ticker];

  let closes = null;
  for (const sym of syms) {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=${range}`,
      { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", Accept: "application/json" } }
    );
    if (!r.ok) continue;
    const json = await r.json();
    const raw  = json?.chart?.result?.[0]?.indicators?.quote?.[0]?.close ?? [];
    const valid = raw.filter((c) => c != null && c > 0);
    if (valid.length > 0) { closes = valid; break; }
  }
  if (!closes || closes.length === 0)
    return res.status(404).json({ error: "no history for " + ticker });

  // 3. ATH 계산 (기간 내 최고가 기준)
  const ratchet = buildAthFromHistory(closes, Number(resetPct));

  // 4. ath_state upsert (user JWT → RLS 통과)
  const upsertRes = await fetch(`${SUPABASE_URL}/rest/v1/ath_state`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_ANON,
      Authorization: auth,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify({
      user_id: uid,
      ticker,
      ...ratchet,
      baseline_level: 0,
      active_levels: [],
      level_last_alert: {},
      last_trade_day: null,
      updated_at: new Date().toISOString(),
    }),
  });

  if (!upsertRes.ok) {
    const err = await upsertRes.text();
    console.error("[init-ath] upsert failed:", err);
    return res.status(500).json({ error: "db write failed", detail: err.slice(0, 200) });
  }

  res.setHeader("Cache-Control", "no-store");
  res.status(200).json({ ticker, ...ratchet });
}
