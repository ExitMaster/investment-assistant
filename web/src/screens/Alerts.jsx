import React, { useEffect, useState, useRef } from "react";
import { supabase } from "../supabase.js";

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

function fmtRemain(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}시간 ${m}분`;
  if (m > 0) return `${m}분 ${s}초`;
  return `${s}초`;
}

/* ── 알림 일시중지 ── */
function MutePanel({ uid }) {
  const [mutedUntil, setMutedUntil] = useState(null);  // Date | null
  const [now, setNow] = useState(Date.now());
  const [showPicker, setShowPicker] = useState(false);
  const longPressed = useRef(false);
  const timer = useRef(null);

  useEffect(() => {
    (async () => {
      const { data } = await supabase
        .from("settings").select("muted_until").eq("user_id", uid).single();
      if (data?.muted_until) setMutedUntil(new Date(data.muted_until));
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
    longPressed.current = false;
    timer.current = setTimeout(() => {
      longPressed.current = true;
      setShowPicker(true);
      try { navigator.vibrate(30); } catch {}
    }, 450);
  }
  function endPress() {
    clearTimeout(timer.current);
    if (!longPressed.current) addMinutes(30);  // 탭
  }
  function cancelPress() { clearTimeout(timer.current); }

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <button
          className="mute-bell"
          onMouseDown={startPress}
          onMouseUp={endPress}
          onMouseLeave={cancelPress}
          onTouchStart={(e) => { e.preventDefault(); startPress(); }}
          onTouchEnd={(e) => { e.preventDefault(); endPress(); }}
          onContextMenu={(e) => e.preventDefault()}
          style={{
            background: isMuted ? "var(--down-bg)" : "var(--bg-elev)",
            color: isMuted ? "var(--down)" : "var(--text-dim)",
          }}
        >
          <BellIcon off={isMuted} />
        </button>

        <div style={{ flex: 1, minWidth: 0 }}>
          {isMuted ? (
            <>
              <div style={{ fontWeight: 600, color: "var(--down)" }}>
                알림 중지 중 · {fmtRemain(mutedUntil.getTime() - now)} 남음
              </div>
              <div className="hint" style={{ fontSize: 11, marginTop: 2 }}>
                탭 +30분 · 롱프레스 시간선택
              </div>
            </>
          ) : (
            <>
              <div style={{ fontWeight: 600 }}>알림 켜짐</div>
              <div className="hint" style={{ fontSize: 11, marginTop: 2 }}>
                탭 +30분 · 롱프레스 시간선택
              </div>
            </>
          )}
        </div>

        {isMuted && (
          <button className="btn-ghost" style={{ fontSize: 13 }} onClick={clearMute}>
            해제
          </button>
        )}
      </div>

      {showPicker && (
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

export default function Alerts({ profile }) {
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
    </>
  );
}
