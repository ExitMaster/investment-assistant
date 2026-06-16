"""
무한투자 알림 - 핵심 신호 엔진 (검증용 프로토타입)
데이터 소스와 무관하게 로직 정확성을 검증하는 것이 목적.
실제 배포 시에는 yfinance가 OHLCV DataFrame을 공급한다.
"""
import numpy as np
import pandas as pd


# ============================================================
# 1. ATH RATCHET 로직 (우리가 합의한 핵심 규칙)
# ============================================================
def compute_ath_state(closes, reset_pct=10.0):
    """확정 고점(confirmed peak) 방식으로 ATH 상태를 계산한다.

    규칙:
    - 한 구간의 고점(peak)을 추적하다가, 종가가 peak 대비 reset_pct% 이상
      눌리면 그 peak를 '확정'하고 ATH = max(기존 ATH, peak) 로 갱신(위로만).
    - 확정 후엔 그 눌림 지점부터 새 구간의 고점 추적을 다시 시작.
    - 상승만 하고 reset_pct% 눌림이 없으면 직전 확정 고점이 ATH로 유지된다
      (→ ATH 대비 +10/20/30%에서 매도 신호가 계속 발생).
    - 구간 내 reset_pct% 조정이 한 번도 없으면 종가 최고값으로 폴백.

    반환: {"ath", "running_high", "exceeded_threshold"} 또는 None.
    """
    vals = [float(c) for c in closes if c is not None and float(c) > 0]
    if not vals:
        return None
    r = reset_pct / 100.0

    ath = None
    peak = vals[0]            # 현재 구간(미확정)의 고점
    for c in vals:
        if c > peak:
            peak = c
        if c <= peak * (1 - r):           # peak 대비 reset_pct% 눌림 → 확정
            ath = peak if ath is None else max(ath, peak)
            peak = c                       # 눌림 지점부터 새 구간 시작

    if ath is None:                        # 조정이 한 번도 없던 예외 → 폴백
        ath = max(vals)

    running_high = peak                    # 현재 미확정 구간의 고점
    return {
        "ath": ath,
        "running_high": running_high,
        # 다음 눌림 발생 시 ATH를 끌어올릴 후보가 있는지 (정보용)
        "exceeded_threshold": running_high > ath,
    }


def final_regime_extremes(closes, reset_pct=10.0):
    """현재(마지막) 확정 ATH가 활성화된 이후 겪은 (최대 하락률%, 최대 초과상승률%).

    티커를 뒤늦게 등록할 때 '이미 지나간' 매수/매도 레벨을 baseline으로 억제하기 위해,
    현재가 한 점이 아니라 이 ATH 구간의 과거 이력 전체에서 가장 깊은 하락·가장 높은
    초과상승을 본다. 예: -12%→-15%→-9%→[등록]→-11% 라면 이미 -15%까지 갔으므로
    최대 하락률 15%가 반환되어 -10% 매수 레벨이 억제된다.
    반환: (max_drawdown_pct, max_gain_pct) — 둘 다 0 이상.
    """
    vals = [float(c) for c in closes if c is not None and float(c) > 0]
    if not vals:
        return 0.0, 0.0
    r = reset_pct / 100.0

    ath = None
    peak = vals[0]
    series = []                            # 각 봉 시점의 확정 ATH(미확정 구간은 None)
    for c in vals:
        if c > peak:
            peak = c
        if c <= peak * (1 - r):
            ath = peak if ath is None else max(ath, peak)
            peak = c
        series.append(ath)

    final_ath = series[-1]
    if final_ath is None:                  # 확정 조정이 없던 예외 → 전체 구간 기준
        final_ath = max(vals)
        start = 0
    else:                                  # 마지막 ATH가 처음 확정된 지점부터가 현재 구간
        start = next(i for i, a in enumerate(series) if a == final_ath)

    window = vals[start:]
    max_dd = max(0.0, (final_ath - min(window)) / final_ath * 100.0)
    max_gain = max(0.0, (max(window) - final_ath) / final_ath * 100.0)
    return max_dd, max_gain


