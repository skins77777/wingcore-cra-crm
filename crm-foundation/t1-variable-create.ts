import {MetadataApiClient} from 'twenty-client-sdk/metadata';
export const main=async()=>{
 const c=new MetadataApiClient({url:'http://server:3000/metadata'});
 const r=await c.query({exportApplication:{__args:{universalIdentifier:'f9fad091-c5ba-4257-af6f-00fac4a5f4d4'},manifest:true}});
 const old=r.exportApplication.manifest;
 const m={...old,application:{...old.application,applicationVariables:{...old.application.applicationVariables,
  CRA_T1_API_KEY:{universalIdentifier:'966f1f93-ab73-5035-b53b-dff0032645ea',label:'报价跟进后台密钥',description:'T1报价跟进专用；人员/商机只读，任务读写。',isSecret:true,isRequired:true,type:'TEXT'}}}};
 for(const k of Object.keys(m))if(Array.isArray(m[k]))m[k]=[];
 const preview=await c.mutation({syncApplication:{__args:{manifest:m,dryRun:true,inferDeletionFromMissingEntities:false},actions:true}});
 const changes=preview.syncApplication.actions;
 if(changes.some(a=>a.metadataName!=='applicationVariable'||a.type!=='create'||a.flatEntity?.key!=='CRA_T1_API_KEY'))throw new Error('Unexpected application change');
 if(!changes.length)return {reused:true};
 const done=await c.mutation({syncApplication:{__args:{manifest:m,dryRun:false,inferDeletionFromMissingEntities:false},actions:true}});
 return {changes:done.syncApplication.actions.map(a=>({type:a.type,metadataName:a.metadataName,key:a.flatEntity?.key,isSecret:a.flatEntity?.isSecret})),defaultRoleChanged:false};
};
