"""
bitcoin_terminal/gui/panels/lightning_panel.py

Lightning Network dashboard.
• Node summary card
• Channel list with liquidity bars
• Recent payments + forwarding history
• Global LN graph summary
"""

from __future__ import annotations

import time
from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView,
        QSizePolicy, QSplitter, QProgressBar, QGridLayout,
        QAbstractItemView,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient
except ImportError:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView,
        QSizePolicy, QSplitter, QProgressBar, QGridLayout,
        QAbstractItemView,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient

from gui.theme import C


# ── Liquidity bar cell ────────────────────────────────────────────────────────

class LiquidityBar(QWidget):
    """Bi-directional liquidity bar: local (amber) | remote (cyan)."""

    def __init__(self, local: int, remote: int, parent=None) -> None:
        super().__init__(parent)
        self._local = local
        self._remote = remote
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        total = self._local + self._remote or 1
        lw = int(self._local / total * w)
        rw = w - lw

        painter.fillRect(0, 2, lw, h - 4, QColor(C.AMBER))
        painter.fillRect(lw, 2, rw, h - 4, QColor(C.CYAN_DIM))

        # centre divider
        painter.setPen(QPen(QColor(C.BASE), 2))
        painter.drawLine(lw, 0, lw, h)
        painter.end()


# ── LN panel ──────────────────────────────────────────────────────────────────

