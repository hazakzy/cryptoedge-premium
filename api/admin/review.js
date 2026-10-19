const { neon } = require('@neondatabase/serverless');
const { requireAdmin } = require('../_auth');

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!requireAdmin(req, res)) return;
  const body = req.body || {};
  const id = String(body.id ?? '');
  const action = body.action;
  if (!/^\d{1,9}$/.test(id)) return res.status(400).json({ error: 'Invalid id' });
  if (!['approve', 'reject'].includes(action)) return res.status(400).json({ error: 'Invalid action' });
  if (action === 'approve' && body.verified !== true)
    return res.status(400).json({ error: 'Confirm you manually verified the payment on the correct network, recipient and amount.' });
  try {
    const sql = neon(process.env.DATABASE_URL);
    const rows = await sql`SELECT * FROM review_payment(${Number(id)}, ${action}, ${body.verified === true}, ${String(body.tx_hash || '')})`;
    const s = rows[0];
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json({ ok: true, submission: {
      id: s.id, reference: `CE-${s.id}`, status: s.status, expires_at: s.expires_at
    }, delivery: action === 'approve' ? 'queued' : undefined });
  } catch (err) {
    if (err.code === '23505') return res.status(409).json({ error: 'Transaction already submitted or used for membership.' });
    const message = String(err.message || '');
    const known = ['Submission not found', 'Submission already reviewed', 'Manual payment verification required', 'Legacy approval requires manual reconciliation',
      'Subscriber must open their private Start link first', 'A verified transaction hash is required'];
    const safe = known.find(x => message.includes(x));
    if (safe) return res.status(safe === 'Submission not found' ? 404 : 409).json({ error: safe });
    console.error('admin review failed', err.code);
    return res.status(500).json({ error: 'Could not update submission.' });
  }
};
