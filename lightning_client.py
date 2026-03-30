"""
bitcoin_terminal/backend/lightning_client.py

LND gRPC client with full demo-mode fallback.

Real connection:  requires lnd running locally + grpcio + protobuf stubs.
Demo connection:  generates synthetic channel / payment / routing data.
"""

from __future__ import annotations

import random
import time
import logging
from typing import Any

import config

log = logging.getLogger(__name__)

# ── Optional gRPC imports ─────────────────────────────────────────────────────
try:
    import grpc                            # type: ignore
    import codecs, os
    _GRPC_AVAILABLE = True
except ImportError:
    _GRPC_AVAILABLE = False
    log.info("grpcio not installed — Lightning client will use demo mode")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_pubkey(rng: random.Random) -> str:
    return "0" + "".join(rng.choice("0123456789abcdef") for _ in range(65))


def _fake_chan_id(rng: random.Random) -> str:
    return str(rng.randint(600_000_000_000_000_000, 900_000_000_000_000_000))


def _fake_alias(rng: random.Random) -> str:
    names = [
        "ACINQ", "Bitfinex", "River Financial", "Voltage", "Boltz",
        "LNMarkets", "Amboss", "WoS", "Breez", "Phoenix", "Kraken",
        "OKX-LN", "Binance-LN", "Strike", "CashApp", "Fold",
        "Muun", "Electrum", "BlueWallet", "ZBD", "Coinos",
    ]
    return rng.choice(names) + f"-{rng.randint(1, 99):02d}"


# ── Lightning client ──────────────────────────────────────────────────────────

