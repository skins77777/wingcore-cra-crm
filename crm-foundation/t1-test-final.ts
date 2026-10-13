import {RestApiClient} from 'twenty-client-sdk/rest';
import {createHash} from 'node:crypto';
export const stamp=v=>typeof v==='string'&&v?Date.parse(v):NaN;
export const hkDay=v=>new Date(stamp(v)+8*3600000).toISOString().slice(0,10);
export const plusDays=(v,n)=>new Date(Date.parse(hkDay(v)+'T15:59:00Z')+n*86400000).toISOString();
export function stableId(key){let h=createHash('sha256').update(key).digest('hex').slice(0,32);return `${h.slice(0,8)}-${h.slice(8,12)}-5${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20)}`;}
export function plan(o,tasks,now){
 const own=tasks.filter(t=>t.craT1OpportunityId===o.id&&t.tiXingQuChongJian?.startsWith('T1|'+o.id+'|'));
 const open=own.filter(t=>t.status!=='DONE');
 const stopped=o.craT1StopReason?.trim()||['CLOSED_WON','CLOSED_LOST'].includes(o.stage);
 if(stopped)return {action:'stop',open,reason:o.craT1StopReason||'商机已结束'};
 if(!o.craT1QuoteRound?.trim()||!Number.isFinite(stamp(o.craT1QuoteSentAt))||!o.craT1QuoteEvidence?.trim())return {action:'blocked',open,reason:'缺少真实报价轮次、发送时间或依据'};
 if(stamp(o.craT1QuoteSentAt)>stamp(now))return {action:'blocked',open,reason:'报价发送时间在未来'};
 const prefix='T1|'+o.id+'|'+o.craT1QuoteRound+'|';
 const obsolete=open.filter(t=>!t.tiXingQuChongJian.startsWith(prefix));
 const current=own.filter(t=>t.tiXingQuChongJian.startsWith(prefix));
 const active=current.filter(t=>t.status!=='DONE');
 if(active.length>1)return {action:'blocked',open,reason:'本轮出现多个未完成提醒'};
 const validDone=current.filter(t=>t.status==='DONE'&&!t.tiXingShiXiaoYuanYin&&Number.isFinite(stamp(t.jianChaWanChengShiJian)));
 if(current.some(t=>t.status==='DONE'&&!t.tiXingShiXiaoYuanYin&&!Number.isFinite(stamp(t.jianChaWanChengShiJian))))return {action:'blocked',open,reason:'完成事件时间尚未记录'};
 // Three generated reminders exhaust the round even if manually voided.
 const issued=current.length;
 let last=validDone.map(t=>t.jianChaWanChengShiJian).sort((a,b)=>stamp(b)-stamp(a))[0];
 const messageFollowed=Number.isFinite(stamp(o.craT1FollowedAt))&&stamp(o.craT1FollowedAt)>=stamp(o.craT1QuoteSentAt)?o.craT1FollowedAt:null;
 if(messageFollowed&&stamp(messageFollowed)>stamp(now))return {action:'blocked',open,reason:'实际跟进时间在未来'};
 if(active.length&&messageFollowed&&stamp(messageFollowed)>=stamp(active[0].createdAt))return {action:'complete',task:active[0],completedAt:messageFollowed,obsolete};
 if(messageFollowed&&(!last||stamp(messageFollowed)>stamp(last)))last=messageFollowed;
 const agreed=Number.isFinite(stamp(o.craT1AgreedAt))&&stamp(o.craT1AgreedAt)>=stamp(o.craT1QuoteSentAt)&&(!last||stamp(o.craT1AgreedAt)>stamp(last))?o.craT1AgreedAt:null;
 const dueAt=agreed||plusDays(last||o.craT1QuoteSentAt,last?3:2);
 if(active.length)return {action:'keep',task:active[0],dueAt,obsolete};
 if(issued>=3)return {action:'exhausted',obsolete};
 if(current.some(t=>t.tiXingShiXiaoYuanYin)&&!validDone.length)return {action:'blocked',open,reason:'本轮曾被人工停止，需明确开启新报价轮次'};
 if(hkDay(now)<hkDay(dueAt))return {action:'future',dueAt,obsolete};
 const key=prefix+(issued+1);
 return {action:'create',key,id:stableId(key),dueAt,round:issued+1,obsolete};
}

const runScan=async()=>{
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

export const main=async()=>{
 const api=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 const id='48bf7b49-8f2e-5f5b-bdd7-a50bbf37b90a';const checks=[];
 const check=(v,label)=>{if(!v)throw new Error(label);checks.push(label);};
 const r=await api.get('/rest/tasks',{query:{filter:'craT1OpportunityId[eq]:'+id,limit:200}});const tasks=r.data.tasks;
 const q1=tasks.filter(t=>t.tiXingQuChongJian.includes('|TEST-Q1|'));
 check(q1.length===3&&q1.every(t=>t.status==='DONE'&&!!t.jianChaWanChengShiJian),'three completed reminders in original round');
 const q2=tasks.filter(t=>t.tiXingQuChongJian.includes('|TEST-Q2|'));
 check(q2.length===1&&q2[0].status==='DONE'&&!!q2[0].tiXingShiXiaoYuanYin&&!q2[0].jianChaWanChengShiJian,'new quote round stopped without false completion');
 check((await runScan()).created===0,'stopped round does not recreate');
 let forbidden=false;try{await api.patch('/rest/opportunities/'+id,{name:'TEST｜T1报价提醒验收｜非业务'});}catch(e){forbidden=(e.status===403||e.body?.code==='PERMISSION_DENIED');}
 check(forbidden,'opportunity updates denied');
 let denied=false;try{await api.get('/rest/dingDans');}catch(e){denied=(e.status===403||e.body?.code==='PERMISSION_DENIED');}
 check(denied,'orders access denied');
 return {checks,fixtureId:id,fixtureTaskIds:tasks.map(t=>t.id),modelCalls:0};
};


