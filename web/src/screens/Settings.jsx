import React, { useEffect, useState, useRef } from "react";
import { supabase } from "../supabase.js";

/* ── ATH 산정 기간 슬라이더 변환 ── */
function lookbackToSlider(v) {
  if (!v || v === "all") return 11;
  if (v === "52w") return 1;
  const n = parseInt(v);
  return isNaN(n) ? 5 : Math.min(Math.max(n, 1), 10);
}
function sliderToLookback(n) { return n >= 11 ? "all" : `${n}y`; }
function sliderLabel(n) { return n >= 11 ? "전체" : `${n}년`; }

/* ── 알림 시각 슬라이더 변환 ── */
function timeToSlider(t) {
  if (!t) return 0;
  if (t.anchor === "open") return Math.min(t.offset_min ?? 0, 180);
  return 360 - Math.min(t.offset_min ?? 0, 180);
}
function sliderToTime(v) {
  if (v <= 180) return { anchor: "open", offset_min: v };
  return { anchor: "close", offset_min: 360 - v };
}
function sliderTimeLabel(v) {
  if (v === 0) return "개장 바로";
  if (v <= 180) return `개장 후 ${v}분`;
  if (v === 360) return "마감 바로";
  return `마감 전 ${360 - v}분`;
}

/* ── 시각 행 (단일 슬라이더) ── */
function TimeRow({ t, i, onUpdate, onDelete }) {
  const v = timeToSlider(t);
  return (
    <div className="time-slider-wrap">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="time-slider-display">{sliderTimeLabel(v)}</span>
        <button className="icon-btn-sm danger" onClick={() => onDelete(i)} title="삭제">×</button>
      </div>
      <div className="time-slider-labels" style={{ marginTop: 8 }}>
        <span>개장</span>
        <span>마감</span>
      </div>
      <input
        type="range"
        className="time-range"
        min="0"
        max="360"
        step="5"
        value={v}
        onChange={(e) => onUpdate(i, sliderToTime(parseInt(e.target.value)))}
      />
    </div>
  );
}

/* ── 하락레벨 칩 입력 ── */
function ChipInput({ levels, onChange }) {
  const [inputVal, setInputVal] = useState("");
  const inputRef = useRef(null);

  function addLevel(raw) {
    const n = parseInt(String(raw).trim());
    if (!n || n <= 0 || n > 100) return;
    if (!levels.includes(n)) onChange([...levels, n].sort((a, b) => a - b));
    setInputVal("");
  }

  function handleKey(e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      addLevel(inputVal);
    } else if (e.key === "Backspace" && inputVal === "" && levels.length > 0) {
      onChange(levels.slice(0, -1));
    }
  }

  return (
    <div className="chip-input-wrap" onClick={() => inputRef.current?.focus()}>
      {levels.map((n) => (
        <span key={n} className="chip">
          -{n}%
          <button
            className="chip-x"
            onClick={(e) => { e.stopPropagation(); onChange(levels.filter((x) => x !== n)); }}
          >×</button>
        </span>
      ))}
      <input
        ref={inputRef}
        className="chip-input"
        type="number"
        min="1"
        max="100"
        value={inputVal}
        onChange={(e) => setInputVal(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => { if (inputVal) addLevel(inputVal); }}
        placeholder={levels.length === 0 ? "숫자 입력 후 Enter" : "+"}
      />
    </div>
  );
}

/* ── 매매 행동 가이드 ── */
function actSym(sym) { return (sym || "").replace(/\.(KS|KQ)$/, ""); }
const DEFAULT_BUY_ACTIONS = {
  10: { product: "IVV", cash: 20 },
  20: { product: "QLD", cash: 40 },
  30: { product: "TQQQ", cash: 70 },
  40: { product: "TQQQ", cash: 100 },
};
function defAction(level) { return DEFAULT_BUY_ACTIONS[level] || { product: "", cash: "" }; }
function getAction(actions, level) { return (actions || {})[level] || defAction(level); }

