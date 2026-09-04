"""
indicators.py

Computes the actual indicator values from raw data, and normalizes each
one to a 0-100 "greed scale" so they're comparable and combinable later.

Normalized scale convention (matches Fear & Greed's own convention):
  0   = extreme fear / extremely undervalued -> historically a buy zone
  100 = extreme greed / extremely overvalued -> historically a sell zone
"""

import datetime as dt
import pandas as pd
import numpy as np

# Named so the dashboard's JS can derive the same raw-value buy/sell
# thresholds these normalizers use (for horizontal reference bands on
# each indicator's own chart) without hardcoding the calibration twice.
SUPPLY_LOSS_CLIP_RANGE = (1.5, 54.7)
MVRV_CLIP_RANGE = (0.9, 2.5)

# Bitcoin reward-halving dates -- the anchor points for the ~4-year cycle
# phase label. This needs no external data source, just the calendar.
HALVING_DATES = [
    dt.date(2012, 11, 28),
    dt.date(2016, 7, 9),
    dt.date(2020, 5, 11),
    dt.date(2024, 4, 20),
]


def compute_cycle_context(as_of: dt.date) -> dict:
    """
    Labels roughly where `as_of` sits in the ~4-year halving cycle, based on
    when the three completed cycles (2012/2016/2020 halvings) topped and
    bottomed relative to their halving date: tops landed ~12-19 months
    (365-580 days) post-halving, bottoms landed ~24-32 months (730-970
    days) post-halving.

    This is CONTEXT ONLY. It does not feed the composite score or any
    buy/sell zone, and it is not walk-forward tested -- with only 3
    completed cycles to draw the phase boundaries from, there isn't enough
    history to validate this the way the other indicators were. Treat the
    phase label as a rough historical-pattern marker, not a signal.
    """
    past_halvings = [h for h in HALVING_DATES if h <= as_of]
    last_halving = max(past_halvings) if past_halvings else HALVING_DATES[0]
    days_since = (as_of - last_halving).days

    if days_since < 365:
        phase = "Early post-halving (historically accumulation)"
    elif days_since < 580:
        phase = "Historical cycle-top window (~12-19mo post-halving)"
    elif days_since < 730:
        phase = "Post-top distribution (historically)"
    elif days_since < 970:
        phase = "Historical cycle-bottom window (~24-32mo post-halving)"
    elif days_since < 1460:
        phase = "Late-cycle re-accumulation (historically)"
    else:
        phase = "Approaching next halving"

    return {
        "last_halving": last_halving.isoformat(),
        "days_since_halving": days_since,
        "phase": phase,
        "wyckoff_phase": _wyckoff_phase_for_days(days_since),
    }


def _wyckoff_phase_for_days(days_since_halving: int) -> str:
    """
    Collapses compute_cycle_context()'s 6-way day-count bucketing into the
    4 classic Wyckoff market-cycle phases (accumulation/markup/distribution/
    markdown), by request, for chart shading. "Late-cycle re-accumulation"
    and the very start of the next cycle share the "accumulation" label --
    Wyckoff's own cycle wraps accumulation -> markup -> distribution ->
    markdown -> accumulation, so treating the run-up to a halving and the
    period just after it as the same phase matches that wraparound rather
    than resetting mid-phase at the halving date itself.
    """
    if days_since_halving < 365:
        return "accumulation"
    elif days_since_halving < 580:
        return "markup"
    elif days_since_halving < 730:
        return "distribution"
    elif days_since_halving < 970:
        return "markdown"
    else:
        return "accumulation"


def compute_wyckoff_phases(dates: pd.Series) -> pd.Series:
    """
    Vectorized per-date version of compute_cycle_context()'s wyckoff_phase,
    for shading a whole price history rather than just labeling "today".
    Same CONTEXT ONLY caveat applies -- see compute_cycle_context().
    """
    def _phase(d):
        as_of = d.date() if hasattr(d, "date") else d
        past_halvings = [h for h in HALVING_DATES if h <= as_of]
        last_halving = max(past_halvings) if past_halvings else HALVING_DATES[0]
        days_since = (as_of - last_halving).days
        return _wyckoff_phase_for_days(days_since)
    return dates.apply(_phase)


