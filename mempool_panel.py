"""
bitcoin_terminal/gui/panels/mempool_panel.py

Mempool visualisation panel.
• Fee rate histogram rendered natively via QPainter (no Matplotlib dep)
• Congestion meter
• Historical mempool size chart (sparkline)
• Fee tier quick-reference table
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
        QGridLayout, QProgressBar, QSplitter,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
except ImportError:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
        QGridLayout, QProgressBar, QSplitter,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient

from gui.theme import C


# ── Fee histogram ─────────────────────────────────────────────────────────────

class FeeHistogramWidget(QWidget):
    """Native QPainter bar chart for mempool fee distribution."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[float, int]] = []   # (sat/vB, count)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hovered: int | None = None
        self.setMouseTracking(True)

    def set_data(self, histogram: list[tuple[float, int]]) -> None:
        self._data = histogram[:120]   # cap to 120 sat/vB
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._data:
            return
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 50, 20, 20, 40
        bar_w = max(2, (w - pad_l - pad_r) // max(len(self._data), 1))
        x = event.x()
        idx = (x - pad_l) // max(bar_w, 1)
        self._hovered = idx if 0 <= idx < len(self._data) else None
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = None
        self.update()

    def paintEvent(self, event) -> None:
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 50, 20, 20, 40
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_t - pad_b

        max_count = max(c for _, c in self._data) or 1
        n = len(self._data)
        bar_w = max(2, chart_w // n)

        # Background grid
        painter.setPen(QPen(QColor(C.BORDER), 1))
        for i in range(5):
            y = pad_t + i * chart_h // 4
            painter.drawLine(pad_l, y, w - pad_r, y)

        # Bars
        for i, (fee, count) in enumerate(self._data):
            bar_h = int((count / max_count) * chart_h)
            x = pad_l + i * bar_w
            y = pad_t + chart_h - bar_h

            # Colour by fee tier
            if fee <= 5:
                color = QColor(C.GREEN)
            elif fee <= 20:
                color = QColor(C.AMBER)
            elif fee <= 50:
                color = QColor("#FF8C00")
            else:
                color = QColor(C.RED)

            if i == self._hovered:
                color = color.lighter(140)

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRect(x, y, bar_w - 1, bar_h)

        # Hover tooltip
        if self._hovered is not None and self._hovered < len(self._data):
            fee, count = self._data[self._hovered]
            tip = f"{fee:.0f} sat/vB  •  {count:,} txs"
            bar_x = pad_l + self._hovered * bar_w
            bar_h = int((count / max_count) * chart_h)
            tip_y = pad_t + chart_h - bar_h - 8

            painter.setPen(QPen(QColor(C.AMBER), 1))
            painter.setBrush(QBrush(QColor(C.PANEL)))
            tp_w, tp_h = 170, 24
            tp_x = min(bar_x, w - tp_w - 4)
            painter.drawRoundedRect(tp_x, max(4, tip_y - tp_h), tp_w, tp_h, 3, 3)
            painter.setPen(QColor(C.AMBER_GLOW))
            painter.setFont(QFont("JetBrains Mono", 9))
            painter.drawText(tp_x + 8, max(4, tip_y - tp_h) + 15, tip)

        # X-axis labels
        painter.setPen(QColor(C.TEXT_SEC))
        painter.setFont(QFont("JetBrains Mono", 8))
        tick_every = max(1, n // 10)
        for i, (fee, _) in enumerate(self._data):
            if i % tick_every == 0:
                x = pad_l + i * bar_w
                painter.drawText(x - 5, h - 8, f"{fee:.0f}")

        # Y-axis labels
        for i in range(5):
            v = int((1 - i / 4) * max_count)
            y = pad_t + i * chart_h // 4
            painter.drawText(4, y + 4, f"{v:,}")

        # Axis labels
        painter.setPen(QColor(C.TEXT_MUT))
        painter.setFont(QFont("JetBrains Mono", 9))
        painter.drawText(w // 2 - 40, h - 2, "sat / vByte")
        painter.end()


# ── Mempool size sparkline ─────────────────────────────────────────────────────

class MempoolSizeWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[int] = []
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, snapshots: list[dict]) -> None:
        self._data = [s["tx_count"] for s in snapshots[-300:]]
        self.update()

    def paintEvent(self, event) -> None:
        if len(self._data) < 2:
            return
        try:
            from PyQt5.QtCore import QPointF
            from PyQt5.QtGui import QPolygonF
        except ImportError:
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QPolygonF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 4
        lo, hi = min(self._data), max(self._data)
        rng = max(hi - lo, 1)

        def xf(i): return pad + (i / (len(self._data) - 1)) * (w - 2 * pad)
        def yf(v): return h - pad - ((v - lo) / rng) * (h - 2 * pad)

        grad = QLinearGradient(0, 0, 0, h)
        tc = QColor(C.CYAN)
        tc.setAlpha(50)
        bc = QColor(C.BASE)
        bc.setAlpha(0)
        grad.setColorAt(0, tc)
        grad.setColorAt(1, bc)

        poly = [QPointF(xf(i), yf(v)) for i, v in enumerate(self._data)]
        poly.append(QPointF(xf(len(self._data) - 1), h))
        poly.append(QPointF(xf(0), h))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF(poly))

        painter.setPen(QPen(QColor(C.CYAN), 1.5))
        painter.setBrush(Qt.NoBrush)
        for i in range(1, len(self._data)):
            painter.drawLine(int(xf(i-1)), int(yf(self._data[i-1])),
                             int(xf(i)), int(yf(self._data[i])))
        painter.end()


# ── Main panel ────────────────────────────────────────────────────────────────

class MempoolPanel(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ── Top metric strip ─────────────────────────────────────────────────
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(10)

        self._stat_vals: dict[str, QLabel] = {}
        stats = [
            ("TX Count", "tx_count", C.AMBER),
            ("Size (MB)", "size_mb", C.CYAN),
            ("Total Fees (BTC)", "total_fee", C.GREEN),
            ("Min Fee (sat/vB)", "min_fee", C.AMBER),
            ("Median Fee", "med_fee", C.CYAN),
            ("Max Fee", "max_fee", C.RED),
        ]
        for lbl, key, color in stats:
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
            metrics_row.addWidget(card)
        root.addLayout(metrics_row)

        # ── Histogram section ────────────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        hist_frame = QFrame()
        hist_frame.setObjectName("metric_card")
        hf_layout = QVBoxLayout(hist_frame)
        hf_layout.setContentsMargins(12, 10, 12, 10)
        hf_layout.setSpacing(8)

        hist_hdr = QHBoxLayout()
        hist_title = QLabel("FEE RATE DISTRIBUTION  (sat/vByte)")
        hist_title.setObjectName("section_header")
        self._legend = QLabel(
            "■ <5  ■ 5-20  ■ 20-50  ■ >50 sat/vB"
        )
        self._legend.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 10px;")
        hist_hdr.addWidget(hist_title)
        hist_hdr.addStretch()
        hist_hdr.addWidget(self._legend)

        hf_layout.addLayout(hist_hdr)

        self._histogram = FeeHistogramWidget()
        hf_layout.addWidget(self._histogram)
        splitter.addWidget(hist_frame)

        # Bottom row: mempool history + fee tiers table
        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)

        # Mempool size history
        hist2_frame = QFrame()
        hist2_frame.setObjectName("metric_card")
        h2l = QVBoxLayout(hist2_frame)
        h2l.setContentsMargins(12, 10, 12, 10)
        h2l.setSpacing(6)
        h2l.addWidget(self._header("MEMPOOL SIZE  (24H HISTORY)"))
        self._size_chart = MempoolSizeWidget()
        h2l.addWidget(self._size_chart)
        bl.addWidget(hist2_frame, 2)

        # Fee tiers table
        tier_frame = QFrame()
        tier_frame.setObjectName("metric_card")
        tl = QVBoxLayout(tier_frame)
        tl.setContentsMargins(12, 10, 12, 10)
        tl.setSpacing(6)
        tl.addWidget(self._header("FEE PRIORITY TIERS"))

        self._tier_table = QTableWidget(6, 3)
        self._tier_table.setHorizontalHeaderLabels(["PRIORITY", "SAT/vB", "ETA"])
        self._tier_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tier_table.verticalHeader().setVisible(False)
        self._tier_table.setEditTriggers(QTableWidget.NoEditTriggers)

        tiers = [
            ("⚡ Next Block",  "—", "~10 min"),
            ("◆ 3 Blocks",    "—", "~30 min"),
            ("● 6 Blocks",    "—", "~1 hour"),
            ("○ 12 Blocks",   "—", "~2 hours"),
            ("· Day",         "—", "~24 hours"),
            ("· Economy",     "—", "> 24 hours"),
        ]
        self._tier_sat_cells: list[QTableWidgetItem] = []
        for r, (pri, sat, eta) in enumerate(tiers):
            for c, v in enumerate([pri, sat, eta]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 0:
                    item.setForeground(QColor(C.AMBER))
                elif c == 1:
                    item.setForeground(QColor(C.CYAN))
                self._tier_table.setItem(r, c, item)
            self._tier_sat_cells.append(self._tier_table.item(r, 1))

        tl.addWidget(self._tier_table)
        bl.addWidget(tier_frame, 2)

        # Congestion meter
        cong_frame = QFrame()
        cong_frame.setObjectName("metric_card")
        cgl = QVBoxLayout(cong_frame)
        cgl.setContentsMargins(12, 10, 12, 10)
        cgl.setSpacing(8)
        cgl.addWidget(self._header("CONGESTION LEVEL"))

        self._cong_label = QLabel("MODERATE")
        self._cong_label.setAlignment(Qt.AlignCenter)
        self._cong_label.setStyleSheet(
            f"color: {C.AMBER}; font-size: 20px; font-weight: 700; "
            f"letter-spacing: 3px;")
        cgl.addWidget(self._cong_label)

        self._cong_bar = QProgressBar()
        self._cong_bar.setRange(0, 100)
        self._cong_bar.setValue(40)
        self._cong_bar.setTextVisible(False)
        self._cong_bar.setFixedHeight(10)
        cgl.addWidget(self._cong_bar)

        self._cong_desc = QLabel("")
        self._cong_desc.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 10px;")
        self._cong_desc.setWordWrap(True)
        self._cong_desc.setAlignment(Qt.AlignCenter)
        cgl.addWidget(self._cong_desc)
        cgl.addStretch()

        bl.addWidget(cong_frame, 1)
        bottom.setLayout(bl)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter)

    @staticmethod
    def _header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        return lbl

    # ── Public updates ────────────────────────────────────────────────────────

    def update_mempool_info(self, info: dict) -> None:
        size = info.get("size", 0)
        bytes_ = info.get("bytes", 0)
        fee = info.get("total_fee", 0.0)

        self._stat_vals["tx_count"].setText(f"{size:,}")
        self._stat_vals["size_mb"].setText(f"{bytes_ / 1e6:.2f}")
        self._stat_vals["total_fee"].setText(f"{fee:.4f}")

        # Congestion
        max_pool = info.get("maxmempool", 300_000_000)
        pct = min(100, int(bytes_ / max_pool * 100))
        self._cong_bar.setValue(pct)
        if pct < 25:
            level, color = "LOW", C.GREEN
            desc = "Mempool has ample capacity. Economy fees are viable."
        elif pct < 55:
            level, color = "MODERATE", C.AMBER
            desc = "Moderate congestion. Standard fees for timely confirmation."
        elif pct < 80:
            level, color = "HIGH", "#FF8C00"
            desc = "High congestion. Use next-block fee for reliable confirmation."
        else:
            level, color = "CRITICAL", C.RED
            desc = "Extreme congestion. High fees required for any confirmation."
        self._cong_label.setText(level)
        self._cong_label.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: 700; "
            f"letter-spacing: 3px;")
        self._cong_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}")
        self._cong_desc.setText(desc)

    def update_fee_histogram(self, histogram: list[tuple[float, int]]) -> None:
        self._histogram.set_data(histogram)
        if not histogram:
            return
        fees = [f for f, _ in histogram]
        self._stat_vals["min_fee"].setText(f"{min(fees):.0f}")
        self._stat_vals["max_fee"].setText(f"{max(fees):.0f}")
        self._stat_vals["med_fee"].setText(f"{fees[len(fees)//2]:.0f}")

    def update_fee_tiers(self, fee_1: float, fee_3: float, fee_6: float,
                         fee_12: float, fee_day: float) -> None:
        sat = lambda f: f"{round(f * 1e5, 1)}"
        vals = [sat(fee_1), sat(fee_3), sat(fee_6), sat(fee_12),
                sat(fee_day), sat(fee_day * 0.5)]
        for cell, v in zip(self._tier_sat_cells, vals):
            cell.setText(v)

    def update_history(self, snapshots: list[dict]) -> None:
        self._size_chart.set_data(snapshots)
