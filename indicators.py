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


def compute_weekly_rsi(price_df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Computes RSI on WEEKLY closes (not daily) -- daily RSI is a momentum
    indicator too noisy for a positioning system, but the weekly version
    is a standard long-term overbought/oversold gauge and needs only the
    price series we already have (no on-chain data required).

    Uses Wilder's smoothing (the standard RSI method) via an EWM with
    alpha=1/period.

    Returns df with columns: date, weekly_rsi
    Note: 'date' here is the week-ending date each weekly bar is labeled with.
    """
    weekly = price_df.copy().set_index("date")["price"].resample("W").last().dropna()
    delta = weekly.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.rename("weekly_rsi").reset_index()


def build_indicator_table(price_df: pd.DataFrame, fng_df: pd.DataFrame) -> pd.DataFrame:
    """
    Joins all indicators into a single date-aligned table, with each
    indicator normalized to the 0-100 greed scale.

    Returns df with columns:
      date, price, ma_200w, pct_distance, ma_200w_score,
      fng_value, fng_smoothed, fng_score, weekly_rsi, rsi_score
    """
    ma_df = compute_200w_ma_distance(price_df)
    ma_df["ma_200w_score"] = normalize_200w_distance(ma_df["pct_distance"])

    fng_smooth_df = smooth_fear_greed(fng_df)
    fng_smooth_df["fng_score"] = fng_smooth_df["fng_smoothed"]  # already 0-100

    merged = pd.merge(ma_df, fng_smooth_df, on="date", how="inner")

    rsi_df = compute_weekly_rsi(price_df)
    # merge_asof(direction="backward") attaches each daily row the most
    # recently COMPLETED weekly RSI bar -- never a bar that hasn't closed
    # yet as of that date, so this doesn't leak future data into the past.
    merged = pd.merge_asof(
        merged.sort_values("date"), rsi_df.sort_values("date"), on="date", direction="backward"
    )
    merged["rsi_score"] = merged["weekly_rsi"]  # already 0-100, same convention

    return merged


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()

    table = build_indicator_table(price_df, fng_df)
    print(table.tail(10))
    print(f"\n{len(table)} aligned rows, from {table['date'].min().date()} to {table['date'].max().date()}")
    print(f"Rows with valid 200w MA: {table['ma_200w'].notna().sum()}")
