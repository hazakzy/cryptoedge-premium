const crypto = require('crypto');

// Returns true if the request is authorized; otherwise sends the response and returns false.
function requireAdmin(req, res) {
  const expected = process.env.ADMIN_TOKEN;
  if (!expected || !process.env.DATABASE_URL) {
    res.status(500).json({ error: 'Server not configured' });
    return false;
  }
  const header = String(req.headers['authorization'] || '');
  const m = header.match(/^Bearer\s+(.+)$/i);
  const provided = m ? m[1].trim() : '';
  const a = crypto.createHash('sha256').update(provided).digest();
  const b = crypto.createHash('sha256').update(expected).digest();
  if (!provided || !crypto.timingSafeEqual(a, b)) {
    res.status(401).json({ error: 'Unauthorized' });
    return false;
  }
  return true;
}

module.exports = { requireAdmin };
