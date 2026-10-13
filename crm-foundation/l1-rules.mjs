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
