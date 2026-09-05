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

    Renormalizes per ROW over whichever weighted columns are non-null
    that day, rather than requiring all of them present. This matters
    now that LIVE_WEIGHTS includes mvrv_score, whose source data only
    starts ~Sept 2022 (see indicators.build_indicator_table()) -- without
    this, every earlier row's composite_score would go NaN just because
    one of five inputs wasn't available yet, rather than being computed
    from the other four. A no-op for any table where every weighted
    column is fully populated (the common case), since row_weight_sum
    then always equals total_weight.

    Returns the input df with an added 'composite_score' column.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    df = table.copy()
    cols = list(weights.keys())
    w = pd.Series(weights, dtype=float)

    values = df[cols]
    available = values.notna()
    row_weight_sum = available.mul(w, axis=1).sum(axis=1)
    weighted_sum = values.fillna(0).mul(w, axis=1).sum(axis=1)

    df["composite_score"] = weighted_sum / row_weight_sum
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


EXTREME_LOW_THRESHOLD = 20
EXTREME_HIGH_THRESHOLD = 70
# Derived from the actual historical distribution of composite_score
# (2018-present), not guessed: those scores sit almost exactly at the
# 10th and 90th percentiles of the full history (~22 and ~69), rounded
# to clean numbers. This is deliberately a stricter, rarer band than the
# 40/60 buy_zone/sell_zone thresholds used elsewhere (those were chosen
# for walk-forward predictive value, not for marking rarity) -- "extreme"
# here means "in the most unusual ~10% of readings," a plain historical
# fact about the score rather than a claim about what to do next.
#
# Deliberately NOT called "extreme_fear"/"extreme_greed": the composite
# blends 200w MA distance (valuation), Fear & Greed (sentiment), weekly
# RSI (momentum), and Pi Cycle Top ratio (a price-ratio cycle-top signal)
# -- only one of those four is literally sentiment. Labeling the whole
# composite's tails "fear"/"greed" would borrow an emotional claim that's
# only true for a quarter of what feeds it. "extreme_low"/"extreme_high"
# describes what this actually is: a percentile fact about the score.


def flag_extreme_zones(df: pd.DataFrame, extreme_low_threshold: float = EXTREME_LOW_THRESHOLD,
                        extreme_high_threshold: float = EXTREME_HIGH_THRESHOLD) -> pd.DataFrame:
    """
    Flags each row 'extreme_low', 'extreme_high', or 'normal' based on
    how rare that composite_score reading has historically been -- see
    EXTREME_LOW_THRESHOLD/EXTREME_HIGH_THRESHOLD above for how these
    were derived, and why they're not named after fear/greed. Independent
    of flag_zones()/apply_confirmation(): no confirmation delay is applied
    here, since sitting in the most extreme ~10% of readings is itself a
    rare, meaningful event.

    Returns the input df with an added 'extreme_zone' column.
    """
    df = df.copy()
    df["extreme_zone"] = "normal"
    df.loc[df["composite_score"] <= extreme_low_threshold, "extreme_zone"] = "extreme_low"
    df.loc[df["composite_score"] >= extreme_high_threshold, "extreme_zone"] = "extreme_high"
    return df


def flag_five_zones(df: pd.DataFrame, extreme_buy_threshold: float = EXTREME_LOW_THRESHOLD,
                     buy_threshold: float = 45, sell_threshold: float = 55,
                     extreme_sell_threshold: float = EXTREME_HIGH_THRESHOLD) -> pd.DataFrame:
    """
    A finer-grained sibling to flag_zones(): splits buy_zone/sell_zone
    each into two tiers (extreme_buy/buy_zone, sell_zone/extreme_sell),
    by request. Reuses EXTREME_LOW_THRESHOLD/EXTREME_HIGH_THRESHOLD --
    the same percentile bounds flag_extreme_zones() uses for its separate
    "how rare is this reading" stat above -- as the outer cutoffs, so
    there's one definition of "extreme" in this codebase, not two
    independently calibrated ones.

    Unlike flag_extreme_zones(), this feeds apply_confirmation() the same
    way flag_zones() does (both are generic over the zone column's value
    set, so neither needed changes) -- these tiers gate the same buy/sell
    decision flag_zones() gates, just with an extra "how strongly"
    gradient, not a separate rarity callout.

    Checked against forward returns on the LIVE (equal-weight) composite,
    split TRAIN/TEST like everywhere else in this project: the buy-side
    split holds up (extreme_buy shows stronger subsequent returns than
    buy_zone alone, in both TRAIN and TEST). The sell-side split does
    NOT -- extreme_sell vs sell_zone flips order between TRAIN and TEST,
    and the extreme_buy sample in TEST is thin (n=20). Treat "Extreme
    Sell" as a finer label on an already-validated sell signal, not as a
    separately-proven stronger one -- see README's "Five-tier zones
    (Extreme Buy/Buy/Neutral/Sell/Extreme Sell)".

    Returns the input df with an added 'zone' column: one of
    extreme_buy, buy_zone, neutral, sell_zone, extreme_sell.
    """
    df = df.copy()
    df["zone"] = "neutral"
    df.loc[df["composite_score"] <= buy_threshold, "zone"] = "buy_zone"
    df.loc[df["composite_score"] <= extreme_buy_threshold, "zone"] = "extreme_buy"
    df.loc[df["composite_score"] >= sell_threshold, "zone"] = "sell_zone"
    df.loc[df["composite_score"] >= extreme_sell_threshold, "zone"] = "extreme_sell"
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


def apply_signal_cooldown(transitions: pd.DataFrame, min_gap_days: int = 21) -> pd.DataFrame:
    """
    Collapses same-zone signals that re-trigger within `min_gap_days` of
    the last KEPT signal of that same zone into a single episode --
    without this, a signal that dips out of confirmation for a few days
    (e.g. a brief pullback within an otherwise sustained sell-off) and
    then re-confirms gets counted as a second, independent repositioning
    decision, inflating the signals/year headline. A flip to the OPPOSITE
    zone is always kept regardless of gap -- that's a genuine pivot, not
    a re-trigger of the same call.

    Apply this to the output of extract_zone_transitions(). Generic over
    any zone labels (buy_zone/sell_zone, or others), not specific to
    either the long-term or short-term indicator sets.

    Returns a filtered copy of the transitions df.
    """
    transitions = transitions.copy().sort_values("date").reset_index(drop=True)
    keep = []
    last_kept_date = {}
    for _, row in transitions.iterrows():
        zone = row["zone"]
        prev_date = last_kept_date.get(zone)
        if prev_date is None or (row["date"] - prev_date).days >= min_gap_days:
            keep.append(True)
            last_kept_date[zone] = row["date"]
        else:
            keep.append(False)
    return transitions[keep].reset_index(drop=True)


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
