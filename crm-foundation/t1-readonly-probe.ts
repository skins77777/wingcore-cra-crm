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

export const main=async()=>{
 const c=new RestApiClient({baseUrl:'http://server:3000'});
 const get=async plural=>{let rows=[],cursor;for(let n=0;n<100;n++){const r=await c.get('/rest/'+plural,{query:{limit:200,...(cursor?{starting_after:cursor}:{})}});if(!Array.isArray(r?.data?.[plural]))throw new Error('Invalid '+plural);rows.push(...r.data[plural]);if(!r.pageInfo?.hasNextPage)return rows;if(!r.pageInfo.endCursor||cursor===r.pageInfo.endCursor)throw new Error('cursor');cursor=r.pageInfo.endCursor;}throw new Error('page bound');};
 const opportunities=await get('opportunities'),tasks=await get('tasks');
 const counts={};for(const o of opportunities){const p=plan(o,tasks,new Date().toISOString());counts[p.action]=(counts[p.action]||0)+1;}
 return {readOnly:true,opportunities:opportunities.length,decisions:counts,crmWrites:0,modelCalls:0};
};
