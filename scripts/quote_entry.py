"""Manual quote registration MVP. No chat, model, task or quote-history APIs.

The lock database serializes execution across threads/processes, releases on
process death, and lets the registration database commit before remote writes.
"""
import argparse
from contextlib import closing, contextmanager
import datetime as dt
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'records/quote-entry/registration.sqlite3'
FIELDS = ('craT1QuoteRound', 'craT1QuoteSentAt', 'craT1QuoteEvidence')
READ_FIELDS = ('id', 'updatedAt', 'deletedAt', *FIELDS)
STATUSES = ('unknown', 'not_quoted', 'draft', 'sent')
CHANNELS = {'whatsapp': 'WhatsApp', 'email': 'Email', 'alibaba': '阿里平台', 'other': '其他'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class QuoteError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def identifier(value):
    if not isinstance(value, str):
        raise QuoteError('invalid_identifier', 400)
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise QuoteError('invalid_identifier', 400) from None


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise QuoteError('invalid_timestamp', 400)
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        raise QuoteError('invalid_timestamp', 400) from None


def text_field(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise QuoteError('invalid_' + name, 400)
    return value.strip()


def validate(body):
    allowed = {'submissionId', 'opportunityId', 'status', 'expectedUpdatedAt',
               'quoteRound', 'sentAt', 'channel', 'channelDetail', 'evidence'}
    if not isinstance(body, dict) or set(body) - allowed:
        raise QuoteError('invalid_request_fields', 400)
    result = {key: identifier(body.get(key)) for key in ('submissionId', 'opportunityId')}
    status = body.get('status')
    if status not in STATUSES:
        raise QuoteError('invalid_quote_status', 400)
    result['status'] = status
    if status != 'sent':
        if set(body) - {'submissionId', 'opportunityId', 'status'}:
            raise QuoteError('unsent_has_sent_fields', 400)
        return result
    result['quoteRound'] = text_field(body.get('quoteRound'), 'quote_round', 120)
    result['sentAt'] = timestamp(body.get('sentAt')).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    if timestamp(result['sentAt']) > timestamp(now()):
        raise QuoteError('sent_at_in_future', 400)
    channel = body.get('channel')
    if not isinstance(channel, str) or channel not in CHANNELS:
        raise QuoteError('invalid_channel', 400)
    result['channel'] = channel
    result['evidence'] = text_field(body.get('evidence'), 'evidence', 4000)
    if channel == 'other':
        result['channelDetail'] = text_field(body.get('channelDetail'), 'channel_detail', 120)
    elif body.get('channelDetail') is not None:
        raise QuoteError('unexpected_channel_detail', 400)
    result['expectedUpdatedAt'] = text_field(body.get('expectedUpdatedAt'), 'expected_updated_at', 40)
    timestamp(result['expectedUpdatedAt'])
    return result


def target_fields(body):
    channel = CHANNELS[body['channel']]
    if body['channel'] == 'other':
        channel += '（' + body['channelDetail'] + '）'
    return dict(zip(FIELDS, (body['quoteRound'], body['sentAt'], channel + '｜' + body['evidence'])))


def agrees(record, expected):
    if not record or record.get('deletedAt'):
        return False
    for key, value in expected.items():
        actual = record.get(key)
        if key == 'craT1QuoteSentAt' and value is not None:
            try:
                if timestamp(actual) != timestamp(value):
                    return False
            except QuoteError:
                return False
        elif actual != value:
            return False
    return True


class NoQuoteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise QuoteError('twenty_redirect_denied', 502)


class QuoteRemote:
    """Backend-only key; six read fields and exactly three writable fields.

    Twenty may include its mandatory record label in REST responses. Never
    return the raw upstream record beyond this adapter or send caller fields.
    """
    def __init__(self, token, url='http://127.0.0.1:3000'):
        self.token, self.url = token, url.rstrip('/')

    def call(self, method, path, body=None):
        request = urllib.request.Request(self.url + '/rest/' + path, method=method,
            data=encode(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoQuoteRedirect()).open(request, timeout=15) as response:
            return json.load(response)

    def read(self, opportunity_id):
        try:
            result = self.call('GET', 'opportunities/' + identifier(opportunity_id))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        record = result.get('data', {}).get('opportunity')
        if (not isinstance(record, dict) or record.get('id') != opportunity_id or
                any(key not in record for key in READ_FIELDS)):
            raise QuoteError('unexpected_read_response', 502)
        return {key: record[key] for key in READ_FIELDS}

    def update(self, opportunity_id, expected_updated_at, fields):
        if set(fields) != set(FIELDS):
            raise QuoteError('write_field_scope', 400)
        opportunity_id = identifier(opportunity_id)
        timestamp(expected_updated_at)
        expression = 'and(id[eq]:' + opportunity_id + ',updatedAt[eq]:' + expected_updated_at + ')'
        response = self.call('PATCH', 'opportunities?' + urllib.parse.urlencode({'filter': expression}), fields)
        records = response.get('data', {}).get('updateOpportunities')
        if records == []:
            raise QuoteError('remote_version_conflict')
        if not isinstance(records, list) or len(records) != 1 or records[0].get('id') != opportunity_id:
            raise QuoteError('unexpected_update_response', 502)


def open_store(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS submissions (
        submission_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL,
        actor_id TEXT NOT NULL, quote_status TEXT NOT NULL, payload TEXT NOT NULL,
        payload_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, plan TEXT,
        result TEXT, error_code TEXT);
      CREATE INDEX IF NOT EXISTS submissions_target ON submissions(opportunity_id, state);
      CREATE TABLE IF NOT EXISTS latest (
        opportunity_id TEXT PRIMARY KEY, registration_id TEXT NOT NULL, sent_id TEXT);
    ''')
    return db


@contextmanager
def execution_lock(path):
    # No expiring lease: an older in-flight worker cannot write after a takeover.
    # This small MVP serializes all quote executions, including across processes.
    with closing(sqlite3.connect(str(path) + '.lock.sqlite3', timeout=20)) as lock:
        try:
            lock.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError:
            raise QuoteError('registration_busy', 503) from None
        try:
            yield
        finally:
            lock.rollback()


class QuoteService:
    def __init__(self, remote, members, path=STORE):
        self.remote, self.members, self.path = remote, members, Path(path)

    def authorize(self, actor, opportunity_id):
        actor = identifier(actor)
        scope = self.members.get(actor, [])
        if scope != '*' and opportunity_id not in scope:
            raise QuoteError('quote_permission_denied', 403)
        return actor

    def current(self, opportunity_id):
        record = self.remote.read(opportunity_id)
        if not record or record.get('deletedAt'):
            raise QuoteError('opportunity_not_found', 404)
        if record.get('id') != opportunity_id:
            raise QuoteError('unexpected_read_response', 502)
        return record

    @staticmethod
    def public(row):
        payload = json.loads(row['payload'])
        return {'submissionId': row['submission_id'], 'opportunityId': row['opportunity_id'],
                'status': row['quote_status'], 'registeredBy': row['actor_id'],
                'registeredAt': row['created_at'], 'updatedAt': row['updated_at'],
                'processingState': row['state'], 'attempts': row['attempts'],
                'retryable': row['state'] in ('pending', 'applying', 'retryable'),
                'errorCode': row['error_code'],
                'quoteFact': {key: payload[key] for key in ('quoteRound', 'sentAt', 'channel', 'channelDetail', 'evidence') if key in payload},
                'result': json.loads(row['result']) if row['result'] else None}

    def get(self, opportunity_id, actor, submission_id=None):
        opportunity_id = identifier(opportunity_id)
        self.authorize(actor, opportunity_id)
        current = self.current(opportunity_id)
        with closing(open_store(self.path)) as db:
            if submission_id:
                row = db.execute('SELECT * FROM submissions WHERE submission_id=? AND opportunity_id=?',
                                 (identifier(submission_id), opportunity_id)).fetchone()
                if not row:
                    raise QuoteError('submission_not_found', 404)
                return {'value': self.public(row)}
            pointers = db.execute('SELECT * FROM latest WHERE opportunity_id=?', (opportunity_id,)).fetchone()
            def registration(key):
                row = db.execute('SELECT * FROM submissions WHERE submission_id=?', (pointers[key],)).fetchone() if pointers and pointers[key] else None
                return self.public(row) if row else None
            return {'opportunityId': opportunity_id, 'expectedUpdatedAt': current.get('updatedAt'),
                    't1Fields': {key: current.get(key) for key in FIELDS},
                    'latestRegistration': registration('registration_id'),
                    'lastVerifiedSent': registration('sent_id')}

    def submit(self, body, actor):
        body = validate(body)
        actor = self.authorize(actor, body['opportunityId'])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with execution_lock(self.path), closing(open_store(self.path)) as db:
            row = db.execute('SELECT * FROM submissions WHERE submission_id=?', (body['submissionId'],)).fetchone()
            payload_hash = hashlib.sha256(encode(body).encode()).hexdigest()
            if row:
                if row['actor_id'] != actor or row['payload_hash'] != payload_hash:
                    raise QuoteError('submission_id_conflict')
                if row['state'] in ('succeeded', 'conflict', 'rejected'):
                    return {'value': self.public(row), 'replayed': True}
            else:
                self.current(body['opportunityId'])
                if body['status'] == 'sent' and db.execute(
                    "SELECT 1 FROM submissions WHERE opportunity_id=? AND state IN ('pending','applying','retryable')",
                    (body['opportunityId'],)).fetchone():
                    raise QuoteError('earlier_submission_unresolved')
                with db:
                    stamp = now()
                    db.execute('''INSERT INTO submissions(submission_id,opportunity_id,actor_id,quote_status,
                        payload,payload_hash,created_at,updated_at,state) VALUES(?,?,?,?,?,?,?,?,?)''',
                        (body['submissionId'], body['opportunityId'], actor, body['status'], encode(body),
                         payload_hash, stamp, stamp, 'pending'))
                    db.execute('''INSERT INTO latest(opportunity_id,registration_id) VALUES(?,?)
                        ON CONFLICT(opportunity_id) DO UPDATE SET registration_id=excluded.registration_id''',
                        (body['opportunityId'], body['submissionId']))
            with db:
                db.execute('UPDATE submissions SET attempts=attempts+1,updated_at=? WHERE submission_id=?',
                           (now(), body['submissionId']))
            try:
                result = self.process(db, body)
                with db:
                    db.execute("UPDATE submissions SET state='succeeded',result=?,error_code=NULL,updated_at=? WHERE submission_id=?",
                               (encode(result), now(), body['submissionId']))
                    if body['status'] == 'sent':
                        db.execute('UPDATE latest SET sent_id=? WHERE opportunity_id=?',
                                   (body['submissionId'], body['opportunityId']))
            except Exception as exc:
                if isinstance(exc, QuoteError):
                    state = 'retryable' if exc.status >= 500 else 'conflict' if exc.status == 409 else 'rejected'
                    code = exc.code
                elif isinstance(exc, urllib.error.HTTPError):
                    state = 'retryable' if exc.code in (401, 403, 429) or exc.code >= 500 else 'rejected'
                    code = 'twenty_http_' + str(exc.code)
                elif isinstance(exc, (OSError, TimeoutError)):
                    state, code = 'retryable', 'twenty_unavailable'
                else:
                    # Preserve uncertain executions. Do not disclose upstream bodies or keys.
                    state, code = 'retryable', 'processing_unavailable'
                with db:
                    db.execute('UPDATE submissions SET state=?,error_code=?,updated_at=? WHERE submission_id=?',
                               (state, code, now(), body['submissionId']))
            row = db.execute('SELECT * FROM submissions WHERE submission_id=?', (body['submissionId'],)).fetchone()
            return {'value': self.public(row), 'replayed': False}

    def process(self, db, body):
        current = self.current(body['opportunityId'])
        if body['status'] != 'sent':
            return {'action': 'registered_only', 't1Updated': False}
        after = target_fields(body)
        row = db.execute('SELECT plan FROM submissions WHERE submission_id=?', (body['submissionId'],)).fetchone()
        plan = json.loads(row['plan']) if row['plan'] else None
        if agrees(current, after):
            return {'action': 'recovered_readback' if plan else 'already_satisfied',
                    't1Updated': bool(plan), 'verifiedAt': now(), 'verifiedFields': after}
        if plan:
            if current.get('updatedAt') != plan['expectedUpdatedAt'] or not agrees(current, plan['before']):
                raise QuoteError('remote_version_conflict')
        else:
            if current.get('updatedAt') != body['expectedUpdatedAt']:
                raise QuoteError('remote_version_conflict')
            previous_round = current.get(FIELDS[0])
            if previous_round == body['quoteRound']:
                raise QuoteError('same_round_different_facts')
            previous_time = current.get(FIELDS[1])
            if previous_time:
                try:
                    old_time = timestamp(previous_time)
                except QuoteError:
                    raise QuoteError('existing_quote_time_invalid') from None
                if timestamp(body['sentAt']) <= old_time:
                    raise QuoteError('quote_not_newer')
            plan = {'expectedUpdatedAt': current['updatedAt'],
                    'before': {key: current.get(key) for key in FIELDS}, 'after': after}
            with db:
                db.execute("UPDATE submissions SET state='applying',plan=?,updated_at=? WHERE submission_id=?",
                           (encode(plan), now(), body['submissionId']))
        # No automatic retry inside the HTTP client. A retry uses this durable plan.
        try:
            self.remote.update(body['opportunityId'], plan['expectedUpdatedAt'], after)
        except Exception:
            current = self.current(body['opportunityId'])
            if agrees(current, after):
                return {'action': 'recovered_readback', 't1Updated': True,
                        'verifiedAt': now(), 'verifiedFields': after}
            raise
        current = self.current(body['opportunityId'])
        if not agrees(current, after):
            raise QuoteError('readback_mismatch', 502)
        return {'action': 'updated', 't1Updated': True, 'verifiedAt': now(), 'verifiedFields': after}


def service_from_config(cfg):
    if cfg.get('CRA_QUOTE_ENABLED') != 'true':
        raise QuoteError('quote_module_disabled', 503)
    try:
        if identifier(cfg['CRA_QUOTE_WORKSPACE_ID']) != cfg['CRA_QUOTE_WORKSPACE_ID']:
            raise ValueError()
        members = json.loads(cfg['CRA_QUOTE_MEMBER_SCOPES'])
        if not isinstance(members, dict) or not members or not cfg['CRA_QUOTE_API_KEY']:
            raise ValueError()
        for actor, scope in members.items():
            if identifier(actor) != actor or (scope != '*' and (not isinstance(scope, list) or
                    not scope or any(identifier(x) != x for x in scope))):
                raise ValueError()
    except (KeyError, ValueError, QuoteError):
        raise QuoteError('quote_configuration_invalid', 503) from None
    return QuoteService(QuoteRemote(cfg['CRA_QUOTE_API_KEY']), members)


def handle_http(handler, cfg, post):
    """Trusted server-to-server gateway. Actor headers come from Twenty context."""
    token = cfg.get('CRA_QUOTE_API_TOKEN', '')
    actor = handler.headers.get('x-cra-member-id', '')
    if not token or not hmac.compare_digest(handler.headers.get('Authorization', ''), 'Bearer ' + token):
        handler.respond(403, {'error': 'unauthorized'})
        return
    if handler.headers.get('x-cra-workspace-id') != cfg.get('CRA_QUOTE_WORKSPACE_ID'):
        handler.respond(403, {'error': 'workspace_denied'})
        return
    try:
        service = service_from_config(cfg)
        parsed = urllib.parse.urlparse(handler.path)
        if post and parsed.path == '/v1/quotes/registrations' and not parsed.query:
            size = int(handler.headers.get('Content-Length', '0'))
            if size <= 0 or size > 24000:
                raise QuoteError('invalid_body_length', 400)
            result = service.submit(json.loads(handler.rfile.read(size)), actor)
            state = result['value']['processingState']
            code = 200 if state == 'succeeded' else 503 if result['value']['retryable'] else 409 if state == 'conflict' else 422
        elif not post and parsed.path.startswith('/v1/quotes/opportunities/'):
            parts = parsed.path.split('/')
            if len(parts) != 5:
                raise QuoteError('not_found', 404)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if set(query) - {'submissionId'} or any(len(v) != 1 for v in query.values()):
                raise QuoteError('invalid_query', 400)
            result = service.get(parts[4], actor, query.get('submissionId', [None])[0])
            code = 200
        else:
            raise QuoteError('not_found', 404)
        handler.respond(code, result)
    except QuoteError as exc:
        handler.respond(exc.status, {'error': exc.code})
    except (ValueError, TypeError):
        handler.respond(400, {'error': 'invalid_request'})
    except Exception:
        handler.respond(503, {'error': 'quote_temporarily_unavailable'})


def backup(destination, path=STORE):
    """SQLite online snapshot; never copy a database with uncheckpointed journals."""
    if not Path(path).exists():
        return False
    with closing(sqlite3.connect('file:' + Path(path).as_posix() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['backup'])
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    backup(args.destination)
