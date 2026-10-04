"""
build_dashboard4_data.py

Produces the JSON blob for the "Signal Research" dashboard -- a research/
context dashboard, NOT a composite-score dashboard like 1-3. It surfaces
two indicators investigated after watching an Alessio Rastani video and a
Glassnode social post, each tested honestly against this project's own
data before being shown here (see the conversation record / README):

1. WEEKLY MACD DIVERGENCE (price makes a new swing high/low that weekly
   MACD doesn't confirm). Extremely rare (8 signals in 842 weeks,
   2010-2026) and the small sample means its 75-100% directional
   follow-through rate is NOT distinguishable from BTC's own baseline
   volatility (any random week already has a 66.4%/48.2% chance of a
   >=10% rally/drop within 12 weeks) -- shown as a rare "pay attention"
   flag, not a scored signal, with that caveat surfaced on the page
   itself, not buried.

2. LTH-MVRV (Long-Term Holder MVRV -- market cap / realized cap
   restricted to coins held 155+ days, from BGeometrics, same ~4-year
   free-history cap as the plain MVRV already used on dashboard 1).
   Tests whether long-term holders are in aggregate profit (>1) or
   capitulating (<1). Confirmed directly in this project's own data: it
   never dipped below 1 across the Oct 2025 ATH -> Jul 2026 trough, the
   same crash window already used as this project's stress test
   elsewhere (scenario-testing conversation record) -- independent
   corroboration of the "long-term holders never went underwater this
   cycle" claim, at least for the one cycle our free data window covers.

3. MVRV MOMENTUM (MVRV ratio vs. its own 365-day rolling mean, from a
   separate Glassnode social post). Claim: crossing back above 1.0 marked
   the start of the 2019 and 2023 bull markets. Our free MVRV history
   (same ~4-year BGeometrics cap as #2) starts Oct 2022 -- the 2019 cross
   is entirely outside this data, and the 2023 one sits right at the edge
   of the 365-day lead-in a rolling mean needs, so neither historical
   comparison can actually be confirmed or refuted here. The raw daily
   ratio also whipsaws across 1.0 dozens of times a year against this
   short baseline, far noisier than Glassnode's own long-history chart --
   shown 7-day-smoothed with a 10-day hold required to count as a regime
   change, same confirmation-delay spirit as scoring.apply_confirmation()
   elsewhere in this project, and that filtering is disclosed on the page.

None of the three indicators is in any composite here -- this dashboard
is deliberately presentational/context-only, same spirit as dashboard 1's
EMA-structure and MVRV charts.

Run standalone to print the JSON to stdout, or import build_data() and
call it from build_dashboards.py.
"""

import json
import argparse
import numpy as np
import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_lth_mvrv_history, fetch_mvrv_history
from st_indicators import compute_macd

MOMENTUM_SMOOTH_DAYS = 7     # smooths day-to-day whipsaw around the 1.0 line
MOMENTUM_MIN_SEGMENT_DAYS = 10  # a crossing only counts as a regime change if it holds this long

SWING_WINDOW_FINE = 4    # +/- weeks, for divergence-candidate swing points
SWING_WINDOW_COARSE = 12  # +/- weeks, for "real major peak/trough" evaluation
DIVERGENCE_EVAL_WINDOW = 6   # weeks, catch-rate matching window
DIVERGENCE_FWD_WEEKS = 12    # weeks, precision-check forward window
DIVERGENCE_MOVE_THRESHOLD = 0.10


def _find_swings(values: np.ndarray, window: int):
    n = len(values)
    is_low = np.zeros(n, dtype=bool)
    is_high = np.zeros(n, dtype=bool)
    for i in range(n):
        lo, hi = max(0, i - window), min(n, i + window + 1)
        segment = values[lo:hi]
        if values[i] == segment.min():
            is_low[i] = True
        if values[i] == segment.max():
            is_high[i] = True
    return is_low, is_high


