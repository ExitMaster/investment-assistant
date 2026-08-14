"""History must not move when the data are re-fetched (SC-19).

Each anchor below is a month whose value is independently checkable against
the historical record.  If a later retrieval changes any of them, a source has
revised, re-based or corrupted its history and every result downstream is
suspect -- so this fails loudly rather than silently re-writing the study.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.build_dataset import load

# (dataset, column, month, expected value, what the month is)
ANCHORS = [
    ("structural", "SPY", "1987-10", -0.2259, "Black Monday"),
    ("structural", "SPY", "2008-10", -0.1712, "post-Lehman collapse"),
    ("structural", "SPY", "1933-04", 0.3891, "the sharpest month of the 1933 rally"),
    ("structural", "GOLD", "1980-01", 0.27539, "the Hunt-brothers gold spike"),
    ("structural", "QQQ", "2000-04", -0.1004, "the month the dot-com bubble broke"),
    ("structural", "CASH", "1981-06", 0.0135, "the Volcker rate peak (~17.5%/yr)"),
    ("live", "SPY", "2020-03", -0.12487, "the covid crash"),
    ("live", "QQQ", "2008-10", -0.15472, "post-Lehman collapse"),
    ("cpi", "CPIAUCNS", "2020-01", 257.971, "a published CPI level"),
]


@pytest.mark.parametrize("dataset,col,month,expected,what", ANCHORS)
def test_anchor_value_unchanged(dataset, col, month, expected, what):
    df = load(dataset)
    actual = float(df.loc[pd.Period(month, freq="M"), col])
    assert actual == pytest.approx(expected, abs=5e-5), (
        f"{dataset}.{col} for {month} ({what}) is now {actual}, was {expected}")


def test_sample_boundaries_unchanged():
    """The first month of each series is a property of the source, not of us."""
    s = load("structural")
    assert str(s["SPY"].dropna().index[0]) == "1926-07"
    assert str(s["GOLD"].dropna().index[0]) == "1968-05"
    assert str(s["QQQ"].dropna().index[0]) == "1965-07"
    live = load("live")
    assert str(live["SPY"].dropna().index[0]) == "1993-02"
    assert str(live["QQQ"].dropna().index[0]) == "1999-04"
    assert str(live["SCHD"].dropna().index[0]) == "2011-11"
    assert str(live["SPMO"].dropna().index[0]) == "2015-11"
