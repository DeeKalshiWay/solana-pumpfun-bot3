"""Offline pins for the post-review safety fixes.

No RPC, no wallet, no transaction submission.
"""
import asyncio
import time

import pytest

import risk.manager as rm_mod
from risk.manager import Position, RiskManager


class _Wallet:
    pubkey = "FakeWalletPubkey1111111111111111111111111111"

    def __init__(self, balance: float = 1.0):
        self.balance = balance

    async def get_sol_balance(self) -> float:
        return self.balance

    def deduct(self, amount: float):
        self.balance -= amount

    def credit(self, amount: float):
        self.balance += amount


class _Dash:
    def record_signal(self, token):
        self.last = token


def _pos(mint="MintA", **overrides) -> Position:
    base = dict(
        mint=mint, symbol="SYM", creator="creator",
        entry_price_sol=1e-8, entry_time=time.time(),
        sol_invested=0.05, tokens_held=1_000_000,
        current_price=1.6e-8, highest_price=1.6e-8, score=70,
    )
    base.update(overrides)
    return Position(**base)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(rm_mod, "RISK_STATE_FILE", str(tmp_path / "risk_state.json"))
    monkeypatch.setattr(rm_mod, "OPEN_POSITIONS_FILE", str(tmp_path / "open_positions.json"))
    monkeypatch.setattr(rm_mod, "CLOSED_TRADES_FILE", str(tmp_path / "closed_trades.jsonl"))
    monkeypatch.setattr(rm_mod, "SYMBOL_DEPLOYED_FILE", str(tmp_path / "symbol_deployed.json"))
    return tmp_path


class TestPaperAccounting:
    def test_zero_token_sell_fails_and_does_not_charge(self, tmp_path, monkeypatch):
        import trader.paper_executor as pe
        import trader.paper_wallet as pw
        monkeypatch.setattr(pw, "PAPER_STATE_FILE", str(tmp_path / "paper.json"))
        monkeypatch.setattr(pe, "REALISTIC_PAPER_SIM", False)
        wallet = pw.PaperWallet(1.0)
        ex = pe.PaperExecutor(wallet)
        before = asyncio.run(wallet.get_sol_balance())
        result = asyncio.run(ex.sell("NOBODY", "100%", reason="stop_loss"))
        after = asyncio.run(wallet.get_sol_balance())
        assert result["success"] is False
        assert result["error"] == "zero_amount"
        assert after == pytest.approx(before)

    def test_restore_inventory_sells_the_restored_tokens(self, tmp_path, monkeypatch):
        import trader.paper_executor as pe
        import trader.paper_wallet as pw
        monkeypatch.setattr(pw, "PAPER_STATE_FILE", str(tmp_path / "paper.json"))
        monkeypatch.setattr(pe, "REALISTIC_PAPER_SIM", False)
        wallet = pw.PaperWallet(1.0)
        first = pe.PaperExecutor(wallet)
        buy = asyncio.run(first.buy("MintR", 0.05, {
            "symbol": "R", "v_sol_in_bonding": 30.0, "v_tokens_in_bonding": 1_073_000_000.0,
        }))
        restarted = pe.PaperExecutor(wallet)
        assert restarted._tokens_held == {}
        pos = _pos(
            "MintR",
            tokens_held=buy["tokens_expected"],
            current_price=first._prices["MintR"],
            entry_price_sol=first._prices["MintR"],
        )
        assert restarted.restore_inventory({"MintR": pos}) == 1
        sold = asyncio.run(restarted.sell("MintR", "100%", reason="exit"))
        assert sold["success"] is True
        assert sold["sol_received"] > 0

    def test_recorded_round_trip_matches_wallet(self, tmp_path, monkeypatch):
        import trader.paper_executor as pe
        import trader.paper_wallet as pw
        monkeypatch.setattr(pw, "PAPER_STATE_FILE", str(tmp_path / "paper.json"))
        monkeypatch.setattr(pe, "REALISTIC_PAPER_SIM", False)
        monkeypatch.setattr(pe, "EXIT_LATENCY_ENABLED", True)
        wallet = pw.PaperWallet(1.0)
        ex = pe.PaperExecutor(wallet)
        start = asyncio.run(wallet.get_sol_balance())
        buy = asyncio.run(ex.buy("MintF", 0.05, {
            "symbol": "F", "v_sol_in_bonding": 30.0, "v_tokens_in_bonding": 1_073_000_000.0,
        }))
        sell = asyncio.run(ex.sell("MintF", "100%", reason="time_exit"))
        end = asyncio.run(wallet.get_sol_balance())
        recorded = sell["sol_received"] - buy["sol_spent"]
        assert recorded == pytest.approx(end - start)

    def test_legacy_mode_skips_stampede_multiplier(self, tmp_path, monkeypatch):
        import trader.paper_executor as pe
        import trader.paper_wallet as pw
        monkeypatch.setattr(pw, "PAPER_STATE_FILE", str(tmp_path / "paper.json"))
        monkeypatch.setattr(pe, "REALISTIC_PAPER_SIM", False)
        monkeypatch.setattr(pe, "EXIT_LATENCY_ENABLED", True)

        def _round(reason: str) -> float:
            wallet = pw.PaperWallet(1.0)
            ex = pe.PaperExecutor(wallet)
            asyncio.run(ex.buy("MintS", 0.05, {
                "symbol": "S", "v_sol_in_bonding": 30.0, "v_tokens_in_bonding": 1_073_000_000.0,
            }))
            sold = asyncio.run(ex.sell("MintS", "100%", reason=reason))
            return sold["sol_received"]

        assert _round("time_exit") == pytest.approx(_round("exit"))


