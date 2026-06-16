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

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


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
