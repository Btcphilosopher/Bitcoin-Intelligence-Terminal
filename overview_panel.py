"""
bitcoin_terminal/gui/panels/overview_panel.py

Overview / Dashboard panel.
Left: live price + 24-hour sparkline + BTC stats grid.
Right: recent blocks table + hash-rate / difficulty gauges.
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
        QGridLayout, QProgressBar, QSplitter,
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush
except ImportError:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
        QGridLayout, QProgressBar, QSplitter,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush

from gui.theme import C


# ── Sparkline widget ──────────────────────────────────────────────────────────

class SparklineWidget(QWidget):
    """Minimal GPU-light price sparkline rendered with QPainter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[float] = []
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, values: list[float]) -> None:
        self._data = values[-400:]
        self.update()

    def paintEvent(self, event) -> None:
        if len(self._data) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pad = 4
        lo, hi = min(self._data), max(self._data)
        rng = max(hi - lo, 1.0)

        def x_of(i): return pad + (i / (len(self._data) - 1)) * (w - 2 * pad)
        def y_of(v): return h - pad - ((v - lo) / rng) * (h - 2 * pad)

        # gradient fill
        grad = QLinearGradient(0, 0, 0, h)
        is_up = self._data[-1] >= self._data[0]
        top_color = QColor(C.GREEN if is_up else C.RED)
        top_color.setAlpha(60)
        bot_color = QColor(C.BASE)
        bot_color.setAlpha(0)
        grad.setColorAt(0.0, top_color)
        grad.setColorAt(1.0, bot_color)

        from PyQt5.QtGui import QPolygonF
        try:
            from PyQt5.QtCore import QPointF
        except ImportError:
            from PySide6.QtCore import QPointF

        poly = [QPointF(x_of(i), y_of(v)) for i, v in enumerate(self._data)]
        poly.append(QPointF(x_of(len(self._data) - 1), h))
        poly.append(QPointF(x_of(0), h))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)

        try:
            from PyQt5.QtGui import QPolygonF as PF
        except ImportError:
            from PySide6.QtGui import QPolygonF as PF
        painter.drawPolygon(PF(poly))

        # line
        line_color = QColor(C.GREEN if is_up else C.RED)
        pen = QPen(line_color, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for i in range(1, len(self._data)):
            painter.drawLine(
                int(x_of(i - 1)), int(y_of(self._data[i - 1])),
                int(x_of(i)), int(y_of(self._data[i]))
            )

        # current price dot
        last_x = int(x_of(len(self._data) - 1))
        last_y = int(y_of(self._data[-1]))
        dot_color = QColor(C.GREEN if is_up else C.RED)
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(last_x - 3, last_y - 3, 6, 6)
        painter.end()


# ── Metric card ───────────────────────────────────────────────────────────────

def _metric_card(label: str, value: str = "—",
                 accent: str = "accent") -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName(f"metric_card_{accent}")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(4)

    lbl = QLabel(label.upper())
    lbl.setObjectName("stat_label")

    val = QLabel(value)
    val.setObjectName("stat_value")
    val.setStyleSheet(f"color: {C.AMBER}; font-size: 18px; font-weight: 700;")

    layout.addWidget(lbl)
    layout.addWidget(val)
    return card, val


# ── Overview panel ────────────────────────────────────────────────────────────

class OverviewPanel(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._price_history: list[float] = []
        self._blocks: list[dict] = []
        self._build_ui()
        self._start_clock()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

    def _build_left(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Price card
        price_card = QFrame()
        price_card.setObjectName("metric_card_accent")
        pc_layout = QVBoxLayout(price_card)
        pc_layout.setContentsMargins(16, 14, 16, 14)
        pc_layout.setSpacing(6)

        price_header = QHBoxLayout()
        btc_label = QLabel("BTC / USD")
        btc_label.setObjectName("section_header")
        self._live_dot = QLabel("● LIVE")
        self._live_dot.setStyleSheet(f"color: {C.GREEN}; font-size: 10px; "
                                     f"letter-spacing: 1px;")
        price_header.addWidget(btc_label)
        price_header.addStretch()
        price_header.addWidget(self._live_dot)
        pc_layout.addLayout(price_header)

        self._price_lbl = QLabel("$—")
        self._price_lbl.setObjectName("price_display")
        pc_layout.addWidget(self._price_lbl)

        change_row = QHBoxLayout()
        self._change_abs = QLabel("")
        self._change_pct = QLabel("")
        self._change_abs.setObjectName("ticker_positive")
        self._change_pct.setObjectName("ticker_positive")
        change_row.addWidget(self._change_abs)
        change_row.addWidget(self._change_pct)
        change_row.addStretch()
        pc_layout.addLayout(change_row)

        self._sparkline = SparklineWidget()
        pc_layout.addWidget(self._sparkline)

        layout.addWidget(price_card)

        # Stats grid
        grid_lbl = QLabel("CHAIN METRICS")
        grid_lbl.setObjectName("section_header")
        layout.addWidget(grid_lbl)

        grid = QGridLayout()
        grid.setSpacing(8)

        metrics = [
            ("Block Height",   "block_height",   "accent"),
            ("Difficulty",     "difficulty",     "cyan"),
            ("Hash Rate",      "hash_rate",      "green"),
            ("Connections",    "connections",    "accent"),
            ("Mempool TXs",    "mempool_size",   "cyan"),
            ("Next-Block Fee", "fee_1blk",       "green"),
            ("6-Blk Fee",      "fee_6blk",       "accent"),
            ("Block Reward",   "block_reward",   "cyan"),
        ]
        self._metric_vals: dict[str, QLabel] = {}
        for idx, (label, key, accent) in enumerate(metrics):
            card, val_lbl = _metric_card(label, "—", accent)
            self._metric_vals[key] = val_lbl
            grid.addWidget(card, idx // 2, idx % 2)

        layout.addLayout(grid)
        layout.addStretch()
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        hdr = QLabel("RECENT BLOCKS")
        hdr.setObjectName("section_header")
        layout.addWidget(hdr)

        self._block_table = QTableWidget()
        self._block_table.setColumnCount(7)
        self._block_table.setHorizontalHeaderLabels([
            "HEIGHT", "TXNS", "SIZE (KB)", "WEIGHT", "FEES (BTC)",
            "DIFFICULTY", "TIME",
        ])
        self._block_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._block_table.setAlternatingRowColors(True)
        self._block_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._block_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._block_table.verticalHeader().setVisible(False)
        layout.addWidget(self._block_table, stretch=3)

        # Node info strip
        node_hdr = QLabel("NODE STATUS")
        node_hdr.setObjectName("section_header")
        layout.addWidget(node_hdr)

        node_frame = QFrame()
        node_frame.setObjectName("metric_card")
        node_layout = QGridLayout(node_frame)
        node_layout.setContentsMargins(12, 10, 12, 10)
        node_layout.setSpacing(8)

        node_items = [
            ("Version", "node_version"),
            ("Chain", "node_chain"),
            ("Peers In", "peers_in"),
            ("Peers Out", "peers_out"),
            ("IBD", "node_ibd"),
            ("Disk Used", "disk_gb"),
        ]
        self._node_vals: dict[str, QLabel] = {}
        for i, (lbl, key) in enumerate(node_items):
            l = QLabel(lbl.upper())
            l.setObjectName("stat_label")
            v = QLabel("—")
            v.setStyleSheet(f"color: {C.CYAN}; font-size: 13px; font-weight: 600;")
            self._node_vals[key] = v
            node_layout.addWidget(l, i // 3, (i % 3) * 2)
            node_layout.addWidget(v, i // 3, (i % 3) * 2 + 1)

        layout.addWidget(node_frame)
        return w

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _start_clock(self) -> None:
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._blink_dot)
        self._clock_timer.start(1000)
        self._dot_on = True

    def _blink_dot(self) -> None:
        self._dot_on = not self._dot_on
        color = C.GREEN if self._dot_on else C.TEXT_MUT
        self._live_dot.setStyleSheet(
            f"color: {color}; font-size: 10px; letter-spacing: 1px;"
        )

    # ── Public update slots ───────────────────────────────────────────────────

    def update_price(self, price: float, history: list[tuple[int, float]],
                     change_abs: float, change_pct: float) -> None:
        self._price_lbl.setText(f"${price:,.2f}")
        sign = "+" if change_abs >= 0 else ""
        color = C.GREEN if change_abs >= 0 else C.RED
        self._change_abs.setText(f"{sign}${change_abs:,.2f}")
        self._change_pct.setText(f"({sign}{change_pct:.2f}%)")
        for lbl in (self._change_abs, self._change_pct):
            lbl.setObjectName("ticker_positive" if change_abs >= 0
                               else "ticker_negative")
            lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600;")
        prices = [p for _, p in history]
        self._sparkline.set_data(prices)

    def update_chain(self, info: dict) -> None:
        h = info.get("blocks", 0)
        diff = info.get("difficulty", 0)
        self._metric_vals["block_height"].setText(f"{h:,}")
        self._metric_vals["difficulty"].setText(f"{diff / 1e12:.2f} T")
        self._metric_vals["block_reward"].setText("3.125 BTC")
        self._node_vals["node_chain"].setText(info.get("chain", "—").upper())
        disk = info.get("size_on_disk", 0) / 1e9
        self._node_vals["disk_gb"].setText(f"{disk:.0f} GB")
        ibd = "YES" if info.get("verificationprogress", 1) < 0.999 else "NO"
        self._node_vals["node_ibd"].setText(ibd)

    def update_network(self, info: dict) -> None:
        self._metric_vals["connections"].setText(
            str(info.get("connections", "—")))
        self._node_vals["node_version"].setText(
            info.get("subversion", "—").strip("/"))
        self._node_vals["peers_in"].setText(
            str(info.get("connections_in", "—")))
        self._node_vals["peers_out"].setText(
            str(info.get("connections_out", "—")))

    def update_mining(self, info: dict) -> None:
        hp = info.get("networkhashps", 0)
        if hp > 1e18:
            hs = f"{hp / 1e18:.2f} EH/s"
        elif hp > 1e15:
            hs = f"{hp / 1e15:.2f} PH/s"
        else:
            hs = f"{hp / 1e12:.2f} TH/s"
        self._metric_vals["hash_rate"].setText(hs)

    def update_mempool(self, info: dict) -> None:
        size = info.get("size", 0)
        self._metric_vals["mempool_size"].setText(f"{size:,}")

    def update_fees(self, fee_1blk: float, fee_6blk: float) -> None:
        sat1 = round(fee_1blk * 1e5, 1)
        sat6 = round(fee_6blk * 1e5, 1)
        self._metric_vals["fee_1blk"].setText(f"{sat1} sat/vB")
        self._metric_vals["fee_6blk"].setText(f"{sat6} sat/vB")

    def update_blocks(self, blocks: list[dict]) -> None:
        self._block_table.setRowCount(0)
        for row_idx, blk in enumerate(blocks[:40]):
            self._block_table.insertRow(row_idx)
            ts = blk.get("timestamp", blk.get("time", 0))
            dt = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "—"
            vals = [
                f"{blk.get('height', 0):,}",
                f"{blk.get('n_tx', blk.get('ntx', blk.get('nTx', 0))):,}",
                f"{blk.get('size', 0) / 1000:.1f}",
                f"{blk.get('weight', 0):,}",
                f"{blk.get('total_fees_btc', blk.get('_total_fees_btc', 0)):.4f}",
                f"{blk.get('difficulty', 0) / 1e12:.2f} T",
                dt,
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 0:
                    item.setForeground(QColor(C.AMBER))
                self._block_table.setItem(row_idx, col, item)
