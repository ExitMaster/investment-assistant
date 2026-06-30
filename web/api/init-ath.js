// Vercel Serverless: POST /api/init-ath
// 티커 추가 시 즉시 ATH ratchet 계산 → ath_state upsert

// Python engine의 compute_ath_state와 동일한 로직 (확정 고점 방식):
// 어떤 고점에서 resetPct% 눌림이 나오면 그 고점을 ATH로 확정, 위로만 갱신.
// 상승장에서 resetPct% 미만 눌림·재상승 반복 시 직전 확정 고점 유지.
// 구간 내 조정이 한 번도 없으면 종가 최고값으로 폴백.
function buildAthFromHistory(closes, resetPct = 10) {
  const vals = closes.filter((c) => c != null && c > 0).map(Number);
  if (!vals.length) return null;
  const r = resetPct / 100;

  let ath = null;
  let peak = vals[0]; // 현재 미확정 구간의 고점
  for (const c of vals) {
    if (c > peak) peak = c;
    if (c <= peak * (1 - r)) {
      // peak 대비 resetPct% 눌림 → 확정 (위로만)
      ath = ath === null ? peak : Math.max(ath, peak);
      peak = c; // 눌림 지점부터 새 구간 시작
    }
  }
  if (ath === null) ath = Math.max(...vals); // 조정 없던 예외 → 폴백

  return {
    ath,
    running_high: peak,
    exceeded_threshold: peak > ath,
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
    const result = json?.chart?.result?.[0];
    // 국내 코드는 .KS/.KQ 둘 다 응답하되 한쪽은 코드만 같은 펀드 → EQUITY만 채택
    if (isKR && result?.meta?.instrumentType && result.meta.instrumentType !== "EQUITY") continue;
    const raw  = result?.indicators?.quote?.[0]?.close ?? [];
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
      // 어떤 설정값으로 계산했는지 기록 → 엔진이 헛-재계산하지 않도록(설정 변경 감지용)
      reset_pct_used: Number(resetPct),
      lookback_used: lookback,
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
