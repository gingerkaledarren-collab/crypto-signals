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


def compute_pi_cycle_ratio(price_df: pd.DataFrame, short_window: int = 111, long_window: int = 350) -> pd.DataFrame:
    """
    Computes the Pi Cycle Top ratio: 111-day SMA / (2 x 350-day SMA).

    This is a well-known price-only cycle-top indicator -- historically,
    the 111-day SMA crossing above 2x the 350-day SMA (ratio crossing 1.0)
    has closely marked BTC cycle tops. It needs only price data, unlike
    MVRV Z-Score/Puell Multiple which need on-chain realized-cap data we
    don't have a free source for.

    Returns df with columns: date, sma_111, sma_350x2, pi_cycle_ratio
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    df["sma_111"] = df["price"].rolling(window=short_window, min_periods=short_window).mean()
    df["sma_350x2"] = df["price"].rolling(window=long_window, min_periods=long_window).mean() * 2
    df["pi_cycle_ratio"] = df["sma_111"] / df["sma_350x2"]
    return df[["date", "sma_111", "sma_350x2", "pi_cycle_ratio"]]


def normalize_pi_cycle_ratio(ratio: pd.Series, clip_range: tuple = (0.35, 1.05)) -> pd.Series:
    """
    Maps the Pi Cycle ratio to a 0-100 greed scale.

    Calibration note: historically (2011-present) this ratio has run from
    ~0.30 (deep capitulation) up to ~1.47 (2013 blow-off top), with the
    classic "top signal" cross at ratio=1.0. Clip bounds are set from the
    ~5th/95th percentiles of that history, so ratio=1.0 lands around a
    score of ~90 (strong but not maximal greed) rather than pinning to 100.
    """
    lo, hi = clip_range
    clipped = ratio.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


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
      fng_value, fng_smoothed, fng_score, weekly_rsi, rsi_score,
      sma_111, sma_350x2, pi_cycle_ratio, pi_cycle_score
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

    pi_df = compute_pi_cycle_ratio(price_df)
    pi_df["pi_cycle_score"] = normalize_pi_cycle_ratio(pi_df["pi_cycle_ratio"])
    merged = pd.merge(merged, pi_df[["date", "sma_111", "sma_350x2", "pi_cycle_ratio", "pi_cycle_score"]],
                       on="date", how="inner")

    return merged


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()

    table = build_indicator_table(price_df, fng_df)
    print(table.tail(10))
    print(f"\n{len(table)} aligned rows, from {table['date'].min().date()} to {table['date'].max().date()}")
    print(f"Rows with valid 200w MA: {table['ma_200w'].notna().sum()}")
