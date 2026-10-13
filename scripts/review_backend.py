"""Authenticated local review API; saves decisions, never writes CRM or calls AI."""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import hmac
import json
import pathlib
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from signal_queue import ROOT, DATA, WORKSPACE, encode, digest, now, prospect_context
from review_plans import intake_plan,build_review
from crm_intake_executor import queue_schema,enabled
from crm_update_executor import schema as update_schema,ensure_current as update_current,PlanConflict as UpdateConflict

MEMBER='ceb518d8-6989-443f-aa75-197021ee139c'
REVIEW_FORMAT_VERSION=3

class Conflict(Exception): pass

def db_open(path=None):
    db=sqlite3.connect(path or DATA/'review.sqlite3',timeout=20)
    db.row_factory=sqlite3.Row
    db.executescript('''CREATE TABLE IF NOT EXISTS requests (
      id TEXT PRIMARY KEY, task_id TEXT, rules_hash TEXT, context_hash TEXT, payload TEXT,
      status TEXT, created_at TEXT, decision TEXT);
      CREATE TABLE IF NOT EXISTS decision_audit (
      id TEXT PRIMARY KEY, request_id TEXT, member_id TEXT, saved_at TEXT, payload TEXT);''')
    queue_schema(db)
    update_schema(db)
    return db

def item_public(row,db=None):
    item=json.loads(row['payload']);item['status']=row['status']
    plan=item.pop('executionPlan',None)
    update_plan=item.pop('contextUpdatePlan',None)
    item['decision']=json.loads(row['decision']) if row['decision'] else None
    item['canDecide']=row['status']=='pending'
    if row['status']=='approved':
        item['execution']={'status':'manual_required','message':'决定已保存，CRM执行器尚未接通；当前没有写入CRM。'}
        execution=db.execute('SELECT state,error_code FROM crm_intake_outbox WHERE request_id=?',(row['id'],)).fetchone() if db else None
        if plan:
            item['execution']={'status':'manual_required','message':'精确建档计划已保存；等待专用CRM权限配置和启用，当前未执行。'}
        if execution:
            state=execution['state'];messages={'pending':'等待已授权的执行器处理。','running':'正在执行建档并核对结果。','succeeded':'三条建档记录已通过官方API写入并回读核对。','conflict':'资料或远端记录已变化，需要核实；已完成的部分保留，不覆盖人工修改。','failed':'建档执行未完成，请交给Codex排查；已完成的部分保留。'}
            item['execution']={'status':'queued' if state=='pending' else state,'message':messages[state]}
        if update_plan and db:
            update=db.execute('SELECT state FROM crm_update_outbox WHERE request_id=?',(row['id'],)).fetchone()
            if update:
                state=update['state'];messages={'pending':'等待执行字段更新。','running':'正在核对远端版本并更新字段。','succeeded':'目标字段值已通过官方API回读核对。','conflict':'来源或CRM记录已变化，停止覆盖，请交给Codex核对。','failed':'字段更新未完成，请交给Codex排查。'}
                item['execution']={'status':'queued' if state=='pending' else state,'message':messages[state]}
    else:item['execution']={'status':'not_started','message':'尚未执行CRM变更。'}
    return item

