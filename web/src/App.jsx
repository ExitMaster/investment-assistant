import React, { useEffect, useState } from "react";
import { supabase } from "./supabase.js";
import Login from "./screens/Login.jsx";
import Pending from "./screens/Pending.jsx";
import Dashboard, { MarqueeTape } from "./screens/Dashboard.jsx";
import Alerts from "./screens/Alerts.jsx";
import Settings from "./screens/Settings.jsx";
import Admin from "./screens/Admin.jsx";
import Backtest from "./screens/Backtest.jsx";

/* ── SVG 아이콘 ── */
const BellIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
);
const GearIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);
const SunIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);
const MoonIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);
const ShieldIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);
const ChartIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 3v5h5" />
    <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
    <path d="M12 7v5l4 2" />
  </svg>
);
const LogoutIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

export default function App() {
  const [session, setSession] = useState(undefined);
  const [profile, setProfile] = useState(null);
  const [screen, setScreen] = useState(() => {
    const s = new URLSearchParams(window.location.search).get("screen");
    return ["dashboard", "alerts", "settings", "admin", "backtest"].includes(s) ? s : "dashboard";
  });
  const [theme, setTheme] = useState(
    () => localStorage.getItem("ia-theme") || "dark"
  );
  const [toast, setToast] = useState(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("ia-theme", theme);
  }, [theme]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) =>
      setSession(s ?? null)
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  async function loadProfile() {
    if (!session) { setProfile(null); return; }
    const { data } = await supabase
      .from("profiles").select("*").eq("id", session.user.id).single();
    setProfile(data ?? null);
    // 색상 반전 설정 적용
    if (data) {
      const { data: st } = await supabase
        .from("settings").select("color_inverted").eq("user_id", data.id).single();
      document.documentElement.setAttribute(
        "data-color-inverted",
        st?.color_inverted ? "true" : "false"
      );
    }
  }
  useEffect(() => { loadProfile(); /* eslint-disable-next-line */ }, [session]);

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2600);
  };

  if (session === undefined)
    return <div className="center-screen"><p className="muted">불러오는 중…</p></div>;
  if (session === null) return <Login />;
  if (!profile)
    return <div className="center-screen"><p className="muted">프로필 확인 중…</p></div>;
  if (profile.status !== "active")
    return <Pending profile={profile} onSignOut={() => supabase.auth.signOut()} />;

  const isAdmin = profile.role === "admin";

  return (
    <div className="app-wrap">
      <div className="topbar">
        <div className="topbar-row">
          <div className="brand" onClick={() => setScreen("dashboard")}>
            Investment Assistant
          </div>
          <div className="topbar-actions">
            <button
              className={`icon-btn ${screen === "backtest" ? "active" : ""}`}
              onClick={() => setScreen("backtest")}
              title="백테스트"
            >
              <ChartIcon />
            </button>
            <button
              className={`icon-btn ${screen === "alerts" ? "active" : ""}`}
              onClick={() => setScreen("alerts")}
              title="알림"
            >
              <BellIcon />
            </button>
            {isAdmin && (
              <button
                className={`icon-btn ${screen === "admin" ? "active" : ""}`}
                onClick={() => setScreen("admin")}
                title="관리자"
              >
                <ShieldIcon />
              </button>
            )}
            <button
              className="icon-btn"
              onClick={() => supabase.auth.signOut()}
              title="로그아웃"
            >
              <LogoutIcon />
            </button>
            <button
              className="icon-btn"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              title={theme === "dark" ? "밝은 모드로 전환" : "다크 모드로 전환"}
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
            <button
              className={`icon-btn ${screen === "settings" ? "active" : ""}`}
              onClick={() => setScreen("settings")}
              title="설정"
            >
              <GearIcon />
            </button>
          </div>
        </div>
        <MarqueeTape uid={profile.id} />
      </div>

      <div className="screen-content">
        {screen === "dashboard" && (
          <Dashboard profile={profile} flash={flash} />
        )}
        {screen === "backtest" && <Backtest profile={profile} />}
        {screen === "alerts" && (
          <Alerts profile={profile} onTelegramLinked={loadProfile} />
        )}
        {screen === "settings" && (
          <Settings
            profile={profile}
            flash={flash}
            onTelegramLinked={loadProfile}
          />
        )}
        {screen === "admin" && isAdmin && <Admin flash={flash} />}
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
