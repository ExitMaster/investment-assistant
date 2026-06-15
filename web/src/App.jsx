import React, { useEffect, useState } from "react";
import { supabase } from "./supabase.js";
import Login from "./screens/Login.jsx";
import Pending from "./screens/Pending.jsx";
import Dashboard from "./screens/Dashboard.jsx";
import Settings from "./screens/Settings.jsx";
import Admin from "./screens/Admin.jsx";

export default function App() {
  const [session, setSession] = useState(undefined); // undefined=로딩, null=로그아웃
  const [profile, setProfile] = useState(null);
  const [tab, setTab] = useState("dashboard");
  const [toast, setToast] = useState(null);

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2600);
  };

  // 세션 추적
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s ?? null));
    return () => sub.subscription.unsubscribe();
  }, []);

  // 프로필 로드
  async function loadProfile() {
    if (!session) { setProfile(null); return; }
    const { data } = await supabase
      .from("profiles")
      .select("*")
      .eq("id", session.user.id)
      .single();
    setProfile(data ?? null);
  }
  useEffect(() => { loadProfile(); /* eslint-disable-next-line */ }, [session]);

  if (session === undefined) {
    return <div className="center-screen"><p className="muted">불러오는 중…</p></div>;
  }
  if (session === null) return <Login />;
  if (!profile) return <div className="center-screen"><p className="muted">프로필 확인 중…</p></div>;
  if (profile.status !== "active") {
    return <Pending profile={profile} onSignOut={() => supabase.auth.signOut()} />;
  }

  const isAdmin = profile.role === "admin";

  return (
    <div className="app-wrap">
      <div className="topbar">
        <div className="brand">Investment<span className="dot">·</span>Assistant</div>
        <button className="btn-ghost" onClick={() => supabase.auth.signOut()}>로그아웃</button>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "dashboard" ? "active" : ""}`} onClick={() => setTab("dashboard")}>대시보드</button>
        <button className={`tab ${tab === "settings" ? "active" : ""}`} onClick={() => setTab("settings")}>설정</button>
        {isAdmin && <button className={`tab ${tab === "admin" ? "active" : ""}`} onClick={() => setTab("admin")}>관리자</button>}
      </div>

      {tab === "dashboard" && <Dashboard profile={profile} flash={flash} />}
      {tab === "settings" && <Settings profile={profile} flash={flash} onTelegramLinked={loadProfile} />}
      {tab === "admin" && isAdmin && <Admin flash={flash} />}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
