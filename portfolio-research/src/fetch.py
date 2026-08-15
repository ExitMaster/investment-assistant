"""Raw data acquisition.

Every function writes an untouched copy of what the source returned into
``data/raw`` and returns a tidy pandas object.  Nothing here transforms
returns; that happens in :mod:`build_dataset`.

Sources used (all authoritative or academic):
  * Yahoo Finance chart API  -- ETF / index price + adjusted-close histories
  * FRED (Federal Reserve Bank of St. Louis) -- CPI, Treasury-bill rates
  * LBMA (London Bullion Market Association) -- the gold benchmark price
  * Kenneth R. French data library (Dartmouth) -- long-horizon academic
    portfolio total returns
"""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
LBMA_GOLD_PM = "https://prices.lbma.org.uk/json/gold_pm.json"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# FRED's bot mitigation silently black-holes requests carrying a browser
# User-Agent (and some custom ones).  Leaving the library's own User-Agent in
# place is what it accepts, so this header set deliberately does not set one.
_SCRIPT_HEADERS = {"Accept": "*/*"}


def _get(url: str, session: requests.Session | None = None, tries: int = 6,
         headers: dict | None = None, **kw) -> requests.Response:
    """GET with exponential backoff.  Raises on the final failure.

    Yahoo answers 429 when hit too fast; that gets a longer pause than an
    ordinary network flake.
    """
    sess = session or requests
    last: Exception | None = None
    for i in range(tries):
        try:
            r = sess.get(url, timeout=60, headers=headers or _HEADERS, **kw)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} for {url}")
            time.sleep((10 if r.status_code == 429 else 2) * (i + 1))
            continue
        except Exception as exc:  # network flake
            last = exc
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed after {tries} tries: {url}") from last


def _cache_path(name: str) -> Path:
    return RAW / name


# --------------------------------------------------------------------------
# Yahoo Finance
# --------------------------------------------------------------------------
class Yahoo:
    """Yahoo chart API client (cookie + crumb handshake)."""

    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(_HEADERS)
        self._crumb: str | None = None
        self._last_call = 0.0

    def _handshake(self) -> str:
        if self._crumb:
            return self._crumb
        # fc.yahoo.com answers 404 but sets the consent cookies the crumb
        # endpoint requires; the quote page tops them up.
        for warm in ("https://fc.yahoo.com/", "https://finance.yahoo.com/quote/SPY/"):
            try:
                self.s.get(warm, timeout=60)
            except Exception:
                pass
        r = _get("https://query2.finance.yahoo.com/v1/test/getcrumb", self.s)
        self._crumb = r.text.strip()
        if not self._crumb:
            raise RuntimeError("Yahoo returned an empty crumb")
        return self._crumb

    def _throttle(self, seconds: float = 1.5) -> None:
        wait = seconds - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def daily(self, symbol: str, refresh: bool = False) -> pd.DataFrame:
        """Full daily history with ``close`` and ``adjclose``.

        ``adjclose`` is dividend- and split-adjusted -> total return.
        ``close`` is split-adjusted only -> price return.
        """
        cache = _cache_path(f"yahoo_{symbol.replace('^', 'IDX_')}.json")
        if refresh or not cache.exists():
            self._throttle()
            crumb = self._handshake()
            url = (
                "https://query2.finance.yahoo.com/v8/finance/chart/"
                f"{requests.utils.quote(symbol)}"
                "?period1=-2208988800&period2=9999999999&interval=1d"
                f"&events=div%7Csplit&crumb={requests.utils.quote(crumb)}"
            )
            r = _get(url, self.s)
            cache.write_text(r.text)
        payload = json.loads(cache.read_text())
        res = payload["chart"]["result"][0]
        idx = pd.to_datetime(pd.Series(res["timestamp"]), unit="s", utc=True)
        idx = idx.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
        quote = res["indicators"]["quote"][0]
        df = pd.DataFrame({"close": quote["close"]}, index=pd.DatetimeIndex(idx))
        adj = res["indicators"].get("adjclose")
        df["adjclose"] = adj[0]["adjclose"] if adj else quote["close"]
        df = df.dropna(how="all").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df


