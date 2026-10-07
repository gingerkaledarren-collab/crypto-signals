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

**MACD(8/17/9) removed from the composite entirely, by request**, after
analysis found it was the second-biggest drag after Fear & Greed (3.4 of
a 16.2-point average shortfall from 80 at real peaks that missed
extreme_sell, ~21% of the total) AND largely redundant with what's
already in the mix -- correlated 0.67 with both RSI(7) and Bollinger
%B(10) across full history (vs. 0.06 for F&G), i.e. a third vote on the
same short-term momentum those two already cover, not an independent
signal. Unlike the MA20 removal, dropping MACD improved EVERY metric
checked, not a mixed result:

    variant (4-input, with MA20 already removed)   TRAIN     TEST    peaks>=80  days>=80
    with MACD                                      -8.0pp    -5.4pp    8%        2.8%
    MACD removed (3-input: F&G/RSI7/BB10)          -6.7pp    -3.8pp   13%        3.2%

**Fear & Greed also changed from 5-day smoothed to 1-day (unsmoothed),
by request** -- same change, same rationale as the live short-term
composite's (st_indicators.py's FNG_SHORT_WINDOW). Combined with the
MACD removal above, the final 3-input composite (F&G 1D / RSI(7) /
Bollinger %B(10,2)) scores:

    TRAIN spread=-6.3pp, TEST spread=-3.5pp, peaks>=80: 15%, days>=80: 4.2%

Still negative walk-forward spread -- this doesn't fix the composite's
core problem, it's not a validated edge -- but it's the least-negative,
highest-extreme-catch-rate version of this composite found so far, via
two independently-reasoned removals (redundancy + drag) stacking
cleanly rather than fighting each other.

**Remaining three inputs (F&G 1D / RSI(7) / Bollinger %B(10,2)) changed
from weighted (46%/27%/27% after normalization) to EQUAL (1/3 each), by
request**, to see what de-emphasizing F&G's dominance does. Mixed, not a
clean win this time -- unlike the MACD removal, the two metrics move in
OPPOSITE directions:

    variant                        TRAIN     TEST     peaks>=80   days>=80
    weighted (46/27/27)            -6.3pp    -3.7pp     15%         4.2%
    equal (1/3 each)               -6.8pp    -5.0pp     18%         4.6%

Equal weighting catches MORE real extremes (18% of peaks vs. 15%, more
days spent extreme) but the walk-forward spread gets WORSE on both
splits. Read together with the F&G-drag finding earlier: F&G's heavier
weight was directly responsible for both the lower extreme-catch-rate
AND the better (less-negative) walk-forward spread -- de-weighting it
trades one for the other rather than being a free improvement. Kept
as requested; this is the config this dashboard currently ships.

