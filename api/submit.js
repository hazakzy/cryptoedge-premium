const { neon } = require('@neondatabase/serverless');
const { randomBytes } = require('node:crypto');

const METHODS = ['BTC', 'USDT_BSC', 'USDT_ARB'];
const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024; // 2 MB
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!process.env.DATABASE_URL) return res.status(500).json({ error: 'Server not configured' });

  const body = req.body || {};
  const username = String(body.telegram_username || '').trim().replace(/^@/, '');
  const method = String(body.method || '');
  const txHash = String(body.tx_hash || '').trim();
  const shot = body.screenshot_base64 ? String(body.screenshot_base64) : null;
  const shotType = body.screenshot_type ? String(body.screenshot_type) : null;

  if (!/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(username)) {
    return res.status(400).json({ error: 'Enter a valid Telegram username (5-32 letters, numbers, underscores).' });
  }
  if (!METHODS.includes(method)) {
    return res.status(400).json({ error: 'Choose a payment method.' });
  }
  if (txHash && !(method === 'BTC' ? /^[a-fA-F0-9]{64}$/ : /^0x[a-fA-F0-9]{64}$/i).test(txHash)) {
    return res.status(400).json({ error: 'Enter a valid transaction hash for the selected network.' });
  }
  if (!txHash && !shot) {
    return res.status(400).json({ error: 'Provide a transaction hash or a payment screenshot.' });
  }

  let shotBytes = null;
  if (shot) {
    if (!ALLOWED_TYPES.includes(shotType)) {
      return res.status(400).json({ error: 'Screenshot must be PNG, JPEG, or WEBP.' });
    }
    shotBytes = Buffer.from(shot.replace(/^data:[^,]*,/, ''), 'base64');
    if (!shotBytes.length) {
      return res.status(400).json({ error: 'Screenshot could not be read. Please try another image.' });
    }
    if (shotBytes.length > MAX_SCREENSHOT_BYTES) {
      return res.status(400).json({ error: 'Screenshot must be under 2 MB.' });
    }
  }

  try {
    const sql = neon(process.env.DATABASE_URL);
    // The Neon HTTP driver JSON-encodes query params, so a Buffer would be stored as the text
    // {"type":"Buffer","data":[...]}. Send a hex bytea literal and cast it explicitly instead.
    const shotHex = shotBytes ? '\\x' + shotBytes.toString('hex') : null;
    const linkToken = randomBytes(24).toString('hex');
    const rows = await sql`
      INSERT INTO submissions (telegram_username, method, tx_hash, screenshot, screenshot_type, link_token)
      VALUES (${username}, ${method}, ${txHash || null}, ${shotHex}::bytea, ${shot ? shotType : null}, ${linkToken})
      RETURNING id
    `;
    res.setHeader('Cache-Control', 'no-store');
    return res.status(201).json({ ok: true, reference: `CE-${rows[0].id}`, start_token: linkToken });
  } catch (err) {
    if (err.code === '23505') return res.status(409).json({ error: 'This transaction was already submitted. Contact the admin with your existing reference.' });
    console.error('submit error', err);
    return res.status(500).json({ error: 'Could not save your submission. Please try again.' });
  }
};
