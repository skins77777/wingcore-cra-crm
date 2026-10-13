"""Synthetic MIME checks: no mailbox credentials or live data are used."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('collector', pathlib.Path(__file__).with_name('collect-mail.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

class MimeChecks(unittest.TestCase):
    def test_plain_and_html_alternative_sections(self):
        structure = collector.parse_structure(b'1 (UID 1 BODYSTRUCTURE (("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "BASE64" 20 1 NIL NIL NIL)("TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "BASE64" 30 1 NIL NIL NIL) "ALTERNATIVE"))')
        self.assertEqual([part['section'] for part in collector.text_parts(structure)], ['1','2'])
    def test_attachment_text_excluded(self):
        structure = ['TEXT','PLAIN',['CHARSET','UTF-8'],None,None,'7BIT',20,1,None,['ATTACHMENT',['FILENAME','x.txt']]]
        self.assertEqual(collector.text_parts(structure), [])
    def test_nested_mixed_does_not_select_image(self):
        plain = ['TEXT','PLAIN',None,None,None,'7BIT',5,1]
        image = ['IMAGE','PNG',None,None,None,'BASE64',99]
        self.assertEqual([part['section'] for part in collector.text_parts([[plain,'ALTERNATIVE'],image,'MIXED'])], ['1.1'])
    def test_html_does_not_include_script(self):
        part={'encoding':'7bit','charset':'utf-8','subtype':'html'}
        result = collector.decode_part(b'<p>Quote</p><script>ignore me</script><p>USD 10</p>',part)
        self.assertIn('USD 10', result)
        self.assertNotIn('ignore me',result)
    def test_valid_utf8_and_gbk_are_text_only(self):
        cases = [
            (b'\xe8\xaf\xa2\xe4\xbb\xb7', 'utf-8', '询价'),
            ('产品咨询'.encode('gbk'), 'gbk', '产品咨询'),
        ]
        for payload, charset, expected in cases:
            with self.subTest(charset=charset):
                part = {'encoding':'8bit','charset':charset,'subtype':'plain','bytes':len(payload)}
                text, decode_error = collector.decode_part_with_status(payload, part)
                self.assertEqual(text, expected)
                self.assertFalse(decode_error)
                self.assertEqual(collector.text_completeness([part], [decode_error]), 'text_only')
    def test_damaged_utf8_sets_decode_error(self):
        part = {'encoding':'8bit','charset':'utf-8','subtype':'plain','bytes':4}
        text, decode_error = collector.decode_part_with_status(b'\xff\xfe10', part)
        self.assertIn('\ufffd', text)
        self.assertTrue(decode_error)
        self.assertEqual(collector.text_completeness([part], [decode_error]), 'text_decode_error')
    def test_unknown_charset_and_existing_replacement_character_are_errors(self):
        unknown = {'encoding':'8bit','charset':'x-unknown-charset','subtype':'plain','bytes':4}
        text, decode_error = collector.decode_part_with_status('测试'.encode('utf-8'), unknown)
        self.assertEqual(text, '测试')
        self.assertTrue(decode_error)
        replacement = {'encoding':'8bit','charset':'utf-8','subtype':'plain','bytes':4}
        text, decode_error = collector.decode_part_with_status('A\ufffdB'.encode('utf-8'), replacement)
        self.assertIn('\ufffd', text)
        self.assertTrue(decode_error)
    def test_truncation_keeps_precedence_over_decode_error(self):
        part = {'encoding':'8bit','charset':'utf-8','subtype':'plain','bytes':collector.MAX_TEXT_BYTES+1}
        self.assertEqual(collector.text_completeness([part], [True]), 'text_truncated')
    def test_unsupported_literal_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            collector.parse_structure(b'BODYSTRUCTURE ("TEXT" "PLAIN" ({3}\r\nfoo) NIL NIL "7BIT" 3 1)')

unittest.main()
