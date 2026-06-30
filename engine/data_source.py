"""
데이터 수집 모듈.
- 일봉(OHLCV) 히스토리: ATH·보조지표 계산용
- 실시간 현재가: 장중 하락률 판정용
yfinance를 기본 소스로 사용. (GitHub Actions 환경에서는 정상 작동)
"""
import re
import json
import time
import urllib.parse
import urllib.request
from datetime import timezone
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


_KR_CODE = re.compile(r'^\d{6}$')
_kr_symbol_cache = {}

# 국내 지수 별칭: 웹/네이버에서 쓰는 KOSPI/KOSDAQ ↔ yfinance 심볼 ^KS11/^KQ11
_INDEX_ALIAS = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}


def _resolve_kr_symbol(code):
    """국내 6자리 코드 → yfinance 정식 심볼(.KS/.KQ). Yahoo 심볼검색에서 EQUITY를 고른다.
    .KS·.KQ 둘 다 시세를 반환하되 한쪽은 코드만 같은 펀드(MUTUALFUND)라, quoteType=EQUITY로
    구분해야 엉뚱한 펀드 값을 집지 않는다. 해석 실패 시 .KS 기본값(캐시 안 함 → 다음에 재시도)."""
    if code in _kr_symbol_cache:
        return _kr_symbol_cache[code]
    url = ("https://query1.finance.yahoo.com/v1/finance/search?q="
           + urllib.parse.quote(code) + "&quotesCount=8&newsCount=0")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            quotes = json.load(resp).get("quotes", [])
        for q in quotes:  # 1순위: 코드로 시작하는 .KS/.KQ 중 EQUITY
            s = q.get("symbol", "")
            if s.startswith(code) and s.endswith((".KS", ".KQ")) and q.get("quoteType") == "EQUITY":
                _kr_symbol_cache[code] = s
                return s
        for q in quotes:  # 2순위: EQUITY가 없으면 첫 .KS/.KQ
            s = q.get("symbol", "")
            if s.endswith((".KS", ".KQ")):
                _kr_symbol_cache[code] = s
                return s
    except Exception as e:
        print(f"[data] {code} KR resolve failed: {e}")
    return code + ".KS"


def _yf(ticker):
    """저장 티커를 yfinance 심볼로 변환. 국내 지수 별칭(KOSPI/KOSDAQ)·6자리 코드(.KS/.KQ) 해석."""
    if ticker in _INDEX_ALIAS:
        return _INDEX_ALIAS[ticker]
    if _KR_CODE.match(ticker):
        return _resolve_kr_symbol(ticker)
    return ticker


def get_daily_history(ticker, period="6y", interval="1d"):
    """
    일봉 OHLCV DataFrame 반환.
    컬럼: Open, High, Low, Close, Volume (auto_adjust=True)
    실패 시 None.
    """
    sym = _yf(ticker)
    for attempt in range(3):
        try:
            df = yf.download(
                sym, period=period, interval=interval,
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
    sym = _yf(ticker)
    for attempt in range(3):
        try:
            t = yf.Ticker(sym)
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
    sym = _yf(ticker)
    for attempt in range(3):
        try:
            t = yf.Ticker(sym)
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
