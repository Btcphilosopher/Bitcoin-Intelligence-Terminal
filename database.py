"""
bitcoin_terminal/backend/database.py

SQLite persistence layer.
Stores block summaries, mempool snapshots, price history, and alerts.
All writes are async-safe via a dedicated writer thread (WAL mode).
"""

from __future__ import annotations

import sqlite3
import threading
import time
import logging
from pathlib import Path
from typing import Any

import config

log = logging.getLogger(__name__)

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous   = NORMAL;

CREATE TABLE IF NOT EXISTS blocks (
    height          INTEGER PRIMARY KEY,
    hash            TEXT    NOT NULL,
    timestamp       INTEGER NOT NULL,
    n_tx            INTEGER NOT NULL,
    size            INTEGER NOT NULL,
    weight          INTEGER NOT NULL,
    difficulty      REAL    NOT NULL,
    total_output_btc REAL   DEFAULT 0,
    total_fees_btc  REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mempool_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       INTEGER NOT NULL,
    tx_count        INTEGER NOT NULL,
    size_bytes      INTEGER NOT NULL,
    total_fee_btc   REAL    NOT NULL,
    min_fee_sat_vb  REAL    NOT NULL,
    median_fee_sat_vb REAL  NOT NULL,
    max_fee_sat_vb  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       INTEGER NOT NULL,
    price_usd       REAL    NOT NULL,
    source          TEXT    DEFAULT 'coingecko'
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       INTEGER NOT NULL,
    severity        TEXT    NOT NULL,   -- INFO | WARNING | CRITICAL
    category        TEXT    NOT NULL,   -- MEMPOOL | WHALE | BLOCK | PRICE | LN
    title           TEXT    NOT NULL,
    body            TEXT    NOT NULL,
    acknowledged    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whale_transactions (
    txid            TEXT    PRIMARY KEY,
    timestamp       INTEGER NOT NULL,
    btc_amount      REAL    NOT NULL,
    usd_amount      REAL    NOT NULL,
    from_address    TEXT,
    to_address      TEXT,
    confirmations   INTEGER DEFAULT 0,
    fee_sat_vb      REAL    DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mempool_ts   ON mempool_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_price_ts     ON price_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_ts    ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_whale_ts     ON whale_transactions(timestamp);
"""


class Database:
    """Thread-safe SQLite wrapper."""

    def __init__(self, path: Path = config.DB_PATH) -> None:
        self._path = path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self._path))
            conn.executescript(_SCHEMA)
            conn.commit()
            conn.close()
        log.info("Database initialised at %s", self._path)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn().execute(sql, params)

    def executemany(self, sql: str, data: list) -> None:
        with self._lock:
            self._conn().executemany(sql, data)
            self._conn().commit()

    def commit(self) -> None:
        with self._lock:
            self._conn().commit()

    # ── Block storage ─────────────────────────────────────────────────────────

    def upsert_block(self, block: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO blocks
            (height, hash, timestamp, n_tx, size, weight, difficulty,
             total_output_btc, total_fees_btc)
            VALUES (?,?,?,?,?,?,?,?,?)
        """
        with self._lock:
            self._conn().execute(sql, (
                block["height"],
                block.get("hash", ""),
                block.get("time", 0),
                block.get("nTx", block.get("ntx", 0)),
                block.get("size", 0),
                block.get("weight", 0),
                block.get("difficulty", 0.0),
                block.get("_total_output_btc", 0.0),
                block.get("_total_fees_btc", 0.0),
            ))
            self._conn().commit()

    def get_blocks(self, limit: int = 200, offset: int = 0) -> list[dict]:
        cur = self.execute(
            "SELECT * FROM blocks ORDER BY height DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_block_range(self, start_height: int, end_height: int) -> list[dict]:
        cur = self.execute(
            "SELECT * FROM blocks WHERE height BETWEEN ? AND ? ORDER BY height",
            (start_height, end_height),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Mempool snapshots ─────────────────────────────────────────────────────

    def insert_mempool_snapshot(self, data: dict) -> None:
        sql = """
            INSERT INTO mempool_snapshots
            (timestamp, tx_count, size_bytes, total_fee_btc,
             min_fee_sat_vb, median_fee_sat_vb, max_fee_sat_vb)
            VALUES (?,?,?,?,?,?,?)
        """
        with self._lock:
            self._conn().execute(sql, (
                data["timestamp"],
                data["tx_count"],
                data["size_bytes"],
                data["total_fee_btc"],
                data["min_fee_sat_vb"],
                data["median_fee_sat_vb"],
                data["max_fee_sat_vb"],
            ))
            self._conn().commit()

    def get_mempool_history(self, hours: int = 24) -> list[dict]:
        since = int(time.time()) - hours * 3600
        cur = self.execute(
            "SELECT * FROM mempool_snapshots WHERE timestamp > ? ORDER BY timestamp",
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Price history ─────────────────────────────────────────────────────────

    def insert_price(self, price_usd: float, source: str = "coingecko") -> None:
        with self._lock:
            self._conn().execute(
                "INSERT INTO price_history (timestamp, price_usd, source) VALUES (?,?,?)",
                (int(time.time()), price_usd, source),
            )
            self._conn().commit()

    def get_price_history(self, hours: int = 24) -> list[dict]:
        since = int(time.time()) - hours * 3600
        cur = self.execute(
            "SELECT * FROM price_history WHERE timestamp > ? ORDER BY timestamp",
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_latest_price(self) -> float | None:
        cur = self.execute(
            "SELECT price_usd FROM price_history ORDER BY timestamp DESC LIMIT 1"
        )
        row = cur.fetchone()
        return row["price_usd"] if row else None

    # ── Alerts ────────────────────────────────────────────────────────────────

    def insert_alert(self, severity: str, category: str,
                     title: str, body: str) -> int:
        with self._lock:
            cur = self._conn().execute(
                """INSERT INTO alerts (timestamp, severity, category, title, body)
                   VALUES (?,?,?,?,?)""",
                (int(time.time()), severity, category, title, body),
            )
            self._conn().commit()
            return cur.lastrowid

    def get_alerts(self, limit: int = 100, unread_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM alerts"
        params: tuple = ()
        if unread_only:
            sql += " WHERE acknowledged = 0"
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params = (limit,)
        cur = self.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def acknowledge_alert(self, alert_id: int) -> None:
        with self._lock:
            self._conn().execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
            )
            self._conn().commit()

    def acknowledge_all_alerts(self) -> None:
        with self._lock:
            self._conn().execute("UPDATE alerts SET acknowledged = 1")
            self._conn().commit()

    def get_unread_alert_count(self) -> int:
        cur = self.execute(
            "SELECT COUNT(*) AS c FROM alerts WHERE acknowledged = 0"
        )
        return cur.fetchone()["c"]

    # ── Whale transactions ────────────────────────────────────────────────────

    def upsert_whale_tx(self, tx: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO whale_transactions
            (txid, timestamp, btc_amount, usd_amount,
             from_address, to_address, confirmations, fee_sat_vb)
            VALUES (?,?,?,?,?,?,?,?)
        """
        with self._lock:
            self._conn().execute(sql, (
                tx["txid"],
                tx["timestamp"],
                tx["btc"],
                tx["usd"],
                tx.get("from_address", ""),
                tx.get("to_address", ""),
                tx.get("confirmations", 0),
                tx.get("fee_sat_vb", 0),
            ))
            self._conn().commit()

    def get_whale_transactions(self, limit: int = 50,
                               min_btc: float = 0.0) -> list[dict]:
        cur = self.execute(
            """SELECT * FROM whale_transactions
               WHERE btc_amount >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (min_btc, limit),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Stats helpers ─────────────────────────────────────────────────────────

    def get_db_stats(self) -> dict:
        tables = ["blocks", "mempool_snapshots", "price_history",
                  "alerts", "whale_transactions"]
        stats = {}
        for t in tables:
            cur = self.execute(f"SELECT COUNT(*) AS c FROM {t}")
            stats[t] = cur.fetchone()["c"]
        return stats
