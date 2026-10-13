export const main=async()=>{
 const api=new RestApiClient({baseUrl:'http://server:3000',token:process.env.CRA_T1_API_KEY});
 const id='48bf7b49-8f2e-5f5b-bdd7-a50bbf37b90a';const checks=[];
 const check=(v,label)=>{if(!v)throw new Error(label);checks.push(label);};
 const r=await api.get('/rest/tasks',{query:{filter:'craT1OpportunityId[eq]:'+id,limit:200}});const tasks=r.data.tasks;
 const q1=tasks.filter(t=>t.tiXingQuChongJian.includes('|TEST-Q1|'));
 check(q1.length===3&&q1.every(t=>t.status==='DONE'&&!!t.jianChaWanChengShiJian),'three completed reminders in original round');
 const q2=tasks.filter(t=>t.tiXingQuChongJian.includes('|TEST-Q2|'));
 check(q2.length===1&&q2[0].status==='DONE'&&!!q2[0].tiXingShiXiaoYuanYin&&!q2[0].jianChaWanChengShiJian,'new quote round stopped without false completion');
 check((await runScan()).created===0,'stopped round does not recreate');
 let forbidden=false;try{await api.patch('/rest/opportunities/'+id,{name:'TEST｜T1报价提醒验收｜非业务'});}catch(e){forbidden=(e.status===403||e.body?.code==='PERMISSION_DENIED');}
 check(forbidden,'opportunity updates denied');
 let denied=false;try{await api.get('/rest/dingDans');}catch(e){denied=(e.status===403||e.body?.code==='PERMISSION_DENIED');}
 check(denied,'orders access denied');
 return {checks,fixtureId:id,fixtureTaskIds:tasks.map(t=>t.id),modelCalls:0};
};

