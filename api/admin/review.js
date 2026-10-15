const { neon } = require('@neondatabase/serverless');
const { requireAdmin } = require('../_auth');

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!requireAdmin(req, res)) return;

  const body = req.body || {};
  const idStr = String(body.id === undefined || body.id === null ? '' : body.id);
  const action = String(body.action || '');
  if (!/^\d{1,9}$/.test(idStr)) return res.status(400).json({ error: 'Invalid id' });
  if (action !== 'approve' && action !== 'reject') return res.status(400).json({ error: 'Invalid action' });
  const id = parseInt(idStr, 10);

  try {
    const sql = neon(process.env.DATABASE_URL);
    const rows = action === 'approve'
      ? await sql`
          UPDATE submissions
          SET status = 'approved', approved_at = now(), expires_at = now() + interval '30 days'
          WHERE id = ${id} AND status = 'pending'
          RETURNING id, telegram_username, method, tx_hash, status, created_at, approved_at, expires_at
        `
      : await sql`
          UPDATE submissions SET status = 'rejected'
          WHERE id = ${id} AND status = 'pending'
          RETURNING id, telegram_username, method, tx_hash, status, created_at, approved_at, expires_at
        `;
    if (rows.length) return res.status(200).json({ ok: true, submission: { ...rows[0], reference: `CE-${rows[0].id}` } });

    const exists = await sql`SELECT 1 FROM submissions WHERE id = ${id}`;
    if (!exists.length) return res.status(404).json({ error: 'Submission not found' });
    return res.status(409).json({ error: 'Submission already reviewed' });
  } catch (err) {
    console.error('admin review error', err);
    return res.status(500).json({ error: 'Could not update submission.' });
  }
};
