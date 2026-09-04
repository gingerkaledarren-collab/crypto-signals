# Crypto Long-Term Signal System (Starter)

A minimal starting point for a long-term BTC positioning signal system.
The originally validated composite (still what `backtest.py`,
`trim_signal.py`, `portfolio_simulation.py`, and `scoring.DEFAULT_WEIGHTS`
use, and what everything below through "Walk-forward validation" is
about) combines four indicators:

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

A 5th indicator, **21w/34w EMA structure** (`indicators.compute_ema_structure`),
is also computed but deliberately left OUT of the default composite —
see "Why the EMA structure indicator isn't in the default weighting"
below for why.

**The live dashboard and `current_status.py` use a different composite**
(`current_status.LIVE_WEIGHTS`): Pi Cycle Top removed, Bitcoin Supply in
Loss % added in its place, by explicit request. This is NOT the
validated composite above -- see "Removing Pi Cycle Top, adding Supply
in Loss %" for the full walk-forward comparison and an honest number:
this specific combination tests as having essentially no validated
forward-return signal. It's live anyway, the same way Dashboard 2
already ships a composite that isn't separately validated.

## Data sources

BTC price comes from blockchain.info's charts API (free, no key, full
history back to 2010).

Fear & Greed is blended from two sources, by request: **alternative.me**
(free, keyless, public API) for all dates before ~June 2023, and
**CoinMarketCap** from that point forward, considered more accurate
day-to-day. CMC has no free/keyless *official* API for this index --
it's gated behind a paid Pro API key -- so `fetch_data.py` instead calls
the internal endpoint CMC's own website frontend uses. That's an
unofficial, undocumented dependency that could change or get blocked
without notice, and its own history only goes back to ~June 2023, which
is why it's blended onto alternative.me's longer history rather than
replacing it outright -- a full switch would have left the 2018-2023
walk-forward training window with no Fear & Greed input at all. If
CMC's endpoint fails, `fetch_fear_greed_history()` falls back to
alternative.me's full history alone rather than hard-failing.

Bitcoin Supply in Loss % comes from **BGeometrics**. Same shape of
caveat as CMC above: no free/keyless official API exists for this
metric (paid Pro API key only), so `fetch_supply_in_profit_history()`
calls the static JSON file BGeometrics' own free chart page fetches for
anonymous viewers -- unofficial and undocumented, could change or break
without notice. Unlike CMC's Fear & Greed endpoint, though, this one
has a long history (2014-present, ~1 day lag), so no blending was
needed. The fetched series is "% of supply in PROFIT" (confirmed
against known dates: 96.9% at the Nov 2021 ATH, 44.9% at the Nov 2022
capitulation low); loss% = 100 minus that value, computed in
`indicators.compute_supply_in_loss()`.

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

# Step 5: proper out-of-sample check (tune on early history, test blind on later history)
python walkforward.py

# Step 6: check where things stand TODAY (the one to actually run periodically)
python current_status.py --refresh

# Step 7: the second, faster system -- validation, then today's status
python trim_walkforward.py
python trim_current_status.py
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

## Checking today's signal (`current_status.py`)

Everything above answers "does this work on history." `current_status.py`
answers the question you actually check periodically: what does the
system say RIGHT NOW. It prints today's price, each indicator's score,
the composite, whether you're in a confirmed buy/sell zone (and how many
days into that run), and the last 3 confirmed signals for context.

```bash
python current_status.py --refresh   # --refresh pulls fresh data instead of using the cache
```

Defaults to the walk-forward-selected config (sell=60, buy=40, confirm
after 5 days) since that's the most rigorously chosen starting point so
far — override with `--sell`, `--buy`, `--confirm-days` to try others.

It also reports **extreme zone** status — see the next section.

## Extreme zone history (separate from buy_zone/sell_zone)

The 40/60 buy_zone/sell_zone thresholds (`flag_zones()`) were chosen for
walk-forward *predictive* value, not for marking rarity — the composite
crosses 40/60 fairly often (that's what let it hit ~3-4 confirmed
signals/year). Sometimes what you actually want to know is simpler: has
this reading historically been unusual at all?

`scoring.flag_extreme_zones()` answers that directly from the data: it
computes `extreme_low`/`extreme_high` from `EXTREME_LOW_THRESHOLD` (20)
and `EXTREME_HIGH_THRESHOLD` (70) — thresholds set from the actual
historical distribution of `composite_score` (2018-present), where they
land almost exactly on the 10th and 90th percentiles. So "extreme" here
means "in the rarest ~10% of readings, historically" — a plain fact about
the score's distribution, not a claim about predictive value like the
buy/sell thresholds. No confirmation delay is applied (unlike
buy_zone/sell_zone) since sitting in the most extreme decile is already a
rare, meaningful event on its own.