class LightningPanel(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Node summary strip ───────────────────────────────────────────────
        node_frame = QFrame()
        node_frame.setObjectName("metric_card_accent")
        nfl = QGridLayout(node_frame)
        nfl.setContentsMargins(16, 12, 16, 12)
        nfl.setSpacing(12)

        ln_hdr = QLabel("⚡ LIGHTNING NODE")
        ln_hdr.setObjectName("section_header")
        ln_hdr.setStyleSheet(f"color: {C.AMBER}; font-size: 12px; font-weight: 700; "
                              f"letter-spacing: 2px; border: none;")
        nfl.addWidget(ln_hdr, 0, 0, 1, 6)

        self._node_vals: dict[str, QLabel] = {}
        items = [
            ("Alias",      "alias",        C.AMBER_GLOW),
            ("Active Ch",  "active_ch",    C.GREEN),
            ("Peers",      "peers",        C.CYAN),
            ("Cap (BTC)",  "capacity",     C.AMBER),
            ("Local (BTC)","local",        C.GREEN),
            ("Remote BTC", "remote",       C.CYAN),
            ("Version",    "version",      C.TEXT_SEC),
            ("Synced",     "synced",       C.GREEN),
            ("Net Nodes",  "net_nodes",    C.AMBER),
            ("Net Ch",     "net_ch",       C.CYAN),
            ("Net Cap",    "net_cap",      C.AMBER),
            ("Routing Fee","fee_earned",   C.GREEN),
        ]
        for col, (lbl, key, color) in enumerate(items):
            l = QLabel(lbl.upper())
            l.setObjectName("stat_label")
            v = QLabel("—")
            v.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 700;")
            self._node_vals[key] = v
            nfl.addWidget(l, 1, col % 6)
            nfl.addWidget(v, 2, col % 6)
            if col == 5:
                nfl.addWidget(self._sep(), 3, 0, 1, 6)

        root.addWidget(node_frame)

        # ── Splitter: channels | payments ────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Channel list
        ch_frame = QFrame()
        ch_frame.setObjectName("metric_card")
        chl = QVBoxLayout(ch_frame)
        chl.setContentsMargins(12, 10, 12, 10)
        chl.setSpacing(6)
        chl.addWidget(self._header("CHANNELS  (LOCAL ■ ■ REMOTE)"))

        self._ch_table = QTableWidget()
        self._ch_table.setColumnCount(7)
        self._ch_table.setHorizontalHeaderLabels([
            "ALIAS", "CAP (SAT)", "LOCAL", "REMOTE", "LIQUIDITY", "SENT/RECV", "STATUS",
        ])
        hdr = self._ch_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        for col in (1, 2, 3, 5, 6):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self._ch_table.setAlternatingRowColors(True)
        self._ch_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._ch_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._ch_table.verticalHeader().setVisible(False)
        chl.addWidget(self._ch_table)
        splitter.addWidget(ch_frame)

        # Right column: payments + forwarding
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        # Payments
        pay_frame = QFrame()
        pay_frame.setObjectName("metric_card")
        pfl = QVBoxLayout(pay_frame)
        pfl.setContentsMargins(12, 10, 12, 10)
        pfl.setSpacing(6)
        pfl.addWidget(self._header("RECENT PAYMENTS"))

        self._pay_table = QTableWidget()
        self._pay_table.setColumnCount(4)
        self._pay_table.setHorizontalHeaderLabels(
            ["HASH", "VALUE (SAT)", "FEE (SAT)", "STATUS"])
        self._pay_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._pay_table.setAlternatingRowColors(True)
        self._pay_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pay_table.verticalHeader().setVisible(False)
        pfl.addWidget(self._pay_table)
        rl.addWidget(pay_frame)

        # Forwarding
        fwd_frame = QFrame()
        fwd_frame.setObjectName("metric_card")
        ffl = QVBoxLayout(fwd_frame)
        ffl.setContentsMargins(12, 10, 12, 10)
        ffl.setSpacing(6)
        ffl.addWidget(self._header("FORWARDING HISTORY"))

        self._fwd_table = QTableWidget()
        self._fwd_table.setColumnCount(4)
        self._fwd_table.setHorizontalHeaderLabels(
            ["AMT IN (SAT)", "AMT OUT (SAT)", "FEE (SAT)", "TIME"])
        self._fwd_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._fwd_table.setAlternatingRowColors(True)
        self._fwd_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._fwd_table.verticalHeader().setVisible(False)
        ffl.addWidget(self._fwd_table)
        rl.addWidget(fwd_frame)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

    @staticmethod
    def _header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        return lbl

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"color: {C.BORDER};")
        return f

    # ── Public updates ────────────────────────────────────────────────────────

    def update_node_info(self, info: dict) -> None:
        self._node_vals["alias"].setText(info.get("alias", "—"))
        self._node_vals["version"].setText(info.get("version", "—"))
        synced = "✓ YES" if info.get("synced_to_chain") else "✗ NO"
        self._node_vals["synced"].setText(synced)
        self._node_vals["peers"].setText(str(info.get("num_peers", "—")))
        self._node_vals["active_ch"].setText(
            str(info.get("num_active_channels", "—")))

    def update_channels(self, channels: list[dict]) -> None:
        self._ch_table.setRowCount(0)
        total_cap = sum(c["capacity"] for c in channels)
        total_local = sum(c["local_balance"] for c in channels)
        total_remote = sum(c["remote_balance"] for c in channels)

        # Update summary
        self._node_vals["capacity"].setText(f"{total_cap / 1e8:.4f}")
        self._node_vals["local"].setText(f"{total_local / 1e8:.4f}")
        self._node_vals["remote"].setText(f"{total_remote / 1e8:.4f}")

        for row, ch in enumerate(channels):
            self._ch_table.insertRow(row)
            active = ch.get("active", False)
            sent = ch.get("total_satoshis_sent", 0)
            recv = ch.get("total_satoshis_received", 0)
            sent_recv = f"↑{sent // 1000}K / ↓{recv // 1000}K"

            vals = [
                ch.get("alias", ch["remote_pubkey"][:12] + "…"),
                f"{ch['capacity']:,}",
                f"{ch['local_balance']:,}",
                f"{ch['remote_balance']:,}",
                "",   # liquidity bar
                sent_recv,
                "ACTIVE" if active else "INACTIVE",
            ]
            for col, v in enumerate(vals):
                if col == 4:
                    bar = LiquidityBar(ch["local_balance"], ch["remote_balance"])
                    self._ch_table.setCellWidget(row, col, bar)
                    continue
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 0:
                    item.setForeground(QColor(C.AMBER if active else C.TEXT_SEC))
                elif col == 6:
                    item.setForeground(QColor(C.GREEN if active else C.RED))
                self._ch_table.setItem(row, col, item)

    def update_payments(self, payments: list[dict]) -> None:
        self._pay_table.setRowCount(0)
        status_colors = {
            "SUCCEEDED": C.GREEN, "FAILED": C.RED,
            "IN_FLIGHT": C.AMBER, "UNKNOWN": C.TEXT_SEC,
        }
        for row, pmt in enumerate(payments[:40]):
            self._pay_table.insertRow(row)
            status = pmt.get("status", "UNKNOWN")
            vals = [
                pmt.get("payment_hash", "—")[:20] + "…",
                f"{pmt.get('value_sat', 0):,}",
                f"{pmt.get('fee_sat', 0):,}",
                status,
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 3:
                    item.setForeground(QColor(
                        status_colors.get(status, C.TEXT_SEC)))
                self._pay_table.setItem(row, col, item)

    def update_forwarding(self, events: list[dict]) -> None:
        self._fwd_table.setRowCount(0)
        total_fee = 0
        for row, ev in enumerate(events[:40]):
            self._fwd_table.insertRow(row)
            ts = ev.get("timestamp", 0)
            dt = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts else "—"
            fee = ev.get("fee", 0)
            total_fee += fee
            vals = [
                f"{ev.get('amt_in', 0):,}",
                f"{ev.get('amt_out', 0):,}",
                f"{fee:,}",
                dt,
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 2:
                    item.setForeground(QColor(C.GREEN))
                self._fwd_table.setItem(row, col, item)
        self._node_vals["fee_earned"].setText(f"{total_fee:,} sat")

    def update_graph(self, graph: dict) -> None:
        self._node_vals["net_nodes"].setText(
            f"{graph.get('num_nodes', 0):,}")
        self._node_vals["net_ch"].setText(
            f"{graph.get('num_channels', 0):,}")
        cap = graph.get("total_capacity_sat", 0) / 1e8
        self._node_vals["net_cap"].setText(f"{cap:,.0f} BTC")

    def update_liquidity(self, liq: dict) -> None:
        ratio = liq.get("balance_ratio", 0.5)
        pct = int(ratio * 100)
        self._node_vals.get("alias")   # already set elsewhere
