"""
current_status.py

A practical "where do things stand today" report -- the piece that was
missing so far: everything else answers "does this system work on
history," this answers "what does it say right now."

LIVE_WEIGHTS (by explicit request) removes Pi Cycle Top and adds Bitcoin
Supply in Loss % and MVRV Ratio in its place -- see README's "Removing
Pi Cycle Top, adding Supply in Loss %" and "Adding MVRV Ratio despite
its short history" for the full walk-forward comparisons. Reported
honestly: none of these changes held up under this project's own
methodology (see those README sections for the numbers). It's live
anyway, by request, the same way Dashboard 2 already ships a
technicals-based composite that isn't separately validated -- just
don't mistake the buy/sell zone calls below for something this
project's own methodology found to work.

Several weight rebalances were tried by explicit request (200w MA 5% /
F&G 30% / RSI 30% / Supply in Loss 30% / MVRV 5%; 20/35/20/20/5;
20/30/20/20/10) -- every one of them FAILED the TRAIN walk-forward sweep
outright (not one config came back with a positive spread), so all were
reverted. See README's "Weight-rebalancing experiments" for the full
comparison table.

scoring.DEFAULT_WEIGHTS (the original, Pi-Cycle-based composite) is left
untouched for backtest.py / trim_signal.py / portfolio_simulation.py /
trim_walkforward.py, which document and depend on it specifically --
only this file and the dashboard it feeds use LIVE_WEIGHTS.

MVRV RATIO WAS DROPPED FROM THE COMPOSITE ENTIRELY, by explicit request,
after being flagged (with a chart) as having a structurally declining
cycle-top ceiling across BTC's history (~7 in 2013, ~5 in 2017, ~4 in
2021, ~2.6-2.7 this cycle per BGeometrics) -- the same "an indicator's
own amplitude decays as the market matures" dynamic that got Pi Cycle
Top removed earlier. indicators.MVRV_CLIP_RANGE's upper bound (2.5) is
calibrated only off BGeometrics' free ~4-year window (exactly ONE cycle
top), so it would progressively understate real danger at future tops if
the decline continues -- and no amount of downweighting MVRV (tried down
to 5% and 10%) fixed the composite's failing TRAIN sweep. Dropping it
outright, leaving the other four equal-weighted at 25% each, tested
BETTER than every weighted variant including the original equal-20%-
across-5 baseline on both TRAIN (+1.9pp vs +1.7pp) and TEST (-2.9pp vs
-4.1pp) -- see README's "MVRV's declining ceiling" for the full
reasoning. MVRV Ratio is still fetched and still shown on the dashboard
as a standalone, context-only chart (same treatment as the 21w/34w EMA
lines) -- visible, not scored.

Thresholds (sell=55, buy=45, confirm=5d) are the TRAIN-selected best for
the current 4-indicator equal-weighted LIVE_WEIGHTS (re-verified against
the current data pipeline -- fng_window=7 -- not inherited from an
earlier, now-stale 60/40/5d that predates the Supply-in-Loss/MVRV
additions).

Zones are FIVE-tier (extreme_buy/buy_zone/neutral/sell_zone/
extreme_sell), by request, not the original three-tier buy/sell/neutral
-- see scoring.flag_five_zones() for the mechanics and the honest
forward-return check on whether the extra tiers are actually meaningful
(buy-side split holds up, sell-side split is inconsistent between TRAIN
and TEST).

scoring.EXTREME_HIGH_THRESHOLD was recalibrated from 70 to 80, by
request, after being caught drifting: it was calibrated years ago against
a composite that no longer exists in this form (Pi Cycle removed, MVRV
added then dropped, weights rebalanced then reverted), and had quietly
grown to capture the top ~22% of readings instead of its own stated
~10% "rarest readings" intent. 80 restores that intent (~11% of days)
and, as a side effect, makes the extreme band symmetric with
EXTREME_LOW_THRESHOLD (20/80, both 20 points from their respective
edges) -- see scoring.py's own comment for the full numbers.
"""

import argparse
import pandas as pd
from fetch_data import (fetch_btc_price_history, fetch_fear_greed_history,
                        fetch_supply_in_profit_history, fetch_mvrv_history)