# --------------------------------------------------------------------------
# FRED
# --------------------------------------------------------------------------
def fred(series_id: str, refresh: bool = False) -> pd.Series:
    cache = _cache_path(f"fred_{series_id}.csv")
    if refresh or not cache.exists():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        cache.write_bytes(_get(url, headers=_SCRIPT_HEADERS).content)
    df = pd.read_csv(cache)
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col])
    s = pd.to_numeric(df[series_id], errors="coerce")
    s.index = df[date_col]
    s.name = series_id
    return s.dropna()


# --------------------------------------------------------------------------
# LBMA gold
# --------------------------------------------------------------------------
def lbma_gold_pm(refresh: bool = False) -> pd.Series:
    """Daily LBMA Gold Price PM in USD/troy oz (from 1968-04-01)."""
    cache = _cache_path("lbma_gold_pm.json")
    if refresh or not cache.exists():
        cache.write_bytes(_get(LBMA_GOLD_PM).content)
    rows = json.loads(cache.read_text())
    recs = [(r["d"], r["v"][0]) for r in rows if r.get("v") and r["v"][0] is not None]
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in recs}).sort_index()
    s.name = "gold_usd_pm"
    return s


# --------------------------------------------------------------------------
# Kenneth French data library
# --------------------------------------------------------------------------
def french_zip(name: str, refresh: bool = False) -> str:
    """Download a French library CSV zip and return the decoded text."""
    cache = _cache_path(f"french_{name}")
    if refresh or not cache.exists():
        cache.write_bytes(_get(f"{FRENCH_BASE}/{name}").content)
    with zipfile.ZipFile(io.BytesIO(cache.read_bytes())) as z:
        inner = z.namelist()[0]
        return z.read(inner).decode("latin-1")


def french_monthly_blocks(text: str) -> list[tuple[str, pd.DataFrame]]:
    """Split a French library CSV into ``(section_title, monthly_table)`` pairs.

    French files stack several tables (VW returns, EW returns, firm counts,
    ...) separated by blank lines, each introduced by a free-text title such as
    ``  Average Value Weighted Returns -- Monthly``.  Only monthly blocks --
    recognised by their ``YYYYMM`` row labels -- are returned; annual blocks
    (``YYYY`` labels) are skipped.
    """
    blocks: list[tuple[str, pd.DataFrame]] = []
    pending: list[str] = []      # non-data lines seen since the last block
    rows: list[str] = []

    def flush() -> None:
        if not rows:
            return
        col_header = pending[-1] if pending else ""
        title = pending[-2].strip() if len(pending) >= 2 else ""
        df = pd.read_csv(io.StringIO("\n".join([col_header] + rows)))
        df.columns = ["ym"] + [str(c).strip() for c in df.columns[1:]]
        idx = pd.PeriodIndex(pd.to_datetime(df["ym"].astype(str).str.strip(),
                                            format="%Y%m"), freq="M")
        out = df.drop(columns=["ym"]).apply(pd.to_numeric, errors="coerce")
        out.index = idx
        out = out.mask(out <= -99.0)   # French missing-data markers
        blocks.append((title, out))

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        first = line.split(",")[0].strip()
        if first.isdigit() and len(first) == 6:
            rows.append(line)
            continue
        if rows:                       # a data run just ended
            flush()
            rows = []
            pending = []
        if line.strip():
            pending.append(line)
    if rows:
        flush()
    return blocks


def french_monthly_table(text: str, title_pattern: str | None) -> pd.DataFrame:
    """Return the monthly block whose section title matches ``title_pattern``.

    ``None`` selects the first (and, for single-table files such as the
    Fama-French factor file, only) monthly block.
    """
    if title_pattern is None:
        return french_monthly_blocks(text)[0][1]
    rx = re.compile(title_pattern, re.I)
    hits = [(t, d) for t, d in french_monthly_blocks(text) if rx.search(t)]
    if not hits:
        titles = [t for t, _ in french_monthly_blocks(text)]
        raise KeyError(f"no monthly block matching {title_pattern!r}; have {titles}")
    if len(hits) > 1:
        raise KeyError(f"{title_pattern!r} matches {len(hits)} blocks: "
                       f"{[t for t, _ in hits]}")
    return hits[0][1]


