"""
bitcoin_terminal/gui/main_window.py

SATURN — Main application window.
Assembles all panels, starts all backend workers, wires Qt signals.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QTabWidget, QStatusBar, QLabel,
        QWidget, QHBoxLayout, QFrame, QApplication,
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QFont, QIcon, QColor
except ImportError:
    from PySide6.QtWidgets import (
        QMainWindow, QTabWidget, QStatusBar, QLabel,
        QWidget, QHBoxLayout, QFrame, QApplication,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QIcon, QColor

import config
from gui.theme import C, build_stylesheet
from gui.panels.overview_panel  import OverviewPanel
from gui.panels.mempool_panel   import MempoolPanel
from gui.panels.whale_panel     import WhalePanel
from gui.panels.lightning_panel import LightningPanel
from gui.panels.search_panel    import SearchPanel
from gui.panels.alerts_panel    import AlertsPanel

from backend.rpc_client      import BitcoinRPCClient
from backend.lightning_client import LightningClient
from backend.database        import Database
from backend.price_feed      import PriceFeed
from backend.workers         import (
    BlockWorker, MempoolWorker, WhaleWorker,
    LightningWorker, AlertWorker,
)

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(config.APP_TITLE)
        self.resize(config.WINDOW_W, config.WINDOW_H)

        # ── Apply stylesheet ─────────────────────────────────────────────────
        QApplication.instance().setStyleSheet(build_stylesheet())

        # ── Backend objects ──────────────────────────────────────────────────
        self._rpc  = BitcoinRPCClient()
        self._ln   = LightningClient()
        self._db   = Database()
        self._feed = PriceFeed(callback=self._on_price_tick)

        self._rpc.test_connection()
        self._ln.connect()

        # ── Panels ───────────────────────────────────────────────────────────
        self._overview  = OverviewPanel()
        self._mempool   = MempoolPanel()
        self._whale     = WhalePanel()
        self._lightning = LightningPanel()
        self._search    = SearchPanel(self._rpc)
        self._alerts    = AlertsPanel(self._db)

        # ── Tab widget ───────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        tab_defs = [
            ("⬡  OVERVIEW",   self._overview),
            ("⛏  MEMPOOL",    self._mempool),
            ("🐋  WHALES",     self._whale),
            ("⚡  LIGHTNING",  self._lightning),
            ("🔍  SEARCH",     self._search),
            ("🔔  ALERTS",     self._alerts),
        ]
        for label, panel in tab_defs:
            self._tabs.addTab(panel, label)
        self.setCentralWidget(self._tabs)

        # ── Status bar ───────────────────────────────────────────────────────
        self._build_status_bar()

        # ── Workers ──────────────────────────────────────────────────────────
        self._alert_worker = AlertWorker(self._db)
        self._block_worker = BlockWorker(self._rpc, self._db)
        self._mempool_worker = MempoolWorker(self._rpc, self._db)
        self._whale_worker = WhaleWorker(self._rpc, self._db)
        self._ln_worker = LightningWorker(self._ln)

        self._connect_signals()

        # ── Pre-load history from DB ─────────────────────────────────────────
        self._load_db_history()

        # ── Start everything ─────────────────────────────────────────────────
        self._feed.start()
        self._alert_worker.start()
        self._block_worker.start()
        self._mempool_worker.start()
        self._whale_worker.start()
        self._ln_worker.start()

        # ── Clock timer ──────────────────────────────────────────────────────
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        log.info("SATURN main window initialised — demo_mode=%s", config.DEMO_MODE)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = self.statusBar()

        self._sb_mode = QLabel(
            "  ● DEMO MODE  " if config.DEMO_MODE else "  ● LIVE NODE  "
        )
        self._sb_mode.setStyleSheet(
            f"color: {C.AMBER if config.DEMO_MODE else C.GREEN}; "
            f"font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )

        self._sb_price = QLabel("BTC: $—")
        self._sb_price.setStyleSheet(f"color: {C.AMBER_GLOW}; font-size: 10px;")

        self._sb_block = QLabel("Block: —")
        self._sb_block.setStyleSheet(f"color: {C.CYAN}; font-size: 10px;")

        self._sb_mempool = QLabel("Mempool: —")
        self._sb_mempool.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 10px;")

        self._sb_time = QLabel("")
        self._sb_time.setStyleSheet(f"color: {C.TEXT_MUT}; font-size: 10px;")

        self._sb_alerts = QLabel("Alerts: 0")
        self._sb_alerts.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 10px;")

        for w in (self._sb_mode, self._sb_price, self._sb_block,
                  self._sb_mempool, self._sb_alerts):
            sb.addWidget(self._sep())
            sb.addWidget(w)

        sb.addPermanentWidget(self._sb_time)

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet(f"color: {C.BORDER};")
        return f

    def _tick_clock(self) -> None:
        now = datetime.utcnow().strftime("%Y-%m-%d  %H:%M:%S  UTC")
        self._sb_time.setText(f"  {now}  ")

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        # Block worker → overview
        self._block_worker.chain_update.connect(self._on_chain_update)
        self._block_worker.block_update.connect(self._on_block_update)
        self._block_worker.network_update.connect(self._overview.update_network)
        self._block_worker.mining_update.connect(self._overview.update_mining)

        # Mempool worker → mempool panel + overview + alert engine
        self._mempool_worker.mempool_info.connect(self._on_mempool_info)
        self._mempool_worker.fee_histogram.connect(self._on_fee_histogram)
        self._mempool_worker.snapshot_saved.connect(self._reload_mempool_history)

        # Whale worker → whale panel + alert engine
        self._whale_worker.whale_txs_update.connect(self._on_whale_txs)
        self._whale_worker.new_whale_alert.connect(self._whale.add_alert_tx)

        # Lightning worker → lightning panel
        self._ln_worker.node_info_update.connect(self._lightning.update_node_info)
        self._ln_worker.channels_update.connect(self._lightning.update_channels)
        self._ln_worker.payments_update.connect(self._lightning.update_payments)
        self._ln_worker.forwarding_update.connect(self._lightning.update_forwarding)
        self._ln_worker.liquidity_update.connect(self._lightning.update_liquidity)
        self._ln_worker.graph_summary_update.connect(self._lightning.update_graph)

        # Alert worker → alerts panel + status bar + tab badge
        self._alert_worker.new_alert.connect(self._on_new_alert)
        self._alert_worker.unread_count.connect(self._on_unread_count)

        # Worker errors → status bar
        for w in (self._block_worker, self._mempool_worker,
                  self._whale_worker, self._ln_worker):
            w.error.connect(lambda msg: log.error("Worker: %s", msg))

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _on_price_tick(self, price: float) -> None:
        history = self._feed.get_history()
        abs_ch, pct_ch = self._feed.get_24h_change()
        self._overview.update_price(price, history, abs_ch, pct_ch)
        self._sb_price.setText(f"BTC: ${price:,.2f}")
        # feed to alert engine
        prev = self._alert_worker._state.get("price_now")
        self._alert_worker.ingest("price_prev", prev)
        self._alert_worker.ingest("price_now", price)
        # persist
        self._db.insert_price(price)

    def _on_chain_update(self, info: dict) -> None:
        self._overview.update_chain(info)
        self._sb_block.setText(f"Block: {info.get('blocks', 0):,}")

    def _on_block_update(self, blk: dict) -> None:
        blocks = self._db.get_blocks(limit=40)
        if not blocks:
            blocks = [blk]
        self._overview.update_blocks(blocks)

    def _on_mempool_info(self, info: dict) -> None:
        self._overview.update_mempool(info)
        self._mempool.update_mempool_info(info)
        self._sb_mempool.setText(f"Mempool: {info.get('size', 0):,} txs")
        self._alert_worker.ingest("mempool_info", info)

    def _on_fee_histogram(self, histogram: list) -> None:
        self._mempool.update_fee_histogram(histogram)
        self._alert_worker.ingest("fee_histogram", histogram)
        if histogram:
            fees = [f for f, _ in histogram]
            fee_1  = fees[min(len(fees)-1, max(0, len(fees) - len(fees)//4))]
            fee_6  = fees[len(fees)//2] if len(fees) > 1 else fees[0]
            fee_12 = fees[min(2, len(fees)-1)]
            fee_day = fees[0]
            self._overview.update_fees(fee_1 * 1e-5, fee_6 * 1e-5)
            self._mempool.update_fee_tiers(
                fee_1 * 1e-5, fees[-1] * 1e-5 * 0.7,
                fee_6 * 1e-5, fee_12 * 1e-5,
                fee_day * 1e-5,
            )

    def _on_whale_txs(self, txs: list) -> None:
        self._whale.update_whale_txs(txs)
        self._alert_worker.ingest("whale_txs", txs)

    def _on_new_alert(self, alert: dict) -> None:
        self._alerts.add_alert(alert)
        log.warning("[%s] %s — %s",
                    alert["severity"], alert["title"], alert["body"])

    def _on_unread_count(self, count: int) -> None:
        self._alerts.update_unread_count(count)
        self._sb_alerts.setText(f"Alerts: {count}")
        self._sb_alerts.setStyleSheet(
            f"color: {C.RED if count else C.TEXT_SEC}; font-size: 10px;"
        )
        # Update tab label
        label = f"🔔  ALERTS{' (' + str(count) + ')' if count else ''}"
        self._tabs.setTabText(5, label)

    def _reload_mempool_history(self) -> None:
        history = self._db.get_mempool_history(hours=24)
        self._mempool.update_history(history)

    def _load_db_history(self) -> None:
        """Pre-populate panels with persisted data on start."""
        blocks = self._db.get_blocks(limit=40)
        if blocks:
            self._overview.update_blocks(blocks)
        history = self._db.get_mempool_history(hours=24)
        if history:
            self._mempool.update_history(history)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        log.info("Shutting down SATURN…")
        self._feed.stop()
        for w in (self._alert_worker, self._block_worker,
                  self._mempool_worker, self._whale_worker,
                  self._ln_worker):
            w.stop()
        event.accept()
