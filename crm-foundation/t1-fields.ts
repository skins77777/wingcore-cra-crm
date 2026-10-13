import { MetadataApiClient } from 'twenty-client-sdk/metadata';
export const main=async()=>{
 const c=new MetadataApiClient({url:'http://server:3000/metadata'});
 const opportunity='bf0e1eb9-8d87-43f3-a379-84f07efaafd8';
 const defs=[
  {objectMetadataId:opportunity,name:'craT1QuoteRound',label:'报价轮次',type:'TEXT',description:'每次新版商品报价实际发送后填写唯一版本；仅运费补充不新开轮。'},
  {objectMetadataId:opportunity,name:'craT1QuoteSentAt',label:'报价实际发送时间',type:'DATE_TIME',description:'实际发给本次采购客户的报价时间；草稿或示例不填。未知留空。'},
  {objectMetadataId:opportunity,name:'craT1QuoteEvidence',label:'报价发送依据',type:'TEXT',description:'已发送商品报价的渠道、消息或人工核实依据。'},
  {objectMetadataId:opportunity,name:'craT1AgreedAt',label:'报价约定跟进时间',type:'DATE_TIME',description:'客户明确约定的下次跟进日期/时间，优先于默认节奏；未知留空。'},
  {objectMetadataId:opportunity,name:'craT1FollowedAt',label:'本轮实际跟进时间',type:'DATE_TIME',description:'实际询问本次报价反馈或采购决定的时间；普通问候不算。新报价轮次不复用旧时间。'},
  {objectMetadataId:opportunity,name:'craT1StopReason',label:'本轮停止跟进原因',type:'TEXT',description:'明确确认下单、取消或人工停止时填写；新商品报价实际发出才可清空并开启新轮。'},
  {objectMetadataId:'a84be558-fe43-416d-8497-86b325f1398b',name:'craT1OpportunityId',label:'报价跟进商机编号',type:'TEXT',description:'T1专用商机UUID；任务正文提供商机链接；不作为订单号。'}
 ];
 const old=await c.query({fields:{edges:{node:{id:true,name:true,type:true,objectMetadataId:true}}}});
 const result=[];
 for(const def of defs){
  const existing=old.fields.edges.find(e=>e.node.name===def.name&&e.node.objectMetadataId===def.objectMetadataId)?.node;
  if(existing){if(existing.type!==def.type)throw new Error('Field type conflict: '+def.name);result.push({...existing,reused:true});continue;}
  const r=await c.mutation({createOneField:{__args:{input:{field:{...def,isActive:true,isSystem:false,isUIEditable:true,isUIReadOnly:false,isNullable:true,isUnique:false,isLabelSyncedWithName:false}}},id:true,name:true,type:true,objectMetadataId:true}});
  result.push(r.createOneField);
 }
 return {fields:result,businessRecordWrites:0};
};
