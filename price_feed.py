"""
bitcoin_terminal/backend/price_feed.py

BTC price aggregation from multiple sources.
• CoinGecko REST  — reliable, free, 30-second resolution
• Binance WS      — real-time ticker (optional)
• Synthetic       — demo fallback with realistic noise model
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
import logging
from typing import Callable

import requests

import config

log = logging.getLogger(__name__)

# ── Synthetic price model ─────────────────────────────────────────────────────

class _GBMModel:
    """
    Geometric Brownian Motion price simulator.
    Provides realistic-looking BTC price noise for demo mode.
    """
    def __init__(self, price: float = 68_400.0, vol: float = 0.0002) -> None:
        self._price = price
        self._vol = vol
        self._drift = 0.00001

    def next(self) -> float:
        shock = random.gauss(0, 1)
        self._price *= math.exp(
            (self._drift - 0.5 * self._vol ** 2) + self._vol * shock
        )
        self._price = max(10_000.0, self._price)
        return round(self._price, 2)


# ── Feed ──────────────────────────────────────────────────────────────────────

class PriceFeed:
    """
    Thread-safe price feed.

    Usage:
        feed = PriceFeed(callback=my_fn)   # my_fn(price: float)
        feed.start()
        # later
        feed.stop()
    """

    def __init__(self, callback: Callable[[float], None] | None = None) -> None:
        self._callback = callback
        self._latest: float | None = None
        self._history: list[tuple[int, float]] = []   # (unix_ts, price)
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._demo_model = _GBMModel()

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ── Public getters ────────────────────────────────────────────────────────

    @property
    def latest(self) -> float | None:
        with self._lock:
            return self._latest

    def get_history(self, points: int = 500) -> list[tuple[int, float]]:
        with self._lock:
            return list(self._history[-points:])

    def get_24h_change(self) -> tuple[float, float]:
        """Returns (absolute_change, percent_change)."""
        with self._lock:
            if len(self._history) < 2:
                return 0.0, 0.0
            oldest = self._history[0][1]
            newest = self._history[-1][1]
            delta = newest - oldest
            pct = (delta / oldest) * 100 if oldest else 0.0
            return round(delta, 2), round(pct, 2)

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _run(self) -> None:
        # Seed history with 24 h of synthetic data before going live
        if config.DEMO_MODE:
            self._seed_history()
        while self._running:
            price = self._fetch_price()
            if price is not None:
                ts = int(time.time())
                with self._lock:
                    self._latest = price
                    self._history.append((ts, price))
                    # keep ≤ 2880 points (24 h at 30-second resolution)
                    if len(self._history) > 2880:
                        self._history = self._history[-2880:]
                if self._callback:
                    try:
                        self._callback(price)
                    except Exception:
                        pass
            time.sleep(config.PRICE_POLL_INTERVAL)

    def _fetch_price(self) -> float | None:
        if config.DEMO_MODE:
            return self._demo_model.next()
        # Try CoinGecko
        try:
            resp = requests.get(
                config.PRICE_FEED_URL,
                params={"ids": "bitcoin", "vs_currencies": "usd"},
                timeout=8,
            )
            resp.raise_for_status()
            price = resp.json()["bitcoin"]["usd"]
            return float(price)
        except Exception as exc:
            log.warning("CoinGecko price fetch failed: %s", exc)
        # Try Binance REST fallback
        try:
            resp = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"},
                timeout=8,
            )
            resp.raise_for_status()
            return float(resp.json()["price"])
        except Exception as exc:
            log.warning("Binance price fetch failed: %s", exc)
        return None

    def _seed_history(self, points: int = 2880) -> None:
        """Pre-fill 24 h of synthetic price history."""
        model = _GBMModel(68_400.0)
        now = int(time.time())
        interval = 30
        start = now - points * interval
        self._history = [
            (start + i * interval, model.next())
            for i in range(points)
        ]
        self._latest = self._history[-1][1]
