"""Exact, human-verified identity lookup; never infer identity from display names."""
import json
import pathlib
import sqlite3
from contextlib import closing

ROOT = pathlib.Path(__file__).resolve().parents[1]

def approved_intake(item, review_path=None):
    """Trust an exact approved and executed plan, never a JSON source label alone."""
    path = review_path or ROOT / 'records/chat-signal/review.sqlite3'
    try:
        with closing(sqlite3.connect('file:'+path.as_posix()+'?mode=ro', uri=True)) as db:
            row = db.execute('SELECT status,decision,payload FROM requests WHERE id=?',
                             (item['verification']['request_id'],)).fetchone()
            if not row or row[0]!='approved' or json.loads(row[1]).get('selectedChoiceId')!='create_intake':return None
            plan = json.loads(row[2])['executionPlan']
            outbox = db.execute('SELECT state,plan FROM crm_intake_outbox WHERE request_id=?',
                                (item['verification']['request_id'],)).fetchone()
            if not outbox or outbox[0]!='succeeded' or json.loads(outbox[1])!=plan:return None
            person = plan['operations'][0]
            if (item['channel']!='whatsapp' or person['collection']!='people' or
                person['id']!=item['person_id'] or person['body']['craWhatsappIdentity']!=item['identity']):return None
            for op in plan['operations']:
                readback = db.execute('SELECT payload FROM crm_intake_readback WHERE request_id=? AND record_id=?',
                                      (item['verification']['request_id'],op['id'])).fetchone()
                if not readback:return None
                record = json.loads(readback[0])
                if record.get('deletedAt') or any(record.get(k)!=v for k,v in op['body'].items()):return None
            return plan
    except (OSError, sqlite3.Error, KeyError, ValueError, TypeError):
        return None

def resolve(channel, identity, path=None, review_path=None):
    path = path or ROOT / 'records/chat-signal/identity-bindings.json'
    if not path.exists():
        return {'status': 'unverified', 'person_id': None}
    data = json.loads(path.read_text(encoding='utf-8'))
    normalized = identity.strip().lower() if channel == 'email' else identity.strip()
    matches = [item for item in data['bindings']
               if item['channel'] == channel and item['identity'] == normalized
               and (item['verification']['source'] == 'human_confirmation' or
                    (item['verification']['source']=='crm_review_approval' and approved_intake(item, review_path)))
               and item.get('active') is True]
    ids = {item['person_id'] for item in matches}
    if len(ids) > 1:
        return {'status': 'conflict', 'person_id': None}
    if not ids:
        return {'status': 'unverified', 'person_id': None}
    return {'status': 'verified', 'person_id': ids.pop(),
            'verification': matches[0]['verification']}
