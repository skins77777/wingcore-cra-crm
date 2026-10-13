"""Adopt an executed intake identity without replaying its analyzed history."""
import json
from chat_identity import approved_intake
from signal_queue import digest, now

def adopt(db, item, review_path=None):
    plan = approved_intake(item, review_path)
    if not plan:raise ValueError('executed_approval_required')
    task = db.execute('SELECT state FROM analysis_tasks WHERE id=?',(plan['task_id'],)).fetchone()
    if not task or task[0] not in ('succeeded','succeeded_local_validation'):
        raise ValueError('source_analysis_not_successful')
    binding = {'status':'verified','person_id':item['person_id'],'verification':item['verification']}
    version = digest(binding)
    rows = db.execute('SELECT e.* FROM evidence e JOIN task_evidence t ON e.id=t.evidence_id WHERE t.task_id=?',
                      (plan['task_id'],)).fetchall()
    # Any changed revision or reassignment blocks this bounded adoption.
    if not rows or any(not r['active'] or r['channel']!='whatsapp' or r['external_identity']!=item['identity'] or
        not ((r['identity_state']=='unverified' and r['person_id'] is None) or
             (r['identity_state']=='verified' and r['person_id']==item['person_id'] and r['identity_version']==version))
        for r in rows):raise ValueError('source_identity_or_revision_changed')
    db.execute('CREATE TABLE IF NOT EXISTS identity_adoptions(request_id TEXT,evidence_id TEXT,source_task_id TEXT,person_id TEXT,old_identity_version TEXT,new_identity_version TEXT,adopted_at TEXT,PRIMARY KEY(request_id,evidence_id))')
    count = 0
    for row in rows:
        count += db.execute('INSERT OR IGNORE INTO identity_adoptions VALUES(?,?,?,?,?,?,?)',
            (item['verification']['request_id'],row['id'],plan['task_id'],item['person_id'],row['identity_version'],version,now())).rowcount
        eligibility = 'candidate_text' if row['eligibility']=='identity_unresolved' else row['eligibility']
        db.execute('UPDATE evidence SET person_id=?,identity_state=?,identity_version=?,eligibility=? WHERE id=?',
            (item['person_id'],'verified',version,eligibility,row['id']))
    # Historical task and attempt records retain their original intake identity.
    return count