def compute_200w_ma_distance(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes the 200-week moving average (= 1400 days) and the price's
    % distance above/below it.

    NOTE: this needs ~4 years of price history to produce values from
    day 1 of your analysis window. With less history, the early portion
    of the series will be NaN until the rolling window fills.

    Returns df with columns: date, price, ma_200w, pct_distance
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    window_days = 200 * 7  # 1400 days

    df["ma_200w"] = df["price"].rolling(window=window_days, min_periods=window_days).mean()
    df["pct_distance"] = (df["price"] - df["ma_200w"]) / df["ma_200w"] * 100

    return df[["date", "price", "ma_200w", "pct_distance"]]


def normalize_200w_distance(pct_distance: pd.Series, clip_range: tuple = (-40, 150)) -> pd.Series:
    """
    Maps % distance from 200w MA to a 0-100 greed scale.

    Calibration note: historically BTC has traded from roughly -40% below
    its 200w MA (deep bear capitulation) to +150%+ above it (late-cycle
    euphoria, e.g. 2017/2021 tops). These clip bounds are a starting
    assumption -- once we backtest against full cycle history we should
    revisit them using actual percentile distributions rather than
    eyeballed bounds.
    """
    lo, hi = clip_range
    clipped = pct_distance.clip(lower=lo, upper=hi)
    normalized = (clipped - lo) / (hi - lo) * 100
    return normalized


def smooth_fear_greed(fng_df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """
    Applies a rolling average to the daily Fear & Greed Index to reduce
    day-to-day noise, since raw daily F&G can whipsaw and isn't meant
    for a long-term positioning system on its own.

    Returns df with columns: date, fng_value, fng_smoothed
    """
    df = fng_df.copy().sort_values("date").reset_index(drop=True)
    df["fng_smoothed"] = df["fng_value"].rolling(window=window, min_periods=1).mean()
    return df[["date", "fng_value", "fng_smoothed"]]


def compute_pi_cycle_ratio(price_df: pd.DataFrame, short_window: int = 111, long_window: int = 350) -> pd.DataFrame:
    """
    Computes the Pi Cycle Top ratio: 111-day SMA / (2 x 350-day SMA).

    This is a well-known price-only cycle-top indicator -- historically,
    the 111-day SMA crossing above 2x the 350-day SMA (ratio crossing 1.0)
    has closely marked BTC cycle tops. It needs only price data, unlike
    MVRV Z-Score/Puell Multiple which need on-chain realized-cap data we
    don't have a free source for.

    Returns df with columns: date, sma_111, sma_350x2, pi_cycle_ratio
    """
    df = price_df.copy().sort_values("date").reset_index(drop=True)
    df["sma_111"] = df["price"].rolling(window=short_window, min_periods=short_window).mean()
    df["sma_350x2"] = df["price"].rolling(window=long_window, min_periods=long_window).mean() * 2
    df["pi_cycle_ratio"] = df["sma_111"] / df["sma_350x2"]
    return df[["date", "sma_111", "sma_350x2", "pi_cycle_ratio"]]


def normalize_pi_cycle_ratio(ratio: pd.Series, clip_range: tuple = (0.35, 1.05)) -> pd.Series:
    """
    Maps the Pi Cycle ratio to a 0-100 greed scale.

    Calibration note: historically (2011-present) this ratio has run from
    ~0.30 (deep capitulation) up to ~1.47 (2013 blow-off top), with the
    classic "top signal" cross at ratio=1.0. Clip bounds are set from the
    ~5th/95th percentiles of that history, so ratio=1.0 lands around a
    score of ~90 (strong but not maximal greed) rather than pinning to 100.
    """
    lo, hi = clip_range
    clipped = ratio.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def compute_weekly_rsi(price_df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Computes RSI on WEEKLY closes (not daily) -- daily RSI is a momentum
    indicator too noisy for a positioning system, but the weekly version
    is a standard long-term overbought/oversold gauge and needs only the
    price series we already have (no on-chain data required).

    Uses Wilder's smoothing (the standard RSI method) via an EWM with
    alpha=1/period.

    Returns df with columns: date, weekly_rsi
    Note: 'date' here is the week-ending date each weekly bar is labeled with.
    """
    weekly = price_df.copy().set_index("date")["price"].resample("W").last().dropna()
    delta = weekly.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.rename("weekly_rsi").reset_index()


def compute_ema_structure(price_df: pd.DataFrame, fast_window: int = 21, slow_window: int = 34) -> pd.DataFrame:
    """
    Computes the 21-week / 34-week EMA support structure popularized by
    trader Alessio Rastani for reading BTC's weekly trend: holding above
    the 21w EMA is read as bullish support, losing it but holding the 34w
    EMA is a caution zone, and losing the 34w EMA too confirms a deeper
    bearish structure. Fibonacci-sequence periods, consistent with his
    Elliott Wave-based approach. Computed on WEEKLY closes, not daily.

    Returns df with columns: date, ema_21w, ema_34w, pct_distance_21w
    ('date' is the week-ending date, like compute_weekly_rsi.)
    """
    weekly = price_df.copy().set_index("date")["price"].resample("W").last().dropna()
    ema_fast = weekly.ewm(span=fast_window, adjust=False).mean()
    ema_slow = weekly.ewm(span=slow_window, adjust=False).mean()
    pct_distance_21w = (weekly - ema_fast) / ema_fast * 100

    return pd.DataFrame({
        "date": weekly.index,
        "ema_21w": ema_fast.values,
        "ema_34w": ema_slow.values,
        "pct_distance_21w": pct_distance_21w.values,
    })


def normalize_ema_structure(pct_distance_21w: pd.Series, clip_range: tuple = (-25, 45)) -> pd.Series:
    """
    Maps price's % distance from the 21w EMA to a 0-100 greed scale.

    Calibration note: within our 2018-present analysis window, this
    distance has run from about -40% (deep weekly-trend breakdowns) to
    +75%+ (blow-off extensions), with the 5th/95th percentiles landing
    around -26%/+46%. Clip bounds are set from that, same approach as
    the 200w MA and Pi Cycle normalizers. The 34w EMA isn't separately
    weighted in the composite -- it's highly correlated with the 21w EMA
    (only 13 weeks apart), so it's tracked and surfaced as a secondary
    reference level (see current_status.py) rather than double-counted.
    """
    lo, hi = clip_range
    clipped = pct_distance_21w.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def compute_supply_in_loss(supply_profit_df: pd.DataFrame) -> pd.DataFrame:
    """
    Bitcoin's % of circulating supply currently underwater relative to
    its last-moved (realized) price -- an on-chain capitulation/euphoria
    gauge, distinct from the price-only/sentiment indicators above.

    supply_profit_df comes from fetch_supply_in_profit_history(), which
    fetches "% of supply in PROFIT" (see that function's docstring for
    why); this just flips it to loss%, which is the metric actually
    wanted here.

    Returns df with columns: date, supply_in_loss_pct
    """
    df = supply_profit_df.copy().sort_values("date").reset_index(drop=True)
    df["supply_in_loss_pct"] = 100 - df["supply_in_profit_pct"]
    return df[["date", "supply_in_loss_pct"]]


def normalize_supply_in_loss(supply_in_loss_pct: pd.Series, clip_range: tuple = SUPPLY_LOSS_CLIP_RANGE) -> pd.Series:
    """
    Maps supply-in-loss % to the 0-100 greed scale. Since HIGH loss% means
    capitulation (fear/undervalued) and LOW loss% means euphoria (greed/
    overvalued), this is an inverted rescale relative to the other
    normalizers here -- high input -> low score, not high -> high.

    Clip bounds are the ~5th/95th percentiles of the full 2014-present
    history (0.2 to 64.2 actual min/max): at loss%<=1.5 score saturates
    at 100 (as euphoric as this metric gets), at loss%>=54.7 it saturates
    at 0 (as capitulated as this metric gets historically).
    """
    lo, hi = clip_range
    clipped = supply_in_loss_pct.clip(lower=lo, upper=hi)
    return (hi - clipped) / (hi - lo) * 100


def normalize_mvrv(mvrv_ratio: pd.Series, clip_range: tuple = MVRV_CLIP_RANGE) -> pd.Series:
    """
    Maps the MVRV ratio (market cap / realized cap) to the 0-100 greed
    scale directly -- unlike supply-in-loss, no inversion needed: high
    MVRV already means euphoria/greed (most of the network sitting on
    large unrealized gains), low/near-1 MVRV already means capitulation.

    Clip bounds are the ~5th/95th percentiles of BGeometrics' available
    history (Sept 2022-present only -- see fetch_mvrv_history()'s
    docstring for why this metric's free history is so much shorter than
    the others here). At mvrv<=0.9 score floors at 0, at mvrv>=2.5 it
    caps at 100.
    """
    lo, hi = clip_range
    clipped = mvrv_ratio.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo) * 100


def build_indicator_table(price_df: pd.DataFrame, fng_df: pd.DataFrame, fng_window: int = 30,
                           supply_profit_df: pd.DataFrame = None, mvrv_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Joins all indicators into a single date-aligned table, with each
    indicator normalized to the 0-100 greed scale.

    fng_window: smoothing window for Fear & Greed, in days. Default (30)
    is the live system's validated setting. Exposed as a parameter so
    the daily/no-smoothing variant can be walk-forward tested (see
    README's "Testing daily (unsmoothed) Fear & Greed") without a
    second code path -- fng_window=1 is exactly "no smoothing" since
    smooth_fear_greed()'s rolling(window=1) is a no-op.

    supply_profit_df: optional, from fetch_supply_in_profit_history(). If
    given, adds supply_loss_score (see compute_supply_in_loss()) to the
    table. Not in scoring.DEFAULT_WEIGHTS (only current_status.LIVE_WEIGHTS
    -- see README's "Removing Pi Cycle Top, adding Supply in Loss %").
    Omitted by default so existing callers are unaffected.

    mvrv_df: optional, from fetch_mvrv_history(). If given, adds
    mvrv_score (see normalize_mvrv()) to the table. Its history only
    starts ~Sept 2022, so rows before that get NaN here -- by design,
    not a bug (see README's "Adding MVRV Ratio despite its short
    history"). Also not in scoring.DEFAULT_WEIGHTS.

    Returns df with columns:
      date, price, ma_200w, pct_distance, ma_200w_score,
      fng_value, fng_smoothed, fng_score, weekly_rsi, rsi_score,
      sma_111, sma_350x2, pi_cycle_ratio, pi_cycle_score,
      ema_21w, ema_34w, pct_distance_21w, ema_structure_score,
      [supply_in_profit_pct, supply_in_loss_pct, supply_loss_score if supply_profit_df given]
      [mvrv_ratio, mvrv_score if mvrv_df given]
    """
    ma_df = compute_200w_ma_distance(price_df)
    ma_df["ma_200w_score"] = normalize_200w_distance(ma_df["pct_distance"])

    fng_smooth_df = smooth_fear_greed(fng_df, window=fng_window)
    fng_smooth_df["fng_score"] = fng_smooth_df["fng_smoothed"]  # already 0-100

    merged = pd.merge(ma_df, fng_smooth_df, on="date", how="inner")

    # merge_asof(direction="backward") attaches each daily row the most
    # recently COMPLETED weekly bar -- never a bar that hasn't closed
    # yet as of that date, so this doesn't leak future data into the past.
    rsi_df = compute_weekly_rsi(price_df)
    merged = pd.merge_asof(
        merged.sort_values("date"), rsi_df.sort_values("date"), on="date", direction="backward"
    )
    merged["rsi_score"] = merged["weekly_rsi"]  # already 0-100, same convention

    pi_df = compute_pi_cycle_ratio(price_df)
    pi_df["pi_cycle_score"] = normalize_pi_cycle_ratio(pi_df["pi_cycle_ratio"])
    merged = pd.merge(merged, pi_df[["date", "sma_111", "sma_350x2", "pi_cycle_ratio", "pi_cycle_score"]],
                       on="date", how="inner")

    ema_df = compute_ema_structure(price_df)
    ema_df["ema_structure_score"] = normalize_ema_structure(ema_df["pct_distance_21w"])
    merged = pd.merge_asof(
        merged.sort_values("date"), ema_df.sort_values("date"), on="date", direction="backward"
    )

    if supply_profit_df is not None:
        # backward merge_asof, not an inner join: the supply-in-loss source
        # lags ~1 day behind price/F&G, and an inner join would silently
        # drop today's row entirely rather than just leaving today's
        # supply_loss_score one day stale.
        loss_df = compute_supply_in_loss(supply_profit_df)
        loss_df["supply_loss_score"] = normalize_supply_in_loss(loss_df["supply_in_loss_pct"])
        merged = pd.merge_asof(
            merged.sort_values("date"), loss_df.sort_values("date"), on="date", direction="backward"
        )

    if mvrv_df is not None:
        # Same backward merge_asof pattern, but mvrv_df's history only
        # starts ~Sept 2022 -- merge_asof naturally leaves mvrv_score as
        # NaN for every date before that (no prior row to match), rather
        # than erroring or fabricating a value. scoring.compute_composite_score()
        # renormalizes weights per-row over whichever columns are non-null,
        # so those earlier rows still get a real composite from the other
        # indicators instead of going NaN themselves.
        mvrv_scored = mvrv_df.copy().sort_values("date").reset_index(drop=True)
        mvrv_scored["mvrv_score"] = normalize_mvrv(mvrv_scored["mvrv_ratio"])
        merged = pd.merge_asof(
            merged.sort_values("date"), mvrv_scored.sort_values("date"), on="date", direction="backward"
        )

    return merged


if __name__ == "__main__":
    from fetch_data import fetch_btc_price_history, fetch_fear_greed_history

    price_df = fetch_btc_price_history()
    fng_df = fetch_fear_greed_history()

    table = build_indicator_table(price_df, fng_df)
    print(table.tail(10))
    print(f"\n{len(table)} aligned rows, from {table['date'].min().date()} to {table['date'].max().date()}")
    print(f"Rows with valid 200w MA: {table['ma_200w'].notna().sum()}")
