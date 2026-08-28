"""
scoring.py

Combines individual 0-100 indicator scores into a single composite score,
and flags buy/sell zones based on threshold + agreement rules.

Weighting is deliberately left as an explicit, adjustable input rather
than hardcoded -- you said you want to decide weighting AFTER seeing
backtest results, so this is built to make that easy to experiment with.
"""

import pandas as pd


DEFAULT_WEIGHTS = {
    "ma_200w_score": 0.5,
    "fng_score": 0.5,
}


def compute_composite_score(table: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    Computes a weighted composite score from the indicator columns.

    weights: dict mapping column name -> weight. Weights are normalized
    to sum to 1 automatically, so you can pass e.g. {"ma_200w_score": 2,
    "fng_score": 1} for a 2:1 ratio without doing the math yourself.

    Returns the input df with an added 'composite_score' column.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    total_weight = sum(weights.values())
    normalized_weights = {k: v / total_weight for k, v in weights.items()}

    df = table.copy()
    df["composite_score"] = sum(
        df[col] * w for col, w in normalized_weights.items()
    )
    return df


def flag_zones(df: pd.DataFrame, sell_threshold: float = 75, buy_threshold: float = 25) -> pd.DataFrame:
    """
    Flags each row as 'sell_zone', 'buy_zone', or 'neutral' based on
    the composite score crossing the given thresholds.

    These thresholds are starting assumptions, not calibrated values --
    the backtest is what tells you whether 75/25 actually produces
    ~8-10 signals/year or something wildly different for BTC's history.
    """
    df = df.copy()
    df["zone"] = "neutral"
    df.loc[df["composite_score"] >= sell_threshold, "zone"] = "sell_zone"
    df.loc[df["composite_score"] <= buy_threshold, "zone"] = "buy_zone"
    return df


def extract_zone_transitions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reduces the daily zone series down to just the transition POINTS
    (i.e. the moment a zone starts), which is what you'd actually act on --
    not every day you're sitting inside a zone.

    Returns a df of just the rows where the zone changed from the
    previous day, which is the realistic count of "signals per year".
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    df["zone_changed"] = df["zone"] != df["zone"].shift(1)
    transitions = df[df["zone_changed"] & (df["zone"] != "neutral")]
    return transitions[["date", "price", "composite_score", "zone"]]


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
    from indicators import build_indicator_table

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()
    table = build_indicator_table(price_df, fng_df)

    scored = compute_composite_score(table)
    zoned = flag_zones(scored)
    transitions = extract_zone_transitions(zoned)

    print(f"Total signal transitions across full history: {len(transitions)}")
    print(f"Date range: {zoned['date'].min().date()} to {zoned['date'].max().date()}")
    years = (zoned["date"].max() - zoned["date"].min()).days / 365.25
    print(f"That's ~{len(transitions) / years:.1f} signals/year on average\n")
    print(transitions.to_string(index=False))
