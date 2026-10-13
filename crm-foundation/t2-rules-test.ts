import { createHash } from 'node:crypto';

// Native Twenty Logic Function. No model, external service, or persistent API key.
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

import assert from 'node:assert/strict';
const now='2026-10-11T06:00:00Z';
const paid={id:'order',shouKuanHeShiZhuangTai:'YUAN_DAN_QUAN_KUAN_YI_SHOU',yuanDingDanJinE:{currencyCode:'USD',amountMicros:1000000},yiShouJinE:{currencyCode:'USD',amountMicros:1000000},shiJiLuYueZhuangTai:'CAI_GOU_BEI_HUO',quanKuanDaoZhangShiJian:'2026-10-09T01:00:00Z'};
let passed=0;
function check(name:string,actual:any,expected:any){assert.deepEqual(actual,expected,name);passed++;console.log('PASS '+name);}
check('Hong Kong natural day +2, end of day',plusTwoDays('2026-10-09T23:30:00Z'),'2026-10-12T15:59:00.000Z');
check('paid and due creates',plan(paid,[],LINES[0],now).action,'create');
check('unverified never procures',plan({...paid,shouKuanHeShiZhuangTai:'WEI_HE_SHI'},[],LINES[0],now).action,'stop');
check('short payment never procures',plan({...paid,yiShouJinE:{currencyCode:'USD',amountMicros:500000}},[],LINES[0],now).action,'stop');
check('missing receipt date blocked',plan({...paid,quanKuanDaoZhangShiJian:null},[],LINES[0],now).action,'blocked');
check('agreed date overrides fallback',plan({...paid,caiGouYueDingJianChaShiJian:'2026-10-14T15:59:00Z'},[],LINES[0],now).action,'future');
const task={id:'task',genJinDingDanId:'order',tiXingQuChongJian:'T2|order|purchase|initial',status:'TODO',dueAt:'2026-10-11T15:59:00Z'};
check('unfinished task retained without duplicate',plan(paid,[task],LINES[0],now).action,'keep');
check('date change updates original task',plan({...paid,caiGouYueDingJianChaShiJian:'2026-10-15T15:59:00Z'},[task],LINES[0],now).dueAt,'2026-10-15T15:59:00Z');
const done={...task,status:'DONE',jianChaWanChengShiJian:'2026-10-11T01:00:00Z'};
check('completed check repeats +2',plan(paid,[done],LINES[0],now).dueAt,'2026-10-13T15:59:00.000Z');
check('completion is not preparation finish',plan(paid,[done],LINES[0],'2026-10-13T02:00:00Z').action,'create');
check('purchase completion stops only purchase',plan({...paid,caiGouZhunBeiWanCheng:true},[task],LINES[0],now).action,'stop');
check('logistics remains independent',plan({...paid,caiGouZhunBeiWanCheng:true},[],LINES[1],now).action,'create');
check('delivered stops',plan({...paid,shiJiLuYueZhuangTai:'KE_HU_AN_QUAN_SHOU_HUO'},[task],LINES[0],now).action,'stop');
check('cancelled stops',plan({...paid,shiJiLuYueZhuangTai:'YI_QU_XIAO'},[task],LINES[0],now).action,'stop');
check('returned retail does not restart procurement',plan({...paid,shiJiLuYueZhuangTai:'TUI_HUI_CHONG_FA_ZHUN_BEI'},[],LINES[0],now).action,'stop');
check('returned retail can prepare logistics',plan({...paid,shiJiLuYueZhuangTai:'TUI_HUI_CHONG_FA_ZHUN_BEI'},[],LINES[1],now).action,'create');
check('multiple open tasks fail closed',plan(paid,[task,{...task,id:'other'}],LINES[0],now).action,'blocked');
check('same round generates same key and UUID',stableId(plan(paid,[],LINES[0],now).key),stableId(plan(paid,[],LINES[0],now).key));
console.log(JSON.stringify({passed}));
