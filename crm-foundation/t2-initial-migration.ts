import { RestApiClient } from 'twenty-client-sdk/rest';
import { createHash } from 'node:crypto';

// Native Twenty Logic Function. No model, external service, or persistent API key.
const client = new RestApiClient({ baseUrl: 'http://server:3000' });
const ROOT = '/rest';
const LINES = [
  { code: 'purchase', label: '采购', done: 'caiGouZhunBeiWanCheng', agreed: 'caiGouYueDingJianChaShiJian', checked: 'caiGouZuiJinJianChaShiJian' },
  { code: 'logistics', label: '物流', done: 'wuLiuZhunBeiWanCheng', agreed: 'wuLiuYueDingJianChaShiJian', checked: 'wuLiuZuiJinJianChaShiJian' },
];
type RecordData = { [key: string]: any };
export const stableId = (key: string): string => {
  const hex = createHash('sha256').update(key).digest('hex').slice(0, 32);
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-5${hex.slice(13,16)}-a${hex.slice(17,20)}-${hex.slice(20)}`;
};
const stamp = (value: any): number => value ? Date.parse(value) : NaN;
const hkDay = (value: any): string => new Date(stamp(value) + 8 * 3600000).toISOString().slice(0,10);
export const plusTwoDays = (value: any): string => {
  const day = hkDay(value);
  return new Date(Date.parse(`${day}T15:59:00Z`) + 2 * 86400000).toISOString();
};
const prefix = (id: string, line: string) => `T2|${id}|${line}|`;
const completed = (tasks: RecordData[]) => tasks.filter(t => t.status === 'DONE' && !t.tiXingShiXiaoYuanYin && Number.isFinite(stamp(t.jianChaWanChengShiJian)))
  .sort((a,b) => stamp(b.jianChaWanChengShiJian)-stamp(a.jianChaWanChengShiJian) || b.id.localeCompare(a.id))[0];
export const plan = (order: RecordData, tasks: RecordData[], line: any, now: string): RecordData => {
  const own = tasks.filter(t => t.genJinDingDanId === order.id && t.tiXingQuChongJian?.startsWith(prefix(order.id,line.code)));
  const open = own.filter(t => t.status !== 'DONE');
  const paid = order.shouKuanHeShiZhuangTai === 'YUAN_DAN_QUAN_KUAN_YI_SHOU'
    && order.yuanDingDanJinE?.currencyCode === 'USD' && order.yiShouJinE?.currencyCode === 'USD'
    && Number(order.yuanDingDanJinE.amountMicros) > 0
    && Number(order.yiShouJinE.amountMicros) >= Number(order.yuanDingDanJinE.amountMicros);
  const stageAllows = order.shiJiLuYueZhuangTai === 'CAI_GOU_BEI_HUO'
    || (line.code === 'logistics' && order.shiJiLuYueZhuangTai === 'TUI_HUI_CHONG_FA_ZHUN_BEI');
  if (order[line.done] === true || !stageAllows || !paid) return { action:'stop', open, reason: order[line.done] ? `${line.label}准备已人工确认完成` : !stageAllows ? '实际履约阶段已离开本准备环节' : '全款核实条件不再成立' };
  const last = completed(own);
  const anchors = [order[line.checked],last?.jianChaWanChengShiJian].filter(x => Number.isFinite(stamp(x)));
  const checked = anchors.sort((a,b)=>stamp(b)-stamp(a))[0];
  const agreed = Number.isFinite(stamp(order[line.agreed])) && (!checked || stamp(order[line.agreed]) > stamp(checked)) ? order[line.agreed] : null;
  const anchor = checked || order.quanKuanDaoZhangShiJian;
  const dueAt = agreed || (Number.isFinite(stamp(anchor)) ? plusTwoDays(anchor) : null);
  if (open.length > 1) return {action:'blocked', reason:'同一准备线出现多个开放任务，需要人工核对', open};
  if (open.length) return {action:'keep', task:open[0], dueAt, checked, open};
  if (!dueAt) return {action:'blocked',reason:'缺少已核实到账日期或约定检查日期',open};
  if (hkDay(dueAt)>hkDay(now)) return {action:'future',dueAt,checked,open};
  const key = prefix(order.id,line.code)+(last?.id || 'initial');
  // A completed/cancelled round is never recreated. Reopening it is an explicit manual action.
  if (own.some(t=>t.tiXingQuChongJian===key)) return {action:'blocked',reason:'该轮次已存在历史任务，需人工核对',open};
  return {action:'create',key,id:stableId(key),dueAt,checked,open};
};
async function all(plural: string): Promise<RecordData[]> {
  const rows: RecordData[] = [];
  let after: string | undefined;
  for (let page=0;page<100;page++) {
    const response: any = await client.get(`${ROOT}/${plural}`,{query:{limit:200,...(after?{starting_after:after}:{})}});
    const batch=response?.data?.[plural];
    if (!Array.isArray(batch)) throw new Error(`Unexpected collection response: ${plural}`);
    rows.push(...batch);
    if (!response.pageInfo?.hasNextPage) return rows;
    const next=response.pageInfo.endCursor;
    if (!next || next===after) throw new Error(`Missing pagination cursor: ${plural}`);
    after=next;
  }
  throw new Error(`Pagination safety bound reached: ${plural}`);
}
async function one(plural:string,singular:string,id:string):Promise<RecordData> {
  const response:any=await client.get(`${ROOT}/${plural}/${id}`);
  const row=response?.data?.[singular];
  if (!row?.id) throw new Error(`Unexpected record response: ${singular}`);
  return row;
}
async function uniquePost(plural:string,singular:string,data:RecordData):Promise<void> {
  try { await client.post(`${ROOT}/${plural}`,data); }
  catch(error) {
    const existing=await one(plural,singular,data.id).catch(()=>null);
    if (!existing || (data.tiXingQuChongJian && existing.tiXingQuChongJian!==data.tiXingQuChongJian)) throw error;
  }
}
async function ensureTargets(task:RecordData,order:RecordData):Promise<void> {
  const existing=await all('taskTargets');
  for (const [kind,id] of [['targetDingDanId',order.id],['targetPersonId',order.keHuId]]) {
    if (!id) continue;
    if (existing.some(t=>t.taskId===task.id && t[kind as string]===id)) continue;
    await uniquePost('taskTargets','taskTarget',{id:stableId(`${task.id}|${kind}|${id}`),taskId:task.id,[kind as string]:id});
  }
}
export async function runScan(onlyOrderId?:string):Promise<object> {
  const now=new Date().toISOString();
  const orders=(await all('dingDans')).filter(o=>!onlyOrderId || o.id===onlyOrderId);
  const result:any={scanned:orders.length,created:0,kept:0,stopped:0,future:0,blocked:[]};
  for (const listed of orders) {
    for (const line of LINES) {
      // Re-read immediately before writes; field uniqueness protects creation races.
      const order=await one('dingDans','dingDan',listed.id);
      const tasks=await all('tasks');
      const decision=plan(order,tasks,line,now);
      if (decision.action==='stop') {
        for (const listedTask of decision.open) {
          const current=await one('tasks','task',listedTask.id);
          if (current.status==='DONE') continue;
          await client.patch(`${ROOT}/tasks/${current.id}`,{status:'DONE',tiXingShiXiaoYuanYin:decision.reason});
          result.stopped++;
        }
        continue;
      }
      if (decision.action==='blocked') {result.blocked.push({orderId:order.id,line:line.label,reason:decision.reason});continue;}
      if (decision.checked && order[line.checked]!==decision.checked) await client.patch(`${ROOT}/dingDans/${order.id}`,{[line.checked]:decision.checked});
      if (decision.action==='future') {result.future++;continue;}
      if (decision.action==='keep') {
        const task=await one('tasks','task',decision.task.id);
        if (task.status==='DONE') continue;
        if (decision.dueAt && task.dueAt!==decision.dueAt) await client.patch(`${ROOT}/tasks/${task.id}`,{dueAt:decision.dueAt});
        await ensureTargets(task,order);
        result.kept++;continue;
      }
      const person=order.keHuId?await one('people','person',order.keHuId):null;
      if (!person?.keHuFuZeRenId) {result.blocked.push({orderId:order.id,line:line.label,reason:'客户负责人未指定'});continue;}
      const description=line.code==='purchase'
        ? '人工比价、核实库存、同行调货或生产交期；货物确实准备好且供应商确认可交接后，再勾选订单的采购准备完成。'
        : '人工确认货代、敏感货承运、费用、收货及交接安排；全部确认后，再勾选订单的物流准备完成。';
      const task={id:decision.id,title:`${order.name}：${line.label}准备检查`,status:'TODO',dueAt:decision.dueAt,assigneeId:person.keHuFuZeRenId,
        genJinDingDanId:order.id,tiXingQuChongJian:decision.key,
        bodyV2:{markdown:`${description}\n\n检查后在任务正文记录结果、下一步和约定日期，再将任务设为完成。完成检查不等于准备完成。若继续等待，无约定日期时从本次检查完成日加两天。\n\n提醒只在CRM内部展示，不自动联系客户或供应商。`}};
      await uniquePost('tasks','task',task);
      await ensureTargets(task,order);
      result.created++;
    }
  }
  return result;
}

const knownIds = ["8902baa6-3725-4a7b-abb8-7e6602c38a65","9b6b0841-81fa-4cb5-90d6-8cca56fea005","01575040-e62b-47a2-9d17-52b24313f75e","e99efab0-4179-45a4-ab36-c7e8e62ed1d8","5e3bb9e5-25c0-4665-8715-f54b75f871c0","268e8444-523a-4182-adf0-1070e02f13e0","33ddefd4-851b-42d8-ba7f-2590be5894fd","1a172e74-1f77-4d96-845b-0397d1cc5068","88ee38ed-2319-4793-bc9a-3b3b950f9ce3","b2bb50c4-6378-4b82-b399-da227ce32b99"];
export const main = async ():Promise<object> => {
 for(const id of knownIds) await client.patch('/rest/dingDans/'+id,{caiGouZhunBeiWanCheng:false,wuLiuZhunBeiWanCheng:false});
 const id='b2bb50c4-6378-4b82-b399-da227ce32b99';
 await client.patch('/rest/dingDans/'+id,{wuLiuYueDingJianChaShiJian:'2026-10-12T15:59:00Z'});
 const taskId='85921b66-cea9-4b2f-91f6-4d598d28f807';
 await client.patch('/rest/tasks/'+taskId,{genJinDingDanId:id,tiXingQuChongJian:'T2|'+id+'|logistics|initial'});
 await ensureTargets(await one('tasks','task',taskId),await one('dingDans','dingDan',id));
 const verified=[]; for(const knownId of knownIds) { await client.patch('/rest/dingDans/'+knownId,{caiGouZhunBeiWanCheng:false,wuLiuZhunBeiWanCheng:false}); const r=await one('dingDans','dingDan',knownId); verified.push({id:knownId,purchase:r.caiGouZhunBeiWanCheng,logistics:r.wuLiuZhunBeiWanCheng}); } return {verified,adoptedExistingTask:taskId,createdBusinessTasks:0};
};