def _build_macd_divergence(price_df: pd.DataFrame) -> dict:
    weekly = price_df.set_index("date")["price"].resample("W").last().dropna().reset_index()
    weekly.columns = ["date", "price"]
    macd_df = compute_macd(weekly, fast=12, slow=26, signal=9)
    weekly = pd.merge(weekly, macd_df, on="date", how="inner").reset_index(drop=True)

    fine_low, fine_high = _find_swings(weekly["price"].values, SWING_WINDOW_FINE)
    low_idxs = weekly.index[fine_low].tolist()
    high_idxs = weekly.index[fine_high].tolist()

    divergences = []
    for a, b in zip(low_idxs[:-1], low_idxs[1:]):
        if weekly.loc[b, "price"] < weekly.loc[a, "price"] and weekly.loc[b, "macd_line"] > weekly.loc[a, "macd_line"]:
            divergences.append({"type": "bullish", "idx_a": int(a), "idx_b": int(b)})
    for a, b in zip(high_idxs[:-1], high_idxs[1:]):
        if weekly.loc[b, "price"] > weekly.loc[a, "price"] and weekly.loc[b, "macd_line"] < weekly.loc[a, "macd_line"]:
            divergences.append({"type": "bearish", "idx_a": int(a), "idx_b": int(b)})
    divergences.sort(key=lambda d: d["idx_b"])

    # precision check: of all signals, how many were followed by a
    # >=10% move the "right" way within DIVERGENCE_FWD_WEEKS?
    hits_bull = total_bull = hits_bear = total_bear = 0
    for d in divergences:
        idx = d["idx_b"]
        end_idx = min(len(weekly) - 1, idx + DIVERGENCE_FWD_WEEKS)
        future = weekly["price"].values[idx:end_idx + 1]
        start_price = weekly["price"].values[idx]
        if d["type"] == "bullish":
            total_bull += 1
            if future.max() / start_price - 1 >= DIVERGENCE_MOVE_THRESHOLD:
                hits_bull += 1
        else:
            total_bear += 1
            if 1 - future.min() / start_price >= DIVERGENCE_MOVE_THRESHOLD:
                hits_bear += 1

    series = [
        {"date": row["date"].strftime("%Y-%m-%d"), "price": round(float(row["price"]), 2),
         "macd": round(float(row["macd_line"]), 1)}
        for _, row in weekly.iterrows()
    ]

    last = divergences[-1] if divergences else None
    return {
        "series": series,
        "divergences": divergences,
        "hits_bull": hits_bull, "total_bull": total_bull,
        "hits_bear": hits_bear, "total_bear": total_bear,
        "weeks": len(weekly),
        "last_signal": {
            "date": weekly.loc[last["idx_b"], "date"].strftime("%Y-%m-%d"),
            "type": last["type"],
            "price": round(float(weekly.loc[last["idx_b"], "price"]), 2),
        } if last else None,
    }


