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


def compute_weekly_macd(price_df: pd.DataFrame, fast_weeks: int = 12,
                        slow_weeks: int = 26, signal_weeks: int = 9) -> pd.DataFrame:
    """
    Computes a weekly-timeframe MACD (default 12/26/9 weeks) on daily data.

    Classic MACD runs on daily candles, which is far too twitchy for a
    long-term positioning system. Scaling the EMA spans by 7 (84/182/63
    days) gives the weekly-chart MACD that cycle analysts watch, while
    staying on the same daily date index as the other indicators. Like
    the 200w MA, values are NaN until the slow EMA's window has filled.

    Because raw MACD is in dollars, a +$2k reading meant something very
    different at $10k BTC than at $60k. 'macd_pct' is the scale-free
    version (MACD as % of the slow EMA, a.k.a. the Percentage Price
    Oscillator), which is what gets normalized for scoring.

    Returns df with columns:
      date, macd, macd_signal, macd_hist, macd_pct
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    fast_span, slow_span, signal_span = fast_weeks * 7, slow_weeks * 7, signal_weeks * 7

    ema_fast = df["price"].ewm(span=fast_span, adjust=False, min_periods=slow_span).mean()
    ema_slow = df["price"].ewm(span=slow_span, adjust=False, min_periods=slow_span).mean()

    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal_span, adjust=False, min_periods=signal_span).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["macd_pct"] = df["macd"] / ema_slow * 100

    return df[["date", "macd", "macd_signal", "macd_hist", "macd_pct"]]


def normalize_macd_pct(macd_pct: pd.Series, clip_range: tuple = (-30, 60)) -> pd.Series:
    """
    Maps weekly MACD-as-%-of-price to a 0-100 greed scale.

    Calibration note: these bounds are an unvalidated starting guess --
    deep bear markets should push the weekly fast EMA well below the slow
    one, and parabolic run-ups (2017, 2021) stretch it far above, with
    the upside historically more extreme than the downside. As with the
    200w MA bounds, revisit them using the actual percentile distribution
    once full-cycle history is available.

    Unlike the other two indicators, MACD measures trend momentum rather
    than valuation or sentiment, so it tends to lag at turning points --
    worth checking in the backtest whether it adds signal or just delay.
    """
    lo, hi = clip_range
    clipped = macd_pct.clip(lower=lo, upper=hi)
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
    Joins all indicators into a single date-aligned table, with each
    indicator normalized to the 0-100 greed scale.

    Returns df with columns:
      date, price, ma_200w, pct_distance, ma_200w_score,
      macd, macd_signal, macd_hist, macd_pct, macd_score,
      fng_value, fng_smoothed, fng_score
    """
    ma_df = compute_200w_ma_distance(price_df)
    ma_df["ma_200w_score"] = normalize_200w_distance(ma_df["pct_distance"])

    macd_df = compute_weekly_macd(price_df)
    macd_df["macd_score"] = normalize_macd_pct(macd_df["macd_pct"])
    ma_df = pd.merge(ma_df, macd_df, on="date", how="left")

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
    print(f"Rows with valid weekly MACD: {table['macd'].notna().sum()}")
