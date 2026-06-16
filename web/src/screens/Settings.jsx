import React, { useEffect, useState, useRef } from "react";
import { supabase, TELEGRAM_BOT_USERNAME } from "../supabase.js";

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
  if (v === 0) return "장시작 바로";
  if (v <= 180) return `장시작 후 ${v}분`;
  if (v === 360) return "장마감 바로";
  return `장마감 전 ${360 - v}분`;
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
        <span>장시작</span>
        <span>장마감</span>
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

export default function Settings({ profile, flash, onTelegramLinked }) {
  const [s, setS] = useState(null);
  const [saving, setSaving] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const [indexTickers, setIndexTickers] = useState([]);
  const [tickerActions, setTickerActions] = useState({});

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

  const up = (patch) => setS({ ...s, ...patch });

  async function save() {
    setSaving(true);
    const { user_id, updated_at, display_ticker, ...payload } = s;
    const { error } = await supabase
      .from("settings")
      .update({ ...payload, updated_at: new Date().toISOString() })
      .eq("user_id", profile.id);
    // 지표별 매매 행동 저장
    await Promise.all(
      Object.entries(tickerActions)
        .filter(([, act]) => act && typeof act === "object")
        .map(([tk, act]) =>
          supabase.from("index_tickers").update({ buy_actions: act })
            .eq("user_id", profile.id).eq("ticker", tk)
        )
    );
    setSaving(false);
    if (!error) {
      document.documentElement.setAttribute(
        "data-color-inverted",
        s.color_inverted ? "true" : "false"
      );
    }
    flash(error ? "저장 실패: " + error.message : "설정을 저장했습니다");
  }

  async function unlinkTelegram() {
    setUnlinking(true);
    await supabase.from("profiles").update({
      telegram_chat_id: null,
      telegram_linked: false,
      telegram_display_name: null,
    }).eq("id", profile.id);
    setUnlinking(false);
    flash("텔레그램 연결을 해제했습니다");
    if (onTelegramLinked) onTelegramLinked();
  }

  const times = Array.isArray(s.indicator_alert_times) ? s.indicator_alert_times : [];
  const levels = Array.isArray(s.drawdown_levels) ? s.drawdown_levels : [10, 20, 30];
  const mode = s.action_mode === "per_ticker" ? "per_ticker" : "common";
  const lookbackSlider = lookbackToSlider(s.ath_lookback);
  const tgLink = TELEGRAM_BOT_USERNAME
    ? `https://t.me/${TELEGRAM_BOT_USERNAME}?start=${profile.id}`
    : null;

  return (
    <>
      {/* ① 알림 채널 & 알림 켜기/끄기 */}
      <div className="card">
        <h2>알림 설정</h2>

        {/* 텔레그램 */}
        <div style={{ marginBottom: 14 }}>
          {profile.telegram_linked ? (
            <div className="tg-connected">
              <div className="tg-name">
                <span className="tg-dot" />
                텔레그램 연결됨
                {profile.telegram_display_name && (
                  <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>
                    ({profile.telegram_display_name})
                  </span>
                )}
              </div>
              <button
                className="btn-danger"
                style={{ fontSize: 12, padding: "5px 10px" }}
                onClick={unlinkTelegram}
                disabled={unlinking}
              >
                {unlinking ? "해제 중…" : "연결 끊기"}
              </button>
            </div>
          ) : tgLink ? (
            <div>
              <p className="muted" style={{ margin: "0 0 10px", fontSize: 13 }}>
                아래 버튼을 눌러 봇과 대화를 시작하면 알림이 연결됩니다.
              </p>
              <a
                className="btn-primary"
                href={tgLink}
                target="_blank"
                rel="noreferrer"
                style={{ textDecoration: "none", display: "inline-block", fontSize: 13 }}
              >
                텔레그램 봇 연결하기
              </a>
              <p className="hint" style={{ marginTop: 6 }}>
                연결 후 이 페이지를 새로고침하면 상태가 갱신됩니다.
              </p>
            </div>
          ) : (
            <p className="muted" style={{ fontSize: 13 }}>
              봇 주소가 설정되지 않았습니다. 관리자에게 문의하세요.
            </p>
          )}
        </div>

        <hr className="divider" />

        {/* 알림 토글 */}
        {[
          ["enable_buy_levels",     "ATH 대비 하락율∙매도 알림",    "ATH 대비 −N% 하락 및 ATH 도달/초과 매도 신호"],
          ["enable_sell_signals",   "ATH 대비 상승 매도 신호 알림", "ATH 도달 시 및 ATH 대비 매 10% 초과 상승 시"],
          ["enable_buy_indicators", "기술적 매수∙매도신호 알림",    "DMI·스토캐스틱·거래량 기준 매수∙매도 신호"],
          ["enable_watchlist",      "국내주식 DMI 매수신호 알림",   "개별 종목 DMI 매수신호 감시"],
        ].map(([key, label, desc]) => (
          <div className="toggle-row" key={key}>
            <div>
              <div className="toggle-label">{label}</div>
              <div className="toggle-desc">{desc}</div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={!!s[key]}
                onChange={(e) => up({ [key]: e.target.checked })}
              />
              <span />
            </label>
          </div>
        ))}

        {/* 색상 반전 */}
        <div className="toggle-row">
          <div>
            <div className="toggle-label">색상 반전</div>
            <div className="toggle-desc">상승=빨강, 하락=초록으로 표시 (저장 시 적용)</div>
          </div>
          <label className="switch">
            <input
              type="checkbox"
              checked={!!s.color_inverted}
              onChange={(e) => up({ color_inverted: e.target.checked })}
            />
            <span />
          </label>
        </div>
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
            신고가가 현재 ATH 대비 이 % 이상 상승한 뒤 다시 내려올 때만 ATH가 갱신됩니다 (쌍봉·노이즈 방지).
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

        <div className="hint" style={{ padding: "8px 10px", background: "var(--bg-elev)", borderRadius: 6, marginTop: 4 }}>
          매도 알림: ATH 도달 시 + ATH 대비 매 10% 초과 상승 시.
          ATH 대비 하락율∙매도 알림 분류에 등록된 티커가 대상입니다.
        </div>
      </div>

      {/* ②-b 매매 행동 가이드 */}
      <div className="card">
        <h2>매매 행동 가이드</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          매수·매도 알림에 '무엇을 얼마나' 함께 표시합니다 (참고용 안내).
        </p>

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
            setTickerActions={setTickerActions}
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
            <div className="toggle-desc">다음 매수레벨에 근접하면 미리 1회 알림</div>
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
            <div className="hint">현재 하락율이 다음 레벨까지 이 %p 이내로 근접하면 예고 알림.</div>
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

      <button
        className="btn-primary"
        onClick={save}
        disabled={saving}
        style={{ width: "100%", padding: 13, marginTop: 4 }}
      >
        {saving ? "저장 중…" : "설정 저장"}
      </button>
    </>
  );
}