class AthRatchet:
    """
    종가 기준 ATH 기준선 관리 (확정 고점 방식).
    - 구간 고점이 reset_pct% 눌림으로 확정될 때만 ATH 갱신, 위로만 상향.
    - 상승장에서 reset_pct% 미만 눌림·재상승 반복 시 직전 확정 고점 유지.

    운영에서는 매 거래일 일봉 히스토리로 compute_ath_state를 호출해
    상태를 재계산하므로, 아래 update()는 단건 증분 갱신용 보조 메서드다.
    """
    def __init__(self, initial_ath, reset_pct=10.0):
        self.ath = float(initial_ath)
        self.reset_pct = reset_pct / 100.0
        self.running_high = float(initial_ath)
        self.exceeded_threshold = False  # running_high > ath (상향 후보)

    def update(self, close):
        """하루 종가를 받아 상태 증분 갱신. 갱신 이벤트가 있으면 반환."""
        event = None
        close = float(close)

        if close > self.running_high:
            self.running_high = close

        # 현재 구간 고점(running_high) 대비 reset_pct% 눌림 → 확정
        if close <= self.running_high * (1 - self.reset_pct):
            if self.running_high > self.ath:     # 위로만 갱신
                old = self.ath
                self.ath = self.running_high
                event = ('ATH_UPDATED', old, self.ath)
            self.running_high = close             # 새 구간 시작
        self.exceeded_threshold = self.running_high > self.ath
        return event

    def drawdown_pct(self, price):
        """현재가의 ATH 대비 하락률 (양수=하락)"""
        return (self.ath - price) / self.ath * 100.0

    def gain_pct(self, price):
        """ATH 대비 상승률 (양수=ATH 초과 상승)"""
        return (price - self.ath) / self.ath * 100.0


# ============================================================
# 2. 보조지표 계산
# ============================================================
def wilder_dmi(high, low, close, period=14):
    """DMI: +DI, -DI, ADX (Wilder smoothing)"""
    high, low, close = map(lambda s: pd.Series(s).astype(float), (high, low, close))
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return plus_di, minus_di, adx


def stochastics_slow(high, low, close, k=5, d=3, smooth=3):
    """Stochastics Slow (5,3,3)"""
    high, low, close = map(lambda s: pd.Series(s).astype(float), (high, low, close))
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    fast_k = 100 * (close - ll) / (hh - ll)
    slow_k = fast_k.rolling(smooth).mean()
    slow_d = slow_k.rolling(d).mean()
    return slow_k, slow_d


def volume_spike(volume, lookback=126):
    """최근 lookback(약6개월) 중 최대 거래량인지"""
    volume = pd.Series(volume).astype(float)
    is_max = volume == volume.rolling(lookback, min_periods=1).max()
    return is_max


# ============================================================
# 3. DMI 매수신호 판정 (PDF 정의)
#   기준선 30 이상에서 DI- 라인이 ADX 라인을 하향 돌파
# ============================================================
def dmi_buy_signal(minus_di, adx, threshold=30):
    """오늘 DI-가 ADX를 하향돌파 & 둘 다 직전에 30 이상이었나"""
    md, ax = minus_di, adx
    sig = (md.shift(1) >= ax.shift(1)) & (md < ax) & \
          (md.shift(1) >= threshold) & (ax.shift(1) >= threshold)
    return sig


def dmi_imminent(minus_di, adx, threshold=30, gap=3.0):
    """DMI 매수신호 임박: DI-·ADX 둘 다 30 이상이고 DI-가 ADX 바로 위에서 근접
    (곧 하향 돌파 예상). 마지막 봉 기준 bool."""
    md, ax = pd.Series(minus_di), pd.Series(adx)
    if len(md) < 2:
        return False
    m, a = float(md.iloc[-1]), float(ax.iloc[-1])
    return bool(m >= threshold and a >= threshold and 0 <= (m - a) <= gap)


