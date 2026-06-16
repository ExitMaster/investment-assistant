import React, { useEffect, useState, useCallback, useRef } from "react";
import { supabase } from "../supabase.js";
import { getQuotes, searchTickers } from "../quotes.js";

/* ── 유틸 ── */
function pct(a, b) {
  if (!a || !b) return null;
  return ((a - b) / b) * 100;
}
function fmtPct(v, digits = 2) {
  if (v == null) return null;
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}
function tvLink(sym) {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
}
function isKR(sym) { return /^\d{6}/.test((sym || "").split(".")[0]); }

// 대표 지수 티커 → 친숙한 이름
const INDEX_NAMES = {
  "^KS11": "KOSPI",
  "^KQ11": "KOSDAQ",
  "^KS200": "KOSPI 200",
  "^IXIC": "NASDAQ",
  "^NDX": "NASDAQ 100",
  "^GSPC": "S&P 500",
  "^DJI": "다우존스",
  "^RUT": "러셀 2000",
  "^VIX": "VIX",
  "^SOX": "필라델피아 반도체",
  "USDKRW=X": "달러/원",
};
function displaySym(sym) {
  if (INDEX_NAMES[sym]) return INDEX_NAMES[sym];
  return sym.replace(/\.(KS|KQ)$/, "");
}
function fmtPrice(v, sym, showCurrency = false) {
  if (v == null) return null;
  const kr = isKR(sym);
  const isIdx = /^\^/.test(sym) || sym.includes("=X");  // 지수·환율은 통화 표기 없음
  const formatted = kr
    ? Math.round(v).toLocaleString("ko-KR")
    : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (!showCurrency || isIdx) return formatted;
  return `${kr ? "KRW" : "USD"} ${formatted}`;
}

/* ── SVG 아이콘 ── */
const PlusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);
const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
const InfoIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);
const RefreshIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);
const GearIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const GripIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="9" cy="6" r="1" fill="currentColor" stroke="none"/>
    <circle cx="15" cy="6" r="1" fill="currentColor" stroke="none"/>
    <circle cx="9" cy="12" r="1" fill="currentColor" stroke="none"/>
    <circle cx="15" cy="12" r="1" fill="currentColor" stroke="none"/>
    <circle cx="9" cy="18" r="1" fill="currentColor" stroke="none"/>
    <circle cx="15" cy="18" r="1" fill="currentColor" stroke="none"/>
  </svg>
);
const EditIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);

/* ── 드래그 정렬 훅 (데스크톱 HTML5 + 모바일 long-press, edit 모드 전용) ── */
function useDragSort(externalItems, onCommit, enabled) {
  const [list, setList] = useState(externalItems);
  const [activeIdx, setActiveIdx] = useState(null);
  const [overIdx, setOverIdx] = useState(null);
  const containerRef = useRef(null);
  // 모든 가변 상태를 단일 ref에 보관 (useEffect 내 stale closure 완전 방지)
  const s = useRef({
    active: false, from: null, over: null,
    startX: 0, startY: 0,
    timer: null,
    list: externalItems,
    onCommit,
  });

  useEffect(() => { s.current.onCommit = onCommit; }, [onCommit]);
  useEffect(() => { s.current.list = externalItems; setList(externalItems); }, [externalItems]);

  function doCommit(from, to) {
    if (from == null || to == null || from === to) return;
    const next = [...s.current.list];
    const [x] = next.splice(from, 1);
    next.splice(to, 0, x);
    s.current.list = next;
    setList(next);
    s.current.onCommit?.(next);
  }

  // rowProps: 데스크톱 draggable + 모바일 long-press (행 전체에 적용)
  function rowProps(idx) {
    if (!enabled) return { "data-row-idx": String(idx) };
    return {
      draggable: true,
      "data-row-idx": String(idx),
      onDragStart: () => { s.current.from = idx; setActiveIdx(idx); },
      onDragOver: (e) => {
        e.preventDefault();
        if (idx !== s.current.from) { s.current.over = idx; setOverIdx(idx); }
      },
      onDrop: (e) => {
        e.preventDefault();
        doCommit(s.current.from, s.current.over);
        s.current.from = null; s.current.over = null;
        setActiveIdx(null); setOverIdx(null);
      },
      onDragEnd: () => {
        s.current.from = null; s.current.over = null;
        setActiveIdx(null); setOverIdx(null);
      },
      onTouchStart: (e) => {
        const t = e.touches[0];
        s.current.startX = t.clientX;
        s.current.startY = t.clientY;
        s.current.active = false;
        clearTimeout(s.current.timer);
        s.current.timer = setTimeout(() => {
          s.current.active = true;
          s.current.from = idx;
          s.current.over = idx;
          setActiveIdx(idx);
          setOverIdx(idx);
          try { navigator.vibrate(40); } catch {}
        }, 450);
      },
    };
  }

  // 전역 터치 이벤트 — 드래그 중 스크롤 방지 + 타겟 행 감지 + 커밋
  useEffect(() => {
    function onMove(e) {
      const t = e.touches[0];
      if (!s.current.active) {
        const dx = Math.abs(t.clientX - s.current.startX);
        const dy = Math.abs(t.clientY - s.current.startY);
        if (dx > 8 || dy > 8) { clearTimeout(s.current.timer); }
        return;
      }
      e.preventDefault();
      // 손가락 좌표 아래의 실제 DOM 요소를 찾아 그 행 인덱스를 사용 (rect 루프보다 정확)
      const el = document.elementFromPoint(t.clientX, t.clientY);
      const row = el?.closest?.("[data-row-idx]");
      if (row && containerRef.current?.contains(row)) {
        const i = +row.dataset.rowIdx;
        if (!Number.isNaN(i) && i !== s.current.over) { s.current.over = i; setOverIdx(i); }
      }
    }
    function onEnd() {
      clearTimeout(s.current.timer);
      if (s.current.active) {
        doCommit(s.current.from, s.current.over);
      }
      s.current.active = false;
      s.current.from = null;
      s.current.over = null;
      setActiveIdx(null);
      setOverIdx(null);
    }
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd);
    document.addEventListener("touchcancel", onEnd);
    return () => {
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
  }, []); // ref만 사용 — deps 없음

  return { list, containerRef, activeIdx, overIdx, rowProps };
}


