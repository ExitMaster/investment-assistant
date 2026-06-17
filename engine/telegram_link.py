"""
텔레그램 chat_id 자동 등록기.
사용자가 웹앱의 '텔레그램 봇 연결하기' 버튼을 누르면
  https://t.me/<bot>?start=<user_id>
로 봇과 대화가 시작되고, 봇은 '/start <user_id>' 메시지를 받는다.
이 스크립트가 getUpdates로 그 메시지를 읽어
profiles.telegram_chat_id 와 telegram_display_name 에 저장한다.

GitHub Actions에서 수 분 간격으로 실행.
"""
import os
import json
import urllib.request
import urllib.parse

import db
import notify

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _send_admins(text, exclude=None):
    """모든 관리자(텔레그램 연결됨)에게 발송. 한 명이라도 성공하면 True."""
    chat_ids = db.get_admin_chat_ids(exclude=exclude)
    ok = False
    for cid in chat_ids:
        if notify.send_message(cid, text, with_footer=False):
            ok = True
    return ok


def notify_admin_events():
    """신규 가입 요청·텔레그램 해지를 관리자에게 통지(폴링 기반)."""
    # 신규 가입 요청
    for u in db.get_pending_unnotified():
        text = notify.format_admin_new_user(u.get("display_name"), u.get("email"))
        if _send_admins(text):
            db.mark_admin_notified(u["id"])
            print(f"[admin] notified new user {u.get('email')}")
    # 텔레그램 연결 해지 (웹앱이 플래그 설정)
    for u in db.get_pending_unlink_notify():
        text = notify.format_admin_tg_unlinked(u.get("display_name"), u.get("email"))
        # 해지 알림은 한 번 통지하면 관리자 부재 여부와 무관하게 플래그를 내린다
        _send_admins(text)
        db.clear_unlink_notify(u["id"])
        print(f"[admin] notified unlink {u.get('email')}")


def tg_api(method, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"[tg] {method} error: {e}")
        return None


def main():
    if not BOT_TOKEN:
        print("no bot token"); return

    # 신규 가입·해지 등 관리자 통지 먼저 처리
    notify_admin_events()

    res = tg_api("getUpdates", {"timeout": 0})
    if not res or not res.get("ok"):
        print("getUpdates failed"); return

    updates = res.get("result", [])
    print(f"[tg] {len(updates)} updates")
    last_id = None

    for upd in updates:
        last_id = upd["update_id"]
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        text = (msg.get("text") or "").strip()
        chat_id = msg["chat"]["id"]

        # 발신자 표시명: @username 우선, 없으면 이름
        from_user = msg.get("from", {})
        username = from_user.get("username")
        first_name = from_user.get("first_name", "")
        last_name = from_user.get("last_name", "")
        if username:
            display_name = f"@{username}"
        elif first_name or last_name:
            display_name = f"{first_name} {last_name}".strip()
        else:
            display_name = str(chat_id)

        # '/start <user_id>' 처리
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                user_id = parts[1].strip()
                r = db.link_telegram(user_id, chat_id, display_name=display_name)
                if r is not None:
                    tg_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": "✅ 연결되었습니다. 이제 매수/매도 신호 알림을 이 채팅으로 받습니다.",
                    })
                    print(f"[tg] linked user={user_id} chat={chat_id} name={display_name}")
                    # 관리자에게 연결 사실 통지(방금 연결한 본인 제외)
                    prof = db.get_profile(user_id)
                    if prof:
                        text = notify.format_admin_tg_linked(
                            prof.get("display_name"), prof.get("email"), display_name)
                        _send_admins(text, exclude=chat_id)
                else:
                    tg_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": "연결에 실패했습니다. 웹앱에서 다시 시도해 주세요.",
                    })
            else:
                tg_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": "웹앱의 '텔레그램 봇 연결하기' 버튼으로 접속해 주세요.",
                })

    if last_id is not None:
        tg_api("getUpdates", {"offset": last_id + 1, "timeout": 0})


if __name__ == "__main__":
    main()
