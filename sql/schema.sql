-- Run once in the Neon SQL editor
CREATE TABLE IF NOT EXISTS submissions (
  id SERIAL PRIMARY KEY,
  telegram_username TEXT NOT NULL,
  method TEXT NOT NULL CHECK (method IN ('BTC', 'USDT_BSC', 'USDT_ARB')),
  tx_hash TEXT,
  screenshot BYTEA,
  screenshot_type TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS members (
  telegram_user_id BIGINT PRIMARY KEY,
  username TEXT,
  expires_at TIMESTAMPTZ NOT NULL
);
