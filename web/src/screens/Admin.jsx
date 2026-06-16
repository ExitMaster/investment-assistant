import React, { useEffect, useState } from "react";
import { supabase } from "../supabase.js";

const STATUS_LABEL = { pending: "대기", active: "활성", blocked: "중지" };

export default function Admin({ flash }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const { data } = await supabase
      .from("profiles")
      .select("id,email,display_name,role,status,telegram_linked,telegram_display_name,created_at")
      .order("created_at", { ascending: false });
    setUsers(data ?? []);
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

  if (loading) return <div className="card"><p className="muted">사용자 불러오는 중…</p></div>;

  return (
    <div className="card">
      <h2>사용자 관리 ({users.length})</h2>
      {users.map((u) => (
        <div key={u.id} style={{ padding: "14px 0", borderBottom: "1px solid var(--border)" }}>
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
            <span className={`chip`} style={{
              background: u.status === "active" ? "var(--up-bg)" : u.status === "blocked" ? "var(--down-bg)" : "var(--bg-elev)",
              color: u.status === "active" ? "var(--up)" : u.status === "blocked" ? "var(--down)" : "var(--text-dim)",
            }}>{STATUS_LABEL[u.status]}</span>
          </div>
          <div className="row-inline" style={{ marginTop: 10 }}>
            {u.status !== "active" && <button className="btn-ghost" onClick={() => setStatus(u.id, "active")}>승인</button>}
            {u.status === "active" && <button className="btn-danger" onClick={() => setStatus(u.id, "blocked")}>중지</button>}
            {u.status === "blocked" && <button className="btn-ghost" onClick={() => setStatus(u.id, "pending")}>대기로</button>}
            {u.role === "user"
              ? <button className="btn-ghost" onClick={() => setRole(u.id, "admin")}>admin 부여</button>
              : <button className="btn-ghost" onClick={() => setRole(u.id, "user")}>admin 해제</button>}
          </div>
        </div>
      ))}
    </div>
  );
}
