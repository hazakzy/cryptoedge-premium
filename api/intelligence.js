// Compatibility endpoint only. Intelligence lives in Telegram; no database access.
module.exports = (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method === 'POST') {
    res.setHeader('Cache-Control', 'no-store');
    return res.status(410).json({error:'Website publication is retired. Intelligence is published in Telegram.'});
  }
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({error:'Method not allowed'});
  }
  res.setHeader('Cache-Control', 'public, s-maxage=3600');
  return res.status(200).json({status:'telegram_only', telegram_url:'https://t.me/cryptoedgelab'});
};
