const {test,before,beforeEach,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {PGlite}=require('@electric-sql/pglite');
const {validate,ukDate}=require('../lib/public-intelligence');
let db,calls=[],failure=null;
const original=Module._load;
Module._load=function(name,...args){
  if(name==='@neondatabase/serverless')return {neon:()=>async(strings,...values)=>{
    const sql=strings[0]+strings.slice(1).map((s,i)=>'$'+(i+1)+s).join('');
    calls.push(sql);if(failure)throw failure;return (await db.query(sql,values)).rows;
  }};
  return original.call(this,name,...args);
};
const handler=require('../api/intelligence');Module._load=original;
const secret='test-publisher-secret-with-more-than-32-characters';
function publication(){const now=new Date();return {edition_date:ukDate(now),as_of:now.toISOString(),title:'Daily market brief',preview:'A focused view of the market.',body:'MARKET OUTLOOK\nMixed conditions. Wait for confirmation.'};}
function response(){return {code:200,headers:{},status(c){this.code=c;return this;},setHeader(k,v){this.headers[k]=v;},json(b){this.body=b;return this;}};}
function request(method,body,token=secret){return {method,body,headers:{authorization:'Bearer '+token},query:{}};}
before(async()=>{db=new PGlite();await db.exec(fs.readFileSync(path.join(__dirname,'../sql/intelligence.sql'),'utf8'));});
beforeEach(async()=>{await db.exec('DELETE FROM public_intelligence_briefs');calls=[];failure=null;process.env.DATABASE_URL='local-test-only';process.env.INTELLIGENCE_PUBLISH_TOKEN=secret;});
after(async()=>{await db.close();});
test('free public read needs no account or authorization',async()=>{
  const p=publication(),sent=response();await handler(request('POST',p),sent);assert.equal(sent.code,200);
  const read=response();await handler({method:'GET',headers:{},query:{}},read);
  assert.equal(read.code,200);assert.equal(read.body.briefs[0].body,p.body);
  assert.match(read.headers['Cache-Control'],/s-maxage=300/);assert.ok(calls.every(s=>!s.includes('members')));
});
test('publishing rejects incorrect credentials before database access',async()=>{
  const res=response();await handler(request('POST',publication(),'wrong'),res);assert.equal(res.code,401);assert.equal(calls.length,0);
});
test('identical publication retries do not duplicate an edition',async()=>{
  const p=publication();for(let i=0;i<2;i++){const res=response();await handler(request('POST',p),res);assert.equal(res.code,200);}
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public_intelligence_briefs')).rows[0].n,1);
});
test('conflicting content cannot silently overwrite a published brief',async()=>{
  const p=publication();await handler(request('POST',p),response());const res=response();
  await handler(request('POST',{...p,body:'Different conclusion'}),res);assert.equal(res.code,409);
  assert.equal((await db.query('SELECT body FROM public_intelligence_briefs')).rows[0].body,p.body);
});
test('private provider details and additional research payload fields are rejected',async()=>{
  for(const change of [{body:'Coinalyze CVD and funding rate readings'},{raw_evidence:{private:true}},{body:'DEMONSTRATION — FICTIONAL DATA'}]){
    const res=response();await handler(request('POST',{...publication(),...change}),res);assert.equal(res.code,400);
  }assert.equal(calls.length,0);
});
test('stale, future and oversized publications are rejected',()=>{
  const now=new Date();for(const as_of of [new Date(now-21*60000).toISOString(),new Date(+now+60000).toISOString()])assert.throws(()=>validate({...publication(),as_of},now));
  assert.throws(()=>validate({...publication(),body:'x'.repeat(16001)},now));
});
test('publication prunes old editions and retains only the current seven-day window',async()=>{
  await db.exec("INSERT INTO public_intelligence_briefs VALUES ((now() AT TIME ZONE 'Europe/London')::date-8,now(),'Old','Old','Old',repeat('a',64)),((now() AT TIME ZONE 'Europe/London')::date-6,now(),'Keep','Keep','Keep',repeat('b',64))");
  const res=response();await handler(request('POST',publication()),res);assert.equal(res.code,200);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public_intelligence_briefs')).rows[0].n,2);
});
test('the database independently enforces the brief size limit',async()=>{
  await assert.rejects(db.query("INSERT INTO public_intelligence_briefs VALUES (current_date,now(),'Title','Preview',$1,repeat('a',64))",['x'.repeat(16001)]));
});
test('an unconfigured site has a truthful empty state',async()=>{
  delete process.env.DATABASE_URL;const res=response();await handler({method:'GET',headers:{},query:{}},res);
  assert.deepEqual(res.body,{briefs:[],status:'preparing'});assert.equal(calls.length,0);
});
test('missing migration does not expose database details',async()=>{
  failure={code:'42P01',message:'private database details'};const res=response();await handler({method:'GET',headers:{},query:{}},res);
  assert.equal(res.code,200);assert.equal(res.body.status,'preparing');assert.ok(!JSON.stringify(res.body).includes('database'));
});
test('reads are bounded and unsupported methods are rejected',async()=>{
  const invalid=response();await handler({method:'GET',headers:{},query:{limit:'1000000'}},invalid);assert.equal(invalid.code,400);
  const extra=response();await handler({method:'GET',headers:{},query:{limit:'1',random:'cache-bypass'}},extra);assert.equal(extra.code,400);
  const unsupported=response();await handler({method:'DELETE',headers:{},query:{}},unsupported);assert.equal(unsupported.code,405);
});
test('edition dates use UK local days around summer midnight',()=>{
  assert.equal(ukDate(new Date('2026-07-01T23:30:00Z')),'2026-07-02');
  assert.equal(ukDate(new Date('2026-11-01T23:30:00Z')),'2026-11-01');
});
