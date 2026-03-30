"""
bitcoin_terminal/gui/panels/whale_panel.py

Whale activity tracker.
• Live feed of large BTC transfers (≥ WHALE_THRESHOLD_BTC)
• Address cluster heatmap (synthetic in demo)
• Flow direction indicator
"""

from __future__ import annotations

import time
from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
        QAbstractItemView, QSplitter, QGridLayout, QSpinBox,
        QPushButton, QComboBox,
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient
except ImportError:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
        QAbstractItemView, QSplitter, QGridLayout, QSpinBox,
        QPushButton, QComboBox,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient

from gui.theme import C
import config


# ── BTC flow bubble chart ─────────────────────────────────────────────────────

class BubbleFlowWidget(QWidget):
    """
    Visualises whale transactions as sized bubbles.
    Bubble radius ∝ sqrt(BTC) for perceptual accuracy.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._txs: list[dict] = []
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, txs: list[dict]) -> None:
        self._txs = txs[:30]
        self.update()

    def paintEvent(self, event) -> None:
        if not self._txs:
            return
        try:
            from PyQt5.QtCore import QRectF
        except ImportError:
            from PySide6.QtCore import QRectF
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        max_btc = max(t["btc"] for t in self._txs)
        max_r = min(h / 2 - 4, 60)

        x_cursor = 12
        for tx in self._txs:
            r = max(8, int(math.sqrt(tx["btc"] / max_btc) * max_r))
            y = h // 2
            if x_cursor + r * 2 > w - 12:
                break
            # pick colour by size
            if tx["btc"] >= 1000:
                col = QColor(C.RED)
            elif tx["btc"] >= 500:
                col = QColor("#FF8C00")
            elif tx["btc"] >= 200:
                col = QColor(C.AMBER)
            else:
                col = QColor(C.CYAN)

            col.setAlpha(180)
            painter.setBrush(QBrush(col))
            outer = col.lighter(130)
            outer.setAlpha(80)
            painter.setPen(QPen(outer, 1))
            painter.drawEllipse(x_cursor, y - r, r * 2, r * 2)

            # label if large enough
            if r > 20:
                painter.setPen(QColor(C.TEXT_PRI))
                painter.setFont(QFont("JetBrains Mono", max(7, r // 4)))
                painter.drawText(
                    x_cursor, y - r, r * 2, r * 2,
                    Qt.AlignCenter,
                    f"{tx['btc']:.0f}\nBTC"
                )
            x_cursor += r * 2 + 6
        painter.end()


# ── Whale panel ───────────────────────────────────────────────────────────────

class WhalePanel(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._txs: list[dict] = []
        self._min_btc = config.WHALE_THRESHOLD_BTC
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Control bar ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.addWidget(self._header("WHALE ACTIVITY TRACKER"))
        ctrl.addStretch()

        ctrl.addWidget(QLabel("Min BTC:"))
        self._min_spin = QSpinBox()
        self._min_spin.setRange(10, 10_000)
        self._min_spin.setValue(int(self._min_btc))
        self._min_spin.setSuffix(" BTC")
        self._min_spin.setFixedWidth(110)
        self._min_spin.valueChanged.connect(self._on_filter_change)
        ctrl.addWidget(self._min_spin)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Sort: BTC ▼", "Sort: Time ▼", "Sort: USD ▼"])
        self._sort_combo.setFixedWidth(130)
        self._sort_combo.currentIndexChanged.connect(self._refresh_table)
        ctrl.addWidget(self._sort_combo)

        root.addLayout(ctrl)

        # ── Bubble chart ─────────────────────────────────────────────────────
        bubble_frame = QFrame()
        bubble_frame.setObjectName("metric_card")
        bf_l = QVBoxLayout(bubble_frame)
        bf_l.setContentsMargins(12, 8, 12, 8)
        bf_l.setSpacing(4)
        bf_l.addWidget(self._header("TRANSACTION SIZE MAP"))

        self._bubbles = BubbleFlowWidget()
        bf_l.addWidget(self._bubbles)

        legend = QHBoxLayout()
        for label, color in [("≥ 1000 BTC", C.RED), ("≥ 500 BTC", "#FF8C00"),
                              ("≥ 200 BTC", C.AMBER), ("< 200 BTC", C.CYAN)]:
            dot = QLabel(f"● {label}")
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")
            legend.addWidget(dot)
        legend.addStretch()
        bf_l.addLayout(legend)

        root.addWidget(bubble_frame)

        # ── Summary stats ─────────────────────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._stat_vals: dict[str, QLabel] = {}
        for lbl, key, color in [
            ("Total Transfers", "total", C.AMBER),
            ("BTC Moved (1H)", "btc_1h", C.CYAN),
            ("USD Value (1H)", "usd_1h", C.GREEN),
            ("Largest Transfer", "largest", C.RED),
        ]:
            card = QFrame()
            card.setObjectName("metric_card_accent")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(3)
            l = QLabel(lbl.upper())
            l.setObjectName("stat_label")
            v = QLabel("—")
            v.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 700;")
            self._stat_vals[key] = v
            cl.addWidget(l)
            cl.addWidget(v)
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        # ── TX table ─────────────────────────────────────────────────────────
        root.addWidget(self._header("LARGE TRANSACTION FEED"))

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "TXID", "BTC", "USD", "FROM", "TO",
            "CONFIRMS", "FEE (sat/vB)", "TIME",
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        for col in (1, 2, 5, 6, 7):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, stretch=3)

    @staticmethod
    def _header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        return lbl

    def _on_filter_change(self, val: int) -> None:
        self._min_btc = float(val)
        self._refresh_table()

    def _refresh_table(self) -> None:
        txs = [t for t in self._txs if t["btc"] >= self._min_btc]
        sort_idx = self._sort_combo.currentIndex()
        if sort_idx == 0:
            txs.sort(key=lambda x: x["btc"], reverse=True)
        elif sort_idx == 1:
            txs.sort(key=lambda x: x["timestamp"], reverse=True)
        else:
            txs.sort(key=lambda x: x["usd"], reverse=True)

        self._table.setRowCount(0)
        now = time.time()
        for row, tx in enumerate(txs):
            self._table.insertRow(row)
            ts = tx.get("timestamp", 0)
            age_s = int(now - ts) if ts else 0
            age = (f"{age_s // 60}m {age_s % 60}s ago"
                   if age_s < 3600 else f"{age_s // 3600}h ago")

            conf = tx.get("confirmations", 0)
            vals = [
                tx["txid"][:20] + "…",
                f"{tx['btc']:,.2f}",
                f"${tx['usd']:,.0f}",
                tx.get("from_address", "—")[:18] + "…",
                tx.get("to_address", "—")[:18] + "…",
                str(conf),
                f"{tx.get('fee_sat_vb', 0):.1f}",
                age,
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 1:
                    btc = tx["btc"]
                    c = (C.RED if btc >= 1000 else
                         "#FF8C00" if btc >= 500 else
                         C.AMBER if btc >= 200 else C.CYAN)
                    item.setForeground(QColor(c))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                elif col == 2:
                    item.setForeground(QColor(C.GREEN))
                elif col == 5:
                    c = C.GREEN if conf >= 6 else (C.AMBER if conf >= 1 else C.RED)
                    item.setForeground(QColor(c))
                self._table.setItem(row, col, item)

    # ── Public updates ────────────────────────────────────────────────────────

    def update_whale_txs(self, txs: list[dict]) -> None:
        self._txs = txs
        self._refresh_table()
        filtered = [t for t in txs if t["btc"] >= self._min_btc]
        self._bubbles.set_data(filtered[:20])

        # stats
        now = time.time()
        recent = [t for t in txs if now - t.get("timestamp", 0) <= 3600]
        btc_1h = sum(t["btc"] for t in recent)
        usd_1h = sum(t["usd"] for t in recent)
        largest = max((t["btc"] for t in txs), default=0)

        self._stat_vals["total"].setText(str(len(txs)))
        self._stat_vals["btc_1h"].setText(f"{btc_1h:,.1f} BTC")
        self._stat_vals["usd_1h"].setText(f"${usd_1h / 1e6:.2f}M")
        self._stat_vals["largest"].setText(f"{largest:,.0f} BTC")

    def add_alert_tx(self, tx: dict) -> None:
        """Highlight a newly detected whale TX with a brief flash."""
        # Simply prepend and refresh
        self._txs.insert(0, tx)
        self.update_whale_txs(self._txs)
