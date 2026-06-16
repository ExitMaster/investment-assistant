"""
Supabase 연동 (엔진용, service_role/secret key 사용 → RLS 우회).
외부 라이브러리 없이 REST API 직접 호출.
"""
import os
import json
import urllib.request
import urllib.parse

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

BASE = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SECRET_KEY,
    "Authorization": f"Bearer {SECRET_KEY}",
    "Content-Type": "application/json",
}


def _request(method, path, params=None, body=None, prefer=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe="*().,")
    headers = dict(HEADERS)
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else []
    except urllib.error.HTTPError as e:
        print(f"[supabase] {method} {path} -> {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        print(f"[supabase] {method} {path} error: {e}")
        return None


def get_active_users():
    """status=active 인 사용자 + 설정 조회."""
    rows = _request("GET", "profiles", params={
        "select": "id,email,display_name,telegram_chat_id,telegram_linked,status",
        "status": "eq.active",
    })
    return rows or []


def get_settings(user_id):
    rows = _request("GET", "settings", params={
        "user_id": f"eq.{user_id}", "select": "*",
    })
    return rows[0] if rows else None


def get_index_tickers(user_id):
    """index_tickers 테이블에서 사용자의 ATH 감시 티커 목록 반환."""
    rows = _request("GET", "index_tickers", params={
        "user_id": f"eq.{user_id}", "select": "ticker",
    })
    return [r["ticker"] for r in (rows or [])]


def get_watchlist(user_id):
    rows = _request("GET", "watchlist", params={
        "user_id": f"eq.{user_id}", "select": "ticker",
    })
    return [r["ticker"] for r in (rows or [])]


def get_ath_state(user_id, ticker):
    rows = _request("GET", "ath_state", params={
        "user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}", "select": "*",
    })
    return rows[0] if rows else None


def upsert_ath_state(state):
    """state: dict with user_id, ticker, ath, running_high, ... (PK: user_id,ticker)"""
    return _request("POST", "ath_state", body=state,
                    prefer="resolution=merge-duplicates")


def insert_alert(alert):
    return _request("POST", "alerts", body=alert, prefer="return=minimal")


def link_telegram(user_id, chat_id):
    return _request("PATCH", "profiles",
                    params={"id": f"eq.{user_id}"},
                    body={"telegram_chat_id": str(chat_id), "telegram_linked": True},
                    prefer="return=minimal")
