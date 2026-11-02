const {neon}=require('@neondatabase/serverless');
const {validate,authorized}=require('../lib/public-intelligence');

module.exports=async (req,res)=>{
  res.setHeader('X-Content-Type-Options','nosniff');
  if (!['GET','POST'].includes(req.method)) {
    res.setHeader('Allow','GET, POST');return res.status(405).json({error:'Method not allowed'});
  }
  if(req.method==='POST'){
    res.setHeader('Cache-Control','no-store');
    if(!authorized(req.headers.authorization))return res.status(401).json({error:'Unauthorized'});
    let p;try{p=validate(req.body);}catch{return res.status(400).json({error:'Invalid or stale brief'});}
    if(!process.env.DATABASE_URL)return res.status(503).json({error:'Publishing is not configured'});
    try{
      const sql=neon(process.env.DATABASE_URL);
      const rows=await sql`WITH pruned AS (
        DELETE FROM public_intelligence_briefs WHERE edition_date < (now() AT TIME ZONE 'Europe/London')::date-6
      ), added AS (
        INSERT INTO public_intelligence_briefs(edition_date,as_of,title,preview,body,content_hash)
        VALUES(${p.edition_date}::date,${p.as_of}::timestamptz,${p.title},${p.preview},${p.body},${p.hash})
        ON CONFLICT(edition_date) DO NOTHING RETURNING content_hash
      ) SELECT content_hash FROM added UNION ALL
        SELECT content_hash FROM public_intelligence_briefs WHERE edition_date=${p.edition_date}::date LIMIT 1`;
      if(!rows.length)return res.status(503).json({error:'Publication is settling. Retry the same edition.'});
      if(rows[0].content_hash!==p.hash)return res.status(409).json({error:'An edition already exists with different content. Review before correcting.'});
      return res.status(200).json({ok:true,edition_date:p.edition_date});
    }catch{return res.status(503).json({error:'Publishing is temporarily unavailable'});}
  }
  const limit=String(req.query?.limit||'1');
  if(Object.keys(req.query||{}).some(key=>key!=='limit') || !['1','7'].includes(limit))return res.status(400).json({error:'Invalid limit'});
  res.setHeader('Cache-Control','public, s-maxage=300, stale-while-revalidate=600');
  if(!process.env.DATABASE_URL)return res.status(200).json({briefs:[],status:'preparing'});
  try{
    const sql=neon(process.env.DATABASE_URL);
    const rows=await sql`SELECT edition_date::text AS edition_date,as_of,title,preview,body
      FROM public_intelligence_briefs WHERE edition_date >= (now() AT TIME ZONE 'Europe/London')::date-6
      ORDER BY edition_date DESC LIMIT ${Number(limit)}`;
    return res.status(200).json({briefs:rows,status:rows.length?'published':'preparing'});
  }catch(error){
    if(error.code==='42P01')return res.status(200).json({briefs:[],status:'preparing'});
    res.setHeader('Cache-Control','no-store');
    return res.status(503).json({error:'The latest brief is temporarily unavailable'});
  }
};
module.exports.config={api:{bodyParser:{sizeLimit:'24kb'}}};
