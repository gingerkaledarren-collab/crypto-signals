"""
indicators.py

Computes the actual indicator values from raw data, and normalizes each
one to a 0-100 "greed scale" so they're comparable and combinable later.

Normalized scale convention (matches Fear & Greed's own convention):
  0   = extreme fear / extremely undervalued -> historically a buy zone
  100 = extreme greed / extremely overvalued -> historically a sell zone
"""

import pandas as pd
import numpy as np


def compute_200w_ma_distance(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes the 200-week moving average (= 1400 days) and the price's
    % distance above/below it.

    NOTE: this needs ~4 years of price history to produce values from
    day 1 of your analysis window. With less history, the early portion
    of the series will be NaN until the rolling window fills.

    Returns df with columns: date, price, ma_200w, pct_distance
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    window_days = 200 * 7  # 1400 days

    df["ma_200w"] = df["price"].rolling(window=window_days, min_periods=window_days).mean()
    df["pct_distance"] = (df["price"] - df["ma_200w"]) / df["ma_200w"] * 100

    return df[["date", "price", "ma_200w", "pct_distance"]]


def normalize_200w_distance(pct_distance: pd.Series, clip_range: tuple = (-40, 150)) -> pd.Series:
    """
    Maps % distance from 200w MA to a 0-100 greed scale.

    Calibration note: historically BTC has traded from roughly -40% below
    its 200w MA (deep bear capitulation) to +150%+ above it (late-cycle
    euphoria, e.g. 2017/2021 tops). These clip bounds are a starting
    assumption -- once we backtest against full cycle history we should
    revisit them using actual percentile distributions rather than
    eyeballed bounds.
    """
    lo, hi = clip_range
    clipped = pct_distance.clip(lower=lo, upper=hi)
    normalized = (clipped - lo) / (hi - lo) * 100
    return normalized


def smooth_fear_greed(fng_df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """
    Applies a rolling average to the daily Fear & Greed Index to reduce
    day-to-day noise, since raw daily F&G can whipsaw and isn't meant
    for a long-term positioning system on its own.

    Returns df with columns: date, fng_value, fng_smoothed
    """
    df = fng_df.copy().sort_values("date").reset_index(drop=True)
    df["fng_smoothed"] = df["fng_value"].rolling(window=window, min_periods=1).mean()
    return df[["date", "fng_value", "fng_smoothed"]]


def build_indicator_table(price_df: pd.DataFrame, fng_df: pd.DataFrame) -> pd.DataFrame:
    """
    Joins both indicators into a single date-aligned table, with each
    indicator normalized to the 0-100 greed scale.

    Returns df with columns:
      date, price, ma_200w, pct_distance, ma_200w_score,
      fng_value, fng_smoothed, fng_score
    """
    ma_df = compute_200w_ma_distance(price_df)
    ma_df["ma_200w_score"] = normalize_200w_distance(ma_df["pct_distance"])

    fng_smooth_df = smooth_fear_greed(fng_df)
    fng_smooth_df["fng_score"] = fng_smooth_df["fng_smoothed"]  # already 0-100

    merged = pd.merge(ma_df, fng_smooth_df, on="date", how="inner")
    return merged


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()

    table = build_indicator_table(price_df, fng_df)
    print(table.tail(10))
    print(f"\n{len(table)} aligned rows, from {table['date'].min().date()} to {table['date'].max().date()}")
    print(f"Rows with valid 200w MA: {table['ma_200w'].notna().sum()}")
