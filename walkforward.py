"""
walkforward.py

Proper out-of-sample validation, as opposed to backtest.py which tunes
and evaluates on the full history at once (hindsight bias risk).

Approach:
  1. Split history chronologically into a TRAIN period and a TEST period.
  2. Sweep threshold/confirmation configs on TRAIN ONLY, selecting the
     best by a real predictive-value metric (not just signal frequency):
     the average forward return following buy-zone days minus the
     average forward return following sell-zone days. A working signal
     should show buy zones leading to better subsequent returns than
     sell zones.
  3. Apply that single, frozen config to TEST with NO further tuning --
     this is the blind, out-of-sample check. If it falls apart there,
     the train-period result was overfit to that period's specific
     cycle shape, not a real edge.

Caveat: forward returns for the last `horizon_days` of TRAIN pull in
some TEST-period price action (you need future price to know the
forward return). This is a minor boundary leak into config SELECTION,
not into the composite score itself -- worth knowing about, not worth
over-engineering away given how little history we have to split.
"""

import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history, fetch_supply_in_profit_history
from indicators import build_indicator_table
from scoring import compute_composite_score, flag_zones, apply_confirmation

FORWARD_HORIZON_DAYS = 90  # ~3 months; roughly matches the signal spacing we've observed


def add_forward_return(df: pd.DataFrame, horizon_days: int = FORWARD_HORIZON_DAYS) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    df["fwd_price"] = df["price"].shift(-horizon_days)
    df["fwd_return_pct"] = (df["fwd_price"] - df["price"]) / df["price"] * 100
    return df


def evaluate_config(df: pd.DataFrame, weights: dict, sell_threshold: float, buy_threshold: float,
                     confirm_days: int, horizon_days: int = FORWARD_HORIZON_DAYS) -> dict:
    scored = compute_composite_score(df, weights=weights)
    zoned = flag_zones(scored, sell_threshold=sell_threshold, buy_threshold=buy_threshold)
    zoned = apply_confirmation(zoned, min_days=confirm_days)
    zoned = add_forward_return(zoned, horizon_days)

    valid = zoned.dropna(subset=["fwd_return_pct"])
    by_zone = valid.groupby("confirmed_zone")["fwd_return_pct"]

    buy_ret = by_zone.mean().get("buy_zone", float("nan"))
    sell_ret = by_zone.mean().get("sell_zone", float("nan"))
    neutral_ret = by_zone.mean().get("neutral", float("nan"))
    baseline_ret = valid["fwd_return_pct"].mean()

    spread = buy_ret - sell_ret if pd.notna(buy_ret) and pd.notna(sell_ret) else float("-inf")

    return {
        "sell_threshold": sell_threshold, "buy_threshold": buy_threshold, "confirm_days": confirm_days,
        "buy_ret": buy_ret, "sell_ret": sell_ret, "neutral_ret": neutral_ret, "baseline_ret": baseline_ret,
        "spread": spread,
        "n_buy_days": int((valid["confirmed_zone"] == "buy_zone").sum()),
        "n_sell_days": int((valid["confirmed_zone"] == "sell_zone").sum()),
    }


def fmt_pct(x):
    return f"{x:.1f}%" if pd.notna(x) else "n/a"


def run_walkforward(weights: dict = None, configs: list = None, split_frac: float = 0.65,
                     horizon_days: int = FORWARD_HORIZON_DAYS, fng_window: int = 30,
                     include_supply_loss: bool = False):
    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()
    supply_df = fetch_supply_in_profit_history() if include_supply_loss else None
    table = build_indicator_table(price_df, fng_df, fng_window=fng_window,
                                   supply_profit_df=supply_df).sort_values("date").reset_index(drop=True)

    split_idx = int(len(table) * split_frac)
    split_date = table.iloc[split_idx]["date"]
    train = table[table["date"] < split_date].reset_index(drop=True)
    test = table[table["date"] >= split_date].reset_index(drop=True)

    print("=" * 70)
    print("WALK-FORWARD VALIDATION")
    print("=" * 70)
    print(f"TRAIN (tune here): {train['date'].min().date()} to {train['date'].max().date()} ({len(train)} rows)")
    print(f"TEST  (blind check): {test['date'].min().date()} to {test['date'].max().date()} ({len(test)} rows)")
    print()

    results = [evaluate_config(train, weights, s, b, c, horizon_days) for s, b, c in configs]
    results.sort(key=lambda r: r["spread"], reverse=True)

    print(f"--- TRAIN sweep, ranked by (buy_zone fwd return - sell_zone fwd return) over {horizon_days}d ---")
    for r in results:
        print(f"sell={r['sell_threshold']:>2} buy={r['buy_threshold']:>2} confirm={r['confirm_days']}d: "
              f"buy_ret={fmt_pct(r['buy_ret'])}, sell_ret={fmt_pct(r['sell_ret'])}, "
              f"spread={r['spread']:.1f}pp, n_buy={r['n_buy_days']}, n_sell={r['n_sell_days']}")

    best = results[0]
    print(f"\nBest on TRAIN: sell={best['sell_threshold']} buy={best['buy_threshold']} "
          f"confirm={best['confirm_days']}d (spread={best['spread']:.1f}pp)")

    test_result = evaluate_config(test, weights, best["sell_threshold"], best["buy_threshold"],
                                   best["confirm_days"], horizon_days)

    print()
    print(f"--- OUT-OF-SAMPLE (TEST) result, using the TRAIN-selected config with NO further tuning ---")
    print(f"buy_zone fwd_ret={fmt_pct(test_result['buy_ret'])} (n={test_result['n_buy_days']} days)")
    print(f"sell_zone fwd_ret={fmt_pct(test_result['sell_ret'])} (n={test_result['n_sell_days']} days)")
    print(f"neutral fwd_ret={fmt_pct(test_result['neutral_ret'])}")
    print(f"all-days baseline fwd_ret={fmt_pct(test_result['baseline_ret'])}  (roughly buy-and-hold, this horizon)")
    print(f"spread={test_result['spread']:.1f}pp")

    return results, best, test_result


if __name__ == "__main__":
    CONFIGS = [
        (75, 25, 0), (75, 25, 3), (70, 30, 3), (65, 35, 3), (65, 35, 5),
        (60, 40, 3), (60, 40, 5), (55, 45, 3), (55, 45, 5),
    ]
    run_walkforward(configs=CONFIGS)