function ActionTable({ levels, actions, onChange }) {
  function setCell(level, key, val) {
    onChange({ ...(actions || {}), [level]: { ...getAction(actions, level), [key]: val } });
  }
  return (
    <div className="action-table">
      {levels.map((L) => {
        const a = getAction(actions, L);
        return (
          <div className="action-row" key={L}>
            <span className="action-level">-{L}%</span>
            <input className="action-prod" value={a.product ?? ""} placeholder="종목"
              onChange={(e) => setCell(L, "product", e.target.value)} />
            <span className="action-cash-wrap">
              현금
              <input className="action-cash" type="number" min="0" max="100" value={a.cash ?? ""}
                onChange={(e) => setCell(L, "cash", e.target.value === "" ? "" : parseFloat(e.target.value))} />
              %
            </span>
          </div>
        );
      })}
    </div>
  );
}

function PerTickerActions({ indexTickers, tickerActions, setTickerActions, levels }) {
  const [open, setOpen] = useState({});
  function copyFrom(target, source) {
    setTickerActions((prev) => ({ ...prev, [target]: JSON.parse(JSON.stringify(prev[source] || {})) }));
  }
  return (
    <>
      {indexTickers.map((t) => (
        <div key={t.ticker} className="per-ticker-block">
          <div className="per-ticker-head" onClick={() => setOpen((o) => ({ ...o, [t.ticker]: !o[t.ticker] }))}>
            <span>
              <b>{actSym(t.ticker)}</b>
              {t.name && <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>{t.name}</span>}
            </span>
            <span style={{ color: "var(--accent)" }}>{open[t.ticker] ? "▲" : "▼"}</span>
          </div>
          {open[t.ticker] && (
            <div style={{ marginTop: 8 }}>
              {indexTickers.length > 1 && (
                <div className="copy-row">
                  <select defaultValue="" onChange={(e) => { if (e.target.value) copyFrom(t.ticker, e.target.value); e.target.value = ""; }}>
                    <option value="">다른 종목에서 복사…</option>
                    {indexTickers.filter((o) => o.ticker !== t.ticker).map((o) => (
                      <option key={o.ticker} value={o.ticker}>{actSym(o.ticker)}</option>
                    ))}
                  </select>
                </div>
              )}
              <ActionTable levels={levels} actions={tickerActions[t.ticker]}
                onChange={(next) => setTickerActions((prev) => ({ ...prev, [t.ticker]: next }))} />
            </div>
          )}
        </div>
      ))}
    </>
  );
}

