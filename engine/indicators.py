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


if __name__ == '__main__':
    print("engine module loaded")
