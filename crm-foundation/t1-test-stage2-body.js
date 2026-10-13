export const main=async()=>{
 const admin=new RestApiClient({baseUrl:'http://server:3000'});
 const api=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 const id='48bf7b49-8f2e-5f5b-bdd7-a50bbf37b90a';const checks=[];
 const check=(v,label)=>{if(!v)throw new Error(label);checks.push(label);};
 const list=async()=>{const r=await api.get('/rest/tasks',{query:{filter:'craT1OpportunityId[eq]:'+id,limit:200}});return r.data.tasks;};
 const get=async taskId=>(await api.get('/rest/tasks/'+taskId)).data.task;
 const wait=async(taskId,predicate)=>{for(let n=0;n<30;n++){const t=await get(taskId);if(predicate(t))return t;await new Promise(r=>setTimeout(r,100));}throw new Error('Native event not recorded');};
 let tasks=await list();const first=tasks.find(t=>t.tiXingQuChongJian==='T1|'+id+'|TEST-Q1|1');
 check(first.status==='DONE'&&Number.isFinite(stamp(first.jianChaWanChengShiJian)),'native completion time exists');
 check((await runScan()).created===0,'completed check waits three HK dates');
 await api.patch('/rest/tasks/'+first.id,{status:'TODO'});await wait(first.id,t=>t.jianChaWanChengShiJian===null);
 check((await get(first.id)).jianChaWanChengShiJian===null,'reopening clears obsolete completion timestamp');
 await api.patch('/rest/tasks/'+first.id,{status:'DONE'});await wait(first.id,t=>!!t.jianChaWanChengShiJian);
 const threeDaysAgo=new Date(Date.now()-3*86400000).toISOString();
 await api.patch('/rest/tasks/'+first.id,{jianChaWanChengShiJian:threeDaysAgo});
 check((await runScan()).created===1,'second reminder after completed-date plus three');
 tasks=await list();const second=tasks.find(t=>t.tiXingQuChongJian==='T1|'+id+'|TEST-Q1|2');
 await api.patch('/rest/tasks/'+second.id,{status:'DONE'});await wait(second.id,t=>!!t.jianChaWanChengShiJian);
 await api.patch('/rest/tasks/'+second.id,{jianChaWanChengShiJian:threeDaysAgo});
 check((await runScan()).created===1,'third reminder can be created');
 tasks=await list();const third=tasks.find(t=>t.tiXingQuChongJian==='T1|'+id+'|TEST-Q1|3');
 await api.patch('/rest/tasks/'+third.id,{status:'DONE'});await wait(third.id,t=>!!t.jianChaWanChengShiJian);
 check((await runScan()).created===0,'no fourth reminder in same quote round');
 const past=new Date(Date.now()-3*86400000).toISOString();
 await admin.patch('/rest/opportunities/'+id,{craT1QuoteRound:'TEST-Q2',craT1QuoteSentAt:past});
 check((await runScan()).created===1,'new sent quote opens another round');
 tasks=await list();const active=tasks.find(t=>t.tiXingQuChongJian==='T1|'+id+'|TEST-Q2|1');
 await admin.patch('/rest/opportunities/'+id,{craT1StopReason:'合成测试：客户确认下单'});
 await runScan();const stopped=await get(active.id);
 check(stopped.status==='DONE'&&!!stopped.tiXingShiXiaoYuanYin&&stopped.jianChaWanChengShiJian===null,'confirmed order stops reminder without false completion');
 check((await runScan()).created===0,'stopped round never recreates reminder');
 let forbidden=false;try{await api.patch('/rest/opportunities/'+id,{name:'TEST｜T1报价提醒验收｜非业务'});}catch(e){forbidden=(e.status===403||e.body?.code==='PERMISSION_DENIED');}
 check(forbidden,'restricted credential cannot update opportunity');
 let denied=false;try{await api.get('/rest/dingDans');}catch(e){denied=(e.status===403||e.body?.code==='PERMISSION_DENIED');}
 check(denied,'restricted credential cannot read orders');
 return {checks,fixtureId:id,fixtureTaskIds:(await list()).map(t=>t.id),timeSimulation:'only synthetic fixture timestamps',modelCalls:0};
};

