"""
텔레그램 알림 발송.
공용 봇 하나로 각 사용자의 chat_id에 발송.
"""
import os
import re
import urllib.request
import urllib.parse
import json

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
APP_URL = os.environ.get("APP_URL", "https://investment-assistant-navy.vercel.app")
# 알림 하단에 붙는 링크 (URL 노출 없이 문구에만 하이퍼링크)
_FOOTER = f'\n\n<a href="{APP_URL}/?screen=alerts">Investment Assistant</a>'


def _is_kr(ticker):
    return bool(re.match(r'^\d{6}', ticker.split('.')[0]))


def _ticker_display(ticker, name=None):
    """한국 주식은 코드 + 국문명, 나머지는 티커만."""
    base = ticker.split('.')[0]
    if _is_kr(ticker) and name and name not in (ticker, base):
        return f"{base} {name}"
    return base


def _fmt_price(price, ticker):
    """KRW는 정수, USD는 소숫점 2자리, 천단위 콤마."""
    if _is_kr(ticker):
        return f"{int(round(price)):,}"
    return f"{price:,.2f}"


def send_message(chat_id, text, with_footer=True):
    """단일 사용자에게 메시지 발송. 성공 여부 반환."""
    if not BOT_TOKEN or not chat_id:
        print(f"[telegram] skip: token/chat_id missing (chat={chat_id})")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text + (_FOOTER if with_footer else ""),
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


def format_buy_level(ticker, level, price, ath, dd, name=None):
    disp = _ticker_display(ticker, name)
    p = _fmt_price(price, ticker)
    a = _fmt_price(ath, ticker)
    return (
        f"🔻 <b>{disp} 매수 신호</b>\n"
        f"ATH 대비 <b>-{level}%</b> 하락 도달\n"
        f"현재가 {p}  |  ATH {a} ({dd:+.1f}%)"
    )


def format_sell(ticker, level, price, ath, gain, name=None):
    disp = _ticker_display(ticker, name)
    p = _fmt_price(price, ticker)
    a = _fmt_price(ath, ticker)
    if level == 0:
        return (
            f"🔺 <b>{disp} 매도 신호</b>\n"
            f"ATH <b>도달</b>\n"
            f"현재가 {p}  |  ATH {a}"
        )
    return (
        f"🔺 <b>{disp} 매도 신호</b>\n"
        f"ATH 대비 <b>+{level}%</b> 초과 상승\n"
        f"현재가 {p}  |  ATH {a}"
    )


def format_indicator(ticker, signals, name=None):
    disp = _ticker_display(ticker, name)
    lines = [f"📊 <b>{disp} 보조지표 신호</b>"]
    if signals.get("dmi_buy"):
        v = signals["dmi_values"]
        lines.append(f"• DMI 매수신호 (DI-={v['minus_di']}, ADX={v['adx']})")
    if signals.get("volume_spike"):
        lines.append("• 저점 대량거래 발생")
    return "\n".join(lines)


def format_watchlist(ticker, signals, name=None):
    disp = _ticker_display(ticker, name)
    v = signals["dmi_values"]
    return (
        f"⭐ <b>개별주식 DMI 매수 신호</b>\n"
        f"[{disp} DMI 매수신호 발생]\n"
        f"DI-={v['minus_di']}, ADX={v['adx']}"
    )
