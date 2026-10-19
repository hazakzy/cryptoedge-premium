const { test } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const original = Module._load;
let calls = [], failure = null;
Module._load = function(name, ...args) {
  if (name === '@neondatabase/serverless') return { neon: () => async (strings, ...values) => {
    calls.push({sql:strings.join('?'),values});
    if (failure) throw failure;
    return [{id:1,status:'approved',expires_at:'2030-01-01'}];
  }};
  return original.call(this,name,...args);
};
const review = require('../api/admin/review');
const submit = require('../api/submit');
Module._load = original;
process.env.ADMIN_TOKEN='test-only';
process.env.DATABASE_URL='test-only';
function response() { return {code:200, status(v){this.code=v;return this;},json(v){this.body=v;return this;},setHeader(){}}; }
function request(body, authorized=true) { return {method:'POST',body,headers:{authorization:authorized?'Bearer test-only':'Bearer wrong'}}; }

test('review rejects unauthorized calls before database access', async () => {
  calls=[];const res=response(); await review(request({id:1,action:'approve',verified:true},false),res);
  assert.equal(res.code,401);assert.equal(calls.length,0);
});
test('approval requires explicit manual verification', async () => {
  calls=[];const res=response();await review(request({id:1,action:'approve'}),res);
  assert.equal(res.code,400);assert.equal(calls.length,0);
});
test('website uses shared review transaction and reports queued delivery', async () => {
  calls=[];const res=response();await review(request({id:1,action:'approve',verified:true,tx_hash:'a'.repeat(64)}),res);
  assert.equal(res.code,200);assert.equal(res.body.delivery,'queued');
  assert.match(calls[0].sql,/review_payment/);assert.equal(calls[0].values[2],true);
  assert.equal(res.body.submission.link_token,undefined);
});
test('rejection does not require verified payment', async () => {
  const res=response();await review(request({id:1,action:'reject'}),res);assert.equal(res.code,200);
});
test('duplicate claims have actionable conflict response', async () => {
  failure={code:'23505'};const res=response();await review(request({id:1,action:'approve',verified:true}),res);
  failure=null;assert.equal(res.code,409);
});
test('submission returns unpredictable private Start token', async () => {
  calls=[];
  const body={telegram_username:'tester',method:'BTC',tx_hash:'a'.repeat(64)};
  const a=response(),b=response();await submit(request(body),a);await submit(request(body),b);
  assert.equal(a.code,201);assert.match(a.body.start_token,/^[a-f0-9]{48}$/);
  assert.notEqual(a.body.start_token,b.body.start_token);assert.match(calls[0].sql,/link_token/);
});
test('malformed payment hashes are rejected', async () => {
  const res=response();await submit(request({telegram_username:'tester',method:'BTC',tx_hash:'fake'}),res);
  assert.equal(res.code,400);
});
test('duplicate submission is not a server error', async () => {
  failure={code:'23505'};const res=response();
  await submit(request({telegram_username:'tester',method:'BTC',tx_hash:'a'.repeat(64)}),res);
  failure=null;assert.equal(res.code,409);
});

const config = require('../api/config');
test('staging can use its own Telegram bot without changing production defaults', () => {
  delete process.env.TELEGRAM_BOT_USERNAME;
  const a=response();config({},a);assert.equal(a.body.telegram_bot_username,'thetce_bot');
  process.env.TELEGRAM_BOT_USERNAME='cryptoedge_test_bot';
  const b=response();config({},b);assert.equal(b.body.telegram_bot_username,'cryptoedge_test_bot');
  process.env.TELEGRAM_BOT_USERNAME='bad<name';
  const c=response();config({},c);assert.equal(c.code,500);
  delete process.env.TELEGRAM_BOT_USERNAME;
});
