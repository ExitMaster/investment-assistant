import React, { useEffect, useState, useRef } from "react";
import { supabase, TELEGRAM_BOT_USERNAME } from "../supabase.js";

function tvLink(sym) {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
}

const BellIcon = ({ off }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    {off && <line x1="2" y1="2" x2="22" y2="22" />}
  </svg>
);

// 롱프레스 시간 선택 프리셋 (분)
const PRESETS = [
  { label: "15분", min: 15 },
  { label: "30분", min: 30 },
  { label: "1시간", min: 60 },
  { label: "2시간", min: 120 },
  { label: "4시간", min: 240 },
  { label: "8시간", min: 480 },
  { label: "12시간", min: 720 },
  { label: "24시간", min: 1440 },
];

// 남은 시간 표기: 시=h, 분=m, 초=s (예: "2h 30m", "30m 12s")
function fmtRemain(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/* ── 알림 차단 (마스터 토글 + 일시중지 타이머) ── */
function MutePanel({ uid }) {
  const [mutedUntil, setMutedUntil] = useState(null);  // Date | null
  const [masterOff, setMasterOff] = useState(false);   // 마스터 차단 (무기한)
  const [now, setNow] = useState(Date.now());
  const [showPicker, setShowPicker] = useState(false);
  const longPressed = useRef(false);
  const timer = useRef(null);

  useEffect(() => {
    (async () => {
      const { data } = await supabase
        .from("settings").select("muted_until,alerts_master_off").eq("user_id", uid).single();
      if (data?.muted_until) setMutedUntil(new Date(data.muted_until));
      setMasterOff(!!data?.alerts_master_off);
    })();
  }, [uid]);

  // 1초마다 카운트다운 갱신
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const isMuted = mutedUntil && mutedUntil.getTime() > now;

  async function save(until) {
    setMutedUntil(until);
    await supabase.from("settings")
      .update({ muted_until: until ? until.toISOString() : null })
      .eq("user_id", uid);
  }
  async function saveMaster(v) {
    setMasterOff(v);
    await supabase.from("settings")
      .update({ alerts_master_off: v })
      .eq("user_id", uid);
  }

  function addMinutes(min) {
    const base = isMuted ? mutedUntil.getTime() : Date.now();
    save(new Date(base + min * 60000));
  }
  function setMinutes(min) {
    save(new Date(Date.now() + min * 60000));
    setShowPicker(false);
  }
  function clearMute() {
    save(null);
    setShowPicker(false);
  }

  // 탭 = +30분, 롱프레스 = 시간선택
  function startPress() {
    if (masterOff) return;
    longPressed.current = false;
    timer.current = setTimeout(() => {
      longPressed.current = true;
      setShowPicker(true);
      try { navigator.vibrate(30); } catch {}
    }, 450);
  }
  function endPress() {
    if (masterOff) return;
    clearTimeout(timer.current);
    if (!longPressed.current) addMinutes(30);  // 탭
  }
  function cancelPress() { clearTimeout(timer.current); }

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      {/* 마스터 차단 토글 */}
      <div className="toggle-row" style={{ marginTop: 0 }}>
        <div>
          <div className="toggle-label">알림 전체 차단</div>
          <div className="toggle-desc">켜면 모든 텔레그램 알림이 무기한 차단됩니다(타이머와 별개).</div>
        </div>
        <label className="switch">
          <input type="checkbox" checked={masterOff} onChange={(e) => saveMaster(e.target.checked)} />
          <span />
        </label>
      </div>

      {/* 일시중지 타이머 */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, opacity: masterOff ? 0.4 : 1 }}>
        <button
          className="mute-bell"
          disabled={masterOff}
          onMouseDown={startPress}
          onMouseUp={endPress}
          onMouseLeave={cancelPress}
          onTouchStart={(e) => { e.preventDefault(); startPress(); }}
          onTouchEnd={(e) => { e.preventDefault(); endPress(); }}
          onContextMenu={(e) => e.preventDefault()}
          style={{
            background: isMuted ? "var(--down-bg)" : "var(--bg-elev)",
            color: isMuted ? "var(--down)" : "var(--text-dim)",
            cursor: masterOff ? "not-allowed" : "pointer",
          }}
        >
          <BellIcon off={isMuted || masterOff} />
        </button>

        <div style={{ flex: 1, minWidth: 0 }}>
          {isMuted ? (
            <>
              <div style={{ fontWeight: 600, color: "var(--down)" }}>알림 중지 중</div>
              <div style={{ fontWeight: 600, color: "var(--down)", fontFamily: "var(--mono)" }}>
                {fmtRemain(mutedUntil.getTime() - now)} 남음
              </div>
              <div className="hint" style={{ fontSize: 11, marginTop: 4 }}>
                일시중지: 탭 +30분 · 길게 눌러 시간선택
              </div>
            </>
          ) : (
            <>
              <div style={{ fontWeight: 600 }}>알림 켜짐</div>
              <div className="hint" style={{ fontSize: 11, marginTop: 2 }}>
                일시중지: 탭 +30분 · 길게 눌러 시간선택
              </div>
            </>
          )}
        </div>

        {isMuted && !masterOff && (
          <button className="btn-ghost" style={{ fontSize: 13 }} onClick={clearMute}>
            해제
          </button>
        )}
      </div>

      {showPicker && !masterOff && (
        <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {PRESETS.map((p) => (
            <button
              key={p.min}
              className="btn-ghost"
              style={{ fontSize: 13, flex: "1 0 22%" }}
              onClick={() => setMinutes(p.min)}
            >
              {p.label}
            </button>
          ))}
          <button
            className="btn-ghost"
            style={{ fontSize: 12, width: "100%", color: "var(--text-faint)" }}
            onClick={() => setShowPicker(false)}
          >
            닫기
          </button>
        </div>
      )}
    </div>
  );
}