def _build_lth_mvrv(price_df: pd.DataFrame, lth_df: pd.DataFrame) -> dict:
    merged = pd.merge(price_df, lth_df, on="date", how="inner").sort_values("date").reset_index(drop=True)

    below_one = merged["lth_mvrv_ratio"] < 1
    run_id = (below_one != below_one.shift(1)).cumsum()
    periods = []
    for rid, grp in merged.groupby(run_id):
        if not bool(grp["lth_mvrv_ratio"].iloc[0] < 1):
            continue
        min_idx = grp["lth_mvrv_ratio"].idxmin()
        periods.append({
            "start_date": grp["date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": grp["date"].iloc[-1].strftime("%Y-%m-%d"),
            "days": len(grp),
            "min_ratio": round(float(grp["lth_mvrv_ratio"].min()), 3),
            "min_date": merged.loc[min_idx, "date"].strftime("%Y-%m-%d"),
        })

    latest = merged.iloc[-1]
    min_row = merged.loc[merged["lth_mvrv_ratio"].idxmin()]

    # The "green circle" equivalent from the Glassnode chart: the low point
    # of the MOST RECENT pullback that didn't tip into capitulation --
    # confirming the "long-term holders never went underwater this time"
    # read with an actual marked low, not just a never-breached line.
    #
    # Deliberately scoped to the trailing RECENT_LOW_WINDOW_DAYS, not the
    # minimum of the whole multi-year above-1.0 run: since there's been
    # only one such run in our ~4-year data window (no second capitulation
    # since early 2023), its global minimum landed on an early, minor dip
    # (2023-03-10, 1.014) rather than the much deeper and more recent
    # pullback (2026-06-30, 1.19) that's the one actually worth marking --
    # same mismatch a human reading the chart would flag.
    RECENT_LOW_WINDOW_DAYS = 540
    non_capitulation_low = None
    recent_window = merged[merged["date"] >= merged["date"].max() - pd.Timedelta(days=RECENT_LOW_WINDOW_DAYS)]
    recent_above = recent_window[recent_window["lth_mvrv_ratio"] >= 1]
    if not recent_above.empty:
        low_idx = recent_above["lth_mvrv_ratio"].idxmin()
        non_capitulation_low = {
            "date": merged.loc[low_idx, "date"].strftime("%Y-%m-%d"),
            "value": round(float(merged.loc[low_idx, "lth_mvrv_ratio"]), 3),
        }

    series = [
        {"date": row["date"].strftime("%Y-%m-%d"), "price": round(float(row["price"]), 2),
         "lth_mvrv": round(float(row["lth_mvrv_ratio"]), 3)}
        for _, row in merged.iterrows()
    ]

    return {
        "series": series,
        "below_one_periods": periods,
        "as_of": latest["date"].strftime("%Y-%m-%d"),
        "current": round(float(latest["lth_mvrv_ratio"]), 3),
        "data_start": merged["date"].min().strftime("%Y-%m-%d"),
        "all_time_min": {
            "date": min_row["date"].strftime("%Y-%m-%d"),
            "value": round(float(min_row["lth_mvrv_ratio"]), 3),
        },
        "non_capitulation_low": non_capitulation_low,
    }


def _build_mvrv_momentum(price_df: pd.DataFrame, mvrv_df: pd.DataFrame) -> dict:
    """
    Tests the Glassnode "MVRV momentum" claim: MVRV crossing back above its
    own 365-day mean supposedly marked the start of the 2019 and 2023 bull
    markets. Our free MVRV history (BGeometrics, same ~4-year cap as
    fetch_mvrv_history()) only starts Oct 2022, so the 2019 crossing is
    entirely outside what we can check, and the 365-day rolling mean itself
    only has a full year of lead-in by ~Apr 2023 -- the 2023 comparison is
    right at the edge of what this data can support, not a clean
    confirmation either.

    The raw daily ratio whipsaws across 1.0 dozens of times a year on this
    short baseline (far noisier than Glassnode's own smoother long-history
    chart) -- MOMENTUM_SMOOTH_DAYS (7-day mean) and a MOMENTUM_MIN_SEGMENT_DAYS
    (10-day hold) filter are applied before calling anything a regime
    change, same spirit as this project's signal-confirmation logic
    elsewhere (scoring.apply_confirmation).
    """
    merged = pd.merge(price_df, mvrv_df, on="date", how="inner").sort_values("date").reset_index(drop=True)
    merged["mvrv_365mean"] = merged["mvrv_ratio"].rolling(365, min_periods=200).mean()
    merged["momentum_raw"] = merged["mvrv_ratio"] / merged["mvrv_365mean"]
    merged["momentum"] = merged["momentum_raw"].rolling(MOMENTUM_SMOOTH_DAYS, min_periods=1).mean()

    valid = merged.dropna(subset=["momentum"]).reset_index(drop=True)
    above = valid["momentum"] > 1
    run_id = (above != above.shift(1)).cumsum()

    segments = []
    for rid, grp in valid.groupby(run_id):
        if len(grp) < MOMENTUM_MIN_SEGMENT_DAYS:
            continue
        segments.append({
            "start_date": grp["date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": grp["date"].iloc[-1].strftime("%Y-%m-%d"),
            "days": len(grp),
            "above": bool(grp["momentum"].iloc[0] > 1),
        })

    latest = valid.iloc[-1]
    series = [
        {"date": row["date"].strftime("%Y-%m-%d"), "price": round(float(row["price"]), 2),
         "momentum": round(float(row["momentum"]), 3)}
        for _, row in valid.iterrows()
    ]

    return {
        "series": series,
        "segments": segments,
        "as_of": latest["date"].strftime("%Y-%m-%d"),
        "current": round(float(latest["momentum"]), 3),
        "data_start": valid["date"].min().strftime("%Y-%m-%d"),
        "smooth_days": MOMENTUM_SMOOTH_DAYS,
    }


def build_data(force_refresh: bool = False) -> dict:
    price_df = fetch_btc_price_history(force_refresh=force_refresh)
    lth_df = fetch_lth_mvrv_history(force_refresh=force_refresh)
    mvrv_df = fetch_mvrv_history(force_refresh=force_refresh)

    macd_div = _build_macd_divergence(price_df)
    lth_mvrv = _build_lth_mvrv(price_df, lth_df)
    mvrv_momentum = _build_mvrv_momentum(price_df, mvrv_df)

    latest_price = price_df.iloc[-1]
    return {
        "as_of": latest_price["date"].strftime("%Y-%m-%d"),
        "price": round(float(latest_price["price"]), 2),
        "macd_divergence": macd_div,
        "lth_mvrv": lth_mvrv,
        "mvrv_momentum": mvrv_momentum,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/on-chain data")
    args = parser.parse_args()

    print(json.dumps(build_data(force_refresh=args.refresh)))
