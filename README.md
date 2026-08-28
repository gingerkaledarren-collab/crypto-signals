# Crypto Long-Term Signal System (Starter)

A minimal starting point for a long-term BTC positioning signal system.
Currently combines four indicators:

1. **200-week moving average distance** — how far price is above/below
   its 200-week MA, as a proxy for long-term valuation.
2. **Fear & Greed Index** (30-day smoothed) — sentiment extremes.
3. **Weekly RSI** — long-term momentum overbought/oversold gauge,
   computed from weekly closes (not daily, which is too noisy for a
   positioning system).
4. **Pi Cycle Top ratio** (111-day SMA vs. 2x 350-day SMA) — a
   well-known price-only cycle-top indicator, computable without any
   on-chain data.

All four are normalized to a 0-100 "greed scale" and combined into a
composite score. Zone transitions (crossing into buy/sell territory,
then *holding* for a minimum number of days — see "confirmation rule"
below) are what you'd actually act on, not the daily noise.

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
- **4 of the ~7 indicators discussed** (200w MA, Fear & Greed, weekly
  RSI, Pi Cycle Top ratio). MVRV Z-Score, Puell Multiple, and BTC
  dominance all need data (on-chain realized cap, or market cap across
  every coin) we don't currently have a free source for.
- **CoinGecko's free tier now hard-caps historical queries at 365
  days** (confirmed via direct API test: `days=max` returns HTTP 401 /
  error_code 10012) — nowhere near enough for a 200-week MA. Price
  history now comes from blockchain.info's market-price chart
  instead, which has no such cap and goes back to 2009.

## Confirmation rule (filtering whipsaw)

`scoring.apply_confirmation()` requires the raw zone to hold for
`min_confirm_days` CONSECUTIVE days before it counts as a real signal
(`backtest.run_basic_backtest()` defaults to 5). This exists because the
raw threshold sweep below showed the composite score clustering and
briefly flickering back across a threshold rather than moving through
cleanly — without confirmation, looser thresholds mostly added whipsaw
noise near the boundary, not genuinely new repositioning opportunities.

## Threshold + confirmation tuning findings

With the original 3-indicator composite, loosening 75/25 toward 55/45
alone was non-monotonic and noisy (2.5-4.6 signals/year, no clean
trend). Adding Pi Cycle Top as a 4th indicator and pairing threshold
loosening WITH the confirmation rule fixed that — frequency now scales
sensibly with looseness instead of bouncing around:

| sell/buy | confirm days | confirmed signals/year |
|----------|--------------|-------------------------|
| 75/25    | 0            | 1.2 |
| 70/30    | 3            | 1.5 |
| 65/35    | 5            | 2.2 |
| 65/35    | 3            | 2.6 |
| 60/40    | 5            | 2.7 |
| 60/40    | 3            | 2.8 |
| 55/45    | 3            | 3.4 |

Practical takeaways:
- **The confirmation rule is what made threshold tuning meaningful** —
  it's the fix, not just an add-on. Tune thresholds on the *confirmed*
  signal count, not the raw one.
- **Adding Pi Cycle Top lowered frequency further** at strict
  thresholds (75/25 dropped from ~2.5/yr with 3 indicators to ~1.2/yr
  with 4), because it sits in the 30-60 range outside real blow-off
  tops, pulling the average down. It didn't "miss" the April/Nov 2021
  tops though — both fall inside one continuous sell-zone run that
  started in Nov 2020, which is arguably the *right* behavior for a
  long-term system (stay positioned to sell through an extended
  euphoric phase rather than re-signaling every few weeks).
- **8-10/year still isn't reached anywhere in this range** without
  pushing thresholds close to 50/50, at which point they stop meaning
  anything as "extremes." Worth revisiting the target itself: 3-5
  *genuine, confirmed* trend-turn signals/year (roughly the 60-65/35-40
  band above) looks like a more realistic cadence for how often BTC's
  cycle actually turns, versus a frequency picked before seeing real
  backtest data.

## Next steps

1. Run this, look at the output, see if it's sane.
2. Decide on final weights/thresholds using the confirmed-signal
   counts above, not raw ones.
3. Build proper walk-forward / out-of-sample backtesting — everything
   so far has been tuned by looking at the whole history at once,
   which risks hindsight bias.
4. Only after walk-forward validation looks sound: consider paying for
   an on-chain data source (Glassnode, CoinMetrics) to add MVRV
   Z-Score, Puell Multiple, or BTC dominance.
