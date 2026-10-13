"""Read-only image evidence staging for verified outbound customer messages.

No model calls, CRM writes, Seen flags or outbound messages. Attachments are
content-addressed; each original send remains a separate evidence reference.
"""
import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import email
import email.policy
from email.utils import getaddresses, parsedate_to_datetime
import hashlib
import importlib.util
import imaplib
import json
from pathlib import Path
import quopri
import re
import sqlite3
import ssl

from chat_identity import resolve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'records/chat-signal'
MEDIA = DATA / 'quote-media'
MAX_BYTES = 10 * 1024 * 1024
spec = importlib.util.spec_from_file_location('mail_collector', ROOT / 'scripts/collect-mail.py')
mail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail)

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def image_parts(node, prefix=''):
    if not isinstance(node, list) or not node:
        return []
    if isinstance(node[0], list):
        result = []
        for index, child in enumerate(node):
            if not isinstance(child, list):
                break
            result.extend(image_parts(child, (prefix + '.' if prefix else '') + str(index + 1)))
        return result
    if len(node) < 7 or str(node[0]).lower() != 'image' or str(node[1]).lower() not in ('jpeg', 'png'):
        return []
    params = node[2] if isinstance(node[2], list) else []
    names = {str(params[i]).lower(): params[i + 1] for i in range(0, len(params) - 1, 2)}
    return [{'section': prefix or '1', 'mime': 'image/' + str(node[1]).lower(),
             'filename': names.get('name'), 'encoding': str(node[5]).lower(),
             'transfer_bytes': node[6]}]

def verified_recipient(headers):
    identities = set(address.strip().lower() for _, address in getaddresses([headers.get('To', '')]) if address)
    # Multiple recipients can expose or mix several customers; do not silently choose one.
    if len(identities) != 1 or headers.get('Cc', '').strip():
        return None
    identity = identities.pop()
    match = resolve('email', identity)
    return (identity, match['person_id']) if match['status'] == 'verified' else None

