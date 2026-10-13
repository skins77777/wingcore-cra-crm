"""Local read-only IMAP ingestion. No SMTP, model calls or CRM writes."""
import base64
import datetime as dt
import email
import email.policy
import hashlib
import html.parser
import imaplib
import json
import pathlib
import quopri
import re
import sqlite3
import ssl
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'records/chat-signal'
START_DATE = '11-Sep-2026'  # User approved last 30 days on 2026-10-11 (Hong Kong).
MAX_TEXT_BYTES = 1024 * 1024

def config():
    values = {}
    for line in (ROOT / 'deployment/mail/.env').read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip()
    return values

def parse_structure(data):
    """Parse the nested IMAP BODYSTRUCTURE, rejecting unsupported literal strings."""
    position = data.upper().index(b'BODYSTRUCTURE') + len(b'BODYSTRUCTURE')
    tokens = re.findall(rb'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', data[position:])
    def parse(index):
        token = tokens[index]
        if token == b'(':
            result = []
            index += 1
            while tokens[index] != b')':
                item, index = parse(index)
                result.append(item)
            return result, index + 1
        if token.startswith(b'{'):
            raise ValueError('unsupported BODYSTRUCTURE literal')
        if token.startswith(b'"'):
            return re.sub(rb'\\(.)', rb'\1', token[1:-1]).decode('utf-8', 'replace'), index + 1
        if token.upper() == b'NIL':
            return None, index + 1
        if token.isdigit():
            return int(token), index + 1
        return token.decode('ascii', 'replace'), index + 1
    return parse(0)[0]

def text_parts(node, prefix=''):
    if not isinstance(node, list) or not node:
        return []
    if isinstance(node[0], list):
        result = []
        for i, child in enumerate(node):
            if not isinstance(child, list):
                break
            result.extend(text_parts(child, (prefix + '.' if prefix else '') + str(i + 1)))
        return result
    # Attached text files are attachments, not the message body.
    if len(node) < 7 or str(node[0]).upper() != 'TEXT':
        return []
    for extension in node[8:]:
        if isinstance(extension, list) and extension and str(extension[0]).upper() == 'ATTACHMENT':
            return []
    params = node[2] if isinstance(node[2], list) else []
    charset = 'utf-8'
    for i in range(0, len(params) - 1, 2):
        if str(params[i]).upper() == 'CHARSET':
            charset = params[i + 1] or 'utf-8'
    return [{'section': prefix or '1', 'subtype': str(node[1]).lower(),
             'charset': charset, 'encoding': str(node[5]).lower(), 'bytes': node[6]}]

class HtmlText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.suppressed = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.suppressed += 1
        if tag in ('br', 'p', 'div', 'li', 'tr'):
            self.output.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.suppressed:
            self.suppressed -= 1
    def handle_data(self, value):
        if not self.suppressed:
            self.output.append(value)

def literal(response):
    chunks = [item[1] for item in response if isinstance(item, tuple) and isinstance(item[1], bytes)]
    if len(chunks) != 1:
        raise ValueError('unexpected IMAP literal response')
    return chunks[0]

def fetch(mailbox, uid, request):
    status, response = mailbox.uid('FETCH', str(uid), request)
    if status != 'OK':
        raise RuntimeError('IMAP FETCH failed')
    return response

def decode_part_with_status(payload, part):
    """Decode one MIME text part and report character decoding problems."""
    if part['encoding'] == 'base64':
        payload = base64.b64decode(payload, validate=False)
    elif part['encoding'] == 'quoted-printable':
        payload = quopri.decodestring(payload)
    decode_error = False
    try:
        decoded = payload.decode(part['charset'])
    except UnicodeDecodeError:
        decode_error = True
        decoded = payload.decode(part['charset'], errors='replace')
    except LookupError:
        decode_error = True
        decoded = payload.decode('utf-8', errors='replace')
    if part['subtype'] == 'html':
        parser = HtmlText()
        parser.feed(decoded)
        decoded = ''.join(parser.output)
    if '\ufffd' in decoded:
        decode_error = True
    return decoded, decode_error

def decode_part(payload, part):
    """Compatibility wrapper returning only decoded text."""
    return decode_part_with_status(payload, part)[0]

def text_completeness(parts, decode_errors):
    """Return the collector status; truncation keeps precedence over decode errors."""
    if not parts:
        return 'no_supported_text'
    if any(isinstance(part['bytes'], int) and part['bytes'] > MAX_TEXT_BYTES for part in parts):
        return 'text_truncated'
    if any(decode_errors):
        return 'text_decode_error'
    return 'text_only'

