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


def _admin_footer():
    return f'\n\n<a href="{APP_URL}/?screen=admin">관리자 페이지 열기</a>'


def format_admin_new_user(name, email):
    """신규 가입 요청 알림 (관리자용). Gmail 검색·관리자 페이지 링크 포함."""
    name_disp = name or "(이름 없음)"
    line = f"🆕 <b>신규 가입 요청</b>\n이름: {name_disp}"
    if email:
        gmail = "https://mail.google.com/mail/u/0/#search/" + urllib.parse.quote(email)
        line += f"\n이메일: {email}\n\n<a href=\"{gmail}\">📬 Gmail에서 이 사용자 찾기</a>"
    return line + _admin_footer()


def format_admin_tg_linked(name, email, tg_name):
    """텔레그램 연결됨 알림 (관리자용)."""
    name_disp = name or "(이름 없음)"
    who = f"{name_disp} ({email})" if email else name_disp
    return (
        f"📲 <b>텔레그램 연결됨</b>\n"
        f"{who}\n"
        f"→ {tg_name}"
        f"{_admin_footer()}"
    )


def format_admin_tg_unlinked(name, email):
    """텔레그램 연결 해지 알림 (관리자용)."""
    name_disp = name or "(이름 없음)"
    who = f"{name_disp} ({email})" if email else name_disp
    return (
        f"🔕 <b>텔레그램 연결 해지</b>\n"
        f"{who}"
        f"{_admin_footer()}"
    )


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


def _tv_link(ticker):
    """TradingView 차트 URL. 모바일에 앱이 설치돼 있으면 앱으로 열린다(유니버설 링크)."""
    if _is_kr(ticker):
        sym = f"KRX:{ticker.split('.')[0]}"
    else:
        sym = ticker
    return "https://www.tradingview.com/chart/?symbol=" + urllib.parse.quote(sym, safe=":")


def _ticker_link(ticker, name=None):
    """티커 표시명을 TradingView 링크로 감싼다."""
    return f'<a href="{_tv_link(ticker)}">{_ticker_display(ticker, name)}</a>'


def _dir_icon(is_up_event, inverted=False):
    """방향+색상 아이콘. is_up_event: True=상승(매도)·False=하락(매수).
    기본 색상은 상승=초록·하락=빨강. color_inverted면 반대."""
    green = (is_up_event != inverted)
    return ("🟢" if green else "🔴") + ("⬆️" if is_up_event else "⬇️")


def _chg_suffix(price, prev_close):
    """전일 종가 대비 등락률 꼬리표. prev_close 없으면 빈 문자열."""
    if not prev_close:
        return ""
    pct = (price / prev_close - 1) * 100
    arrow = "▲" if pct >= 0 else "▼"
    return f"  {arrow}{abs(pct):.1f}% (전일)"


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


def _buy_action_line(action):
    """매수 행동 안내 라인. action: {'product':..., 'cash':...} 또는 None."""
    if not action:
        return ""
    prod = (action.get("product") or "").strip()
    cash = action.get("cash")
    has_cash = cash not in (None, "")
    if prod and has_cash:
        return f"\n→ {prod} 매수 · 현금성 자산의 {cash}%"
    if prod:
        return f"\n→ {prod} 매수"
    if has_cash:
        return f"\n→ 현금성 자산의 {cash}% 매수"
    return ""


def format_buy_level(ticker, level, price, ath, dd, name=None, action=None,
                     inverted=False, prev_close=None, next_level=None, next_gap=None):
    """매수 레벨 도달 알림.
    dd: ATH 대비 현재 등락률(음수). next_level/next_gap: 다음 매수레벨과 남은 %p."""
    icon = _dir_icon(False, inverted)
    link = _ticker_link(ticker, name)
    p = _fmt_price(price, ticker)
    a = _fmt_price(ath, ticker)
    lines = [
        f"{icon} <b>{link} 매수 신호</b>",
        f"매수 <b>-{level}%</b> 레벨 도달",
        f"현재가 {p}{_chg_suffix(price, prev_close)}",
        f"ATH {a}  ·  현재 {dd:+.1f}%",
    ]
    if next_level is not None and next_gap is not None:
        lines.append(f"다음 -{next_level}%까지 -{next_gap:.1f}%p")
    return "\n".join(lines) + _buy_action_line(action)