def refresh(db, data=DATA):
    """Convert exact saved candidates and provenance; do not invent runnable writes."""
    active_rules=digest((ROOT/'crm-foundation/chat-signal-rules.md').read_text(encoding='utf-8'))
    curated=intake_plan()
    update_path=data/'context-update-plan.json'
    update_plan=json.loads(update_path.read_text(encoding='utf-8')) if update_path.exists() else None
    with closing(sqlite3.connect('file:'+str(data/'signal.sqlite3')+'?mode=ro',uri=True)) as signal:
        signal.row_factory=sqlite3.Row
        current={r['id']:r for r in signal.execute('SELECT * FROM analysis_tasks')}
        candidate_rows=signal.execute("SELECT * FROM candidates WHERE state='candidate_only'").fetchall()
        # A prospect background is current only for its exact WhatsApp identity.
        with db:
            for old in db.execute("SELECT * FROM requests WHERE status IN ('pending','approved')").fetchall():
                task=current.get(old['task_id'])
                evidences=signal.execute('SELECT e.* FROM evidence e JOIN task_evidence te ON e.id=te.evidence_id WHERE te.task_id=?',(old['task_id'],)).fetchall()
                context=prospect_context(evidences[0]['external_identity']) if evidences and evidences[0]['channel']=='whatsapp' else None
                previous=json.loads(old['payload'])
                if previous.get('contextUpdatePlan',{}).get('kind')=='r02_explicit_stage':continue
                if previous.get('contextUpdatePlan'):
                    finished=db.execute("SELECT 1 FROM crm_update_outbox WHERE request_id=? AND state='succeeded'",(old['id'],)).fetchone()
                    if finished:continue
                    try:
                        update_current(previous['contextUpdatePlan'])
                        if not update_plan or update_plan!=previous['contextUpdatePlan']:raise UpdateConflict('update_plan_changed')
                    except UpdateConflict:
                        db.execute("UPDATE requests SET status='superseded' WHERE id=?",(old['id'],));continue
                changed_plan=previous.get('executionPlan') and (not curated or previous['executionPlan']['plan_digest']!=curated['plan_digest'])
                if not task or task['state']=='invalidated' or old['context_hash']!=digest(context) or old['rules_hash']!=active_rules or any(not e['active'] for e in evidences) or previous.get('reviewFormatVersion')!=REVIEW_FORMAT_VERSION or changed_plan:
                    db.execute("UPDATE requests SET status='superseded' WHERE id=?",(old['id'],))
            for row in candidate_rows:
                if curated and row['task_id']==curated['task_id']:continue
                task=current[row['task_id']]
                if task['state'] not in ('succeeded','succeeded_local_validation'):continue
                if task['rules_hash']!=active_rules:continue
                proposal=json.loads(row['payload'])
                evidence_rows=signal.execute('SELECT * FROM evidence WHERE id IN (%s)'%','.join('?'*len(proposal['evidence_ids'])),proposal['evidence_ids']).fetchall()
                if not evidence_rows or any(not e['active'] for e in evidence_rows):continue
                identity=evidence_rows[0]['external_identity']
                context=prospect_context(identity) if evidence_rows[0]['channel']=='whatsapp' else None
                context_hash=digest(context)
                label=context['display_name'] if context else '身份待核实的采购联系人'
                title=proposal.get('question') or ('确认客户候选' if proposal.get('object_type')=='customer' else '确认采购意向候选')
                fields=proposal.get('fields',{})
                changes=[{'fieldLabel':key,'before':'','after':str(value)} for key,value in fields.items() if value is not None]
                if context:
                    changes=[c for c in changes if c['fieldLabel'] not in ('国家','名称','身份')]
                    changes += [{'fieldLabel':'国家','before':'','after':context['country_zh']},
                                {'fieldLabel':'最新状态','before':'','after':'等待客户消息，未成交，不自动输单'}]
                options=proposal.get('options',[])
                # Unsupported semantic suggestions remain plans; approvals are not writes.
                choices=[{'id':'choice_'+str(i),'label':option,'description':'仅保存此选择；CRM操作仍需执行器或人工处理。'} for i,option in enumerate(options)]
                evidence=[{'sourceLabel':e['channel']+' · '+('你发出' if e['direction']=='outbound' else '客户发来')+' · '+(e['occurred_at'] or '时间未知'),
                           'reference':e['id'],'excerpt':e['text'][:3500]} for e in evidence_rows]
                reason=proposal.get('reason','需要核实采购归属')
                if context:
                    verification=context['verification']
                    evidence.insert(0,{'sourceLabel':'你已确认 · '+verification['recorded_at'], 'reference':verification['question_item_id'], 'excerpt':verification['statement']})
                    if proposal.get('object_type')=='customer':reason='国家、阿里来源和等待客户消息的状态已由你确认；姓名、公司及具体CRM客户关联仍未知。'
                item={'id':digest([row['id'],context_hash,REVIEW_FORMAT_VERSION]),'workspaceId':WORKSPACE,'planDigest':'','reviewFormatVersion':REVIEW_FORMAT_VERSION,
                    'ruleId':'R01-R11','ruleVersion':task['rules_hash'],'title':title,
                    'reason':reason+' 此候选尚未生成可执行字段计划；当前保存确认决定，需核对具体采购事实。',
                    'status':'pending','createdAt':row['created_at'],'target':{'objectLabel':proposal.get('object_type','业务确认'),'recordLabel':label},
                    'changes':changes,'evidence':evidence,'choices':choices,'decision':None,
                    'execution':{'status':'not_started','message':'尚未执行CRM变更。'},'canDecide':True}
                item['planDigest']=digest(item)
                db.execute('INSERT OR IGNORE INTO requests VALUES(?,?,?,?,?,?,?,?)',
                    (item['id'],row['task_id'],task['rules_hash'],context_hash,encode(item),'pending',row['created_at'],None))
            if curated:
                item=build_review(curated,signal,REVIEW_FORMAT_VERSION)
                if item:
                    db.execute('INSERT OR IGNORE INTO requests VALUES(?,?,?,?,?,?,?,?)',(item['id'],curated['task_id'],curated['rules_hash'],curated['context_hash'],encode(item),'pending',curated['created_at'],None))
            if update_plan:
                try:update_current(update_plan)
                except UpdateConflict:return
                evidence=[]
                for eid in update_plan['evidence_ids']:
                    e=signal.execute('SELECT * FROM evidence WHERE id=?',(eid,)).fetchone()
                    evidence.append({'sourceLabel':e['channel']+' · '+('你发出' if e['direction']=='outbound' else '客户发来'),'reference':eid,'excerpt':e['text'][:3500]})
                background=prospect_context(e['external_identity']) if e['channel']=='whatsapp' else None
                if background:
                    verification=background['verification']
                    evidence.insert(0,{'sourceLabel':'你已确认 · '+verification['recorded_at'],'reference':verification['question_item_id'],'excerpt':verification['statement']})
                item={'id':digest(['context_update',update_plan['plan_digest']]),'workspaceId':WORKSPACE,'planDigest':'','reviewFormatVersion':REVIEW_FORMAT_VERSION,
                    'ruleId':'客户与采购小结','ruleVersion':update_plan['rules_hash'],'title':'整理乌兹别克斯坦客户总览，保留两项独立采购',
                    'reason':'整理已核实的背景和现有商机摘要；姓名、公司、付款和订单不补猜。按当前远端版本更新，人工修改后旧计划停止覆盖。',
                    'status':'pending','createdAt':update_plan['created_at'],'target':{'objectLabel':'客户','recordLabel':update_plan['record_label']},
                    'changes':[{'fieldLabel':'沟通摘要','before':update_plan['before']['craChatSummary'],'after':update_plan['after']['craChatSummary']}],
                    'evidence':evidence,'choices':[{'id':'update_context','label':'更新客户总览摘要','description':'仅更新这位客户的沟通摘要；两个商机、订单和金额保持原值。'}],
                    'decision':None,'execution':{'status':'not_started','message':'尚未更新CRM。'},'canDecide':True,'contextUpdatePlan':update_plan}
                item['planDigest']=digest(item)
                db.execute('INSERT OR IGNORE INTO requests VALUES(?,?,?,?,?,?,?,?)',(item['id'],update_plan['task_id'],update_plan['rules_hash'],update_plan['context_hash'],encode(item),'pending',update_plan['created_at'],None))

