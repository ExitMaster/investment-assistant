"""
텔레그램 chat_id 자동 등록기.
사용자가 웹앱의 '텔레그램 봇 연결하기' 버튼을 누르면
  https://t.me/<bot>?start=<user_id>
로 봇과 대화가 시작되고, 봇은 '/start <user_id>' 메시지를 받는다.
이 스크립트가 getUpdates로 그 메시지를 읽어
profiles.telegram_chat_id 에 chat_id를 저장한다.

GitHub Actions에서 수 분 간격으로 실행.
offset은 ath_state와 별도로 telegram_offset 키에 보관(간단히 파일 대신 DB의 전용 행 사용은 생략하고 매번 마지막 update만 처리).
"""
import os
import json
import urllib.request
import urllib.parse

import db  # 같은 폴더의 db.py 재사용

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

        # '/start <user_id>' 처리
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                user_id = parts[1].strip()
                r = db.link_telegram(user_id, chat_id)
                if r is not None:
                    tg_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": "✅ 연결되었습니다. 이제 매수/매도 신호 알림을 이 채팅으로 받습니다.",
                    })
                    print(f"[tg] linked user={user_id} chat={chat_id}")
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

    # 처리한 업데이트 확인(offset 전진) — 다음 호출에서 같은 메시지 재처리 방지
    if last_id is not None:
        tg_api("getUpdates", {"offset": last_id + 1, "timeout": 0})


if __name__ == "__main__":
    main()
