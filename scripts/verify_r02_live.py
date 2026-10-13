"""Real API capability probe with unchanged business stage; no fabricated inquiry."""
import json
from signal_queue import DATA,now
from crm_intake_executor import read_config,PlanConflict
from crm_update_executor import UpdateRemote

def run():
    intake=json.loads((DATA/'customer-intake-plan.json').read_text(encoding='utf-8'))
    identifier=intake['operations'][1]['id'];remote=UpdateRemote(read_config()['CRA_CRM_INTAKE_API_KEY'])
    before=remote.read('opportunities',identifier)
    if before['craPurchaseStage']!='询盘' or before['craFulfilmentStatus']!='样品暂缓；等待客户消息':raise ValueError('probe_scope_changed')
    probe={'collection':'opportunities','record_id':identifier,'expected_updated_at':before['updatedAt'],'after':{'craPurchaseStage':before['craPurchaseStage']}}
    result=remote.conditional_update(probe);after=remote.read('opportunities',identifier)
    business=['name','amount','stage','craPurchaseStage','craFulfilmentStatus','craChatSummary','pointOfContactId']
    if result.get('id')!=identifier or any(before[k]!=after[k] for k in business):raise ValueError('same_value_probe_changed_business_fields')
    if before['updatedAt']==after['updatedAt']:raise ValueError('version_did_not_advance')
    stale_rejected=False
    try:remote.conditional_update(probe)
    except PlanConflict as exc:
        if str(exc)!='remote_version_conflict':raise
        stale_rejected=True
    if not stale_rejected:raise ValueError('stale_version_not_rejected')
    latest=remote.read('opportunities',identifier)
    if any(latest[k]!=after[k] for k in business) or latest['updatedAt']!=after['updatedAt']:raise ValueError('stale_retry_changed_record')
    context_path=DATA/'crm-contexts.json';contexts=json.loads(context_path.read_text(encoding='utf-8'))
    for customer in contexts['customers']:
        for purchase in customer['purchase_contexts']:
            if purchase['opportunity_id']==identifier:
                for key in list(purchase['crm_fields']):purchase['crm_fields'][key]=latest.get(key)
                customer['snapshot_at']=now()
    context_path.write_text(json.dumps(contexts,ensure_ascii=False,indent=2),encoding='utf-8')
    proof={'checked_at':now(),'opportunity_id':identifier,'matching_same_value_patch_count':1,
        'stage_before':before['craPurchaseStage'],'stage_after':after['craPurchaseStage'],
        'business_fields_unchanged':True,'stale_version_rejected':True,'model_calls':0,
        'real_R02_advancement_verified':False,'reason':'No new eligible buyer message; actual stage advancement is verified only in isolation.'}
    (DATA/'r02-live-verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof,ensure_ascii=False))

if __name__=='__main__':run()
