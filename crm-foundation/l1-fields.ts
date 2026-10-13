import {MetadataApiClient} from 'twenty-client-sdk/metadata';
export const main=async()=>{
 const c=new MetadataApiClient({url:'http://server:3000/metadata'});
 const op='bf0e1eb9-8d87-43f3-a379-84f07efaafd8';
 const defs=[
  {objectMetadataId:op,name:'craReplyReviewScope',label:'无回复复核适用范围',type:'SELECT',description:'人工核实；仅未付款售前询盘/报价适用，未知留空。付款/备货/运输/售后须排除。',options:[{id:'adac2ad4-a20c-550a-8043-9dbf5933090e',value:'UNPAID_PRESALES',label:'已核实未付款售前',position:0,color:'blue'},{id:'8ef2bd4e-786f-5fa3-ad09-70420483e6d2',value:'EXCLUDED',label:'已排除',position:1,color:'gray'}]},
  {objectMetadataId:op,name:'craReplyReviewAnchorAt',label:'客户有效回复起点',type:'DATE_TIME',description:'客户本次采购最后有效回复或首次明确询盘的实际时间。普通问候/卖方催问不重置，补导入不填今天。'},
  {objectMetadataId:op,name:'craReplyReviewEvidence',label:'有效回复日期依据',type:'TEXT',description:'本次采购、客户实际回复或首次询盘的原消息/人工核实依据。'},
  {objectMetadataId:op,name:'craReplyReviewAgreedAt',label:'客户约定联系时间',type:'DATE_TIME',description:'客户明确约定更晚日期时延后，不猜缺失日期。'},
  {objectMetadataId:op,name:'craReplyReviewDecision',label:'无回复复核处理',type:'SELECT',description:'人工决定；任务完成不等于输单。已人工转输单仅在经营者确实更新采购阶段后填写。',options:[{id:'59a1cb6f-f67c-59d1-9c31-65978b5e999d',value:'CONTINUE',label:'继续跟进',position:0,color:'green'},{id:'2fefec94-f291-5561-b1d6-7495c8aab4e7',value:'DEFER',label:'延期复核',position:1,color:'blue'},{id:'c6f12eb1-6278-5d04-87f1-fa39088474a9',value:'LOST_CONFIRMED',label:'已人工转输单',position:2,color:'red'}]},
  {objectMetadataId:op,name:'craReplyReviewNextAt',label:'复核后下次检查时间',type:'DATE_TIME',description:'人工选择继续/延期后指定新日期；没有日期不自动每30天重复提醒。'},
  {objectMetadataId:'a84be558-fe43-416d-8497-86b325f1398b',name:'craReplyReviewOpportunityId',label:'无回复复核商机编号',type:'TEXT',description:'复核任务对应商机UUID，正文链接商机，不是订单号。'}
 ];
 const out=[];
 for(const def of defs){const r=await c.mutation({createOneField:{__args:{input:{field:{...def,isActive:true,isSystem:false,isUIEditable:true,isUIReadOnly:false,isNullable:true,isUnique:false,isLabelSyncedWithName:false}}},id:true,name:true,type:true}});out.push(r.createOneField);}
 return {fields:out,businessRecordWrites:0};
};
