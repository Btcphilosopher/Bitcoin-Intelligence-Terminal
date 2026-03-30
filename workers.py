"""
bitcoin_terminal/backend/workers.py

PyQt5 QThread workers that poll the various data sources and emit
typed Qt signals so the GUI can safely update from the main thread.
"""

from __future__ import annotations

import time
import logging
import traceback
from typing import Any

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except ImportError:
    from PySide6.QtCore import QThread, Signal as pyqtSignal

import config
from backend.rpc_client import BitcoinRPCClient
from backend.lightning_client import LightningClient
from backend.database import Database

log = logging.getLogger(__name__)


# ── Base worker ───────────────────────────────────────────────────────────────

class _BaseWorker(QThread):
    error = pyqtSignal(str)

    def __init__(self, interval: float, parent=None) -> None:
        super().__init__(parent)
        self._interval = interval
        self._running = False

    def stop(self) -> None:
        self._running = False
        self.quit()
        self.wait(3000)

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                log.error("Worker %s error: %s", self.__class__.__name__, exc)
                self.error.emit(str(exc))
            for _ in range(int(self._interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _tick(self) -> None:
        raise NotImplementedError


# ── Block & chain worker ──────────────────────────────────────────────────────

class BlockWorker(_BaseWorker):
    """Emits fresh blockchain info every BLOCK_POLL_INTERVAL seconds."""

    chain_update   = pyqtSignal(dict)   # getblockchaininfo
    block_update   = pyqtSignal(dict)   # latest block
    network_update = pyqtSignal(dict)   # getnetworkinfo
    mining_update  = pyqtSignal(dict)   # getmininginfo

    def __init__(self, rpc: BitcoinRPCClient, db: Database, parent=None) -> None:
        super().__init__(config.BLOCK_POLL_INTERVAL, parent)
        self._rpc = rpc
        self._db = db
        self._last_height = -1

    def _tick(self) -> None:
        chain = self._rpc.get_blockchain_info()
        self.chain_update.emit(chain)

        height = chain["blocks"]
        if height != self._last_height:
            block = self._rpc.get_block_by_height(height)
            self._db.upsert_block(block)
            self.block_update.emit(block)
            self._last_height = height

        self.network_update.emit(self._rpc.get_network_info())
        self.mining_update.emit(self._rpc.get_mining_info())


# ── Mempool worker ────────────────────────────────────────────────────────────

class MempoolWorker(_BaseWorker):
    """Polls mempool every MEMPOOL_POLL_INTERVAL seconds."""

    mempool_info    = pyqtSignal(dict)
    fee_histogram   = pyqtSignal(list)
    snapshot_saved  = pyqtSignal()

    def __init__(self, rpc: BitcoinRPCClient, db: Database, parent=None) -> None:
        super().__init__(config.MEMPOOL_POLL_INTERVAL, parent)
        self._rpc = rpc
        self._db = db

    def _tick(self) -> None:
        info = self._rpc.get_mempool_info()
        self.mempool_info.emit(info)

        histogram = self._rpc.get_fee_histogram()
        self.fee_histogram.emit(histogram)

        if histogram:
            fees = [f for f, _ in histogram]
            counts = [c for _, c in histogram]
            weighted_fees = [f * c for f, c in histogram]
            total_count = sum(counts)
            median_fee = fees[len(fees) // 2] if fees else 0.0
            self._db.insert_mempool_snapshot({
                "timestamp": int(time.time()),
                "tx_count": info["size"],
                "size_bytes": info["bytes"],
                "total_fee_btc": info.get("total_fee", 0.0),
                "min_fee_sat_vb": min(fees, default=1.0),
                "median_fee_sat_vb": median_fee,
                "max_fee_sat_vb": max(fees, default=1.0),
            })
            self.snapshot_saved.emit()


# ── Whale tracker worker ──────────────────────────────────────────────────────

class WhaleWorker(_BaseWorker):
    """Scans recent blocks for large transactions."""

    whale_txs_update = pyqtSignal(list)
    new_whale_alert  = pyqtSignal(dict)

    def __init__(self, rpc: BitcoinRPCClient, db: Database, parent=None) -> None:
        super().__init__(config.BLOCK_POLL_INTERVAL, parent)
        self._rpc = rpc
        self._db = db
        self._seen: set[str] = set()

    def _tick(self) -> None:
        txs = self._rpc.get_recent_large_transactions(
            min_btc=config.WHALE_THRESHOLD_BTC, limit=50
        )
        for tx in txs:
            if tx["txid"] not in self._seen:
                self._seen.add(tx["txid"])
                self._db.upsert_whale_tx(tx)
                if tx["btc"] >= config.WHALE_THRESHOLD_BTC * 5:
                    self.new_whale_alert.emit(tx)
        self.whale_txs_update.emit(txs)


# ── Lightning worker ──────────────────────────────────────────────────────────

class LightningWorker(_BaseWorker):
    """Polls Lightning node every LN_POLL_INTERVAL seconds."""

    node_info_update     = pyqtSignal(dict)
    channels_update      = pyqtSignal(list)
    payments_update      = pyqtSignal(list)
    forwarding_update    = pyqtSignal(list)
    liquidity_update     = pyqtSignal(dict)
    graph_summary_update = pyqtSignal(dict)

    def __init__(self, ln: LightningClient, parent=None) -> None:
        super().__init__(config.LN_POLL_INTERVAL, parent)
        self._ln = ln

    def _tick(self) -> None:
        self.node_info_update.emit(self._ln.get_node_info())
        channels = self._ln.get_channels()
        self.channels_update.emit(channels)
        self.payments_update.emit(self._ln.get_payments(50))
        self.forwarding_update.emit(self._ln.get_forwarding_history(100))
        self.liquidity_update.emit(self._ln.get_liquidity_summary())
        self.graph_summary_update.emit(self._ln.get_network_graph_summary())


# ── Alert engine worker ───────────────────────────────────────────────────────

class AlertWorker(_BaseWorker):
    """
    Rule-based alert engine.
    Evaluates thresholds against the latest data every ALERT_CHECK_INTERVAL.
    """

    new_alert        = pyqtSignal(dict)   # {severity, category, title, body}
    unread_count     = pyqtSignal(int)

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(config.ALERT_CHECK_INTERVAL, parent)
        self._db = db
        self._state: dict[str, Any] = {}

    def ingest(self, key: str, value: Any) -> None:
        """Called by other workers to share their latest readings."""
        self._state[key] = value

    def _tick(self) -> None:
        s = self._state
        alerts: list[tuple[str, str, str, str]] = []

        # ── Mempool congestion ───────────────────────────────────────────────
        mempool = s.get("mempool_info")
        if mempool:
            size = mempool.get("size", 0)
            if size > 100_000:
                alerts.append((
                    "CRITICAL", "MEMPOOL",
                    "Extreme Mempool Congestion",
                    f"Mempool contains {size:,} unconfirmed transactions. "
                    "Next-block fees exceeding 100 sat/vB.",
                ))
            elif size > 50_000:
                alerts.append((
                    "WARNING", "MEMPOOL",
                    "Mempool Congestion",
                    f"Mempool at {size:,} transactions. Fees elevated.",
                ))

        # ── Fee spike ────────────────────────────────────────────────────────
        fee_hist = s.get("fee_histogram", [])
        if fee_hist:
            max_fee = max((f for f, _ in fee_hist), default=0)
            if max_fee > 200:
                alerts.append((
                    "CRITICAL", "MEMPOOL",
                    "Fee Spike Detected",
                    f"Max observed fee rate: {max_fee:.0f} sat/vB. "
                    "Consider delaying non-urgent transactions.",
                ))

        # ── Whale movement ───────────────────────────────────────────────────
        whale_txs = s.get("whale_txs", [])
        if whale_txs:
            top = whale_txs[0]
            if top["btc"] >= 1000:
                alerts.append((
                    "WARNING", "WHALE",
                    f"Large Transfer: {top['btc']:,.0f} BTC",
                    f"${top['usd']:,.0f} moved. TXID: {top['txid'][:16]}…",
                ))

        # ── Price movement ───────────────────────────────────────────────────
        price_prev = self._state.get("price_prev")
        price_now  = self._state.get("price_now")
        if price_prev and price_now:
            change_pct = abs((price_now - price_prev) / price_prev * 100)
            if change_pct >= 3.0:
                direction = "surged" if price_now > price_prev else "dropped"
                alerts.append((
                    "WARNING", "PRICE",
                    f"BTC Price {direction.upper()} {change_pct:.1f}%",
                    f"Price moved from ${price_prev:,.0f} to ${price_now:,.0f} "
                    f"({'+' if price_now > price_prev else ''}{change_pct:.1f}%).",
                ))

        # ── LN liquidity imbalance ───────────────────────────────────────────
        liquidity = s.get("liquidity")
        if liquidity:
            ratio = liquidity.get("balance_ratio", 0.5)
            if ratio < 0.1 or ratio > 0.9:
                side = "outbound" if ratio < 0.1 else "inbound"
                alerts.append((
                    "WARNING", "LN",
                    "Lightning Liquidity Imbalance",
                    f"Channel balance ratio is {ratio:.0%} local. "
                    f"Low {side} liquidity may cause routing failures.",
                ))

        # persist & emit new ones
        for sev, cat, title, body in alerts:
            key = f"{cat}:{title}"
            last_ts = self._state.get(f"alert_last_{key}", 0)
            if time.time() - last_ts > 300:   # don't spam same alert within 5 min
                self._state[f"alert_last_{key}"] = time.time()
                aid = self._db.insert_alert(sev, cat, title, body)
                self.new_alert.emit({
                    "id": aid, "severity": sev, "category": cat,
                    "title": title, "body": body,
                    "timestamp": int(time.time()),
                })

        self.unread_count.emit(self._db.get_unread_alert_count())
