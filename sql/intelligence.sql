-- Run explicitly in the existing Neon database, in staging first.
-- One public edition per day, at most 16KB of brief text. Publication removes
-- editions older than seven calendar days. No market dataset or new database.
BEGIN;
CREATE TABLE IF NOT EXISTS public_intelligence_briefs (
  edition_date DATE PRIMARY KEY,
  as_of TIMESTAMPTZ NOT NULL,
  title TEXT NOT NULL CHECK(octet_length(title) BETWEEN 1 AND 100),
  preview TEXT NOT NULL CHECK(octet_length(preview) BETWEEN 1 AND 240),
  body TEXT NOT NULL CHECK(octet_length(body) BETWEEN 1 AND 16000),
  content_hash TEXT NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$')
);
COMMIT;
