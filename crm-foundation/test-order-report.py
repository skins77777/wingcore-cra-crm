import copy, json
from decimal import Decimal
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('report',Path(__file__).with_name('order-report.py'))
module=module_from_spec(spec);spec.loader.exec_module(module)
raw=module.read_crm();fx={'rate':'6.706851'}
base=module.calculate(raw,fx);results=[]
def check(name,passed):
    assert passed,name
    results.append({'name':name,'passed':True})
check('10 unique orders, six safe deliveries',base['groups']['all']['count']==10 and base['groups']['success']['count']==6)
check('Authoritative base amount',base['groups']['all']['base']['known']=='10938.53')
check('Unknown cash is not zero',base['groups']['all']['received']['known']=='328.53' and base['groups']['all']['received']['unknown']==7)
check('Unknown freight is not inferred',base['groups']['all']['freight']['unknown']==10)
check('Pending USD10 excluded from total',base['groups']['all']['effective']['known']=='10938.53' and base['groups']['all']['pending']['known']=='10.00')
duplicated=copy.deepcopy(raw);duplicated['orders']+=copy.deepcopy(raw['orders']);duplicated['changes']+=copy.deepcopy(raw['changes'])
check('Replay does not duplicate',module.calculate(duplicated,fx)['groups']==base['groups'])
accepted=copy.deepcopy(raw);accepted['changes'][0]['decision']='YI_TONG_YI'
r=module.calculate(accepted,fx)
check('Agreement changes price, not cash',r['groups']['all']['effective']['known']=='10948.53' and r['groups']['all']['received']['known']=='328.53')
paid=copy.deepcopy(accepted);paid['changes'][0]['received']='10000000';r=module.calculate(paid,fx)
check('Verified extra counted once',r['groups']['all']['received']['known']=='338.53' and r['groups']['all']['count']==10)
unknown=copy.deepcopy(raw);unknown['changes'][0]['received']=None;r=module.calculate(unknown,fx)
check('Unknown supplemental receipt stays unknown',r['groups']['all']['received']['unknown']==8 and r['groups']['all']['extraReceived']['unknown']==1)
corrected=copy.deepcopy(raw);corrected['orders'][0]['base']='100000000';r=module.calculate(corrected,fx)
expected=Decimal(base['groups']['all']['base']['known'])-Decimal(raw['orders'][0]['base'])/1000000+100
check('Correction recomputes without count drift',r['groups']['all']['base']['known']==module.formatted(expected) and r['groups']['all']['count']==10)
cancelled=copy.deepcopy(raw);cancelled['orders'][0]['status']='YI_QU_XIAO';r=module.calculate(cancelled,fx)
check('Cancellation without verified refund is flagged',r['groups']['all']['count']==10 and bool(r['warnings']) and r['groups']['all']['effective']['unknown']==1)
refund=copy.deepcopy(raw);refund['orders'][0]['receiptStatus']='YI_TUI_KUAN';r=module.calculate(refund,fx)
check('Unspecified refund blocks net, preserves original',bool(r['warnings']) and r['groups']['all']['effective']['unknown']==1 and r['groups']['all']['base']['unknown']==0)
bad=copy.deepcopy(raw);bad['orders'][0]['baseCurrency']='CNY'
try: module.calculate(bad,fx); mismatch=False
except ValueError: mismatch=True
check('Mixed currencies rejected',mismatch)
check('Exact decimal CNY rounding',module.formatted(Decimal('10938.53')*Decimal(fx['rate']))=='73363.09')
partial=copy.deepcopy(raw)
target=next(o for o in partial['orders'] if o['status']=='KE_HU_AN_QUAN_SHOU_HUO')
target.update(received='883000000',receivedCurrency='USD',freight='3000000',freightCurrency='USD',refundState='BU_FEN_YI_HE_SHI',refundGoods='20000000',refundFreight='0',refundCash='20000000',refundGoodsCurrency='USD',refundFreightCurrency='USD',refundCashCurrency='USD',refundVerifiedAt='2026-10-11T12:00:00Z')
r=module.calculate(partial,fx)
check('Partial refund keeps six successful orders and reduces net',r['groups']['success']['count']==6 and r['groups']['success']['effective']['known']=='5278.00' and r['groups']['all']['base']['known']=='10938.53')
full=copy.deepcopy(partial);target=next(o for o in full['orders'] if o['id']==target['id'])
target.update(status='YI_QU_XIAO',refundState='QUAN_E_YI_HE_SHI',refundGoods='880000000',refundFreight='3000000',refundCash='883000000')
r=module.calculate(full,fx)
check('Full verified refund with cancellation removes one success',r['groups']['success']['count']==5 and r['groups']['all']['count']==9 and r['groups']['all']['effective']['known']=='10055.53')
incomplete=copy.deepcopy(full);next(o for o in incomplete['orders'] if o['id']==target['id'])['refundCash']=None;r=module.calculate(incomplete,fx)
check('Incomplete full refund does not disappear',r['groups']['all']['count']==10 and r['groups']['all']['effective']['unknown']==1 and bool(r['warnings']))
over=copy.deepcopy(partial);next(o for o in over['orders'] if o['id']==target['id'])['refundGoods']='900000000';r=module.calculate(over,fx)
check('Refund over original price blocked',r['groups']['all']['effective']['unknown']==1 and bool(r['warnings']))
frozen=copy.deepcopy(raw);frozen['changes'][0].update(fixedRate='7.100000',fixedDate='2026-10-09',fixedSource='人工确认测试快照',received='10000000',actualSettlementCny='68000000')
r1=module.calculate(frozen,{'rate':'6.706851'});r2=module.calculate(frozen,{'rate':'7.5'})
check('Historical rate and actual CNY stay unchanged on daily FX change',r1['changes'][0]['frozenReferenceCny']==r2['changes'][0]['frozenReferenceCny']=='71.00' and r2['changes'][0]['actualSettlementCny']=='68000000')
module.atomic(module.OUT/'verification.json',{'results':results,'passed':len(results),'crmWrites':0})
print(json.dumps({'passed':len(results),'crmWrites':0}))
