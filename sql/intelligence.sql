-- Run explicitly in the existing Neon database, in staging first.
-- One public summary per day, at most 1,200 bytes of highlights. Publication removes
-- editions older than seven calendar days. No market dataset or new database.
BEGIN;
CREATE TABLE IF NOT EXISTS public_intelligence_briefs (
  edition_date DATE PRIMARY KEY,
  as_of TIMESTAMPTZ NOT NULL,
  title TEXT NOT NULL CHECK(octet_length(title) BETWEEN 1 AND 100),
  preview TEXT NOT NULL CHECK(octet_length(preview) BETWEEN 1 AND 240),
  highlights TEXT NOT NULL CHECK(octet_length(highlights) BETWEEN 1 AND 1200),
  content_hash TEXT NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$')
);
-- Upgrade an earlier draft safely: retain its short preview and remove full text.
ALTER TABLE public_intelligence_briefs ADD COLUMN IF NOT EXISTS highlights TEXT
  CHECK(octet_length(highlights) BETWEEN 1 AND 1200);
UPDATE public_intelligence_briefs SET highlights=preview WHERE highlights IS NULL;
ALTER TABLE public_intelligence_briefs ALTER COLUMN highlights SET NOT NULL;
ALTER TABLE public_intelligence_briefs DROP COLUMN IF EXISTS body;
COMMIT;
