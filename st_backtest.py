"""
st_backtest.py

The SHORT-TERM signal system (st_indicators.py): a symmetric buy/sell-zone
composite tuned for a faster, ~8-10x/year repositioning cadence -- a
technicals-based tool (moving average distance, RSI, Bollinger %B, MACD,
Fear & Greed), not a separately statistically validated one like the
long-term system in indicators.py/scoring.py. Reuses scoring.py's
flag_zones/apply_confirmation/extract_zone_transitions/apply_signal_cooldown
directly -- those are generic over any 'composite_score' column.

Note on the momentum indicators (MA distance, RSI, Bollinger %B, MACD):
earlier testing in this project (see README) found that at this
short lookback, they behave as trend-CONFIRMING signals in BTC's history
rather than reversal-predicting ones -- "overbought" tended to precede
further gains, not drops. This system is built anyway, by request, as a
practical/technicals-based tool rather than a claim that it's been shown
to beat the market; the frequency and thresholds below are chosen to hit
the requested cadence, not to maximize a validated edge.
"""

import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from st_indicators import build_st_indicator_table
from scoring import (compute_composite_score, flag_zones, apply_confirmation, extract_zone_transitions,
                     apply_signal_cooldown)

ST_DEFAULT_WEIGHTS = {
    "ma50_score": 0.175,
    "fng_st_score": 0.30,
    "rsi_st_score": 0.175,
    "bb_score": 0.175,
    "macd_score": 0.175,
}


def run_st_backtest(weights: dict = None, sell_threshold: float = 70, buy_threshold: float = 30,
                     min_confirm_days: int = 3, cooldown_days: int = 14):
    if weights is None:
        weights = ST_DEFAULT_WEIGHTS

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()
    table = build_st_indicator_table(price_df, fng_df)

    scored = compute_composite_score(table, weights=weights)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=min_confirm_days)
    raw_transitions = extract_zone_transitions(zoned, zone_col="zone")
    confirmed_transitions = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    transitions = apply_signal_cooldown(confirmed_transitions, min_gap_days=cooldown_days)

    years = (zoned["date"].max() - zoned["date"].min()).days / 365.25
    signals_per_year = len(transitions) / years if years > 0 else 0

    print("=" * 60)
    print(f"SHORT-TERM BACKTEST: sell>={sell_threshold}, buy<={buy_threshold}, "
          f"confirm>={min_confirm_days}d, cooldown>={cooldown_days}d")
    print("=" * 60)
    print(f"Data range: {zoned['date'].min().date()} to {zoned['date'].max().date()} ({years:.1f} years)")
    print(f"Raw zone transitions (pre-confirmation): {len(raw_transitions)}")
    print(f"Confirmed transitions (pre-cooldown): {len(confirmed_transitions)}")
    print(f"After cooldown filter: {len(transitions)}  (~{signals_per_year:.1f}/year)")
    print()
    print("Signal transitions:")
    print(transitions.to_string(index=False))

    return transitions, zoned


if __name__ == "__main__":
    run_st_backtest()
