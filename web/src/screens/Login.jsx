import React from "react";
import { supabase } from "../supabase.js";

export default function Login() {
  async function signIn() {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
  }
  return (
    <div className="center-screen">
      <div>
        <div className="brand" style={{ fontSize: 26, marginBottom: 6 }}>
          Investment<span className="dot">·</span>Assistant
        </div>
        <p className="muted" style={{ maxWidth: 340 }}>
          지수가 고점 대비 설정한 폭만큼 하락하면 텔레그램으로 매수 신호를 보냅니다.
          접속하지 않아도 알림이 도착합니다.
        </p>
      </div>
      <button className="btn-primary" onClick={signIn} style={{ minWidth: 220 }}>
        Google로 계속하기
      </button>
      <p className="muted" style={{ fontSize: 13 }}>
        가입 후 관리자 승인이 있어야 알림이 시작됩니다.
      </p>
    </div>
  );
}
