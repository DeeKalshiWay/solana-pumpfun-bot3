"""Free latency-path pins. No network, no wallet, no send."""
import asyncio
import time

import pytest


def test_bonding_curve_skips_jupiter_quote():
    from trader.executor import on_bonding_curve
    assert on_bonding_curve({"pool": "pump", "bonding_curve_pct": 12}) is True
    assert on_bonding_curve({"bonding_curve_pct": 40}) is True
    assert on_bonding_curve({"bonding_curve_pct": 100}) is False
    assert on_bonding_curve({"pool": "raydium"}) is False
    assert on_bonding_curve(None) is False


@pytest.mark.asyncio
async def test_buy_on_curve_does_not_call_jupiter():
    from solders.keypair import Keypair

    from trader.executor import TradeExecutor

    ex = TradeExecutor(Keypair())
    called = {"quote": 0, "pp": 0}

    async def quote(*_a, **_k):
        called["quote"] += 1
        return {"outAmount": "1", "priceImpactPct": "0"}

    class _PP:
        async def buy(self, mint, sol):
            called["pp"] += 1
            return {"success": True, "venue": "pumpportal", "mint": mint}

    ex.get_quote = quote
    ex.pumpportal = _PP()
    result = await ex.buy("MintCurve", 0.05, {"pool": "pump", "bonding_curve_pct": 8})
    assert result["success"] is True
    assert called["quote"] == 0
    assert called["pp"] == 1


@pytest.mark.asyncio
async def test_graduated_buy_still_asks_jupiter():
    from solders.keypair import Keypair

    from trader.executor import TradeExecutor

    ex = TradeExecutor(Keypair())
    called = {"quote": 0}

    async def quote(*_a, **_k):
        called["quote"] += 1
        return None

    class _PP:
        async def buy(self, mint, sol):
            return {"success": True, "venue": "pumpportal"}

    ex.get_quote = quote
    ex.pumpportal = _PP()
    await ex.buy("MintGrad", 0.05, {"pool": "raydium", "bonding_curve_pct": 100})
    assert called["quote"] == 1


@pytest.mark.asyncio
async def test_confirm_waits_for_the_slow_positive_status():
    from trader.pumpportal_executor import first_positive

    async def empty():
        return None

    async def slow():
        await asyncio.sleep(0.05)
        return {"confirmationStatus": "confirmed", "err": None}

    found = await first_positive([empty(), slow()], timeout=1.0)
    assert found["confirmationStatus"] == "confirmed"


def test_stale_prebuild_is_refreshed_and_fresh_is_kept():
    from main import prebuild_needs_refresh

    class _Pos:
        def __init__(self, blob, ts):
            self.prebuilt_sell_tx = blob
            self.prebuilt_sell_ts = ts

    now = time.time()
    assert prebuild_needs_refresh(_Pos(None, 0), now) is True
    assert prebuild_needs_refresh(_Pos(b"tx", now - 40), now) is True
    assert prebuild_needs_refresh(_Pos(b"tx", now - 5), now) is False


@pytest.mark.asyncio
async def test_refresh_once_only_rebuilds_stale(isolated_paths):
    from main import refresh_prebuilt_sells_once

    class _Pos:
        def __init__(self, blob, ts):
            self.prebuilt_sell_tx = blob
            self.prebuilt_sell_ts = ts

    now = time.time()
    positions = {
        "stale": _Pos(b"old", now - 40),
        "fresh": _Pos(b"new", now - 5),
        "missing": _Pos(None, 0),
    }

    class _RM:
        def __init__(self):
            self.positions = positions

    class _EX:
        def __init__(self):
            self.mints = []

        async def prebuild_sell_tx(self, mint):
            self.mints.append(mint)
            return b"rebuilt"

    rm = _RM()
    ex = _EX()
    n = await refresh_prebuilt_sells_once(ex, rm, now=now)
    assert n == 2
    assert set(ex.mints) == {"stale", "missing"}
    assert positions["stale"].prebuilt_sell_tx == b"rebuilt"
    assert positions["fresh"].prebuilt_sell_tx == b"new"


@pytest.fixture
def isolated_paths():
    return None
