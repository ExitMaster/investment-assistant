"""
텔레그램 알림 발송.
공용 봇 하나로 각 사용자의 chat_id에 발송.
"""
import os
import urllib.request
import urllib.parse
import json

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def send_message(chat_id, text):
    """단일 사용자에게 메시지 발송. 성공 여부 반환."""
    if not BOT_TOKEN or not chat_id:
        print(f"[telegram] skip: token/chat_id missing (chat={chat_id})")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode())
            return res.get("ok", False)
    except Exception as e:
        print(f"[telegram] send failed: {e}")
        return False


def format_buy_level(ticker, display, level, price, ath, dd):
    return (
        f"🔻 <b>{ticker} 매수 신호</b>\n"
        f"고점 대비 <b>-{level}%</b> 도달\n"
        f"현재가 {price:.2f} (ATH {ath:.2f}, {dd:+.1f}%)\n"
        f"참고: {display}"
    )


def format_sell(ticker, level, price, ath, gain):
    return (
        f"🔺 <b>{ticker} 매도 신호</b>\n"
        f"고점 대비 <b>+{level}%</b> 초과 상승\n"
        f"현재가 {price:.2f} (ATH {ath:.2f}, +{gain:.1f}%)"
    )


def format_indicator(ticker, signals):
    lines = [f"📊 <b>{ticker} 보조지표</b>"]
    if signals.get("dmi_buy"):
        v = signals["dmi_values"]
        lines.append(f"• DMI 매수신호 (DI-={v['minus_di']}, ADX={v['adx']})")
    if signals.get("volume_spike"):
        lines.append("• 저점 대량거래 발생")
    return "\n".join(lines)


def format_watchlist(ticker, signals):
    v = signals["dmi_values"]
    return (
        f"⭐ <b>{ticker} 매수신호</b> (관찰종목)\n"
        f"DMI: DI-={v['minus_di']}, ADX={v['adx']}"
    )
