"""Read-only Alibaba XLSX inbox. No model, credentials, network writes or CRM writes."""
from pathlib import Path
import collections, datetime as dt, decimal, hashlib, html, json, os
import re, sqlite3, subprocess, sys, uuid, zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / '阿里导出接入'
DATA = ROOT / 'records' / 'ali-export'
NS = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
SCHEMA = 'workspace_avtucyqgg66sjy5h7kb5degx3'
COUNTRIES = {'US':'美国','RO':'罗马尼亚','AM':'亚美尼亚','EE':'爱沙尼亚','TR':'土耳其'}
REQUIRED = ['订单编号(Order Number)','买家名称(Buyer Name)','卖家名称(Seller Name)',
            '数量(Quantity)','单价(Unit Price)','订单总价(Order Amount)',
            '运费(Shipping Fee)','折扣金额(Discount Amount)','订单币种(Order Currency)',
            '买家国家(Buyer Country)','状态(Status)','产品名称(Product Name)','邮箱(Email)']

def atomic(path, data):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def number(v):
    value = decimal.Decimal(str(v))
    if not value.is_finite() or value < 0:
        raise ValueError('Invalid nonnegative number')
    return value

def read_xlsx(path):
    if path.stat().st_size > 20*1024*1024:
        raise ValueError('File exceeds 20 MiB')
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 100*1024*1024:
            raise ValueError('Unpacked workbook exceeds 100 MiB')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        sheets=wb.find('m:sheets',NS)
        if len(sheets)!=1:
            raise ValueError('Expected single-sheet Alibaba order export')
        rid=sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rel=next(x for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')) if x.get('Id')==rid)
        target=rel.get('Target')
        sheetfile=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        if '..' in sheetfile:
            raise ValueError('Invalid worksheet path')
        xml=ET.fromstring(z.read(sheetfile))
        rows=[]
        for row in xml.findall('m:sheetData/m:row',NS):
            cells={}
            for c in row.findall('m:c',NS):
                if c.find('m:f',NS) is not None:
                    raise ValueError('Formulas are not accepted in order exports')
                a=re.match(r'([A-Z]+)\d+$',c.get('r',''))
                if not a:
                    raise ValueError('Invalid cell reference')
                idx=0
                for letter in a[1]: idx=idx*26+ord(letter)-64
                if idx>100: raise ValueError('Unexpected column count')
                v=c.find('m:v',NS)
                text=v.text if v is not None else ''
                if c.get('t')=='s': text=strings[int(text)]
                elif c.get('t')=='inlineStr':
                    text=''.join(t.text or '' for t in c.findall('.//m:t',NS))
                cells[idx-1]=text or ''
            rows.append((int(row.get('r')),cells))
        if not rows or len(rows)>50000: raise ValueError('Invalid row count')
        headers=rows[0][1]
        if len(set(headers.values()))!=len(headers): raise ValueError('Duplicate headers')
        if not set(REQUIRED)<=set(headers.values()): raise ValueError('Not an Alibaba order export')
        result=[]
        for rn,cells in rows[1:]:
            if not any(cells.values()): continue
            result.append({'_row':rn,**{label:cells.get(i,'') for i,label in headers.items()}})
        return result

def aggregate(rows):
    orders={}
    for r in rows:
        key=r['订单编号(Order Number)']
        if not re.fullmatch(r'\d{12,25}',key): raise ValueError('Order ID must be intact text digits')
        currency=r['订单币种(Order Currency)']
        if currency!='USD': raise ValueError('Only confirmed USD scope is supported')
        signature={k:r[k] for k in REQUIRED if k not in ['数量(Quantity)','单价(Unit Price)','产品名称(Product Name)']}
        o=orders.setdefault(key,{'number':key,'header':signature,'rows':[], 'items':[], 'raw':r})
        if signature!=o['header']: raise ValueError('Conflicting repeated order fields: '+key)
        if any(i['product']==r['产品名称(Product Name)'] and i['sku']==r.get('SKU规格(Sku Specification)','') for i in o['items']):
            raise ValueError('Repeated identical item requires review: '+key)
        qty=number(r['数量(Quantity)']); price=number(r['单价(Unit Price)'])
        if qty<=0: raise ValueError('Quantity must be positive')
        o['rows'].append(r['_row'])
        o['items'].append({'product':r['产品名称(Product Name)'],'sku':r.get('SKU规格(Sku Specification)',''),
                           'quantity':str(qty),'unit_price':str(price)})
    for o in orders.values():
        r=o['raw'];o['goods']=sum((number(i['quantity'])*number(i['unit_price']) for i in o['items']),decimal.Decimal(0))
        o['total']=number(r['订单总价(Order Amount)']);o['freight']=number(r['运费(Shipping Fee)'])
        o['difference']=o['total']-o['goods']-o['freight']+number(r['折扣金额(Discount Amount)'])
    return orders

def read_crm():
    sql=f'''BEGIN TRANSACTION READ ONLY;
SELECT json_build_object('orders',COALESCE((SELECT json_agg(to_jsonb(o)) FROM {SCHEMA}."_dingDan" o WHERE "deletedAt" IS NULL),'[]'::json),
'people',COALESCE((SELECT json_agg(to_jsonb(p)) FROM {SCHEMA}.person p WHERE "deletedAt" IS NULL),'[]'::json));
COMMIT;'''
    args=['wsl.exe','-d','CRA-Ubuntu-24.04','-u','root','--cd','/mnt/k/CRA客户项目/deployment/twenty',
          '--','docker','compose','exec','-T','db','psql','-U','postgres','-d','twenty','-At','-v','ON_ERROR_STOP=1']
    res=subprocess.run(args,input=sql,text=True,encoding='utf-8',capture_output=True,timeout=45,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if res.returncode: raise RuntimeError('CRM read-only snapshot unavailable')
    return json.loads(next(x for x in res.stdout.splitlines() if x.startswith('{')))

def display_name(p):
    return ' '.join(str(p.get(k) or '') for k in ['nameFirstName','nameLastName']).strip()

def plan(orders, crm, source_hash):
    bynumber=collections.defaultdict(list)
    for o in crm['orders']: bynumber[o.get('aLiDingDanHao')].append(o)
    persons={p['id']:p for p in crm['people']}
    changes=[]; issues=[]; customers={}
    for key,o in orders.items():
        r=o['raw'];buyer=r['买家名称(Buyer Name)'];country=r['买家国家(Buyer Country)']
        label=COUNTRIES.get(country,country)+'｜'+buyer
        matched=bynumber[key]
        if len(matched)>1:
            issues.append({'order':key,'issue':'CRM存在重复订单号，不能自动选择'});continue
        current=matched[0] if matched else None
        p=persons.get(current.get('keHuId')) if current else None
        if p and display_name(p)!=label:
            issues.append({'order':key,'issue':'关联客户姓名或国家与导出不一致'});continue
        if not p:
            candidates=[x for x in crm['people'] if display_name(x)==label]
            if len(candidates)>1:
                issues.append({'order':key,'issue':'同名客户多条，待确认归属'});continue
            p=candidates[0] if candidates else None
        customer_key=(country,buyer)
        customer=customers.setdefault(customer_key,{'customer':label,'record_id':p['id'] if p else None,
            'action':'核对已有客户' if p else '建议新建客户','emails':set(), 'orders':[], 'proposals':[],
            'expected_updated_at':p.get('updatedAt') if p else None})
        customer['emails'].add(r['邮箱(Email)'].strip().lower());customer['orders'].append(key)
        if o['difference']!=0: issues.append({'order':key,'issue':f'总价与商品加运费减折扣差额 USD {o["difference"]}，费用类型待核'})
        items=' / '.join(i['product']+(('；'+i['sku']) if i['sku'] else '')+f'；USD{i["unit_price"]}×{i["quantity"]}' for i in o['items'])
        suggestions={'pingTaiZhuangTai':r['状态(Status)'],'shangPinMingXi':items}
        # Original contract / verified shipping fields are not blindly overwritten by a later export.
        if current:
            for field,amount in [('yuanDingDanJinE',o['total']),('lieBiaoShangPinJinE',o['goods'])]:
                v=current.get(field+'AmountMicros')
                if v is None or decimal.Decimal(str(v))/1000000!=amount:
                    issues.append({'order':key,'issue':f'{field} 与导出不同，保留原值，建议单独核实'})
            if current.get('yiQueRenYunFeiAmountMicros') is None:
                suggestions['yiQueRenYunFei']={'amountMicros':int(o['freight']*1000000),'currencyCode':'USD'}
        else:
            suggestions.update({'name':label+'｜'+key,'aLiDingDanHao':key,
                'yuanDingDanJinE':{'amountMicros':int(o['total']*1000000),'currencyCode':'USD'},
                'lieBiaoShangPinJinE':{'amountMicros':int(o['goods']*1000000),'currencyCode':'USD'}})
        sourcefacts={'source_hash':source_hash,'source_rows':o['rows'],'platform_status':r['状态(Status)'],
            'buyer_country':country,'shipping_country':r.get('国家 (Country)'), 'seller_display_name':r['卖家名称(Seller Name)'],
            'contract_shipping_usd':str(o['freight']), 'actual_delivery_raw':r.get('实际发货时间(Actual Delivery Time)'),
            'appointed_delivery_raw':r.get('约定发货时间(Appointed Delivery Time)'),
            'unexplained_difference_usd':str(o['difference'])}
        managed='[阿里导出核对]\n'+f'来源文件 SHA256 {source_hash}，商品行 {o["rows"]}。\n'+f'平台状态：{r["状态(Status)"]}；业务员：{r["卖家名称(Seller Name)"]}；买家国家：{country}；收货国家：{r.get("国家 (Country)")}。\n'+f'合同运费 USD {o["freight"]}；实际发货时间（原文，时区未注明）：{r.get("实际发货时间(Actual Delivery Time)") or "未提供"}；约定发货时间（原文）：{r.get("约定发货时间(Appointed Delivery Time)") or "未提供"}。\n预付款和尾款为合同字段，不作为收款证明；实际履约及补差沿用人工核实。'
        oldfacts=(current.get('shiShiYuLaiYuan') or '') if current else ''
        # Preserve all prior human evidence; replace only this reader's bounded trailing block.
        oldfacts=oldfacts.split('\n[阿里导出核对]\n',1)[0]
        suggestions['shiShiYuLaiYuan']=(oldfacts+'\n'+managed).strip()
        changed={}
        for field,value in suggestions.items():
            actual=current.get(field) if current else None
            if field=='yiQueRenYunFei' and current:
                actual={'amountMicros':current.get(field+'AmountMicros'),'currencyCode':current.get(field+'CurrencyCode')}
            if actual!=value: changed[field]={'before':actual,'proposed':value}
        changes.append({'order':key,'customer':label,'action':'建议更新' if current else '建议新建',
            'record_id':current['id'] if current else None, 'expected_updated_at':current.get('updatedAt') if current else None,
            'fields':changed,'source_facts':sourcefacts,
            'preserved_fields':['已收金额','收款核实状态','实际履约状态','补差变动','退款','下一步行动','跟进时间']})
    for c in customers.values():
        c['emails']=sorted(c['emails'])
        if len(c['emails'])!=1:
            c['proposals'].append('多邮箱来源需核对，不选择覆盖');continue
        email=c['emails'][0];p=persons.get(c['record_id'])
        if not p: c['proposals'].append('建议以国家加姓名建档，邮箱来自本次导出，电话不自动绑定WhatsApp');continue
        existing=p.get('emailsPrimaryEmail') or ''
        others=[x for x in crm['people'] if x['id']!=p['id'] and (x.get('emailsPrimaryEmail') or '').lower()==email]
        if others: c['proposals'].append('邮箱已关联其他客户，需核对')
        elif not existing: c['proposals'].append('建议补充空白邮箱：'+email)
        elif existing.lower()==email: c['proposals'].append('邮箱与现有CRM一致，无需修改')
        else: c['proposals'].append('现有邮箱不同，保留原值，将导出邮箱交由人工核对')
    return {'mode':'read_only','crm_writes':0,'model_calls':0,'source_hash':source_hash,
        'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'unique_orders':len(orders),
        'item_rows':sum(len(o['items']) for o in orders.values()), 'customers':list(customers.values()),
        'orders':changes,'issues':issues,'contract_total_usd':str(sum((o['total'] for o in orders.values()),decimal.Decimal(0)))}

def render(p):
    e=lambda v: html.escape(str(v))
    lines=['<!doctype html><meta charset="utf-8"><title>阿里导出与CRM核对</title>',
        '<style>body{font:16px "Microsoft YaHei",sans-serif;max-width:1100px;margin:32px auto;padding:16px;color:#203047}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd}th{background:#edf2f7}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{padding:12px;border-bottom:1px solid #ddd}</style>',
        '<h1>阿里导出与CRM核对</h1><p>只读运行，未修改CRM。生成时间：'+e(p['checked_at'])+'</p>',
        f'<p>{p["unique_orders"]}笔订单，{p["item_rows"]}条商品明细，{len(p["customers"])}位客户。更新清单保留原收款、履约、补差和退款记录。</p>',
        '<h2>客户信息</h2><table><tr><th>客户</th><th>建议</th></tr>']
    for c in p['customers']: lines.append('<tr><td>'+e(c['customer'])+'</td><td>'+e('；'.join(c['proposals']))+'</td></tr>')
    lines.append('</table><h2>需要核实</h2>')
    for i in p['issues']:lines.append('<p>'+e(i['order']+'：'+i['issue'])+'</p>')
    lines.append('<h2>订单更新清单</h2>')
    labels={'pingTaiZhuangTai':'平台状态','shangPinMingXi':'商品明细','yiQueRenYunFei':'合同运费（拟填入已确认运费，需核对）',
        'name':'订单名称','aLiDingDanHao':'阿里订单编号','yuanDingDanJinE':'原订单金额','lieBiaoShangPinJinE':'商品金额','shiShiYuLaiYuan':'事实与来源'}
    def friendly(v):
        if isinstance(v,dict) and 'amountMicros' in v:
            return '未填写' if v['amountMicros'] is None else str(decimal.Decimal(str(v['amountMicros']))/1000000)+' '+v['currencyCode']
        return '未填写' if v is None else str(v)
    for o in p['orders']:
        lines.append('<details><summary>'+e(o['order']+' '+o['customer']+' '+o['action'])+'</summary><table><tr><th>字段</th><th>现有值</th><th>建议值</th></tr>')
        for k,v in o['fields'].items():
            lines.append('<tr><td>'+e(labels.get(k,k))+'</td><td><pre>'+e(friendly(v['before']))+'</pre></td><td><pre>'+e(friendly(v['proposed']))+'</pre></td></tr>')
        lines.append('</table></details>')
    lines.append('<p>当前文件不含运单号、完整物流轨迹或询盘记录。后续写入须专用权限和独立执行器；本程序没有写入路径。</p>')
    return '\n'.join(lines)

def run():
    INBOX.mkdir(exist_ok=True);DATA.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DATA/'reader.sqlite3',timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS files(hash TEXT PRIMARY KEY,path TEXT,state TEXT,checked_at TEXT)')
        for file in sorted(INBOX.glob('*.xlsx')):
            if file.name.startswith('~$') or dt.datetime.now().timestamp()-file.stat().st_mtime<5: continue
            raw=file.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
            previous=db.execute('SELECT state FROM files WHERE hash=?',(sha,)).fetchone()
            if previous and previous[0] in ('processed','rejected') and '--refresh' not in sys.argv:continue
            try:
                rows=read_xlsx(file)
                if hashlib.sha256(file.read_bytes()).hexdigest()!=sha: raise RuntimeError('File changed during processing')
                orders=aggregate(rows);crm=read_crm();p=plan(orders,crm,sha)
                archive=DATA/(sha+'.xlsx')
                if not archive.exists():archive.write_bytes(raw)
                atomic(DATA/(sha+'.plan.json'),p)
                atomic(DATA/'latest-plan.json',p)
                (DATA/'最新核对.html').write_text(render(p),encoding='utf-8')
                db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',(sha,file.name,'processed',p['checked_at']))
                db.commit();atomic(DATA/'status.json',{'state':'processed','file':file.name,'checked_at':p['checked_at'],'crm_writes':0,'model_calls':0})
            except Exception as exc:
                atomic(DATA/'status.json',{'state':'error','file':file.name,'error':type(exc).__name__+': '+str(exc),'crm_writes':0})
                if isinstance(exc,ValueError):
                    db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',(sha,file.name,'rejected',dt.datetime.now(dt.timezone.utc).isoformat()));db.commit()
                raise

if __name__=='__main__':
    try: run()
    except Exception: sys.exit(1)
