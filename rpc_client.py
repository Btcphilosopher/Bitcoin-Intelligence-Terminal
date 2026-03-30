"""
bitcoin_terminal/backend/rpc_client.py

Bitcoin Core JSON-RPC wrapper.
Falls back to realistic synthetic data when DEMO_MODE=1 or the node
is unreachable.
"""

from __future__ import annotations

import random
import time
import math
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

import config

log = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _rng_seed(block_height: int) -> random.Random:
    """Deterministic RNG per block so repeated calls are stable."""
    return random.Random(block_height * 0xDEADBEEF)


# ── RPC client ────────────────────────────────────────────────────────────────

class BitcoinRPCError(Exception):
    pass


class BitcoinRPCClient:
    """
    Thin wrapper around Bitcoin Core's JSON-RPC 1.0 interface.

    All public methods return plain Python dicts / lists compatible with
    what Bitcoin Core actually sends, so the GUI layer never needs to know
    whether data is real or synthetic.
    """

    def __init__(self) -> None:
        self._url = (
            f"http://{config.BITCOIN_RPC_HOST}:{config.BITCOIN_RPC_PORT}/"
        )
        self._auth = HTTPBasicAuth(
            config.BITCOIN_RPC_USER, config.BITCOIN_RPC_PASSWORD
        )
        self._id = 0
        self._demo = config.DEMO_MODE
        self._connected = False
        self._demo_height = 840_000
        self._demo_mempool_size = 12_400
        self._demo_price = 68_400.0

    # ── connectivity ──────────────────────────────────────────────────────────

    def test_connection(self) -> bool:
        if self._demo:
            self._connected = True
            return True
        try:
            self._call("getblockchaininfo")
            self._connected = True
            return True
        except Exception as exc:
            log.warning("Bitcoin RPC unreachable — switching to demo: %s", exc)
            self._demo = True
            self._connected = True
            return False

    def is_connected(self) -> bool:
        return self._connected

    # ── raw RPC ───────────────────────────────────────────────────────────────

    def _call(self, method: str, params: list | None = None) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "1.0",
            "id": str(self._id),
            "method": method,
            "params": params or [],
        }
        resp = requests.post(
            self._url,
            json=payload,
            auth=self._auth,
            timeout=config.BITCOIN_RPC_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise BitcoinRPCError(data["error"])
        return data["result"]

    # ── public API ────────────────────────────────────────────────────────────

    def get_blockchain_info(self) -> dict:
        if not self._demo:
            return self._call("getblockchaininfo")
        h = self._demo_height
        return {
            "chain": "main",
            "blocks": h,
            "headers": h,
            "bestblockhash": f"0000000000000000000{'a'*45}"[:64],
            "difficulty": 86_408_066_388_378.1,
            "mediantime": int(time.time()) - 300,
            "verificationprogress": 0.9999998,
            "chainwork": "00000000000000000000000000000000000000005a97dd6fa4fe1e2f9d52d995",
            "size_on_disk": 627_000_000_000,
            "pruned": False,
        }

    def get_block_count(self) -> int:
        if not self._demo:
            return self._call("getblockcount")
        return self._demo_height

    def get_best_block_hash(self) -> str:
        if not self._demo:
            return self._call("getbestblockhash")
        return "0" * 12 + "a" * 52

    def get_block(self, block_hash: str, verbosity: int = 2) -> dict:
        if not self._demo:
            return self._call("getblock", [block_hash, verbosity])
        return self._synthetic_block(self._demo_height)

    def get_block_by_height(self, height: int) -> dict:
        if not self._demo:
            h = self._call("getblockhash", [height])
            return self._call("getblock", [h, 2])
        return self._synthetic_block(height)

    def get_mempool_info(self) -> dict:
        if not self._demo:
            return self._call("getmempoolinfo")
        size = self._demo_mempool_size + random.randint(-200, 200)
        self._demo_mempool_size = max(100, size)
        bytes_ = size * 500
        return {
            "loaded": True,
            "size": size,
            "bytes": bytes_,
            "usage": bytes_ * 2,
            "total_fee": round(size * 0.00002, 8),
            "maxmempool": 300_000_000,
            "mempoolminfee": 0.00001000,
            "minrelaytxfee": 0.00001000,
        }

    def get_raw_mempool(self, verbose: bool = True) -> dict | list:
        if not self._demo:
            return self._call("getrawmempool", [verbose])
        return self._synthetic_mempool(500 if verbose else 500)

    def get_network_info(self) -> dict:
        if not self._demo:
            return self._call("getnetworkinfo")
        return {
            "version": 250000,
            "subversion": "/Satoshi:25.0.0/",
            "protocolversion": 70016,
            "localservices": "0000000000000409",
            "localrelay": True,
            "timeoffset": 0,
            "networkactive": True,
            "connections": 125,
            "connections_in": 114,
            "connections_out": 11,
            "relayfee": 0.00001,
            "incrementalfee": 0.00001,
        }

    def get_mining_info(self) -> dict:
        if not self._demo:
            return self._call("getmininginfo")
        return {
            "blocks": self._demo_height,
            "currentblockweight": 3_993_456,
            "currentblocktx": 3124,
            "difficulty": 86_408_066_388_378.1,
            "networkhashps": 6.28e20,
            "pooledtx": self._demo_mempool_size,
            "chain": "main",
            "warnings": "",
        }

    def get_tx(self, txid: str) -> dict | None:
        if not self._demo:
            try:
                return self._call("getrawtransaction", [txid, True])
            except BitcoinRPCError:
                return None
        return self._synthetic_tx(txid)

    def estimate_fee(self, conf_target: int = 6) -> float:
        """Returns fee rate in BTC/kB."""
        if not self._demo:
            result = self._call("estimatesmartfee", [conf_target])
            return result.get("feerate", 0.0001)
        # sat/vB tiers shift with demo noise
        base = {1: 45, 3: 28, 6: 18, 12: 12, 144: 5}.get(conf_target, 18)
        return round(base * (1 + random.uniform(-0.15, 0.15)) * 1e-5, 8)

    # ── synthetic data generators ─────────────────────────────────────────────

    def _synthetic_block(self, height: int) -> dict:
        rng = _rng_seed(height)
        n_tx = rng.randint(1800, 4200)
        timestamp = int(time.time()) - rng.randint(0, 600)
        txids = [self._fake_txid(rng) for _ in range(min(n_tx, 50))]
        total_out = sum(rng.uniform(0.001, 50) for _ in range(n_tx))
        fees = rng.uniform(0.05, 1.2)
        return {
            "hash": f"0000000000000000{'b'*48}"[:64],
            "confirmations": self._demo_height - height + 1,
            "height": height,
            "version": 0x20000004,
            "time": timestamp,
            "mediantime": timestamp - 300,
            "nonce": rng.randint(0, 2**32),
            "bits": "17034219",
            "difficulty": 86_408_066_388_378.1,
            "chainwork": "0" * 64,
            "ntx": n_tx,
            "nTx": n_tx,
            "size": n_tx * rng.randint(300, 700),
            "strippedsize": n_tx * 220,
            "weight": n_tx * 900,
            "tx": txids,
            "_total_output_btc": round(total_out, 8),
            "_total_fees_btc": round(fees, 8),
        }

    def _synthetic_tx(self, txid: str | None = None) -> dict:
        rng = random.Random(txid)
        n_vin = rng.randint(1, 5)
        n_vout = rng.randint(1, 4)
        value = round(rng.uniform(0.0001, 500.0), 8)
        return {
            "txid": txid or self._fake_txid(rng),
            "hash": txid or self._fake_txid(rng),
            "version": 2,
            "size": rng.randint(200, 2000),
            "vsize": rng.randint(150, 800),
            "weight": rng.randint(600, 3200),
            "locktime": 0,
            "vin": [{"txid": self._fake_txid(rng), "vout": rng.randint(0, 3)}
                    for _ in range(n_vin)],
            "vout": [
                {
                    "value": round(value / n_vout, 8),
                    "n": i,
                    "scriptPubKey": {"address": self._fake_address(rng)},
                }
                for i in range(n_vout)
            ],
            "confirmations": rng.randint(0, 10),
            "blocktime": int(time.time()) - rng.randint(0, 3600),
        }

    def _synthetic_mempool(self, n: int) -> dict:
        rng = random.Random()
        result = {}
        for _ in range(n):
            txid = self._fake_txid(rng)
            size = rng.randint(141, 2000)
            fee = round(rng.uniform(0.000015, 0.002), 8)
            result[txid] = {
                "vsize": size,
                "weight": size * 4,
                "fee": fee,
                "modifiedfee": fee,
                "time": int(time.time()) - rng.randint(0, 7200),
                "height": self._demo_height,
                "descendantcount": rng.randint(1, 3),
                "descendantsize": size,
                "descendantfees": int(fee * 1e8),
                "ancestorcount": rng.randint(1, 2),
                "ancestorsize": size,
                "ancestorfees": int(fee * 1e8),
                "wtxid": self._fake_txid(rng),
                "fees": {"base": fee, "modified": fee, "ancestor": fee, "descendant": fee},
            }
        return result

    @staticmethod
    def _fake_txid(rng: random.Random) -> str:
        return "".join(rng.choice("0123456789abcdef") for _ in range(64))

    @staticmethod
    def _fake_address(rng: random.Random) -> str:
        prefixes = ["bc1q", "bc1p", "3", "1"]
        prefix = rng.choice(prefixes)
        suffix_len = 40 - len(prefix)
        chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return prefix + "".join(rng.choice(chars) for _ in range(suffix_len))

    # ── convenience aggregates ────────────────────────────────────────────────

    def get_fee_histogram(self) -> list[tuple[float, int]]:
        """Returns [(sat_per_vbyte, count), ...] for mempool visualisation."""
        if not self._demo:
            raw = self.get_raw_mempool(verbose=True)
            buckets: dict[int, int] = {}
            for info in raw.values():
                fee_rate = info["fees"]["modified"] / info["vsize"] * 1e8
                bucket = max(1, int(fee_rate))
                buckets[bucket] = buckets.get(bucket, 0) + 1
            return sorted(buckets.items())

        rng = random.Random()
        buckets = []
        for sat_vb in range(1, 120):
            if sat_vb < 5:
                count = rng.randint(50, 200)
            elif sat_vb < 15:
                count = rng.randint(200, 800)
            elif sat_vb < 40:
                count = rng.randint(100, 500)
            elif sat_vb < 80:
                count = rng.randint(10, 100)
            else:
                count = rng.randint(0, 20)
            if count:
                buckets.append((float(sat_vb), count))
        return buckets

    def get_recent_large_transactions(self, min_btc: float = 100.0,
                                      limit: int = 30) -> list[dict]:
        """Returns whale transactions from the last few blocks."""
        rng = random.Random(int(time.time() // 60))
        result = []
        for i in range(limit):
            btc = round(rng.uniform(min_btc, 5000.0), 4)
            result.append({
                "txid": self._fake_txid(rng),
                "btc": btc,
                "usd": round(btc * self._demo_price, 0),
                "from_address": self._fake_address(rng),
                "to_address": self._fake_address(rng),
                "confirmations": rng.randint(0, 6),
                "timestamp": int(time.time()) - rng.randint(0, 3600),
                "fee_sat_vb": round(rng.uniform(5, 60), 1),
            })
        result.sort(key=lambda x: x["btc"], reverse=True)
        return result
