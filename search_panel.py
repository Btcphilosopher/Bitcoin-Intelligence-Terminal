"""
bitcoin_terminal/gui/panels/search_panel.py

Universal search panel.
Searches TXIDs, addresses, block heights, and Lightning channel IDs.
Results are displayed in a tabbed result area with detail panel.
"""

from __future__ import annotations

from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
        QHeaderView, QSplitter, QTextEdit, QComboBox, QTabWidget,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QColor, QFont
except ImportError:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
        QHeaderView, QSplitter, QTextEdit, QComboBox, QTabWidget,
    )
    from PySide6.QtCore import Qt, QThread, Signal as pyqtSignal
    from PySide6.QtGui import QColor, QFont

from gui.theme import C
from backend.rpc_client import BitcoinRPCClient


# ── Search worker ─────────────────────────────────────────────────────────────

class SearchWorker(QThread):
    result_ready = pyqtSignal(str, dict)    # (query, result_dict)
    error        = pyqtSignal(str)

    def __init__(self, rpc: BitcoinRPCClient, query: str,
                 kind: str, parent=None) -> None:
        super().__init__(parent)
        self._rpc = rpc
        self._query = query.strip()
        self._kind = kind

    def run(self) -> None:
        q = self._query
        if not q:
            return
        try:
            if self._kind == "tx" or len(q) == 64:
                data = self._rpc.get_tx(q)
                if data:
                    self.result_ready.emit(q, {"type": "tx", "data": data})
                    return
            if self._kind == "block" or q.isdigit():
                blk = self._rpc.get_block_by_height(int(q) if q.isdigit() else 0)
                if blk:
                    self.result_ready.emit(q, {"type": "block", "data": blk})
                    return
            # address or LN channel  (just echo in demo)
            self.result_ready.emit(q, {
                "type": "address",
                "data": {"address": q, "note": "Address lookup requires chain index."},
            })
        except Exception as exc:
            self.error.emit(str(exc))


# ── Search panel ──────────────────────────────────────────────────────────────

