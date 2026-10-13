import {RestApiClient} from 'twenty-client-sdk/rest';
import {createHash} from 'node:crypto';
export const stamp=v=>typeof v==='string'&&v?Date.parse(v):NaN;
export const hkDay=v=>new Date(stamp(v)+8*3600000).toISOString().slice(0,10);
export const plusDays=(v,n)=>new Date(Date.parse(hkDay(v)+'T15:59:00Z')+n*86400000).toISOString();
export const digest=v=>createHash('sha256').update(v).digest('hex');
export const stableId=key=>{const h=digest(key).slice(0,32);return `${h.slice(0,8)}-${h.slice(8,12)}-5${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20)}`;};
export function plan(o,tasks,now){
 const own=tasks.filter(t=>t.craReplyReviewOpportunityId===o.id&&t.tiXingQuChongJian?.startsWith('L1|'+o.id+'|'));
 const open=own.filter(t=>t.status!=='DONE');
 if(o.craReplyReviewScope==='EXCLUDED'||o.craReplyReviewDecision==='LOST_CONFIRMED')return {action:'stop',open,reason:'已人工排除本复核范围或确认已转输单'};
 const allowed=['询盘','需求确认','报价'];
 const excluded=['订单确认','订单已确认','付款待核实','采购/物流准备','采购备货','运输/交接','运输交接中','目的国清关中','退回重发准备','售后','成功','客户安全收货','输单','已取消'];
 if(excluded.includes(o.craPurchaseStage))return {action:'stop',open,reason:'已离开未付款售前询盘/报价范围'};
 if(o.craReplyReviewScope!=='UNPAID_PRESALES'||!allowed.includes(o.craPurchaseStage))return {action:'blocked',open,reason:'未核实属于未付款售前询盘/报价'};
 if(!Number.isFinite(stamp(o.craReplyReviewAnchorAt))||!o.craReplyReviewEvidence?.trim())return {action:'blocked',open,reason:'缺客户有效回复/首次询盘实际日期及依据'};
 if(stamp(o.craReplyReviewAnchorAt)>stamp(now))return {action:'blocked',open,reason:'有效回复日期在未来'};
 const anchor=new Date(stamp(o.craReplyReviewAnchorAt)).toISOString();
 const prefix='L1|'+o.id+'|'+digest(anchor).slice(0,16)+'|';
 const current=own.filter(t=>t.tiXingQuChongJian.startsWith(prefix));
 const active=current.filter(t=>t.status!=='DONE');
 if(active.length>1)return {action:'blocked',open,reason:'同一回复周期出现多个未处理复核任务'};
 let next=null;
 if(['CONTINUE','DEFER'].includes(o.craReplyReviewDecision)){
  if(!Number.isFinite(stamp(o.craReplyReviewNextAt)))return {action:'blocked',open,reason:'选择继续/延期后须指定下次复核日期'};
  if(stamp(o.craReplyReviewNextAt)<=stamp(anchor))return {action:'blocked',open,reason:'下次复核日期须晚于有效回复起点'};
  next=new Date(stamp(o.craReplyReviewNextAt)).toISOString();
 }
 let dueAt=plusDays(anchor,30);
 for(const v of [o.craReplyReviewAgreedAt,next])if(Number.isFinite(stamp(v))&&hkDay(v)>hkDay(dueAt))dueAt=v;
 const obsolete=open.filter(t=>!t.tiXingQuChongJian.startsWith(prefix));
 // A deferral never creates a second task while the first remains unresolved.
 if(active.length)return {action:'keep',task:active[0],dueAt,obsolete};
 const key=prefix+(next?digest(next).slice(0,16):'initial');
 if(current.some(t=>t.tiXingQuChongJian===key))return {action:'handled',obsolete,reason:'此复核已处理；需要新的明确日期或客户有效回复'};
 if(current.length&&!next)return {action:'blocked',open,reason:'复核完成后未指定继续/延期日期'};
 if(hkDay(now)<hkDay(dueAt))return {action:'future',dueAt,obsolete};
 return {action:'create',key,id:stableId(key),dueAt,obsolete};
}

const runScan=async()=>{
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

export const main=async()=>{
 const admin=new RestApiClient({baseUrl:'http://server:3000'});
 const api=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 const id='73779383-9e27-5e0f-9b74-c7fb685e646b';
 if((await admin.get('/rest/opportunities/'+id).catch(()=>null))?.data?.opportunity)throw new Error('Fixture exists; inspect before rerun');
 const p=await admin.get('/rest/people/8b8e32d1-4880-4d99-8f93-dff1a338b7d6');
 const past=new Date(Date.now()-35*86400000).toISOString();
 await admin.post('/rest/opportunities',{id,name:'TEST｜L1无回复复核｜非业务',stage:'NEW',ownerId:p.data.person.keHuFuZeRenId,craPurchaseStage:'询盘',craReplyReviewScope:'UNPAID_PRESALES',craReplyReviewAnchorAt:past,craReplyReviewEvidence:'合成测试：客户有效采购回复，非真实业务'});
 const checks=[];const check=(v,label)=>{if(!v)throw new Error(label);checks.push(label);};
 check((await runScan()).created===1,'overdue verified presales creates one review');
 check((await runScan()).created===0,'unhandled review not duplicated');
 const r=await api.get('/rest/tasks',{query:{filter:'craReplyReviewOpportunityId[eq]:'+id,limit:200}});check(r.data.tasks.length===1,'one task uniquely references fixture');const task=r.data.tasks[0];
 const future=new Date(Date.now()+6*86400000).toISOString();
 await admin.patch('/rest/opportunities/'+id,{craReplyReviewAgreedAt:future});await runScan();
 const after=await api.get('/rest/tasks/'+task.id);check(Date.parse(after.data.task.dueAt)===Date.parse(future),'customer later appointment updates same task');
 await api.patch('/rest/tasks/'+task.id,{status:'DONE'});
 await admin.patch('/rest/opportunities/'+id,{craReplyReviewAgreedAt:null,craReplyReviewDecision:'DEFER',craReplyReviewNextAt:future});
 check((await runScan()).created===0,'resolved deferral waits for specified future date');
 return {checks,fixtureId:id,taskId:task.id,fixtureOnly:true,modelCalls:0};
};