const DEFAULT_MARQUEE = [
  { symbol: "^IXIC",    label: "NASDAQ" },
  { symbol: "^GSPC",    label: "S&P500" },
  { symbol: "^DJI",     label: "DOW" },
  { symbol: "^KS11",    label: "KOSPI" },
  { symbol: "^KQ11",    label: "KOSDAQ" },
  { symbol: "USDKRW=X", label: "USD/KRW" },
];

/* ── 전광판 ── */
export function MarqueeTape({ uid }) {
  const [items, setItems] = useState([]);        // { symbol, label, enabled }
  const [prices, setPrices] = useState({});
  const [showPanel, setShowPanel] = useState(false);
  const [addSym, setAddSym] = useState("");
  const [dragIdx, setDragIdx] = useState(null);
  const timer = useRef(null);

  // DB에서 marquee_tickers 로드 (없으면 기본값 삽입)
  useEffect(() => {
    if (!uid) return;
    (async () => {
      const { data } = await supabase
        .from("marquee_tickers")
        .select("symbol,enabled,sort_order")
        .eq("user_id", uid)
        .order("sort_order");
      if (data && data.length > 0) {
        const merged = data.map((r) => ({
          symbol: r.symbol,
          label: DEFAULT_MARQUEE.find((d) => d.symbol === r.symbol)?.label || r.symbol,
          enabled: r.enabled,
        }));
        setItems(merged);
      } else {
        // 기본값 삽입
        const rows = DEFAULT_MARQUEE.map((d, i) => ({
          user_id: uid, symbol: d.symbol, enabled: true, sort_order: i,
        }));
        await supabase.from("marquee_tickers").insert(rows);
        setItems(DEFAULT_MARQUEE.map((d) => ({ ...d, enabled: true })));
      }
    })();
  }, [uid]);

  const fetchPrices = useCallback(async () => {
    const syms = items.filter((i) => i.enabled).map((i) => i.symbol);
    if (!syms.length) return;
    const q = await getQuotes(syms);
    setPrices(q);
  }, [items]);

  useEffect(() => {
    fetchPrices();
    clearInterval(timer.current);
    timer.current = setInterval(fetchPrices, 30000);
    return () => clearInterval(timer.current);
  }, [fetchPrices]);

  async function toggleItem(symbol, enabled) {
    const next = items.map((i) => i.symbol === symbol ? { ...i, enabled } : i);
    setItems(next);
    await supabase.from("marquee_tickers")
      .update({ enabled })
      .eq("user_id", uid).eq("symbol", symbol);
  }

  async function addCustom() {
    const sym = addSym.trim().toUpperCase();
    if (!sym || items.find((i) => i.symbol === sym)) { setAddSym(""); return; }
    const newItem = { symbol: sym, label: sym, enabled: true };
    const next = [...items, newItem];
    setItems(next);
    setAddSym("");
    await supabase.from("marquee_tickers").insert({
      user_id: uid, symbol: sym, enabled: true, sort_order: next.length - 1,
    });
  }

  async function removeItem(symbol) {
    setItems((prev) => prev.filter((i) => i.symbol !== symbol));
    await supabase.from("marquee_tickers")
      .delete().eq("user_id", uid).eq("symbol", symbol);
  }

  function onDragStart(idx) { setDragIdx(idx); }
  function onDragOver(e, idx) {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) return;
    const next = [...items];
    const [moved] = next.splice(dragIdx, 1);
    next.splice(idx, 0, moved);
    setItems(next);
    setDragIdx(idx);
  }
  async function onDragEnd() {
    setDragIdx(null);
    await Promise.all(items.map((item, i) =>
      supabase.from("marquee_tickers").update({ sort_order: i })
        .eq("user_id", uid).eq("symbol", item.symbol)
    ));
  }

  const visible = items.filter((i) => i.enabled);

  const itemEls = visible.map((item) => {
    const q = prices[item.symbol];
    const dayChg = q ? pct(q.price, q.prevClose) : null;
    const chgClass = dayChg == null ? "neutral" : dayChg >= 0 ? "up" : "down";
    return (
      <div key={item.symbol} className="marquee-item">
        <span className="marquee-label">{item.label}</span>
        {q?.price != null ? (
          <>
            <span className={`marquee-price ${chgClass}`}>
              {isKR(item.symbol)
                ? Math.round(q.price).toLocaleString("ko-KR")
                : q.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            {dayChg != null && (
              <span className={`badge ${chgClass}`} style={{ fontSize: 10 }}>{fmtPct(dayChg)}</span>
            )}
          </>
        ) : (
          <span className="marquee-price" style={{ color: "var(--text-faint)" }}>—</span>
        )}
      </div>
    );
  });

  // 항목당 6초 속도로 느리게 연속 스크롤 (Bloomberg 티커 스타일)
  const n = visible.length || 1;
  const duration = n * 6;

  return (
    <>
      <div className="marquee-wrap" style={{ position: "relative" }}>
        <div className="marquee-scroll" style={{ overflow: "hidden" }}>
          <div
            className="marquee-track"
            style={{ animationDuration: `${duration}s` }}
          >
            {itemEls}
            {itemEls}
          </div>
        </div>
        <div className="marquee-gear">
          <button
            className="icon-btn-sm"
            onClick={() => setShowPanel((v) => !v)}
            title="전광판 설정"
            style={{ color: showPanel ? "var(--accent)" : undefined }}
          >
            <GearIcon />
          </button>
        </div>
      </div>

      {showPanel && (
        <div className="marquee-panel">
          <p className="marquee-panel-title">지수 전광판 설정 · 드래그로 순서 변경</p>
          {items.map((item, i) => (
            <div
              key={item.symbol}
              className="marquee-toggle-row"
              draggable
              onDragStart={() => onDragStart(i)}
              onDragOver={(e) => onDragOver(e, i)}
              onDragEnd={onDragEnd}
              style={{ cursor: "grab", opacity: dragIdx === i ? 0.4 : 1 }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "var(--text-faint)", fontSize: 14, lineHeight: 1 }}>⠿</span>
                {item.label || item.symbol}
              </span>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <label className="switch" style={{ width: 36, height: 20 }}>
                  <input
                    type="checkbox"
                    checked={item.enabled}
                    onChange={(e) => toggleItem(item.symbol, e.target.checked)}
                  />
                  <span style={{ borderRadius: 999 }} />
                </label>
                {!DEFAULT_MARQUEE.find((d) => d.symbol === item.symbol) && (
                  <button className="icon-btn-sm danger" onClick={() => removeItem(item.symbol)}>
                    <XIcon />
                  </button>
                )}
              </div>
            </div>
          ))}
          <div className="row-inline" style={{ marginTop: 10 }}>
            <input
              value={addSym}
              onChange={(e) => setAddSym(e.target.value)}
              placeholder="심볼 추가 (예: BTC-USD)"
              style={{ flex: 1, fontSize: 13 }}
              onKeyDown={(e) => e.key === "Enter" && addCustom()}
            />
            <button className="btn-ghost" style={{ fontSize: 12 }} onClick={addCustom}>추가</button>
          </div>
        </div>
      )}
    </>
  );
}

