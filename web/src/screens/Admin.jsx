import React, { useEffect, useState } from "react";
import { supabase } from "../supabase.js";

const STATUS_LABEL = { pending: "대기", active: "활성", blocked: "중지" };

function displaySym(sym) { return sym.replace(/\.(KS|KQ)$/, ""); }

export default function Admin({ flash }) {
  const [users, setUsers] = useState([]);
  const [tickers, setTickers] = useState({});   // { user_id: { index, indicator, watchlist } }
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});  // { user_id: bool }

  async function load() {
    setLoading(true);
    const [{ data: profiles }, { data: ix }, { data: ind }, { data: wl }] = await Promise.all([
      supabase.from("profiles")
        .select("id,email,display_name,role,status,telegram_linked,telegram_display_name,created_at")
        .order("created_at", { ascending: false }),
      supabase.from("index_tickers").select("user_id,ticker,name"),
      supabase.from("indicator_tickers").select("user_id,ticker,name"),
      supabase.from("watchlist").select("user_id,ticker,name"),
    ]);

    setUsers(profiles ?? []);

    const map = {};
    for (const row of (ix ?? [])) {
      if (!map[row.user_id]) map[row.user_id] = { index: [], indicator: [], watchlist: [] };
      map[row.user_id].index.push(row);
    }
    for (const row of (ind ?? [])) {
      if (!map[row.user_id]) map[row.user_id] = { index: [], indicator: [], watchlist: [] };
      map[row.user_id].indicator.push(row);
    }
    for (const row of (wl ?? [])) {
      if (!map[row.user_id]) map[row.user_id] = { index: [], indicator: [], watchlist: [] };
      map[row.user_id].watchlist.push(row);
    }
    setTickers(map);
    setLoading(false);
  }
  useEffect(() => { load(); }, []);

  async function setStatus(id, status) {
    const { error } = await supabase.from("profiles").update({ status }).eq("id", id);
    if (error) return flash("실패: " + error.message);
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, status } : u)));
    flash(`상태: ${STATUS_LABEL[status]}`);
  }
  async function setRole(id, role) {
    const { error } = await supabase.from("profiles").update({ role }).eq("id", id);
    if (error) return flash("실패: " + error.message);
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, role } : u)));
    flash(`권한: ${role}`);
  }
  function confirmRole(u, role) {
    const who = u.display_name || u.email;
    const msg = role === "admin"
      ? `${who} 님에게 admin 권한을 부여할까요?`
      : `${who} 님의 admin 권한을 해제할까요?`;
    if (window.confirm(msg)) setRole(u.id, role);
  }

  if (loading) return <div className="card"><p className="muted">사용자 불러오는 중…</p></div>;

  return (
    <div className="card">
      <h2>사용자 관리 ({users.length})</h2>
      {users.map((u) => {
        const t = tickers[u.id] ?? { index: [], indicator: [], watchlist: [] };
        const totalTickers = t.index.length + t.indicator.length + t.watchlist.length;
        const isExpanded = expanded[u.id];
        return (
          <div key={u.id} style={{ padding: "14px 0", borderBottom: "1px solid var(--border)" }}>
            {/* 이름 · 상태 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  {u.display_name || u.email}
                  {u.role === "admin" && <span className="chip">admin</span>}
                  {u.telegram_linked
                    ? <span className="chip" style={{ background: "var(--up-bg)", color: "var(--up)" }}>
                        TG {u.telegram_display_name ? `· ${u.telegram_display_name}` : "연결됨"}
                      </span>
                    : <span className="chip" style={{ color: "var(--text-faint)" }}>TG 미연결</span>
                  }
                </div>
                <div className="t-sub">{u.email}</div>
              </div>
              <span className="chip" style={{
                background: u.status === "active" ? "var(--up-bg)" : u.status === "blocked" ? "var(--down-bg)" : "var(--bg-elev)",
                color: u.status === "active" ? "var(--up)" : u.status === "blocked" ? "var(--down)" : "var(--text-dim)",
              }}>{STATUS_LABEL[u.status]}</span>
            </div>

            {/* 티커 요약 (클릭 시 펼치기) */}
            <div
              style={{ marginTop: 8, cursor: totalTickers > 0 ? "pointer" : "default", userSelect: "none" }}
              onClick={() => totalTickers > 0 && setExpanded((e) => ({ ...e, [u.id]: !e[u.id] }))}
            >
              {totalTickers === 0 ? (
                <span style={{ fontSize: 11, color: "var(--text-faint)" }}>티커 없음</span>
              ) : (
                <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                  {t.index.length > 0 && `ATH ${t.index.length}개`}
                  {t.index.length > 0 && (t.indicator.length > 0 || t.watchlist.length > 0) && " · "}
                  {t.indicator.length > 0 && `기술신호 ${t.indicator.length}개`}
                  {t.indicator.length > 0 && t.watchlist.length > 0 && " · "}
                  {t.watchlist.length > 0 && `개별주식 ${t.watchlist.length}개`}
                  <span style={{ marginLeft: 6, color: "var(--accent)" }}>{isExpanded ? "▲" : "▼"}</span>
                </span>
              )}
            </div>

            {/* 펼쳤을 때 티커 목록 */}
            {isExpanded && (
              <div style={{ marginTop: 8, paddingLeft: 4, fontSize: 12, color: "var(--text-dim)" }}>
                {[
                  { label: "ATH 감시", rows: t.index },
                  { label: "기술신호", rows: t.indicator },
                  { label: "개별주식", rows: t.watchlist },
                ].filter(g => g.rows.length > 0).map(g => (
                  <div key={g.label} style={{ marginBottom: 4 }}>
                    <span style={{ color: "var(--text-faint)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      {g.label}
                    </span>
                    <span style={{ marginLeft: 8 }}>
                      {g.rows.map(r => (
                        <span key={r.ticker} style={{ marginRight: 8 }}>
                          <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: "var(--text)" }}>{displaySym(r.ticker)}</span>
                          {r.name && <span style={{ color: "var(--text-faint)", marginLeft: 3 }}>{r.name}</span>}
                        </span>
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* 관리 버튼 */}
            <div className="row-inline" style={{ marginTop: 10 }}>
              {u.status !== "active" && <button className="btn-ghost" onClick={() => setStatus(u.id, "active")}>승인</button>}
              {u.status === "active" && <button className="btn-danger" onClick={() => setStatus(u.id, "blocked")}>중지</button>}
              {u.status === "blocked" && <button className="btn-ghost" onClick={() => setStatus(u.id, "pending")}>대기로</button>}
              {u.role === "user"
                ? <button className="btn-ghost" onClick={() => confirmRole(u, "admin")}>admin 부여</button>
                : <button className="btn-ghost" onClick={() => confirmRole(u, "user")}>admin 해제</button>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