from indicators import build_indicator_table
from scoring import (compute_composite_score, flag_five_zones, apply_confirmation, extract_zone_transitions,
                     flag_extreme_zones, extract_extreme_periods,
                     EXTREME_LOW_THRESHOLD, EXTREME_HIGH_THRESHOLD)

DEFAULT_SELL_THRESHOLD = 55
DEFAULT_BUY_THRESHOLD = 45
DEFAULT_CONFIRM_DAYS = 5
# build_indicator_table()'s own default is 30d -- this file previously
# never overrode it, so the CLI silently ran 30d-smoothed F&G while
# build_dashboard1_data.py (which does pass fng_window=7) ran the 7d
# experimental variant the dashboard actually ships. Fixed by passing the
# same 7 here, so current_status.py and the dashboard can't silently
# disagree about the live signal on any given day.
DEFAULT_FNG_WINDOW = 7

# The live composite: 200w MA distance, Fear & Greed, weekly RSI, and
# Bitcoin Supply in Loss %, equal-weighted -- Pi Cycle Top removed by
# request; several weight rebalances were tried and reverted; MVRV Ratio
# was tried, then dropped entirely (see module docstring above for all
# three). See the module docstring for the walk-forward results.
LIVE_WEIGHTS = {
    "ma_200w_score": 0.25,
    "fng_score": 0.25,
    "rsi_score": 0.25,
    "supply_loss_score": 0.25,
}

INDICATOR_LABELS = {
    "ma_200w_score": "200-week MA distance",
    "fng_score": "Fear & Greed (30d smoothed)",
    "rsi_score": "Weekly RSI",
    "supply_loss_score": "Bitcoin Supply in Loss (%)",
}

# Not in the default composite (see scoring.py) -- shown separately as
# context, Rastani-style: is price currently holding its 21w/34w EMA
# support structure. Informational only, doesn't feed the zone call.


def get_current_status(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                        confirm_days: int = DEFAULT_CONFIRM_DAYS, force_refresh: bool = False,
                        fng_window: int = DEFAULT_FNG_WINDOW):
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    supply_df = fetch_supply_in_profit_history(force_refresh=force_refresh)
    mvrv_df = fetch_mvrv_history(force_refresh=force_refresh)
    table = build_indicator_table(price_df, fng_df, fng_window=fng_window, supply_profit_df=supply_df, mvrv_df=mvrv_df)

    scored = compute_composite_score(table, weights=LIVE_WEIGHTS)
    zoned = flag_five_zones(scored, buy_threshold=buy_threshold, sell_threshold=sell_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)
    zoned = flag_extreme_zones(zoned)

    latest = zoned.iloc[-1]
    history = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    extreme_periods = extract_extreme_periods(zoned)

    return latest, zoned, history, extreme_periods


def print_report(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                  confirm_days: int = DEFAULT_CONFIRM_DAYS, force_refresh: bool = False,
                  fng_window: int = DEFAULT_FNG_WINDOW):
    latest, zoned, history, extreme_periods = get_current_status(sell_threshold, buy_threshold, confirm_days,
                                                                   force_refresh, fng_window)

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

    ema_side = "above" if latest["price"] >= latest["ema_21w"] else "below"
    slow_side = "above" if latest["price"] >= latest["ema_34w"] else "below"
    print(f"EMA structure (context only, not in composite): price is {ema_side} the 21w EMA "
          f"(${latest['ema_21w']:,.0f}) and {slow_side} the 34w EMA (${latest['ema_34w']:,.0f})")
    print()

    if len(history) > 0:
        print("Last 3 confirmed signals:")
        print(history.tail(3).to_string(index=False))
    else:
        print("No confirmed signals in this history yet.")
    print()

    extreme_labels = {"extreme_low": "extreme low (bottom decile)", "extreme_high": "extreme high (top decile)"}
    extreme_status = extreme_labels.get(latest["extreme_zone"], "not currently in one")
    print(f"Extreme reading (score <= {EXTREME_LOW_THRESHOLD} or >= {EXTREME_HIGH_THRESHOLD}, "
          f"~10% rarest readings historically -- a statistical fact about the composite, not a")
    print(f"fear/greed sentiment claim): {extreme_status}")
    if len(extreme_periods) > 0:
        print(f"{len(extreme_periods)} such episodes since {zoned['date'].min().date()}. Last 3:")
        print(extreme_periods.tail(3).to_string(index=False))
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
