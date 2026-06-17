import React from "react";

export default function Pending({ profile, onSignOut }) {
  const blocked = profile.status === "blocked";
  return (
    <div className="center-screen">
      <div className="brand" style={{ fontSize: 22 }}>
        Investment Assistant
      </div>
      {blocked ? (
        <p className="muted" style={{ maxWidth: 360 }}>
          이 계정은 접근이 중지되었습니다. 관리자에게 문의하세요.
        </p>
      ) : (
        <p className="muted" style={{ maxWidth: 360 }}>
          승인 대기 중입니다.<br />
          관리자가 <b>{profile.email}</b> 계정을 승인하면 알림 설정을 시작할 수 있습니다.
        </p>
      )}
      <button className="btn-ghost" onClick={onSignOut}>로그아웃</button>
    </div>
  );
}
