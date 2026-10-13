import { MetadataApiClient } from 'twenty-client-sdk/metadata';
export const main = async () => {
 const c = new MetadataApiClient({url:'http://server:3000/metadata'});
 const r = await c.query({exportApplication:{__args:{universalIdentifier:'f9fad091-c5ba-4257-af6f-00fac4a5f4d4'},manifest:true}});
 const original=r.exportApplication.manifest;
 const m={...original,application:{...original.application,defaultRoleUniversalIdentifier:null,applicationVariables:{CRA_T2_API_KEY:{universalIdentifier:'f7ef7778-cbed-4803-a628-17177bd9be37',label:'T2后台提醒密钥',description:'仅用于采购与物流准备提醒；受限API角色。',isSecret:true,isRequired:true,type:'TEXT'}}}};
 for(const k of Object.keys(m)) if(Array.isArray(m[k])) m[k]=[];
 const applied = await c.mutation({syncApplication:{__args:{manifest:m,dryRun:false,inferDeletionFromMissingEntities:false},applicationUniversalIdentifier:true,actions:true}});
 return {changes:applied.syncApplication.actions.map((a:any)=>({type:a.type,metadataName:a.metadataName,key:a.flatEntity?.key,isSecret:a.flatEntity?.isSecret}))};
};


