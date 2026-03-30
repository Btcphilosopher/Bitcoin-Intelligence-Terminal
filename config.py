"""
Bitcoin Terminal — Configuration
Centralises all node endpoints, credentials, and runtime flags.
Edit this file before launching; do NOT commit secrets to version control.
"""

import os
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# ── Bitcoin Core RPC ──────────────────────────────────────────────────────────
BITCOIN_RPC_HOST     = os.getenv("BTC_RPC_HOST",     "127.0.0.1")
BITCOIN_RPC_PORT     = int(os.getenv("BTC_RPC_PORT", "8332"))
BITCOIN_RPC_USER     = os.getenv("BTC_RPC_USER",     "bitcoinrpc")
BITCOIN_RPC_PASSWORD = os.getenv("BTC_RPC_PASS",     "changeme")
BITCOIN_RPC_TIMEOUT  = 30   # seconds

# ── Lightning Node (LND gRPC) ─────────────────────────────────────────────────
LND_HOST         = os.getenv("LND_HOST",    "127.0.0.1")
LND_GRPC_PORT    = int(os.getenv("LND_PORT", "10009"))
LND_MACAROON     = os.getenv("LND_MACAROON_PATH",
                   str(Path.home() / ".lnd/data/chain/bitcoin/mainnet/admin.macaroon"))
LND_TLS_CERT     = os.getenv("LND_TLS_CERT_PATH",
                   str(Path.home() / ".lnd/tls.cert"))

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = BASE_DIR / "bitcoin_terminal.db"

# ── Price feed ────────────────────────────────────────────────────────────────
PRICE_FEED_URL   = "https://api.coingecko.com/api/v3/simple/price"
BINANCE_WS_URL   = "wss://stream.binance.com:9443/ws/btcusdt@ticker"

# ── Polling intervals (seconds) ───────────────────────────────────────────────
BLOCK_POLL_INTERVAL   = 10
MEMPOOL_POLL_INTERVAL = 5
PRICE_POLL_INTERVAL   = 3
LN_POLL_INTERVAL      = 15
WHALE_THRESHOLD_BTC   = 100      # flag transfers >= this value
ALERT_CHECK_INTERVAL  = 10

# ── Demo / simulation mode ────────────────────────────────────────────────────
# When True the app generates realistic synthetic data so it can run
# without a live Bitcoin or Lightning node.
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"

# ── UI ────────────────────────────────────────────────────────────────────────
APP_TITLE   = "SATURN — Bitcoin Intelligence Terminal"
APP_VERSION = "1.0.0"
WINDOW_W    = 1600
WINDOW_H    = 960
