import {RestApiClient} from 'twenty-client-sdk/rest';
export const main=async()=>{const c=new RestApiClient({baseUrl:'http://server:3000'}); const id='baa3ae7b-1159-5542-ae85-e317e871da99';await c.patch('/rest/tasks/'+id,{status:'TODO',jianChaWanChengShiJian:null});await c.patch('/rest/tasks/'+id,{status:'DONE'});return{fixtureTask:id,replayed:true};};

