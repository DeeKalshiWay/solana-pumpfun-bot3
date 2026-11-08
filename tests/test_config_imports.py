"""Import smoke test. If config.py or any top-level module breaks
(syntax error, missing import, removed constant), CI catches it before
it ever hits the running bot."""
import importlib
from pathlib import Path


def test_config_imports():
    cfg = importlib.import_module("config")
    # A handful of constants the rest of the system relies on.
    for name in (
        "PAPER_TRADING",
        "MAX_SOL_PER_TRADE",
        "MAX_POSITION_PCT",
        "MAX_TOTAL_EXPOSURE_SOL",
        "MIN_BUY_SCORE",
        "STOP_LOSS_PCT",
        "TIME_EXIT_MINUTES",
        "LOSS_STREAK_LIMIT",
        "LOSS_STREAK_PAUSE_MIN",
        "TAKE_PROFIT_LEVELS",
    ):
        assert hasattr(cfg, name), f"config.{name} missing"


def test_risk_invariants():
    cfg = importlib.import_module("config")
    assert 0 < cfg.MAX_POSITION_PCT <= 1.0
    assert cfg.MAX_SOL_PER_TRADE > 0
    assert cfg.MAX_TOTAL_EXPOSURE_SOL >= cfg.MAX_SOL_PER_TRADE
    assert cfg.STOP_LOSS_PCT > 0
    assert cfg.LOSS_STREAK_LIMIT >= 1
    assert cfg.LOSS_STREAK_PAUSE_MIN >= 1
    # TP ladder must be monotonically increasing on gain_pct.
    gains = [lvl["gain_pct"] for lvl in cfg.TAKE_PROFIT_LEVELS]
    assert gains == sorted(gains), "TP ladder must be monotonic"
    # Sell percentages must sum to <100 — a fraction always rides.
    sells = sum(lvl["sell_pct"] for lvl in cfg.TAKE_PROFIT_LEVELS)
    assert sells < 100, "TP ladder sells everything; nothing rides for moonshot"


def test_risk_module_imports():
    importlib.import_module("risk.manager")


def test_committed_safe_defaults():
    """The integration must keep paper mode on and local tx building off
    unless an operator opts in. Assert the source defaults, not the
    process environment (load_dotenv can override the live values)."""
    src = (Path(__file__).resolve().parent.parent / "config.py").read_text(encoding="utf-8")
    assert '_env_bool("PAPER_TRADING", True)' in src
    assert '_env_bool("USE_LOCAL_TX_BUILD", False)' in src
    assert "Refusing to inject synthetic tokens in LIVE mode" in (
        Path(__file__).resolve().parent.parent / "main.py"
    ).read_text(encoding="utf-8")
