import {RestApiClient} from 'twenty-client-sdk/rest';
export const main=async(params:{taskId:string;completedAt:string})=>{
 if(!process.env.CRA_T1_API_KEY)throw new Error('报价提醒专用后台凭据尚未配置');
 const c=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 if(!params?.taskId)return {ignored:'missing task id'};
 const r:any=await c.get('/rest/tasks/'+params.taskId);const t=r?.data?.task;
 if(!t?.tiXingQuChongJian?.startsWith('T1|'))return {ignored:'not T1'};
 if(t.tiXingShiXiaoYuanYin)return {ignored:'obsolete reminder'};
 if(t.status!=='DONE'){
  if(t.jianChaWanChengShiJian)await c.patch('/rest/tasks',{jianChaWanChengShiJian:null},{query:{filter:'and(id[eq]:'+t.id+',updatedAt[eq]:'+t.updatedAt+')'}});
  return {ignored:'not completed'};
 }
 if(t.jianChaWanChengShiJian)return {ignored:'already recorded'};
 if(!params.completedAt||!Number.isFinite(Date.parse(params.completedAt)))throw new Error('Missing native completion event time');
 await c.patch('/rest/tasks',{jianChaWanChengShiJian:params.completedAt},{query:{filter:'and(id[eq]:'+t.id+',updatedAt[eq]:'+t.updatedAt+')'}});
 const a:any=await c.get('/rest/tasks/'+t.id);
 if(a?.data?.task?.jianChaWanChengShiJian!==params.completedAt)throw new Error('Completion readback mismatch');
 return {taskId:t.id,completedAt:params.completedAt};
};
