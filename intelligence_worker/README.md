# CryptoEdge Intelligence — Telegram first

This folder belongs to the website repository, `hazakzy/cryptoedge-premium`. Deploy it as a separate Railway service. Keep Vercel serving the existing website from the repository root.

The public offer is free daily Intelligence plus free BTC signals in `@cryptoedgelab`. Premium adds supported altcoin trade coverage. This worker publishes research only. The existing Auto trading bot remains responsible for actual BTC entry, stop, target and position updates; this worker neither polls private positions nor places orders. The brief ends with **TOP GAINERS & LOSERS — 24H**, replacing the earlier CryptoEdge Status section.

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
- Automatic selected US economic-release times from the official BLS and BEA iCalendar subscriptions, converted into UK local time. This covers selected inflation, employment, GDP, PCE and trade releases, not a global economic calendar or the full Fed/BoE/ECB schedule.
- Top three positive and top three negative rolling-24h changes among the covered venue's USDT spot pairs with at least 10m USDT in 24h turnover. Stablecoin identifiers and 2L/2S/3L/3S/5L/5S suffixes are filtered. This is not an all-exchange or market-cap ranking; filters are finite, not a guarantee every synthetic or stable asset is excluded.
- Public copy excludes raw positioning, research provider names, credentials and strategy parameters.

The outlook is an initial price-structure baseline. Order flow is optional and off by default because it does not yet change that baseline. There is no smart-wallet tracking, exchange-netflow analysis, verified autonomous news interpretation, or performance claim. Do not advertise these as completed features.

## Calendar, catalysts and daily movers update

Merge and redeploy the existing Intelligence service; no new environment variables, API key, dependency, volume, database or separate service are needed for these three sections. Normal hosting charges still apply. This update is independent of the optional Buffer/X pull request and can be merged before or after it.

