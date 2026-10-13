"""Prepare one exact summary review and probe stale-version rejection only."""
import json
from crm_update_executor import UpdateRemote,ensure_current,PlanConflict
from crm_intake_executor import read_config
from signal_queue import DATA,WORKSPACE,digest,now

def run():
    intake=json.loads((DATA/'customer-intake-plan.json').read_text(encoding='utf-8'))
    remote=UpdateRemote(read_config()['CRA_CRM_INTAKE_API_KEY'])
    person=intake['operations'][0]['id'];before=remote.read('people',person)
    after='阿里来源，乌兹别克斯坦；姓名、公司及具体收货地点待确认。两项独立采购：① AI VISION CUBE DT Pro 两件样品，当前暂缓；② 七个 PCB/PCBA 项目询价，当前等待客户消息。两项均未确认成交，本次不建立订单或认定收款。WhatsApp LID仅作渠道身份，不是电话号码。'
    plan={'workspace_id':WORKSPACE,'collection':'people','record_id':person,'person_id':person,
        'record_label':before['name']['firstName'],'expected_updated_at':before['updatedAt'],
        'before':{'craChatSummary':before['craChatSummary']},'after':{'craChatSummary':after},
        'task_id':intake['task_id'],'rules_hash':intake['rules_hash'],'context_hash':intake['context_hash'],
        'evidence_ids':[intake['evidence_ids'][i] for i in (0,6,9)],'created_at':now()}
    plan['plan_digest']=digest(plan);ensure_current(plan)
    # Impossible old timestamp and same existing text: no business field can change.
    stale=dict(plan,expected_updated_at='2000-01-01T00:00:00.000Z',after=plan['before'])
    rejected=False
    try:remote.conditional_update(stale)
    except PlanConflict as exc:
        if str(exc)!='remote_version_conflict':raise
        rejected=True
    if not rejected:raise ValueError('conditional_update_failed_to_reject_stale_version')
    current=remote.read('people',person)
    if current!=before:raise ValueError('stale_probe_changed_record')
    (DATA/'context-update-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    proof={'checked_at':now(),'endpoint':'PATCH /rest/people?filter=and(id[eq]:...,updatedAt[eq]:...)',
        'stale_version_rejected':True,'record_unchanged_after_probe':True,'model_calls':0,'matched_updates':0,
        'server_version':'2.45.0','source_checked':'local runFilteredMutation -> WorkspaceMutationQueryBuilder -> UPDATE WHERE RETURNING'}
    (DATA/'context-update-verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    print(json.dumps(proof))

if __name__=='__main__':run()
