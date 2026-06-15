"""
ATH ratchet 상태를 과거 종가 시리즈로부터 구축/갱신하는 헬퍼,
그리고 매수/매도 신호 판정 로직.
"""
from indicators import AthRatchet, wilder_dmi, stochastics_slow, volume_spike, dmi_buy_signal


def build_ath_from_history(closes, reset_pct=10.0):
    """
    과거 종가 시리즈로부터 '현재 시점의 ATH 기준선'을 구축한다.

    ratchet의 본래 규칙(ATH 아래로 내려갈 때만 갱신)을 히스토리 전체에
    그대로 적용하면, 상승만 한 구간에서 ATH가 첫 종가에 고정되는 문제가 있다.
    초기화의 올바른 정의는 "현재까지의 종가 최고점"을 기준선으로 삼는 것이다.
    이후 실시간 운영에서 ratchet(쌍봉 방지, +reset% 후 하향 시 갱신)이 동작한다.

    따라서:
      - 기준선 ATH = 시리즈의 종가 최고값
      - running_high = 마지막 종가 (이후 신고가 추적 시작점)
      - exceeded_threshold = 마지막 종가가 이미 ATH+reset% 위인지
    반환: AthRatchet 인스턴스
    """
    closes = [float(c) for c in closes if c is not None]
    if not closes:
        return None

    peak = max(closes)            # 현재까지의 최고 종가 = 초기 ATH 기준선
    last = closes[-1]             # 현재가(마지막 종가)

    obj = AthRatchet(peak, reset_pct=reset_pct)
    # 마지막 종가가 최고점보다 높을 일은 없지만(peak가 max), 안전하게 running 설정
    obj.running_high = last
    obj.exceeded_threshold = last >= peak * (1 + reset_pct / 100.0)
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
    반환: (newly_entered_levels, current_deepest)
      - newly_entered_levels: 이번에 새로 진입한 레벨 리스트 (즉시 알림 대상)
      - current_deepest: 현재 가장 깊은 레벨 (재알림 간격 판정용)
    baseline_level 이하(전일부터 활성)는 신규진입에서 제외.
    """
    dd = ath_obj.drawdown_pct(price)
    cur = deepest_level(dd, levels)
    newly = []
    for L in sorted(levels):
        if L > baseline_level and dd >= L and L not in active_levels:
            newly.append(L)
    return newly, cur, dd


def evaluate_sell_levels(price, ath_obj, sell_pcts=(10, 20, 30)):
    """
    ATH 초과 상승 매도 신호 (+10%/+20%/...).
    반환: 도달한 가장 높은 +구간 (없으면 0)
    """
    gain = ath_obj.gain_pct(price)
    hit = 0
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

    # DMI 매수신호
    pdi, mdi, adx = wilder_dmi(high, low, close)
    buy = dmi_buy_signal(mdi, adx, threshold=settings.get("dmi_threshold", 30))
    out["dmi_buy"] = bool(buy.iloc[-1]) if len(buy) else False
    out["dmi_values"] = {
        "plus_di": round(float(pdi.iloc[-1]), 1),
        "minus_di": round(float(mdi.iloc[-1]), 1),
        "adx": round(float(adx.iloc[-1]), 1),
    }

    # Stochastics Slow
    sp = settings.get("stoch_params", [5, 3, 3])
    k, d = stochastics_slow(high, low, close, k=sp[0], d=sp[1], smooth=sp[2])
    out["stoch"] = {"k": round(float(k.iloc[-1]), 1), "d": round(float(d.iloc[-1]), 1)}

    # 저점 대량거래
    lookback = settings.get("volume_lookback_days", 126)
    vspike = volume_spike(vol, lookback=lookback)
    out["volume_spike"] = bool(vspike.iloc[-1]) if len(vspike) else False

    return out
