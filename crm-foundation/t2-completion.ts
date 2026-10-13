import { RestApiClient } from 'twenty-client-sdk/rest';
// Inputs bind to native task update event: after.id and after.updatedAt.
export const main = async (params: { taskId: string; completedAt: string }):Promise<object> => {
  if (!params?.taskId) return {ignored:'missing task event id'};
  if (!process.env.CRA_T2_API_KEY) throw new Error('T2后台凭据尚未配置；不能记录自动完成时间');
  const client=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T2_API_KEY});
  let response:any; try { response=await client.get(`/rest/tasks/${params.taskId}`); } catch(e:any) { throw new Error(JSON.stringify({message:e.message,body:e.body,status:e.status})); }
  const task=response?.data?.task;
  if (!task || !task.tiXingQuChongJian?.startsWith('T2|')) return {ignored:'not T2'};
  if (task.tiXingShiXiaoYuanYin) return {ignored:'obsolete reminder, not an actual check'};
  if (task.status!=='DONE') {
    if (task.jianChaWanChengShiJian) await client.patch(`/rest/tasks/${task.id}`,{jianChaWanChengShiJian:null});
    return {ignored:'not completed'};
  }
  if (task.jianChaWanChengShiJian) return {ignored:'completion timestamp already saved'};
  if (!Number.isFinite(Date.parse(params.completedAt))) throw new Error('Missing actual task update event time');
  try { await client.patch(`/rest/tasks/${task.id}`,{jianChaWanChengShiJian:params.completedAt}); } catch(e:any) { throw new Error(JSON.stringify({message:e.message,body:e.body,status:e.status,completedAt:params.completedAt})); }
  return {taskId:task.id,completedAt:params.completedAt};
};




