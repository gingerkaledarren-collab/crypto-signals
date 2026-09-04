"""
fetch_data.py

Pulls the raw data series we need:
  1. BTC daily price history (blockchain.info - free, no API key needed)
  2. Fear & Greed Index history (blended: alternative.me + CoinMarketCap,
     see fetch_fear_greed_history() docstring)
  3. Bitcoin Supply in Profit/Loss (%) (BGeometrics, see
     fetch_supply_in_profit_history() docstring)

All are cached to local CSV files so we don't hammer the APIs on every run.
Re-run with force_refresh=True to pull fresh data.
"""

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PRICE_CACHE = DATA_DIR / "btc_price_history.csv"
FNG_CACHE = DATA_DIR / "fear_greed_history.csv"
SUPPLY_PROFIT_CACHE = DATA_DIR / "supply_in_profit_history.csv"


def fetch_btc_price_history(days: int = "max", force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch BTC daily price history from blockchain.info's charts API.

    NOTE: CoinGecko's free tier now caps historical queries at 365 days
    (their /market_chart endpoint returns a 401/10012 error beyond that),
    which isn't enough for a 200-week MA. blockchain.info's market-price
    chart has no such cap and goes back to 2009, so we use that instead.
    `days` is kept as a parameter for API compatibility but is unused.

    The `timespan=all` query (needed for full daily resolution back to
    2010) turned out to lag ~1 day behind blockchain.info's own
    short-range queries -- e.g. it was still capped at Sept 3 with a
    fetch made on Sept 4, when a `timespan=10days` fetch already had
    Sept 4's point. So we always follow up with a short recent window
    and let it overwrite the tail of the long history, rather than
    trusting `all`'s last day or two.

    Returns a DataFrame with columns: date, price
    """
    if PRICE_CACHE.exists() and not force_refresh:
        df = pd.read_csv(PRICE_CACHE, parse_dates=["date"])
        return df

    url = "https://api.blockchain.info/charts/market-price"

    def _fetch(params):
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        values = resp.json()["values"]  # list of {"x": timestamp_s, "y": price}
        df = pd.DataFrame(values).rename(columns={"x": "timestamp_s", "y": "price"})
        df["date"] = pd.to_datetime(df["timestamp_s"], unit="s").dt.normalize()
        return df[["date", "price"]]

    full = _fetch({"timespan": "all", "format": "json", "sampled": "false"})
    recent = _fetch({"timespan": "10days", "format": "json", "sampled": "false"})

    df = pd.concat([full[full["date"] < recent["date"].min()], recent], ignore_index=True)
    df = df.drop_duplicates(subset="date").reset_index(drop=True)
    df = df[df["price"] > 0].reset_index(drop=True)  # drop pre-exchange zero-price rows
    df = df.sort_values("date").reset_index(drop=True)

    df.to_csv(PRICE_CACHE, index=False)
    return df


def _fetch_fear_greed_alternative_me() -> pd.DataFrame:
    """alternative.me's public Fear & Greed API -- free, keyless, and the
    only one of the two sources with history back to 2018."""
    url = "https://api.alternative.me/fng/"
    params = {"limit": 0, "format": "json"}  # limit=0 means "all history"

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    records = resp.json()["data"]

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
    df["fng_value"] = df["value"].astype(int)
    df = df[["date", "fng_value", "value_classification"]].rename(
        columns={"value_classification": "fng_classification"}
    )
    return df.sort_values("date").reset_index(drop=True)


def _fetch_fear_greed_coinmarketcap() -> pd.DataFrame:
    """
    CoinMarketCap's Fear & Greed Index. CMC has no free/keyless *official*
    API for this (it's gated behind a paid Pro API key) -- this instead
    calls the internal endpoint CMC's own website frontend uses
    (api.coinmarketcap.com/data-api/v3/fear-greed/chart). That's an
    unofficial, undocumented dependency that could change or get blocked
    without notice, and its history only goes back to ~June 2023 (vs.
    alternative.me's 2018), which is why fetch_fear_greed_history() below
    blends the two rather than replacing alternative.me outright.

    Returns a DataFrame with columns: date, fng_value, fng_classification
    (columns match _fetch_fear_greed_alternative_me() for a clean concat).
    """
    url = "https://api.coinmarketcap.com/data-api/v3/fear-greed/chart"
    start = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime.now(timezone.utc).timestamp())

    resp = requests.get(url, params={"start": start, "end": end}, timeout=30)
    resp.raise_for_status()
    records = resp.json()["data"]["dataList"]

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
    df["fng_value"] = df["score"].astype(int)
    df["fng_classification"] = df["name"].str.title()  # CMC uses "Extreme fear"; alternative.me uses "Extreme Fear"
    df = df[["date", "fng_value", "fng_classification"]]
    # CMC gives an intraday reading for "today" -- collapse to one row/day, keeping the latest.
    return df.sort_values("date").drop_duplicates(subset="date", keep="last").reset_index(drop=True)


def fetch_fear_greed_history(force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch the Fear & Greed Index history, blended from two sources:
    alternative.me for everything before CoinMarketCap's index begins,
    CoinMarketCap's own index from that point forward (by request --
    considered more accurate day-to-day, but with much shorter history).
    If CMC's unofficial endpoint fails, falls back to alternative.me's
    full history alone rather than hard-failing the whole pipeline.

    Returns a DataFrame with columns: date, fng_value (0-100), fng_classification
    """
    if FNG_CACHE.exists() and not force_refresh:
        df = pd.read_csv(FNG_CACHE, parse_dates=["date"])
        return df

    alt_df = _fetch_fear_greed_alternative_me()

    try:
        cmc_df = _fetch_fear_greed_coinmarketcap()
    except Exception:
        cmc_df = pd.DataFrame(columns=["date", "fng_value", "fng_classification"])

    if len(cmc_df) > 0:
        cutover = cmc_df["date"].min()
        df = pd.concat([alt_df[alt_df["date"] < cutover], cmc_df], ignore_index=True)
    else:
        df = alt_df

    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(FNG_CACHE, index=False)
    return df


def fetch_supply_in_profit_history(force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch Bitcoin's daily "% of supply in profit" history from BGeometrics.

    BGeometrics' documented API (api.bgeometrics.com) requires a paid key
    for this metric. This instead calls the static JSON file their own
    free chart page (charts.bgeometrics.com/supply_in_profit.html) fetches
    for anonymous viewers -- an unofficial, undocumented dependency that
    could change or get blocked without notice, same caveat as the
    CoinMarketCap Fear & Greed endpoint. Unlike that one, though, this has
    a long history (2014-present, ~1 day lag), so no blending is needed.

    The series is "% of supply in PROFIT" (confirmed against known dates:
    96.9% at the Nov 2021 ATH, 44.9% at the Nov 2022 capitulation low --
    consistent with profit%, not loss%). Supply-in-LOSS %, the metric
    actually asked for, is 100 minus this value -- computed in
    indicators.py, not here, so this function's column name stays
    accurate to what it actually fetched.

    Returns a DataFrame with columns: date, supply_in_profit_pct
    """
    if SUPPLY_PROFIT_CACHE.exists() and not force_refresh:
        df = pd.read_csv(SUPPLY_PROFIT_CACHE, parse_dates=["date"])
        return df

    url = "https://charts.bgeometrics.com/files/profit_loss.json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    records = resp.json()  # list of [timestamp_ms, profit_pct]

    df = pd.DataFrame(records, columns=["timestamp_ms", "supply_in_profit_pct"])
    df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms").dt.normalize()
    df = df[["date", "supply_in_profit_pct"]].dropna()
    df = df.sort_values("date").reset_index(drop=True)

    df.to_csv(SUPPLY_PROFIT_CACHE, index=False)
    return df


if __name__ == "__main__":
    print("Fetching BTC price history...")
    price_df = fetch_btc_price_history(force_refresh=True)
    print(f"  Got {len(price_df)} days of price data, from {price_df['date'].min().date()} to {price_df['date'].max().date()}")

    print("Fetching Fear & Greed Index history...")
    fng_df = fetch_fear_greed_history(force_refresh=True)
    print(f"  Got {len(fng_df)} days of F&G data, from {fng_df['date'].min().date()} to {fng_df['date'].max().date()}")

    print("Fetching Bitcoin Supply in Profit/Loss history...")
    supply_df = fetch_supply_in_profit_history(force_refresh=True)
    print(f"  Got {len(supply_df)} days of supply-in-profit data, from {supply_df['date'].min().date()} to {supply_df['date'].max().date()}")

    print(f"\nCached to {DATA_DIR}/")
