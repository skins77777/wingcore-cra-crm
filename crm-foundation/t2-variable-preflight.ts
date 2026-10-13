import { MetadataApiClient } from 'twenty-client-sdk/metadata';
export const main = async () => {
 const c = new MetadataApiClient({url:'http://server:3000/metadata'});
 const r = await c.query({exportApplication:{__args:{universalIdentifier:'f9fad091-c5ba-4257-af6f-00fac4a5f4d4'},manifest:true}});
 const m=r.exportApplication.manifest;
 return {application:m.application, keys:Object.keys(m), variableDefinitions:m.application.applicationVariables, counts:Object.fromEntries(Object.entries(m).filter(([k,v])=>Array.isArray(v)).map(([k,v])=>[k,(v as any[]).length]))};
};

