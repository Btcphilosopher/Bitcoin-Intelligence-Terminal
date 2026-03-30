"""
bitcoin_terminal/gui/panels/alerts_panel.py

Alert centre — displays all system-generated alerts with severity
filtering, acknowledgement controls, and sound-on-critical support.
"""

from __future__ import annotations

import time
from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
        QComboBox, QCheckBox, QSizePolicy, QAbstractItemView,
        QTextEdit, QSplitter,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QFont
except ImportError:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
        QComboBox, QCheckBox, QSizePolicy, QAbstractItemView,
        QTextEdit, QSplitter,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont

from gui.theme import C, severity_color, severity_bg
from backend.database import Database


SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
CATEGORY_ICONS = {
    "MEMPOOL": "⛏",
    "WHALE":   "🐋",
    "PRICE":   "₿",
    "LN":      "⚡",
    "BLOCK":   "◼",
}


class AlertsPanel(QWidget):

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._all_alerts: list[dict] = []
        self._build_ui()
        self._refresh_from_db()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Header & controls ─────────────────────────────────────────────────
        ctrl = QHBoxLayout()

        hdr = QLabel("ALERT CENTRE")
        hdr.setObjectName("section_header")
        ctrl.addWidget(hdr)
        ctrl.addStretch()

        self._unread_badge = QLabel("0 unread")
        self._unread_badge.setStyleSheet(
            f"color: {C.RED}; font-size: 11px; font-weight: 700;")
        ctrl.addWidget(self._unread_badge)

        self._sev_filter = QComboBox()
        self._sev_filter.addItems(["ALL SEVERITY", "CRITICAL", "WARNING", "INFO"])
        self._sev_filter.setFixedWidth(130)
        self._sev_filter.currentIndexChanged.connect(self._apply_filter)
        ctrl.addWidget(self._sev_filter)

        self._cat_filter = QComboBox()
        self._cat_filter.addItems(["ALL CATEGORIES", "MEMPOOL", "WHALE",
                                   "PRICE", "LN", "BLOCK"])
        self._cat_filter.setFixedWidth(140)
        self._cat_filter.currentIndexChanged.connect(self._apply_filter)
        ctrl.addWidget(self._cat_filter)

        self._unread_only = QCheckBox("Unread only")
        self._unread_only.stateChanged.connect(self._apply_filter)
        ctrl.addWidget(self._unread_only)

        ack_btn = QPushButton("ACK ALL")
        ack_btn.setObjectName("btn_primary")
        ack_btn.setFixedWidth(80)
        ack_btn.clicked.connect(self._ack_all)
        ctrl.addWidget(ack_btn)

        root.addLayout(ctrl)

        # ── Summary strip ─────────────────────────────────────────────────────
        strip = QHBoxLayout()
        strip.setSpacing(10)
        self._sum_vals: dict[str, QLabel] = {}
        for sev, color in [("CRITICAL", C.RED), ("WARNING", C.YELLOW), ("INFO", C.CYAN)]:
            card = QFrame()
            card.setObjectName("metric_card")
            card.setStyleSheet(
                f"QFrame#metric_card {{ border-left: 3px solid {color}; }}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(2)
            l = QLabel(sev)
            l.setObjectName("stat_label")
            v = QLabel("0")
            v.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")
            self._sum_vals[sev] = v
            cl.addWidget(l)
            cl.addWidget(v)
            strip.addWidget(card)
        strip.addStretch()
        root.addLayout(strip)

        # ── Main splitter: table | detail ─────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "", "SEVERITY", "CATEGORY", "TITLE", "BODY", "TIME",
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._table.setColumnWidth(3, 220)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_row_select)
        splitter.addWidget(self._table)

        # Detail card
        detail = QFrame()
        detail.setObjectName("metric_card")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(16, 12, 16, 12)
        dl.setSpacing(8)
        self._detail_title = QLabel("Select an alert to view details.")
        self._detail_title.setStyleSheet(
            f"color: {C.AMBER}; font-size: 13px; font-weight: 700;")
        self._detail_body = QTextEdit()
        self._detail_body.setReadOnly(True)
        self._detail_body.setStyleSheet(
            f"background: {C.SURFACE}; color: {C.TEXT_PRI}; font-size: 11px; "
            f"border: none;")
        self._detail_body.setMaximumHeight(80)
        self._ack_btn = QPushButton("ACKNOWLEDGE")
        self._ack_btn.setObjectName("btn_primary")
        self._ack_btn.setFixedWidth(140)
        self._ack_btn.setEnabled(False)
        self._ack_btn.clicked.connect(self._ack_selected)
        dl.addWidget(self._detail_title)
        dl.addWidget(self._detail_body)
        dl.addWidget(self._ack_btn, alignment=Qt.AlignRight)
        splitter.addWidget(detail)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _render_table(self, alerts: list[dict]) -> None:
        self._table.setRowCount(0)
        for row, alert in enumerate(alerts):
            self._table.insertRow(row)
            ts = alert.get("timestamp", 0)
            dt = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M:%S") if ts else "—"
            sev  = alert.get("severity", "INFO")
            cat  = alert.get("category", "—")
            ack  = bool(alert.get("acknowledged", 0))
            icon = CATEGORY_ICONS.get(cat, "•")
            color = severity_color(sev)
            bg = severity_bg(sev) if not ack else C.SURFACE

            vals = [
                "✓" if ack else "●",
                sev,
                f"{icon} {cat}",
                alert.get("title", ""),
                alert.get("body", ""),
                dt,
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter if col != 4 else Qt.AlignLeft | Qt.AlignVCenter)
                item.setData(Qt.UserRole, alert.get("id"))
                if col == 1:
                    item.setForeground(QColor(color))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif col == 0:
                    item.setForeground(QColor(C.GREEN if ack else C.RED))
                else:
                    item.setForeground(QColor(
                        C.TEXT_SEC if ack else C.TEXT_PRI))
                self._table.setItem(row, col, item)

    def _apply_filter(self) -> None:
        sev_filter = self._sev_filter.currentText()
        cat_filter = self._cat_filter.currentText()
        unread = self._unread_only.isChecked()

        filtered = self._all_alerts
        if sev_filter != "ALL SEVERITY":
            filtered = [a for a in filtered if a.get("severity") == sev_filter]
        if cat_filter != "ALL CATEGORIES":
            filtered = [a for a in filtered if a.get("category") == cat_filter]
        if unread:
            filtered = [a for a in filtered if not a.get("acknowledged")]

        self._render_table(filtered)

    def _on_row_select(self) -> None:
        rows = self._table.selectedItems()
        if not rows:
            return
        row = self._table.currentRow()
        title = self._table.item(row, 3)
        body  = self._table.item(row, 4)
        sev   = self._table.item(row, 1)
        if title:
            self._detail_title.setText(title.text())
            color = severity_color(sev.text() if sev else "INFO")
            self._detail_title.setStyleSheet(
                f"color: {color}; font-size: 13px; font-weight: 700;")
        if body:
            self._detail_body.setPlainText(body.text())
        self._ack_btn.setEnabled(True)
        self._selected_id = (
            self._table.item(row, 0).data(Qt.UserRole) if self._table.item(row, 0) else None
        )

    def _ack_selected(self) -> None:
        if self._selected_id is not None:
            self._db.acknowledge_alert(self._selected_id)
        self._refresh_from_db()

    def _ack_all(self) -> None:
        self._db.acknowledge_all_alerts()
        self._refresh_from_db()

    def _refresh_from_db(self) -> None:
        self._all_alerts = self._db.get_alerts(limit=200)
        self._update_summary()
        self._apply_filter()

    def _update_summary(self) -> None:
        counts = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
        unread = 0
        for a in self._all_alerts:
            sev = a.get("severity", "INFO")
            if sev in counts:
                counts[sev] += 1
            if not a.get("acknowledged"):
                unread += 1
        for sev, v in counts.items():
            self._sum_vals[sev].setText(str(v))
        self._unread_badge.setText(
            f"{unread} unread" if unread else "All read ✓"
        )
        self._unread_badge.setStyleSheet(
            f"color: {C.RED if unread else C.GREEN}; font-size: 11px; font-weight: 700;")

    # ── Public slots ──────────────────────────────────────────────────────────

    def add_alert(self, alert: dict) -> None:
        """Called when a new alert fires from the AlertWorker."""
        self._all_alerts.insert(0, alert)
        self._update_summary()
        self._apply_filter()

    def update_unread_count(self, count: int) -> None:
        self._unread_badge.setText(
            f"{count} unread" if count else "All read ✓"
        )
        self._unread_badge.setStyleSheet(
            f"color: {C.RED if count else C.GREEN}; font-size: 11px; font-weight: 700;")
