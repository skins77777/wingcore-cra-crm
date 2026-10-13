"""Read-only Evolution snapshots. No marking read, media download, AI or CRM write.

Reconcile the currently available API records every run, retaining changed content
as revisions. This cannot prove complete phone history or capture deletions that
the API no longer returns; protocol records remain explicitly unresolved.
"""
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'records/chat-signal'
INSTANCE = 'wingcore-business'
OWNER = '8615361615301@s.whatsapp.net'
BASE = 'http://127.0.0.1:8082'

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def api(path, config, payload=None):
    request = urllib.request.Request(BASE + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'apikey': config['AUTHENTICATION_API_KEY'],
                 'Content-Type': 'application/json', 'Origin': 'http://localhost:8082'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS wa_versions (
      account TEXT, message_key TEXT, revision TEXT, chat TEXT, external_id TEXT,
      direction TEXT, occurred_at INTEGER, message_type TEXT, text TEXT,
      evidence TEXT, completeness TEXT, first_seen TEXT,
      PRIMARY KEY(account,message_key,revision));
    CREATE TABLE IF NOT EXISTS wa_current (
      account TEXT, message_key TEXT, revision TEXT, last_seen TEXT,
      PRIMARY KEY(account,message_key));
    CREATE TABLE IF NOT EXISTS wa_runs (
      started TEXT PRIMARY KEY, finished TEXT, status TEXT, source_count INTEGER,
      new_versions INTEGER, connection_state TEXT);
    ''')

def normalize(row):
    key = row['key']
    if not isinstance(key.get('fromMe'), bool) or not key.get('id') or not key.get('remoteJid'):
        raise ValueError('Unsupported message identity')
    if key['remoteJid'].endswith('@g.us') or key['remoteJid'] == 'status@broadcast':
        return None
    body = row.get('message') or {}
    message_type = row.get('messageType', 'unknown')
    text = body.get('conversation', '')
    if not text:
        text = body.get('extendedTextMessage', {}).get('text', '')
    if not text:
        text = (body.get('imageMessage') or body.get('videoMessage') or
                body.get('documentMessage') or {}).get('caption', '')
    timestamp = row.get('messageTimestamp')
    if isinstance(timestamp, str) and timestamp.isdigit():
        timestamp = int(timestamp)
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        timestamp = None
    completeness = ('revision_event_unresolved' if message_type == 'protocolMessage' else
                    'media_not_downloaded' if message_type in ('imageMessage','videoMessage','documentMessage','audioMessage','stickerMessage') else
                    'text_available' if text else 'unsupported_content')
    evidence = {'key': key, 'message': body, 'messageType': message_type,
                'messageTimestamp': timestamp, 'contextInfo': row.get('contextInfo')}
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    identity = json.dumps([key['remoteJid'], key['fromMe'], key['id']], separators=(',', ':'))
    return (identity, hashlib.sha256(serialized.encode()).hexdigest(), key['remoteJid'],
            key['id'], 'outbound' if key['fromMe'] else 'inbound', timestamp,
            message_type, text, serialized, completeness)

def save_rows(db, rows):
    new = 0
    observed = now()
    for row in rows:
        normalized = normalize(row)
        if normalized is None:
            continue
        new += db.execute('INSERT OR IGNORE INTO wa_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                          (INSTANCE, *normalized, observed)).rowcount
        db.execute('INSERT OR REPLACE INTO wa_current VALUES(?,?,?,?)',
                   (INSTANCE, normalized[0], normalized[1], observed))
    return new

def run():
    DATA.mkdir(parents=True, exist_ok=True)
    config = dict(line.split('=', 1) for line in
        (ROOT / 'deployment/evolution/.env').read_text(encoding='utf-8-sig').splitlines()
        if '=' in line and not line.lstrip().startswith('#'))
    started = now()
    connection = api('/instance/connectionState/' + INSTANCE, config)['instance']['state']
    instances = api('/instance/fetchInstances', config)
    verified = [item for item in instances if item.get('name') == INSTANCE and item.get('ownerJid') == OWNER]
    if len(verified) != 1:
        raise ValueError('Account identity mismatch')
    rows = []
    expected = None
    for page in range(1, 101):
        response = api('/chat/findMessages/' + INSTANCE, config,
                       {'where': {}, 'page': page, 'offset': 100})['messages']
        if not isinstance(response.get('records'), list) or response.get('currentPage') != page:
            raise ValueError('Unsupported pagination')
        if expected is None:
            expected = response['total']
        elif response['total'] != expected:
            raise ValueError('Snapshot changed; retry next scheduled run')
        rows.extend(response['records'])
        if page >= max(1, response['pages']):
            break
    else:
        raise ValueError('Snapshot exceeds supported page count')
    if len(rows) != expected:
        raise ValueError('Incomplete snapshot')
    identities = [normalize(row)[0] for row in rows if normalize(row) is not None]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate pagination identities')
    with sqlite3.connect(DATA / 'whatsapp.sqlite3', timeout=30) as db:
        initialize(db)
        with db:
            new = save_rows(db, rows)
            db.execute('INSERT INTO wa_runs VALUES(?,?,?,?,?,?)',
                       (started, now(), 'ok', len(rows), new, connection))
        counts = dict(db.execute('SELECT direction,count(*) FROM wa_versions v JOIN wa_current c USING(account,message_key,revision) GROUP BY direction'))
        unresolved = db.execute("SELECT count(*) FROM wa_versions v JOIN wa_current c USING(account,message_key,revision) WHERE completeness='revision_event_unresolved'").fetchone()[0]
    status = {'status': 'ok', 'started_at': started, 'finished_at': now(),
              'connection_state': connection, 'source_records': len(rows),
              'new_versions': new, 'current_by_direction': counts,
              'unresolved_protocol_records': unresolved,
              'history_completeness': 'not_proven', 'deletion_capture': 'not_verified',
              'model_calls': 0, 'crm_writes': 0}
    (DATA / 'whatsapp-status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    print(json.dumps(status))

if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        DATA.mkdir(parents=True, exist_ok=True)
        status = {'status':'error', 'error_type':type(error).__name__, 'failed_at':now()}
        (DATA / 'whatsapp-status.json').write_text(json.dumps(status), encoding='utf-8')
        print(json.dumps(status))
        sys.exit(1)
