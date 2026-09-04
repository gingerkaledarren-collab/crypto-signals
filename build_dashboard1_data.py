"""
build_dashboard1_data.py

Produces the JSON blob the "Signal Dashboard" artifact embeds as its
`DATA` object. Split out from current_status.py's print_report() so the
same numbers that print_report shows on the CLI can also drive the
Artifact, without hand-copying values between the two.

Run standalone to print the JSON to stdout, or import build_data() and
call it from build_dashboards.py.
"""

import json
import argparse
import pandas as pd
from fetch_data import (fetch_btc_price_history, fetch_fear_greed_history,
                        fetch_supply_in_profit_history, fetch_mvrv_history)
from indicators import build_indicator_table, SUPPLY_LOSS_CLIP_RANGE, MVRV_CLIP_RANGE, compute_cycle_context, HALVING_DATES
from scoring import (compute_composite_score, flag_zones, apply_confirmation, extract_zone_transitions,
                     flag_extreme_zones, extract_extreme_periods,
                     EXTREME_LOW_THRESHOLD, EXTREME_HIGH_THRESHOLD)
from current_status import DEFAULT_SELL_THRESHOLD, DEFAULT_BUY_THRESHOLD, DEFAULT_CONFIRM_DAYS, INDICATOR_LABELS, LIVE_WEIGHTS


def build_data(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
               confirm_days: int = DEFAULT_CONFIRM_DAYS, force_refresh: bool = False, fng_window: int = 7) -> dict:
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    supply_df = fetch_supply_in_profit_history(force_refresh=force_refresh)
    mvrv_df = fetch_mvrv_history(force_refresh=force_refresh)
    table = build_indicator_table(price_df, fng_df, fng_window=fng_window, supply_profit_df=supply_df, mvrv_df=mvrv_df)

    scored = compute_composite_score(table, weights=LIVE_WEIGHTS)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)
    zoned = flag_extreme_zones(zoned)

    latest = zoned.iloc[-1]
    zone = zoned["zone"]
    run_id = (zone != zone.shift(1)).cumsum()
    current_run_length = int((run_id == run_id.iloc[-1]).sum())

    signals = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    extreme_periods = extract_extreme_periods(zoned)

    data = {
        "as_of": latest["date"].strftime("%Y-%m-%d"),
        "price": round(float(latest["price"]), 2),
        "composite": round(float(latest["composite_score"]), 1),
        "zone": latest["zone"],
        "confirmed_zone": latest["confirmed_zone"],
        "run_length": current_run_length,
        "sell_threshold": sell_threshold,
        "buy_threshold": buy_threshold,
        "confirm_days": confirm_days,
        "extreme_low_threshold": EXTREME_LOW_THRESHOLD,
        "extreme_high_threshold": EXTREME_HIGH_THRESHOLD,
        "current_extreme_zone": latest["extreme_zone"],
        "data_start": zoned["date"].min().strftime("%Y-%m-%d"),
        "supply_loss_clip_range": list(SUPPLY_LOSS_CLIP_RANGE),
        "mvrv_clip_range": list(MVRV_CLIP_RANGE),
        "cycle_context": compute_cycle_context(latest["date"].date()),
        "halving_dates": [d.isoformat() for d in HALVING_DATES],
        "indicators": {key: round(float(latest[key]), 1) for key in INDICATOR_LABELS},
        "ema_context": {
            "ema_21w": round(float(latest["ema_21w"]), 2),
            "ema_34w": round(float(latest["ema_34w"]), 2),
            "above_21w": bool(latest["price"] >= latest["ema_21w"]),
            "above_34w": bool(latest["price"] >= latest["ema_34w"]),
        },
        "signals": [
            {
                "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                "price": round(float(row["price"]), 2),
                "composite": round(float(row["composite_score"]), 1),
                "zone": row["zone"],
            }
            for _, row in signals.iterrows()
        ],
        "extreme_periods": [
            {
                "zone": row["zone"],
                "start_date": pd.Timestamp(row["start_date"]).strftime("%Y-%m-%d"),
                "end_date": pd.Timestamp(row["end_date"]).strftime("%Y-%m-%d"),
                "days": int(row["days"]),
                "min_composite": round(float(row["min_composite"]), 1),
                "max_composite": round(float(row["max_composite"]), 1),
                "start_price": round(float(row["start_price"]), 2),
                "end_price": round(float(row["end_price"]), 2),
            }
            for _, row in extreme_periods.iterrows()
        ],
        "series": _build_weekly_series(zoned),
    }
    return data


def _build_weekly_series(zoned: pd.DataFrame) -> list:
    """
    The chart series is deliberately down-sampled to one point/week (this
    is a 200-week-MA-driven system; daily granularity is 7x the points
    for no visual benefit and quintuples the page's embedded-data size).
    resample("W").last() takes each week's last available day, matching
    how compute_weekly_rsi()/compute_ema_structure() already label weekly
    bars by week-ending (Sunday) date.
    """
    weekly = zoned.set_index("date").resample("W").last().reset_index()

    def _val(row, col):
        return round(float(row[col]), 2) if pd.notna(row[col]) else None

    return [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "price": _val(row, "price"),
            "composite": round(float(row["composite_score"]), 1),
            "zone": row["zone"],
            "ema21": _val(row, "ema_21w"),
            "ema34": _val(row, "ema_34w"),
            "ma_200w": _val(row, "ma_200w"),
            "ma_200w_score": _val(row, "ma_200w_score"),
            "weekly_rsi": _val(row, "weekly_rsi"),
            "supply_in_loss_pct": _val(row, "supply_in_loss_pct"),
            "supply_loss_score": _val(row, "supply_loss_score"),
            "mvrv_ratio": _val(row, "mvrv_ratio"),
            "mvrv_score": _val(row, "mvrv_score"),
        }
        for _, row in weekly.iterrows()
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/F&G data")
    args = parser.parse_args()

    print(json.dumps(build_data(force_refresh=args.refresh)))
