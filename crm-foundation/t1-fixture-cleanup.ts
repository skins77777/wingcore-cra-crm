import {RestApiClient} from 'twenty-client-sdk/rest';
export const main=async()=>{
 const c=new RestApiClient({baseUrl:'http://server:3000'});
 const id='48bf7b49-8f2e-5f5b-bdd7-a50bbf37b90a';
 const ids=['c3033c49-8030-5a0c-ae27-cab5fe7485e4','c988199d-8427-5251-a026-f598ead5e9ca','088511c8-b60f-56ba-a64b-73f88f42064e','7e8d8042-5769-5154-a266-d2589e167797'];
 const o:any=await c.get('/rest/opportunities/'+id);
 if(o.data.opportunity.name!=='TEST｜T1报价提醒验收｜非业务')throw new Error('Fixture mismatch');
 for(const taskId of ids){const r:any=await c.get('/rest/tasks/'+taskId);if(r.data.task.craT1OpportunityId!==id||!r.data.task.tiXingQuChongJian?.startsWith('T1|'+id+'|TEST-Q'))throw new Error('Task target mismatch');}
 for(const taskId of ids)await c.delete('/rest/tasks/'+taskId,{query:{soft_delete:true}});
 await c.delete('/rest/opportunities/'+id,{query:{soft_delete:true}});
 return {softDeletedTasks:ids.length,softDeletedOpportunity:id,recoverable:true};
};
