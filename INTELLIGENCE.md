# Free Intelligence and BTC signals

The website introduces the free public Telegram offer: daily market Intelligence, original verified news where available, DeFi research and free BTC signals. Full published editions stay in `https://t.me/cryptoedgelab`. The website shows a clearly labeled format example and links to the channel. There is no automatic Intelligence feed or archive on the website.

The Python worker lives in this repository's `intelligence_worker/` folder and runs as a separate Railway service. The website remains on Vercel. Follow [the worker deployment guide](intelligence_worker/README.md). No separate repository, Neon database, SQLite queue, persistent volume or Intelligence migration is required.

The worker prepares research; the existing Auto trading bot continues to own BTC entry, stop, target and position alerts. Confirm its `TELEGRAM_FREE_CHANNEL_ID` uses the public channel. Premium adds supported altcoin trade coverage. The public brief uses **CRYPTOEDGE STATUS** and never invents a live trade status from market research.

Publication defaults off. Source access, a fresh complete preview, data permissions and the channel destination must be verified before enabling sends. News verification is still editorial and the initial directional assessment uses price structure. Missing verified news and incomplete event coverage are disclosed.

No raw research or provider details are stored on the website. `GET /api/intelligence` is a compatibility endpoint returning Telegram channel metadata without a database client. `POST` is retired with HTTP 410. The earlier database helper, SQL migration and browser feed script are removed. Do not run the old SQL migration or configure website publisher tokens. No production tables are dropped by this change. Payment and membership infrastructure is unchanged.

Run `npm test` for the website and existing payment checks, and `python -B -m unittest discover -s intelligence_worker/tests -v` for the worker. Browser QA should cover Home and Intelligence on desktop/mobile and both themes.
