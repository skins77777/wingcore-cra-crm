import json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sql='''BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
'workflows',(SELECT json_agg(json_build_object('id',id,'name',name,'statuses',statuses,'publishedVersionId',"lastPublishedVersionId")) FROM workspace_avtucyqgg66sjy5h7kb5degx3.workflow WHERE id IN ('d2b3df8b-c449-411e-bc20-abda8d47b92e','70430ef6-852b-4fd1-8d53-32e932004d3a')),
'scanRuns',(SELECT coalesce(json_agg(json_build_object('id',id,'status',status,'versionId',"workflowVersionId",'createdAt',"createdAt",'startedAt',"startedAt",'endedAt',"endedAt",'trigger',state#>'{stepInfos,trigger}','step',state#>'{stepInfos,23f82a11-2fc3-428e-a309-3edb487814e4}')),'[]'::json) FROM workspace_avtucyqgg66sjy5h7kb5degx3."workflowRun" WHERE "workflowId"='d2b3df8b-c449-411e-bc20-abda8d47b92e'),
'key',(SELECT json_build_object('id',id,'name',name,'expiresAt',"expiresAt") FROM core."apiKey" WHERE id='4dd27024-2879-4014-a63c-97279697aed3'));
COMMIT;'''
p=subprocess.run(['wsl.exe','-d','CRA-Ubuntu-24.04','-u','root','--cd','/mnt/k/CRA客户项目/deployment/twenty','--','docker','compose','exec','-T','db','psql','-U','postgres','-d','twenty','-At','-v','ON_ERROR_STOP=1'],input=sql,text=True,encoding='utf-8',capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
if p.returncode:raise RuntimeError('Read-only runtime verification unavailable')
data=json.loads(next(x for x in p.stdout.splitlines() if x.startswith('{')))
(root/'crm-foundation/t1-runtime-proof.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'workflows':[{k:w[k] for k in ('name','statuses')} for w in data['workflows']],'scanRuns':[{'id':r['id'],'status':r['status'],'result':r['step'].get('result') if r['step'] else None} for r in data['scanRuns']]},ensure_ascii=True))
