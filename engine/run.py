"""
Investment Assistant — 엔진 메인 러너
GitHub Actions에서 주기 실행.

모드:
  python run.py intraday    # 5분마다: 하락률 매수레벨 + ATH초과 매도 (실시간가)
  python run.py indicators  # 지정 시각: 보조지표(DMI/거래량) 판정 (일봉 확정)

사용자별 설정을 Supabase에서 읽어 각자 기준으로 판정/발송.
"""
import sys
import re as _re
from datetime import datetime, timezone, timedelta

import db
import notify
from signals import (
    build_ath_from_history, evaluate_buy_levels, evaluate_sell_levels,
    evaluate_indicators, deepest_level,
)
from data_source import (
    get_current_price, get_daily_closes_for_ath, get_daily_history,
)

ET  = timezone(timedelta(hours=-4))   # 간이 ET (서머타임은 워크플로 스케줄에서 관리)
KST = timezone(timedelta(hours=9))

_US_OPEN  = (9, 30)
_US_CLOSE = (16, 0)
_KR_OPEN  = (9, 0)
_KR_CLOSE = (15, 30)

SELL_LEVELS = (0, 10, 20, 30)


def _is_kr(ticker):
    return bool(_re.match(r'^\d{6}', ticker.split('.')[0]))


def should_run_indicator(ticker, alert_times, now_utc, window_min=5):
    """indicator_alert_times 중 하나와 현재 시각이 ±window_min분 이내면 True.
    alert_times 미설정 시 항상 True."""
    if not alert_times:
        return True
    kr = _is_kr(ticker)
    tz = KST if kr else ET
    open_hm  = _KR_OPEN  if kr else _US_OPEN
    close_hm = _KR_CLOSE if kr else _US_CLOSE
    now_local = now_utc.astimezone(tz)
    for at in alert_times:
        anchor = at.get("anchor", "open")
        offset = int(at.get("offset_min", 0))
        h, m = open_hm if anchor == "open" else close_hm
        base = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
        if anchor == "open":
            target = base + timedelta(minutes=offset)
        else:
            target = base - timedelta(minutes=offset)
        if abs((now_utc - target.astimezone(timezone.utc)).total_seconds()) <= window_min * 60:
            return True
    return False


def today_et():
    return datetime.now(ET).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ----- ATH 상태: DB 우선, 없으면 히스토리로 구축 -----
def get_or_build_ath(user_id, ticker, lookback, reset_pct):
    saved = db.get_ath_state(user_id, ticker)
    if saved:
        from indicators import AthRatchet
        obj = AthRatchet(saved["ath"], reset_pct=reset_pct)
        obj.running_high = saved["running_high"]
        obj.exceeded_threshold = saved["exceeded_threshold"]
        return obj, saved
    closes = get_daily_closes_for_ath(ticker, lookback)
    if closes is None:
        return None, None
    obj = build_ath_from_history(closes, reset_pct=reset_pct)
    return obj, None


def save_ath(user_id, ticker, obj, baseline_level, active_levels,
             level_last_alert, last_trade_day):
    db.upsert_ath_state({
        "user_id": user_id, "ticker": ticker,
        "ath": obj.ath, "running_high": obj.running_high,
        "exceeded_threshold": obj.exceeded_threshold,
        "baseline_level": baseline_level,
        "active_levels": active_levels,
        "level_last_alert": level_last_alert,
        "last_trade_day": last_trade_day,
        "updated_at": now_iso(),
    })


