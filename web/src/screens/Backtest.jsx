import React, { useEffect, useMemo, useRef, useState } from "react";
import { supabase } from "../supabase.js";
import { runBacktest, SIGNAL_STYLE } from "../lib/signals.js";

const RANGES = [
  { v: "1y", label: "1년" },
  { v: "3y", label: "3년" },
  { v: "5y", label: "5년" },
];

// 신호 타입별 1:1 칩 (8종)
const GROUPS = [
  { key: "buy_level",    label: "ATH 매수",    color: "#22c55e" },
  { key: "sell",         label: "ATH 매도",    color: "#ef4444" },
  { key: "dmi_buy",      label: "DMI 매수",    color: "#3b82f6" },
  { key: "dmi_imminent", label: "DMI 신호임박", color: "#60a5fa" },
  { key: "bull_div",     label: "상승 Div",    color: "#14b8a6" },
  { key: "bear_div",     label: "하락 Div",    color: "#f97316" },
  { key: "low_vol",      label: "저점 Vol",    color: "#a855f7" },
  { key: "high_vol",     label: "고점 Vol",    color: "#eab308" },
];
const ALL_KEYS = GROUPS.map((g) => g.key);
// 타입 키와 그룹 키가 동일 (1:1)
const TYPE_TO_GROUP = Object.fromEntries(ALL_KEYS.map((k) => [k, k]));

function markersFor(events, enabled) {
  return events
    .filter((e) => enabled.has(TYPE_TO_GROUP[e.type]))
    .map((e) => {
      const s = SIGNAL_STYLE[e.type];
      return { time: e.time, position: s.position, color: s.color, shape: s.shape, text: s.text };
    });
}

