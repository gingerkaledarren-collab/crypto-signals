"""
trim_signal.py

SUPERSEDED as dashboard 2's active driver by st_backtest.py's simpler,
symmetric buy/sell-zone concept (by request -- an explicit choice to
prioritize a practical, ~8-10x/year technicals-based tool over this
module's narrower, statistically-validated-but-rare one-directional
signal). Kept in the repo because it's real, out-of-sample-tested
research and the one rigorously validated construction found for this
timeframe -- see the README for the full comparison.

The original description, still accurate for what this module IS:
a validated, ONE-DIRECTIONAL trim/de-risk overlay combining the
long-term composite (indicators.py/scoring.py, unchanged -- dashboard 1
stays exactly as it was) with a Fear & Greed-heavy short-term composite
(st_indicators.py).

GENESIS -- what was tried and rejected before this:
  1. A standalone short-term momentum composite (50d MA distance, daily
     RSI, Bollinger %B, lightly-smoothed F&G) was tested as a contrarian
     buy/sell signal. It failed BACKWARDS: "overbought" readings preceded
     LARGER subsequent gains than "oversold" readings, at every horizon
     from 7 to 120 days, confirmed out-of-sample. Short-lookback
     technicals measure trend strength in BTC's history, not exhaustion.
  2. Gating that short-term composite by the long-term composite's state
     (hypothesis: short-term euphoria within a long-term downtrend is a
     bear-market-rally top) was tested next. The exact opposite quadrant
     turned out to matter: "long-term expensive but short-term momentum
     has gone quiet" was the one quadrant with a real, replicable
     negative forward return -- not "short-term spiking".
  3. A mirrored buy-side rule (long-term cheap AND short-term not
     capitulating) looked strong on TRAIN (+30.9pp) and completely
     INVERTED out-of-sample (-25.5pp, on a small n=57) -- a textbook
     overfitting signature. There is NO validated buy-side counterpart
     to this system. Don't add one without the same out-of-sample rigor.

THE RULE (this file): flag a 'trim_zone' day when the long-term composite
reads >= TRIM_LT_THRESHOLD (expensive-ish on the 4-year view) AND the
short-term composite reads < TRIM_ST_THRESHOLD (NOT in an active
melt-up). This targets "an expensive market whose rally has lost steam",
not "catch the spike as it happens" -- that direction failed testing.

VALIDATION (see trim_walkforward.py to reproduce): chronological
train/test split (train 2018-02 to 2023-08, test 2023-08 to 2026-08),
90-day forward return. At the thresholds used here (50/70): TRAIN spread
(rest return - trim-zone return) = +20.7pp, TEST spread = +8.6pp -- same
direction, confirmed blind. A stricter threshold (lt>=65) validates much
more strongly (TRAIN +33.8pp, TEST +23.0pp) but only fires ~1.6-1.8x/year;
50/70 was chosen to land in the requested 4-6x/year range, at the cost of
roughly half the effect size. That tradeoff is real and worth knowing,
not hidden: rarer extremes are more informative by nature.
"""

import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from indicators import build_indicator_table
from st_indicators import build_st_indicator_table
from scoring import compute_composite_score, apply_confirmation, extract_zone_transitions, apply_signal_cooldown

# Short-term composite weights for this system -- Fear & Greed weighted
# heavily per request. Tested against equal-weight and 40%-F&G versions:
# makes no material difference to validation strength or current status
# (the long-term side is the binding constraint either way), so this is
# a legitimate stylistic choice rather than one that changes the finding.
ST_WEIGHTS = {
    "ma50_score": 1 / 6,
    "fng_st_score": 0.5,
    "rsi_st_score": 1 / 6,
    "bb_score": 1 / 6,
}

TRIM_LT_THRESHOLD = 50
TRIM_ST_THRESHOLD = 70
TRIM_CONFIRM_DAYS = 3
TRIM_COOLDOWN_DAYS = 14
FORWARD_HORIZON_DAYS = 90  # the horizon this rule was validated against


def build_trim_table(price_df: pd.DataFrame = None, fng_df: pd.DataFrame = None,
                      lt_threshold: float = TRIM_LT_THRESHOLD, st_threshold: float = TRIM_ST_THRESHOLD) -> pd.DataFrame:
    """
    Builds the combined long-term + short-term table with the trim_zone
    flag applied.

    Returns df with columns: date, price, ma50_score, fng_st_score,
    rsi_st_score, bb_score, st_score, ma_200w_score, fng_score, rsi_score,
    pi_cycle_score, lt_score, composite_score (alias for st_score, needed
    by scoring.py's generic zone functions), zone
    """
    if price_df is None:
        price_df = fetch_btc_price_history()
    if fng_df is None:
        fng_df = fetch_fear_greed_history()

    lt_table = build_indicator_table(price_df, fng_df)
    lt_scored = compute_composite_score(lt_table).rename(columns={"composite_score": "lt_score"})

    st_table = build_st_indicator_table(price_df, fng_df)
    st_scored = compute_composite_score(st_table, weights=ST_WEIGHTS).rename(columns={"composite_score": "st_score"})

    merged = pd.merge(
        st_scored[["date", "price", "ma50_score", "fng_st_score", "rsi_st_score", "bb_score", "st_score"]],
        lt_scored[["date", "ma_200w_score", "fng_score", "rsi_score", "pi_cycle_score", "lt_score"]],
        on="date", how="inner",
    ).sort_values("date").reset_index(drop=True)

    merged["zone"] = "neutral"
    merged.loc[(merged["lt_score"] >= lt_threshold) & (merged["st_score"] < st_threshold), "zone"] = "trim_zone"

    # apply_confirmation()/extract_zone_transitions() are generic over any
    # 'zone' column and expect a 'composite_score' column for their output
    # -- point it at st_score (the faster-moving side), same pattern used
    # in st_backtest.py.
    merged["composite_score"] = merged["st_score"]
    return merged


def get_trim_signals(confirm_days: int = TRIM_CONFIRM_DAYS, cooldown_days: int = TRIM_COOLDOWN_DAYS,
                      lt_threshold: float = TRIM_LT_THRESHOLD, st_threshold: float = TRIM_ST_THRESHOLD):
    """
    Runs the full pipeline: build table -> confirm -> extract transitions
    -> cooldown filter.

    Returns (zoned_df, signals_df).
    """
    table = build_trim_table(lt_threshold=lt_threshold, st_threshold=st_threshold)
    zoned = apply_confirmation(table, min_days=confirm_days)
    confirmed = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    signals = apply_signal_cooldown(confirmed, min_gap_days=cooldown_days)
    return zoned, signals


if __name__ == "__main__":
    zoned, signals = get_trim_signals()
    years = (zoned["date"].max() - zoned["date"].min()).days / 365.25
    print(f"Trim signals: {len(signals)} over {years:.1f} years (~{len(signals) / years:.1f}/year)")
    print(f"Rule: long-term composite >= {TRIM_LT_THRESHOLD} AND short-term composite < {TRIM_ST_THRESHOLD}")
    print()
    print(signals.to_string(index=False))
    print()
    latest = zoned.iloc[-1]
    print(f"Current ({latest['date'].date()}): lt_score={latest['lt_score']:.1f}, st_score={latest['st_score']:.1f}, "
          f"zone={latest['zone']}")