def list_items(db,status='pending',limit=50,cursor=None):
    if status not in ('pending','approved','rejected','superseded'):raise ValueError('status')
    limit=max(1,min(50,int(limit)))
    params=[status];condition='status=?'
    if cursor:
        after=db.execute('SELECT created_at,id FROM requests WHERE id=?',(cursor,)).fetchone()
        if not after:raise ValueError('cursor')
        condition+=' AND (created_at>? OR (created_at=? AND id>?))';params.extend([after['created_at'],after['created_at'],after['id']])
    rows=db.execute('SELECT * FROM requests WHERE '+condition+' ORDER BY created_at,id LIMIT ?',[*params,limit+1]).fetchall()
    total=db.execute('SELECT count(*) FROM requests WHERE status=?',(status,)).fetchone()[0]
    return {'values':[item_public(r,db) for r in rows[:limit]],'nextCursor':rows[limit-1]['id'] if len(rows)>limit else None,'total':total}

def decide(db,identifier,input,member=MEMBER):
    if member!=MEMBER:raise PermissionError('member')
    if input.get('id')!=identifier or input.get('outcome') not in ('approved','rejected') or not isinstance(input.get('note'),str) or len(input['note'])>4000:raise ValueError('decision')
    db.execute('BEGIN IMMEDIATE')
    try:
        row=db.execute('SELECT * FROM requests WHERE id=?',(identifier,)).fetchone()
        if not row or input.get('planDigest')!=json.loads(row['payload'])['planDigest'] or row['status']=='superseded':raise Conflict('stale_plan')
        choices={c['id'] for c in json.loads(row['payload'])['choices']};chosen=input.get('selectedChoiceId')
        if input['outcome']=='rejected' and chosen is not None:raise ValueError('rejected_choice')
        if input['outcome']=='approved' and ((choices and chosen not in choices) or (not choices and chosen is not None)):raise ValueError('choice')
        if row['decision']:
            prior=json.loads(row['decision'])
            if any(prior[k]!=input[k] for k in ('outcome','note','selectedChoiceId')):raise Conflict('different_decision')
            db.commit();return {'value':item_public(row,db)}
        result={'outcome':input['outcome'],'actorLabel':'Leeyu YIHE01','decidedAt':now(),'note':input['note'],'selectedChoiceId':chosen}
        db.execute('UPDATE requests SET status=?,decision=? WHERE id=?',(input['outcome'],encode(result),identifier))
        db.execute('INSERT INTO decision_audit VALUES(?,?,?,?,?)',(digest([identifier,result]),identifier,member,now(),encode(result)))
        plan=json.loads(row['payload']).get('executionPlan')
        if input['outcome']=='approved' and input.get('selectedChoiceId')=='create_intake' and plan and enabled():
            db.execute('INSERT OR IGNORE INTO crm_intake_outbox(request_id,plan,state,updated_at) VALUES(?,?,?,?)',(identifier,encode(plan),'pending',now()))
        update_plan=json.loads(row['payload']).get('contextUpdatePlan')
        if input['outcome']=='approved' and chosen=='update_context' and update_plan and enabled():
            update_current(update_plan)
            db.execute('INSERT OR IGNORE INTO crm_update_outbox(request_id,plan,state,updated_at) VALUES(?,?,?,?)',(identifier,encode(update_plan),'pending',now()))
        db.commit()
        return {'value':item_public(db.execute('SELECT * FROM requests WHERE id=?',(identifier,)).fetchone(),db)}
    except Exception:db.rollback();raise

