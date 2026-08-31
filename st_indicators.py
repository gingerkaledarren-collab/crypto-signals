"""
st_indicators.py

Indicators for the SHORT-TERM (8-10x/year) repositioning system -- a
separate project from indicators.py (the long-term, 200-week-MA-based
system), not a retuning of it. The long-term system's indicators are
structurally slow (200-week MA, weekly RSI, Pi Cycle Top) and were shown
in backtesting to top out around 3-5 confirmed signals/year even at
aggressive thresholds -- no amount of threshold tuning fixes that, the
indicators themselves need a shorter lookback.

Same 0-100 "greed scale" convention as indicators.py (0 = extreme
low/undervalued, 100 = extreme high/overvalued), same normalization
pattern (clip to a historically-derived range, then linearly rescale),
computed from the SAME raw price/Fear & Greed data -- only the lookback
windows differ. All calibration bounds below come from the actual
2018-present distribution of each raw metric (see the analysis in the
project conversation), not eyeballed.
"""

import pandas as pd


def compute_fng_short_smoothed(fng_df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Lightly-smoothed Fear & Greed Index (5-day, vs. 30-day in the
    long-term system) -- responsive enough to catch a week-long spike
    into "Greed" territory instead of averaging it away.

    Returns df with columns: date, fng_value, fng_short_smoothed
    """
    df = fng_df.copy().sort_values("date").reset_index(drop=True)
    df["fng_short_smoothed"] = df["fng_value"].rolling(window=window, min_periods=1).mean()
    return df[["date", "fng_value", "fng_short_smoothed"]]


def compute_ma50_distance(price_df: pd.DataFrame, window: int = 50) -> pd.DataFrame:
    """
    50-day moving average distance -- a medium-term trend/valuation
    stretch measure, analogous to the long-term system's 200-week MA
    but reacting on a scale of weeks rather than years.

    Returns df with columns: date, price, ma50, pct_distance_50
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    df["ma50"] = df["price"].rolling(window=window, min_periods=window).mean()
    df["pct_distance_50"] = (df["price"] - df["ma50"]) / df["ma50"] * 100
    return df[["date", "price", "ma50", "pct_distance_50"]]


def normalize_ma50_distance(pct_distance_50: pd.Series, clip_range: tuple = (-20, 30)) -> pd.Series:
    """
    Maps % distance from the 50-day MA to a 0-100 scale. Clip bounds set
    from the 2018-present distribution's ~5th/95th percentiles (-20.8 /
    +27.2), rounded to clean numbers.
    """
    lo, hi = clip_range
    clipped = pct_distance_50.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def compute_daily_rsi(price_df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Standard daily RSI(14) -- the classic swing-timeframe momentum
    oscillator (vs. the long-term system's weekly RSI). Already bounded
    0-100 by construction (Wilder's smoothing), used directly with no
    further normalization, same as weekly RSI in indicators.py.

    Returns df with columns: date, daily_rsi
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    delta = df["price"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    df["daily_rsi"] = 100 - (100 / (1 + rs))
    return df[["date", "daily_rsi"]]


def compute_bollinger_pct_b(price_df: pd.DataFrame, window: int = 20, num_std: float = 2) -> pd.DataFrame:
    """
    Bollinger %B (20-day, 2 std dev) -- price's position within its
    recent volatility band: 0 = at the lower band, 100 = at the upper
    band, with excursions beyond during breakouts/breakdowns. A
    genuinely different SIGNAL TYPE than the other three (volatility-
    relative position, not trend distance or momentum), which is the
    point of including it -- diversifying what kind of extreme gets
    detected, same design principle as the long-term system's mix.

    Returns df with columns: date, price, bb_mid, bb_upper, bb_lower, pct_b
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    df["bb_mid"] = df["price"].rolling(window=window, min_periods=window).mean()
    std = df["price"].rolling(window=window, min_periods=window).std()
    df["bb_upper"] = df["bb_mid"] + num_std * std
    df["bb_lower"] = df["bb_mid"] - num_std * std
    df["pct_b"] = (df["price"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]) * 100
    return df[["date", "price", "bb_mid", "bb_upper", "bb_lower", "pct_b"]]


def normalize_pct_b(pct_b: pd.Series, clip_range: tuple = (-15, 115)) -> pd.Series:
    """
    Rescales Bollinger %B to a clean 0-100 scale. %B is already close to
    0-100 by construction, but clip bounds are set a bit wider than the
    nominal band (from the 2018-present ~1st/99th percentiles, -17.2 /
    +119.7) so genuine breakout/breakdown excursions still get graded
    rather than pinned flat at 0 or 100.
    """
    lo, hi = clip_range
    clipped = pct_b.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def compute_macd(price_df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Daily MACD histogram (12/26/9, the standard parameters), expressed as
    a % of price so it's comparable across BTC's price history rather
    than a raw USD figure.

    Note: like RSI/Bollinger/MA-distance in this file, this measures
    short-term trend/momentum -- in earlier testing (see README and the
    project conversation) that made it and its siblings trend-CONFIRMING
    rather than reversal-predicting in BTC's history at this timeframe.
    Included here as a technicals-based input by request, not as a
    separately validated signal.

    Returns df with columns: date, macd_line, macd_signal, macd_hist_pct
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    ema_fast = df["price"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["price"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - macd_signal

    df["macd_line"] = macd_line
    df["macd_signal"] = macd_signal
    df["macd_hist_pct"] = histogram / df["price"] * 100
    return df[["date", "macd_line", "macd_signal", "macd_hist_pct"]]


def normalize_macd(macd_hist_pct: pd.Series, clip_range: tuple = (-1.9, 1.83)) -> pd.Series:
    """
    Maps the MACD histogram (as % of price) to a 0-100 scale. Clip bounds
    from the 2018-present ~5th/95th percentiles.
    """
    lo, hi = clip_range
    clipped = macd_hist_pct.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def build_st_indicator_table(price_df: pd.DataFrame, fng_df: pd.DataFrame) -> pd.DataFrame:
    """
    Joins the short-term indicator set into one date-aligned table, each
    normalized to the shared 0-100 scale.

    Returns df with columns:
      date, price, ma50, pct_distance_50, ma50_score,
      fng_value, fng_short_smoothed, fng_st_score,
      daily_rsi, rsi_st_score,
      bb_mid, bb_upper, bb_lower, pct_b, bb_score,
      macd_line, macd_signal, macd_hist_pct, macd_score
    """
    ma_df = compute_ma50_distance(price_df)
    ma_df["ma50_score"] = normalize_ma50_distance(ma_df["pct_distance_50"])

    fng_short_df = compute_fng_short_smoothed(fng_df)
    fng_short_df["fng_st_score"] = fng_short_df["fng_short_smoothed"]  # already 0-100

    merged = pd.merge(ma_df, fng_short_df, on="date", how="inner")

    rsi_df = compute_daily_rsi(price_df)
    rsi_df["rsi_st_score"] = rsi_df["daily_rsi"]  # already 0-100
    merged = pd.merge(merged, rsi_df, on="date", how="inner")

    bb_df = compute_bollinger_pct_b(price_df)
    bb_df["bb_score"] = normalize_pct_b(bb_df["pct_b"])
    merged = pd.merge(merged, bb_df[["date", "bb_mid", "bb_upper", "bb_lower", "pct_b", "bb_score"]],
                       on="date", how="inner")

    macd_df = compute_macd(price_df)
    macd_df["macd_score"] = normalize_macd(macd_df["macd_hist_pct"])
    merged = pd.merge(merged, macd_df, on="date", how="inner")

    return merged


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()

    table = build_st_indicator_table(price_df, fng_df)
    print(table.tail(10))
    print(f"\n{len(table)} aligned rows, from {table['date'].min().date()} to {table['date'].max().date()}")
