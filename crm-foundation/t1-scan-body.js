export const main=async()=>{
 if(!process.env.CRA_T1_API_KEY)throw new Error('报价提醒专用后台凭据尚未配置');
 const c=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 const all=async plural=>{
  let rows=[],cursor;
  for(let n=0;n<100;n++){
   const r=await c.get('/rest/'+plural,{query:{limit:200,...(cursor?{starting_after:cursor}:{})}});
   if(!Array.isArray(r?.data?.[plural]))throw new Error('Invalid collection '+plural);
   rows.push(...r.data[plural]);if(!r.pageInfo?.hasNextPage)return rows;
   if(!r.pageInfo.endCursor||r.pageInfo.endCursor===cursor)throw new Error('Invalid cursor');cursor=r.pageInfo.endCursor;
  }throw new Error('Pagination bound');
 };
 const one=async(plural,singular,id)=>{const r=await c.get('/rest/'+plural+'/'+id);if(!r?.data?.[singular]?.id)throw new Error('Missing '+singular);return r.data[singular];};
 const result={scanned:0,created:0,kept:0,completed:0,stopped:0,blocked:[],modelCalls:0};
 const now=new Date().toISOString();
 const update=async(task,fields)=>{
  const current=await one('tasks','task',task.id);
  if(current.updatedAt!==task.updatedAt)throw new Error('Task concurrently changed');
  const r=await c.patch('/rest/tasks',fields,{query:{filter:'and(id[eq]:'+task.id+',updatedAt[eq]:'+task.updatedAt+')'}});
  const after=await one('tasks','task',task.id);
  if(!Object.entries(fields).every(([k,v])=>after[k]===v))throw new Error('Task update readback mismatch');
 };
 for(const listed of await all('opportunities')){
  const o=await one('opportunities','opportunity',listed.id);const tasks=await all('tasks');
  const p=plan(o,tasks,now);result.scanned++;
  if(p.action==='blocked'){if(p.open?.length||o.craT1QuoteRound)result.blocked.push({opportunityId:o.id,reason:p.reason});continue;}
  // Before any task write, ensure the quote/stopping facts still have this version.
  const latest=await one('opportunities','opportunity',o.id);
  if(latest.updatedAt!==o.updatedAt){result.blocked.push({opportunityId:o.id,reason:'商机已被更新，下轮重新核对'});continue;}
  const obsolete=p.action==='stop'?p.open:p.obsolete||[];
  for(const t of obsolete){await update(t,{status:'DONE',tiXingShiXiaoYuanYin:p.action==='stop'?p.reason:'新版商品报价已实际发送，旧轮停止'});result.stopped++;}
  if(p.action==='stop'||p.action==='future'||p.action==='exhausted')continue;
  if(p.action==='complete'){await update(p.task,{status:'DONE',jianChaWanChengShiJian:p.completedAt});result.completed++;continue;}
  if(p.action==='keep'){if(p.task.dueAt!==p.dueAt)await update(p.task,{dueAt:p.dueAt});result.kept++;continue;}
  const person=o.pointOfContactId?await one('people','person',o.pointOfContactId):null;
  const assigneeId=o.ownerId||person?.keHuFuZeRenId;
  if(!assigneeId){result.blocked.push({opportunityId:o.id,reason:'商机/客户负责人未指定'});continue;}
  const task={id:p.id,title:o.name+'：报价反馈跟进（'+p.round+'/3）',status:'TODO',dueAt:p.dueAt,assigneeId,craT1OpportunityId:o.id,tiXingQuChongJian:p.key,
    bodyV2:{markdown:'请实际询问本次商品报价反馈或采购决定，完成后记录结果并将任务设为完成。普通问候不计完成。\n\n商机：http://localhost:3000/object/opportunity/'+o.id+'\n报价轮次：'+o.craT1QuoteRound+'\n实际发送：'+o.craT1QuoteSentAt+'\n来源：'+o.craT1QuoteEvidence+'\n\n提醒只显示在CRM，不主动发客户消息。'}};
  try{await c.post('/rest/tasks',task);}catch(e){const existing=await one('tasks','task',p.id).catch(()=>null);if(!existing||existing.tiXingQuChongJian!==p.key)throw e;}
  const after=await one('tasks','task',p.id);
  if(after.tiXingQuChongJian!==p.key||after.craT1OpportunityId!==o.id||after.assigneeId!==assigneeId)throw new Error('Creation readback mismatch');
  result.created++;
 }
 return result;
};
