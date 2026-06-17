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
from indicators import final_regime_extremes
from data_source import (
    get_current_price, get_current_quote, get_daily_closes_for_ath, get_daily_history,
)

ET  = timezone(timedelta(hours=-4))   # 간이 ET (서머타임은 워크플로 스케줄에서 관리)
KST = timezone(timedelta(hours=9))

_US_OPEN  = (9, 30)
_US_CLOSE = (16, 0)
_KR_OPEN  = (9, 0)
_KR_CLOSE = (15, 30)

SELL_LEVELS = (0, 10, 20, 30)

DEFAULT_BUY_ACTIONS = {
    10: {"product": "IVV", "cash": 20},
    20: {"product": "QLD", "cash": 40},
    30: {"product": "TQQQ", "cash": 70},
    40: {"product": "TQQQ", "cash": 100},
}


def resolve_action(level, st, ticker_actions):
    """레벨별 매매 행동 조회. 우선순위: 지표별 모드의 티커 설정 → 공통 설정 → PDF 기본값.
    include_action_guide 가 False면 행동 가이드를 표시하지 않음(None)."""
    if st.get("include_action_guide") is False:
        return None
    src = None
    if st.get("action_mode") == "per_ticker" and ticker_actions:
        src = ticker_actions
    elif st.get("buy_actions"):
        src = st.get("buy_actions")
    if src:
        a = src.get(str(level)) or src.get(level)
        if a:
            return a
    return DEFAULT_BUY_ACTIONS.get(level)


def _is_kr(ticker):
    return bool(_re.match(r'^\d{6}', ticker.split('.')[0]))


