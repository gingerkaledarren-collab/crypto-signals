# Crypto Long-Term Signal System (Starter)

A minimal starting point for a long-term BTC positioning signal system.
Currently combines two indicators:

1. **200-week moving average distance** — how far price is above/below
   its 200-week MA, as a proxy for long-term valuation.
2. **Fear & Greed Index** (30-day smoothed) — sentiment extremes.

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
- **Thresholds (75/25) are unvalidated guesses.** The backtest will
  tell you whether these need to move.
- **No walk-forward / out-of-sample testing yet.** This first pass
  checks the whole history at once, which risks fooling you with
  hindsight bias. Once the basic mechanics look sane, the next step
  is splitting history into a "tune" period and a "blind test" period.
- **Only 2 of the ~7 indicators discussed.** MVRV Z-Score, Pi Cycle
  Top, weekly RSI, BTC dominance, and Puell Multiple are natural next
  additions once these two prove out.
- **CoinGecko's free tier** limits price history granularity/length —
  if the 200-week MA doesn't have enough history to populate, that's
  why, and it's a signal we may need a different price data source for
  full historical backtesting.

## Next steps

1. Run this, look at the output, see if it's sane.
2. Decide: does F&G add value over the 200w MA alone, or is it mostly
   noise? (Try running with weight 100% on one indicator vs the other
   and compare.)
3. Add a 3rd indicator (MVRV Z-Score is the natural next pick — it's
   a valuation metric like the 200w MA but computed differently, so it
   tests whether independent-but-related signals add robustness).
4. Build proper walk-forward backtesting before trusting any of this
   with real money decisions.