**Deliberately not called "extreme fear"/"extreme greed."** The composite
blends four things — 200w MA distance (valuation), the actual Fear & Greed
Index (sentiment), weekly RSI (momentum), and Pi Cycle Top ratio (a
price-ratio cycle-top signal) — and only one of those four is literally
sentiment. Labeling the composite's tails "fear"/"greed" would borrow an
emotional claim that's only true for a quarter of what feeds it. (The
0-100 "greed scale" *convention* used for each individual indicator's
own normalization, inherited from the Fear & Greed Index's own scale, is
a separate, pre-existing choice documented in `indicators.py` — this
extreme-zone feature is the one place that convention would have been
actively misleading if carried through literally, so it isn't here.)

`scoring.extract_extreme_periods()` groups consecutive extreme days into
date ranges rather than a raw day-by-day list — 22 episodes since 2018,
from single-day spikes to the 188-day extreme-high stretch spanning the
Nov 2020-May 2021 blow-off run. Both `current_status.py` (a text summary)
and the dashboard artifact (a dedicated "Extreme zone history" table) show
this. On the dashboard it's deliberately styled as outlined pills, not the
filled pills used for buy_zone/sell_zone, so it doesn't visually read as
"another kind of trading signal" — it's historical context, not a call to
action.

## Walk-forward validation (`walkforward.py`)

The backtests above all tune and evaluate on the full history at once,
which risks hindsight bias — you can always find a threshold that
looks great on data you've already seen. `walkforward.py` fixes that:

1. Splits history chronologically: **train** = 2018-02 to 2023-08
   (covers a full cycle: 2018 bottom, 2021 top, 2022 bottom), **test**
   = 2023-08 to 2026-08 (the 2023-2025 bull run and current pullback —
   genuinely different market structure the config never saw).
2. Sweeps threshold/confirmation configs on TRAIN ONLY, scored by a
   real predictive-value metric: average 90-day forward return
   following confirmed buy-zone days minus the same following
   sell-zone days. A working contrarian signal should show buy > sell.
3. Freezes the best TRAIN config and applies it to TEST with **no
   further tuning** — the actual blind, out-of-sample check.

**Result:** best TRAIN config (sell=60, buy=40, confirm=5d) showed a
+10.3pp spread (buy-zone days: +22.4% fwd return; sell-zone: +12.1%).
Applied unchanged to TEST, the spread held up at +9.3pp (buy-zone:
+4.6%; sell-zone: -4.7%) — the buy/sell direction is genuinely
out-of-sample, not an artifact of fitting to one period.

**Important caveat found in the same run:** in the TEST window,
"neutral" days averaged +24.8% forward return — better than buy-zone,
sell-zone, *and* the all-days baseline (+10.8%, roughly buy-and-hold
for that horizon). A lot of the 2023-2025 bull run sat in the neutral
40-60 band rather than registering as extreme greed, so simply holding
through neutral periods outperformed acting on this system's sell
signals in that specific window. Treat this less as "sell fully at
sell-zone, sit in cash otherwise" and more as a risk-reduction/trim
signal at genuine extremes — not a return-maximizer on its own. Also
worth noting the 90-day forward-return horizon is a specific choice;
re-running with 30d/180d horizons could tell a different story and is
worth trying before trusting this further.

## Why the EMA structure indicator isn't in the default weighting

`indicators.compute_ema_structure()` adds the 21-week / 34-week EMA
support structure popularized by trader Alessio Rastani: holding above
the 21w EMA reads as bullish support, losing it but holding the 34w EMA
is a caution zone, losing the 34w EMA too confirms a deeper bearish
structure (Fibonacci-sequence periods, consistent with his Elliott Wave
approach). It's fully computed and available as `ema_structure_score`.

It was added to `DEFAULT_WEIGHTS` at equal weight (5-way, 20% each) and
re-run through `walkforward.py` as a real test, per this project's own
rule of deciding weights from backtest evidence, not assumption. The
result was worse, not better:

| | 4 indicators (current default) | 5 indicators (+ EMA structure) |
|---|---|---|
| Best TRAIN spread | +10.3pp | +0.9pp |
| TEST (out-of-sample) buy-zone fwd return | +4.6% | **-4.1%** |
| TEST spread | +9.3pp | +3.7pp |

