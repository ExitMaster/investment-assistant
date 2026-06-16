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
const EditIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);

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
            style={{ width: "100%" }}
          />
          {(results.length > 0 || busy) && (
            <div className="search-dropdown">
              {busy && <div className="search-item muted">검색 중…</div>}
              {results.map((r) => (
                <button key={r.symbol} className="search-item" onClick={() => onSelect(r)}>
                  <span className="t-sym" style={{ fontSize: 14 }}>{r.symbol}</span>
                  <span className="t-name" style={{ marginLeft: 8 }}>{r.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="btn-ghost" style={{ whiteSpace: "nowrap" }} onClick={onCancel}>
          취소
        </button>
      </div>
      {hint && <p className="hint" style={{ marginTop: 6 }}>{hint}</p>}
    </div>
  );
}

/* ── 티커 한 행 ── */
function TickerRow({ sym, quotes, athMap, onRemove, onEdit }) {
  const q = quotes[sym];
  const athRow = athMap[sym];
  const ath = athRow?.ath ?? null;
  const price = q?.price ?? null;
  const prevClose = q?.prevClose ?? null;
  const name = q?.name && q.name !== sym ? q.name : null;

  const dayChg = pct(price, prevClose);
  const athChg = pct(price, ath);

  return (
    <div className="ticker-row">
      <div className="t-info">
        <a className="t-sym" href={tvLink(sym)} target="_blank" rel="noreferrer">{sym}</a>
        {name && <div className="t-name">{name}</div>}
        {price != null && (
          <div className="t-current">
            <span className="t-current-label">현재가</span>
            <span className="t-current-price mono">{price.toFixed(2)}</span>
          </div>
        )}
      </div>

      <div className="t-data">
        {ath != null && (
          <div className="t-ref-row">
            <span className="t-ref mono">ATH {ath.toFixed(2)}</span>
            {athChg != null && (
              <span className={`badge mono ${athChg >= 0 ? "up" : "down"}`}>{fmtPct(athChg)}</span>
            )}
          </div>
        )}
        {prevClose != null && (
          <div className="t-ref-row">
            <span className="t-ref mono">전일 {prevClose.toFixed(2)}</span>
            {dayChg != null && (
              <span className={`badge mono ${dayChg >= 0 ? "up" : "down"}`}>{fmtPct(dayChg)}</span>
            )}
          </div>
        )}
      </div>

      <div className="t-actions">
        {onEdit && (
          <button className="icon-btn-sm" onClick={onEdit} title="수정"><EditIcon /></button>
        )}
        {onRemove && (
          <button className="icon-btn-sm danger" onClick={() => onRemove(sym)} title="삭제"><XIcon /></button>
        )}
      </div>
    </div>
  );
}

/* ── 섹션 카드 ── */
function SectionCard({
  title, note,
  tickers, quotes, athMap,
  onRemove, onEdit,
  onAdd, addDisabled, addLabel,
  adding, onCancelAdd, onSelectAdd,
  searchPlaceholder, searchHint,
}) {
  return (
    <div className="card">
      <div className="section-header">
        <div>
          <h2 style={{ marginBottom: 2 }}>{title}</h2>
          {note && <p className="hint" style={{ margin: 0 }}>{note}</p>}
        </div>
        {onAdd && (
          <button
            className="icon-btn"
            onClick={onAdd}
            disabled={addDisabled}
            title="추가"
            style={{ flexShrink: 0 }}
          >
            <PlusIcon />
            {addLabel && <span style={{ fontSize: 11, marginLeft: 4 }}>{addLabel}</span>}
          </button>
        )}
      </div>

      {tickers.length === 0 && !adding && (
        <p className="muted" style={{ marginTop: 12, fontSize: 14 }}>
          + 버튼으로 티커를 추가하세요.
        </p>
      )}

      {tickers.map((sym) => (
        <TickerRow
          key={sym}
          sym={sym}
          quotes={quotes}
          athMap={athMap}
          onRemove={onRemove}
          onEdit={onEdit ? () => onEdit(sym) : null}
        />
      ))}

      {adding && (
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
  const [watchlist, setWatchlist] = useState([]);
  const [athMap, setAthMap] = useState({});
  const [quotes, setQuotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);

  const [addingTo, setAddingTo] = useState(null); // 'ath' | 'indicator' | 'watchlist' | null
  const [indicatorTickers, setIndicatorTickers] = useState([]);

  const uid = profile.id;

  const loadAll = useCallback(async () => {
    const [{ data: st }, { data: ix }, { data: ind }, { data: wl }, { data: aths }] =
      await Promise.all([
        supabase.from("settings").select("*").eq("user_id", uid).single(),
        supabase.from("index_tickers").select("ticker").eq("user_id", uid),
        supabase.from("indicator_tickers").select("ticker").eq("user_id", uid),
        supabase.from("watchlist").select("ticker").eq("user_id", uid),
        supabase.from("ath_state").select("*").eq("user_id", uid),
      ]);
    setSettings(st);
    const ixList = (ix ?? []).map((r) => r.ticker);
    const indList = (ind ?? []).map((r) => r.ticker);
    const wlList = (wl ?? []).map((r) => r.ticker);
    setIndexTickers(ixList);
    setIndicatorTickers(indList);
    setWatchlist(wlList);
    const m = {};
    (aths ?? []).forEach((r) => { m[r.ticker] = r; });
    setAthMap(m);
    return { st, ixList, indList, wlList };
  }, [uid]);

  const refreshQuotes = useCallback(async (ixList, indList, wlList) => {
    const syms = new Set([
      ...(ixList ?? []),
      ...(indList ?? []),
      ...(wlList ?? []),
    ]);
    if (syms.size === 0) return;
    const q = await getQuotes([...syms]);
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
    const id = setInterval(
      () => refreshQuotes(indexTickers, indicatorTickers, watchlist),
      30000
    );
    return () => clearInterval(id);
  }, [loading, indexTickers, indicatorTickers, watchlist, refreshQuotes]);

  /* ── ATH 감시 티커 추가/삭제 ── */
  async function addIndexTicker(item) {
    const t = item.symbol;
    if (indexTickers.length >= 5) {
      flash("ATH 감시는 최대 5개까지 추가할 수 있습니다");
      return;
    }
    if (indexTickers.includes(t)) { setAddingTo(null); return; }
    const { error } = await supabase
      .from("index_tickers")
      .insert({ user_id: uid, ticker: t });
    if (error) { flash("추가 실패: " + error.message); return; }
    const next = [...indexTickers, t];
    setIndexTickers(next);
    setAddingTo(null);
    flash(`${t} 추가됨`);
    refreshQuotes(next, indicatorTickers, watchlist);
  }
  async function removeIndexTicker(t) {
    await supabase.from("index_tickers").delete().eq("user_id", uid).eq("ticker", t);
    const next = indexTickers.filter((x) => x !== t);
    setIndexTickers(next);
    flash(`${t} 삭제됨`);
  }

  /* ── 기술적 매수신호 티커 추가/삭제 ── */
  async function addIndicatorTicker(item) {
    const t = item.symbol;
    if (indicatorTickers.length >= 30) {
      flash("기술적 매수신호 감시는 최대 30개까지 추가할 수 있습니다");
      return;
    }
    if (indicatorTickers.includes(t)) { setAddingTo(null); return; }
    const { error } = await supabase.from("indicator_tickers").insert({ user_id: uid, ticker: t });
    if (error) { flash("추가 실패: " + error.message); return; }
    const next = [...indicatorTickers, t];
    setIndicatorTickers(next);
    setAddingTo(null);
    flash(`${t} 추가됨`);
    refreshQuotes(indexTickers, next, watchlist);
  }
  async function removeIndicatorTicker(t) {
    await supabase.from("indicator_tickers").delete().eq("user_id", uid).eq("ticker", t);
    const next = indicatorTickers.filter((x) => x !== t);
    setIndicatorTickers(next);
    flash(`${t} 삭제됨`);
  }

  /* ── 국내주식 DMI 티커 추가/삭제 ── */
  async function addWatchTicker(item) {
    const t = item.symbol;
    if (watchlist.length >= 30) {
      flash("국내주식 DMI 감시는 최대 30개까지 추가할 수 있습니다");
      return;
    }
    if (watchlist.includes(t)) { setAddingTo(null); return; }
    const { error } = await supabase.from("watchlist").insert({ user_id: uid, ticker: t });
    if (error) { flash("추가 실패: " + error.message); return; }
    const next = [...watchlist, t];
    setWatchlist(next);
    setAddingTo(null);
    flash(`${t} 추가됨`);
    refreshQuotes(indexTickers, indicatorTickers, next);
  }
  async function removeWatchTicker(t) {
    await supabase.from("watchlist").delete().eq("user_id", uid).eq("ticker", t);
    const next = watchlist.filter((x) => x !== t);
    setWatchlist(next);
    flash(`${t} 삭제됨`);
  }

  if (loading)
    return <div className="card"><p className="muted">불러오는 중…</p></div>;

  return (
    <>
      {/* ① ATH 대비 하락율 알림 */}
      <SectionCard
        title="ATH 대비 하락율 알림"
        note={`ATH 대비 설정된 % 하락 시 텔레그램 알림 · 매수 신호: ATH 대비 −${
          (settings?.drawdown_levels ?? [10, 20, 30]).join(" / −")
        }%`}
        tickers={indexTickers}
        quotes={quotes}
        athMap={athMap}
        onRemove={removeIndexTicker}
        onAdd={() => setAddingTo("ath")}
        addDisabled={indexTickers.length >= 5}
        addLabel={`${indexTickers.length}/5`}
        adding={addingTo === "ath"}
        onCancelAdd={() => setAddingTo(null)}
        onSelectAdd={addIndexTicker}
        searchPlaceholder="예: QQQ, SPY, 069500"
        searchHint="ATH 대비 하락율 신호를 계산할 지수 티커. 최대 5개."
      />

      {/* ② 기술적 매수신호 알림 */}
      <SectionCard
        title="기술적 매수신호 알림"
        note="DMI·스토캐스틱·거래량 기준, 장시작/마감 특정 시점 판정 · 매도 신호: ATH 대비 +10% / +20% …"
        tickers={indicatorTickers}
        quotes={quotes}
        athMap={athMap}
        onRemove={removeIndicatorTicker}
        onAdd={() => setAddingTo("indicator")}
        addDisabled={indicatorTickers.length >= 30}
        addLabel={`${indicatorTickers.length}/30`}
        adding={addingTo === "indicator"}
        onCancelAdd={() => setAddingTo(null)}
        onSelectAdd={addIndicatorTicker}
        searchPlaceholder="예: QQQ, 069500"
        searchHint="DMI·거래량 보조지표 계산에 사용할 티커. 최대 30개."
      />

      {/* ③ 국내주식 DMI 매수신호 알림 */}
      <SectionCard
        title="국내주식 DMI 매수신호 알림"
        note="개별 종목 DMI 매수신호 감시 · 한국어 종목명 또는 6자리 코드로 검색"
        tickers={watchlist}
        quotes={quotes}
        athMap={athMap}
        onRemove={removeWatchTicker}
        onAdd={() => setAddingTo("watchlist")}
        addDisabled={watchlist.length >= 30}
        addLabel={`${watchlist.length}/30`}
        adding={addingTo === "watchlist"}
        onCancelAdd={() => setAddingTo(null)}
        onSelectAdd={addWatchTicker}
        searchPlaceholder="예: 삼성전자, 005930, KODEX"
        searchHint="국내 주식 종목명 또는 6자리 코드로 검색. 최대 30개."
      />

      <p className="hint" style={{ textAlign: "center", marginTop: 4, fontSize: 12 }}>
        현재가 30초마다 갱신 · ATH는 엔진이 계산 · 미국/한국 시장 지원
        {updatedAt
          ? ` · 갱신 ${updatedAt.toLocaleTimeString("ko-KR", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}`
          : ""}
      </p>
    </>
  );
}
