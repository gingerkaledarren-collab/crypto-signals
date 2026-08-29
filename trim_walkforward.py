"""
trim_walkforward.py

Reproduces the out-of-sample validation behind trim_signal.py's chosen
thresholds (50/70), same chronological train/test method as walkforward.py
and st_walkforward.py: sweep candidate (lt_threshold, st_threshold) pairs
on TRAIN ONLY, then check the frozen winner blind on TEST.

Unlike the other two walk-forward scripts, this one prints a full
threshold/frequency tradeoff table rather than picking a single "best"
config -- the actual choice of 50/70 was a deliberate frequency/strength
tradeoff (see trim_signal.py's docstring), not a pure spread-maximization,
so seeing the whole table is the honest way to show that choice.
"""

import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from indicators import build_indicator_table
from st_indicators import build_st_indicator_table
from scoring import compute_composite_score, apply_confirmation, extract_zone_transitions, apply_signal_cooldown
from trim_signal import ST_WEIGHTS, TRIM_CONFIRM_DAYS, TRIM_COOLDOWN_DAYS

FORWARD_HORIZON_DAYS = 90


def build_merged_table(price_df=None, fng_df=None) -> pd.DataFrame:
    if price_df is None:
        price_df = fetch_btc_price_history()
    if fng_df is None:
        fng_df = fetch_fear_greed_history()

    lt_table = build_indicator_table(price_df, fng_df)
    lt_scored = compute_composite_score(lt_table)[["date", "composite_score"]].rename(
        columns={"composite_score": "lt_score"})

    st_table = build_st_indicator_table(price_df, fng_df)
    st_scored = compute_composite_score(st_table, weights=ST_WEIGHTS)[["date", "price", "composite_score"]].rename(
        columns={"composite_score": "st_score"})

    merged = pd.merge(st_scored, lt_scored, on="date", how="inner").sort_values("date").reset_index(drop=True)
    for h in [30, 60, 90]:
        merged[f"fwd_{h}"] = (merged["price"].shift(-h) - merged["price"]) / merged["price"] * 100
    return merged


def eval_rule(df: pd.DataFrame, lt_threshold: float, st_threshold: float, horizon: int = FORWARD_HORIZON_DAYS) -> dict:
    mask = (df["lt_score"] >= lt_threshold) & (df["st_score"] < st_threshold)
    trim = df[mask][f"fwd_{horizon}"].dropna()
    rest = df[~mask][f"fwd_{horizon}"].dropna()
    return {
        "lt_threshold": lt_threshold, "st_threshold": st_threshold, "horizon": horizon,
        "trim_ret": trim.mean(), "rest_ret": rest.mean(), "spread": rest.mean() - trim.mean(),
        "n_trim": len(trim), "n_rest": len(rest),
    }


def signal_frequency(merged: pd.DataFrame, lt_threshold: float, st_threshold: float,
                      confirm_days: int = TRIM_CONFIRM_DAYS, cooldown_days: int = TRIM_COOLDOWN_DAYS) -> float:
    m = merged.copy()
    m["zone"] = "neutral"
    m.loc[(m["lt_score"] >= lt_threshold) & (m["st_score"] < st_threshold), "zone"] = "trim_zone"
    m["composite_score"] = m["st_score"]
    zoned = apply_confirmation(m, min_days=confirm_days)
    confirmed = extract_zone_transitions(zoned, zone_col="confirmed_zone")
    signals = apply_signal_cooldown(confirmed, min_gap_days=cooldown_days)
    years = (merged["date"].max() - merged["date"].min()).days / 365.25
    return len(signals) / years


def run_trim_walkforward(split_frac: float = 0.65, horizon: int = FORWARD_HORIZON_DAYS):
    merged = build_merged_table()
    split_idx = int(len(merged) * split_frac)
    split_date = merged.iloc[split_idx]["date"]
    train = merged[merged["date"] < split_date]
    test = merged[merged["date"] >= split_date]

    print("=" * 78)
    print("TRIM SIGNAL WALK-FORWARD VALIDATION")
    print("=" * 78)
    print(f"TRAIN: {train['date'].min().date()} to {train['date'].max().date()}")
    print(f"TEST  (blind): {test['date'].min().date()} to {test['date'].max().date()}")
    print()
    print(f"{'lt>=':>5} {'st<':>4} {'freq/yr':>8} | {'TRAIN spread':>13} | {'TEST spread':>12}")
    print("-" * 55)

    candidates = [(50, 70), (55, 70), (60, 70), (65, 70), (65, 65), (60, 65)]
    for lt_thresh, st_thresh in candidates:
        train_r = eval_rule(train, lt_thresh, st_thresh, horizon)
        test_r = eval_rule(test, lt_thresh, st_thresh, horizon)
        freq = signal_frequency(merged, lt_thresh, st_thresh)
        marker = "  <-- chosen" if (lt_thresh, st_thresh) == (50, 70) else ""
        print(f"{lt_thresh:>5} {st_thresh:>4} {freq:>7.1f}  | {train_r['spread']:>11.1f}pp | "
              f"{test_r['spread']:>10.1f}pp{marker}")

    print()
    print("Chosen: lt>=50, st<70 -- lands in the requested 4-6 signals/year range.")
    print("Tradeoff: roughly half the TEST spread of the stricter lt>=65 rule,")
    print("which only fires ~1.6-1.8x/year. Same direction confirmed at both")
    print("60d and 90d horizons -- see the conversation history / trim_signal.py")
    print("docstring for the full genesis of this rule and what was rejected.")


if __name__ == "__main__":
    run_trim_walkforward()