def open_database():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'mail.sqlite3', timeout=15)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS folder_cursor(account TEXT, folder TEXT, validity TEXT, uid INTEGER,
        PRIMARY KEY(account,folder));
      CREATE TABLE IF NOT EXISTS messages(account TEXT, message_key TEXT, message_id TEXT,
        direction TEXT, headers TEXT, text TEXT, structure TEXT, completeness TEXT, collected_at TEXT,
        PRIMARY KEY(account,message_key));
      CREATE TABLE IF NOT EXISTS copies(account TEXT, folder TEXT, validity TEXT, uid INTEGER,
        message_key TEXT, PRIMARY KEY(account,folder,validity,uid));
    ''')
    return db

def run():
    values = config()
    secret = values.get('IMAP_AUTHORIZATION_CODE')
    if not secret:
        raise RuntimeError('mail credentials not configured')
    account = values['MAIL_ADDRESS']
    stats = {'service': 'CRA-Wingcore-Mail', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
             'history_since': START_DATE, 'new_messages': 0, 'new_copies': 0, 'folders': [],
             'attachments_downloaded': 0, 'crm_writes': 0, 'model_calls': 0}
    with open_database() as db, imaplib.IMAP4_SSL(values['IMAP_HOST'], int(values['IMAP_PORT']),
                    ssl_context=ssl.create_default_context(), timeout=30) as mailbox:
        mailbox.login(account, secret)
        _, capabilities = mailbox.capability()
        if any(b'ID' in item.split() for item in capabilities if item):
            imaplib.Commands.setdefault('ID', ('NONAUTH', 'AUTH', 'SELECTED'))
            result, _ = mailbox._simple_command('ID', '("name" "Wingcore CRM" "version" "1.0" "vendor" "YIHE" "contact" "wingcore2026@163.com")')
            if result != 'OK':
                raise RuntimeError('IMAP ID failed')
        status, folders = mailbox.list()
        if status != 'OK':
            raise RuntimeError('LIST failed')
        sent = []
        for folder in folders:
            if folder and b'\\Sent' in folder:
                match = re.search(rb'"([^"\\]*)"\s*$', folder)
                if match:
                    sent.append(match.group(1).decode('ascii'))
        if len(sent) != 1:
            raise RuntimeError('sent folder mapping ambiguous')
        for folder, direction in [('INBOX', 'inbound'), (sent[0], 'outbound')]:
            status, _ = mailbox.select('"' + folder + '"', readonly=True)
            if status != 'OK':
                raise RuntimeError('EXAMINE failed')
            _, validity_data = mailbox.response('UIDVALIDITY')
            if not validity_data or not validity_data[0]:
                raise RuntimeError('UIDVALIDITY missing')
            validity = validity_data[0].decode('ascii')
            cursor = db.execute('SELECT validity,uid FROM folder_cursor WHERE account=? AND folder=?',
                                (account, folder)).fetchone()
            last = cursor[1] if cursor and cursor[0] == validity else 0
            # SINCE is based on server INTERNALDATE and the fixed authorized start date.
            status, found = mailbox.uid('SEARCH', None, 'SINCE', START_DATE, 'UID', f'{last + 1}:*')
            if status != 'OK':
                raise RuntimeError('UID SEARCH failed')
            uids = [int(uid) for uid in found[0].split() if int(uid) > last]
            for uid in sorted(uids):
                if db.execute('SELECT 1 FROM copies WHERE account=? AND folder=? AND validity=? AND uid=?',
                              (account, folder, validity, uid)).fetchone():
                    last = uid
                    continue
                header_bytes = literal(fetch(mailbox, uid, '(BODY.PEEK[HEADER])'))
                header = email.message_from_bytes(header_bytes, policy=email.policy.default)
                structure_response = fetch(mailbox, uid, '(BODYSTRUCTURE)')
                structure_bytes = b' '.join(item for item in structure_response if isinstance(item, bytes))
                structure = parse_structure(structure_bytes)
                parts = text_parts(structure)
                chosen = [part for part in parts if part['subtype'] == 'plain']
                if not chosen:
                    chosen = [part for part in parts if part['subtype'] == 'html']
                body = []
                decode_errors = []
                for part in chosen:
                    request = '(BODY.PEEK[' + part['section'] + ']<0.' + str(MAX_TEXT_BYTES) + '>)'
                    payload = literal(fetch(mailbox, uid, request))
                    decoded, decode_error = decode_part_with_status(payload, part)
                    body.append(decoded)
                    decode_errors.append(decode_error)
                complete = text_completeness(chosen, decode_errors)
                text = '\n'.join(body)
                headers = json.dumps({key: str(header.get(key, '')) for key in
                    ('Message-ID','Date','From','To','Cc','Reply-To','Subject','In-Reply-To','References','Auto-Submitted','List-ID')}, ensure_ascii=False)
                message_id = str(header.get('Message-ID', '')).strip()
                # Same Message-ID with different content is retained as a separate evidence version.
                digest = hashlib.sha256((headers + '\n' + text).encode('utf-8')).hexdigest()
                key = (message_id + ':' if message_id else 'no-id:') + digest
                with db:
                    inserted = db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,?)',
                        (account,key,message_id,direction,headers,text,json.dumps(structure),complete,
                         dt.datetime.now(dt.timezone.utc).isoformat())).rowcount
                    db.execute('INSERT INTO copies VALUES(?,?,?,?,?)',(account,folder,validity,uid,key))
                    db.execute('INSERT OR REPLACE INTO folder_cursor VALUES(?,?,?,?)',(account,folder,validity,uid))
                stats['new_messages'] += inserted
                stats['new_copies'] += 1
                last = uid
            stats['folders'].append({'direction':direction,'matched_new_uids':len(uids),'last_uid':last})
        stats['stored_messages'] = db.execute('SELECT count(*) FROM messages').fetchone()[0]
    stats['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    stats['status'] = 'ok'
    (DATA / 'mail-status.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print(json.dumps(stats))

if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        DATA.mkdir(parents=True, exist_ok=True)
        status = {'status':'error','error_type':type(error).__name__,
                  'failed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        (DATA / 'mail-status.json').write_text(json.dumps(status),encoding='utf-8')
        print(json.dumps(status))
        sys.exit(1)