Run standalone to print the JSON to stdout, or import build_data() and
call it from build_dashboards.py.
"""

import json
import argparse
import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from st_indicators_fast import build_st_indicator_table_fast, BB10_CLIP_RANGE, MACD_FAST_CLIP_RANGE
from scoring import (compute_composite_score, flag_five_zones, apply_confirmation, extract_zone_transitions,
                     apply_signal_cooldown, flag_extreme_zones, extract_extreme_periods)
from st_current_status import DEFAULT_SELL_THRESHOLD, DEFAULT_CONFIRM_DAYS

COOLDOWN_DAYS = 14
SERIES_MONTHS = 24

# Extreme thresholds recalibrated for THIS composite specifically, by
# request -- the shared scoring.EXTREME_LOW_THRESHOLD/EXTREME_HIGH_THRESHOLD
# (20/80) were calibrated against the long-term composite's distribution
# and, reused here unmodified, badly undershot this composite's own "top
# ~10% of readings" design intent (only 4.6% of days at 20/80, vs. the
# ~9.5% that 25/75 or the ~16% that 30/70 actually give this composite).
# 30/70 was chosen over the better-calibrated-to-10% 25/75 anyway, by
# request, trading rarity for sensitivity (peak catch-rate 18%->52%,
# trough catch-rate 32%->73%, episodes/year roughly double).
#
# buy_threshold also moves from the shared DEFAULT_BUY_THRESHOLD (30) to
# 40 -- otherwise it would exactly coincide with extreme_buy_threshold
# (30), and flag_five_zones() applies buy_zone before extreme_buy, so an
# identical pair of cutoffs would silently erase the plain buy_zone tier
# (every buy_zone day would get immediately overwritten to extreme_buy).
# sell_threshold stays at the shared 60 -- 70 is still safely above it,
# so sell_zone/extreme_sell stay distinct without any change there. The
# result is a symmetric structure: neutral 40-60 (20pp wide, centered on
# 50), buy_zone 30-40 and sell_zone 60-70 (10pp each), extreme outside that.
FAST_BUY_THRESHOLD = 40
FAST_EXTREME_LOW_THRESHOLD = 30
FAST_EXTREME_HIGH_THRESHOLD = 70

# Plain buy_zone/sell_zone confirmation shortened from the shared
# DEFAULT_CONFIRM_DAYS (3) to 1 day, by request (2026-10-07) -- the badge
# showed "Neutral" on day 2 of a raw sell_zone run, which read as wrong.
# With 1, the confirmed zone is just the raw zone, same-day, matching how
# the extreme tiers already behave. Trades away the whipsaw filter.
FAST_CONFIRM_DAYS = 1

# 20-day MA distance and MACD(8/17/9) both removed by request (see module
# docstring) -- compute_composite_score() normalizes by the total, so
# just deleting those two dict entries redistributes their weight
# proportionally. The remaining three were then changed from weighted
# (30/17.5/17.5) to EQUAL (1/3 each), also by request -- see the mixed
# result (catches more extremes, worse walk-forward spread) above.
ST_FAST_WEIGHTS = {
    "fng_st_score": 1 / 3,
    "rsi7_score": 1 / 3,
    "bb10_score": 1 / 3,
}

INDICATOR_LABELS_FAST = {
    "fng_st_score": "Fear & Greed (1D, unsmoothed)",
    "rsi7_score": "RSI(7)",
    "bb10_score": "Bollinger %B (10d)",
}


def build_data(sell_threshold: float = DEFAULT_SELL_THRESHOLD, buy_threshold: float = FAST_BUY_THRESHOLD,
               extreme_low_threshold: float = FAST_EXTREME_LOW_THRESHOLD,
               extreme_high_threshold: float = FAST_EXTREME_HIGH_THRESHOLD,
               confirm_days: int = FAST_CONFIRM_DAYS, cooldown_days: int = COOLDOWN_DAYS,
               force_refresh: bool = False) -> dict:
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    fng_df = fetch_fear_greed_history(force_refresh=force_refresh)
    table = build_st_indicator_table_fast(price_df, fng_df)

    scored = compute_composite_score(table, weights=ST_FAST_WEIGHTS)
    zoned = flag_five_zones(scored, buy_threshold=buy_threshold, sell_threshold=sell_threshold,
                             extreme_buy_threshold=extreme_low_threshold,
                             extreme_sell_threshold=extreme_high_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)
    zoned = flag_extreme_zones(zoned, extreme_low_threshold=extreme_low_threshold,
                               extreme_high_threshold=extreme_high_threshold)

    # apply_confirmation() tracks each of the five zone LABELS separately --
    # a day that escalates from a confirmed sell_zone into extreme_sell
    # starts a brand-new "extreme_sell" run at length 1, which (correctly
    # for the plain buy/sell tiers) gets downgraded to 'neutral' until it
    # holds confirm_days. That's wrong for the extreme tier specifically:
    # flag_extreme_zones()'s own extreme_zone column is deliberately NOT
    # confirmation-gated (an extreme reading is already rare/meaningful on
    # day 1 -- see its docstring), and extract_extreme_periods()/the
    # recommended_action logic below both already treat it that way. Having
    # confirmed_zone silently report 'neutral' on day 1 of a fresh extreme
    # run -- while the page's own action card says "sell today" -- is a
    # contradiction on the same dashboard, not a feature. Override
    # confirmed_zone with the extreme label whenever extreme_zone fires, so
    # the hero badge and signal history agree with the action card and the
    # extreme-zone table on what "right now" means. Ordinary buy_zone/
    # sell_zone/neutral days are untouched -- the 3-day hold still applies
    # there.
    extreme_to_zone = {"extreme_high": "extreme_sell", "extreme_low": "extreme_buy"}
    zoned["confirmed_zone"] = zoned["extreme_zone"].map(extreme_to_zone).fillna(zoned["confirmed_zone"])

    confirmed_transitions = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    signals = apply_signal_cooldown(confirmed_transitions, min_gap_days=cooldown_days)
    extreme_periods = extract_extreme_periods(zoned)

    latest = zoned.iloc[-1]
    zone_series = zoned["zone"]
    run_id = (zone_series != zone_series.shift(1)).cumsum()
    current_run_length = int((run_id == run_id.iloc[-1]).sum())

    # "Today's recommended action" under the backtested sizing rule
    # (euro1,500 every day in extreme_sell; euro5,000 once per NEW
    # extreme_buy episode) -- a position-sizing rule layered on top of
    # this composite's own extreme_zone, never separately walk-forward
    # validated itself (see the scenario-testing conversation record /
    # README). extreme_zone has no confirmation delay, same basis the
    # backtests used. Episode-based (not calendar-run-length-of-`zone`)
    # so a fresh extreme_buy triggers once even if the plain zone/
    # confirmed_zone run already started earlier.
    extreme_series = zoned["extreme_zone"]
    extreme_run_id = (extreme_series != extreme_series.shift(1)).cumsum()
    extreme_run_length = int((extreme_run_id == extreme_run_id.iloc[-1]).sum())
    current_extreme = latest["extreme_zone"]
    if current_extreme == "extreme_high":
        recommended_action = {
            "type": "sell", "amount": 1500,
            "detail": f"Sell €1,500 today — day {extreme_run_length} of this extreme_sell run",
        }
    elif current_extreme == "extreme_low" and extreme_run_length == 1:
        recommended_action = {
            "type": "buy", "amount": 5000,
            "detail": "Buy €5,000 today — new extreme_buy signal",
        }
    elif current_extreme == "extreme_low":
        recommended_action = {
            "type": "none", "amount": 0,
            "detail": f"No new ST action — day {extreme_run_length} of an extreme_buy run already triggered on day 1",
        }
    else:
        recommended_action = {
            "type": "none", "amount": 0,
            "detail": "No action — composite isn't at an ST extreme",
        }

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
        "extreme_low_threshold": extreme_low_threshold,
        "extreme_high_threshold": extreme_high_threshold,
        "current_extreme_zone": latest["extreme_zone"],
        "extreme_run_length": extreme_run_length,
        "recommended_action": recommended_action,
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
