"""
current_status.py

A practical "where do things stand today" report -- the piece that was
missing so far: everything else answers "does this system work on
history," this answers "what does it say right now."

Uses the config walkforward.py selected on TRAIN data (sell=60, buy=40,
confirm=5d) as the default, since it's the most rigorously chosen config
so far. Override via the CLI flags below if you want to try another.
"""

import argparse
import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from indicators import build_indicator_table
from scoring import compute_composite_score, flag_zones, apply_confirmation, extract_zone_transitions

# Walk-forward-selected config (see walkforward.py / README) -- the most
# validated starting point so far, not a guarantee it's optimal going forward.
DEFAULT_SELL_THRESHOLD = 60
DEFAULT_BUY_THRESHOLD = 40
DEFAULT_CONFIRM_DAYS = 5

INDICATOR_LABELS = {
    "ma_200w_score": "200-week MA distance",
    "fng_score": "Fear & Greed (30d smoothed)",
    "rsi_score": "Weekly RSI",
    "pi_cycle_score": "Pi Cycle Top ratio",
}


def get_current_status(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                        confirm_days: int = DEFAULT_CONFIRM_DAYS, force_refresh: bool = False):
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    table = build_indicator_table(price_df, fng_df)

    scored = compute_composite_score(table)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)

    latest = zoned.iloc[-1]
    history = extract_zone_transitions(zoned, zone_col="confirmed_zone")

    return latest, zoned, history


def print_report(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                  confirm_days: int = DEFAULT_CONFIRM_DAYS, force_refresh: bool = False):
    latest, zoned, history = get_current_status(sell_threshold, buy_threshold, confirm_days, force_refresh)

    # How many consecutive days the CURRENT raw zone has held, to show
    # progress toward (or past) the confirm_days requirement.
    zone = zoned["zone"]
    run_id = (zone != zone.shift(1)).cumsum()
    current_run_length = int((run_id == run_id.iloc[-1]).sum())

    print("=" * 60)
    print(f"CURRENT STATUS -- as of {latest['date'].date()}")
    print("=" * 60)
    print(f"BTC price: ${latest['price']:,.0f}")
    print()
    print("Indicator breakdown (0 = extreme fear/undervalued, 100 = extreme greed/overvalued):")
    for col, label in INDICATOR_LABELS.items():
        print(f"  {label:<32} {latest[col]:5.1f}")
    print(f"  {'Composite score':<32} {latest['composite_score']:5.1f}")
    print()
    print(f"Thresholds in use: sell >= {sell_threshold}, buy <= {buy_threshold}, "
          f"confirm after {confirm_days} consecutive days")
    print(f"Raw zone today: {latest['zone']}  (day {current_run_length} of this run)")
    print(f"Confirmed zone: {latest['confirmed_zone']}"
          + ("" if latest['confirmed_zone'] == "neutral" or current_run_length >= confirm_days
             else f"  (needs {confirm_days - current_run_length} more day(s) to confirm)"))
    print()

    if len(history) > 0:
        print("Last 3 confirmed signals:")
        print(history.tail(3).to_string(index=False))
    else:
        print("No confirmed signals in this history yet.")
    print()
    print("NOTE: per the walk-forward test (see README), treat this as a")
    print("risk-reduction/trim signal at genuine extremes, not a standalone")
    print("return-maximizer -- 'neutral' periods have historically included")
    print("some of the best returns to just be holding through.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sell", type=float, default=DEFAULT_SELL_THRESHOLD, help="sell zone threshold")
    parser.add_argument("--buy", type=float, default=DEFAULT_BUY_THRESHOLD, help="buy zone threshold")
    parser.add_argument("--confirm-days", type=int, default=DEFAULT_CONFIRM_DAYS, help="confirmation days")
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/F&G data")
    args = parser.parse_args()

    print_report(sell_threshold=args.sell, buy_threshold=args.buy,
                 confirm_days=args.confirm_days, force_refresh=args.refresh)