# ============================================================
# 4. 스윙 피벗 / 다이버전스 (Stochastics Slow 기준)
# ============================================================
def find_pivots(series, width=3):
    """좌우 width 봉보다 낮은/높은 확정 피벗의 정수 인덱스 목록.
    반환: (low_idx_list, high_idx_list)"""
    s = pd.Series(series).astype(float).reset_index(drop=True)
    n = len(s)
    lows, highs = [], []
    for i in range(width, n - width):
        win = s.iloc[i - width:i + width + 1]
        c = s.iloc[i]
        if c == win.min() and c < s.iloc[i - 1] and c < s.iloc[i + 1]:
            lows.append(i)
        if c == win.max() and c > s.iloc[i - 1] and c > s.iloc[i + 1]:
            highs.append(i)
    return lows, highs


def bullish_divergence(low, slow_k, width=3):
    """상승 다이버전스(매수): 주가 저점은 더 낮은데 Stochastics 저점은 더 높고 상향 턴.
    마지막 봉 부근에서 새 피벗이 확정될 때만 True."""
    pl = pd.Series(low).astype(float).reset_index(drop=True)
    sk = pd.Series(slow_k).astype(float).reset_index(drop=True)
    lows_idx, _ = find_pivots(pl, width)
    if len(lows_idx) < 2:
        return False, None
    i1, i2 = lows_idx[-2], lows_idx[-1]
    n = len(pl)
    if (n - 1) - (i2 + width) > 1:          # 최근 확정 피벗만
        return False, None
    if pl.iloc[i2] < pl.iloc[i1] and sk.iloc[i2] > sk.iloc[i1] and sk.iloc[-1] > sk.iloc[i2]:
        return True, {"k1": round(float(sk.iloc[i1]), 1), "k2": round(float(sk.iloc[i2]), 1)}
    return False, None


def bearish_divergence(high, slow_k, width=3):
    """하락 다이버전스(매도): 주가 고점은 더 높은데 Stochastics 고점은 더 낮고 하향 턴."""
    ph = pd.Series(high).astype(float).reset_index(drop=True)
    sk = pd.Series(slow_k).astype(float).reset_index(drop=True)
    _, highs_idx = find_pivots(ph, width)
    if len(highs_idx) < 2:
        return False, None
    i1, i2 = highs_idx[-2], highs_idx[-1]
    n = len(ph)
    if (n - 1) - (i2 + width) > 1:
        return False, None
    if ph.iloc[i2] > ph.iloc[i1] and sk.iloc[i2] < sk.iloc[i1] and sk.iloc[-1] < sk.iloc[i2]:
        return True, {"k1": round(float(sk.iloc[i1]), 1), "k2": round(float(sk.iloc[i2]), 1)}
    return False, None


# ============================================================
# 5. 저점/고점 대량거래 돌파 (3영업일 확정)
# ============================================================
def volume_breakout(df, lookback=126, confirm_days=3, trend_ma=60):
    """최근 lookback 중 최대 거래량 봉이 confirm_days 이내에 발생했고,
    저점(매수): 하락추세에서 그 봉 고가를 종가가 돌파,
    고점(매도): 상승추세에서 그 봉 저가를 종가가 이탈."""
    high = df["High"].astype(float).reset_index(drop=True)
    low = df["Low"].astype(float).reset_index(drop=True)
    close = df["Close"].astype(float).reset_index(drop=True)
    vol = df["Volume"].astype(float).reset_index(drop=True)
    n = len(df)
    out = {"low_vol": False, "high_vol": False, "vol_ratio": None}
    if n < trend_ma:
        return out
    window = vol.iloc[-lookback:] if n >= lookback else vol
    max_i = int(window.idxmax())
    bars_since = (n - 1) - max_i
    if not (0 <= bars_since <= confirm_days):
        return out
    ma = close.rolling(trend_ma).mean()
    bar_ma = ma.iloc[max_i]
    if pd.isna(bar_ma):
        return out
    bar_close = close.iloc[max_i]
    price = close.iloc[-1]
    out["vol_ratio"] = round(float(vol.iloc[max_i] / max(vol.iloc[-lookback:].median(), 1e-9)), 1)
    if bar_close < bar_ma and price > high.iloc[max_i]:        # 저점 대량거래 돌파(매수)
        out["low_vol"] = True
    if bar_close > bar_ma and price < low.iloc[max_i]:         # 고점 대량거래 이탈(매도)
        out["high_vol"] = True
    return out


if __name__ == '__main__':
    print("engine module loaded")
