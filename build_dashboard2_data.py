"""
build_dashboard2_data.py

Produces the JSON blob the "Short-Term Signal" artifact embeds as its
`DATA` object -- mirrors build_dashboard1_data.py's role, but for
st_backtest.py's symmetric buy/sell composite. The "series" here is
trimmed to the last 24 months (daily data, unlike dashboard 1's weekly),
matching what the artifact actually charts.

Run standalone to print the JSON to stdout, or import build_data() and
call it from build_dashboards.py.
"""

import json
import argparse
import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from st_indicators import build_st_indicator_table
from scoring import compute_composite_score, flag_zones, apply_confirmation, extract_zone_transitions, apply_signal_cooldown
from st_backtest import ST_DEFAULT_WEIGHTS
from st_current_status import DEFAULT_SELL_THRESHOLD, DEFAULT_BUY_THRESHOLD, DEFAULT_CONFIRM_DAYS, INDICATOR_LABELS

COOLDOWN_DAYS = 14
SERIES_MONTHS = 24


def build_data(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
               confirm_days: int = DEFAULT_CONFIRM_DAYS, cooldown_days: int = COOLDOWN_DAYS,
               force_refresh: bool = False) -> dict:
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    table = build_st_indicator_table(price_df, fng_df)

    scored = compute_composite_score(table, weights=ST_DEFAULT_WEIGHTS)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)

    confirmed_transitions = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    signals = apply_signal_cooldown(confirmed_transitions, min_gap_days=cooldown_days)

    latest = zoned.iloc[-1]
    zone_series = zoned["zone"]
    run_id = (zone_series != zone_series.shift(1)).cumsum()
    current_run_length = int((run_id == run_id.iloc[-1]).sum())

    years = (zoned["date"].max() - zoned["date"].min()).days / 365.25

    last_date = zoned["date"].max()
    cutoff = last_date - pd.DateOffset(months=SERIES_MONTHS)
    recent = zoned[zoned["date"] >= cutoff]

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
        "cooldown_days": cooldown_days,
        "indicators": [
            {"key": key, "label": label, "value": round(float(latest[key]), 1)}
            for key, label in INDICATOR_LABELS.items()
        ],
        "signals": [
            {
                "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                "price": round(float(row["price"]), 2),
                "composite": round(float(row["composite_score"]), 1),
                "zone": row["zone"],
            }
            for _, row in signals.iterrows()
        ],
        "years": round(years, 1),
        "per_year": round(len(signals) / years, 1) if years > 0 else 0,
        "series": [
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "price": round(float(row["price"]), 2),
                "composite": round(float(row["composite_score"]), 2),
                "zone": row["zone"],
                "daily_rsi": round(float(row["daily_rsi"]), 2) if pd.notna(row["daily_rsi"]) else None,
                "ma50": round(float(row["ma50"]), 2) if pd.notna(row["ma50"]) else None,
                "macd_line": round(float(row["macd_line"]), 2) if pd.notna(row["macd_line"]) else None,
                "macd_signal": round(float(row["macd_signal"]), 2) if pd.notna(row["macd_signal"]) else None,
            }
            for _, row in recent.iterrows()
        ],
    }
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/F&G data")
    args = parser.parse_args()

    print(json.dumps(build_data(force_refresh=args.refresh)))
