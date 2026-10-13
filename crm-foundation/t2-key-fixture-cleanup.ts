import { RestApiClient } from 'twenty-client-sdk/rest';
// One-off cleanup with the signed-in operator's delegated identity; never deploy as a cron.
export const main = async () => {
 const c=new RestApiClient({baseUrl:'http://server:3000'});
 const id='943edb71-e1bc-4c49-809d-95c8865026bc';
 const ids=['bdaceed6-c7d1-59e1-a06e-9a8328f67c52','9e9a6e75-75e7-56c4-a5f2-b56b195b28bc','7c121dfa-ca2e-56ea-a16d-74b233df9224'];
 for(const taskId of ids) {
  const r=await c.get('/rest/tasks/'+taskId); const t=r.data.task;
  if(t.genJinDingDanId!==id) throw new Error('Cleanup target mismatch');
  if(t.tiXingShiXiaoYuanYin && t.jianChaWanChengShiJian) throw new Error('Obsolete task incorrectly marked as actual completed check');
 }
 const order=(await c.get('/rest/dingDans/'+id)).data.dingDan;
 if(order.aLiDingDanHao!=='TEST-T2-20261011-03') throw new Error('Cleanup order mismatch');
 for(const taskId of ids) await c.delete('/rest/tasks/'+taskId,{query:{soft_delete:true}});
 await c.delete('/rest/dingDans/'+id,{query:{soft_delete:true}});
 return {obsoleteEventsIgnored:true,softDeletedTasks:ids.length,softDeletedOrder:id};
};
