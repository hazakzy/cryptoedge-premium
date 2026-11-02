# CryptoEdge Intelligence — Telegram first

This folder belongs to the website repository, `hazakzy/cryptoedge-premium`. Deploy it as a separate Railway service. Keep Vercel serving the existing website from the repository root.

The public offer is free daily Intelligence plus free BTC signals in `@cryptoedgelab`. Premium adds supported altcoin trade coverage. This worker publishes research only. The existing Auto trading bot remains responsible for actual BTC entry, stop, target and position updates; this worker neither polls private positions nor places orders. Its message section is **CRYPTOEDGE STATUS**.

## Storage and costs

No Neon, SQLite, volume, disk archive, delivery receipt file, article archive or website publisher. Market responses and delivery state exist only in process memory. Telegram keeps successfully published messages in the channel. The image disables Python bytecode writes, and runtime code does not write application data. Hosting logs are separate; keep their retention short. Hosting, network and optional data API charges are not eliminated by removing storage.

Use one replica, one region and one Intelligence scheduler. Stop any earlier Intelligence service from the Auto repository before enabling this one. The Auto trading service itself continues running.

Without durable receipts, the worker cannot guarantee exactly-once delivery across restarts or overlapping deployments. It deliberately skips the current day's scheduled publication when it starts at or after the scheduled time. A restart before the next day's schedule resumes normally. Network timeouts, server errors and interrupted sends are not retried automatically. An explicit Telegram rate-limit rejection may retry while the brief is fresh. A send must occur within 20 minutes of collection. A one-off manual send requires checking the channel first.

## What the first version provides

- Completed hourly and four-hour price structure for BTC, ETH, SOL, XRP and HYPE. Missing, stale or gapped candles are rejected.
- Scoped DeFi locked-value observations for Aave V3, Uniswap V3 and Hyperliquid Bridge. TVL changes are not net inflows, revenue or token upside.
- Official Federal Reserve monetary-policy and Ethereum feed discovery. Candidates are not automatically verified news or automatically republished.
- Original news/event summaries supplied through `INTELLIGENCE_EDITORIAL_JSON`, with source URLs, review times and validity windows. Empty or expired coverage is disclosed honestly in the published brief. Feed discovery is limited; this is not a complete crypto or macro news service.
- UK local scheduling and message timestamps without a timezone suffix.
- Public copy excludes raw positioning, research provider names, credentials and strategy parameters.

The outlook is an initial price-structure baseline. Order flow is optional and off by default because it does not yet change that baseline. There is no smart-wallet tracking, exchange-netflow analysis, verified autonomous news interpretation, or performance claim. Do not advertise these as completed features.

## Railway — exact setup

