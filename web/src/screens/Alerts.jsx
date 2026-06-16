import React, { useEffect, useState } from "react";
import { supabase } from "../supabase.js";

function tvLink(sym) {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
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

  if (loading) return <div className="card"><p className="muted">불러오는 중…</p></div>;

  return (
    <div className="card">
      <h2>알림 이력</h2>
      {alerts.length === 0 ? (
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
  );
}