def format_prealert(ticker, level, price, ath, dd, gap, name=None, action=None):
    """다음 매수레벨 임박 예고. gap: 레벨까지 남은 %p(양수)."""
    disp = _ticker_link(ticker, name)
    p = _fmt_price(price, ticker)
    a = _fmt_price(ath, ticker)
    line = _buy_action_line(action)
    prep = line.replace(" 매수", " 매수 준비") if line else ""
    return (
        f"⏳ <b>{disp} -{level}% 매수레벨 임박</b>\n"
        f"현재 {dd:+.1f}% · 레벨까지 -{gap:.1f}%p 남음\n"
        f"현재가 {p}  |  ATH {a}"
        f"{prep}"
    )


def format_prealert_sell(ticker, level, price, ath, gain, gap, name=None):
    """다음 매도레벨 임박 예고. gap: 레벨까지 남은 %p(양수)."""
    disp = _ticker_link(ticker, name)
    p = _fmt_price(price, ticker)
    a = _fmt_price(ath, ticker)
    target = "ATH 도달" if level == 0 else f"+{level}%"
    return (
        f"⏳ <b>{disp} 매도레벨 임박</b>\n"
        f"{target}까지 +{gap:.1f}%p 남음 (현재 {gain:+.1f}%)\n"
        f"현재가 {p}  |  ATH {a}"
    )


def format_sell(ticker, level, price, ath, gain, name=None, cash_target=None,
                inverted=False, prev_close=None, next_level=None, next_gap=None):
    """매도 레벨(ATH 도달/초과) 알림.
    gain: ATH 대비 현재 등락률. next_level/next_gap: 다음 매도레벨과 남은 %p."""
    icon = _dir_icon(True, inverted)
    link = _ticker_link(ticker, name)
    p = _fmt_price(price, ticker)
    a = _fmt_price(ath, ticker)
    head = "매도 <b>ATH 도달</b>" if level == 0 else f"매도 <b>+{level}%</b> 레벨 도달"
    lines = [
        f"{icon} <b>{link} 매도 신호</b>",
        head,
        f"현재가 {p}{_chg_suffix(price, prev_close)}",
        f"ATH {a}  ·  현재 {gain:+.1f}%",
    ]
    if next_level is not None and next_gap is not None:
        lines.append(f"다음 +{next_level}%까지 +{next_gap:.1f}%p")
    tail = f"\n→ 레버리지 높은 종목부터 매도 · 현금비중 {cash_target}% 목표" if cash_target not in (None, "") else ""
    return "\n".join(lines) + tail


def format_indicator(ticker, signals, name=None):
    """매수 계열 보조지표 신호. 발생한 항목이 없으면 None."""
    disp = _ticker_link(ticker, name)
    v = signals.get("dmi_values", {})
    lines = []
    if signals.get("dmi_buy"):
        lines.append(f"• DMI 매수신호 (DI-={v.get('minus_di')}, ADX={v.get('adx')})")
    if signals.get("dmi_imminent"):
        lines.append(f"• DMI 매수신호 임박 (DI-={v.get('minus_di')} ≳ ADX={v.get('adx')})")
    if signals.get("bull_div"):
        bv = signals.get("bull_div_values") or {}
        lines.append(f"• 상승 다이버전스 (%K {bv.get('k1')}→{bv.get('k2')} 상향)")
    if signals.get("low_vol_breakout"):
        r = signals.get("vol_ratio")
        lines.append(f"• 저점 대량거래 돌파{f' (거래량 x{r})' if r else ''}")
    if not lines:
        return None
    return f"📊 <b>{disp} 예외적 매수 신호</b>\n" + "\n".join(lines)


def format_sell_indicator(ticker, signals, name=None):
    """매도 계열 보조지표 예외 신호. 발생한 항목이 없으면 None."""
    disp = _ticker_link(ticker, name)
    lines = []
    if signals.get("bear_div"):
        bv = signals.get("bear_div_values") or {}
        lines.append(f"• 하락 다이버전스 (%K {bv.get('k1')}→{bv.get('k2')} 하향)")
    if signals.get("high_vol_breakout"):
        r = signals.get("vol_ratio")
        lines.append(f"• 고점 대량거래 이탈{f' (거래량 x{r})' if r else ''}")
    if not lines:
        return None
    return f"📉 <b>{disp} 예외적 매도 신호</b>\n" + "\n".join(lines)


def format_watchlist(ticker, signals, name=None):
    disp = _ticker_link(ticker, name)
    v = signals["dmi_values"]
    return (
        f"⭐ <b>{disp} 개별주식 DMI 매수 신호</b>\n"
        f"DI-={v['minus_di']}, ADX={v['adx']}"
    )