class TestRiskBook:
    def test_second_open_does_not_replace(self, isolated):
        rm = RiskManager(_Wallet(), object())
        token = {"mint": "MintA", "symbol": "SYM", "creator": "creator", "score": 70}
        rm.open_position(token, {"tokens_expected": 100, "sol_spent": 0.05})
        rm.open_position(token, {"tokens_expected": 999, "sol_spent": 0.2})
        assert rm.positions["MintA"].tokens_held == 100
        assert rm.positions["MintA"].sol_invested == pytest.approx(0.05)

    def test_creator_symbol_caps_are_independent(self, isolated):
        rm = RiskManager(_Wallet(1.0), object())
        rm.starting_sol_balance = 1.0
        cap = rm._symbol_cap_sol()
        rm._symbol_deployed[rm._deploy_key("HOT", "alice")] = cap + 1.0
        blocked = asyncio.run(rm.calculate_position_size(80, symbol="HOT", creator="alice"))
        allowed = asyncio.run(rm.calculate_position_size(80, symbol="HOT", creator="bob"))
        assert blocked[1] == "symbol_cap"
        assert allowed[1] == ""
        assert allowed[0] > 0

    def test_stale_book_is_not_a_total_loss(self, isolated):
        from risk.manager import STALE_PRICE_SEC
        rm = RiskManager(_Wallet(), object())
        rm.starting_sol_balance = 1.0
        pos = _pos("MintStale", sol_invested=0.50, current_price=1e-8, tokens_held=1_000_000)
        pos.price_updated_at = time.time() - (STALE_PRICE_SEC + 5)
        rm.positions["MintStale"] = pos
        assert rm._equity_drawdown_pct(0.50) == pytest.approx(0.0, abs=1e-6)

    def test_fresh_loss_still_counts(self, isolated):
        rm = RiskManager(_Wallet(), object())
        rm.starting_sol_balance = 1.0
        assert rm._equity_drawdown_pct(0.70) == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_partial_clears_prebuilt_sell(self, isolated):
        class _Exec:
            async def sell(self, mint, amount, reason="exit", prebuilt_tx=None, price_history=None):
                return {"success": True, "sol_received": 0.02, "reason": reason, "venue": "paper"}

        rm = RiskManager(_Wallet(), _Exec())
        rm._append_closed_trade = lambda rec: None
        pos = _pos("MintTP", entry_price_sol=1.0, current_price=1.6, highest_price=1.6,
                   sol_invested=0.05, tokens_held=10_000_000)
        pos.prebuilt_sell_tx = b"stale"
        pos.prebuilt_sell_ts = time.time()
        rm.positions["MintTP"] = pos
        await rm._check_position("MintTP")
        assert rm.positions["MintTP"].prebuilt_sell_tx is None
        assert "tp_50" in rm.positions["MintTP"].tp_levels_hit


