"""
backtest.py

A skeleton for sanity-checking the signal system against real BTC history
BEFORE trusting it. This is intentionally simple right now -- the goal at
this stage is just to answer two questions:

  1. Does this produce roughly 8-10 signals/year, or is it wildly off?
  2. Do the flagged buy/sell zones roughly line up with known cycle
     lows/highs (e.g. Dec 2018, Mar 2020, Nov 2021, Nov 2022), or not?

This is NOT yet a rigorous walk-forward backtest with out-of-sample
splits -- that's the next step once we've confirmed the basic mechanics
produce sane output. Don't use this version to make real decisions yet.
"""

import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from indicators import build_indicator_table
from scoring import compute_composite_score, flag_zones, apply_confirmation, extract_zone_transitions


# Known approximate cycle extremes, for a rough sanity check against
# what the signal system flags. Not exhaustive, just reference points.
KNOWN_CYCLE_POINTS = {
    "2018-12-15": "cycle low (~$3.2k)",
    "2019-06-26": "local high (~$13.8k)",
    "2020-03-12": "COVID crash low (~$4.9k)",
    "2021-04-14": "local high (~$64k)",
    "2021-11-10": "cycle high (~$69k)",
    "2022-11-21": "cycle low (~$15.5k)",
}


def run_basic_backtest(weights: dict = None, sell_threshold: float = 75, buy_threshold: float = 25,
                        min_confirm_days: int = 5):
    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()
    table = build_indicator_table(price_df, fng_df)

    scored = compute_composite_score(table, weights=weights)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=min_confirm_days)
    raw_transitions = extract_zone_transitions(zoned, zone_col="zone")
    transitions = extract_zone_transitions(zoned, zone_col="confirmed_zone")

    years = (zoned["date"].max() - zoned["date"].min()).days / 365.25
    signals_per_year = len(transitions) / years if years > 0 else 0

    print("=" * 60)
    print(f"BACKTEST: weights={weights}, sell>={sell_threshold}, buy<={buy_threshold}, "
          f"confirm>={min_confirm_days}d")
    print("=" * 60)
    print(f"Data range: {zoned['date'].min().date()} to {zoned['date'].max().date()} ({years:.1f} years)")
    print(f"Rows with valid composite score: {zoned['composite_score'].notna().sum()} / {len(zoned)}")
    print(f"Raw zone transitions (pre-confirmation): {len(raw_transitions)}")
    print(f"Confirmed zone transitions: {len(transitions)}  (~{signals_per_year:.1f}/year)")
    print()
    print("Confirmed signal transitions:")
    print(transitions.to_string(index=False))
    print()
    print("Reference: known cycle extremes")
    print("-" * 40)
    for date_str, label in KNOWN_CYCLE_POINTS.items():
        ref_date = pd.Timestamp(date_str)
        nearby = zoned[(zoned["date"] >= ref_date - pd.Timedelta(days=10)) &
                        (zoned["date"] <= ref_date + pd.Timedelta(days=10))]
        if nearby.empty:
            print(f"{date_str} ({label}): no data in range")
            continue
        avg_score = nearby["composite_score"].mean()
        print(f"{date_str} ({label}): composite score ~{avg_score:.1f}")

    return transitions, zoned


if __name__ == "__main__":
    # Run with the default equal weighting first, as a baseline.
    run_basic_backtest()
