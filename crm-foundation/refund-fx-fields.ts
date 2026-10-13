import {MetadataApiClient} from 'twenty-client-sdk/metadata';
export const main=async()=>{
 const c=new MetadataApiClient({url:'http://server:3000/metadata'});
 const order='eaf59e23-630e-49e0-9284-bd0f542ce217',change='96ff19f0-0533-4f74-9f4f-1806498d5ef2';
 const fields=[
 {objectMetadataId:order,name:'tuiKuanHeShi',label:'退款核实',type:'SELECT',description:'人工核实；未登记不等于确认无退款。部分退款保次数；取消且全额退款才撤出成功次数。',options:[{id:'947f78e6-b4bf-41d0-9a70-a4aebc7b9a70',value:'WU_TUI_KUAN',label:'已核实无退款',position:0,color:'green'},{id:'c53a724a-836c-4b3b-93ca-fcb764048edd',value:'DAI_HE_SHI',label:'退款待核实',position:1,color:'orange'},{id:'c294c127-c4cf-413a-b350-865f95bf7489',value:'BU_FEN_YI_HE_SHI',label:'部分退款已核实',position:2,color:'blue'},{id:'8239dbae-c665-4682-9a1d-11e6baf74616',value:'QUAN_E_YI_HE_SHI',label:'全额退款已核实',position:3,color:'red'}]},
 {objectMetadataId:order,name:'tuiKuanShangPin',label:'退款商品金额',type:'CURRENCY',description:'累计已核实退还的商品金额，USD；不覆盖原价。'},
 {objectMetadataId:order,name:'tuiKuanYunFei',label:'退款运费金额',type:'CURRENCY',description:'累计已核实退还的运费，USD；未知留空。'},
 {objectMetadataId:order,name:'tuiKuanShiFu',label:'退款实际支出',type:'CURRENCY',description:'累计实际退还客户的USD，和约定退款金额分开核实。'},
 {objectMetadataId:order,name:'tuiKuanQueRenShiJian',label:'退款核实时间',type:'DATE_TIME',description:'人工完成核实的时间，不代执行退款。'},
 {objectMetadataId:change,name:'guDingJieSuanHuiLv',label:'固定结算汇率',type:'NUMBER',settings:{decimals:6},description:'1 USD对应CNY。结算/比较时人工确认，保存后不随每日汇率刷新改写。'},
 {objectMetadataId:change,name:'guDingHuiLvRiQi',label:'固定汇率日期',type:'DATE',description:'所用汇率的数据日期；历史日期未知留空，不补今天。'},
 {objectMetadataId:change,name:'guDingHuiLvLaiYuan',label:'固定汇率来源',type:'TEXT',description:'所用快照来源或实际结算凭证说明。'},
 {objectMetadataId:change,name:'shiJiJieSuanCny',label:'实际结算人民币',type:'CURRENCY',cny:true,description:'实际结汇或结算已核实CNY；未结汇留空，不能填参考换算。'},
 {objectMetadataId:change,name:'jieSuanBeiZhu',label:'结算与退款备注',type:'TEXT',description:'人工确认的历史结算依据及更正原因。'}
 ];
 const existing=await c.query({fields:{edges:{node:{id:true,name:true,objectMetadataId:true}}}});
 const nodes=existing.fields.edges.map(e=>e.node),out=[];
 for(const def of fields){
  const old=nodes.find(n=>n.name===def.name&&n.objectMetadataId===def.objectMetadataId);
  if(old){out.push({...old,reused:true});continue;}
  const {cny,...field}=def;
  const input={...field,isActive:true,isSystem:false,isUIEditable:true,isUIReadOnly:false,isNullable:true,isUnique:false,isLabelSyncedWithName:false,
   ...(def.type==='CURRENCY'?{settings:{format:'full',decimals:2},defaultValue:{amountMicros:null,currencyCode:cny?"'CNY'":"'USD'"}}:{})};
  const result=await c.mutation({createOneField:{__args:{input:{field:input}},id:true,name:true,label:true,type:true,objectMetadataId:true}});
  out.push(result.createOneField);
 }
 return {fields:out,businessRecordWrites:0};
};