/* ── 텔레그램 연결 (소형, 페이지 하단) ── */
function TelegramSection({ profile, onTelegramLinked }) {
  const [unlinking, setUnlinking] = useState(false);
  const tgLink = TELEGRAM_BOT_USERNAME
    ? `https://t.me/${TELEGRAM_BOT_USERNAME}?start=${profile.id}`
    : null;

  async function unlinkTelegram() {
    setUnlinking(true);
    await supabase.from("profiles").update({
      telegram_chat_id: null,
      telegram_linked: false,
      telegram_display_name: null,
    }).eq("id", profile.id);
    setUnlinking(false);
    if (onTelegramLinked) onTelegramLinked();
  }

  return (
    <div className="card tg-section-sm">
      <h3 style={{ margin: "0 0 10px", fontSize: 14 }}>텔레그램 연결</h3>
      {profile.telegram_linked ? (
        <div className="tg-connected">
          <div className="tg-name" style={{ fontSize: 13 }}>
            <span className="tg-dot" />
            연결됨
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
          <p className="muted" style={{ margin: "0 0 8px", fontSize: 12 }}>
            봇과 대화를 시작하면 알림이 연결됩니다. 연결 후 새로고침하세요.
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
        </div>
      ) : (
        <p className="muted" style={{ fontSize: 12 }}>
          봇 주소가 설정되지 않았습니다. 관리자에게 문의하세요.
        </p>
      )}
    </div>
  );
}

export default function Alerts({ profile, onTelegramLinked }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const { data } = await supabase
        .from("alerts")
        .select("*")
        .eq("user_id", profile.id)
        .order("created_at", { ascending: false })
        .limit(50);
      setAlerts(data ?? []);
      setLoading(false);
    })();
  }, [profile.id]);

  return (
    <>
      <MutePanel uid={profile.id} />
      <div className="card">
        <h2>알림 이력</h2>
        {loading ? (
          <p className="muted">불러오는 중…</p>
        ) : alerts.length === 0 ? (
          <p className="muted">아직 알림이 없습니다. 신호가 발생하면 여기와 텔레그램에 표시됩니다.</p>
        ) : (
          alerts.map((a) => (
            <div className="alert-item" key={a.id}>
              <span className="alert-time">
                {new Date(a.created_at).toLocaleString("ko-KR", {
                  month: "2-digit", day: "2-digit",
                  hour: "2-digit", minute: "2-digit",
                })}
              </span>
              <span><b>{a.ticker}</b> {a.level}</span>
              <a className="alert-link" href={tvLink(a.ticker)} target="_blank" rel="noreferrer">
                차트 ↗
              </a>
            </div>
          ))
        )}
      </div>

      <TelegramSection profile={profile} onTelegramLinked={onTelegramLinked} />
    </>
  );
}
