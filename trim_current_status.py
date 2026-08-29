"""
trim_current_status.py

"Where does the trim signal stand today" -- mirrors current_status.py's
role for the long-term system, but for trim_signal.py.
"""

import argparse
from trim_signal import (get_trim_signals, TRIM_LT_THRESHOLD, TRIM_ST_THRESHOLD,
                          TRIM_CONFIRM_DAYS, TRIM_COOLDOWN_DAYS)


def print_report(lt_threshold: float = TRIM_LT_THRESHOLD, st_threshold: float = TRIM_ST_THRESHOLD,
                  confirm_days: int = TRIM_CONFIRM_DAYS, cooldown_days: int = TRIM_COOLDOWN_DAYS):
    zoned, signals = get_trim_signals(confirm_days=confirm_days, cooldown_days=cooldown_days,
                                       lt_threshold=lt_threshold, st_threshold=st_threshold)
    latest = zoned.iloc[-1]

    zone = zoned["zone"]
    run_id = (zone != zone.shift(1)).cumsum()
    current_run_length = int((run_id == run_id.iloc[-1]).sum())

    print("=" * 60)
    print(f"TRIM SIGNAL STATUS -- as of {latest['date'].date()}")
    print("=" * 60)
    print(f"BTC price: ${latest['price']:,.0f}")
    print()
    print(f"Long-term composite:  {latest['lt_score']:5.1f}   (rule needs >= {lt_threshold})")
    print(f"Short-term composite: {latest['st_score']:5.1f}   (rule needs <  {st_threshold})")
    print()

    lt_ok = latest["lt_score"] >= lt_threshold
    st_ok = latest["st_score"] < st_threshold
    print(f"Long-term condition met:  {'YES' if lt_ok else 'no'}")
    print(f"Short-term condition met: {'YES' if st_ok else 'no'}")
    print()
    print(f"Raw zone today: {latest['zone']}  (day {current_run_length} of this run)")
    print(f"Confirmed zone: {latest['confirmed_zone']}")
    print()

    if len(signals) > 0:
        print("Last 5 trim signals:")
        print(signals.tail(5).to_string(index=False))
    else:
        print("No trim signals in this history yet.")
    print()
    print("NOTE: this is a ONE-DIRECTIONAL de-risk overlay only -- no validated")
    print("buy-side counterpart exists (the mirrored rule failed out-of-sample")
    print("testing). ~4/year historically, weaker signal strength than a")
    print("stricter/rarer version of this same rule -- see trim_signal.py.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lt-threshold", type=float, default=TRIM_LT_THRESHOLD)
    parser.add_argument("--st-threshold", type=float, default=TRIM_ST_THRESHOLD)
    parser.add_argument("--confirm-days", type=int, default=TRIM_CONFIRM_DAYS)
    parser.add_argument("--cooldown-days", type=int, default=TRIM_COOLDOWN_DAYS)
    args = parser.parse_args()

    print_report(lt_threshold=args.lt_threshold, st_threshold=args.st_threshold,
                 confirm_days=args.confirm_days, cooldown_days=args.cooldown_days)