class SearchPanel(QWidget):

    def __init__(self, rpc: BitcoinRPCClient, parent=None) -> None:
        super().__init__(parent)
        self._rpc = rpc
        self._worker: SearchWorker | None = None
        self._history: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Search bar ───────────────────────────────────────────────────────
        search_frame = QFrame()
        search_frame.setObjectName("metric_card_accent")
        sfl = QVBoxLayout(search_frame)
        sfl.setContentsMargins(16, 12, 16, 12)
        sfl.setSpacing(8)

        hdr = QLabel("BITCOIN EXPLORER")
        hdr.setObjectName("section_header")
        sfl.addWidget(hdr)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        self._kind_combo = QComboBox()
        self._kind_combo.addItems(["AUTO", "TXID", "BLOCK", "ADDRESS", "LN CHANNEL"])
        self._kind_combo.setFixedWidth(130)
        bar.addWidget(self._kind_combo)

        self._search_box = QLineEdit()
        self._search_box.setObjectName("search_input")
        self._search_box.setPlaceholderText(
            "Enter transaction ID, block height, address, or channel ID…")
        self._search_box.returnPressed.connect(self._do_search)
        bar.addWidget(self._search_box)

        self._search_btn = QPushButton("SEARCH")
        self._search_btn.setObjectName("btn_primary")
        self._search_btn.setFixedWidth(100)
        self._search_btn.clicked.connect(self._do_search)
        bar.addWidget(self._search_btn)

        sfl.addLayout(bar)

        # History chips
        self._hist_row = QHBoxLayout()
        self._hist_row.setSpacing(4)
        hist_lbl = QLabel("Recent:")
        hist_lbl.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 10px;")
        self._hist_row.addWidget(hist_lbl)
        self._hist_row.addStretch()
        sfl.addLayout(self._hist_row)

        root.addWidget(search_frame)

        # ── Status ───────────────────────────────────────────────────────────
        self._status_lbl = QLabel("Enter a query to search the blockchain.")
        self._status_lbl.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # ── Result area ───────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Result tabs
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.North)

        # TX tab
        self._tx_view = QTextEdit()
        self._tx_view.setReadOnly(True)
        self._tx_view.setStyleSheet(
            f"background: {C.SURFACE}; color: {C.TEXT_PRI}; "
            f"font-family: 'JetBrains Mono', monospace; font-size: 11px; "
            f"border: 1px solid {C.BORDER};")
        self._tabs.addTab(self._tx_view, "RESULT")

        # Inputs/outputs table
        io_widget = QWidget()
        io_l = QVBoxLayout(io_widget)
        io_l.setContentsMargins(0, 0, 0, 0)
        io_l.setSpacing(6)
        io_l.addWidget(self._hdr("OUTPUTS"))
        self._vout_table = QTableWidget()
        self._vout_table.setColumnCount(3)
        self._vout_table.setHorizontalHeaderLabels(["N", "ADDRESS", "VALUE (BTC)"])
        self._vout_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._vout_table.setAlternatingRowColors(True)
        self._vout_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._vout_table.verticalHeader().setVisible(False)
        io_l.addWidget(self._vout_table)
        self._tabs.addTab(io_widget, "INPUTS / OUTPUTS")

        # Block tab
        blk_widget = QWidget()
        blk_l = QVBoxLayout(blk_widget)
        blk_l.setContentsMargins(0, 0, 0, 0)
        blk_l.setSpacing(6)
        blk_l.addWidget(self._hdr("BLOCK TRANSACTIONS"))
        self._blk_tx_table = QTableWidget()
        self._blk_tx_table.setColumnCount(2)
        self._blk_tx_table.setHorizontalHeaderLabels(["#", "TXID"])
        self._blk_tx_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._blk_tx_table.setAlternatingRowColors(True)
        self._blk_tx_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._blk_tx_table.verticalHeader().setVisible(False)
        blk_l.addWidget(self._blk_tx_table)
        self._tabs.addTab(blk_widget, "BLOCK TXS")

        splitter.addWidget(self._tabs)

        # Quick-ref card
        ref_frame = QFrame()
        ref_frame.setObjectName("metric_card")
        ref_l = QHBoxLayout(ref_frame)
        ref_l.setContentsMargins(16, 10, 16, 10)
        ref_l.setSpacing(30)

        for title, items in [
            ("TX ID", ["64 hex chars", "e.g. 4a5e1e4ba…"]),
            ("Block", ["Height (integer)", "e.g. 840000"]),
            ("Address", ["Bech32 / P2SH / P2PKH", "e.g. bc1q…"]),
            ("LN Channel", ["Short channel ID", "e.g. 740000x1x0"]),
        ]:
            col = QVBoxLayout()
            t = QLabel(title.upper())
            t.setObjectName("stat_label")
            col.addWidget(t)
            for item in items:
                l = QLabel(item)
                l.setStyleSheet(f"color: {C.TEXT_PRI}; font-size: 11px;")
                col.addWidget(l)
            ref_l.addLayout(col)
        ref_l.addStretch()

        splitter.addWidget(ref_frame)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    @staticmethod
    def _hdr(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        return lbl

    # ── Search logic ──────────────────────────────────────────────────────────

    def _do_search(self) -> None:
        q = self._search_box.text().strip()
        if not q:
            return
        self._status_lbl.setText(f"Searching for: {q} …")
        self._search_btn.setEnabled(False)
        kind = self._kind_combo.currentText().lower().replace(" ", "")

        self._worker = SearchWorker(self._rpc, q, kind)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        self._add_to_history(q)

    def _add_to_history(self, q: str) -> None:
        if q not in self._history:
            self._history.insert(0, q)
            self._history = self._history[:6]
        # Rebuild chip row
        for i in reversed(range(self._hist_row.count())):
            item = self._hist_row.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        hist_lbl = QLabel("Recent:")
        hist_lbl.setStyleSheet(f"color: {C.TEXT_SEC}; font-size: 10px;")
        self._hist_row.addWidget(hist_lbl)

        for h in self._history[:5]:
            btn = QPushButton(h[:18] + ("…" if len(h) > 18 else ""))
            btn.setStyleSheet(
                f"QPushButton {{ background: {C.PANEL_ALT}; border: 1px solid {C.BORDER}; "
                f"border-radius: 10px; padding: 2px 8px; font-size: 10px; color: {C.TEXT_SEC}; }}"
                f"QPushButton:hover {{ color: {C.AMBER}; border-color: {C.AMBER_DIM}; }}"
            )
            btn.clicked.connect(lambda checked, q=h: self._jump_to(q))
            self._hist_row.addWidget(btn)
        self._hist_row.addStretch()

    def _jump_to(self, q: str) -> None:
        self._search_box.setText(q)
        self._do_search()

    def _on_result(self, query: str, result: dict) -> None:
        self._search_btn.setEnabled(True)
        kind = result["type"]
        data = result["data"]

        if kind == "tx":
            self._render_tx(data)
        elif kind == "block":
            self._render_block(data)
        else:
            self._tx_view.setPlainText(
                f"Address: {data.get('address','—')}\n{data.get('note','')}"
            )
        self._status_lbl.setText(f"Found: [{kind.upper()}] for query '{query}'")

    def _on_error(self, msg: str) -> None:
        self._search_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {msg}")

    def _render_tx(self, tx: dict) -> None:
        lines = [
            f"TXID         : {tx.get('txid', '—')}",
            f"Size         : {tx.get('size', 0):,} bytes  (vsize: {tx.get('vsize', 0):,})",
            f"Weight       : {tx.get('weight', 0):,}",
            f"Version      : {tx.get('version', 1)}",
            f"Locktime     : {tx.get('locktime', 0)}",
            f"Confirmations: {tx.get('confirmations', 0)}",
            "",
            f"Inputs  ({len(tx.get('vin', []))})",
        ]
        for i, inp in enumerate(tx.get("vin", [])):
            lines.append(f"  [{i}]  {inp.get('txid','coinbase')[:36]}…  vout={inp.get('vout','—')}")

        lines.append(f"\nOutputs ({len(tx.get('vout', []))})")
        self._vout_table.setRowCount(0)
        for vout in tx.get("vout", []):
            lines.append(
                f"  [{vout['n']}]  "
                f"{vout.get('scriptPubKey', {}).get('address', 'OP_RETURN'):<44}  "
                f"{vout['value']:.8f} BTC"
            )
            r = self._vout_table.rowCount()
            self._vout_table.insertRow(r)
            addr = vout.get("scriptPubKey", {}).get("address", "OP_RETURN")
            for col, v in enumerate([str(vout["n"]), addr, f"{vout['value']:.8f}"]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 2:
                    item.setForeground(QColor(C.AMBER))
                self._vout_table.setItem(r, col, item)

        self._tx_view.setPlainText("\n".join(lines))
        self._tabs.setCurrentIndex(0)

    def _render_block(self, blk: dict) -> None:
        ts = blk.get("time", 0)
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "—"
        lines = [
            f"HEIGHT       : {blk.get('height', '—'):,}",
            f"HASH         : {blk.get('hash', '—')}",
            f"TIMESTAMP    : {dt}",
            f"TRANSACTIONS : {blk.get('nTx', blk.get('ntx', '—')):,}",
            f"SIZE         : {blk.get('size', 0):,} bytes",
            f"WEIGHT       : {blk.get('weight', 0):,}",
            f"DIFFICULTY   : {blk.get('difficulty', 0):,.2f}",
            f"NONCE        : {blk.get('nonce', '—')}",
            f"BITS         : {blk.get('bits', '—')}",
            f"VERSION      : {blk.get('version', '—')}",
            f"CHAINWORK    : {blk.get('chainwork', '—')}",
        ]
        self._tx_view.setPlainText("\n".join(lines))

        # TX list
        txs = blk.get("tx", [])
        self._blk_tx_table.setRowCount(0)
        for i, txid in enumerate(txs[:200]):
            r = self._blk_tx_table.rowCount()
            self._blk_tx_table.insertRow(r)
            for col, v in enumerate([str(i), str(txid)]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 1:
                    item.setForeground(QColor(C.CYAN))
                self._blk_tx_table.setItem(r, col, item)

        self._tabs.setCurrentIndex(0)

    def search_for(self, query: str) -> None:
        """External call to trigger a search from another panel."""
        self._search_box.setText(query)
        self._do_search()