def errors(data=DATA):
    with closing(sqlite3.connect('file:'+str(data/'signal.sqlite3')+'?mode=ro',uri=True)) as db:
        items=[{'id':r[0],'label':'聊天分析','state':r[1],'attempts':r[2],'errorCode':r[3],
                'message':'此任务未完成，请把排查信息交给Codex；无需批准错误。'} for r in db.execute("SELECT id,state,attempts,error_code FROM analysis_tasks WHERE state IN ('failed','awaiting_retry')")]
    if (data/'review.sqlite3').exists():
        with closing(db_open(data/'review.sqlite3')) as reviews:
            items += [{'id':r[0],'label':'客户与商机建档','state':r[1],'attempts':r[2],'errorCode':r[3] or 'execution_failed','message':'建档未完成，可能已有部分记录，请交给Codex核对，不要重复新建。'} for r in reviews.execute("SELECT request_id,state,attempts,error_code FROM crm_intake_outbox WHERE state IN ('failed','conflict') OR (state='pending' AND error_code IS NOT NULL)")]
            items += [{'id':r[0],'label':'客户与商机摘要更新','state':r[1],'attempts':r[2],'errorCode':r[3] or 'update_failed','message':'摘要更新未完成或出现冲突，请交给Codex核对。'} for r in reviews.execute("SELECT request_id,state,attempts,error_code FROM crm_update_outbox WHERE state IN ('failed','conflict') OR (state='pending' AND error_code IS NOT NULL)")]
    for filename,label in [('mail-status.json','邮件采集'),('whatsapp-status.json','WhatsApp采集'),('signal-status.json','证据同步'),('r02-runtime-status.json','需求确认接入')]:
        path=data/filename
        if not path.exists():items.append({'id':filename,'label':label,'state':'unavailable','attempts':None,'errorCode':'status_missing','message':'暂时无法检查状态。'});continue
        status=json.loads(path.read_text(encoding='utf-8'))
        if status.get('status')!='ok':items.append({'id':filename,'label':label,'state':'failed','attempts':None,'errorCode':status.get('error_type','unknown'),'message':'需要Codex排查采集或同步。'})
        elif (dt.datetime.now(dt.timezone.utc).timestamp()-path.stat().st_mtime)>300:
            items.append({'id':filename,'label':label,'state':'stale','attempts':None,'errorCode':'no_recent_status','message':'超过五分钟没有新的运行状态，请检查采集任务。'})
        elif filename=='whatsapp-status.json' and status.get('connection_state')!='open':
            items.append({'id':filename,'label':label,'state':'disconnected','attempts':None,'errorCode':'whatsapp_disconnected','message':'WhatsApp当前未连接，请检查手机关联和网络。'})
    return {'values':items,'total':len(items),'checkedAt':now(),'state':'ok'}

