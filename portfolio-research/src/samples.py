"""Sample construction: turn a processed panel into an analysis-ready window.

A *sample* is a dataset plus a date range plus an exposure list.  Every
combination screened inside one sample sees exactly the same months, so
cross-combination comparisons are not distorted by different histories.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from .build_dataset import load

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path) as fh:
        return yaml.safe_load(fh)


@dataclass
class Sample:
    name: str
    label: str
    returns: pd.DataFrame        # monthly returns, PeriodIndex, no NaNs
    cpi: pd.Series               # CPI level aligned to ``returns.index``
    cpi_lagged: pd.Series        # CPI of the previous month, same index
    primary: bool = False

    @property
    def exposures(self) -> list[str]:
        return list(self.returns.columns)

    @property
    def n_months(self) -> int:
        return len(self.returns)

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<Sample {self.name} {self.returns.index[0]}..."
                f"{self.returns.index[-1]} n={self.n_months} "
                f"{self.exposures}>")


def build_sample(name: str, cfg: dict) -> Sample:
    spec = cfg["samples"][name]
    df = load(spec["dataset"])
    exposures = [e for e in cfg["exposures"] if e not in spec.get("exclude", [])]
    missing = [e for e in exposures if e not in df.columns]
    if missing:
        raise KeyError(f"sample {name}: dataset lacks {missing}")
    # Price-return twins live in the same panels for auditing.  They carry a
    # suffix precisely so a simulation can never pick one up by accident.
    leaked = [e for e in exposures if e.endswith("_PRICE_ONLY")]
    if leaked:
        raise ValueError(f"sample {name} would mix price returns in: {leaked}")
    df = df[exposures]

    start = pd.Period(spec["start"], freq="M")
    df = df.loc[df.index >= start]
    df = df.dropna(how="any")            # the common window of all exposures
    if df.empty:
        raise ValueError(f"sample {name} is empty")
    # dropna could leave a hole in the middle; the analysis assumes contiguity.
    span = pd.period_range(df.index[0], df.index[-1], freq="M")
    if len(span) != len(df):
        gaps = sorted(set(span) - set(df.index))
        raise ValueError(f"sample {name} has {len(gaps)} missing months, "
                         f"first at {gaps[0]}")

    cpi = load("cpi")["CPIAUCNS"]
    cpi_lag = cpi.shift(1)
    return Sample(
        name=name,
        label=spec.get("label", ""),
        returns=df,
        cpi=cpi.reindex(df.index),
        cpi_lagged=cpi_lag.reindex(df.index),
        primary=bool(spec.get("primary", False)),
    )


def build_all_samples(cfg: dict) -> dict[str, Sample]:
    return {name: build_sample(name, cfg) for name in cfg["samples"]}
