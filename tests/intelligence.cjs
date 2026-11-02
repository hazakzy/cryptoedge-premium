const {test}=require('node:test');
const assert=require('node:assert/strict');
const Module=require('node:module');
const fs=require('node:fs');
const path=require('node:path');
const original=Module._load;
Module._load=function(name,...args){
  if(name==='@neondatabase/serverless')throw new Error('Intelligence must not import a database client');
  return original.call(this,name,...args);
};
const handler=require('../api/intelligence');
Module._load=original;
function response(){return {code:200,headers:{},status(c){this.code=c;return this;},setHeader(k,v){this.headers[k]=v;},json(body){this.body=body;return this;}};}
test('public channel metadata works without database or authentication',()=>{
  delete process.env.DATABASE_URL;const res=response();handler({method:'GET'},res);
  assert.equal(res.code,200);assert.deepEqual(res.body,{status:'telegram_only',telegram_url:'https://t.me/cryptoedgelab'});
});
test('legacy publisher cannot write or store an edition',()=>{
  process.env.DATABASE_URL='must-not-be-used';const res=response();handler({method:'POST',body:{body:'old full brief'}},res);
  assert.equal(res.code,410);assert.equal(res.headers['Cache-Control'],'no-store');
});
test('unsupported methods cannot change the channel destination',()=>{
  const res=response();handler({method:'DELETE'},res);assert.equal(res.code,405);
});
test('public pages link to Telegram without fetching a stored Intelligence feed',()=>{
  for(const name of ['index.html','intelligence.html']){
    const html=fs.readFileSync(path.join(__dirname,'..',name),'utf8');
    assert.ok(html.includes('https://t.me/cryptoedgelab'));assert.ok(!html.includes('data-intelligence-feed'));
    assert.ok(!html.includes('/assets/intelligence.js'));assert.ok(!html.includes('/api/intelligence'));
    assert.match(html,/free BTC signals/i);
  }
});
