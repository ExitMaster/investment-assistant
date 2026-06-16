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
class AthRatchet:
    """
    종가 기준 ATH 기준선 관리.
    - 평소 신고가는 ATH를 갱신하지 않고 running_high로만 추적
    - running_high가 ATH 대비 +reset_pct 초과한 적이 있고
      그 뒤 종가가 ATH 아래로 내려오면 → ATH를 running_high로 갱신
    - 쌍봉/횡보(+reset_pct 미달)로는 ATH 불변
    """
    def __init__(self, initial_ath, reset_pct=10.0):
        self.ath = float(initial_ath)
        self.reset_pct = reset_pct / 100.0
        self.running_high = float(initial_ath)
        self.exceeded_threshold = False  # running_high가 +10% 넘은 적 있나

    def update(self, close):
        """하루 종가를 받아 상태 갱신. 갱신 이벤트가 있으면 반환."""
        event = None

        # running_high 추적
        if close > self.running_high:
            self.running_high = close

        # running_high가 ATH 대비 +reset_pct 초과했는지 기록
        if self.running_high >= self.ath * (1 + self.reset_pct):
            self.exceeded_threshold = True

        # ATH 아래로 종가가 내려왔을 때
        if close < self.ath:
            if self.exceeded_threshold:
                # +10% 넘었다가 내려옴 → ATH 갱신
                old = self.ath
                self.ath = self.running_high
                event = ('ATH_UPDATED', old, self.ath)
                # 리셋
                self.running_high = close
                self.exceeded_threshold = False
            # 넘은 적 없으면(쌍봉/횡보) ATH 불변
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
