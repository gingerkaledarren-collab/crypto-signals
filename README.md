# Crypto Long-Term Signal System (Starter)

A minimal starting point for a long-term BTC positioning signal system.
Currently combines three indicators:

1. **200-week moving average distance** — how far price is above/below
   its 200-week MA, as a proxy for long-term valuation.
2. **Fear & Greed Index** (30-day smoothed) — sentiment extremes.
3. **Weekly RSI** — long-term momentum overbought/oversold gauge,
   computed from weekly closes (not daily, which is too noisy for a
   positioning system).

Both are normalized to a 0-100 "greed scale" and combined into a
composite score. Zone transitions (crossing into buy/sell territory)
are what you'd actually act on, not the daily noise.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Step 1: pull raw data (caches to data/ so you're not re-fetching every run)
python fetch_data.py

# Step 2: inspect the indicator table
python indicators.py

# Step 3: see composite scores + zone transitions
python scoring.py

# Step 4: run the sanity-check backtest against known cycle extremes
python backtest.py
```

## What to look at first

Run `backtest.py` and check two things:

1. **Signal frequency** — does `signals/year` land anywhere near your
   target of 8-10/year, or is it way higher (too noisy) or lower
   (thresholds too strict)?
2. **Alignment with known cycle points** — do the composite scores near
   known cycle lows (Dec 2018, Mar 2020, Nov 2022) actually read low,
   and near known highs (Nov 2021) read high? If not, the indicators
   or thresholds need rethinking before adding more complexity.

## Known limitations (by design, at this stage)

- **Equal weighting is a placeholder.** You said you want to decide
  weights after seeing backtest results — `scoring.py` is built so you
  can pass any weight dict without touching the underlying logic.
- **Thresholds (75/25) are unvalidated guesses**, and a threshold sweep
  (55/45 through 70/30) shows signal frequency plateaus around 3-5/year
  across that whole band rather than scaling smoothly with the
  threshold — see "Threshold tuning findings" below.
- **No walk-forward / out-of-sample testing yet.** This first pass
  checks the whole history at once, which risks fooling you with
  hindsight bias. Once the basic mechanics look sane, the next step
  is splitting history into a "tune" period and a "blind test" period.
- **3 of the ~7 indicators discussed** (200w MA, Fear & Greed, weekly
  RSI). MVRV Z-Score and Puell Multiple need on-chain realized-cap
  data we don't currently have a free source for; BTC dominance and
  Pi Cycle Top are the more reachable next additions.
- **CoinGecko's free tier now hard-caps historical queries at 365
  days** (confirmed via direct API test: `days=max` returns HTTP 401 /
  error_code 10012) — nowhere near enough for a 200-week MA. Price
  history now comes from blockchain.info's market-price chart
  instead, which has no such cap and goes back to 2009.

## Threshold tuning findings

Loosening the sell/buy thresholds from 75/25 down toward 55/45 does
**not** cleanly increase signal frequency the way you'd expect —
across that entire range, actual signals/year stayed in the 2.5-4.6
range and bounced around non-monotonically (e.g. 60/40 produced *more*
transitions than 65/35). The composite score tends to cluster and
briefly flicker back across a threshold rather than moving through the
middle smoothly, so looser thresholds mostly pick up extra whipsaw
noise near the boundary rather than genuinely new, distinct
repositioning opportunities.

Practical takeaways:
- Getting cleanly to 8-10/year probably isn't a pure threshold-tuning
  problem with this indicator set — it likely needs either an added
  "confirmation" rule (score must hold past the threshold for N days
  before it counts as a real signal, filtering the flicker) or more
  independent indicators that move on different timescales.
- It's also worth revisiting whether 8-10/year is the right target
  now that there's real backtest data: 3-5 *genuine* trend-turn
  signals/year (roughly what 65-70/30-35 gives you before whipsaw
  starts dominating) may better match how often BTC's cycle actually
  turns, versus a frequency target picked before seeing the data.

## Next steps

1. Run this, look at the output, see if it's sane.
2. Decide: does F&G (or RSI) add value over the 200w MA alone, or is
   it mostly noise? (Try running with weight 100% on one indicator vs.
   the others and compare.)
3. Add a signal-confirmation rule (e.g. N consecutive days past
   threshold) to filter whipsaw before tuning thresholds further.
4. Add BTC dominance or Pi Cycle Top as a 4th indicator.
5. Build proper walk-forward backtesting before trusting any of this
   with real money decisions.