# ============================================================
# 모드 1: 장중 하락률 + 매도 (intraday)
# ============================================================
def run_intraday():
    users = db.get_active_users()
    print(f"[intraday] {len(users)} active users")
    day = today_et()

    for u in users:
        uid = u["id"]
        chat = u.get("telegram_chat_id")
        st = db.get_settings(uid)
        if not st:
            continue

        ticker_rows = db.get_index_tickers(uid)
        if not ticker_rows and st.get("index_ticker"):
            ticker_rows = [{"ticker": st["index_ticker"], "name": None}]
        if not ticker_rows:
            continue

        levels = st.get("drawdown_levels", [10, 20, 30, 40])
        reset_pct = float(st.get("ath_reset_pct", 10))
        repeat = int(st.get("redrawdown_repeat_interval", 30))
        buy_enabled = st.get("enable_buy_levels", True)
        sell_enabled = st.get("enable_sell_signals", True)

        tickers_set = {r["ticker"] for r in ticker_rows}

        for row in ticker_rows:
            ticker = row["ticker"]
            name = row.get("name")
            price = get_current_price(ticker)
            if price is None:
                print(f"  {ticker}: no price"); continue

            obj, saved = get_or_build_ath(uid, ticker, st.get("ath_lookback", "5y"), reset_pct)
            if obj is None:
                continue

            is_new_day = not saved or saved.get("last_trade_day") != day
            if is_new_day:
                dd_now = obj.drawdown_pct(price)
                baseline_level = deepest_level(dd_now, levels)
                active_levels = []
                level_last_alert = {}
                # 매도 baseline: 당일 시작 시 이미 활성인 매도 레벨 기록
                gain_now = obj.gain_pct(price)
                sell_baseline = -1
                for L in sorted(SELL_LEVELS):
                    if gain_now >= L:
                        sell_baseline = L
                level_last_alert["sell_baseline"] = sell_baseline
            else:
                baseline_level = saved.get("baseline_level", 0)
                active_levels = list(saved.get("active_levels", []))
                level_last_alert = dict(saved.get("level_last_alert", {}))

            if buy_enabled:
                newly, cur_deep, dd = evaluate_buy_levels(
                    price, obj, levels, baseline_level, active_levels)
                for L in newly:
                    msg = notify.format_buy_level(ticker, L, price, obj.ath, -dd, name=name)
                    if notify.send_message(chat, msg):
                        db.insert_alert({
                            "user_id": uid, "ticker": ticker, "kind": "buy_level",
                            "level": f"-{L}%", "message": msg, "price": price, "ath": obj.ath,
                        })
                    active_levels.append(L)
                    level_last_alert[str(L)] = now_iso()

                # 구간 유지 재알림
                if repeat > 0 and cur_deep > baseline_level and cur_deep in active_levels:
                    last = level_last_alert.get(str(cur_deep))
                    send_repeat = True
                    if last:
                        elapsed = (datetime.now(timezone.utc) -
                                   datetime.fromisoformat(last)).total_seconds() / 60
                        send_repeat = elapsed >= repeat
                    if send_repeat and cur_deep not in newly:
                        msg = notify.format_buy_level(
                            ticker, cur_deep, price, obj.ath, -dd, name=name
                        ) + f"\n(구간 유지 · {repeat}분 재알림)"
                        if notify.send_message(chat, msg):
                            db.insert_alert({
                                "user_id": uid, "ticker": ticker, "kind": "buy_level",
                                "level": f"-{cur_deep}%(유지)", "message": msg,
                                "price": price, "ath": obj.ath,
                            })
                        level_last_alert[str(cur_deep)] = now_iso()
            else:
                newly, cur_deep, dd = evaluate_buy_levels(
                    price, obj, levels, baseline_level, active_levels)

            if sell_enabled:
                hit, gain = evaluate_sell_levels(price, obj, SELL_LEVELS)
                if hit is not None:
                    try:
                        sell_baseline = int(level_last_alert.get("sell_baseline", -1))
                    except (TypeError, ValueError):
                        sell_baseline = -1

                    if hit > sell_baseline:
                        sell_key = f"sell_{hit}"
                        last_sell = level_last_alert.get(sell_key)
                        should_alert = last_sell is None
                        is_repeat_sell = False

                        if last_sell and repeat > 0:
                            elapsed = (datetime.now(timezone.utc) -
                                       datetime.fromisoformat(last_sell)).total_seconds() / 60
                            if elapsed >= repeat:
                                should_alert = True
                                is_repeat_sell = True

                        if should_alert:
                            msg = notify.format_sell(ticker, hit, price, obj.ath, gain, name=name)
                            if is_repeat_sell:
                                msg += f"\n(구간 유지 · {repeat}분 재알림)"
                            if notify.send_message(chat, msg):
                                db.insert_alert({
                                    "user_id": uid, "ticker": ticker, "kind": "sell",
                                    "level": f"+{hit}%" if hit > 0 else "ATH도달",
                                    "message": msg, "price": price, "ath": obj.ath,
                                })
                            level_last_alert[sell_key] = now_iso()

            save_ath(uid, ticker, obj, baseline_level, active_levels, level_last_alert, day)
            print(f"  {ticker}: px={price:.2f} dd={dd:+.1f}% newly={newly}")

        # 나머지 티커(indicator/watchlist) ATH 상태 갱신 (알림 없음)
        ind_rows = db.get_indicator_tickers(uid)
        wl_rows = db.get_watchlist(uid)
        extra = {r["ticker"] for r in ind_rows + wl_rows} - tickers_set
        for ticker in extra:
            price = get_current_price(ticker)
            if price is None:
                continue
            obj, saved = get_or_build_ath(uid, ticker, st.get("ath_lookback", "5y"), reset_pct)
            if obj is None:
                continue
            bl  = saved.get("baseline_level", 0)  if saved else 0
            al  = list(saved.get("active_levels", []))   if saved else []
            lla = dict(saved.get("level_last_alert", {})) if saved else {}
            ltd = saved.get("last_trade_day", day)        if saved else day
            save_ath(uid, ticker, obj, bl, al, lla, ltd)