Adding it nearly erased the TRAIN signal and flipped the TEST buy-zone
forward return negative. The likely reason: EMA structure is a trend-
**following** signal (it reads high while price rides comfortably above
a rising fast EMA, i.e. mid-trend) whereas the other four are all
extremes/mean-reversion flavored (how far price has stretched from a
slow anchor, sentiment extremes, momentum extremes, a cycle-top cross).
Blending a "we're trending" signal into an "is this an extreme"
composite dilutes exactly what the composite is for.

It's kept out of `DEFAULT_WEIGHTS` as a result, but still computed and
shown as **context** in `current_status.py` (whether price currently
holds its 21w/34w EMA support) since that's a genuinely useful,
independent read even when it doesn't belong in the composite. If you
want to experiment with it anyway, pass a custom weights dict to
`compute_composite_score()` — that's exactly what the adjustable-weights
design in `scoring.py` is for.

## Removing Pi Cycle Top, adding Supply in Loss % (live dashboard only)

By explicit request, `current_status.LIVE_WEIGHTS` -- what the live
dashboard and `current_status.py`'s CLI actually use -- diverges from
`scoring.DEFAULT_WEIGHTS` above: Pi Cycle Top is removed, Bitcoin Supply
in Loss % (`indicators.compute_supply_in_loss()`, see "Data sources")
is added in its place. Both changes were walk-forward tested first;
neither survived the test, and the combination is live anyway.

**Pi Cycle Top removal.** The trigger was a real observation: the raw
ratio hasn't crossed its own "top" threshold (1.0) since April 2021, and
`pi_cycle_score` stayed low (27-46/100) even at brand-new nominal ATHs
since then ($71k in 2024, $106-117k in 2025) -- worth knowing, and it
does look like the indicator's calibration has drifted from the
post-2021 market. But removing it from the composite (weight
redistributed equally to the other three) doesn't just "remove dead
weight":

| | 4 indicators (original, with Pi Cycle) | 3 indicators (Pi Cycle removed) |
|---|---|---|
| Best TRAIN config | sell=60, buy=40, confirm=5d | sell=55, buy=45, confirm=5d |
| TRAIN spread | +10.3pp | +10.0pp (looks fine) |
| **TEST spread (blind)** | **+10.3pp** | **-0.4pp** (inverted) |

TRAIN alone makes removal look harmless. Blind, the TRAIN-selected
config collapses to noise (buy_ret 5.7% vs. sell_ret 6.0%) -- the same
overfitting signature flagged elsewhere in this README (the rejected
buy-side mirror in `trim_signal.py`). Pi Cycle's continuous score
appears to be doing real calibration work that generalizes out-of-
sample, despite the raw ratio itself not having crossed 1.0 in years.

**Supply in Loss % addition.** Tested at three weights, added to the
*original* 4-indicator composite (i.e. before Pi Cycle was removed):

| Weight on supply_loss_score | Best TRAIN spread |
|---|---|
| 0% (baseline) | +10.3pp |
| 10% | +8.8pp |
| 15% | +7.2pp |
| 20% (equal 5-way) | +4.6pp |

Monotonic degradation at every weight tried -- the same pattern Pi
Cycle Top's removal showed, and the same outcome as the EMA structure
indicator above: a real, independently interesting metric that doesn't
add validated signal on top of what's already in the composite (most
likely correlated enough with 200w MA distance to mostly add noise).

**The combination actually shipped** (Pi Cycle removed AND Supply Loss
added, `LIVE_WEIGHTS`: 200w MA, F&G, weekly RSI, Supply Loss at 25%
each) is worse than either change alone -- not an overfit that looks
good on TRAIN and fails blind, but weak on **both**:

| | Original (MA+F&G+RSI+Pi Cycle) | LIVE_WEIGHTS (MA+F&G+RSI+SupplyLoss) |
|---|---|---|
| Best TRAIN config | sell=60, buy=40, confirm=5d | sell=60, buy=40, confirm=5d |
| TRAIN spread | +10.3pp | **+0.9pp** |
| TEST spread | +10.3pp | **+0.8pp** |

At the best config found, buy-zone and sell-zone forward returns are
almost identical (22.6% vs. 21.7% on TRAIN) -- this isn't overfitting,
it's closer to no signal at all by this test's own metric. It's live
anyway, by explicit request, the same way Dashboard 2 already ships a
technicals-based composite that isn't separately validated. Thresholds
(sell=60, buy=40, confirm=5d) were re-selected via the standard TRAIN
sweep for this specific composite, not just inherited from the original
-- they happen to land on the same numbers.

