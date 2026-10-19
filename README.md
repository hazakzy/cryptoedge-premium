# cryptoedge-premium
CRYPTOEDGE premium landing page and crypto payment submission form (Vercel + Neon)

## Admin review
Review payment submissions (including screenshots) at `/admin.html`.

- Required env var: `ADMIN_TOKEN` (plus `DATABASE_URL`). Enter the token on the page; it is kept in `sessionStorage` and sent as `Authorization: Bearer <token>` header (never in the URL).
- `GET /api/admin/submissions?status=pending|approved|rejected|all` – list (no screenshot bytes)
- `GET /api/admin/screenshot?id=<id>` – stream the stored screenshot
- `POST /api/admin/review` with `{ "id": 1, "action": "approve" | "reject" }` – include `verified: true` and a manually verified `tx_hash` for approval; grants/renews 30 days atomically and queues Telegram delivery


See [PHASE1.md](PHASE1.md) for the required migration, bot integration, tests and controlled rollout.
