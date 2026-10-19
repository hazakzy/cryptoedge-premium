// Returns public payment settings. Addresses are set in Vercel env vars.
module.exports = (req, res) => {
  const botUsername = process.env.TELEGRAM_BOT_USERNAME || 'thetce_bot';
  if (!/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(botUsername))
    return res.status(500).json({ error: 'Telegram bot username is not configured correctly.' });
  res.setHeader('Cache-Control', 'no-store');
  res.status(200).json({
    price_usd: 10,
    duration_days: 30,
    telegram_bot_username: botUsername,
    methods: {
      BTC: { label: 'Bitcoin (BTC)', network: 'Bitcoin', address: process.env.BTC_ADDRESS || '' },
      USDT_BSC: { label: 'USDT (BEP-20)', network: 'BNB Smart Chain (BSC) only', address: process.env.BSC_ADDRESS || '' },
      USDT_ARB: { label: 'USDT (Arbitrum One)', network: 'Arbitrum One only', address: process.env.ARB_ADDRESS || '' }
    }
  });
};
