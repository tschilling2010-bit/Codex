"""Fetches OHLCV and ticker data from Binance public API."""
from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

BINANCE_BASE = "https://api.binance.com"

SUPPORTED_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
    "XRPUSDT", "ADAUSDT", "DOGEUSDT", "MATICUSDT",
]

INTERVALS = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}

_TIMEOUT = httpx.Timeout(15.0)


async def get_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 150,
) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
        )
        r.raise_for_status()
    return [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in r.json()
    ]


async def get_ticker(symbol: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{BINANCE_BASE}/api/v3/ticker/24hr",
            params={"symbol": symbol.upper()},
        )
        r.raise_for_status()
    d = r.json()
    return {
        "symbol": d["symbol"],
        "price": float(d["lastPrice"]),
        "change_pct": float(d["priceChangePercent"]),
        "high_24h": float(d["highPrice"]),
        "low_24h": float(d["lowPrice"]),
        "volume_24h": float(d["volume"]),
        "quote_volume_24h": float(d["quoteVolume"]),
        "ts": int(time.time()),
    }


async def get_multi_ticker(symbols: List[str]) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(f"{BINANCE_BASE}/api/v3/ticker/24hr")
        r.raise_for_status()
    upper = {s.upper() for s in symbols}
    results = []
    for d in r.json():
        if d["symbol"] in upper:
            results.append({
                "symbol": d["symbol"],
                "price": float(d["lastPrice"]),
                "change_pct": float(d["priceChangePercent"]),
                "high_24h": float(d["highPrice"]),
                "low_24h": float(d["lowPrice"]),
                "volume_24h": float(d["volume"]),
                "quote_volume_24h": float(d["quoteVolume"]),
            })
    results.sort(key=lambda x: symbols.index(x["symbol"]) if x["symbol"] in symbols else 99)
    return results