export default function Settings({ profile, flash, onTelegramLinked, isAdmin, onAdmin }) {
  const [s, setS] = useState(null);
  const [indexTickers, setIndexTickers] = useState([]);
  const [tickerActions, setTickerActions] = useState({});
  const saveTimer = useRef(null);

  useEffect(() => {
    (async () => {
      let { data: st } = await supabase
        .from("settings")
        .select("*")
        .eq("user_id", profile.id)
        .single();
      if (!st) {
        await supabase.from("settings").insert({ user_id: profile.id });
        ({ data: st } = await supabase
          .from("settings")
          .select("*")
          .eq("user_id", profile.id)
          .single());
      }
      setS(st);

      const { data: ix } = await supabase
        .from("index_tickers")
        .select("ticker,name,buy_actions")
        .eq("user_id", profile.id)
        .order("sort_order");
      setIndexTickers((ix ?? []).map((r) => ({ ticker: r.ticker, name: r.name })));
      const map = {};
      (ix ?? []).forEach((r) => { if (r.buy_actions) map[r.ticker] = r.buy_actions; });
      setTickerActions(map);
    })();
  }, [profile.id]);

  if (!s) return <div className="card"><p className="muted">설정 불러오는 중…</p></div>;

  // 완전 자동저장: 변경 즉시 디바운스로 DB 반영 (저장 버튼 없음)
  function persistSettings(nextS) {
    document.documentElement.setAttribute(
      "data-color-inverted", nextS.color_inverted ? "true" : "false"
    );
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      const { user_id, updated_at, display_ticker, ...payload } = nextS;
      await supabase.from("settings")
        .update({ ...payload, updated_at: new Date().toISOString() })
        .eq("user_id", profile.id);
    }, 500);
  }
  function up(patch) {
    const next = { ...s, ...patch };
    setS(next);
    persistSettings(next);
  }

  // 지표별 매매 행동도 변경 즉시 저장
  function changeActions(updater) {
    setTickerActions((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      Object.entries(next)
        .filter(([, act]) => act && typeof act === "object")
        .forEach(([tk, act]) =>
          supabase.from("index_tickers").update({ buy_actions: act })
            .eq("user_id", profile.id).eq("ticker", tk)
        );
      return next;
    });
  }

  // 매매 행동 가이드 기본값 복원
  function resetActions() {
    if (mode === "common") {
      const def = {};
      levels.forEach((L) => { def[L] = defAction(L); });
      up({ buy_actions: def });
    } else {
      const def = {};
      indexTickers.forEach((t) => {
        const m = {};
        levels.forEach((L) => { m[L] = defAction(L); });
        def[t.ticker] = m;
      });
      changeActions(def);
    }
    flash("매매 행동 가이드를 기본값으로 되돌렸습니다");
  }

  const times = Array.isArray(s.indicator_alert_times) ? s.indicator_alert_times : [];
  const levels = Array.isArray(s.drawdown_levels) ? s.drawdown_levels : [10, 20, 30];
  const mode = s.action_mode === "per_ticker" ? "per_ticker" : "common";
  const lookbackSlider = lookbackToSlider(s.ath_lookback);

  return (
    <>
      {/* ① 표시 설정 */}
      <div className="card">
        <h2>표시 설정</h2>

        {/* 등락 색상 — 단일 토글 */}
        <div className="toggle-row">
          <div>
            <div className="toggle-label">등락 색상 반전</div>
            <div className="toggle-desc">
              {s.color_inverted
                ? <><span style={{ color: "#ef4444" }}>▲ 상승 빨강</span> · <span style={{ color: "#16a34a" }}>▼ 하락 초록</span></>
                : <><span style={{ color: "#16a34a" }}>▲ 상승 초록</span> · <span style={{ color: "#ef4444" }}>▼ 하락 빨강</span></>}
            </div>
          </div>
          <label className="switch">
            <input type="checkbox" checked={!!s.color_inverted}
              onChange={(e) => up({ color_inverted: e.target.checked })} />
            <span />
          </label>
        </div>

        {isAdmin && onAdmin && (
          <button className="btn-ghost" style={{ fontSize: 13, marginTop: 10 }} onClick={onAdmin}>
            관리자 페이지 →
          </button>
        )}
      </div>

      {/* ② ATH 대비 하락율∙매도 알림 설정 */}
      <div className="card">
        <h2>ATH 대비 하락율∙매도 알림 설정</h2>

        {/* 산정 기간 + 갱신 임계 */}
        <div className="field">
          <label>전고점(ATH) 산정 기간</label>
          <div className="slider-wrap">
            <input
              type="range"
              min="1"
              max="11"
              step="1"
              value={lookbackSlider}
              onChange={(e) => up({ ath_lookback: sliderToLookback(parseInt(e.target.value)) })}
            />
            <span className="slider-val">{sliderLabel(lookbackSlider)}</span>
          </div>
        </div>

        <div className="field">
          <label>갱신 임계 (%)</label>
          <div className="row-inline">
            <input
              type="number"
              value={s.ath_reset_pct ?? 10}
              onChange={(e) => up({ ath_reset_pct: parseFloat(e.target.value) })}
              style={{ width: 80 }}
            />
          </div>
          <div className="hint">
            어떤 고점에서 이 % 이상 눌림이 나와야 그 고점을 ATH로 확정합니다(위로만 갱신·쌍봉/노이즈 방지).
          </div>
        </div>

        {/* 하락 레벨 */}
        <div className="field">
          <label>하락 알림 레벨 (%)</label>
          <ChipInput levels={levels} onChange={(next) => up({ drawdown_levels: next })} />
          <div className="hint">ATH 대비 이 % 하락 시 알림. 숫자 입력 후 Enter.</div>
        </div>

        {/* 구간 유지 재알림 */}
        <div className="field">
          <label>구간 유지 재알림 간격</label>
          <div className="slider-wrap">
            <input
              type="range"
              min="0"
              max="120"
              step="5"
              value={s.redrawdown_repeat_interval ?? 30}
              onChange={(e) => up({ redrawdown_repeat_interval: parseInt(e.target.value) })}
            />
            <span className="slider-val">
              {(s.redrawdown_repeat_interval ?? 30) === 0
                ? "끔"
                : `${s.redrawdown_repeat_interval ?? 30}분`}
            </span>
          </div>
          <div className="hint">
            하락 또는 매도 구간에 머무는 동안 이 간격으로 재알림. 0이면 진입 시 1회만.
          </div>
        </div>

      </div>

      {/* ②-b 매매 행동 가이드 */}
      <div className="card">
        <div className="section-header">
          <h2 style={{ marginBottom: 0 }}>매매 행동 가이드</h2>
          <button className="btn-ghost" style={{ fontSize: 12 }} onClick={resetActions}>
            기본값 복원
          </button>
        </div>
        <p className="hint" style={{ marginTop: 6 }}>
          매수·매도 알림에 '무엇을 얼마나' 함께 표시합니다 (참고용 안내).
        </p>

        <div className="toggle-row" style={{ marginTop: 0 }}>
          <div>
            <div className="toggle-label">알림에 행동 가이드 포함</div>
            <div className="toggle-desc">끄면 신호만 보내고 종목·현금비중 안내는 생략합니다.</div>
          </div>
          <label className="switch">
            <input type="checkbox" checked={s.include_action_guide !== false}
              onChange={(e) => up({ include_action_guide: e.target.checked })} />
            <span />
          </label>
        </div>

        <div className="mode-toggle">
          <button className={mode === "common" ? "active" : ""} onClick={() => up({ action_mode: "common" })}>
            전지표 공통 모드
          </button>
          <button className={mode === "per_ticker" ? "active" : ""} onClick={() => up({ action_mode: "per_ticker" })}>
            지표별 설정 모드
          </button>
        </div>

        {mode === "common" ? (
          <ActionTable levels={levels} actions={s.buy_actions} onChange={(next) => up({ buy_actions: next })} />
        ) : indexTickers.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>ATH 감시 지표가 없습니다. 대시보드에서 먼저 추가하세요.</p>
        ) : (
          <PerTickerActions
            indexTickers={indexTickers}
            tickerActions={tickerActions}
            setTickerActions={changeActions}
            levels={levels}
          />
        )}

        <hr className="divider" />

        <div className="field">
          <label>매도 목표 현금비중 (%)</label>
          <input type="number" min="0" max="100" value={s.sell_cash_target ?? 30}
            onChange={(e) => up({ sell_cash_target: parseFloat(e.target.value) })} style={{ width: 80 }} />
          <div className="hint">매도 신호 시 "레버리지 높은 종목부터 매도하여 현금비중 N%로" 안내.</div>
        </div>

        <div className="toggle-row">
          <div>
            <div className="toggle-label">임박 알림</div>
            <div className="toggle-desc">ATH 신호가 다음 매수 또는 매도레벨에 설정한 %p로 근접하면 미리 1회 알림</div>
          </div>
          <label className="switch">
            <input type="checkbox" checked={!!s.prealert_enabled}
              onChange={(e) => up({ prealert_enabled: e.target.checked })} />
            <span />
          </label>
        </div>
        {s.prealert_enabled && (
          <div className="field">
            <label>임박 기준 (%p 이내)</label>
            <input type="number" step="0.5" min="0.5" value={s.prealert_pp ?? 2.0}
              onChange={(e) => up({ prealert_pp: parseFloat(e.target.value) })} style={{ width: 80 }} />
          </div>
        )}
      </div>

      {/* ③ 기술적 신호 알림 설정 */}
      <div className="card">
        <h2>기술적 신호 알림 설정</h2>
        <p className="hint" style={{ marginTop: 0, marginBottom: 14 }}>
          DMI·거래량 신호를 판정할 시점을 지정합니다.
          티커가 상장된 시장(미국/한국)의 개장·폐장 시간 기준으로 동작합니다.
        </p>
        {times.map((t, i) => (
          <TimeRow
            key={i}
            t={t}
            i={i}
            onUpdate={(idx, patch) => {
              const next = times.map((x, j) => (j === idx ? { ...x, ...patch } : x));
              up({ indicator_alert_times: next });
            }}
            onDelete={(idx) => up({ indicator_alert_times: times.filter((_, j) => j !== idx) })}
          />
        ))}
        <button
          className="btn-ghost"
          onClick={() => up({ indicator_alert_times: [...times, { anchor: "open", offset_min: 10 }] })}
          style={{ marginTop: 10, fontSize: 13 }}
        >
          + 시각 추가
        </button>
      </div>

      <p className="hint" style={{ textAlign: "center", marginTop: 4, fontSize: 11 }}>
        변경사항은 자동으로 저장됩니다.
      </p>
    </>
  );
}