**Economic calendar:** fetch [BLS](https://www.bls.gov/help/hlpiCAL.htm) and [BEA](https://www.bea.gov/news/schedule/icalendar) subscriptions once per collection. Read explicit timed events, handle New York and UK daylight-saving transitions, unfold calendar lines, ignore cancelled/latest-revision and unsupported recurring events, and reject date-only/floating events rather than guessing a time. Include selected releases today or in the next 24 hours. A past scheduled time is labelled “result unverified”; it does not prove that a delayed release occurred. Stale, unavailable and partial calendar coverage are disclosed. Consensus and actual figures are not included in these public schedules. Reviewed editorial events can supply them.

**Top catalysts:** up to three fresh, reviewed original news summaries under `TOP CATALYSTS — VERIFIED`. Each record accepts `subscriber_copy` (maximum 220 characters), optional `impact_copy` (maximum 120) explaining why it matters, and optional `affected_assets` (up to five uppercase tickers). Provide both of the optional fields when relevant. Discovery-feed headlines remain unverified candidates and are not automatically republished. Without reviewed input, the brief explicitly says no verified material catalyst is included. This update does not create autonomous factual verification or an AI subscription.

**Reviewed calendar details:** existing `events` records accept optional strings `previous`, `forecast` and `actual` (maximum 30 characters each, with units). Event `subscriber_copy` is capped at 140 characters. Use offset-aware `event_at`, current verification and validity windows as before. Events may be from earlier today in UK time or in the next 24 hours. An `actual` is accepted only after the scheduled time and with a review timestamp at or after that time. Results and forecasts still require actual editorial verification; validation checks shape and freshness, not factual truth. Reviewed calendar entries are prioritised over automatic schedule entries, with at most three displayed. Extra items can be omitted whole to fit Telegram length limits.

**Movers:** one public spot-ticker request; reject responses older than five minutes, duplicate symbols and invalid numbers. Show only genuine positive/negative performers; if fewer than three qualify on a side, disclose that rather than filling it with the opposite sign. If ranking data is missing, stale or invalid, publish an unavailable notice. Calendar/mover failures are supplementary and do not suppress an otherwise complete market brief. No raw research provider names are added to subscriber copy. The [ticker schema](https://bybit-exchange.github.io/docs/v5/market/tickers) defines percentage change as a ratio; convert it to percent once.

Preview the fictional example from `intelligence_worker/`:

```text
python -B -m intelligence.runner --fixture examples/demo-snapshot.json --at 2026-11-01T08:00:00Z
```

To include the fictional catalyst and editorial event too, set `INTELLIGENCE_EDITORIAL_JSON` to the contents of `examples/demo-editorial.json` only in your local preview environment. Never deploy the fictional records as live news. The fixture visibly labels the whole edition fictional and cannot send. Official endpoint availability still needs checking in the deployed region; offline tests do not establish live availability.

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

## Optional automatic X posting — Buffer Free

X automation is **off by default**. No new subscription, AI service, direct X developer credits, database, volume or separate worker is required. It runs inside the existing Railway process, whose normal hosting charges still apply. As checked on 3 November 2026, [Buffer Free](https://buffer.com/pricing) includes X publishing, up to three channels, ten queued posts per channel at once, and API access. Our one-summary-per-day integration uses at most two Buffer requests per edition (destination check and submission). Buffer retains its own post records; Telegram remains the full Intelligence archive. No local archive is added. If Free access or limits change, leave this feature disabled rather than upgrading automatically.

The scheduled worker submits one short X post **only after Telegram confirms delivery** of a complete brief. It includes the edition's UK timestamp, BTC outlook implication, a research-only label and a direct link to that Telegram message. It does not invent news, price levels or trade results. The full news, DeFi watch and watchlist remain in Telegram. It uses fixed templates, so there is no language-model API bill. Independent news commentary and weekly reviews still need editorial work; they are not automated here.

Setup after merging this update:

1. Create an account at [Buffer](https://buffer.com) and use its **Free** plan. Do not purchase a subscription or X developer credits for this integration.
2. In Buffer, add a channel, select **X / Twitter**, and personally sign in and authorize the CryptoEdge account. Check that it is the correct public profile. Keep the channel connected, unlocked and unpaused.
3. Open **Buffer account settings → API**, then generate a personal API key. Keep it private. The account owner creates the key. [Authentication and setup](https://buffer.com/api).
4. In Buffer's [API Explorer](https://developers.buffer.com/reference.html), run the read-only queries below. First find your organization ID; then list its channels. Copy the `id` of the channel whose `service` is `twitter` and whose `name` matches your CryptoEdge handle. These queries do not publish anything.

```graphql
query {
  account { organizations { id name } }
}
```

```graphql
query {
  channels(input: { organizationId: "YOUR_ORGANIZATION_ID" }) {
    id name service
  }
}
```

5. In **Railway → robust-radiance → CryptoEdge Intelligence. → Variables**, add:

| Variable | Value |
| --- | --- |
| `INTELLIGENCE_X_ENABLED` | `false` while setting up |
| `INTELLIGENCE_X_HANDLE` | Your exact CryptoEdge X handle, with or without `@` |
| `BUFFER_API_KEY` | Your private Buffer personal API key |
| `BUFFER_X_CHANNEL_ID` | The verified Buffer channel ID from step 4 |

6. Preview locally from `intelligence_worker/` with `python -B -m intelligence.runner --x-draft`. This collects fresh data and prints the short copy without contacting Buffer or posting. An incomplete assessment is held. A fictional preview is available with `--x-draft --fixture examples/demo-snapshot.json --at 2026-11-01T08:00:00Z`; it is visibly labelled fictional.
7. Set `INTELLIGENCE_X_ENABLED=true` and deploy before the next 08:00 UK edition. Keep the existing start command **`python -m intelligence.runner --worker --deliver`** and one replica. Other Telegram flags and settings stay as already configured. This activates future scheduled X summaries; it does not backfill old editions. The one-off `--publish-now` command remains Telegram-only.
8. After an edition, `"x_delivery":"accepted"` means Buffer accepted the submission, **not** proof X published it. Check Buffer's Sent/Failed views and the actual X profile. An uncertain result is not retried automatically. To stop new X submissions, set `INTELLIGENCE_X_ENABLED=false` and redeploy. Already accepted posts must be managed in Buffer.

Telegram failures prevent X promotion of an unpublished edition. X failures do not resend or block Telegram. The same no-disk restart rule applies: starting at or after the daily time skips that day's scheduled edition. No durable exactly-once guarantee exists; check Buffer and X before any manual repost, and never run overlapping schedulers. This version has been tested offline with mocked Buffer responses; real account authorization and an actual post still need verification.

For the first 30 days, use the daily summary consistently, add three original news/DeFi observations a week when verified, and review the week's views including invalidations. Keep research separate from entry signals and disclose sponsored content. Use Buffer/X's existing statistics and Telegram invite links to assess useful engagement and joins without adding an analytics database.

API references: [first post and channel discovery](https://developers.buffer.com/guides/your-first-post.html), [current schema including shareNow](https://developers.buffer.com/reference.html), [Free queue limits](https://support.buffer.com/en-us/articles/how-many-posts-can-i-schedule-in-advance-Kmy2IEecqm).

## Optional data and editorial input

Coinalyze is not required for the default baseline. To enable optional private order-flow collection, add `COINALYZE_API_KEY`, set `INTELLIGENCE_ORDER_FLOW_ENABLED=true` and supply `INTELLIGENCE_MARKET_MAPPING` as a JSON object with verified `spot` and `futures` provider ID lists for each of BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT and HYPEUSDT. Never guess IDs. An enabled but incomplete optional collection holds publication. These observations exist only in memory and do not alter the initial price-based outlook.

For original, reviewed news and events, set `INTELLIGENCE_EDITORIAL_JSON` to an object with `news` and `events` arrays. Each news record needs `id`, `status:"verified"`, `reviewed_by`, HTTPS `source_url`, offset-aware `published_at`, `verified_at`, `valid_from`, `valid_until` and original `subscriber_copy`. Events also need `event_at` in the next 24 hours. Review must be within the previous 24 hours, and the validity window must include publication. Do not paste article bodies. The program validates record shape and freshness, not factual truth. Current sample editorial is empty, so the first preview explicitly discloses no verified catalyst or complete calendar.

## Website and retirement of the earlier draft

The homepage and `/intelligence.html` provide the introduction, clearly labeled sample and public-channel links. They do not fetch an Intelligence database or automatically display Telegram history. The old publisher endpoint rejects POST with 410; GET returns channel metadata only. No Telegram token is exposed in the browser. No Intelligence SQL migration is required. Existing payment and membership tables and endpoints remain unchanged.

An earlier worker remains in Auto's source history. Do not deploy both copies. This folder replaces its archive/volume/website-publisher design. Removing source files does not delete any table or data that was previously created; review any existing Intelligence-only records separately. Do not drop payment or membership tables.

Railway references: [isolated monorepo root directories](https://docs.railway.com/deployments/monorepo), [Dockerfile detection](https://docs.railway.com/builds/dockerfiles).
