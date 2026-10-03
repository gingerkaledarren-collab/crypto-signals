"""
st_indicators_fast.py

A FASTER-lookback variant of st_indicators.py's four non-Fear&Greed
components, built to test whether shortening each indicator's window
catches more real local price extremes (see conversation / README's
"Fast-indicator variant" section). Reuses st_indicators.py's raw
compute_*() functions -- they already take window/period as a parameter
-- with shorter windows, and freshly re-derived clip ranges: the
calibration bounds in st_indicators.py were fit to THAT file's windows
(50-day MA, Bollinger 20, MACD 12/26/9) and do not carry over to a
different lookback, since the underlying raw-value distribution changes
with it.

Fear & Greed is UNCHANGED (still 5-day smoothed, fng_st_score) -- only
the four technical indicators are swapped for faster settings:
  - 50-day MA distance  -> 20-day MA distance
  - RSI(14)             -> RSI(7)
  - Bollinger %B(20,2)  -> Bollinger %B(10,2)
  - MACD(12,26,9)       -> MACD(8,17,9)

This is a comparison/test system, not a proposed replacement for the
live short-term composite in st_indicators.py/st_backtest.py -- see
build_dashboard3_data.py and the README for the walk-forward numbers.
"""

import pandas as pd
from st_indicators import (compute_fng_short_smoothed, compute_ma50_distance, compute_daily_rsi,
                           compute_bollinger_pct_b, compute_macd)

# Clip bounds below are the 2018-present ~5th/95th percentiles (~1st/99th
# for Bollinger %B, matching st_indicators.py's own convention) of each
# raw metric AT ITS NEW WINDOW -- re-derived, not copied from the 50/20/
# 12-26-9 settings.
MA20_CLIP_RANGE = (-14, 22)
BB10_CLIP_RANGE = (-9, 111)
MACD_FAST_CLIP_RANGE = (-2.3, 2.3)


def _normalize(series: pd.Series, clip_range: tuple) -> pd.Series:
    lo, hi = clip_range
    clipped = series.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def build_st_indicator_table_fast(price_df: pd.DataFrame, fng_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns df with columns:
      date, price, ma20, pct_distance_20, ma20_score,
      fng_value, fng_short_smoothed, fng_st_score,
      rsi7, rsi7_score,
      bb10_mid, bb10_upper, bb10_lower, pct_b10, bb10_score,
      macd_fast_line, macd_fast_signal, macd_fast_hist_pct, macdfast_score
    """
    ma_df = compute_ma50_distance(price_df, window=20).rename(
        columns={"ma50": "ma20", "pct_distance_50": "pct_distance_20"})
    ma_df["ma20_score"] = _normalize(ma_df["pct_distance_20"], MA20_CLIP_RANGE)

    fng_short_df = compute_fng_short_smoothed(fng_df)
    fng_short_df["fng_st_score"] = fng_short_df["fng_short_smoothed"]
    merged = pd.merge(ma_df, fng_short_df, on="date", how="inner")

    rsi_df = compute_daily_rsi(price_df, period=7).rename(columns={"daily_rsi": "rsi7"})
    rsi_df["rsi7_score"] = rsi_df["rsi7"]
    merged = pd.merge(merged, rsi_df, on="date", how="inner")

    bb_df = compute_bollinger_pct_b(price_df, window=10, num_std=2).rename(columns={
        "bb_mid": "bb10_mid", "bb_upper": "bb10_upper", "bb_lower": "bb10_lower", "pct_b": "pct_b10"})
    bb_df["bb10_score"] = _normalize(bb_df["pct_b10"], BB10_CLIP_RANGE)
    merged = pd.merge(merged, bb_df[["date", "bb10_mid", "bb10_upper", "bb10_lower", "pct_b10", "bb10_score"]],
                       on="date", how="inner")

    macd_df = compute_macd(price_df, fast=8, slow=17, signal=9).rename(columns={
        "macd_line": "macd_fast_line", "macd_signal": "macd_fast_signal", "macd_hist_pct": "macd_fast_hist_pct"})
    macd_df["macdfast_score"] = _normalize(macd_df["macd_fast_hist_pct"], MACD_FAST_CLIP_RANGE)
    merged = pd.merge(merged, macd_df, on="date", how="inner")

    return merged


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()
    table = build_st_indicator_table_fast(price_df, fng_df)
    print(table.tail(10))
    print(f"\n{len(table)} aligned rows, from {table['date'].min().date()} to {table['date'].max().date()}")