class TestFilters:
    @pytest.mark.asyncio
    async def test_holder_check_unknown_on_rpc_failure(self):
        from detector.holder_filter import get_top10_concentration

        class _Boom:
            def post(self, *args, **kwargs):
                raise TimeoutError("down")

        assert await get_top10_concentration(_Boom(), "Mint") is None

    @pytest.mark.asyncio
    async def test_holder_check_returns_a_real_percent(self):
        from detector.holder_filter import get_top10_concentration

        class _Resp:
            def __init__(self, body):
                self.body = body
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False
            async def json(self):
                return self.body

        bodies = [
            {"result": {"value": [{"amount": "40"}, {"amount": "10"}]}},
            {"result": {"value": {"amount": "100"}}},
        ]

        class _Sess:
            def post(self, *args, **kwargs):
                return _Resp(bodies.pop(0))

        assert await get_top10_concentration(_Sess(), "Mint") == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_freeze_authority_fails_closed(self):
        from analyzer.signal_scorer import SignalScorer

        scorer = SignalScorer(asyncio.Queue(), asyncio.Queue())

        class _Resp:
            def __init__(self, body):
                self.body = body
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False
            async def json(self):
                return self.body

        class _Sess:
            def __init__(self, body=None, explode=False):
                self.body = body
                self.explode = explode
            def post(self, *args, **kwargs):
                if self.explode:
                    raise RuntimeError("rpc")
                return _Resp(self.body)

        scorer._rpc_session = _Sess(explode=True)
        assert await scorer._freeze_authority_safe("Mint") is False
        scorer._rpc_session = _Sess({"result": {"value": None}})
        assert await scorer._freeze_authority_safe("Mint") is False
        scorer._rpc_session = _Sess({
            "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": None}}}}},
        })
        assert await scorer._freeze_authority_safe("Mint") is True
        scorer._rpc_session = _Sess({
            "result": {"value": {"data": {"parsed": {"info": {"freezeAuthority": "Attacker"}}}}},
        })
        assert await scorer._freeze_authority_safe("Mint") is False


class TestControls:
    def test_dashboard_refuses_open_bind_without_auth(self):
        from logger.web_server import dashboard_bind_allowed
        assert dashboard_bind_allowed("127.0.0.1", False) is True
        assert dashboard_bind_allowed("localhost", False) is True
        assert dashboard_bind_allowed("0.0.0.0", False) is False
        assert dashboard_bind_allowed("0.0.0.0", True) is True

    @pytest.mark.asyncio
    async def test_trade_loop_skips_mint_already_open(self, isolated):
        from main import trade_loop
        rm = RiskManager(_Wallet(), object())
        rm.positions["MintA"] = _pos("MintA")
        q = asyncio.Queue()
        token = {"mint": "MintA", "symbol": "SYM", "score": 90, "creator": "creator"}
        await q.put(token)

        class _Exec:
            def __init__(self):
                self.buys = 0
            async def buy(self, *a, **k):
                self.buys += 1
                return {"success": False}

        ex = _Exec()
        task = asyncio.create_task(trade_loop(q, ex, rm, _Dash(), _Wallet()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert ex.buys == 0
        assert token["reject_reason"] == "already_open"

    @pytest.mark.asyncio
    async def test_late_confirm_opens_the_position(self, isolated):
        from main import _adopt_landed_buy
        rm = RiskManager(_Wallet(), object())
        token = {"mint": "MintLate", "symbol": "LATE", "creator": "c", "score": 80}
        result = {
            "signature": "SIGLATE",
            "tokens_expected": 1234,
            "sol_spent": 0.05,
        }

        class _Exec:
            async def confirm_signature(self, signature, max_wait=45):
                return signature == "SIGLATE"

        await _adopt_landed_buy(_Exec(), rm, _Wallet(), token, result)
        assert "MintLate" in rm.positions
        assert rm.positions["MintLate"].tokens_held == 1234
