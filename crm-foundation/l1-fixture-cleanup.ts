import {RestApiClient} from 'twenty-client-sdk/rest';
export const main=async()=>{
 const c=new RestApiClient({baseUrl:'http://server:3000'});
 const id='73779383-9e27-5e0f-9b74-c7fb685e646b';
 const ids=["6f5665f0-2cbd-5a94-a2bb-c4b60c4c10e6","b8812262-8cd9-52a3-ab89-fc4b2c595b7b","cde270f7-d4fc-5ca7-ab21-2aaad8d5a009"];
 const o:any=await c.get('/rest/opportunities/'+id);
 if(o.data.opportunity.name!=='TEST｜L1无回复复核｜非业务')throw new Error('Fixture mismatch');
 for(const taskId of ids){const r:any=await c.get('/rest/tasks/'+taskId);if(r.data.task.craReplyReviewOpportunityId!==id||!r.data.task.tiXingQuChongJian?.startsWith('L1|'+id+'|'))throw new Error('Task mismatch');}
 for(const taskId of ids)await c.delete('/rest/tasks/'+taskId,{query:{soft_delete:true}});
 await c.delete('/rest/opportunities/'+id,{query:{soft_delete:true}});
 return {softDeletedTasks:ids.length,softDeletedOpportunity:id,recoverable:true};
};