`scoring.DEFAULT_WEIGHTS` (unchanged, still Pi-Cycle-based) is what
`backtest.py`, `trim_signal.py`, `trim_walkforward.py`, and
`portfolio_simulation.py` continue to use -- none of that documented
research silently changed underneath it.

## The second system: short-term signal (`st_backtest.py`)

Everything above is one system (~3-5 signals/year, symmetric buy/sell,
statistically validated). This is a genuinely separate, second system
built for a faster, ~8-10x/year cadence, with its own dashboard artifact.
It went through several iterations -- worth knowing what was tried and
rejected before the current version, and being clear about what changed
between "validated" and "current":

1. **A standalone short-term momentum composite** (`st_indicators.py`:
   50-day MA distance, daily RSI, Bollinger %B, 5-day-smoothed Fear &
   Greed) was tested first as a CONTRARIAN signal. It failed BACKWARDS:
   "overbought" readings preceded LARGER subsequent gains than
   "oversold" readings, at every forward horizon from 7 to 120 days,
   confirmed out-of-sample (`st_walkforward.py`). Short-lookback
   technicals measure trend strength in BTC's history, not exhaustion.
2. **Gating that composite by the long-term composite's state** found
   one construction that DID validate out-of-sample: long-term expensive
   (>=50) AND short-term momentum gone quiet (<70) preceded genuinely
   weaker forward returns (TRAIN +20.7pp, TEST +8.6pp spread, 90-day
   horizon). But it was one-directional (trim only -- a mirrored buy-side
   rule inverted out-of-sample) and rare (~4/year at these thresholds,
   ~2/year at a stricter, more strongly-validated version). This
   construction still exists in `trim_signal.py`/`trim_walkforward.py`/
   `trim_current_status.py` and is real, tested research -- just no
   longer what the second dashboard shows.
3. **A portfolio simulation** (`portfolio_simulation.py`) layering small
   partial trims/adds from this construction onto a $50K BTC / $20K cash
   plan found, on ablation, that the short-term layer actively HURT
   results over the most recent 2-year window versus the long-term
   signal alone ($89,224 vs $95,652) -- a third independent confirmation
   that this specific short-lookback construction doesn't add reversal-
   predicting value in BTC's history, however it's combined.

**Current version, by explicit request:** rather than continue requiring
the same statistical bar as the long-term system, the second dashboard
now uses `st_backtest.py`'s symmetric buy/sell-zone composite --
50-day MA distance, daily RSI(14), Bollinger %B(20), MACD histogram
(12/26/9), and Fear & Greed (5d smoothed, 30% weight, `ST_DEFAULT_WEIGHTS`),
at sell>=70/buy<=30/confirm=3d/cooldown=14d, tuned to land at ~9
signals/year. This is a **technicals-based practical tool, not a
separately validated signal** -- the same momentum indicators that
failed as a contrarian signal in points 1-3 above are its core inputs,
used here by deliberate choice rather than as a claim they predict
reversals. Run `python st_current_status.py` for today's reading.

## Keeping the dashboards current

The two published Artifacts ("Signal Dashboard" and "Short-Term Signal")
are static HTML snapshots with the data baked in at publish time -- they
don't fetch anything live in the viewer's browser, so they stay frozen
on whatever date they were last generated.

To refresh both with today's data:

```
python build_dashboards.py --refresh
```

This force-refreshes the cached price/Fear & Greed data, recomputes
both composites via `build_dashboard1_data.py` / `build_dashboard2_data.py`,
and writes `dashboard_output/dashboard1.html` and
`dashboard_output/dashboard2.html` from `dashboard1_template.html` /
`dashboard2_template.html`. A Claude session then needs to publish those
two files to the existing Artifact URLs (the Artifact tool isn't callable
from plain Python) -- that's the step a daily Routine automates: it fires
into a fresh session once a day, runs the command above, and republishes
each output file to its fixed URL so the link stays the same and just
shows fresher numbers.

## Next steps

1. Run this, look at the output, see if it's sane.
2. Try other forward-return horizons in `walkforward.py` (30d, 180d)
   to see how sensitive the train/test result is to that choice.
3. Decide how the system should actually be used given the neutral-
   period finding above — full position sizing on zone, or a trim/add
   overlay on top of a base long-term hold.
4. Only after that: consider paying for an on-chain data source
   (Glassnode, CoinMetrics) to add MVRV Z-Score, Puell Multiple, or
   BTC dominance.
5. The trim signal (above) has no validated buy-side counterpart --
   if a genuine add/reload signal is wanted later, it needs the same
   out-of-sample rigor this one went through, not a symmetric guess.
