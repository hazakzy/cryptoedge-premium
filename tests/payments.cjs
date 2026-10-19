const { PGlite } = require('@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const db = new PGlite();
  await db.exec(fs.readFileSync(path.join(__dirname, '../sql/schema.sql'), 'utf8'));
  await db.exec("INSERT INTO submissions(telegram_username,method,tx_hash,status) VALUES('legacy','BTC',repeat('f',64),'approved')");
  for (const file of ['phase1.sql', 'phase1.sql'])
    await db.exec(fs.readFileSync(path.join(__dirname, '../sql', file), 'utf8'));
  const q = (sql, params=[]) => db.query(sql, params);
  let checks = 0;
  const check = (v) => { assert.ok(v); checks++; };
  const payment = async (uid, hash, method='BTC') => (await q(`INSERT INTO submissions
    (telegram_username,telegram_user_id,method,tx_hash) VALUES('tester',$1,$2,$3) RETURNING id`,
    [uid, method, hash])).rows[0].id;
  const review = (id, action='approve', verified=true, hash=null) => q('SELECT * FROM review_payment($1,$2,$3,$4)', [id,action,verified,hash]);
  const fails = async (fn, pattern) => { await assert.rejects(fn, pattern); checks++; };
  const hash = n => n.toString(16).padStart(64,'0');
  await fails(() => review(1), /Legacy approval requires manual reconciliation/);
  check((await q('SELECT * FROM members')).rows.length===0);
  const sid = await payment(11, hash(1));
  await fails(() => review(sid,'approve',false), /Manual payment verification/);
  await review(sid);
  let member = (await q('SELECT * FROM members WHERE telegram_user_id=11')).rows[0];
  check(Math.abs(new Date(member.expires_at)-Date.now()-30*86400000)<10000);
  const expiry = member.expires_at;
  await Promise.all([review(sid),review(sid)]);
  check(+new Date((await q('SELECT expires_at FROM members WHERE telegram_user_id=11')).rows[0].expires_at)===+new Date(expiry));
  check((await q('SELECT * FROM membership_deliveries')).rows.length===1);
  await fails(() => review(sid,'reject'), /already reviewed/);
  await fails(() => payment(12,'0x'+hash(1).toUpperCase()), /unique constraint/);
  const renewal = await payment(11,hash(2));
  await review(renewal);
  check(+new Date((await q('SELECT expires_at FROM members WHERE telegram_user_id=11')).rows[0].expires_at)===+new Date(expiry)+30*86400000);
  await q("UPDATE members SET expires_at=now()-interval '1 day',removed_at=now() WHERE telegram_user_id=11");
  await review(await payment(11,hash(3)));
  member = (await q('SELECT * FROM members WHERE telegram_user_id=11')).rows[0];
  check(member.removed_at===null && Math.abs(new Date(member.expires_at)-Date.now()-30*86400000)<10000);
  const rejected = await payment(12,hash(4));
  await review(rejected,'reject',false);
  await review(rejected,'reject',false);
  await fails(() => review(rejected), /already reviewed/);
  check((await q('SELECT * FROM members WHERE telegram_user_id=12')).rows.length===0);
  await fails(async () => review(await payment(null,hash(5))), /private Start link/);
  const shot = await payment(14,null);
  await fails(() => review(shot), /verified transaction hash/);
  await review(shot,'approve',true,hash(6));
  const duplicateClaim = await payment(15,null);
  await fails(() => review(duplicateClaim,'approve',true,hash(6)), /unique constraint/);
  check((await q('SELECT * FROM members WHERE telegram_user_id=15')).rows.length===0);
  check((await q('SELECT status FROM submissions WHERE id=$1',[duplicateClaim])).rows[0].status==='pending');
  await review(await payment(16,hash(1),'USDT_ARB')); // same text on a different chain is distinct
  await fails(() => review(999999), /not found/);
  // A membership write failure must roll back the decision and transaction claim.
  await db.exec("ALTER TABLE members ADD CONSTRAINT test_failure CHECK(telegram_user_id<>99)");
  const rollback = await payment(99,hash(99));
  await fails(() => review(rollback), /test_failure/);
  check((await q('SELECT * FROM payment_claims WHERE submission_id=$1',[rollback])).rows.length===0);
  check((await q('SELECT status FROM submissions WHERE id=$1',[rollback])).rows[0].status==='pending');
  const queueRollback = await payment(98,hash(98));
  await db.exec(`ALTER TABLE membership_deliveries ADD CONSTRAINT queue_failure CHECK(submission_id<>${queueRollback})`);
  await fails(() => review(queueRollback), /queue_failure/);
  check((await q('SELECT * FROM members WHERE telegram_user_id=98')).rows.length===0);
  check((await q('SELECT * FROM payment_claims WHERE submission_id=$1',[queueRollback])).rows.length===0);
  check((await q('SELECT status FROM submissions WHERE id=$1',[queueRollback])).rows[0].status==='pending');
  console.log(`${checks} database checks passed (isolated PostgreSQL/PGlite).`);
  await db.close();
})().catch(e => { console.error(e); process.exit(1); });

