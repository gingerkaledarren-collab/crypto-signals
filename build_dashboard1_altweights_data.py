"""
build_dashboard1_altweights_data.py

Produces the JSON blob for a SIDE-BY-SIDE COMPARISON variant of Dashboard 1
-- same four indicators as the live composite (200-week MA distance, Fear
& Greed, weekly RSI, Bitcoin Supply in Loss %), same thresholds/confirm-
days, but weighted 25% / 30% / 30% / 15% instead of the live equal 25%
each -- 200-week MA distance held at the same 25% as live (it's the
indicator that mattered most at the real Oct 2025 all-time high, see
README's "200-week MA distance" section), with the remaining 75% tilted
toward F&G/RSI and away from Supply-in-Loss in the same 40:40:20
proportion originally tested.

Requested to see whether tilting weight toward F&G/RSI and away from
Supply-in-Loss changes the picture. Walk-forward testing found it's a
close call, not a clear win either way (fresh check, 2026-09-20 data,
both with 200-week MA distance included):

    weights                                    TRAIN best spread   TEST spread
    live (25% / 25% / 25% / 25%)               +0.8pp              -1.1pp
    alt  (25% ma200w / 30% / 30% / 15%)        +1.5pp              -5.3pp

Slightly better on TRAIN, worse on TEST -- noise-level differences, not a
signal to change the live weighting. This is NOT a proposed replacement
for the live composite -- purely a comparison artifact so the two can be
viewed side by side. (Earlier version of this comparison, before 200-week
MA distance was restored to the live composite, tested the same F&G/RSI
tilt across just the other three indicators and found it decisively
worse: -21.2pp/-2.7pp live vs. -21.2pp/-13.3pp alt on TRAIN/TEST. See
README's "200-week MA distance" section for the restoration story.)

Run standalone to print the JSON to stdout, or import build_alt_data() and
call it to publish the comparison dashboard.
"""

import json
import argparse
from build_dashboard1_data import build_data

ALT_WEIGHTS = {
    "ma_200w_score": 0.25,
    "fng_score": 0.30,
    "rsi_score": 0.30,
    "supply_loss_score": 0.15,
}


def build_alt_data(force_refresh: bool = False) -> dict:
    return build_data(force_refresh=force_refresh, weights=ALT_WEIGHTS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/F&G data")
    args = parser.parse_args()

    print(json.dumps(build_alt_data(force_refresh=args.refresh)))
