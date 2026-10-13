import json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sql='''BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
'workflows',(SELECT json_agg(json_build_object('id',w.id,'name',w.name,'statuses',w.statuses,'publishedVersionId',w."lastPublishedVersionId")) FROM workspace_avtucyqgg66sjy5h7kb5degx3.workflow w WHERE id IN ('dbe415ec-7625-443d-b959-8069fc5d60da','d2b3df8b-c449-411e-bc20-abda8d47b92e')),
'versions',(SELECT json_agg(json_build_object('workflowId',"workflowId",'id',id,'status',status,'trigger',trigger,'steps',steps)) FROM workspace_avtucyqgg66sjy5h7kb5degx3."workflowVersion" WHERE "workflowId" IN ('dbe415ec-7625-443d-b959-8069fc5d60da','d2b3df8b-c449-411e-bc20-abda8d47b92e') AND status IN ('ACTIVE','DRAFT') AND "deletedAt" IS NULL),
'runs',(SELECT coalesce(json_agg(json_build_object('id',r.id,'workflowId',r."workflowId",'status',r.status,'versionId',r."workflowVersionId",'createdAt',r."createdAt",'startedAt',r."startedAt",'endedAt',r."endedAt",'trigger',r.state#>'{stepInfos,trigger}','steps',(SELECT jsonb_agg(value) FROM jsonb_each(r.state->'stepInfos') WHERE key<>'trigger'))),'[]'::json) FROM workspace_avtucyqgg66sjy5h7kb5degx3."workflowRun" r WHERE r."workflowId"='dbe415ec-7625-443d-b959-8069fc5d60da'));
COMMIT;'''
p=subprocess.run(['wsl.exe','-d','CRA-Ubuntu-24.04','-u','root','--cd','/mnt/k/CRA客户项目/deployment/twenty','--','docker','compose','exec','-T','db','psql','-U','postgres','-d','twenty','-At','-v','ON_ERROR_STOP=1'],input=sql,text=True,encoding='utf-8',capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
if p.returncode:raise RuntimeError('Read-only workflow verification unavailable')
data=json.loads(next(x for x in p.stdout.splitlines() if x.startswith('{')))
(root/'crm-foundation/l1-runtime-proof.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'workflows':[{'name':w['name'],'statuses':w['statuses']} for w in data['workflows']],'runs':data['runs']},ensure_ascii=True))
