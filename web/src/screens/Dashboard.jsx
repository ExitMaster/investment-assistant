import React, { useEffect, useState, useCallback } from "react";
import { supabase } from "../supabase.js";
import { getQuotes } from "../quotes.js";

function pct(now, base) {
  if (!base) return null;
  return ((now - base) / base) * 100;
}

function tvLink(sym) {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
}

export default function Dashboard({ profile, flash }) {
  const [settings, setSettings] = useState(null);
  const [watch, setWatch] = useState([]);
  const [athMap, setAthMap] = useState({});      // ticker -> ath row
  const [quotes, setQuotes] = useState({});       // ticker -> {price, prevClose}
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);

  // 설정·watchlist·ATH·알림 로드
  const loadAll = useCallback(async () => {
    const uid = profile.id;
    const [{ data: st }, { data: wl }, { data: aths }, { data: al }] = await Promise.all([
      supabase.from("settings").select("*").eq("user_id", uid).single(),
      supabase.from("watchlist").select("ticker").eq("user_id", uid),
      supabase.from("ath_state").select("*").eq("user_id", uid),
      supabase.from("alerts").select("*").eq("user_id", uid).order("created_at", { ascending: false }).limit(30),
    ]);
    setSettings(st);
    setWatch((wl ?? []).map((r) => r.ticker));
    const m = {};
    (aths ?? []).forEach((r) => { m[r.ticker] = r; });
    setAthMap(m);
    setAlerts(al ?? []);
    return st;
  }, [profile.id]);

  // 시세 갱신
  const refreshQuotes = useCallback(async (st, wl) => {
    const syms = new Set();
    if (st) { syms.add(st.index_ticker); if (st.display_ticker) syms.add(st.display_ticker); }
    (wl ?? []).forEach((t) => syms.add(t));
    if (syms.size === 0) return;
    const q = await getQuotes([...syms]);
    setQuotes(q);
    setUpdatedAt(new Date());
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const st = await loadAll();
      const { data: wl } = await supabase.from("watchlist").select("ticker").eq("user_id", profile.id);
      await refreshQuotes(st, (wl ?? []).map((r) => r.ticker));
      setLoading(false);
    })();
  }, [loadAll, refreshQuotes, profile.id]);

  // 30초마다 시세 자동 갱신
  useEffect(() => {
    if (!settings) return;
    const id = setInterval(() => refreshQuotes(settings, watch), 30000);
    return () => clearInterval(id);
  }, [settings, watch, refreshQuotes]);

  if (loading) return <div className="card"><p className="muted">불러오는 중…</p></div>;

  if (!settings) {
    return (
      <div className="card">
        <h2>시작하기</h2>
        <p className="muted">먼저 <b>설정</b> 탭에서 감시할 티커와 알림 기준을 저장하세요.</p>
      </div>
    );
  }

  // 상황판 행 구성: 지수 + display + watchlist
  const boardSyms = [];
  boardSyms.push({ sym: settings.index_ticker, role: "감시" });
  if (settings.display_ticker && settings.display_ticker !== settings.index_ticker)
    boardSyms.push({ sym: settings.display_ticker, role: "참고" });
  watch.forEach((t) => boardSyms.push({ sym: t, role: "관찰" }));

  return (
    <>
      <div className="card">
        <h2>
          상황판
          <span style={{ float: "right", fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>
            {updatedAt ? `갱신 ${updatedAt.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : ""}
          </span>
        </h2>

        {boardSyms.map(({ sym, role }) => {
          const q = quotes[sym];
          const ath = athMap[sym]?.ath ?? null;
          const price = q?.price ?? null;
          // ATH 대비 등락 (없으면 전일종가 대비)
          const base = ath ?? q?.prevClose ?? null;
          const change = price != null ? pct(price, base) : null;
          const isDown = change != null && change < 0;
          const nearBuy = change != null && change <= -(settings.drawdown_levels?.[0] ?? 10) + 1;

          return (
            <div className={`ticker-row ${nearBuy ? "alert" : ""}`} key={sym + role}>
              <div>
                <span className="t-sym">{sym}</span>
                <span className="chip">{role}</span>
                <div className="t-sub">
                  {ath ? `ATH ${ath.toFixed(2)}` : q?.prevClose ? `전일 ${q.prevClose.toFixed(2)}` : "기준 없음"}
                </div>
              </div>
              <div className="t-price mono">{price != null ? price.toFixed(2) : "—"}</div>
              <div className={`t-chg mono ${change == null ? "" : isDown ? "down" : "up"}`}>
                {change == null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
              </div>
            </div>
          );
        })}
        <p className="hint" style={{ marginTop: 10, fontSize: 12, color: "var(--text-faint)" }}>
          현재가는 30초마다 갱신됩니다. ATH가 비어 있으면 엔진이 처음 실행될 때 채워집니다.
        </p>
      </div>

      <div className="card">
        <h2>최근 알림</h2>
        {alerts.length === 0 ? (
          <p className="muted">아직 알림이 없습니다. 신호가 발생하면 여기와 텔레그램에 표시됩니다.</p>
        ) : (
          alerts.map((a) => (
            <div className="alert-item" key={a.id}>
              <span className="alert-time">
                {new Date(a.created_at).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
              </span>
              <span><b>{a.ticker}</b> {a.level}</span>
              <a className="alert-link" href={tvLink(a.ticker)} target="_blank" rel="noreferrer">차트 ↗</a>
            </div>
          ))
        )}
      </div>
    </>
  );
}
