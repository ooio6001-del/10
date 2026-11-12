# SOLSTRATS MILLION

A standalone, **paper-only** Solana meme-coin watcher and reproducible strategy laboratory. It does not require wallet credentials or execute transactions.

## Run on Windows

1. Install Python 3.10+.
2. Download this repository as ZIP and extract it.
3. Double-click `start-bot.bat` (or run `py -3 app.py`).
4. Open http://127.0.0.1:8792 .

The watcher uses the public DEX Screener API, with API rate limiting and graceful handling of outages. No API key is necessary. Optional Helius configuration may be added later; do not commit keys to GitHub.

## What is real, and what is not

- Live prices/pools come from DEX Screener when available, and are timestamped and labeled.
- The engine defines **1,000,000 distinct deterministic parameter combinations**. This is a configuration search space, *not* a claim that all combinations have been backtested.
- In live-forward mode only a bounded subset is evaluated each tick. Actual counts are displayed.
- Paper results are estimates; they are *not* executable quotes, and spreads, gas, slippage and changing liquidity may materially worsen results.
- Paper balance grid: $5, $10, $15 … $10,000 (2,000 levels). Stake size grid: $0.01–$5.00 (500 levels). The engine currently samples 100 balance-and-stake scenarios; it does not evaluate all 1,000,000 combinations. All trades are simulated; no transaction signing or broadcasting exists.
- This is a new bot; the old SOLSTRATS trading strategies were not available in the public dashboard repository, so none are claimed as imported.

## Testing

Run `py -3 -m unittest discover -s tests -v`.

## Security

The server binds to localhost. No API keys, seed phrases, private keys, or production wallet files are required. The repository is public: never commit credentials.

## Data limitations

Public DEX Screener token profiles and pair data are snapshots, not a full tick-level historical archive. Live-forward observations accumulate only while the app runs. The bot does not manufacture backtests or claim that incomplete observations are a reliable execution simulation. Free API endpoints can be rate limited. The live watcher is started automatically when launching the server.

## Live data and stake-testing limitations

The live watcher queries DEX Screener for indexed Solana pool prices, liquidity, market cap, and 5-minute transaction counts, with optional GeckoTerminal new-pool discovery. These are third-party snapshots, not independently verified chain transaction receipts. A paper account uses its own initial balance and stake size. The fixed $0.01 per-side modeled cost and 1% variable cost are illustrative, not an executable quote. Tiny stakes can be uneconomic or below real DEX minimums. Historical records from v1 are stored separately in state/session.json and are not automatically migrated into the new balance grid. Rankings should compare percentage returns and drawdowns, not raw dollar equity.
