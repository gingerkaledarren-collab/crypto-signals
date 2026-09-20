"""
build_dashboard1_altweights_data.py

Produces the JSON blob for a SIDE-BY-SIDE COMPARISON variant of Dashboard 1
-- same three indicators (Fear & Greed, weekly RSI, Bitcoin Supply in
Loss %), same thresholds/confirm-days as the live composite, but weighted
40% F&G / 40% RSI / 20% Supply-in-Loss instead of the live equal 1/3 each.

Requested to see whether tilting weight toward F&G/RSI and away from
Supply-in-Loss changes the picture. Walk-forward testing found it doesn't
help -- it's decisively worse than the live equal-weighting on both TRAIN
and TEST (fresh check, 2026-09-20 data):

    weights                          TRAIN best spread   TEST spread
    live (1/3 / 1/3 / 1/3)           -21.2pp             -2.7pp
    alt  (40% / 40% / 20%)           -21.2pp             -13.3pp

This is NOT a proposed replacement for the live composite -- purely a
comparison artifact so the two can be viewed side by side. See
current_status.py's module docstring and README's "200-week MA distance"
section for why the composite (with either weighting) is already
negative-spread since 200w MA distance was removed.

Run standalone to print the JSON to stdout, or import build_alt_data() and
call it to publish the comparison dashboard.
"""

import json
import argparse
from build_dashboard1_data import build_data

ALT_WEIGHTS = {
    "fng_score": 0.4,
    "rsi_score": 0.4,
    "supply_loss_score": 0.2,
}


def build_alt_data(force_refresh: bool = False) -> dict:
    return build_data(force_refresh=force_refresh, weights=ALT_WEIGHTS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/F&G data")
    args = parser.parse_args()

    print(json.dumps(build_alt_data(force_refresh=args.refresh)))
