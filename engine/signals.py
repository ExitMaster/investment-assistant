"""
ATH ratchet 상태를 과거 종가 시리즈로부터 구축/갱신하는 헬퍼,
그리고 매수/매도 신호 판정 로직.
"""
from indicators import (
    AthRatchet, compute_ath_state, wilder_dmi, stochastics_slow, volume_spike,
    dmi_buy_signal, dmi_imminent, bullish_divergence, bearish_divergence,
    volume_breakout,
)


def build_ath_from_history(closes, reset_pct=10.0):
    """
    과거 종가 시리즈로부터 '현재 시점의 ATH 기준선'을 구축한다.

    확정 고점(confirmed peak) 방식: 어떤 고점에서 reset_pct% 눌림이 나오면
    그 고점을 ATH로 확정하고 위로만 갱신한다. 상승장에서 reset_pct% 미만의
    눌림·재상승이 반복되면 직전 확정 고점이 ATH로 유지된다(매도 신호 구간 유지).
    (자세한 규칙은 indicators.compute_ath_state 참고)
    """
    state = compute_ath_state(closes, reset_pct=reset_pct)
    if state is None:
        return None
    obj = AthRatchet(state["ath"], reset_pct=reset_pct)
    obj.running_high = state["running_high"]
    obj.exceeded_threshold = state["exceeded_threshold"]
    return obj


def deepest_level(drawdown_pct, levels):
    """현재 하락률에서 도달한 가장 깊은 매수 레벨 (없으면 0)"""
    d = 0
    for L in sorted(levels):
        if drawdown_pct >= L:
            d = L
    return d


def evaluate_buy_levels(price, ath_obj, levels, baseline_level, active_levels):
    """
    장중 하락률 기반 매수 레벨 신규진입 판정.
    반환: (newly_entered_levels, current_deepest, drawdown_pct)
    baseline_level 이하(전일부터 활성)는 신규진입에서 제외.
    """
    dd = ath_obj.drawdown_pct(price)
    cur = deepest_level(dd, levels)
    newly = []
    for L in sorted(levels):
        if L > baseline_level and dd >= L and L not in active_levels:
            newly.append(L)
    return newly, cur, dd


def evaluate_sell_levels(price, ath_obj, sell_pcts=(0, 10, 20, 30)):
    """
    ATH 도달/초과 매도 신호.
    - level 0: ATH 도달 (gain >= 0)
    - level 10, 20, 30: ATH+10%/+20%/+30% 초과
    반환: (hit_level, gain_pct) 여기서 hit_level은 None(신호없음) 또는 int
    """
    gain = ath_obj.gain_pct(price)
    hit = None
    for L in sorted(sell_pcts):
        if gain >= L:
            hit = L
    return hit, gain


def evaluate_indicators(df, settings):
    """
    보조지표 신호 판정 (일봉 확정 기준).
    df: OHLCV DataFrame
    반환: dict of triggered signals
    """
    out = {}
    high, low, close, vol = df["High"], df["Low"], df["Close"], df["Volume"]

    thr = settings.get("dmi_threshold", 30)
    pdi, mdi, adx = wilder_dmi(high, low, close)
    buy = dmi_buy_signal(mdi, adx, threshold=thr)
    out["dmi_buy"] = bool(buy.iloc[-1]) if len(buy) else False
    out["dmi_imminent"] = dmi_imminent(mdi, adx, threshold=thr)
    out["dmi_values"] = {
        "plus_di": round(float(pdi.iloc[-1]), 1),
        "minus_di": round(float(mdi.iloc[-1]), 1),
        "adx": round(float(adx.iloc[-1]), 1),
    }

    sp = settings.get("stoch_params", [5, 3, 3])
    k, d = stochastics_slow(high, low, close, k=sp[0], d=sp[1], smooth=sp[2])
    out["stoch"] = {"k": round(float(k.iloc[-1]), 1), "d": round(float(d.iloc[-1]), 1)}

    lookback = settings.get("volume_lookback_days", 126)
    vspike = volume_spike(vol, lookback=lookback)
    out["volume_spike"] = bool(vspike.iloc[-1]) if len(vspike) else False

    # 다이버전스 (Stochastics Slow %K 기준)
    bull, bull_v = bullish_divergence(low, k)
    bear, bear_v = bearish_divergence(high, k)
    out["bull_div"] = bull
    out["bull_div_values"] = bull_v
    out["bear_div"] = bear
    out["bear_div_values"] = bear_v

    # 저점/고점 대량거래 돌파 (3영업일 확정)
    vb = volume_breakout(df, lookback=lookback)
    out["low_vol_breakout"] = vb["low_vol"]
    out["high_vol_breakout"] = vb["high_vol"]
    out["vol_ratio"] = vb["vol_ratio"]

    return out
