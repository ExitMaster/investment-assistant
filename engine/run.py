"""
Investment Assistant — 엔진 메인 러너
GitHub Actions에서 주기 실행.

모드:
  python run.py intraday    # 5분마다: 하락률 매수레벨 + ATH초과 매도 (실시간가)
  python run.py indicators  # 지정 시각: 보조지표(DMI/거래량) 판정 (일봉 확정)

사용자별 설정을 Supabase에서 읽어 각자 기준으로 판정/발송.
"""
import sys
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

ET = timezone(timedelta(hours=-4))  # 간이 ET (서머타임은 워크플로 스케줄에서 관리)


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
# 모드 1: 장중 하락률 (intraday)
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

        # index_tickers 테이블 우선, 없으면 settings.index_ticker로 fallback
        tickers = db.get_index_tickers(uid)
        if not tickers and st.get("index_ticker"):
            tickers = [st["index_ticker"]]
        if not tickers:
            continue

        levels = st.get("drawdown_levels", [10, 20, 30])
        reset_pct = float(st.get("ath_reset_pct", 10))
        repeat = int(st.get("redrawdown_repeat_interval", 30))
        buy_enabled = st.get("enable_buy_levels", True)
        sell_enabled = st.get("enable_sell_signals", True)

        for ticker in tickers:
            price = get_current_price(ticker)
            if price is None:
                print(f"  {ticker}: no price"); continue

            obj, saved = get_or_build_ath(uid, ticker, st.get("ath_lookback", "5y"), reset_pct)
            if obj is None:
                continue

            # 새 거래일이면 baseline 재설정
            if not saved or saved.get("last_trade_day") != day:
                dd_now = obj.drawdown_pct(price)
                baseline_level = deepest_level(dd_now, levels)
                active_levels = []
                level_last_alert = {}
            else:
                baseline_level = saved.get("baseline_level", 0)
                active_levels = list(saved.get("active_levels", []))
                level_last_alert = dict(saved.get("level_last_alert", {}))

            if buy_enabled:
                # --- 매수 레벨 신규진입 ---
                newly, cur_deep, dd = evaluate_buy_levels(
                    price, obj, levels, baseline_level, active_levels)
                for L in newly:
                    msg = notify.format_buy_level(ticker, ticker, L, price, obj.ath, -dd)
                    if notify.send_message(chat, msg):
                        db.insert_alert({
                            "user_id": uid, "ticker": ticker, "kind": "buy_level",
                            "level": f"-{L}%", "message": msg, "price": price, "ath": obj.ath,
                        })
                    active_levels.append(L)
                    level_last_alert[str(L)] = now_iso()

                # --- 구간 유지 재알림 ---
                if repeat > 0 and cur_deep > baseline_level and cur_deep in active_levels:
                    last = level_last_alert.get(str(cur_deep))
                    send_repeat = True
                    if last:
                        elapsed = (datetime.now(timezone.utc) -
                                   datetime.fromisoformat(last)).total_seconds() / 60
                        send_repeat = elapsed >= repeat
                    if send_repeat and cur_deep not in newly:
                        msg = notify.format_buy_level(ticker, ticker, cur_deep, price, obj.ath, -dd) \
                              + f"\n(구간 유지 · {repeat}분 재알림)"
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
                # --- ATH 초과 매도 ---
                hit, gain = evaluate_sell_levels(price, obj)
                if hit:
                    sell_key = f"sell_{hit}"
                    if sell_key not in level_last_alert:
                        msg = notify.format_sell(ticker, hit, price, obj.ath, gain)
                        if notify.send_message(chat, msg):
                            db.insert_alert({
                                "user_id": uid, "ticker": ticker, "kind": "sell",
                                "level": f"+{hit}%", "message": msg,
                                "price": price, "ath": obj.ath,
                            })
                        level_last_alert[sell_key] = now_iso()

            save_ath(uid, ticker, obj, baseline_level, active_levels, level_last_alert, day)
            print(f"  {ticker}: px={price:.2f} dd={dd:+.1f}% newly={newly}")


# ============================================================
# 모드 2: 보조지표 (indicators) — 일봉 확정 기준
# ============================================================
def run_indicators():
    users = db.get_active_users()
    print(f"[indicators] {len(users)} active users")

    # 티커별 히스토리 캐시 (사용자 간 중복 다운로드 방지)
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

        # 지수 보조지표
        if st.get("enable_buy_indicators", True):
            tkr = st.get("indicator_ticker", st["index_ticker"])
            df = hist(tkr)
            if df is not None and len(df) > 30:
                sig = evaluate_indicators(df, st)
                if sig["dmi_buy"] or sig["volume_spike"]:
                    msg = notify.format_indicator(tkr, sig)
                    if notify.send_message(chat, msg):
                        db.insert_alert({
                            "user_id": uid, "ticker": tkr, "kind": "buy_indicator",
                            "level": "DMI/Vol", "message": msg,
                            "price": float(df["Close"].iloc[-1]), "ath": None,
                        })

        # 개별주식 watchlist
        if st.get("enable_watchlist", True):
            for wt in db.get_watchlist(uid):
                df = hist(wt)
                if df is None or len(df) < 30:
                    continue
                sig = evaluate_indicators(df, st)
                if sig["dmi_buy"]:
                    msg = notify.format_watchlist(wt, sig)
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