/* ── 자동완성 검색 인풋 ── */
function TickerSearch({ onSelect, onCancel, placeholder, hint }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);

  function handleChange(e) {
    const v = e.target.value;
    setQ(v);
    clearTimeout(timer.current);
    if (!v.trim()) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      setBusy(true);
      const found = await searchTickers(v);
      setResults(found);
      setBusy(false);
    }, 300);
  }

  return (
    <div className="ticker-search-wrap">
      <div className="row-inline">
        <div style={{ position: "relative", flex: 1 }}>
          <input
            autoFocus
            value={q}
            onChange={handleChange}
            placeholder={placeholder || "티커 또는 종목명 검색…"}
            style={{ width: "100%", fontSize: 14 }}
          />
          {(results.length > 0 || busy) && (
            <div className="search-dropdown">
              {busy && <div className="search-item muted">검색 중…</div>}
              {results.map((r) => (
                <button key={r.symbol} className="search-item" onClick={() => onSelect(r)}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{displaySym(r.symbol)}</span>
                  <span style={{ color: "var(--text-dim)", fontSize: 12, marginLeft: 6 }}>{r.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="btn-ghost" style={{ whiteSpace: "nowrap", fontSize: 13 }} onClick={onCancel}>
          취소
        </button>
      </div>
      {hint && <p className="hint" style={{ marginTop: 6 }}>{hint}</p>}
    </div>
  );
}

const ChevronIcon = ({ open }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

/* ── 상태 게이지 (ATH 대비 위치 시각화, 동적 윈도우) ── */
function buildGaugeWindow(c, buyLevels) {
  const maxBuy = Math.max(...buyLevels);
  let lo = Math.floor(c / 10) * 10;
  let hi = lo + 10;
  if (Math.abs(c) < 10) { lo = -20; hi = 20; }       // ATH 부근: 대칭
  else if (c < 0) { hi = Math.max(hi, 10); lo = lo - 10; }  // 하락: 반대(위)는 +10까지, 현재쪽 1눈금 더
  else { lo = Math.min(lo, -10); hi = hi + 10; }     // 상승: 반대(아래)는 -10까지, 현재쪽 1눈금 더
  lo = Math.max(lo, -maxBuy);   // 매수쪽은 가장 깊은 레벨에서 멈춤
  lo = Math.min(lo, -10);       // ATH ±10 은 항상 노출
  hi = Math.max(hi, 10);
  const marks = [];
  for (let v = lo; v <= hi + 0.001; v += 10) marks.push(Math.round(v));
  return { lo, hi, marks };
}

function computeGauge(price, ath, prevClose, buyLevels) {
  if (price == null || ath == null || ath <= 0) return null;
  const c = ((price - ath) / ath) * 100;
  const { lo, hi, marks } = buildGaugeWindow(c, buyLevels);
  const span = hi - lo || 1;
  const posOf = (v) => ((Math.min(Math.max(v, lo), hi) - lo) / span) * 100;
  // 남은 거리는 직전 장마감 종가 기준(증권사 등락률과 동일 기준)으로 계산
  const base = prevClose && prevClose > 0 ? prevClose : price;

  let caption, capDir;
  if (c < 0) {
    const negs = buyLevels.map((L) => -L).sort((a, b) => b - a);   // -10,-20,…
    const deeper = negs.filter((L) => L < c - 0.001);
    if (deeper.length) {
      const next = deeper[0];                       // 도달할 다음 매수레벨(ATH 대비)
      const target = ath * (1 + next / 100);        // 그 레벨의 목표 가격
      const distPp = ((target - price) / base) * 100;  // 직전 종가 대비 추가 등락폭
      caption = `다음 매수 ${next}% · ${distPp >= 0 ? "+" : ""}${distPp.toFixed(1)}%p`;
    } else {
      caption = "최대 매수레벨 도달";
    }
    capDir = "down";
  } else {
    const next = Math.floor(c / 10) * 10 + 10;
    const target = ath * (1 + next / 100);
    const distPp = ((target - price) / base) * 100;
    caption = `다음 매도 +${next}% · +${distPp.toFixed(1)}%p`;
    capDir = "up";
  }
  return { c, lo, hi, marks, posOf, caption, capDir };
}

function StatusGauge({ price, ath, prevClose, sym, buyLevels }) {
  const g = computeGauge(price, ath, prevClose, buyLevels);
  if (!g) return <div className="gauge-empty">ATH 계산 중…</div>;
  const markerLeft = g.posOf(g.c);
  const zeroLeft = g.posOf(0);
  const fillColor = g.c < 0 ? "var(--down)" : "var(--up)";
  return (
    <div className="gauge">
      <div className="gauge-head">
        <span className="gauge-side">매수</span>
        <span className="gauge-ath">ATH {fmtPrice(ath, sym)}</span>
        <span className="gauge-side">매도</span>
      </div>
      <div className="gauge-track">
        <div className="gauge-fill" style={{
          left: `${Math.min(zeroLeft, markerLeft)}%`,
          width: `${Math.abs(markerLeft - zeroLeft)}%`,
          background: fillColor,
        }} />
        {g.marks.map((m) => (
          <div key={m} className={`gauge-tick ${m === 0 ? "ath" : ""}`} style={{ left: `${g.posOf(m)}%` }}>
            <span className="gauge-tick-label">{m === 0 ? "ATH" : m > 0 ? `+${m}` : m}</span>
          </div>
        ))}
        <div className="gauge-marker" style={{ left: `${markerLeft}%`, color: fillColor }}>▲</div>
      </div>
      <div className="gauge-foot">
        <span className="gauge-cur">현재 {fmtPrice(price, sym, true)} ({g.c >= 0 ? "+" : ""}{g.c.toFixed(1)}%)</span>
        <span className="gauge-cap" style={{ color: g.capDir === "down" ? "var(--down)" : "var(--up)" }}>{g.caption}</span>
      </div>
    </div>
  );
}

/* ── 티커 한 행 ── */
function TickerRow({ sym, quotes, athMap, onRemove, editMode, dragRowProps, isDragging, isDragOver,
                    showGauge, expanded, onToggle, buyLevels }) {
  const q = quotes[sym];
  const athRow = athMap[sym];
  const ath = athRow?.ath ?? null;
  const price = q?.price ?? null;
  const prevClose = q?.prevClose ?? null;
  const name = q?.name && q.name !== sym && q.name !== displaySym(sym) ? q.name : null;
  const dayChg = pct(price, prevClose);
  const athChg = pct(price, ath);

  const priceClass = dayChg == null ? "neutral" : dayChg >= 0 ? "up" : "down";
  const dsym = displaySym(sym);
  const canExpand = showGauge && !editMode && onToggle;

  return (
    <>
      <div
        className="ticker-row"
        style={{
          gridTemplateColumns: editMode ? "18px 1fr auto auto" : "1fr auto auto",
          opacity: isDragging ? 0.3 : 1,
          borderTop: isDragOver ? "2px solid var(--accent)" : undefined,
          marginTop: isDragOver ? -1 : undefined,
          transition: "opacity 0.15s",
          cursor: editMode ? "grab" : canExpand ? "pointer" : "default",
          userSelect: editMode ? "none" : undefined,
        }}
        {...(dragRowProps ?? {})}
        onClick={canExpand ? () => onToggle(sym) : undefined}
      >
        {editMode && (
          <div className="drag-handle" title="드래그하여 순서 변경">
            <GripIcon />
          </div>
        )}

        <div className="t-info">
          <a className="t-sym" href={tvLink(sym)} target="_blank" rel="noreferrer"
             onClick={(e) => e.stopPropagation()}>{dsym}</a>
          {name && <div className="t-name">{name}</div>}
        </div>

        <div className="t-data">
          <div className="t-price-row">
            {price != null && (
              <span className={`t-price mono ${priceClass}`}>{fmtPrice(price, sym, true)}</span>
            )}
            {dayChg != null && (
              <span className={`badge ${priceClass}`}>{fmtPct(dayChg)}</span>
            )}
          </div>
          {ath != null && (
            <div className="t-ath-row">
              <span className="t-ath-label">ATH</span>
              <span className="t-ath-price mono">{fmtPrice(ath, sym)}</span>
              {athChg != null && (
                <span className={`badge ${athChg >= 0 ? "up" : "down"}`} style={{ fontSize: 10 }}>{fmtPct(athChg)}</span>
              )}
            </div>
          )}
        </div>

        <div className="t-actions">
          {editMode && onRemove && (
            <button className="icon-btn-sm danger" onClick={(e) => { e.stopPropagation(); onRemove(sym); }} title="삭제"><XIcon /></button>
          )}
          {canExpand && (
            <span className="t-chevron" style={{ color: expanded ? "var(--accent)" : "var(--text-faint)" }}>
              <ChevronIcon open={expanded} />
            </span>
          )}
        </div>
      </div>

      {showGauge && expanded && !editMode && (
        <div className="gauge-row">
          <StatusGauge price={price} ath={ath} prevClose={prevClose} sym={sym} buyLevels={buyLevels} />
        </div>
      )}
    </>
  );
}

/* ── 섹션 카드 ── */
function SectionCard({
  title, note,
  tickers, quotes, athMap,
  onRemove, onRefreshAll, onReorder,
  onAdd, addDisabled, addLabel,
  adding, onCancelAdd, onSelectAdd,
  searchPlaceholder, searchHint,
  withGauge, buyLevels,
}) {
  const [showNote, setShowNote] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set());
  const { list, containerRef, activeIdx, overIdx, rowProps } = useDragSort(tickers, onReorder, editMode);

  function toggleExpand(sym) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(sym) ? next.delete(sym) : next.add(sym);
      return next;
    });
  }

  async function handleRefreshAll() {
    if (!onRefreshAll || refreshing) return;
    setRefreshing(true);
    await onRefreshAll(tickers);
    setRefreshing(false);
  }

  return (
    <div className="card">
      <div className="section-header">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <h2 style={{ marginBottom: 0 }}>{title}</h2>
          {note && (
            <button
              className="icon-btn-sm"
              onClick={() => setShowNote((v) => !v)}
              title="설명"
              style={{ color: showNote ? "var(--accent)" : undefined }}
            >
              <InfoIcon />
            </button>
          )}
        </div>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {onRefreshAll && tickers.length > 0 && !editMode && (
            <button
              className="icon-btn-sm"
              onClick={handleRefreshAll}
              title="ATH 전체 재계산"
              style={{ opacity: refreshing ? 0.4 : 1 }}
            >
              <RefreshIcon />
            </button>
          )}
          {tickers.length > 0 && (
            <button
              className="icon-btn-sm"
              onClick={() => setEditMode((v) => !v)}
              title={editMode ? "편집 완료" : "순서·삭제 편집"}
              style={{ color: editMode ? "var(--accent)" : undefined }}
            >
              <EditIcon />
            </button>
          )}
          {!editMode && onAdd && (
            <button
              className="icon-btn"
              onClick={onAdd}
              disabled={addDisabled}
              title="추가"
              style={{ flexShrink: 0 }}
            >
              <PlusIcon />
              {addLabel && <span style={{ fontSize: 10, marginLeft: 3 }}>{addLabel}</span>}
            </button>
          )}
        </div>
      </div>
      {showNote && note && <p className="section-note">{note}</p>}
      {editMode && (
        <p className="hint" style={{ fontSize: 11, marginTop: 4, marginBottom: 0 }}>
          행을 길게 눌러 순서 변경 · X로 삭제
        </p>
      )}

      {tickers.length === 0 && !adding && (
        <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
          + 버튼으로 티커를 추가하세요.
        </p>
      )}

      <div ref={containerRef}>
        {list.map((sym, idx) => (
          <TickerRow
            key={sym}
            sym={sym}
            quotes={quotes}
            athMap={athMap}
            onRemove={onRemove}
            editMode={editMode}
            dragRowProps={editMode && onReorder ? rowProps(idx) : { "data-row-idx": String(idx) }}
            isDragging={editMode && activeIdx === idx}
            isDragOver={editMode && overIdx === idx && activeIdx !== idx}
            showGauge={withGauge}
            expanded={expanded.has(sym)}
            onToggle={toggleExpand}
            buyLevels={buyLevels}
          />
        ))}
      </div>

      {!editMode && adding && (
        <div style={{ marginTop: 12 }}>
          <TickerSearch
            onSelect={onSelectAdd}
            onCancel={onCancelAdd}
            placeholder={searchPlaceholder}
            hint={searchHint}
          />
        </div>
      )}
    </div>
  );
}

/* ══ 대시보드 ══ */
export default function Dashboard({ profile, flash }) {
  const [settings, setSettings] = useState(null);
  const [indexTickers, setIndexTickers] = useState([]);
  const [indicatorTickers, setIndicatorTickers] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [athMap, setAthMap] = useState({});
  const [quotes, setQuotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [addingTo, setAddingTo] = useState(null);
  const quoteTimer = useRef(null);

  const uid = profile.id;

  const loadAll = useCallback(async () => {
    const [{ data: st }, { data: ix }, { data: ind }, { data: wl }, { data: aths }] =
      await Promise.all([
        supabase.from("settings").select("*").eq("user_id", uid).single(),
        supabase.from("index_tickers").select("ticker,name").eq("user_id", uid).order("sort_order"),
        supabase.from("indicator_tickers").select("ticker,name").eq("user_id", uid).order("sort_order"),
        supabase.from("watchlist").select("ticker,name").eq("user_id", uid).order("sort_order"),
        supabase.from("ath_state").select("*").eq("user_id", uid),
      ]);
    setSettings(st);
    const ixList  = (ix  ?? []).map((r) => r.ticker);
    const indList = (ind ?? []).map((r) => r.ticker);
    const wlList  = (wl  ?? []).map((r) => r.ticker);
    setIndexTickers(ixList);
    setIndicatorTickers(indList);
    setWatchlist(wlList);
    const m = {};
    (aths ?? []).forEach((r) => { m[r.ticker] = r; });
    setAthMap(m);
    return { st, ixList, indList, wlList };
  }, [uid]);

  const refreshQuotes = useCallback(async (ixList, indList, wlList) => {
    const syms = [...new Set([...(ixList ?? []), ...(indList ?? []), ...(wlList ?? [])])];
    if (!syms.length) return;
    const q = await getQuotes(syms);
    setQuotes(q);
    setUpdatedAt(new Date());
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const { ixList, indList, wlList } = await loadAll();
      await refreshQuotes(ixList, indList, wlList);
      setLoading(false);
    })();
  }, [loadAll, refreshQuotes]);

  useEffect(() => {
    if (loading) return;
    clearInterval(quoteTimer.current);
    quoteTimer.current = setInterval(
      () => refreshQuotes(indexTickers, indicatorTickers, watchlist),
      10000
    );
    return () => clearInterval(quoteTimer.current);
  }, [loading, indexTickers, indicatorTickers, watchlist, refreshQuotes]);

  /* ATH 즉시 초기화 (티커 추가 직후) */
  async function initAth(ticker) {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    try {
      const res = await fetch("/api/init-ath", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          ticker,
          resetPct: settings?.ath_reset_pct ?? 10,
          lookback: settings?.ath_lookback ?? "5y",
        }),
      });
      if (!res.ok) return;
      const data = await res.json();
      setAthMap((prev) => ({ ...prev, [ticker]: { ...prev[ticker], ...data } }));
    } catch {}
  }

  /* sort_order DB 저장 */
  async function saveOrder(table, newSymbols) {
    await Promise.all(newSymbols.map((sym, i) =>
      supabase.from(table).update({ sort_order: i }).eq("user_id", uid).eq("ticker", sym)
    ));
  }

  /* 섹션 새로고침: ATH 재계산 + 현재가 갱신 */
  async function initAthAll(sectionTickers) {
    await Promise.all([
      ...sectionTickers.map(initAth),
      refreshQuotes(indexTickers, indicatorTickers, watchlist),
    ]);
  }

  /* 티커 추가 시 종목명 DB에도 저장 */
  async function saveTickerName(table, ticker, name) {
    if (!name || name === ticker) return;
    await supabase.from(table).update({ name }).eq("user_id", uid).eq("ticker", ticker);
  }

  /* ── ATH 대비 하락율∙매도 알림 티커 ── */
  async function addIndexTicker(item) {
    const t = item.symbol;
    if (indexTickers.length >= 10) { flash("ATH 감시는 최대 10개까지 추가할 수 있습니다"); return; }
    if (indexTickers.includes(t)) { setAddingTo(null); return; }
    const { error } = await supabase.from("index_tickers").insert({ user_id: uid, ticker: t, name: item.name || null });
    if (error) { flash("추가 실패: " + error.message); return; }
    const next = [...indexTickers, t];
    setIndexTickers(next);
    setAddingTo(null);
    flash(`${displaySym(t)} 추가됨`);
    refreshQuotes(next, indicatorTickers, watchlist);
    initAth(t);
  }
  async function removeIndexTicker(t) {
    await supabase.from("index_tickers").delete().eq("user_id", uid).eq("ticker", t);
    setIndexTickers((prev) => prev.filter((x) => x !== t));
    flash(`${displaySym(t)} 삭제됨`);
  }

  /* ── 기술적 매수∙매도신호 알림 티커 ── */
  async function addIndicatorTicker(item) {
    const t = item.symbol;
    if (indicatorTickers.length >= 50) { flash("기술적 매수신호 감시는 최대 50개까지 추가할 수 있습니다"); return; }
    if (indicatorTickers.includes(t)) { setAddingTo(null); return; }
    const { error } = await supabase.from("indicator_tickers").insert({ user_id: uid, ticker: t, name: item.name || null });
    if (error) { flash("추가 실패: " + error.message); return; }
    const next = [...indicatorTickers, t];
    setIndicatorTickers(next);
    setAddingTo(null);
    flash(`${displaySym(t)} 추가됨`);
    refreshQuotes(indexTickers, next, watchlist);
    initAth(t);
  }
  async function removeIndicatorTicker(t) {
    await supabase.from("indicator_tickers").delete().eq("user_id", uid).eq("ticker", t);
    setIndicatorTickers((prev) => prev.filter((x) => x !== t));
    flash(`${displaySym(t)} 삭제됨`);
  }

  /* ── 국내주식 DMI 매수신호 알림 티커 ── */
  async function addWatchTicker(item) {
    const t = item.symbol;
    if (watchlist.length >= 50) { flash("국내주식 DMI 감시는 최대 50개까지 추가할 수 있습니다"); return; }
    if (watchlist.includes(t)) { setAddingTo(null); return; }
    const { error } = await supabase.from("watchlist").insert({ user_id: uid, ticker: t, name: item.name || null });
    if (error) { flash("추가 실패: " + error.message); return; }
    const next = [...watchlist, t];
    setWatchlist(next);
    setAddingTo(null);
    flash(`${displaySym(t)} 추가됨`);
    refreshQuotes(indexTickers, indicatorTickers, next);
    initAth(t);
  }
  async function removeWatchTicker(t) {
    await supabase.from("watchlist").delete().eq("user_id", uid).eq("ticker", t);
    setWatchlist((prev) => prev.filter((x) => x !== t));
    flash(`${displaySym(t)} 삭제됨`);
  }

  if (loading)
    return <div className="card"><p className="muted">불러오는 중…</p></div>;

  return (
    <>
      {/* ① ATH 대비 하락율∙매도 알림 */}
      <SectionCard
        title="ATH 대비 하락율∙매도 알림"
        note={`ATH 대비 설정된 % 하락 시 텔레그램 알림 · 매수 신호: ATH 대비 −${
          (settings?.drawdown_levels ?? [10, 20, 30, 40]).join(" / −")
        }% · 매도 알림: ATH 도달 및 ATH 대비 매 10% 초과 상승 시.`}
        tickers={indexTickers}
        quotes={quotes}
        athMap={athMap}
        onRemove={removeIndexTicker}
        onRefreshAll={initAthAll}
        onReorder={(syms) => { setIndexTickers(syms); saveOrder("index_tickers", syms); }}
        onAdd={() => setAddingTo("ath")}
        addDisabled={indexTickers.length >= 10}
        addLabel={`${indexTickers.length}/10`}
        adding={addingTo === "ath"}
        onCancelAdd={() => setAddingTo(null)}
        onSelectAdd={addIndexTicker}
        searchPlaceholder="예: QQQ, SPY, 069500"
        searchHint="ATH 대비 하락율∙매도 신호를 계산할 지수 티커. 최대 10개."
        withGauge
        buyLevels={settings?.drawdown_levels ?? [10, 20, 30, 40]}
      />

      {/* ② 기술적 매수∙매도신호 알림 */}
      <SectionCard
        title="기술적 매수∙매도신호 알림"
        note="DMI·스토캐스틱·거래량 기준, 장시작/마감 특정 시점 판정 · 매도 신호: ATH 대비 +10% / +20% …"
        tickers={indicatorTickers}
        quotes={quotes}
        athMap={athMap}
        onRemove={removeIndicatorTicker}
        onRefreshAll={initAthAll}
        onReorder={(syms) => { setIndicatorTickers(syms); saveOrder("indicator_tickers", syms); }}
        onAdd={() => setAddingTo("indicator")}
        addDisabled={indicatorTickers.length >= 50}
        addLabel={`${indicatorTickers.length}/50`}
        adding={addingTo === "indicator"}
        onCancelAdd={() => setAddingTo(null)}
        onSelectAdd={addIndicatorTicker}
        searchPlaceholder="예: QQQ, 069500"
        searchHint="DMI·거래량 보조지표 계산에 사용할 티커. 최대 50개."
      />

      {/* ③ 개별주식 DMI 매수신호 알림 */}
      <SectionCard
        title="개별주식 DMI 매수신호 알림"
        note="개별주식 DMI 매수신호 감시 · 종목명 또는 6자리 코드로 검색"
        tickers={watchlist}
        quotes={quotes}
        athMap={athMap}
        onRemove={removeWatchTicker}
        onRefreshAll={initAthAll}
        onReorder={(syms) => { setWatchlist(syms); saveOrder("watchlist", syms); }}
        onAdd={() => setAddingTo("watchlist")}
        addDisabled={watchlist.length >= 50}
        addLabel={`${watchlist.length}/50`}
        adding={addingTo === "watchlist"}
        onCancelAdd={() => setAddingTo(null)}
        onSelectAdd={addWatchTicker}
        searchPlaceholder="예: 삼성전자, 005930, KODEX"
        searchHint="개별주식 종목명 또는 6자리 코드로 검색. 최대 50개."
      />

      <p className="hint" style={{ textAlign: "center", marginTop: 4, fontSize: 11 }}>
        현재가 10초마다 갱신 · ATH는 엔진이 계산 · 미국/한국 시장 지원
        {updatedAt
          ? ` · ${updatedAt.toLocaleTimeString("ko-KR", {
              hour: "2-digit", minute: "2-digit", second: "2-digit",
            })}`
          : ""}
      </p>
    </>
  );
}
