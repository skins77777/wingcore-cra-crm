import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
schema='workspace_avtucyqgg66sjy5h7kb5degx3'
sql='BEGIN TRANSACTION READ ONLY; SELECT json_build_object('+','.join("'%s',(SELECT coalesce(json_agg(to_jsonb(r)),'[]'::json) FROM %s.\"%s\" r WHERE \"deletedAt\" IS NULL)"%(name,schema,table) for name,table in [('people','person'),('opportunities','opportunity'),('tasks','task'),('orders','_dingDan')])+'); COMMIT;'
p=subprocess.run(['wsl.exe','-d','CRA-Ubuntu-24.04','-u','root','--cd','/mnt/k/CRA客户项目/deployment/twenty','--','docker','compose','exec','-T','db','psql','-U','postgres','-d','twenty','-At','-v','ON_ERROR_STOP=1'],input=sql,text=True,encoding='utf-8',capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
if p.returncode:raise RuntimeError('Snapshot unavailable')
data=json.loads(next(x for x in p.stdout.splitlines() if x.startswith('{')))
prefix=sys.argv[2] if len(sys.argv)>2 else 't1'
if prefix not in ('t1','l1'):raise ValueError('Unknown verification prefix')
out=root/'crm-foundation'/(prefix+'-business-'+sys.argv[1]+'.json');out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:len(v) for k,v in data.items()}))