# ============================================================
# 모드 2: 보조지표 (indicators) — 일봉 확정 기준
# ============================================================
def run_indicators():
    users = db.get_active_users()
    print(f"[indicators] {len(users)} active users")

    hist_cache = {}

    def hist(ticker):
        if ticker not in hist_cache:
            hist_cache[ticker] = get_daily_history(ticker, period="2y")
        return hist_cache[ticker]

    for u in users:
        uid = u["id"]
        chat = u.get("telegram_chat_id")
        st = db.get_settings(uid)
        if not st:
            continue

        alert_times = st.get("indicator_alert_times") or []
        now_utc = datetime.now(timezone.utc)

        if st.get("enable_buy_indicators", True):
            ind_rows = db.get_indicator_tickers(uid)
            if not ind_rows and st.get("indicator_ticker"):
                ind_rows = [{"ticker": st["indicator_ticker"], "name": None}]
            for row in ind_rows:
                tkr = row["ticker"]
                tname = row.get("name")
                if not should_run_indicator(tkr, alert_times, now_utc):
                    print(f"  [indicators] {tkr}: skip (시각 불일치)")
                    continue
                df = hist(tkr)
                if df is not None and len(df) > 30:
                    sig = evaluate_indicators(df, st)
                    if sig["dmi_buy"] or sig["volume_spike"]:
                        msg = notify.format_indicator(tkr, sig, name=tname)
                        if notify.send_message(chat, msg):
                            db.insert_alert({
                                "user_id": uid, "ticker": tkr, "kind": "buy_indicator",
                                "level": "DMI/Vol", "message": msg,
                                "price": float(df["Close"].iloc[-1]), "ath": None,
                            })

        if st.get("enable_watchlist", True):
            for row in db.get_watchlist(uid):
                wt = row["ticker"]
                wname = row.get("name")
                if not should_run_indicator(wt, alert_times, now_utc):
                    continue
                df = hist(wt)
                if df is None or len(df) < 30:
                    continue
                sig = evaluate_indicators(df, st)
                if sig["dmi_buy"]:
                    msg = notify.format_watchlist(wt, sig, name=wname)
                    if notify.send_message(chat, msg):
                        db.insert_alert({
                            "user_id": uid, "ticker": wt, "kind": "watchlist",
                            "level": "DMI", "message": msg,
                            "price": float(df["Close"].iloc[-1]), "ath": None,
                        })


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "intraday"
    if mode == "intraday":
        run_intraday()
    elif mode == "indicators":
        run_indicators()
    else:
        print(f"unknown mode: {mode}")
