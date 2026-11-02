const crypto = require('node:crypto');
const privateCopy = /coinalyze|coinglass|defillama|nansen|cryptoquant|glassnode|bybit|\bcvd\b|\boi\b|open interest|funding rate|ema\s*\d|api[_ -]?key|https?:\/\/|<(?:script|iframe|img)\b|DEMONSTRATION|FICTIONAL DATA/i;
function ukDate(date) {
  const parts = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);
  const get = type => parts.find(p=>p.type===type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function validate(value, now = new Date()) {
  const fields = ['edition_date','as_of','title','preview','body'];
  if (!value || Array.isArray(value) || typeof value !== 'object' || Object.keys(value).some(k=>!fields.includes(k))) throw new TypeError('Invalid publication fields');
  for (const [name,max] of [['title',100],['preview',240],['body',16000]]) {
    if (typeof value[name] !== 'string' || !value[name].trim() || Buffer.byteLength(value[name])>max || privateCopy.test(value[name])) throw new TypeError('Invalid subscriber copy');
  }
  if (/[\r\n]/.test(value.title+value.preview)) throw new TypeError('Invalid preview');
  const asOf = new Date(value.as_of);
  if (typeof value.as_of !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value.as_of) ||
      !Number.isFinite(asOf.getTime()) || now-asOf<0 || now-asOf>20*60*1000 ||
      value.edition_date!==ukDate(now) || ukDate(asOf)!==value.edition_date) throw new TypeError('Invalid edition date or stale brief');
  return {...value,hash:crypto.createHash('sha256').update(JSON.stringify(fields.map(k=>value[k]))).digest('hex')};
}
function authorized(header) {
  const expected = process.env.INTELLIGENCE_PUBLISH_TOKEN || '';
  if (expected.length<32 || typeof header!=='string' || !header.startsWith('Bearer ')) return false;
  const supplied=header.slice(7);
  if (!supplied || supplied.length>512) return false;
  const hash=x=>crypto.createHash('sha256').update(x).digest();
  return crypto.timingSafeEqual(hash(supplied),hash(expected));
}
module.exports={validate,authorized,ukDate};