1. In the existing Railway project, add a separate service connected to **hazakzy/cryptoedge-premium**, branch **main** after this change is merged.
2. In that service's Settings, set **Root Directory** to `/intelligence_worker`. Railway should detect the Dockerfile in this folder. Keep one replica. No public domain, HTTP health-check path or persistent volume is needed.
3. Leave the custom build command empty: the Dockerfile installs this folder's requirements and copies only the worker code. Leave the start command empty for the first preview deployment: the Dockerfile runs `python -m intelligence.runner --worker`.
4. Add these service variables (not the Vercel project's variables):

| Variable | First deployment |
| --- | --- |
| `INTELLIGENCE_PUBLICATION_ENABLED` | `false` |
| `INTELLIGENCE_DATA_RIGHTS_CONFIRMED` | `false` until permitted publication/use is confirmed |
| `INTELLIGENCE_DAILY_TIME` | `08:00` |
| `INTELLIGENCE_CHANNEL_ID` | `@cryptoedgelab` |
| `TELEGRAM_BOT_TOKEN` | Enter the bot token privately in Railway |
| `INTELLIGENCE_ORDER_FLOW_ENABLED` | `false` |
| `INTELLIGENCE_EDITORIAL_JSON` | `{"news":[],"events":[]}` initially |

5. Add the bot as a channel administrator with permission to post. This worker uses `sendMessage` only, never Telegram polling, so it can use the existing authorized posting bot without starting a second approval bot.
6. Use a temporary start-command override of `python -m intelligence.runner --check` to collect fresh data once and inspect the result. It prints only coverage counts and the outlook; it sends nothing. This is a one-off diagnostic process that exits. Restore the normal worker command after checking. Use a local `python -m intelligence.runner` preview when you want to inspect the complete copy. A complete result does not mean autonomous news verification is implemented.
7. Once the complete current preview, channel and data permissions are verified, set the two enablement flags to `true` and set **Start Command** to:

```text
python -m intelligence.runner --worker --deliver
```

8. Deploy before the next 08:00 UK edition. Starting at or after 08:00 intentionally skips that day's scheduled send. Successful delivery logs contain `"delivery":"sent"`; also check the actual channel. A failed or uncertain delivery needs review. Logs never include the bot token or raw request exceptions.

To deliberately publish a fresh edition once outside the schedule, after checking Telegram for an existing edition, use `python -m intelligence.runner --publish-now --deliver` as a one-off command. It exits after one attempt; do not configure an automatic restart loop for this one-off command. No durable cross-process deduplication exists.

### Existing trading service: free BTC routing

The Auto bot already routes BTC to its free channel. In the **existing Auto trading service**, verify `TELEGRAM_FREE_CHANNEL_ID` points to the same public channel. Do not copy its trading credentials or trading start command into this Intelligence service. Premium routing stays with the Auto bot's existing `TELEGRAM_PREMIUM_CHANNEL_ID`. There is no additional BTC signal generator in this folder.

## Local verification and preview

From the website repository root:

```text
python -m pip install -r intelligence_worker/requirements.txt
python -B -m unittest discover -s intelligence_worker/tests -v
```

From `intelligence_worker/`:

```text
python -B -m intelligence.runner --check
python -B -m intelligence.runner
python -B -m intelligence.runner --fixture examples/demo-snapshot.json --at 2026-11-01T08:00:00Z
```

Environment variables are read directly; `.env.example` is documentation and is not loaded automatically. A fixture is visibly fictional and cannot deliver. Nothing in these commands enables sends unless both explicit environment flags and delivery flags are set.

## Optional data and editorial input

Coinalyze is not required for the default baseline. To enable optional private order-flow collection, add `COINALYZE_API_KEY`, set `INTELLIGENCE_ORDER_FLOW_ENABLED=true` and supply `INTELLIGENCE_MARKET_MAPPING` as a JSON object with verified `spot` and `futures` provider ID lists for each of BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT and HYPEUSDT. Never guess IDs. An enabled but incomplete optional collection holds publication. These observations exist only in memory and do not alter the initial price-based outlook.

For original, reviewed news and events, set `INTELLIGENCE_EDITORIAL_JSON` to an object with `news` and `events` arrays. Each news record needs `id`, `status:"verified"`, `reviewed_by`, HTTPS `source_url`, offset-aware `published_at`, `verified_at`, `valid_from`, `valid_until` and original `subscriber_copy`. Events also need `event_at` in the next 24 hours. Review must be within the previous 24 hours, and the validity window must include publication. Do not paste article bodies. The program validates record shape and freshness, not factual truth. Current sample editorial is empty, so the first preview explicitly discloses no verified catalyst or complete calendar.

## Website and retirement of the earlier draft

The homepage and `/intelligence.html` provide the introduction, clearly labeled sample and public-channel links. They do not fetch an Intelligence database or automatically display Telegram history. The old publisher endpoint rejects POST with 410; GET returns channel metadata only. No Telegram token is exposed in the browser. No Intelligence SQL migration is required. Existing payment and membership tables and endpoints remain unchanged.

An earlier worker remains in Auto's source history. Do not deploy both copies. This folder replaces its archive/volume/website-publisher design. Removing source files does not delete any table or data that was previously created; review any existing Intelligence-only records separately. Do not drop payment or membership tables.

Railway references: [isolated monorepo root directories](https://docs.railway.com/deployments/monorepo), [Dockerfile detection](https://docs.railway.com/builds/dockerfiles).
