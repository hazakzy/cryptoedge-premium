-- Apply after schema.sql, to a staging database first. Never run automatically.
BEGIN;
CREATE TABLE IF NOT EXISTS bot_users (
  telegram_user_id BIGINT PRIMARY KEY, username TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS telegram_user_id BIGINT;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS link_token TEXT UNIQUE;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS notified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE members ADD COLUMN IF NOT EXISTS removed_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS submissions_transaction_unique
ON submissions(method, lower(regexp_replace(trim(tx_hash), '^0[xX]', '')))
WHERE coalesce(trim(tx_hash), '') <> '';
-- Keep historical approvals untouched: reconciliation is a separate manual task.
CREATE TABLE IF NOT EXISTS payment_claims (
  method TEXT NOT NULL, tx_hash TEXT NOT NULL,
  submission_id INTEGER NOT NULL UNIQUE REFERENCES submissions(id),
  PRIMARY KEY(method, tx_hash)
);
-- Abort on historical duplicate approved payments; resolve before retrying migration.
INSERT INTO payment_claims(method, tx_hash, submission_id)
SELECT method, lower(regexp_replace(trim(tx_hash), '^0[xX]', '')), id
FROM submissions WHERE status = 'approved' AND coalesce(trim(tx_hash), '') <> ''
ON CONFLICT (submission_id) DO NOTHING;
CREATE TABLE IF NOT EXISTS membership_deliveries (
  submission_id INTEGER PRIMARY KEY REFERENCES submissions(id),
  telegram_user_id BIGINT NOT NULL REFERENCES members(telegram_user_id),
  state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','sent','expired')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_error TEXT, invite_link TEXT, invite_expires_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ
);

-- Both clients call this function. A committed approval always includes exactly
-- one grant and one durable delivery. Telegram requests never run here.
CREATE OR REPLACE FUNCTION review_payment(p_id INTEGER, p_action TEXT, p_verified BOOLEAN,
                                         p_hash TEXT DEFAULT NULL)
RETURNS submissions LANGUAGE plpgsql AS $$
DECLARE s submissions; expiry TIMESTAMPTZ; normalized TEXT;
BEGIN
  IF p_action IS NULL OR p_action NOT IN ('approve','reject') THEN RAISE EXCEPTION 'Invalid action'; END IF;
  SELECT * INTO s FROM submissions WHERE id = p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Submission not found'; END IF;
  IF s.status = (CASE WHEN p_action = 'approve' THEN 'approved' ELSE 'rejected' END) THEN
    IF s.status='approved' AND NOT EXISTS (
      SELECT 1 FROM membership_deliveries WHERE submission_id=s.id
    ) THEN RAISE EXCEPTION 'Legacy approval requires manual reconciliation'; END IF;
    RETURN s; -- retry of the same decision: no new grant
  END IF;
  IF s.status <> 'pending' THEN RAISE EXCEPTION 'Submission already reviewed'; END IF;
  IF p_action = 'reject' THEN
    UPDATE submissions SET status='rejected' WHERE id=p_id RETURNING * INTO s;
    RETURN s;
  END IF;
  IF p_verified IS DISTINCT FROM true THEN RAISE EXCEPTION 'Manual payment verification required'; END IF;
  IF s.telegram_user_id IS NULL THEN RAISE EXCEPTION 'Subscriber must open their private Start link first'; END IF;
  normalized := lower(regexp_replace(trim(coalesce(nullif(p_hash,''),s.tx_hash,'')), '^0[xX]', ''));
  IF normalized !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'A verified transaction hash is required'; END IF;
  INSERT INTO payment_claims VALUES(s.method, normalized, s.id);
  -- Serialize renewals from different submissions for the same subscriber.
  PERFORM pg_advisory_xact_lock(s.telegram_user_id);
  INSERT INTO members(telegram_user_id, username, expires_at, removed_at)
  VALUES(s.telegram_user_id, s.telegram_username, now()+interval '30 days', NULL)
  ON CONFLICT(telegram_user_id) DO UPDATE SET
    username=EXCLUDED.username,
    expires_at=greatest(members.expires_at,now())+interval '30 days', removed_at=NULL
  RETURNING expires_at INTO expiry;
  UPDATE submissions SET status='approved', tx_hash=normalized, verified_at=now(),
    approved_at=now(), expires_at=expiry WHERE id=p_id RETURNING * INTO s;
  INSERT INTO membership_deliveries(submission_id,telegram_user_id) VALUES(s.id,s.telegram_user_id);
  RETURN s;
END $$;
COMMIT;

