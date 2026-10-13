export const main=async()=>{
 if(!process.env.CRA_T1_API_KEY)throw new Error('售前提醒受限凭据未配置');
 const c=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 const all=async plural=>{let rows=[],cursor;for(let n=0;n<100;n++){const r=await c.get('/rest/'+plural,{query:{limit:200,...(cursor?{starting_after:cursor}:{})}});if(!Array.isArray(r?.data?.[plural]))throw new Error('Invalid '+plural);rows.push(...r.data[plural]);if(!r.pageInfo?.hasNextPage)return rows;if(!r.pageInfo.endCursor||cursor===r.pageInfo.endCursor)throw new Error('Invalid cursor');cursor=r.pageInfo.endCursor;}throw new Error('Pagination bound');};
 const one=async(plural,singular,id)=>{const r=await c.get('/rest/'+plural+'/'+id);if(!r?.data?.[singular]?.id)throw new Error('Missing '+singular);return r.data[singular];};
 const update=async(t,fields)=>{const current=await one('tasks','task',t.id);if(current.updatedAt!==t.updatedAt)throw new Error('Task changed concurrently');await c.patch('/rest/tasks',fields,{query:{filter:'and(id[eq]:'+t.id+',updatedAt[eq]:'+t.updatedAt+')'}});const after=await one('tasks','task',t.id);if(!Object.entries(fields).every(([k,v])=>after[k]===v))throw new Error('Task readback mismatch');};
 const result={scanned:0,created:0,kept:0,stopped:0,future:0,handled:0,missingFacts:0,blocked:[],modelCalls:0};
 const now=new Date().toISOString();
 for(const listed of await all('opportunities')){
  result.scanned++;
  if(!listed.craReplyReviewScope&&!listed.craReplyReviewAnchorAt){result.missingFacts++;continue;}
  const o=await one('opportunities','opportunity',listed.id);const tasks=await all('tasks');const p=plan(o,tasks,now);
  if(p.action==='blocked'){result.blocked.push({opportunityId:o.id,reason:p.reason});continue;}
  const latest=await one('opportunities','opportunity',o.id);if(latest.updatedAt!==o.updatedAt){result.blocked.push({opportunityId:o.id,reason:'商机刚被更新，下轮重新核对'});continue;}
  const obsolete=p.action==='stop'?p.open:p.obsolete||[];
  for(const t of obsolete){await update(t,{status:'DONE',tiXingShiXiaoYuanYin:p.action==='stop'?p.reason:'客户出现新的有效回复，旧复核周期失效'});result.stopped++;}
  if(p.action==='stop')continue;
  if(p.action==='future'){result.future++;continue;}
  if(p.action==='handled'){result.handled++;continue;}
  if(p.action==='keep'){if(p.task.dueAt!==p.dueAt)await update(p.task,{dueAt:p.dueAt});result.kept++;continue;}
  const person=o.pointOfContactId?await one('people','person',o.pointOfContactId):null;
  const assigneeId=o.ownerId||person?.keHuFuZeRenId;
  if(!assigneeId){result.blocked.push({opportunityId:o.id,reason:'商机/客户负责人未指定'});continue;}
  const task={id:p.id,title:o.name+'：30天无有效回复人工复核',status:'TODO',dueAt:p.dueAt,assigneeId,craReplyReviewOpportunityId:o.id,tiXingQuChongJian:p.key,
   bodyV2:{markdown:'请核对本次采购是否继续、延期或已明确输单。本提醒不自动判输单，不修改订单或收款。\n\n商机：http://localhost:3000/object/opportunity/'+o.id+'\n客户有效回复起点：'+o.craReplyReviewAnchorAt+'\n依据：'+o.craReplyReviewEvidence+'\n\n继续/延期：在商机记录处理结果及下次检查日期，再完成本任务。转输单：由你确认并修改采购阶段，记录主要原因；仅任务完成不代表输单。客户新有效回复后按原实际日期更新起点；普通问候和自己的催问不重置。\n\n已付款、采购、运输、清关、售后及补差沟通应排除。只在CRM内部提醒，不主动发消息。'}};
  try{await c.post('/rest/tasks',task);}catch(e){const exists=await one('tasks','task',p.id).catch(()=>null);if(!exists||exists.tiXingQuChongJian!==p.key)throw e;}
  const after=await one('tasks','task',p.id);if(after.tiXingQuChongJian!==p.key||after.craReplyReviewOpportunityId!==o.id||after.assigneeId!==assigneeId)throw new Error('Task creation mismatch');result.created++;
 }
 return result;
};
