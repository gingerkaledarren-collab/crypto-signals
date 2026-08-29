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
    "ma_200w_score": 0.25,
    "fng_score": 0.25,
    "rsi_score": 0.25,
    "pi_cycle_score": 0.25,
}
# ema_structure_score (21w/34w EMA, see indicators.py) is deliberately NOT
# in the default weighting -- the walk-forward re-test with it included
# dropped the buy/sell forward-return spread from +10.3pp to +0.9pp on
# TRAIN and flipped buy-zone out-of-sample returns negative. It's a
# trend-FOLLOWING signal (reads high mid-trend), which conflicts with the
# other four, all extremes/mean-reversion flavored. Computed and exposed
# for experimentation (pass a custom weights dict to try it), but not
# part of the validated default. See README.


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


def apply_confirmation(df: pd.DataFrame, min_days: int = 5) -> pd.DataFrame:
    """
    Requires the raw zone to hold for `min_days` CONSECUTIVE days before
    treating it as a real signal. The threshold sweep in the backtest
    showed loosening thresholds mostly added whipsaw (the score flickering
    back across the boundary within a few days) rather than genuinely new
    signals -- this filters that out without touching the thresholds.

    Days that haven't held long enough are downgraded to 'neutral' in the
    new 'confirmed_zone' column; once a run reaches min_days it stays
    confirmed for the rest of that run.

    Returns the input df with an added 'confirmed_zone' column.
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    zone = df["zone"]

    run_id = (zone != zone.shift(1)).cumsum()
    run_length = zone.groupby(run_id).cumcount() + 1

    confirmed = zone.copy()
    confirmed[(zone != "neutral") & (run_length < min_days)] = "neutral"
    df["confirmed_zone"] = confirmed
    return df


EXTREME_FEAR_THRESHOLD = 20
EXTREME_GREED_THRESHOLD = 70
# Derived from the actual historical distribution of composite_score
# (2018-present), not guessed: those scores sit almost exactly at the
# 10th and 90th percentiles of the full history (~22 and ~69), rounded
# to clean numbers. This is deliberately a stricter, rarer band than the
# 40/60 buy_zone/sell_zone thresholds used elsewhere (those were chosen
# for walk-forward predictive value, not for marking rarity) -- "extreme"
# here means "in the most unusual ~10% of readings," a plain historical
# fact about the score rather than a claim about what to do next.


def flag_extreme_zones(df: pd.DataFrame, extreme_fear_threshold: float = EXTREME_FEAR_THRESHOLD,
                        extreme_greed_threshold: float = EXTREME_GREED_THRESHOLD) -> pd.DataFrame:
    """
    Flags each row 'extreme_fear', 'extreme_greed', or 'normal' based on
    how rare that composite_score reading has historically been -- see
    EXTREME_FEAR_THRESHOLD/EXTREME_GREED_THRESHOLD above for how these
    were derived. Independent of flag_zones()/apply_confirmation(): no
    confirmation delay is applied here, since sitting in the most extreme
    ~10% of readings is itself a rare, meaningful event.

    Returns the input df with an added 'extreme_zone' column.
    """
    df = df.copy()
    df["extreme_zone"] = "normal"
    df.loc[df["composite_score"] <= extreme_fear_threshold, "extreme_zone"] = "extreme_fear"
    df.loc[df["composite_score"] >= extreme_greed_threshold, "extreme_zone"] = "extreme_greed"
    return df


def extract_extreme_periods(df: pd.DataFrame) -> pd.DataFrame:
    """
    Groups consecutive days in the same extreme_zone into date ranges --
    "every day the signal was in an extreme zone" is more useful read as
    contiguous episodes (when did it start, how long did it last, what
    did price do) than as a list of hundreds of individual daily rows.

    Returns a df with columns: zone, start_date, end_date, days,
    min_composite, max_composite, start_price, end_price
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    run_id = (df["extreme_zone"] != df["extreme_zone"].shift(1)).cumsum()

    periods = []
    for _, group in df.groupby(run_id):
        zone = group["extreme_zone"].iloc[0]
        if zone == "normal":
            continue
        periods.append({
            "zone": zone,
            "start_date": group["date"].iloc[0],
            "end_date": group["date"].iloc[-1],
            "days": len(group),
            "min_composite": group["composite_score"].min(),
            "max_composite": group["composite_score"].max(),
            "start_price": group["price"].iloc[0],
            "end_price": group["price"].iloc[-1],
        })
    return pd.DataFrame(periods)


def extract_zone_transitions(df: pd.DataFrame, zone_col: str = "zone") -> pd.DataFrame:
    """
    Reduces the daily zone series down to just the transition POINTS
    (i.e. the moment a zone starts), which is what you'd actually act on --
    not every day you're sitting inside a zone.

    Pass zone_col="confirmed_zone" (after apply_confirmation) to count only
    signals that held for the required number of days, filtering whipsaw.

    Returns a df of just the rows where the zone changed from the
    previous day, which is the realistic count of "signals per year".
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    changed = df[zone_col] != df[zone_col].shift(1)
    transitions = df[changed & (df[zone_col] != "neutral")]
    return transitions[["date", "price", "composite_score", zone_col]].rename(columns={zone_col: "zone"})


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
