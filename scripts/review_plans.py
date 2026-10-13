"""Turn the locally curated, immutable intake plan into one actionable review."""
import json
from signal_queue import ROOT,WORKSPACE,digest,prospect_context

def intake_plan():
    path=ROOT/'records/chat-signal/customer-intake-plan.json'
    if not path.exists():return None
    plan=json.loads(path.read_text(encoding='utf-8'))
    saved=plan.pop('plan_digest')
    if saved!=digest(plan) or plan['workspace_id']!=WORKSPACE:raise ValueError('invalid_intake_plan')
    plan['plan_digest']=saved
    return plan

def build_review(plan,signal,format_version):
    task=signal.execute('SELECT * FROM analysis_tasks WHERE id=?',(plan['task_id'],)).fetchone()
    context=prospect_context(plan['operations'][0]['body']['craWhatsappIdentity'])
    rules=digest((ROOT/'crm-foundation/chat-signal-rules.md').read_text(encoding='utf-8'))
    if not task or task['state'] not in ('succeeded','succeeded_local_validation') or plan['rules_hash']!=rules or plan['context_hash']!=digest(context):return None
    evidence=[]
    for identifier in plan['evidence_ids']:
        row=signal.execute('SELECT * FROM evidence WHERE id=? AND active=1',(identifier,)).fetchone()
        if not row:return None
        evidence.append({'sourceLabel':row['channel']+' · '+('你发出' if row['direction']=='outbound' else '客户发来')+' · '+(row['occurred_at'] or '时间未知'),'reference':row['id'],'excerpt':row['text'][:3500]})
    v=context['verification']
    evidence.insert(0,{'sourceLabel':'你已确认 · '+v['recorded_at'],'reference':v['question_item_id'],'excerpt':v['statement']})
    item={'id':digest(['curated_intake',plan['plan_digest']]),'workspaceId':WORKSPACE,'planDigest':'','reviewFormatVersion':format_version,
          'ruleId':'R01-R03','ruleVersion':rules,'title':plan['title'],'reason':plan['reason']+' 通过仅批准此精确计划；专用CRM访问未授权前仍不执行。',
          'status':'pending','createdAt':plan['created_at'],'target':{'objectLabel':'客户及商机','recordLabel':context['display_name']},
          'changes':plan['changes'],'evidence':evidence,'choices':[{'id':'create_intake','label':'建立临时客户，并分别建立两项询盘','description':'只创建上述三条记录；不更新现有客户、不建立订单。'}],
          'decision':None,'execution':{'status':'not_started','message':'尚未执行CRM变更。'},'canDecide':True,'executionPlan':plan}
    item['planDigest']=digest(item)
    return item
