"""
데이터 수집 모듈.
- 일봉(OHLCV) 히스토리: ATH·보조지표 계산용
- 실시간 현재가: 장중 하락률 판정용
yfinance를 기본 소스로 사용. (GitHub Actions 환경에서는 정상 작동)
"""
import time
from datetime import timezone
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


def get_daily_history(ticker, period="6y", interval="1d"):
    """
    일봉 OHLCV DataFrame 반환.
    컬럼: Open, High, Low, Close, Volume (auto_adjust=True)
    실패 시 None.
    """
    for attempt in range(3):
        try:
            df = yf.download(
                ticker, period=period, interval=interval,
                progress=False, auto_adjust=True, threads=False,
            )
            if df is not None and len(df) > 0:
                # 멀티인덱스 컬럼 평탄화
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df.dropna()
        except Exception as e:
            print(f"[data] {ticker} history attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None


def get_current_price(ticker):
    """
    실시간(또는 최근) 현재가 반환. 실패 시 None.
    장중에는 분 단위 최신가, 장 외에는 마지막 종가.
    """
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)
            # fast_info가 가장 가볍고 빠름
            fi = getattr(t, "fast_info", None)
            if fi:
                px = fi.get("last_price") or fi.get("lastPrice")
                if px:
                    return float(px)
            # fallback: 1분봉 마지막
            df = t.history(period="1d", interval="1m")
            if len(df):
                return float(df["Close"].iloc[-1])
        except Exception as e:
            print(f"[data] {ticker} price attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None


def get_current_quote(ticker):
    """(현재가, 최신 틱 시각 UTC, 전일 종가) 반환. 시각/전일종가를 못 얻으면 None.
    휴장/장외 판별(신선도 가드)·전일대비 등락률 표시에 사용한다."""
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)
            prev_close = None
            try:
                fi = t.fast_info
                pc = fi.get("previousClose") or fi.get("regularMarketPreviousClose") \
                    or fi.get("previous_close")
                if pc:
                    prev_close = float(pc)
            except Exception:
                prev_close = None
            df = t.history(period="1d", interval="1m")
            if len(df):
                price = float(df["Close"].iloc[-1])
                ts = df.index[-1].to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
                return price, ts, prev_close
            fi2 = getattr(t, "fast_info", None)
            if fi2:
                px = fi2.get("last_price") or fi2.get("lastPrice")
                if px:
                    return float(px), None, prev_close
        except Exception as e:
            print(f"[data] {ticker} quote attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None, None, None


def get_daily_closes_for_ath(ticker, lookback):
    """
    ATH 계산용 종가 시리즈. lookback: '5y'|'3y'|'52w'|'all'
    """
    period_map = {
        "1y": "1y", "2y": "2y",
        "3y": "5y", "4y": "5y", "5y": "5y",
        "6y": "10y", "7y": "10y", "8y": "10y", "9y": "10y", "10y": "10y",
        "52w": "1y", "all": "max",
    }
    period = period_map.get(lookback, "5y")
    df = get_daily_history(ticker, period=period)
    if df is None:
        return None
    return df["Close"]
