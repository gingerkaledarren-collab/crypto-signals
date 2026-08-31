"""
st_current_status.py

"Where does the short-term signal stand today" -- mirrors current_status.py's
role for the long-term system, but for st_backtest.py's symmetric buy/sell
composite.
"""

import argparse
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from st_indicators import build_st_indicator_table
from scoring import compute_composite_score, flag_zones, apply_confirmation, extract_zone_transitions
from st_backtest import ST_DEFAULT_WEIGHTS

DEFAULT_SELL_THRESHOLD = 70
DEFAULT_BUY_THRESHOLD = 30
DEFAULT_CONFIRM_DAYS = 3

INDICATOR_LABELS = {
    "ma50_score": "50-day MA distance",
    "fng_st_score": "Fear & Greed (5d smoothed)",
    "rsi_st_score": "Daily RSI(14)",
    "bb_score": "Bollinger %B (20d)",
    "macd_score": "MACD histogram (12/26/9)",
}


def print_report(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                  confirm_days: int = DEFAULT_CONFIRM_DAYS, force_refresh: bool = False):
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    table = build_st_indicator_table(price_df, fng_df)

    scored = compute_composite_score(table, weights=ST_DEFAULT_WEIGHTS)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)

    latest = zoned.iloc[-1]
    zone = zoned["zone"]
    run_id = (zone != zone.shift(1)).cumsum()
    current_run_length = int((run_id == run_id.iloc[-1]).sum())

    history = extract_zone_transitions(zoned, zone_col="confirmed_zone")

    print("=" * 60)
    print(f"SHORT-TERM STATUS -- as of {latest['date'].date()}")
    print("=" * 60)
    print(f"BTC price: ${latest['price']:,.0f}")
    print()
    print("Indicator breakdown (0 = oversold/undervalued, 100 = overbought/overvalued):")
    for col, label in INDICATOR_LABELS.items():
        print(f"  {label:<28} {latest[col]:5.1f}")
    print(f"  {'Composite score':<28} {latest['composite_score']:5.1f}")
    print()
    print(f"Thresholds: sell >= {sell_threshold}, buy <= {buy_threshold}, confirm after {confirm_days} days")
    print(f"Raw zone today: {latest['zone']}  (day {current_run_length} of this run)")
    print(f"Confirmed zone: {latest['confirmed_zone']}")
    print()

    if len(history) > 0:
        print("Last 5 signals:")
        print(history.tail(5).to_string(index=False))
    else:
        print("No confirmed signals in this history yet.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sell", type=float, default=DEFAULT_SELL_THRESHOLD)
    parser.add_argument("--buy", type=float, default=DEFAULT_BUY_THRESHOLD)
    parser.add_argument("--confirm-days", type=int, default=DEFAULT_CONFIRM_DAYS)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    print_report(sell_threshold=args.sell, buy_threshold=args.buy,
                 confirm_days=args.confirm_days, force_refresh=args.refresh)
