"""Prepare limited UI imports; no CRM writes or credentials."""
import csv, hashlib, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import ali_export_reader as a
out=a.DATA/'crm-update-2026-10-12'
out.mkdir(exist_ok=True)
crm=a.read_crm()
a.atomic(out/'before.json',crm)
source=a.ROOT/'records/chat-signal/ali-orders-export-original-2026-10-12.xlsx'
p=a.plan(a.aggregate(a.read_xlsx(source)),crm,hashlib.sha256(source.read_bytes()).hexdigest())
a.atomic(out/'plan.json',p)
def write(name,rows):
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
rows=[]
for o in p['orders']:
    if not o['record_id']:continue
    fields=o['fields']
    current=next(x for x in crm['orders'] if x['id']==o['record_id'])
    def val(k):return fields[k]['proposed'] if k in fields else current.get(k)
    freight=fields.get('yiQueRenYunFei',{}).get('proposed')
    rows.append({'ID':o['record_id'],'平台状态':val('pingTaiZhuangTai'),
        '商品明细':val('shangPinMingXi'),'事实与来源':val('shiShiYuLaiYuan'),
        '已确认运费 / Amount':str(freight['amountMicros']/1000000) if freight else str(current['yiQueRenYunFeiAmountMicros']/1000000),
        '已确认运费 / Currency':'USD'})
write('existing-orders.csv',rows)
people=[]
for c in p['customers']:
    if c['record_id'] and any(x.startswith('建议补充空白邮箱') for x in c['proposals']):
        people.append({'ID':c['record_id'],'Emails / Primary Email':c['emails'][0]})
write('existing-people.csv',people)
print(json.dumps({'orders':len(rows),'people':len(people),'directory':str(out)},ensure_ascii=False))
