# Free public Intelligence

Intelligence is free for now, on `/intelligence.html` and the public Telegram channel. The homepage shows the newest short preview. The dedicated route shows highlights; Telegram carries the full brief and follow-up research updates. Premium signals, existing prices, mentorship and payment approval remain separate.

No member login or paywall was added. The public API returns only compact highlights, never the full Telegram edition, never the research snapshot or provider credentials. Browser rendering uses text nodes rather than HTML from the feed.

## Small storage footprint

Apply `sql/intelligence.sql` explicitly to the existing Neon database, in staging first. It creates one small table, not a new database. The publisher accepts one edition per day with at most 1,200 bytes of highlights, and removes editions outside the current seven-day window on each publication. That is at most 8.4KB of highlights in steady daily operation, plus metadata, indexes and database overhead. No market history, screenshots or article bodies are copied to this table.

Reads also filter out expired editions even if the worker has stopped. Old rows are removed on the next successful publication. The API is cached for five minutes at the hosting edge to reduce repeated database reads; a new edition may therefore take up to five minutes to appear normally, and stale caching can last longer during an origin failure.

## Connect the worker

Website environment:

- Existing `DATABASE_URL`.
- New `INTELLIGENCE_PUBLISH_TOKEN`, a high-entropy secret at least 32 characters long.

Configure the same publisher secret on the separate Auto Intelligence worker, plus:

- `INTELLIGENCE_WEBSITE_URL=https://cryptoedgelab.xyz/api/intelligence`.
- `website_publication_enabled: true` in its private configuration.
- `telegram_channel: "@cryptoedgelab"` or an explicit `INTELLIGENCE_CHANNEL_ID` override.

The worker keeps publication disabled until its source access and required data are verified. Telegram receives the full finished message. The website receives only the outlook and one selected FA/news and DeFi takeaway. Full watchlists, event detail and invalidation context remain in Telegram. The API rejects a full-body field; no full edition is sent to, stored on or returned by the website. API retries are idempotent for identical editions; changed content receives a conflict instead of silently overwriting a published brief.

Do not put the publisher token in frontend code or URLs. Authentication is required only to publish; reading is public. There is no new account/session database.

## Rollout

1. Review the website and Auto worker changes.
2. Test the small migration and publisher against a staging database and URL.
3. Configure the secret using hosting settings; do not commit it.
4. Deploy the website normally through its existing Vercel project.
5. Enable the separately configured worker only after a fresh complete preview is verified.

Without configuration or a published edition, visitors see a truthful waiting message and a public Telegram link. The page never substitutes the illustrative format example for live analysis.

## Checks

`npm test` runs the existing payment checks and the public Intelligence API/database checks. The new cases cover public access, publisher authorization, retry idempotency, conflict handling, payload limits, private-detail exclusion, expiry/pruning and empty states. Desktop/mobile, theme, navigation, FAQ and published-text rendering also need browser QA.
