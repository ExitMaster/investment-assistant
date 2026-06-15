import React, { useEffect, useState } from "react";
import { supabase, TELEGRAM_BOT_USERNAME } from "../supabase.js";

const LOOKBACKS = [
  { v: "5y", label: "최근 5년" },
  { v: "3y", label: "최근 3년" },
  { v: "52w", label: "52주" },
  { v: "all", label: "전체" },
];

export default function Settings({ profile, flash, onTelegramLinked }) {
  const [s, setS] = useState(null);
  const [watch, setWatch] = useState([]);
  const [newTicker, setNewTicker] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      let { data: st } = await supabase.from("settings").select("*").eq("user_id", profile.id).single();
      if (!st) {
        // 기본 설정 생성
        const def = { user_id: profile.id };
        await supabase.from("settings").insert(def);
        ({ data: st } = await supabase.from("settings").select("*").eq("user_id", profile.id).single());
      }
      setS(st);
      const { data: wl } = await supabase.from("watchlist").select("ticker").eq("user_id", profile.id);
      setWatch((wl ?? []).map((r) => r.ticker));
    })();
  }, [profile.id]);

  if (!s) return <div className="card"><p className="muted">설정 불러오는 중…</p></div>;

  const up = (patch) => setS({ ...s, ...patch });

  async function save() {
    setSaving(true);
    const { user_id, updated_at, ...payload } = s;
    const { error } = await supabase.from("settings")
      .update({ ...payload, updated_at: new Date().toISOString() })
      .eq("user_id", profile.id);
    setSaving(false);
    flash(error ? "저장 실패: " + error.message : "설정을 저장했습니다");
  }

  async function addTicker() {
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    if (watch.includes(t)) { setNewTicker(""); return; }
    const { error } = await supabase.from("watchlist").insert({ user_id: profile.id, ticker: t });
    if (!error) { setWatch([...watch, t]); setNewTicker(""); flash(`${t} 추가됨`); }
    else flash("추가 실패: " + error.message);
  }
  async function removeTicker(t) {
    await supabase.from("watchlist").delete().eq("user_id", profile.id).eq("ticker", t);
    setWatch(watch.filter((x) => x !== t));
  }

  // 보조지표 알림 시각
  const times = Array.isArray(s.indicator_alert_times) ? s.indicator_alert_times : [];
  function addTime() {
    up({ indicator_alert_times: [...times, { anchor: "open", offset_min: 20 }] });
  }
  function updTime(i, patch) {
    const next = times.map((t, idx) => (idx === i ? { ...t, ...patch } : t));
    up({ indicator_alert_times: next });
  }
  function delTime(i) {
    up({ indicator_alert_times: times.filter((_, idx) => idx !== i) });
  }

  // 텔레그램 연결
  const tgLink = TELEGRAM_BOT_USERNAME
    ? `https://t.me/${TELEGRAM_BOT_USERNAME}?start=${profile.id}`
    : null;

  return (
    <>
      {/* 텔레그램 */}
      <div className="card">
        <h2>텔레그램 알림</h2>
        {profile.telegram_linked ? (
          <p className="muted">✅ 텔레그램이 연결되었습니다. 알림이 이 계정으로 전송됩니다.</p>
        ) : tgLink ? (
          <>
            <p className="muted" style={{ marginBottom: 12 }}>
              아래 버튼을 눌러 봇과 대화를 시작하면 알림 수신이 연결됩니다.
            </p>
            <a className="btn-primary" href={tgLink} target="_blank" rel="noreferrer"
               style={{ textDecoration: "none", display: "inline-block" }}>
              텔레그램 봇 연결하기
            </a>
            <p className="hint">연결 후 이 페이지를 새로고침하면 상태가 갱신됩니다.</p>
          </>
        ) : (
          <p className="muted">봇 주소가 설정되지 않았습니다. 관리자에게 문의하세요.</p>
        )}
      </div>

      {/* 기준 티커 */}
      <div className="card">
        <h2>기준 티커</h2>
        <div className="field">
          <label>신호 판정 기준 (지수)</label>
          <input value={s.index_ticker} onChange={(e) => up({ index_ticker: e.target.value.toUpperCase() })} />
          <div className="hint">하락률 −10/−20/−30% 와 ATH 를 이 티커로 계산합니다. (예: QQQ)</div>
        </div>
        <div className="field">
          <label>참고 표기</label>
          <input value={s.display_ticker} onChange={(e) => up({ display_ticker: e.target.value.toUpperCase() })} />
          <div className="hint">상황판에 함께 보여줄 티커. (예: QQQM)</div>
        </div>
        <div className="field">
          <label>보조지표 기준</label>
          <input value={s.indicator_ticker} onChange={(e) => up({ indicator_ticker: e.target.value.toUpperCase() })} />
          <div className="hint">DMI·거래량 등 보조지표 계산 티커.</div>
        </div>
      </div>

      {/* 하락 매수 레벨 + 재알림 */}
      <div className="card">
        <h2>매수 신호</h2>
        <div className="field">
          <label>하락 레벨 (%)</label>
          <input
            value={(s.drawdown_levels ?? []).join(", ")}
            onChange={(e) => up({ drawdown_levels: e.target.value.split(",").map((x) => parseInt(x.trim())).filter(Boolean) })}
          />
          <div className="hint">고점 대비 이 % 하락 시 알림. 쉼표로 구분. (예: 10, 20, 30)</div>
        </div>
        <div className="field">
          <label>구간 유지 재알림 간격</label>
          <div className="slider-wrap">
            <input type="range" min="0" max="120" step="5"
              value={s.redrawdown_repeat_interval}
              onChange={(e) => up({ redrawdown_repeat_interval: parseInt(e.target.value) })} />
            <span className="slider-val">
              {s.redrawdown_repeat_interval === 0 ? "끔" : `${s.redrawdown_repeat_interval}분`}
            </span>
          </div>
          <div className="hint">하락 구간에 머무는 동안 이 간격으로 다시 알림. 0이면 진입 시 1회만.</div>
        </div>
      </div>

      {/* ATH */}
      <div className="card">
        <h2>전고점(ATH) 기준</h2>
        <div className="field">
          <label>산정 기간</label>
          <select value={s.ath_lookback} onChange={(e) => up({ ath_lookback: e.target.value })}>
            {LOOKBACKS.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label>갱신 임계 (%)</label>
          <input type="number" value={s.ath_reset_pct}
            onChange={(e) => up({ ath_reset_pct: parseFloat(e.target.value) })} />
          <div className="hint">신고가가 이 % 이상 초과 상승 후 다시 무너질 때만 ATH를 갱신합니다(노이즈 방지).</div>
        </div>
      </div>

      {/* 보조지표 알림 시각 */}
      <div className="card">
        <h2>보조지표 알림 시각</h2>
        <p className="hint" style={{ marginTop: 0, marginBottom: 12 }}>
          DMI·거래량 신호를 판정할 시점. 장 시작/마감 기준 ± 분(5분 단위).
        </p>
        {times.map((t, i) => (
          <div className="row-inline" key={i} style={{ marginBottom: 8 }}>
            <select value={t.anchor} onChange={(e) => updTime(i, { anchor: e.target.value })}>
              <option value="open">장 시작</option>
              <option value="close">장 마감</option>
            </select>
            <input type="number" step="5" style={{ width: 90 }}
              value={t.offset_min} onChange={(e) => updTime(i, { offset_min: parseInt(e.target.value) })} />
            <span className="muted" style={{ fontSize: 13 }}>분</span>
            <button className="btn-danger" onClick={() => delTime(i)}>삭제</button>
          </div>
        ))}
        <button className="btn-ghost" onClick={addTime} style={{ marginTop: 6 }}>+ 시각 추가</button>
        <p className="hint">장 시작 +0 = 개장 직후, 장 마감 +0 = 종가 확정 후, 장 마감 −120 = 마감 2시간 전.</p>
      </div>

      {/* 관찰 종목 */}
      <div className="card">
        <h2>관찰 종목 (개별주식)</h2>
        <div style={{ marginBottom: 12 }}>
          {watch.length === 0 && <p className="muted">아직 없습니다. DMI 매수신호를 감시할 티커를 추가하세요.</p>}
          {watch.map((t) => (
            <span className="tag" key={t}>{t}<button onClick={() => removeTicker(t)}>×</button></span>
          ))}
        </div>
        <div className="row-inline">
          <input placeholder="예: TSLA" value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addTicker()} style={{ width: 140 }} />
          <button className="btn-ghost" onClick={addTicker}>추가</button>
        </div>
      </div>

      {/* 알림 종류 on/off */}
      <div className="card">
        <h2>알림 켜기/끄기</h2>
        {[
          ["enable_buy_levels", "하락률 매수 신호"],
          ["enable_buy_indicators", "매수 보조지표"],
          ["enable_sell_signals", "매도 신호"],
          ["enable_watchlist", "관찰 종목 신호"],
        ].map(([key, label]) => (
          <div className="toggle-row" key={key}>
            <span>{label}</span>
            <label className="switch">
              <input type="checkbox" checked={!!s[key]} onChange={(e) => up({ [key]: e.target.checked })} />
              <span />
            </label>
          </div>
        ))}
      </div>

      <button className="btn-primary" onClick={save} disabled={saving} style={{ width: "100%", padding: 14 }}>
        {saving ? "저장 중…" : "설정 저장"}
      </button>
    </>
  );
}