def connect():
    MEDIA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(MEDIA / 'media.sqlite3', timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS media (
      id TEXT PRIMARY KEY, source TEXT NOT NULL, account TEXT NOT NULL,
      source_key TEXT NOT NULL, source_revision TEXT NOT NULL, person_id TEXT NOT NULL,
      identity TEXT NOT NULL, direction TEXT NOT NULL, occurred_at TEXT,
      part TEXT NOT NULL, metadata TEXT NOT NULL, state TEXT NOT NULL,
      content_hash TEXT, local_file TEXT, downloaded_at TEXT, error_code TEXT,
      classification TEXT, classification_basis TEXT)''')
    return db

def inventory(db):
    count = 0
    with closing(sqlite3.connect('file:' + (DATA / 'mail.sqlite3').as_posix() + '?mode=ro', uri=True)) as source:
        for account, key, header_json, structure_json in source.execute(
                "SELECT account,message_key,headers,structure FROM messages WHERE direction='outbound'"):
            headers, structure = json.loads(header_json), json.loads(structure_json)
            recipient = verified_recipient(headers)
            if not recipient or headers.get('Auto-Submitted', '').lower() not in ('', 'no') or headers.get('List-ID'):
                continue
            try:
                moment = parsedate_to_datetime(headers['Date'])
                occurred_at = moment.astimezone(timezone.utc).isoformat() if moment.tzinfo else None
            except (ValueError, KeyError, TypeError, OverflowError):
                occurred_at = None
            revision = digest([headers, structure])
            for part in image_parts(structure):
                if not isinstance(part['transfer_bytes'], int) or not 0 < part['transfer_bytes'] <= MAX_BYTES:
                    continue
                identifier = digest(['email', account, key, revision, part['section']])
                metadata = {'headers': headers, 'structure': structure, 'image': part}
                count += db.execute('''INSERT OR IGNORE INTO media
                  (id,source,account,source_key,source_revision,person_id,identity,direction,
                   occurred_at,part,metadata,state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (identifier, 'email', account, key, revision, recipient[1], recipient[0],
                   'outbound', occurred_at, part['section'], json.dumps(metadata, ensure_ascii=False),
                   'discovered_unclassified')).rowcount
    db.commit()
    return count

def decode_image(payload, part):
    if len(payload) > MAX_BYTES:
        raise ValueError('transfer_size_exceeded')
    if part['encoding'] == 'base64':
        payload = base64.b64decode(re.sub(rb'\s+', b'', payload), validate=True)
    elif part['encoding'] == 'quoted-printable':
        payload = quopri.decodestring(payload)
    elif part['encoding'] not in ('7bit', '8bit', 'binary'):
        raise ValueError('unsupported_transfer_encoding')
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError('image_size_exceeded')
    # Some real mail clients label JPEG bytes as PNG. Trust only the supported
    # binary signature and preserve the declared/actual discrepancy in metadata.
    if payload.startswith(b'\x89PNG\r\n\x1a\n') and payload.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82'):
        return payload, '.png'
    if payload.startswith(b'\xff\xd8\xff') and payload.endswith(b'\xff\xd9'):
        return payload, '.jpg'
    raise ValueError('mime_signature_mismatch')

def fetch_image(mailbox, copy, metadata):
    folder, validity, uid = copy
    if mailbox.select('"' + folder + '"', readonly=True)[0] != 'OK':
        raise ValueError('readonly_folder_open_failed')
    _, values = mailbox.response('UIDVALIDITY')
    if not values or not values[0] or values[0].decode('ascii') != validity:
        raise ValueError('uidvalidity_changed')
    raw = mail.literal(mail.fetch(mailbox, uid, '(BODY.PEEK[HEADER])'))
    current = email.message_from_bytes(raw, policy=email.policy.default)
    if any(str(current.get(key, '')) != value for key, value in metadata['headers'].items()):
        raise ValueError('source_headers_changed')
    response = mail.fetch(mailbox, uid, '(BODYSTRUCTURE)')
    structure = mail.parse_structure(b' '.join(item for item in response if isinstance(item, bytes)))
    if structure != metadata['structure']:
        raise ValueError('source_structure_changed')
    part = metadata['image']
    if not re.fullmatch(r'[1-9]\d*(?:\.[1-9]\d*)*', part['section']):
        raise ValueError('invalid_part_section')
    payload = mail.literal(mail.fetch(mailbox, uid, '(BODY.PEEK[' + part['section'] + ']<0.' + str(MAX_BYTES + 1) + '>)'))
    if len(payload) != part['transfer_bytes']:
        raise ValueError('incomplete_image_transfer')
    return decode_image(payload, part)

def download(db, identifier):
    row = db.execute('SELECT * FROM media WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise ValueError('unknown_media_id')
    match = resolve('email', row['identity'])
    if row['direction'] != 'outbound' or match['status'] != 'verified' or match['person_id'] != row['person_id']:
        raise ValueError('identity_binding_changed')
    if row['content_hash']:
        path = MEDIA / row['local_file']
        if path.parent != MEDIA or hashlib.sha256(path.read_bytes()).hexdigest() != row['content_hash']:
            raise ValueError('cached_image_integrity_failed')
        return {'id': identifier, 'state': row['state'], 'cached': True, 'local_file': str(path)}
    cfg = mail.config()
    if cfg['MAIL_ADDRESS'] != row['account']:
        raise ValueError('source_account_changed')
    with closing(sqlite3.connect('file:' + (DATA / 'mail.sqlite3').as_posix() + '?mode=ro', uri=True)) as source:
        copy = source.execute('SELECT folder,validity,uid FROM copies WHERE account=? AND message_key=? ORDER BY uid LIMIT 1',
                              (row['account'], row['source_key'])).fetchone()
    if not copy:
        raise ValueError('source_copy_missing')
    with imaplib.IMAP4_SSL(cfg['IMAP_HOST'], int(cfg['IMAP_PORT']), ssl_context=ssl.create_default_context(), timeout=30) as mailbox:
        mailbox.login(cfg['MAIL_ADDRESS'], cfg['IMAP_AUTHORIZATION_CODE'])
        _, capabilities = mailbox.capability()
        if any(b'ID' in item.split() for item in capabilities if item):
            imaplib.Commands.setdefault('ID', ('NONAUTH', 'AUTH', 'SELECTED'))
            if mailbox._simple_command('ID', '("name" "Wingcore CRM" "version" "1.0" "vendor" "YIHE" "contact" "wingcore2026@163.com")')[0] != 'OK':
                raise ValueError('imap_id_failed')
        payload, extension = fetch_image(mailbox, copy, json.loads(row['metadata']))
    content_hash = hashlib.sha256(payload).hexdigest()
    filename = content_hash + extension
    path = MEDIA / filename
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError('content_hash_collision_or_corruption')
    else:
        path.write_bytes(payload)
    metadata = json.loads(row['metadata'])
    metadata['actual_mime'] = 'image/png' if extension == '.png' else 'image/jpeg'
    metadata['declared_mime_matches'] = metadata['actual_mime'] == metadata['image']['mime']
    db.execute('UPDATE media SET state=?,content_hash=?,local_file=?,downloaded_at=?,error_code=NULL,metadata=? WHERE id=?',
               ('downloaded_unclassified', content_hash, filename, now(), json.dumps(metadata, ensure_ascii=False), identifier))
    db.commit()
    return {'id': identifier, 'state': 'downloaded_unclassified', 'cached': False, 'local_file': str(path)}

def exclude_inspected_nonquote(db, content_hash, reason):
    """Local operator inspection only; never derive this decision from a filename."""
    if not re.fullmatch(r'[0-9a-f]{64}', content_hash) or not reason.strip():
        raise ValueError('inspection_basis_required')
    rows = db.execute('SELECT * FROM media WHERE content_hash=?', (content_hash,)).fetchall()
    if not rows:
        raise ValueError('downloaded_image_required')
    for row in rows:
        path = MEDIA / row['local_file']
        if path.parent != MEDIA or hashlib.sha256(path.read_bytes()).hexdigest() != content_hash:
            raise ValueError('cached_image_integrity_failed')
    basis = json.dumps({'method': 'local_visual_inspection', 'reason': reason,
                        'checked_at': now(), 'content_hash': content_hash}, ensure_ascii=False)
    db.execute('UPDATE media SET classification=?,classification_basis=?,state=? WHERE content_hash=?',
               ('not_quotation', basis, 'excluded_nonquote', content_hash))
    db.commit()
    return len(rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', help='Download only this exact staged evidence ID')
    args = parser.parse_args()
    with closing(connect()) as db:
        if args.download:
            try:
                print(json.dumps(download(db, args.download), ensure_ascii=True))
            except Exception as exc:
                code = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                db.execute('UPDATE media SET error_code=? WHERE id=?', (code, args.download))
                db.commit()
                print(json.dumps({'id': args.download, 'status': 'error', 'error_code': code}))
                return 1
        else:
            created = inventory(db)
            rows = [{'id': row['id'], 'state': row['state'], 'occurred_at': row['occurred_at'],
                     'filename': json.loads(row['metadata'])['image']['filename']}
                    for row in db.execute('SELECT * FROM media ORDER BY occurred_at,id')]
            print(json.dumps({'new_references': created, 'references': rows, 'model_calls': 0, 'crm_writes': 0}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
