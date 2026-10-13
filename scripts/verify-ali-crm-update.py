import importlib.util,json,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import ali_export_reader as a
d=a.DATA/'crm-update-2026-10-12'
before=json.loads((d/'before.json').read_text(encoding='utf-8'));after=a.read_crm()
a.atomic(d/'after.json',after)
allowed={'pingTaiZhuangTai','shangPinMingXi','shiShiYuLaiYuan','yiQueRenYunFeiAmountMicros','yiQueRenYunFeiCurrencyCode'}
metadata={'updatedAt','updatedBySource','updatedByWorkspaceMemberId','updatedByName','updatedByContext','searchVector'}
new={o['id']:o for o in after['orders']}
for o in before['orders']:
    assert all(new[o['id']].get(k)==v for k,v in o.items() if k not in allowed|metadata)
people={p['id']:p for p in after['people']}
for p in before['people']:
    assert all(people[p['id']].get(k)==v for k,v in p.items() if k not in {'emailsPrimaryEmail'}|metadata)
assert len(new)==12 and len(people)==12
assert len({o['aLiDingDanHao'] for o in new.values()})==12
spec=importlib.util.spec_from_file_location('report',a.ROOT/'crm-foundation/order-report.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
raw=r.read_crm();result=r.calculate(raw,{'rate':'7'})
assert len(result['sourceOnly'])==2
assert result['groups']['all']['count']==10
assert result['groups']['success']['count']==6
assert result['groups']['all']['base']['known']=='10938.53'
assert result['groups']['all']['received']['known']=='7936.53'
assert result['groups']['all']['pending']['known']=='10.00'
c=raw['changes'][0]
assert c['id']=='e11b68d6-5d96-4286-8d2e-f169f996c800' and c['decision']=='GOU_TONG_ZHONG' and c['received']=='0'
# Lifecycle or cash evidence prevents platform-only exclusion.
for field,value in [('status','YUN_SHU_JIAO_JIE_ZHONG'),('received','1000000'),('receiptStatus','BU_FEN_YI_SHOU')]:
    test=copy.deepcopy(raw);target=next(o for o in test['orders'] if o['number']=='318659674001022131');target[field]=value
    assert len(r.calculate(test,{'rate':'7'})['sourceOnly'])==1
evidence={'orders_updated':10,'customer_emails_added':4,'customers_created':1,'orders_created':2,
          'unique_order_count':12,'business_order_count':10,'success_count':6,
          'base_usd':'10938.53','received_usd':'7936.53','pending_supplement_usd':'10.00',
          'protected_existing_fields_unchanged':True,'source_only_exclusion_tests':4,
          'automatic_folder_reader':'read_only','model_calls':0}
a.atomic(d/'verification.json',evidence)
print(json.dumps(evidence))