export default function Backtest({ profile }) {
  const uid = profile.id;
  const [tickers, setTickers] = useState([]); // [{ticker,name}]
  const [ticker, setTicker] = useState("");
  const [range, setRange] = useState("3y");
  const [settings, setSettings] = useState(null);
  const [data, setData] = useState(null); // history
  const [result, setResult] = useState(null); // {events, athSeries}
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [enabled, setEnabled] = useState(() => new Set(ALL_KEYS));

  const chartRef = useRef(null);
  const chartObj = useRef(null);
  const candleRef = useRef(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  // 사용자 티커 + 설정 로드
  useEffect(() => {
    (async () => {
      const [{ data: idx }, { data: ind }, { data: wl }, { data: st }] = await Promise.all([
        supabase.from("index_tickers").select("ticker,name").eq("user_id", uid).order("sort_order"),
        supabase.from("indicator_tickers").select("ticker,name").eq("user_id", uid).order("sort_order"),
        supabase.from("watchlist").select("ticker,name").eq("user_id", uid).order("sort_order"),
        supabase.from("settings").select("*").eq("user_id", uid).single(),
      ]);
      const seen = new Set();
      const merged = [];
      for (const r of [...(idx || []), ...(ind || []), ...(wl || [])]) {
        if (seen.has(r.ticker)) continue;
        seen.add(r.ticker);
        merged.push(r);
      }
      setTickers(merged);
      setSettings(st || {});
      if (merged.length && !ticker) setTicker(merged[0].ticker);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);

  // 히스토리 조회 + 백테스트 실행
  useEffect(() => {
    if (!ticker || !settings) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setErr("");
      setResult(null);
      try {
        const r = await fetch(`/api/history?ticker=${encodeURIComponent(ticker)}&range=${range}`);
        if (!r.ok) throw new Error((await r.json()).error || "조회 실패");
        const hist = await r.json();
        if (cancelled) return;
        if (!hist.close || hist.close.length < 80) throw new Error("데이터가 부족합니다");
        setData(hist);
        const res = runBacktest(hist, {
          resetPct: settings.ath_reset_pct ?? 10,
          levels: settings.drawdown_levels ?? [10, 20, 30, 40],
          dmiThreshold: settings.dmi_threshold ?? 30,
          stochParams: settings.stoch_params ?? [5, 3, 3],
          volumeLookback: settings.volume_lookback_days ?? 126,
        });
        if (!cancelled) setResult(res);
      } catch (e) {
        if (!cancelled) setErr(String(e.message || e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [ticker, range, settings]);

  // 차트 렌더링 (데이터/결과 변경 시에만 재생성)
  useEffect(() => {
    if (!data || !result || !chartRef.current) return;
    let disposed = false;
    (async () => {
      const lc = await import("lightweight-charts");
      if (disposed || !chartRef.current) return;
      if (chartObj.current) { chartObj.current.remove(); chartObj.current = null; }

      const chart = lc.createChart(chartRef.current, {
        width: chartRef.current.clientWidth,
        height: 360,
        layout: { background: { color: "transparent" }, textColor: "#9aa4b2" },
        grid: { vertLines: { color: "rgba(255,255,255,0.05)" }, horzLines: { color: "rgba(255,255,255,0.05)" } },
        rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
        timeScale: { borderColor: "rgba(255,255,255,0.1)" },
        crosshair: { mode: lc.CrosshairMode ? lc.CrosshairMode.Normal : 0 },
      });
      chartObj.current = chart;

      const candle = chart.addCandlestickSeries({
        upColor: "#22c55e", downColor: "#ef4444",
        borderUpColor: "#22c55e", borderDownColor: "#ef4444",
        wickUpColor: "#22c55e", wickDownColor: "#ef4444",
      });
      candle.setData(data.time.map((t, i) => ({
        time: t, open: data.open[i], high: data.high[i], low: data.low[i], close: data.close[i],
      })));
      candleRef.current = candle;

      const athLine = chart.addLineSeries({
        color: "#eab308", lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
        lineStyle: lc.LineStyle ? lc.LineStyle.Dotted : 1,
      });
      athLine.setData(data.time.map((t, i) => ({ time: t, value: result.athSeries[i] })));

      candle.setMarkers(markersFor(result.events, enabledRef.current));
      chart.timeScale().fitContent();

      const ro = new ResizeObserver(() => {
        if (chartRef.current) chart.applyOptions({ width: chartRef.current.clientWidth });
      });
      ro.observe(chartRef.current);
      chart._ro = ro;
    })();
    return () => {
      disposed = true;
      candleRef.current = null;
      if (chartObj.current) {
        if (chartObj.current._ro) chartObj.current._ro.disconnect();
        chartObj.current.remove();
        chartObj.current = null;
      }
    };
  }, [data, result]);

  // 필터 변경 시: 차트 재생성 없이 마커만 갱신 (줌 유지)
  useEffect(() => {
    if (candleRef.current && result) {
      candleRef.current.setMarkers(markersFor(result.events, enabled));
    }
  }, [enabled, result]);

  const toggleGroup = (key) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };
  const allOn = enabled.size === ALL_KEYS.length;
  const toggleAll = () => setEnabled(allOn ? new Set() : new Set(ALL_KEYS));

  const visibleEvents = useMemo(
    () => (result ? result.events.filter((e) => enabled.has(TYPE_TO_GROUP[e.type])) : []),
    [result, enabled]
  );

  const summary = useMemo(() => {
    const c = { buy: 0, sell: 0, ind: 0 };
    for (const e of visibleEvents) {
      if (e.type === "buy_level") c.buy++;
      else if (e.type === "sell") c.sell++;
      else c.ind++;
    }
    return c;
  }, [visibleEvents]);

  const tname = tickers.find((t) => t.ticker === ticker)?.name;
  const isKR = /^\d{6}/.test(ticker);
  const fmtP = (v) =>
    v == null ? "" : isKR ? Math.round(v).toLocaleString("ko-KR")
      : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="bt-screen">
      <div className="bt-controls">
        <select value={ticker} onChange={(e) => setTicker(e.target.value)} className="bt-select">
          {tickers.length === 0 && <option value="">티커 없음</option>}
          {tickers.map((t) => (
            <option key={t.ticker} value={t.ticker}>
              {t.name ? `${t.ticker} · ${t.name}` : t.ticker}
            </option>
          ))}
        </select>
        <div className="bt-range">
          {RANGES.map((r) => (
            <button
              key={r.v}
              className={`bt-range-btn ${range === r.v ? "active" : ""}`}
              onClick={() => setRange(r.v)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {tname && <div className="bt-title">{tname}</div>}

      {/* 신호 종류 필터 */}
      <div className="bt-filters">
        <button className={`bt-chip bt-chip-all ${allOn ? "active" : ""}`} onClick={toggleAll}>
          전체
        </button>
        {GROUPS.map((g) => {
          const on = enabled.has(g.key);
          return (
            <button
              key={g.key}
              className={`bt-chip ${on ? "active" : ""}`}
              onClick={() => toggleGroup(g.key)}
              style={on ? { background: g.color, borderColor: "transparent", color: "#fff" } : { color: g.color }}
            >
              <span className="bt-chip-dot" style={{ background: g.color }} />
              {g.label}
            </button>
          );
        })}
      </div>

      {loading && <p className="muted bt-msg">불러오는 중…</p>}
      {err && <p className="bt-msg bt-err">⚠️ {err}</p>}

      <div ref={chartRef} className="bt-chart" style={{ display: data && result && !err ? "block" : "none" }} />

      {result && !err && (
        <>
          <div className="bt-summary">
            <span><b>{summary.buy}</b> 매수레벨</span>
            <span><b>{summary.sell}</b> 매도</span>
            <span><b>{summary.ind}</b> 보조지표</span>
            <span className="muted">노란선 = ATH 기준선</span>
          </div>

          <div className="bt-events">
            {visibleEvents.length === 0 && <p className="muted bt-msg">표시할 신호가 없습니다.</p>}
            {[...visibleEvents].reverse().map((e, i) => {
              const s = SIGNAL_STYLE[e.type];
              return (
                <div className="bt-event" key={i}>
                  <span className="bt-ev-date">{e.time}</span>
                  <span className="bt-ev-badge" style={{ background: s.color }}>{e.label}</span>
                  <span className="bt-ev-price mono">{fmtP(e.price)}</span>
                  <span className="bt-ev-reason">{e.reason}</span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
