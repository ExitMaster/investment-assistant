import React, { useEffect, useState } from "react";
import { supabase, TELEGRAM_BOT_USERNAME } from "../supabase.js";

const LOOKBACKS = [
  { v: "5y", label: "최근 5년" },
  { v: "3y", label: "최근 3년" },
  { v: "52w", label: "52주" },
  { v: "all", label: "전체" },
];

/* 보조지표 알림 시각 1개 행 */
function TimeRow({ t, i, onUpdate, onDelete }) {
  const isOpen = t.anchor === "open";
  const absMin = Math.abs(t.offset_min ?? 0);
  const label = isOpen ? `장시작 후 ${absMin}분` : `장마감 ${absMin}분 전`;

  return (
    <div className="time-row" key={i}>
      <div className="time-row-top">
        <select
          value={t.anchor}
          onChange={(e) => onUpdate(i, { anchor: e.target.value, offset_min: 0 })}
        >
          <option value="open">장 시작 후</option>
          <option value="close">장 마감 전</option>
        </select>
        <span className="time-label">{label}</span>
        <button className="icon-btn-sm danger" onClick={() => onDelete(i)} title="삭제">
          ×
        </button>
      </div>
      <div className="slider-wrap" style={{ marginTop: 8 }}>
        <input
          type="range"
          min="0"
          max="180"
          step="5"
          value={absMin}
          onChange={(e) => onUpdate(i, { offset_min: parseInt(e.target.value) })}
        />
        <span className="slider-val">{absMin}분</span>
      </div>
    </div>
  );
}

export default function Settings({ profile, flash, onTelegramLinked }) {
  const [s, setS] = useState(null);
  const [saving, setSaving] = useState(false);

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
    })();
  }, [profile.id]);

  if (!s) return <div className="card"><p className="muted">설정 불러오는 중…</p></div>;

  const up = (patch) => setS({ ...s, ...patch });

  async function save() {
    setSaving(true);
    // display_ticker는 DB에서 제거됨, user_id/updated_at은 제외
    const { user_id, updated_at, display_ticker, ...payload } = s;
    const { error } = await supabase
      .from("settings")
      .update({ ...payload, updated_at: new Date().toISOString() })
      .eq("user_id", profile.id);
    setSaving(false);
    flash(error ? "저장 실패: " + error.message : "설정을 저장했습니다");
  }

  const times = Array.isArray(s.indicator_alert_times) ? s.indicator_alert_times : [];

  function addTime() {
    up({ indicator_alert_times: [...times, { anchor: "open", offset_min: 10 }] });
  }
  function updTime(i, patch) {
    const next = times.map((t, idx) => (idx === i ? { ...t, ...patch } : t));
    up({ indicator_alert_times: next });
  }
  function delTime(i) {
    up({ indicator_alert_times: times.filter((_, idx) => idx !== i) });
  }

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
            <a
              className="btn-primary"
              href={tgLink}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: "none", display: "inline-block" }}
            >
              텔레그램 봇 연결하기
            </a>
            <p className="hint">연결 후 이 페이지를 새로고침하면 상태가 갱신됩니다.</p>
          </>
        ) : (
          <p className="muted">봇 주소가 설정되지 않았습니다. 관리자에게 문의하세요.</p>
        )}
      </div>

      {/* 매수 신호 기본값 */}
      <div className="card">
        <h2>ATH 대비 하락율 알림 기준</h2>
        <div className="field">
          <label>하락 레벨 (%)</label>
          <input
            value={(s.drawdown_levels ?? []).join(", ")}
            onChange={(e) =>
              up({
                drawdown_levels: e.target.value
                  .split(",")
                  .map((x) => parseInt(x.trim()))
                  .filter(Boolean),
              })
            }
          />
          <div className="hint">
            ATH 대비 이 % 하락 시 알림. 쉼표로 구분. (예: 10, 20, 30)
          </div>
        </div>
        <div className="field">
          <label>구간 유지 재알림 간격</label>
          <div className="slider-wrap">
            <input
              type="range"
              min="0"
              max="120"
              step="5"
              value={s.redrawdown_repeat_interval ?? 30}
              onChange={(e) =>
                up({ redrawdown_repeat_interval: parseInt(e.target.value) })
              }
            />
            <span className="slider-val">
              {(s.redrawdown_repeat_interval ?? 30) === 0
                ? "끔"
                : `${s.redrawdown_repeat_interval ?? 30}분`}
            </span>
          </div>
          <div className="hint">
            하락 구간에 머무는 동안 이 간격으로 다시 알림. 0이면 진입 시 1회만.
          </div>
        </div>
      </div>

      {/* ATH 기준 */}
      <div className="card">
        <h2>전고점(ATH) 기준</h2>
        <div className="field">
          <label>산정 기간</label>
          <select
            value={s.ath_lookback}
            onChange={(e) => up({ ath_lookback: e.target.value })}
          >
            {LOOKBACKS.map((l) => (
              <option key={l.v} value={l.v}>
                {l.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>갱신 임계 (%)</label>
          <input
            type="number"
            value={s.ath_reset_pct}
            onChange={(e) => up({ ath_reset_pct: parseFloat(e.target.value) })}
          />
          <div className="hint">
            신고가가 이 % 이상 초과 상승 후 다시 무너질 때만 ATH를 갱신합니다(노이즈 방지).
          </div>
        </div>
      </div>

      {/* 기술적 매수신호 알림 시각 */}
      <div className="card">
        <h2>기술적 매수신호 알림 시각</h2>
        <p className="hint" style={{ marginTop: 0, marginBottom: 14 }}>
          DMI·거래량 신호를 판정할 시점을 지정합니다.
          티커가 상장된 시장의 개장/폐장 시간 기준 (미국/한국 시장 지원).
        </p>
        {times.map((t, i) => (
          <TimeRow key={i} t={t} i={i} onUpdate={updTime} onDelete={delTime} />
        ))}
        <button className="btn-ghost" onClick={addTime} style={{ marginTop: 10 }}>
          + 시각 추가
        </button>
      </div>

      {/* 알림 켜기/끄기 */}
      <div className="card">
        <h2>알림 켜기/끄기</h2>
        {[
          ["enable_buy_levels",    "ATH 대비 하락율 알림",      "ATH 대비 −N% 하락 시 매수 신호"],
          ["enable_buy_indicators","기술적 매수신호 알림",      "DMI·스토캐스틱·거래량 기준 매수 신호"],
          ["enable_sell_signals",  "매도 신호 알림",            "ATH 대비 +10%/+20%… 상승 시 매도 신호"],
          ["enable_watchlist",     "국내주식 DMI 매수신호 알림","개별 종목 DMI 매수신호 감시"],
        ].map(([key, label, desc]) => (
          <div className="toggle-row" key={key}>
            <div>
              <div style={{ fontWeight: 500 }}>{label}</div>
              <div className="hint" style={{ margin: 0 }}>{desc}</div>
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
      </div>

      <button
        className="btn-primary"
        onClick={save}
        disabled={saving}
        style={{ width: "100%", padding: 14 }}
      >
        {saving ? "저장 중…" : "설정 저장"}
      </button>
    </>
  );
}