class Handler(BaseHTTPRequestHandler):
    server_version='CRAReview'
    def log_message(self,*args):pass
    def respond(self,code,body):
        raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def authorized(self):
        cfg=self.server.review_config
        return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+cfg['CRA_REVIEW_API_TOKEN']) and self.headers.get('x-cra-workspace-id')==WORKSPACE and self.headers.get('x-cra-reviewer-id')==MEMBER
    def run_request(self,post=False):
        # Quote registrations bypass candidate refresh and the review database.
        if urllib.parse.urlparse(self.path).path.startswith('/v1/quotes/'):
            from quote_entry import handle_http
            handle_http(self,self.server.review_config,post)
            return
        if not self.authorized():self.respond(403,{'error':'unauthorized'});return
        try:
            parsed=urllib.parse.urlparse(self.path)
            with closing(db_open()) as db:
                refresh(db)
                if not post and parsed.path=='/v1/review/errors':result=errors()
                elif not post and parsed.path=='/v1/review/requests':
                    query=urllib.parse.parse_qs(parsed.query);result=list_items(db,query.get('status',['pending'])[0],query.get('limit',[50])[0],query.get('cursor',[None])[0])
                elif post and parsed.path.startswith('/v1/review/requests/') and parsed.path.endswith('/decision'):
                    size=int(self.headers.get('Content-Length',0))
                    if size<=0 or size>20000:raise ValueError('body_length')
                    result=decide(db,parsed.path.split('/')[-2],json.loads(self.rfile.read(size)))
                else:self.respond(404,{'error':'not_found'});return
            self.respond(200,result)
        except (Conflict,UpdateConflict):self.respond(409,{'error':'stale_or_conflicting_plan'})
        except (ValueError,KeyError):self.respond(400,{'error':'invalid_request'})
        except Exception:self.respond(503,{'error':'review_temporarily_unavailable'})
    def do_GET(self):self.run_request()
    def do_POST(self):self.run_request(True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bind',default='127.0.0.1');args=parser.parse_args()
    cfg=dict(line.split('=',1) for line in (ROOT/'deployment/review/.env').read_text(encoding='utf-8-sig').splitlines() if '=' in line and not line.startswith('#'))
    server=ThreadingHTTPServer((args.bind,3002),Handler);server.review_config=cfg;server.serve_forever()
