# Integration: solana-pumpfun-bot into solana-pumpfun-bot3

Destination repository: `DeeKalshiWay/solana-pumpfun-bot3`.
Source repository: `DeeKalshiWay/solana-pumpfun-bot` (left in place; not deleted or archived).

This pull request is a reviewable merge. It does not merge into the default branch by itself, and it does not start the bot, submit transactions, connect a wallet, or deploy.

## Relationship

Both repositories share the same initial commit `75f7cdb` (2026-05-05, "Initial commit: Solana pump.fun trading bot") and **198 identical commits** through:

`fb16c29` — 2026-05-10 — `fix(lint): clear all ruff errors`

After that tip they diverged:

| Repo | Unique history after `fb16c29` |
| --- | --- |
| `solana-pumpfun-bot3` (destination) | 1 commit: `326db33` — disclaimer line in `README.md`, and deletion of the unrelated `job_search/` folder |
| `solana-pumpfun-bot` (source) | 46 commits, `99b6da2` through `9290bc9` (2026-05-10 to 2026-07-24, plus a 2026-11-04 disclaimer) |

File comparison matches that history. After the fork, `bot3` did not edit any Python module. The source repo is the functional continuation. That conclusion comes from the shared commit graph and the diff, not from which repository looks newer.

## Retained from solana-pumpfun-bot3

- This repository as the destination, including the pre-fork bot: orchestrator, paper wallet, risk engine, detectors, dashboard, CI, Docker, and deploy scripts.
- Educational disclaimer in `README.md` (the source added the same sentence; one copy is kept).
- Deletion of `job_search/` (personal job-search scripts, unrelated to the bot). The source deleted the same folder in `99b6da2`.
- Secret hygiene already on this branch: `.env` and `*.session` stay gitignored. `.env.example` uses placeholders only (`YOUR_HELIUS_KEY_HERE`, empty optional keys). No `.env`, session file, or private key was copied from either checkout.

## Retained from solana-pumpfun-bot

Wired into `main.py` / `SignalScorer` (still paper by default):

- `analyzer/signal_fusion.py` — per-pattern score bonus and penalty (`FUSION_ENABLED` defaults true).
- `analyzer/regime_filter.py` — new-mint rate window on the shared WebSocket.
- `detector/whale_tracker.py` — per-wallet SOL volume on that same socket.
- `detector/x_feed.py` — reads a local JSONL file produced by the optional `x-monitor/` sidecar. The sidecar is not started by `main.py` and still expects `X_BEARER_TOKEN` from the environment.
- Rug-memory hard reject, metadata-less symbol reject, and `AUTO_TUNE_ENABLED` so the score threshold can be frozen.
- Risk additions: single-tick price sanity, momentum-stall only after take-profit 1, partial closes, state recovery.
- Execution additions, all opt-in or paper-safe:
  - `USE_LOCAL_TX_BUILD` defaults **false** (`trader/local_tx_builder.py`).
  - `JITO_REGION` is empty unless set; it only prepends a regional URL.
  - Asymmetric buy/sell slippage settings.
  - CreateIdempotent ATA prepend on the local-tx path.
  - Last-known wallet balance returned when an RPC read fails.
  - `TradeExecutor.sell` forwards `price_history`.
- Paper simulation: realistic friction, percent-string sells resolved against tracked holdings, and `SYNTHETIC_INJECT` refused unless `PAPER_TRADING` is true.

Separate research entrypoints, not launched by `main.py`:

- `tools/graduation_sniper.py`, `tools/edge_brain.py`, graduation reports/alerts, dashboard autostart scripts.
- `analytics/go_live_gate.py` — offline reader of local logs. Exit 0 only when its criteria pass. This PR does not run it against live capital.
- `tools/flip_to_paper.sh`, `tools/paper_smoke.py`, `tools/synthetic_injector.py`, `tools/synthetic_price_mover.py`.
- `web/dashboard.html` and optional `DASHBOARD_AUTH_USER` / `DASHBOARD_AUTH_PASS` placeholders.
- Offline tests that arrived with those modules.

## How overlaps were resolved

`git merge` of source `main` (`9290bc9`) into this branch was clean. There were no conflict markers.

| Overlap | Resolution |
| --- | --- |
| `README.md` disclaimer | Both sides inserted the same sentence onto an otherwise unchanged README. One copy kept. CI badge now points at `solana-pumpfun-bot3`. |
| `job_search/` | Deleted on both sides. `pyproject.toml` exclude entries for that folder were dropped with it. |
| Root `pumpfun_monitor.py` and `signal_scorer.py` | Deleted. They were stale pre-consolidation copies. The live modules are `detector/pumpfun_monitor.py` and `analyzer/signal_scorer.py`. Destination had not edited the root copies after the fork. |
| `config.py`, `risk/manager.py`, executors, `wallet.py`, `signal_scorer.py`, `wallet_intel.py`, dashboard, `web_server.py`, `main.py`, `.env.example` | Destination had no post-fork edits, so the source versions were taken whole. Paper default stays `_env_bool("PAPER_TRADING", True)`. Local transaction building stays off. Synthetic injection still refuses live mode. |
| `.gitignore` | Removed the blanket `dashboard.html` rule so `web/dashboard.html` can be tracked. `.env`, session files, and `logs/` remain ignored. |

`tests/test_config_imports.py::test_committed_safe_defaults` locks the paper-mode default, the local-tx default, and the live-mode synthetic refusal.

## Validation

- Both remotes were readable. Source was cloned and its full history fetched.
- No bot process, RPC session, wallet, or transaction was started.
- Tests are the repo's pytest suite. They use temp files and mocks. They do not place trades.
- `tests/test_paper_executor.py` called `asyncio.get_event_loop()`, which raises on Python 3.12 (the version in `pyproject.toml` and CI). The helper now uses `asyncio.run`. The paper-sell assertions are unchanged.

## Review fixes on this branch

A follow-up pass changed behavior the clean merge had imported as-is:

- A paper sell of zero tokens fails. It no longer closes the position for 0 SOL.
- Restart reloads token inventory and the last mark into the paper executor.
- Paper `sol_spent` includes the buy fee and `sol_received` is net of the sell fee, so the trade record matches the wallet.
- `REALISTIC_PAPER_SIM=0` also disables the stampede multiplier.
- An unconfirmed live buy is watched and adopted if the signature later confirms.
- Startup reconciliation reloads the paper book and, on a live wallet, updates token counts only from a successful balance read.
- Holder concentration and freeze authority fail closed when the read is missing.
- The dashboard binds to `127.0.0.1` unless auth is configured. An open bind without auth does not start.
- Giving up on a force-sell writes an `abandoned_unsold` row marked unreconciled, and does not train rug memory from it.
- Take-profit clears the prebuilt sell. Lifetime symbol caps are per creator plus ticker.
- The local transaction builder also requires `LOCAL_TX_LAYOUT_VERIFIED` (default false).
- A stale price no longer counts deployed capital as a realized loss in the emergency-stop drawdown.
- The go-live gate's pass line says it is not authorization to use funds.

## Unresolved

- No content conflict left open.
- Graduation research code is integrated as separate tools. It is not folded into the `main.py` task graph, which matches how the source repo ran it.
- Live profitability is not claimed. `BLOG_NO_REAL_EDGE.md` and `PRE_LIVE_400_PLAYBOOK.md` still describe the pre-fork strategy limits. Historical links in those notes still point at commits on `solana-pumpfun-bot`.