def french_series(zip_name: str, column: str,
                  title_pattern: str = r"Value Weighted Returns\s*--\s*Monthly",
                  refresh: bool = False) -> pd.Series:
    """Return one French column as a *decimal* monthly total-return series."""
    tbl = french_monthly_table(french_zip(zip_name, refresh=refresh), title_pattern)
    if column not in tbl.columns:
        raise KeyError(f"{column!r} not in {list(tbl.columns)}")
    s = tbl[column].astype(float) / 100.0
    s.name = column
    return s.dropna()


def available_french_columns(zip_name: str,
                             title_pattern: str = r"Monthly") -> Iterable[str]:
    return list(french_monthly_table(french_zip(zip_name), title_pattern).columns)


# --------------------------------------------------------------------------
# Nasdaq official index history
# --------------------------------------------------------------------------
NASDAQ_INDEX_BASE = "https://indexes.nasdaqomx.com"


def _curl_nasdaq(page_url: str, export_url: str, tries: int = 4) -> bytes:
    """Fetch the export with curl, carrying the cookie the page hands out."""
    import subprocess
    import tempfile
    for i in range(tries):
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "cookies.txt"
            out = Path(tmp) / "export.bin"
            base = ["curl", "-sS", "--http1.1", "--max-time", "90",
                    "-H", f"User-Agent: {_UA}"]
            subprocess.run(base + ["-c", str(jar), "-o", "/dev/null", page_url],
                           check=False, capture_output=True)
            subprocess.run(base + ["-b", str(jar), "-H", f"Referer: {page_url}",
                                   "-o", str(out), export_url],
                           check=False, capture_output=True)
            data = out.read_bytes() if out.exists() else b""
        if data[:2] == b"PK":
            return data
        time.sleep(15 * (i + 1))
    return data


def nasdaq_index_history(symbol: str, start: str = "1980-01-01",
                         end: str = "2100-01-01", refresh: bool = False
                         ) -> pd.Series:
    """Daily closing values of a Nasdaq index, from Nasdaq's own index site.

    ``symbol`` is the Nasdaq index ticker, e.g. ``XNDX`` for the Nasdaq-100
    **Total Return** index.  The site hands out an .xlsx export once a session
    cookie exists, so the history page is fetched first.

    The site sits behind Imperva/Incapsula, which starts serving a JavaScript
    challenge to any client that fetches repeatedly.  The export is pulled with
    ``curl`` -- whose TLS fingerprint the challenge accepts where
    python-requests' is refused -- and cached.  A challenged run falls back to
    the cached payload rather than silently producing nothing.
    """
    cache = _cache_path(f"nasdaq_{symbol}.xlsx")
    if refresh or not cache.exists():
        page = f"{NASDAQ_INDEX_BASE}/Index/History/{symbol}"
        url = (f"{NASDAQ_INDEX_BASE}/Index/ExportHistory/{symbol}"
               f"?startDate={start}T00:00:00&endDate={end}T00:00:00&timeOfDay=EOD")
        payload = _curl_nasdaq(page, url)
        if payload[:2] != b"PK":
            if cache.exists():
                print(f"  nasdaq: {symbol} export was challenged; using cache")
            else:
                raise RuntimeError(
                    f"Nasdaq served a challenge instead of the {symbol} export "
                    f"and no cached copy exists. Retry later, or download "
                    f"{url} in a browser and save it to {cache}.")
        else:
            cache.write_bytes(payload)

    import openpyxl
    ws = openpyxl.load_workbook(cache, read_only=True, data_only=True)["History"]
    rows = [(r[0], r[1]) for r in ws.iter_rows(values_only=True)
            if r and hasattr(r[0], "year") and r[1] is not None]
    if not rows:
        raise RuntimeError(f"no rows parsed from the {symbol} export")
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in rows}).sort_index()
    s.name = symbol
    return s
