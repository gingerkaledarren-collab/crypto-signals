"""
fetch_data.py

Pulls the two raw data series we need:
  1. BTC daily price history (CoinGecko - free, no API key needed)
  2. Fear & Greed Index history (alternative.me - free, no API key needed)

Both are cached to local CSV files so we don't hammer the APIs on every run.
Re-run with force_refresh=True to pull fresh data.
"""

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PRICE_CACHE = DATA_DIR / "btc_price_history.csv"
FNG_CACHE = DATA_DIR / "fear_greed_history.csv"


def fetch_btc_price_history(days: int = "max", force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch BTC daily price history from CoinGecko.

    Note: CoinGecko's free tier limits how much history you get per call
    and how granular it is. For a proper 200-week MA we need ~4+ years of
    daily data, which the free /market_chart endpoint supports.

    Returns a DataFrame with columns: date, price
    """
    if PRICE_CACHE.exists() and not force_refresh:
        df = pd.read_csv(PRICE_CACHE, parse_dates=["date"])
        return df

    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    prices = raw["prices"]  # list of [timestamp_ms, price]
    df = pd.DataFrame(prices, columns=["timestamp_ms", "price"])
    df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms").dt.normalize()
    df = df[["date", "price"]].drop_duplicates(subset="date").reset_index(drop=True)

    df.to_csv(PRICE_CACHE, index=False)
    return df


def fetch_fear_greed_history(force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch the full Fear & Greed Index history from alternative.me.

    Returns a DataFrame with columns: date, fng_value (0-100), fng_classification
    """
    if FNG_CACHE.exists() and not force_refresh:
        df = pd.read_csv(FNG_CACHE, parse_dates=["date"])
        return df

    url = "https://api.alternative.me/fng/"
    params = {"limit": 0, "format": "json"}  # limit=0 means "all history"

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    records = raw["data"]
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s").dt.normalize()
    df["fng_value"] = df["value"].astype(int)
    df = df[["date", "fng_value", "value_classification"]].rename(
        columns={"value_classification": "fng_classification"}
    )
    df = df.sort_values("date").reset_index(drop=True)

    df.to_csv(FNG_CACHE, index=False)
    return df


if __name__ == "__main__":
    print("Fetching BTC price history...")
    price_df = fetch_btc_price_history(force_refresh=True)
    print(f"  Got {len(price_df)} days of price data, from {price_df['date'].min().date()} to {price_df['date'].max().date()}")

    print("Fetching Fear & Greed Index history...")
    fng_df = fetch_fear_greed_history(force_refresh=True)
    print(f"  Got {len(fng_df)} days of F&G data, from {fng_df['date'].min().date()} to {fng_df['date'].max().date()}")

    print(f"\nCached to {DATA_DIR}/")