def is_muted(st):
    """알림 차단 상태 판정: 마스터 차단(alerts_master_off) 또는 일시중지(muted_until)."""
    if st.get("alerts_master_off"):
        return True
    mu = st.get("muted_until")
    if not mu:
        return False
    try:
        until = datetime.fromisoformat(mu.replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < until
    except (TypeError, ValueError):
        return False


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
        send_tg = not is_muted(st)
        if not send_tg:
            print(f"  {uid}: muted — 이력 기록, 텔레그램 생략")

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
        sell_cash_target = None if st.get("include_action_guide") is False else st.get("sell_cash_target", 30)
        prealert_enabled = bool(st.get("prealert_enabled", False))
        prealert_pp = float(st.get("prealert_pp", 2.0) or 2.0)

        tickers_set = {r["ticker"] for r in ticker_rows}

        for row in ticker_rows:
            ticker = row["ticker"]
            name = row.get("name")
            ticker_actions = row.get("buy_actions")
            price, tick_ts = get_current_quote(ticker)
            if price is None:
                print(f"  {ticker}: no price"); continue

            # 휴장/장외 신선도 가드: 최신 틱이 '오늘(해당 시장)'이 아니면 판정 건너뜀
            if tick_ts is not None:
                mtz = KST if _is_kr(ticker) else ET
                if tick_ts.astimezone(mtz).date() != datetime.now(mtz).date():
                    print(f"  {ticker}: stale tick {tick_ts.astimezone(mtz)} — 휴장/장외 skip")
                    continue

            obj, saved = get_or_build_ath(uid, ticker, st.get("ath_lookback", "5y"), reset_pct)
            if obj is None:
                continue

            is_new_day = not saved or saved.get("last_trade_day") != day
            if is_new_day and saved:
                # 새 거래일 첫 실행: 확정 종가 히스토리로 ATH 재계산(확정 고점 갱신)
                closes = get_daily_closes_for_ath(ticker, st.get("ath_lookback", "5y"))
                rebuilt = build_ath_from_history(closes, reset_pct=reset_pct) if closes else None
                if rebuilt is not None:
                    obj = rebuilt
            # 한 레벨은 같은 ATH 구간에서 1회만 발화. ATH가 위로 갱신되면 전 레벨 재무장.
            # (매 거래일이 아니라 ATH 갱신을 기준으로 상태를 리셋한다 — 회복 후 재돌파 중복 알림 방지)
            prev_ath = saved.get("ath") if saved else None
            ath_advanced = (prev_ath is None) or (obj.ath > prev_ath + 1e-9)
            # 엔진이 이 티커를 처음 평가하는가. init-ath가 ath_state 행을 미리 만들어
            # saved가 존재할 수 있으므로, last_trade_day 미설정(None)으로 '최초 평가'를 판별한다.
            never_evaluated = (saved is None) or (saved.get("last_trade_day") is None)

            if never_evaluated:
                # 최초 평가(티커 추가 직후 포함): 이미 '지나간' 레벨을 baseline으로 억제.
                # 현재가 한 점이 아니라 현재 ATH 구간의 과거 이력 전체에서 가장 깊은 하락·
                # 가장 높은 초과상승을 기준으로 삼아야, 회복 후 등록해도 중복 알림이 안 간다.
                hist = get_daily_closes_for_ath(ticker, st.get("ath_lookback", "5y"))
                if hist:
                    regime_dd, regime_gain = final_regime_extremes(hist, reset_pct)
                else:
                    regime_dd, regime_gain = obj.drawdown_pct(price), obj.gain_pct(price)
                baseline_level = deepest_level(regime_dd, levels)
                active_levels = []
                level_last_alert = {}
                sell_baseline = -1
                for L in sorted(SELL_LEVELS):
                    if regime_gain >= L:
                        sell_baseline = L
                level_last_alert["sell_baseline"] = sell_baseline
            elif ath_advanced:
                # 전고점(ATH)이 새로 확정되어 위로 갱신됨 → 모든 매수/매도 레벨 재발화 허용
                baseline_level = 0
                active_levels = []
                level_last_alert = {"sell_baseline": -1}
            else:
                # 같은 ATH 구간: 직전 상태 유지 (이미 알린 레벨은 재발화 안 함)
                baseline_level = saved.get("baseline_level", 0)
                active_levels = list(saved.get("active_levels", []))
                level_last_alert = dict(saved.get("level_last_alert", {}))

            if buy_enabled:
                newly, cur_deep, dd = evaluate_buy_levels(
                    price, obj, levels, baseline_level, active_levels)
                for L in newly:
                    action = resolve_action(L, st, ticker_actions)
                    msg = notify.format_buy_level(ticker, L, price, obj.ath, -dd, name=name, action=action)
                    db.insert_alert({
                        "user_id": uid, "ticker": ticker, "kind": "buy_level",
                        "level": f"-{L}%", "message": msg, "price": price, "ath": obj.ath,
                    })
                    if send_tg:
                        notify.send_message(chat, msg)
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
                        action = resolve_action(cur_deep, st, ticker_actions)
                        msg = notify.format_buy_level(
                            ticker, cur_deep, price, obj.ath, -dd, name=name, action=action
                        ) + f"\n(구간 유지 · {repeat}분 재알림)"
                        db.insert_alert({
                            "user_id": uid, "ticker": ticker, "kind": "buy_level",
                            "level": f"-{cur_deep}%(유지)", "message": msg,
                            "price": price, "ath": obj.ath,
                        })
                        if send_tg:
                            notify.send_message(chat, msg)
                        level_last_alert[str(cur_deep)] = now_iso()
            else:
                newly, cur_deep, dd = evaluate_buy_levels(
                    price, obj, levels, baseline_level, active_levels)

            # 임박(선행) 알림: ATH 신호가 다음 매수/매도 레벨에 prealert_pp 이내로 근접 시 1회
            if prealert_enabled and buy_enabled:
                dd_abs = dd  # 양수 하락 깊이
                for L in sorted(levels):
                    if L in active_levels:
                        continue
                    gap = L - dd_abs
                    if 0 < gap <= prealert_pp:
                        key = f"near_{L}"
                        if key not in level_last_alert:
                            action = resolve_action(L, st, ticker_actions)
                            msg = notify.format_prealert(
                                ticker, L, price, obj.ath, -dd_abs, gap, name=name, action=action)
                            db.insert_alert({
                                "user_id": uid, "ticker": ticker, "kind": "prealert",
                                "level": f"-{L}%임박", "message": msg, "price": price, "ath": obj.ath,
                            })
                            if send_tg:
                                notify.send_message(chat, msg)
                            level_last_alert[key] = now_iso()
                        break

            if prealert_enabled and sell_enabled:
                gain_now = obj.gain_pct(price)
                for L in sorted(SELL_LEVELS):
                    if f"sell_{L}" in level_last_alert:   # 이미 도달·알림된 매도 레벨 제외
                        continue
                    gap = L - gain_now
                    if 0 < gap <= prealert_pp:
                        key = f"near_sell_{L}"
                        if key not in level_last_alert:
                            msg = notify.format_prealert_sell(
                                ticker, L, price, obj.ath, gain_now, gap, name=name)
                            db.insert_alert({
                                "user_id": uid, "ticker": ticker, "kind": "prealert",
                                "level": (f"+{L}%임박" if L > 0 else "ATH도달임박"),
                                "message": msg, "price": price, "ath": obj.ath,
                            })
                            if send_tg:
                                notify.send_message(chat, msg)
                            level_last_alert[key] = now_iso()
                        break

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
                            msg = notify.format_sell(ticker, hit, price, obj.ath, gain, name=name,
                                                     cash_target=sell_cash_target)
                            if is_repeat_sell:
                                msg += f"\n(구간 유지 · {repeat}분 재알림)"
                            db.insert_alert({
                                "user_id": uid, "ticker": ticker, "kind": "sell",
                                "level": f"+{hit}%" if hit > 0 else "ATH도달",
                                "message": msg, "price": price, "ath": obj.ath,
                            })
                            if send_tg:
                                notify.send_message(chat, msg)
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
        send_tg = not is_muted(st)
        if not send_tg:
            print(f"  {uid}: muted — 이력 기록, 텔레그램 생략")

        alert_times = st.get("indicator_alert_times") or []
        now_utc = datetime.now(timezone.utc)

        div_on = bool(st.get("enable_divergence", True))
        vol_on = bool(st.get("enable_volume_signal", True))
        sell_on = bool(st.get("enable_sell_signals", True))

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
                if df is None or len(df) <= 30:
                    continue
                sig = evaluate_indicators(df, st)
                px = float(df["Close"].iloc[-1])

                # 토글로 끈 신호는 제외
                if not div_on:
                    sig["bull_div"] = sig["bear_div"] = False
                if not vol_on:
                    sig["low_vol_breakout"] = sig["high_vol_breakout"] = False

                # 매수 계열
                msg = notify.format_indicator(tkr, sig, name=tname)
                if msg:
                    db.insert_alert({
                        "user_id": uid, "ticker": tkr, "kind": "buy_indicator",
                        "level": "보조지표", "message": msg, "price": px, "ath": None,
                    })
                    if send_tg:
                        notify.send_message(chat, msg)

                # 매도 계열 예외 (하락 다이버전스 / 고점 대량거래)
                if sell_on:
                    smsg = notify.format_sell_indicator(tkr, sig, name=tname)
                    if smsg:
                        db.insert_alert({
                            "user_id": uid, "ticker": tkr, "kind": "sell_indicator",
                            "level": "보조지표", "message": smsg, "price": px, "ath": None,
                        })
                        if send_tg:
                            notify.send_message(chat, smsg)

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
                    db.insert_alert({
                        "user_id": uid, "ticker": wt, "kind": "watchlist",
                        "level": "DMI", "message": msg,
                        "price": float(df["Close"].iloc[-1]), "ath": None,
                    })
                    if send_tg:
                        notify.send_message(chat, msg)


# ============================================================
# 간이 백테스트: 보조지표 신호가 과거에 언제 떴는지 출력
# ============================================================
def run_backtest(ticker, period="2y"):
    df = get_daily_history(ticker, period=period)
    if df is None or len(df) < 80:
        print(f"[backtest] {ticker}: 데이터 부족")
        return
    df = df.reset_index(drop=False)
    dates = df.iloc[:, 0]
    st = {}  # 기본 설정
    print(f"[backtest] {ticker} · {len(df)}봉 · 보조지표 신호 발생일")
    hits = 0
    for i in range(70, len(df)):
        sub = df.iloc[:i + 1]
        sig = evaluate_indicators(sub, st)
        tags = []
        if sig["dmi_buy"]: tags.append("DMI매수")
        if sig["dmi_imminent"]: tags.append("DMI임박")
        if sig["bull_div"]: tags.append("상승다이버전스")
        if sig["low_vol_breakout"]: tags.append("저점대량거래")
        if sig["bear_div"]: tags.append("하락다이버전스")
        if sig["high_vol_breakout"]: tags.append("고점대량거래")
        if tags:
            hits += 1
            d = dates.iloc[i]
            ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            print(f"  {ds}  px={float(sub['Close'].iloc[-1]):.2f}  {', '.join(tags)}")
    print(f"[backtest] 총 {hits}건")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "intraday"
    if mode == "intraday":
        run_intraday()
    elif mode == "indicators":
        run_indicators()
    elif mode == "backtest":
        if len(sys.argv) < 3:
            print("usage: python run.py backtest <TICKER> [period]")
        else:
            run_backtest(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "2y")
    else:
        print(f"unknown mode: {mode}")
