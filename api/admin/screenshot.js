const { neon } = require('@neondatabase/serverless');
const { requireAdmin } = require('../_auth');

const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

module.exports = async (req, res) => {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  if (!requireAdmin(req, res)) return;

  const rawId = String((req.query && req.query.id) || '');
  if (!/^\d{1,9}$/.test(rawId)) return res.status(400).json({ error: 'Invalid id' });

  try {
    const sql = neon(process.env.DATABASE_URL);
    const rows = await sql`
      SELECT screenshot, screenshot_type FROM submissions WHERE id = ${parseInt(rawId, 10)}
    `;
    const row = rows[0];
    if (!row || !row.screenshot) return res.status(404).json({ error: 'Not found' });

    // Neon's HTTP driver returns BYTEA as a Buffer (or a "\x..." hex string in some versions)
    let bytes = row.screenshot;
    if (typeof bytes === 'string') {
      bytes = bytes.startsWith('\\x') ? Buffer.from(bytes.slice(2), 'hex') : Buffer.from(bytes, 'binary');
    } else if (!Buffer.isBuffer(bytes)) {
      bytes = Buffer.from(bytes);
    }
    // Legacy rows saved before the submit fix hold the JSON text of a serialized Buffer.
    if (bytes.length && bytes[0] === 0x7b && bytes.slice(0, 16).toString('latin1').startsWith('{"type":"Buffer"')) {
      try {
        const parsed = JSON.parse(bytes.toString('utf8'));
        if (parsed && Array.isArray(parsed.data)) bytes = Buffer.from(parsed.data);
      } catch (e) { /* keep raw bytes */ }
    }
    if (!bytes.length) return res.status(404).json({ error: 'Screenshot is empty' });
    const type = ALLOWED_TYPES.includes(row.screenshot_type) ? row.screenshot_type : 'application/octet-stream';

    res.setHeader('Content-Type', type);
    res.setHeader('Content-Length', bytes.length);
    res.setHeader('Cache-Control', 'private, no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Disposition', 'inline');
    return res.status(200).end(bytes);
  } catch (err) {
    console.error('admin screenshot error', err);
    return res.status(500).json({ error: 'Could not load screenshot.' });
  }
};
