import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from quote_entry import (QuoteError, QuoteRemote, QuoteService, FIELDS, READ_FIELDS, validate,
                         target_fields, handle_http, backup, open_store, service_from_config)

ACTOR = 'ceb518d8-6989-443f-aa75-197021ee139c'
OP = 'c6c75dc6-9f6f-4e27-a27c-096c373217af'
WORKSPACE = 'b7d89ec7-6e83-4216-8e1d-cf16feea5e27'
VERSION = '2026-10-12T02:00:00.000Z'


def request(status='sent', **kwargs):
    body = {'submissionId': str(uuid.uuid4()), 'opportunityId': OP, 'status': status}
    if status == 'sent':
        body.update(quoteRound='Q1', sentAt='2026-10-12T08:00:00+08:00', channel='alibaba',
                    evidence='人工核实消息MSG-001已发给本商机客户', expectedUpdatedAt=VERSION)
    body.update(kwargs)
    return body


class Remote:
    def __init__(self):
        self.record = dict(id=OP, updatedAt=VERSION, deletedAt=None, stage='PROPOSAL', craT1StopReason='人工停止',
                           craT1AgreedAt='2026-10-16T00:00:00.000Z', craT1FollowedAt=None,
                           **{key: None for key in FIELDS})
        self.writes = []
        self.reads = 0
        self.fail_before = False
        self.timeout_after = False
        self.fail_readback = False
        self.race = False
        self.mismatch = False

    def read(self, opportunity_id):
        self.reads += 1
        if self.fail_readback and self.writes:
            raise TimeoutError()
        return copy.deepcopy(self.record)

    def update(self, opportunity_id, version, fields):
        if self.fail_before:
            raise TimeoutError()
        if self.race:
            self.record['updatedAt'] = '2026-10-12T02:00:01.000Z'
            self.record['craT1QuoteEvidence'] = '人工修改'
        if self.record['updatedAt'] != version:
            raise QuoteError('remote_version_conflict')
        self.writes.append(copy.deepcopy(fields))
        self.record.update(fields)
        self.record['updatedAt'] = '2026-10-12T02:00:02.000Z'
        if self.mismatch:
            self.record['craT1QuoteEvidence'] = '返回不一致'
        if self.timeout_after:
            raise TimeoutError()


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'registration.sqlite3'
        self.remote = Remote()
        self.service = QuoteService(self.remote, {ACTOR: [OP]}, self.path)
        self.body = request()

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, body=None):
        return self.service.submit(body or self.body, ACTOR)['value']

    def test_sent_single_write_exact_fields_and_readback(self):
        original = copy.deepcopy(self.remote.record)
        value = self.submit()
        self.assertEqual(value['processingState'], 'succeeded')
        self.assertEqual(value['result']['action'], 'updated')
        self.assertEqual(len(self.remote.writes), 1)
        self.assertEqual(set(self.remote.writes[0]), set(FIELDS))
        self.assertGreaterEqual(self.remote.reads, 3)
        for key in ('stage', 'craT1StopReason', 'craT1AgreedAt', 'craT1FollowedAt'):
            self.assertEqual(self.remote.record[key], original[key])
        self.assertEqual(value['registeredBy'], ACTOR)
        self.assertEqual(self.remote.record['craT1QuoteSentAt'], '2026-10-12T00:00:00.000Z')
        self.assertTrue(self.remote.record['craT1QuoteEvidence'].startswith('阿里平台｜'))

    def test_three_unsent_statuses_preserve_t1(self):
        self.submit()
        before = copy.deepcopy(self.remote.record)
        for status in ('unknown', 'not_quoted', 'draft'):
            with self.subTest(status=status):
                value = self.submit(request(status))
                self.assertEqual(value['result'], {'action': 'registered_only', 't1Updated': False})
                self.assertEqual(self.remote.record, before)
        self.assertEqual(len(self.remote.writes), 1)
        view = self.service.get(OP, ACTOR)
        self.assertEqual(view['latestRegistration']['status'], 'draft')
        self.assertEqual(view['lastVerifiedSent']['submissionId'], self.body['submissionId'])

    def test_repeated_submission_cached_even_after_external_edit(self):
        value = self.submit()
        self.remote.record['craT1QuoteEvidence'] = '后续人工修改'
        again = self.service.submit(self.body, ACTOR)
        self.assertTrue(again['replayed'])
        self.assertEqual(again['value'], value)
        self.assertEqual(len(self.remote.writes), 1)
        self.assertEqual(self.remote.record['craT1QuoteEvidence'], '后续人工修改')

    def test_same_id_changed_payload_rejected(self):
        self.submit()
        with self.assertRaisesRegex(QuoteError, 'submission_id_conflict'):
            self.submit(dict(self.body, evidence='改变依据'))
        self.assertEqual(len(self.remote.writes), 1)

    def test_same_id_different_actor_rejected(self):
        self.submit()
        actor2 = str(uuid.uuid4())
        self.service.members[actor2] = [OP]
        with self.assertRaisesRegex(QuoteError, 'submission_id_conflict'):
            self.service.submit(self.body, actor2)

    def test_same_round_same_facts_new_submission_no_write(self):
        self.submit()
        body = dict(self.body, submissionId=str(uuid.uuid4()))
        self.assertEqual(self.submit(body)['result']['action'], 'already_satisfied')
        self.assertEqual(len(self.remote.writes), 1)

    def test_same_round_changed_facts_conflict(self):
        self.submit()
        value = self.submit(request(expectedUpdatedAt=self.remote.record['updatedAt'], evidence='不同依据'))
        self.assertEqual(value['errorCode'], 'same_round_different_facts')
        self.assertEqual(value['processingState'], 'conflict')
        self.assertEqual(len(self.remote.writes), 1)

    def test_newer_round_updates(self):
        self.submit()
        value = self.submit(request(quoteRound='Q2', sentAt='2026-10-12T01:00:00Z',
                                    expectedUpdatedAt=self.remote.record['updatedAt']))
        self.assertEqual(value['processingState'], 'succeeded')
        self.assertEqual(len(self.remote.writes), 2)

    def test_older_or_equal_timestamp_rejected(self):
        self.submit()
        for sent in ('2026-10-11T00:00:00Z', '2026-10-12T00:00:00Z'):
            value = self.submit(request(quoteRound='Q2', sentAt=sent, expectedUpdatedAt=self.remote.record['updatedAt']))
            self.assertEqual(value['errorCode'], 'quote_not_newer')
        self.assertEqual(len(self.remote.writes), 1)

    def test_future_time(self):
        with self.assertRaisesRegex(QuoteError, 'sent_at_in_future'):
            self.submit(request(sentAt='2099-01-01T00:00:00Z'))
        self.assertFalse(self.remote.writes)

    def test_missing_sent_requirements(self):
        for key in ('quoteRound', 'sentAt', 'channel', 'evidence', 'expectedUpdatedAt'):
            with self.subTest(key=key), self.assertRaises(QuoteError):
                validate({k: v for k, v in self.body.items() if k != key})

    def test_invalid_status(self):
        for status in ('SENT', '', None, {}, []):
            with self.subTest(status=status), self.assertRaises(QuoteError):
                validate(dict(self.body, status=status))

    def test_unknown_fields_and_spoofed_actor_rejected(self):
        for key in ('actorId', 'registeredAt', 'workspaceId', 'amount', 'stage'):
            with self.assertRaises(QuoteError):
                self.submit(dict(self.body, **{key: 'forged'}))

    def test_invalid_timestamp_and_no_timezone(self):
        for value in ('2026-10-12', '2026-10-12T00:00:00', '2026-02-30T00:00:00Z', '2026-10-12T00:00:00.1234Z'):
            with self.assertRaises(QuoteError):
                validate(dict(self.body, sentAt=value))

    def test_other_channel_requires_detail(self):
        with self.assertRaises(QuoteError):
            validate(dict(self.body, channel='other'))
        body = validate(dict(self.body, channel='other', channelDetail='电话核实'))
        self.assertTrue(target_fields(body)['craT1QuoteEvidence'].startswith('其他（电话核实）｜'))

    def test_unsent_rejects_sent_fields(self):
        with self.assertRaises(QuoteError):
            validate(dict(self.body, status='draft'))

    def test_permission_revoked_blocks_replay(self):
        self.submit()
        self.service.members.clear()
        with self.assertRaisesRegex(QuoteError, 'quote_permission_denied'):
            self.submit()

    def test_permission_scope_and_read_denied(self):
        for actor, op in ((str(uuid.uuid4()), OP), (ACTOR, str(uuid.uuid4()))):
            with self.assertRaisesRegex(QuoteError, 'quote_permission_denied'):
                self.service.get(op, actor)
        self.assertEqual(self.remote.reads, 0)

    def test_missing_and_deleted_opportunity(self):
        for record in (None, {'id': OP, 'deletedAt': VERSION}):
            self.remote.record = record
            with self.assertRaisesRegex(QuoteError, 'opportunity_not_found'):
                self.submit()
        with closing(open_store(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM submissions').fetchone()[0], 0)

    def test_stale_version_never_writes(self):
        self.remote.record['updatedAt'] = '2026-10-12T02:00:01.000Z'
        value = self.submit()
        self.assertEqual(value['errorCode'], 'remote_version_conflict')
        self.assertFalse(self.remote.writes)

    def test_race_between_read_and_update(self):
        self.remote.race = True
        value = self.submit()
        self.assertEqual(value['errorCode'], 'remote_version_conflict')
        self.assertFalse(self.remote.writes)
        self.assertEqual(self.remote.record['craT1QuoteEvidence'], '人工修改')

    def test_timeout_after_commit_recovers_without_second_patch(self):
        self.remote.timeout_after = True
        value = self.submit()
        self.assertEqual(value['result']['action'], 'recovered_readback')
        self.assertEqual(value['processingState'], 'succeeded')
        self.submit()
        self.assertEqual(len(self.remote.writes), 1)

    def test_timeout_before_commit_can_retry(self):
        self.remote.fail_before = True
        value = self.submit()
        self.assertEqual(value['processingState'], 'retryable')
        self.assertIsNone(value['result'])
        self.remote.fail_before = False
        restarted = QuoteService(self.remote, {ACTOR: [OP]}, self.path)
        value = restarted.submit(self.body, ACTOR)['value']
        self.assertEqual(value['processingState'], 'succeeded')
        self.assertEqual(value['attempts'], 2)
        self.assertEqual(len(self.remote.writes), 1)

    def test_readback_failure_requires_retry_read_before_write(self):
        self.remote.fail_readback = True
        value = self.submit()
        self.assertEqual(value['processingState'], 'retryable')
        self.remote.fail_readback = False
        value = self.submit()
        self.assertEqual(value['result']['action'], 'recovered_readback')
        self.assertEqual(len(self.remote.writes), 1)

    def test_crash_after_patch_recovers_durable_applying_state(self):
        real_update = self.remote.update
        def crash(*args):
            real_update(*args)
            raise KeyboardInterrupt()
        with patch.object(self.remote, 'update', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.submit()
        with closing(open_store(self.path)) as db:
            row = db.execute('SELECT state,plan FROM submissions').fetchone()
            self.assertEqual(row['state'], 'applying')
            self.assertIsNotNone(row['plan'])
        self.assertEqual(self.submit()['processingState'], 'succeeded')
        self.assertEqual(len(self.remote.writes), 1)

    def test_crash_before_patch_then_retry(self):
        with patch.object(self.remote, 'update', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            self.submit()
        self.assertEqual(self.submit()['processingState'], 'succeeded')
        self.assertEqual(len(self.remote.writes), 1)

    def test_retry_never_overwrites_newer_manual_change(self):
        self.remote.fail_before = True
        self.submit()
        self.remote.fail_before = False
        self.remote.record['updatedAt'] = '2026-10-12T02:00:01.000Z'
        value = self.submit()
        self.assertEqual(value['processingState'], 'conflict')
        self.assertFalse(self.remote.writes)

    def test_unresolved_sent_blocks_new_sent_but_allows_draft(self):
        self.remote.fail_before = True
        self.submit()
        with self.assertRaisesRegex(QuoteError, 'earlier_submission_unresolved'):
            self.submit(request(quoteRound='Q2'))
        draft = request('draft')
        self.assertEqual(self.submit(draft)['processingState'], 'succeeded')
        self.remote.fail_before = False
        self.submit()
        self.assertEqual(self.service.get(OP, ACTOR)['latestRegistration']['submissionId'], draft['submissionId'])

    def test_readback_mismatch_never_claims_success(self):
        self.remote.mismatch = True
        value = self.submit()
        self.assertEqual(value['errorCode'], 'readback_mismatch')
        self.assertNotEqual(value['processingState'], 'succeeded')
        self.assertIsNone(value['result'])

    def test_concurrent_submissions_same_id_one_write_and_record(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: self.submit(), range(4)))
        self.assertTrue(all(v['processingState'] == 'succeeded' for v in values))
        self.assertEqual(len(self.remote.writes), 1)
        with closing(open_store(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM submissions').fetchone()[0], 1)

    def test_concurrent_different_submissions_stale_second_blocked(self):
        bodies = [request(), request(quoteRound='Q2', sentAt='2026-10-12T01:00:00Z')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(self.submit, bodies))
        self.assertEqual(sorted(v['processingState'] for v in values), ['conflict', 'succeeded'])
        self.assertEqual(len(self.remote.writes), 1)

    def test_get_latest_submission_and_missing_submission(self):
        self.submit()
        value = self.service.get(OP, ACTOR, self.body['submissionId'])['value']
        self.assertEqual(value['registeredBy'], ACTOR)
        with self.assertRaisesRegex(QuoteError, 'submission_not_found'):
            self.service.get(OP, ACTOR, str(uuid.uuid4()))

    def test_backup_restore_preserves_idempotency(self):
        self.submit()
        snapshot = Path(self.temp.name) / 'snapshot.sqlite3'
        self.assertTrue(backup(snapshot, self.path))
        restored = QuoteService(self.remote, {ACTOR: [OP]}, snapshot)
        self.assertTrue(restored.submit(self.body, ACTOR)['replayed'])
        self.assertEqual(len(self.remote.writes), 1)

    def test_filtered_patch_contract(self):
        remote = QuoteRemote('synthetic-key')
        calls = []
        def call(method, path, body):
            calls.append((method, path, body))
            return {'data': {'updateOpportunities': [{'id': OP}]}}
        remote.call = call
        after = target_fields(validate(self.body))
        remote.update(OP, VERSION, after)
        method, path, body = calls[0]
        self.assertEqual(method, 'PATCH')
        self.assertEqual(body, after)
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)['filter'],
                         ['and(id[eq]:' + OP + ',updatedAt[eq]:' + VERSION + ')'])

    def test_empty_patch_response_is_conflict(self):
        remote = QuoteRemote('synthetic-key')
        remote.call = lambda *args: {'data': {'updateOpportunities': []}}
        with self.assertRaisesRegex(QuoteError, 'remote_version_conflict'):
            remote.update(OP, VERSION, target_fields(validate(self.body)))

    def test_remote_forbidden_fields_rejected(self):
        with self.assertRaisesRegex(QuoteError, 'write_field_scope'):
            QuoteRemote('synthetic-key').update(OP, VERSION, {'stage': 'PROPOSAL'})

    def test_upstream_extra_fields_never_escape_adapter_or_public_response(self):
        upstream = {**self.remote.record, 'name': 'PRIVATE LABEL',
                    'company': {'name': 'PRIVATE COMPANY'}, 'updatedBy': {'name': 'PRIVATE ACTOR'},
                    'apiKey': 'SYNTHETIC-SECRET-MUST-NOT-ESCAPE'}
        remote = QuoteRemote('synthetic-key')
        remote.call = lambda *args: {'data': {'opportunity': upstream}}
        self.service.remote = remote
        record = remote.read(OP)
        self.assertEqual(set(record), set(READ_FIELDS))
        view = self.service.get(OP, ACTOR)
        self.assertEqual(set(view['t1Fields']), set(FIELDS))
        for private in ('PRIVATE LABEL', 'PRIVATE COMPANY', 'PRIVATE ACTOR', 'SYNTHETIC-SECRET-MUST-NOT-ESCAPE'):
            self.assertNotIn(private, json.dumps(view))

    def test_incomplete_upstream_read_fails_closed(self):
        for missing in READ_FIELDS:
            upstream = {k: v for k, v in self.remote.record.items() if k != missing}
            remote = QuoteRemote('synthetic-key')
            remote.call = lambda *args: {'data': {'opportunity': upstream}}
            with self.subTest(field=missing), self.assertRaisesRegex(QuoteError, 'unexpected_read_response'):
                remote.read(OP)

    def test_submission_cannot_forward_business_or_audit_fields(self):
        for forbidden in ('name', 'amount', 'stage', 'companyId', 'pointOfContactId', 'ownerId',
                          'updatedBy', 'craT1QuoteRound', 'query', 'fields'):
            with self.subTest(field=forbidden), self.assertRaisesRegex(QuoteError, 'invalid_request_fields'):
                self.submit(dict(self.body, **{forbidden: 'SYNTHETIC-INJECTION'}))
        self.assertFalse(self.remote.writes)

    def test_configuration_fail_closed(self):
        cfg = {'CRA_QUOTE_ENABLED': 'true', 'CRA_QUOTE_WORKSPACE_ID': WORKSPACE,
               'CRA_QUOTE_API_KEY': 'synthetic', 'CRA_QUOTE_MEMBER_SCOPES': json.dumps({ACTOR: [OP]})}
        self.assertIsInstance(service_from_config(cfg), QuoteService)
        for change in ({'CRA_QUOTE_ENABLED': 'false'}, {'CRA_QUOTE_MEMBER_SCOPES': '{}'},
                       {'CRA_QUOTE_MEMBER_SCOPES': json.dumps({ACTOR: 'any'})},
                       {'CRA_QUOTE_WORKSPACE_ID': ''}, {'CRA_QUOTE_API_KEY': ''}):
            with self.assertRaises(QuoteError):
                service_from_config(dict(cfg, **change))


class HttpTests(Tests):
    # unittest inherits the core cases too; keep HTTP tests separate via load_tests below.
    def handler(self, path='/v1/quotes/registrations', body=None):
        class Handler:
            def respond(self, code, body):
                self.response = (code, body)
        h = Handler()
        raw = json.dumps(body or self.body).encode()
        h.path = path
        h.rfile = io.BytesIO(raw)
        h.headers = {'Authorization': 'Bearer synthetic-bridge', 'x-cra-workspace-id': WORKSPACE,
                     'x-cra-member-id': ACTOR, 'Content-Length': str(len(raw))}
        return h

    def dispatch(self, h, post=True):
        cfg = {'CRA_QUOTE_API_TOKEN': 'synthetic-bridge', 'CRA_QUOTE_WORKSPACE_ID': WORKSPACE}
        with patch('quote_entry.service_from_config', return_value=self.service):
            handle_http(h, cfg, post)
        return h.response

    def test_http_auth_workspace_and_actor(self):
        for header, value, code in (('Authorization', 'Bearer wrong', 403),
                                    ('x-cra-workspace-id', 'wrong', 403),
                                    ('x-cra-member-id', str(uuid.uuid4()), 403)):
            h = self.handler()
            h.headers[header] = value
            self.assertEqual(self.dispatch(h)[0], code)
        self.assertFalse(self.remote.writes)

    def test_http_submit_and_get(self):
        code, value = self.dispatch(self.handler())
        self.assertEqual(code, 200)
        self.assertEqual(value['value']['processingState'], 'succeeded')
        code, result = self.dispatch(self.handler('/v1/quotes/opportunities/' + OP), False)
        self.assertEqual(code, 200)
        self.assertEqual(result['lastVerifiedSent']['submissionId'], self.body['submissionId'])

    def test_http_failed_persisted_submission(self):
        self.remote.fail_before = True
        code, result = self.dispatch(self.handler())
        self.assertEqual(code, 503)
        self.assertTrue(result['value']['retryable'])

    def test_http_invalid_body_and_route(self):
        h = self.handler()
        h.rfile = io.BytesIO(b'[')
        h.headers['Content-Length'] = '1'
        self.assertEqual(self.dispatch(h)[0], 400)
        self.assertEqual(self.dispatch(self.handler('/v1/quotes/bad'))[0], 404)
        h = self.handler('/v1/quotes/opportunities/' + OP + '?submissionId=a&submissionId=b')
        self.assertEqual(self.dispatch(h, False)[0], 400)

    def test_quote_route_bypasses_review_refresh(self):
        from review_backend import Handler
        h = self.handler()
        h.server = type('Server', (), {'review_config': {}})()
        with patch('quote_entry.handle_http') as quote, patch('review_backend.refresh') as refresh:
            Handler.run_request(h, True)
        quote.assert_called_once_with(h, {}, True)
        refresh.assert_not_called()


class TransportTests(Tests):
    """Real HTTP transports with an isolated Twenty protocol simulator."""
    def setUp(self):
        super().setUp()
        remote = self.remote
        class TwentyHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.headers.get('Authorization') != 'Bearer synthetic-twenty':
                    return self.send(403, {'error': 'denied'})
                if self.path != '/rest/opportunities/' + OP:
                    return self.send(404, {})
                return self.send(200, {'data': {'opportunity': remote.read(OP)}})

            def do_PATCH(self):
                fields = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                expected = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)['filter'][0]
                wanted = 'and(id[eq]:' + OP + ',updatedAt[eq]:' + remote.record['updatedAt'] + ')'
                if expected != wanted:
                    return self.send(200, {'data': {'updateOpportunities': []}})
                remote.update(OP, remote.record['updatedAt'], fields)
                return self.send(200, {'data': {'updateOpportunities': [remote.record]}})
        self.twenty = ThreadingHTTPServer(('127.0.0.1', 0), TwentyHandler)
        self.thread = threading.Thread(target=self.twenty.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.twenty.server_port)
        self.service.remote = QuoteRemote('synthetic-twenty', self.url)

    def tearDown(self):
        self.twenty.shutdown()
        self.twenty.server_close()
        self.thread.join()
        super().tearDown()

    def test_transport_patch_and_readback(self):
        value = self.submit()
        self.assertEqual(value['processingState'], 'succeeded')
        self.assertEqual(value['quoteFact']['channel'], 'alibaba')
        self.assertEqual(len(self.remote.writes), 1)
        self.assertGreaterEqual(self.remote.reads, 3)

    def test_transport_redirect_does_not_forward_key(self):
        received = []
        class Destination(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
        destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
        thread = threading.Thread(target=destination.serve_forever, daemon=True)
        thread.start()
        def redirect(handler):
            handler.send_response(302)
            handler.send_header('Location', 'http://127.0.0.1:' + str(destination.server_port) + '/redirected')
            handler.send_header('Content-Length', '0')
            handler.end_headers()
        try:
            with patch.object(self.twenty.RequestHandlerClass, 'do_GET', redirect):
                with self.assertRaisesRegex(QuoteError, 'twenty_redirect_denied'):
                    self.service.remote.read(OP)
            self.assertEqual(received, [])
        finally:
            destination.shutdown()
            destination.server_close()
            thread.join()

    def test_transport_cross_process_repeat_one_patch(self):
        code = """
import json,sys
from quote_entry import QuoteService,QuoteRemote
payload=json.loads(sys.argv[1])
service=QuoteService(QuoteRemote('synthetic-twenty',sys.argv[2]),{sys.argv[3]:[payload['opportunityId']]},sys.argv[4])
print(json.dumps(service.submit(payload,sys.argv[3])))
"""
        processes = [subprocess.Popen([sys.executable, '-c', code, json.dumps(self.body), self.url, ACTOR, str(self.path)],
            cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(json.loads(stdout)['value']['processingState'], 'succeeded')
            self.assertEqual(len(self.remote.writes), 1)
            with closing(open_store(self.path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM submissions').fetchone()[0], 1)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_transport_real_backend_authenticated_request(self):
        from review_backend import Handler
        backend = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        backend.review_config = {'CRA_QUOTE_API_TOKEN': 'synthetic-bridge', 'CRA_QUOTE_WORKSPACE_ID': WORKSPACE}
        thread = threading.Thread(target=backend.serve_forever, daemon=True)
        thread.start()
        try:
            req = urllib.request.Request('http://127.0.0.1:' + str(backend.server_port) + '/v1/quotes/registrations',
                method='POST', data=json.dumps(self.body).encode(), headers={
                    'Authorization': 'Bearer synthetic-bridge', 'Content-Type': 'application/json',
                    'x-cra-workspace-id': WORKSPACE, 'x-cra-member-id': ACTOR})
            with patch('quote_entry.service_from_config', return_value=self.service), patch('review_backend.refresh') as refresh:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.load(response)['value']['processingState'], 'succeeded')
                refresh.assert_not_called()
            self.assertEqual(len(self.remote.writes), 1)
        finally:
            backend.shutdown()
            backend.server_close()
            thread.join()


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(Tests)
    for case in (HttpTests, TransportTests):
        for name in case.__dict__:
            if name.startswith('test_'):
                suite.addTest(case(name))
    return suite


if __name__ == '__main__':
    unittest.main()
