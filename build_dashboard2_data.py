"""
build_dashboard2_data.py

Produces the JSON blob the "Short-Term Signal" artifact embeds as its
`DATA` object -- mirrors build_dashboard1_data.py's role, but for
st_backtest.py's symmetric buy/sell composite. The "series" here is
trimmed to the last 24 months (daily data, unlike dashboard 1's weekly),
matching what the artifact actually charts.

Five-tier zones (extreme_buy/buy_zone/neutral/sell_zone/extreme_sell), by
request, mirroring dashboard 1's flag_five_zones() -- added after noticing
the plain 3-zone version spends ~72% of days in "neutral" (30-70) even
though the composite legitimately swings from single digits to the high
90s. Checked directly: at real local price peaks (10-day window), the
composite's own median reading is only ~64 -- already inside "neutral" --
and 69% of real peaks never even cross the sell_threshold (70); the
literal Oct 2025 all-time high ($124,777) scored 69.5, a hair under sell.
So the wide neutral band isn't a display-only problem, it's already
swallowing most real turning points; adding extreme_buy/extreme_sell
OUTSIDE the existing 30/70 doesn't fix that, it only adds a rarer, louder
tier for genuine blow-off/capitulation days -- reusing scoring.py's shared
EXTREME_LOW_THRESHOLD/EXTREME_HIGH_THRESHOLD (20/80) rather than inventing
a second "extreme" definition. At 20/80 this composite spends ~9.5% of
days in either extreme tier, roughly 5-6 episodes/year per side -- similar
cadence to dashboard 1's extreme zones. Not separately walk-forward
tested for THIS composite (scoring.py's own five-zone validation was run
against dashboard 1's composite, not this one); this is a display
granularity addition on top of the already-disclosed, already-negative-
spread short-term signal (see the footer/README), not a new edge.

Run standalone to print the JSON to stdout, or import build_data() and
call it from build_dashboards.py.
"""

import json
import argparse
import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from st_indicators import build_st_indicator_table, BB_CLIP_RANGE, MACD_CLIP_RANGE
from scoring import (compute_composite_score, flag_five_zones, apply_confirmation, extract_zone_transitions,
                     apply_signal_cooldown, flag_extreme_zones, extract_extreme_periods,
                     EXTREME_LOW_THRESHOLD, EXTREME_HIGH_THRESHOLD)
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
    zoned = flag_five_zones(scored, buy_threshold=buy_threshold, sell_threshold=sell_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)
    zoned = flag_extreme_zones(zoned)

    confirmed_transitions = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    signals = apply_signal_cooldown(confirmed_transitions, min_gap_days=cooldown_days)
    extreme_periods = extract_extreme_periods(zoned)

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
        "extreme_low_threshold": EXTREME_LOW_THRESHOLD,
        "extreme_high_threshold": EXTREME_HIGH_THRESHOLD,
        "current_extreme_zone": latest["extreme_zone"],
        "confirm_days": confirm_days,
        "cooldown_days": cooldown_days,
        "bb_clip_range": list(BB_CLIP_RANGE),
        "macd_clip_range": list(MACD_CLIP_RANGE),
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
                "macd_hist_pct": round(float(row["macd_hist_pct"]), 3) if pd.notna(row["macd_hist_pct"]) else None,
                "fng_short_smoothed": round(float(row["fng_short_smoothed"]), 2) if pd.notna(row["fng_short_smoothed"]) else None,
                "pct_b": round(float(row["pct_b"]), 2) if pd.notna(row["pct_b"]) else None,
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
