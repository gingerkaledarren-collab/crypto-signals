"""
portfolio_simulation.py

Simulates the position-sizing strategy described for using both dashboards
together, starting from $50,000 in BTC + $20,000 in cash:

RULES (evaluated weekly, in this order each week):
  1. LONG-TERM SELL: the first week a fresh confirmed sell_zone signal
     appears (dashboard 1's validated system: sell>=60, buy<=40, confirm=5d)
     -- sell 90% of current BTC holdings to cash. A one-time, decisive
     action per signal (not repeated every week the zone persists), matching
     "sell all or almost everything" as a reaction to the signal itself.
  2. LONG-TERM BUY: every week the confirmed zone IS buy_zone (compounding
     for as long as it remains buy_zone, not just on the first week) --
     deploy 7.5% of remaining cash into BTC. 7.5% is the midpoint of the
     requested 5-10% range. Compounding means the deployed amount shrinks
     each week as cash depletes -- naturally front-loaded.
  3. SHORT-TERM TRIM: every week the raw short-term composite (trim_signal.py's
     ST_WEIGHTS, F&G-heavy) is >= 70 -- sell 10% of remaining BTC to cash.
  4. SHORT-TERM ADD: every week the raw short-term composite is <= 30 --
     deploy 10% of remaining cash into BTC.

Rules 2-4 all compound weekly while their condition holds, for consistency
with each other (rule 2 was specified that way explicitly; 3 and 4 are
built to match rather than arbitrarily firing once). Rule 1 is deliberately
a one-time action per fresh signal, matching how it was described (a
decisive reaction, not a gradual process) and how "signal" has meant
"transition" throughout this whole project.

Benchmarks for comparison:
  - Buy & hold: $50k BTC bought at simulation start, $20k cash never touched.
  - All-in day 1: the full $70k into BTC at simulation start, held forever.

This is a simulation of a rules-based strategy, not a new validated
signal -- the underlying signals (dashboard 1's zones, dashboard 2's
composite) are the same ones already walk-forward tested. What's being
tested here is the SIZING RULES layered on top, which haven't been
separately validated -- treat these results as "what would this specific
plan have done," not as a new backtest with the same evidentiary weight
as the walk-forward work.
"""

import pandas as pd
from fetch_data import fetch_btc_price_history, fetch_fear_greed_history
from indicators import build_indicator_table
from st_indicators import build_st_indicator_table
from scoring import compute_composite_score, flag_zones, apply_confirmation
from trim_signal import ST_WEIGHTS

STARTING_BTC_USD = 50_000
STARTING_CASH_USD = 20_000

LT_SELL_THRESHOLD = 60
LT_BUY_THRESHOLD = 40
LT_CONFIRM_DAYS = 5

ST_SELL_THRESHOLD = 70
ST_BUY_THRESHOLD = 30

LT_SELL_FRACTION = 0.90
LT_BUY_WEEKLY_FRACTION = 0.075
ST_TRIM_WEEKLY_FRACTION = 0.10
ST_ADD_WEEKLY_FRACTION = 0.10


def build_weekly_table():
    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()

    lt_table = build_indicator_table(price_df, fng_df)
    lt_scored = compute_composite_score(lt_table)
    lt_zoned = flag_zones(lt_scored, sell_threshold=LT_SELL_THRESHOLD, buy_threshold=LT_BUY_THRESHOLD)
    lt_zoned = apply_confirmation(lt_zoned, min_days=LT_CONFIRM_DAYS)
    lt_zoned = lt_zoned[["date", "price", "confirmed_zone"]].rename(columns={"confirmed_zone": "lt_zone"})

    st_table = build_st_indicator_table(price_df, fng_df)
    st_scored = compute_composite_score(st_table, weights=ST_WEIGHTS)[["date", "composite_score"]].rename(
        columns={"composite_score": "st_score"})

    merged = pd.merge(lt_zoned, st_scored, on="date", how="inner").sort_values("date").reset_index(drop=True)
    weekly = merged.set_index("date").resample("W").last().dropna().reset_index()
    return weekly


