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
          Investment Assistant
        </div>
        <p className="muted" style={{ maxWidth: 340 }}>
          웹에 접속해 있지 않더라도 “무한주식투자시스템”에 따른 매수∙매도 신호를
          텔레그램 알림으로 보냅니다.
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
