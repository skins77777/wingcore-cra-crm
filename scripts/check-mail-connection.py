"""Verify TLS, IMAP login and folder listing; never fetch mail or alter flags."""
import imaplib
import pathlib
import re
import ssl
import sys

config_path = pathlib.Path(__file__).resolve().parents[1] / 'deployment/mail/.env'
config = {}
if config_path.exists():
    for line in config_path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
secret = config.get('IMAP_AUTHORIZATION_CODE', '')
if not secret:
    print('NOT_CONFIGURED: Fill IMAP_AUTHORIZATION_CODE in deployment/mail/.env locally.')
    sys.exit(2)
stage = 'TLS'
try:
    with imaplib.IMAP4_SSL(config['IMAP_HOST'], int(config['IMAP_PORT']),
                         ssl_context=ssl.create_default_context(), timeout=20) as mailbox:
        # NetEase requires a declared client identity for mailbox access.
        if b'ID' in mailbox.capabilities:
            stage = 'ID'
            imaplib.Commands.setdefault('ID', ('NONAUTH', 'AUTH', 'SELECTED'))
            mailbox._simple_command('ID', '("name" "Wingcore CRM" "version" "1.0" "vendor" "YIHE")')
        stage = 'LOGIN'
        mailbox.login(config['MAIL_ADDRESS'], secret)
        stage = 'ID'
        capability_status, capability_data = mailbox.capability()
        if capability_status == 'OK' and any(b'ID' in item.split() for item in capability_data if item):
            imaplib.Commands.setdefault('ID', ('NONAUTH', 'AUTH', 'SELECTED'))
            mailbox._simple_command('ID', '("name" "Wingcore CRM" "version" "1.0" "vendor" "YIHE" "contact" "wingcore2026@163.com")')
        stage = 'LIST'
        status, folders = mailbox.list()
        if status != 'OK':
            raise RuntimeError('folder listing failed')
        print('CONNECTED: Authentication and folder listing succeeded. No mail was fetched.')
        for folder in folders:
            if folder:
                print(folder.decode('utf-8', errors='replace'))
        if '--check-folders' in sys.argv:
            selected = ['INBOX']
            for folder in folders:
                if folder and b'\\Sent' in folder:
                    match = re.search(rb'"([^"\\]*)"\s*$', folder)
                    if match:
                        selected.append(match.group(1).decode('ascii'))
            if len(selected) != 2:
                raise RuntimeError('sent folder mapping not unique')
            for folder_name in selected:
                stage = 'EXAMINE'
                result, count = mailbox.select('"' + folder_name + '"', readonly=True)
                if result != 'OK':
                    diagnostic = repr(count).replace(secret, '[REDACTED]').replace(config['MAIL_ADDRESS'], '[ACCOUNT]')
                    print('Folder diagnostic:', diagnostic[:500])
                    raise RuntimeError('read-only folder selection failed')
                print('READ_ONLY_FOLDER:', folder_name, 'messages=', count[0].decode('ascii'))
except Exception as error:
    print('FAILED:', stage, type(error).__name__)
    if isinstance(error, imaplib.IMAP4.error):
        diagnostic = str(error).replace(secret, '[REDACTED]').replace(config.get('MAIL_ADDRESS', ''), '[ACCOUNT]')
        print('IMAP diagnostic:', diagnostic[:500])
    sys.exit(1)