def run_simulation():
    weekly = build_weekly_table()

    start_price = weekly.iloc[0]["price"]
    btc_qty = STARTING_BTC_USD / start_price
    cash = STARTING_CASH_USD

    bh_btc_qty = STARTING_BTC_USD / start_price
    bh_cash = STARTING_CASH_USD

    allin_qty = (STARTING_BTC_USD + STARTING_CASH_USD) / start_price

    prev_lt_zone = None
    log = []

    for _, row in weekly.iterrows():
        price = row["price"]
        lt_zone = row["lt_zone"]
        st_score = row["st_score"]

        lt_fresh_sell = (lt_zone == "sell_zone") and (prev_lt_zone != "sell_zone")

        action = []
        if lt_fresh_sell and btc_qty > 0:
            sold_qty = btc_qty * LT_SELL_FRACTION
            cash += sold_qty * price
            btc_qty -= sold_qty
            action.append(f"LT-SELL {LT_SELL_FRACTION*100:.0f}%")

        if lt_zone == "buy_zone" and cash > 0:
            spend = cash * LT_BUY_WEEKLY_FRACTION
            btc_qty += spend / price
            cash -= spend
            action.append(f"LT-BUY {LT_BUY_WEEKLY_FRACTION*100:.1f}%wk")

        if st_score >= ST_SELL_THRESHOLD and btc_qty > 0:
            sold_qty = btc_qty * ST_TRIM_WEEKLY_FRACTION
            cash += sold_qty * price
            btc_qty -= sold_qty
            action.append(f"ST-TRIM {ST_TRIM_WEEKLY_FRACTION*100:.0f}%wk")

        if st_score <= ST_BUY_THRESHOLD and cash > 0:
            spend = cash * ST_ADD_WEEKLY_FRACTION
            btc_qty += spend / price
            cash -= spend
            action.append(f"ST-ADD {ST_ADD_WEEKLY_FRACTION*100:.0f}%wk")

        total = btc_qty * price + cash
        bh_total = bh_btc_qty * price + bh_cash
        allin_total = allin_qty * price

        log.append({
            "date": row["date"], "price": price, "lt_zone": lt_zone, "st_score": st_score,
            "btc_qty": btc_qty, "cash": cash, "total": total,
            "buy_hold_total": bh_total, "all_in_total": allin_total,
            "action": ";".join(action) if action else "",
        })

        prev_lt_zone = lt_zone

    return pd.DataFrame(log)


def max_drawdown(series):
    running_max = series.cummax()
    drawdown = (series - running_max) / running_max * 100
    return drawdown.min()


if __name__ == "__main__":
    df = run_simulation()

    final = df.iloc[-1]
    print("=" * 70)
    print("PORTFOLIO SIMULATION")
    print("=" * 70)
    print(f"Period: {df.iloc[0]['date'].date()} to {df.iloc[-1]['date'].date()}")
    print(f"Starting: ${STARTING_BTC_USD:,} BTC + ${STARTING_CASH_USD:,} cash = "
          f"${STARTING_BTC_USD + STARTING_CASH_USD:,}")
    print()
    print(f"{'Strategy':<28} {'Final value':>14} {'Return':>10} {'Max drawdown':>14}")
    print("-" * 68)
    for label, col in [("Rules-based (both dashboards)", "total"),
                        ("Buy & hold ($50k BTC only)", "buy_hold_total"),
                        ("All-in day 1 ($70k BTC)", "all_in_total")]:
        final_val = final[col]
        ret = (final_val / (STARTING_BTC_USD + STARTING_CASH_USD) - 1) * 100
        dd = max_drawdown(df[col])
        print(f"{label:<28} {final_val:>13,.0f} {ret:>9.1f}% {dd:>13.1f}%")

    print()
    print(f"Ending BTC qty: {final['btc_qty']:.4f}  |  Ending cash: ${final['cash']:,.0f}")
    print()

    actions = df[df["action"] != ""]
    print(f"Total action-weeks: {len(actions)} / {len(df)} weeks")
    print()
    print("Action counts by type:")
    for kind in ["LT-SELL", "LT-BUY", "ST-TRIM", "ST-ADD"]:
        count = actions["action"].str.contains(kind).sum()
        print(f"  {kind}: {count} weeks")

    print()
    print("First and last 5 action weeks:")
    print(actions[["date", "price", "lt_zone", "st_score", "action", "total"]].head(5).to_string(index=False))
    print("...")
    print(actions[["date", "price", "lt_zone", "st_score", "action", "total"]].tail(5).to_string(index=False))