class LightningClient:
    """
    Wraps LND's gRPC API (Lightning, Router, Graph services).
    Transparently falls back to synthetic data in demo mode.
    """

    def __init__(self) -> None:
        self._demo = config.DEMO_MODE or not _GRPC_AVAILABLE
        self._stub = None
        self._router_stub = None
        self._connected = False
        self._rng = random.Random(42)

    def connect(self) -> bool:
        if self._demo:
            self._connected = True
            log.info("Lightning client: demo mode active")
            return True
        try:
            self._init_grpc()
            # test call
            self._stub.GetInfo(self._ln_req("GetInfoRequest"))
            self._connected = True
            log.info("Lightning client: connected to LND")
            return True
        except Exception as exc:
            log.warning("LND unreachable — falling back to demo: %s", exc)
            self._demo = True
            self._connected = True
            return False

    def _init_grpc(self) -> None:
        import grpc
        os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"
        cert = open(config.LND_TLS_CERT, "rb").read()
        creds = grpc.ssl_channel_credentials(cert)
        channel = grpc.secure_channel(
            f"{config.LND_HOST}:{config.LND_GRPC_PORT}", creds
        )
        # Dynamic import so the app doesn't crash if stubs aren't generated
        try:
            import rpc_pb2_grpc as lnrpc         # type: ignore
            self._stub = lnrpc.LightningStub(channel)
        except ImportError:
            raise RuntimeError("LND protobuf stubs not found. Run scripts/gen_proto.sh")

    def _ln_req(self, class_name: str, **kwargs):
        import rpc_pb2 as lnrpc           # type: ignore
        cls = getattr(lnrpc, class_name)
        return cls(**kwargs)

    # ── Public methods ────────────────────────────────────────────────────────

    def get_node_info(self) -> dict:
        if not self._demo:
            info = self._stub.GetInfo(self._ln_req("GetInfoRequest"))
            return {
                "alias": info.alias,
                "pubkey": info.identity_pubkey,
                "num_active_channels": info.num_active_channels,
                "num_inactive_channels": info.num_inactive_channels,
                "num_pending_channels": info.num_pending_channels,
                "num_peers": info.num_peers,
                "block_height": info.block_height,
                "synced_to_chain": info.synced_to_chain,
                "version": info.version,
            }
        rng = random.Random(1)
        return {
            "alias": "SATURN-NODE",
            "pubkey": _fake_pubkey(rng),
            "num_active_channels": rng.randint(28, 45),
            "num_inactive_channels": rng.randint(0, 3),
            "num_pending_channels": rng.randint(0, 2),
            "num_peers": rng.randint(20, 60),
            "block_height": 840_000,
            "synced_to_chain": True,
            "version": "0.17.4-beta",
        }

    def get_channels(self) -> list[dict]:
        if not self._demo:
            resp = self._stub.ListChannels(self._ln_req("ListChannelsRequest"))
            return [
                {
                    "chan_id": str(c.chan_id),
                    "active": c.active,
                    "remote_pubkey": c.remote_pubkey,
                    "capacity": c.capacity,
                    "local_balance": c.local_balance,
                    "remote_balance": c.remote_balance,
                    "total_satoshis_sent": c.total_satoshis_sent,
                    "total_satoshis_received": c.total_satoshis_received,
                    "alias": "",
                }
                for c in resp.channels
            ]
        rng = random.Random(int(time.time() // 30))
        channels = []
        for i in range(35):
            rng2 = random.Random(i * 7)
            cap = rng2.randint(500_000, 50_000_000)
            local = rng.randint(10_000, cap - 10_000)
            channels.append({
                "chan_id": _fake_chan_id(rng2),
                "active": rng.random() > 0.08,
                "remote_pubkey": _fake_pubkey(rng2),
                "alias": _fake_alias(rng2),
                "capacity": cap,
                "local_balance": local,
                "remote_balance": cap - local,
                "total_satoshis_sent": rng.randint(0, 5_000_000),
                "total_satoshis_received": rng.randint(0, 5_000_000),
                "commit_fee": rng.randint(100, 500),
            })
        return channels

    def get_payments(self, max_payments: int = 50) -> list[dict]:
        if not self._demo:
            resp = self._stub.ListPayments(
                self._ln_req("ListPaymentsRequest", max_payments=max_payments)
            )
            return [
                {
                    "payment_hash": p.payment_hash,
                    "value_sat": p.value_sat,
                    "fee_sat": p.fee_sat,
                    "status": str(p.status),
                    "creation_time": p.creation_time_ns // 1_000_000_000,
                }
                for p in resp.payments
            ]
        rng = random.Random(int(time.time() // 10))
        statuses = ["SUCCEEDED"] * 14 + ["FAILED"] * 2 + ["IN_FLIGHT"] * 1
        payments = []
        for i in range(max_payments):
            rng2 = random.Random(i + int(time.time() // 60))
            payments.append({
                "payment_hash": "".join(rng2.choice("0123456789abcdef") for _ in range(64)),
                "value_sat": rng.randint(1_000, 5_000_000),
                "fee_sat": rng.randint(0, 500),
                "status": rng.choice(statuses),
                "creation_time": int(time.time()) - rng.randint(0, 86400 * 7),
            })
        payments.sort(key=lambda x: x["creation_time"], reverse=True)
        return payments

    def get_forwarding_history(self, limit: int = 100) -> list[dict]:
        if not self._demo:
            resp = self._stub.ForwardingHistory(
                self._ln_req("ForwardingHistoryRequest",
                             num_max_events=limit)
            )
            return [
                {
                    "timestamp": e.timestamp,
                    "chan_id_in": str(e.chan_id_in),
                    "chan_id_out": str(e.chan_id_out),
                    "amt_in": e.amt_in,
                    "amt_out": e.amt_out,
                    "fee": e.fee,
                }
                for e in resp.forwarding_events
            ]
        rng = random.Random(int(time.time() // 60))
        events = []
        for _ in range(limit):
            amt = rng.randint(1000, 2_000_000)
            fee = max(1, int(amt * rng.uniform(0.0001, 0.001)))
            events.append({
                "timestamp": int(time.time()) - rng.randint(0, 86400 * 30),
                "chan_id_in": _fake_chan_id(rng),
                "chan_id_out": _fake_chan_id(rng),
                "amt_in": amt,
                "amt_out": amt - fee,
                "fee": fee,
            })
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        return events

    def get_network_graph_summary(self) -> dict:
        """Returns high-level graph statistics."""
        if not self._demo:
            resp = self._stub.DescribeGraph(
                self._ln_req("ChannelGraphRequest", include_unannounced=False)
            )
            return {
                "num_nodes": len(resp.nodes),
                "num_channels": len(resp.edges),
                "total_capacity_sat": sum(e.capacity for e in resp.edges),
            }
        rng = random.Random(1)
        return {
            "num_nodes": rng.randint(16_000, 17_000),
            "num_channels": rng.randint(60_000, 75_000),
            "total_capacity_sat": rng.randint(4_500, 5_200) * 100_000_000,
        }

    def get_liquidity_summary(self) -> dict:
        channels = self.get_channels()
        total_cap = sum(c["capacity"] for c in channels)
        total_local = sum(c["local_balance"] for c in channels)
        total_remote = sum(c["remote_balance"] for c in channels)
        active = sum(1 for c in channels if c["active"])
        return {
            "total_capacity_sat": total_cap,
            "local_balance_sat": total_local,
            "remote_balance_sat": total_remote,
            "active_channels": active,
            "inactive_channels": len(channels) - active,
            "balance_ratio": total_local / total_cap if total_cap else 0.5,
        }
