const { neon } = require('@neondatabase/serverless');
const { requireAdmin } = require('../_auth');

const STATUSES = ['pending', 'approved', 'rejected', 'all'];

module.exports = async (req, res) => {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  if (!requireAdmin(req, res)) return;

  const status = String((req.query && req.query.status) || 'pending');
  if (!STATUSES.includes(status)) return res.status(400).json({ error: 'Invalid status' });

  try {
    const sql = neon(process.env.DATABASE_URL);
    const rows = await sql`
      SELECT s.id, telegram_username, s.telegram_user_id, method, tx_hash, status, created_at, approved_at, expires_at,
             (screenshot IS NOT NULL) AS has_screenshot, d.state AS delivery_state,
             d.attempts AS delivery_attempts, d.next_attempt_at, d.last_error
      FROM submissions s LEFT JOIN membership_deliveries d ON d.submission_id=s.id
      WHERE (${status} = 'all' OR status = ${status})
      ORDER BY created_at DESC, s.id DESC
      LIMIT 100
    `;
    res.setHeader('Cache-Control', 'private, no-store');
    return res.status(200).json({
      submissions: rows.map((r) => ({ ...r, reference: `CE-${r.id}`, has_screenshot: !!r.has_screenshot })),
    });
  } catch (err) {
    console.error('admin submissions error', err);
    return res.status(500).json({ error: 'Could not load submissions.' });
  }
};
