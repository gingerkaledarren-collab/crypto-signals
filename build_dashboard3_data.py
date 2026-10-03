"""
build_dashboard3_data.py

Produces the JSON blob for the "Short-Term Signal (Fast Variant)"
comparison dashboard -- same composite structure as build_dashboard2_data.py
(five-tier zones, confirmation, cooldown, extreme periods) and the SAME
thresholds (60/30, confirm=3, cooldown=14) for a fair apples-to-apples
comparison, but built from st_indicators_fast.py's shorter-lookback
technicals instead of st_indicators.py's:
  - 50-day MA distance  -> 20-day MA distance
  - RSI(14)             -> RSI(7)
  - Bollinger %B(20,2)  -> Bollinger %B(10,2)
  - MACD(12,26,9)       -> MACD(8,17,9)
Fear & Greed is unchanged (still 5-day smoothed) -- this tests the
technical-indicator lookback choice in isolation, not a general retune.

Requested after noticing each of these four indicators individually
catches real local price peaks/troughs far more often at a shorter
lookback (e.g. RSI(7) hits >=70 on 63% of real peaks vs. RSI(14)'s 34%;
full numbers for all four in the conversation record / README). That
part replicates cleanly here. BUT checked directly whether that
translates into a better composite: it does not. Same 65/35 walk-forward
split, same 60/30/confirm=3 thresholds, 30-day forward-return spread
(buy_zone fwd return minus sell_zone fwd return):

    variant                                TRAIN spread   TEST spread
    current (RSI14/MA50/BB20/MACD12-26-9)  -6.3pp         -5.8pp
    fast (RSI7/MA20/BB10/MACD8-17-9)       -7.4pp         -7.2pp

Slightly WORSE on both splits, not better -- catching more individual
local extremes doesn't fix the composite's already-disclosed trend-
confirming (not reversal-predicting) problem, and may make it marginally
worse by reacting to (and partly just amplifying) short-lived momentum.

It also does NOT solve the original "why doesn't this flash extreme sell
more" question it was built to test: at real local price peaks, the fast
composite crosses the plain sell_threshold (60) more often than the
current one (66% of peaks vs. 58%), but it reaches the rarer EXTREME
tier (>=80) LESS often (7% of peaks vs. 10%) and spends less of its time
there overall (3.2% of all days vs. 4.8%) -- individually-faster
components apparently move independently enough that having all of them
pinned at an extreme simultaneously, for long enough to hold through
confirmation, actually gets harder, not easier, once they're all noisier.

Bottom line: this is a real, useful finding -- published as its own
comparison dashboard rather than silently adopted, same as the Dashboard
1 alt-weights comparison -- not a proposed replacement for the live
short-term composite in st_indicators.py/st_backtest.py.

**20-day MA distance removed from the composite entirely, by request**
(weight redistributed proportionally to the remaining four via
compute_composite_score()'s own normalization -- just deleting the dict
entry is enough). Still computed and charted below as context only
(same treatment as the long-term dashboard's EMA-structure/MVRV charts),
just not scored. Re-ran the same walk-forward comparison with it removed:

    variant                                TRAIN spread   TEST spread
    5-input (with MA20, 17.5%)             -7.4pp         -7.2pp
    4-input (MA20 removed, reweighted)     -8.0pp         -5.4pp

Mixed, not a clear win either way -- slightly worse on TRAIN, better on
TEST, noise-level given how few confirmed signals this composite produces
per split. Same caveat as every other change here: not a validated
improvement, applied because requested and reported honestly either way.

Run standalone to print the JSON to stdout, or import build_data() and
call it from build_dashboards.py.
"""

import json
import argparse
import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from st_indicators_fast import build_st_indicator_table_fast, BB10_CLIP_RANGE, MACD_FAST_CLIP_RANGE
from scoring import (compute_composite_score, flag_five_zones, apply_confirmation, extract_zone_transitions,
                     apply_signal_cooldown, flag_extreme_zones, extract_extreme_periods,
                     EXTREME_LOW_THRESHOLD, EXTREME_HIGH_THRESHOLD)
from st_current_status import DEFAULT_SELL_THRESHOLD, DEFAULT_BUY_THRESHOLD, DEFAULT_CONFIRM_DAYS

COOLDOWN_DAYS = 14
SERIES_MONTHS = 24

# 20-day MA distance removed by request (see module docstring) -- the
# remaining three weights are unchanged from their original values;
# compute_composite_score() normalizes by the total, so dropping this
# entry alone is enough to redistribute its 17.5% proportionally.
ST_FAST_WEIGHTS = {
    "fng_st_score": 0.30,
    "rsi7_score": 0.175,
    "bb10_score": 0.175,
    "macdfast_score": 0.175,
}

INDICATOR_LABELS_FAST = {
    "fng_st_score": "Fear & Greed (5d smoothed)",
    "rsi7_score": "RSI(7)",
    "bb10_score": "Bollinger %B (10d)",
    "macdfast_score": "MACD histogram (8/17/9)",
}


def build_data(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
               confirm_days: int = DEFAULT_CONFIRM_DAYS, cooldown_days: int = COOLDOWN_DAYS,
               force_refresh: bool = False) -> dict:
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    table = build_st_indicator_table_fast(price_df, fng_df)

    scored = compute_composite_score(table, weights=ST_FAST_WEIGHTS)
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
        "bb_clip_range": list(BB10_CLIP_RANGE),
        "macd_clip_range": list(MACD_FAST_CLIP_RANGE),
        "indicators": [
            {"key": key, "label": label, "value": round(float(latest[key]), 1)}
            for key, label in INDICATOR_LABELS_FAST.items()
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
                # Aliased back to dashboard2_template.html's field names so
                # the same chart-rendering JS works unmodified -- the
                # UNDERLYING indicator definition differs (see module
                # docstring), the JSON shape doesn't need to.
                "daily_rsi": round(float(row["rsi7"]), 2) if pd.notna(row["rsi7"]) else None,
                "ma50": round(float(row["ma20"]), 2) if pd.notna(row["ma20"]) else None,
                "macd_line": round(float(row["macd_fast_line"]), 2) if pd.notna(row["macd_fast_line"]) else None,
                "macd_signal": round(float(row["macd_fast_signal"]), 2) if pd.notna(row["macd_fast_signal"]) else None,
                "macd_hist_pct": round(float(row["macd_fast_hist_pct"]), 3) if pd.notna(row["macd_fast_hist_pct"]) else None,
                "fng_short_smoothed": round(float(row["fng_short_smoothed"]), 2) if pd.notna(row["fng_short_smoothed"]) else None,
                "pct_b": round(float(row["pct_b10"]), 2) if pd.notna(row["pct_b10"]) else None,
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
