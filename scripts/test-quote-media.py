import base64
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import quote_media as m

JPEG = b'\xff\xd8\xfftest\xff\xd9'
PNG = b'\x89PNG\r\n\x1a\nbody\x00\x00\x00\x00IEND\xaeB`\x82'

class MediaTests(unittest.TestCase):
    def test_nested_part_keeps_section(self):
        leaf=['image','jpeg',['name','../../bad.jpg'],None,None,'base64',100]
        self.assertEqual(m.image_parts([[leaf,'mixed'],'related'])[0]['section'], '1.1')

    def test_nonimages_are_not_candidates(self):
        self.assertEqual(m.image_parts(['application','pdf',None,None,None,'base64',100]), [])

    def test_unknown_identity_is_excluded(self):
        with patch.object(m, 'resolve', return_value={'status':'unverified'}):
            self.assertIsNone(m.verified_recipient({'To':'unknown@example.test'}))

    def test_multiple_recipients_and_cc_are_excluded(self):
        with patch.object(m, 'resolve') as lookup:
            self.assertIsNone(m.verified_recipient({'To':'a@example.test,b@example.test'}))
            self.assertIsNone(m.verified_recipient({'To':'a@example.test','Cc':'b@example.test'}))
            lookup.assert_not_called()

    def test_png_label_on_jpeg_uses_actual_signature(self):
        data, extension=m.decode_image(base64.b64encode(JPEG),{'encoding':'base64','mime':'image/png'})
        self.assertEqual((data,extension),(JPEG,'.jpg'))

    def test_real_png_and_wrapped_base64(self):
        encoded=base64.b64encode(PNG)
        self.assertEqual(m.decode_image(encoded[:8]+b'\r\n'+encoded[8:],{'encoding':'base64','mime':'image/png'}),(PNG,'.png'))

    def test_invalid_or_truncated_image_rejected(self):
        for data in (b'<html>wrong</html>',PNG[:-4],JPEG[:-2]):
            with self.assertRaises(ValueError):
                m.decode_image(data,{'encoding':'binary','mime':'image/png'})

    def test_size_limit(self):
        with patch.object(m,'MAX_BYTES',3),self.assertRaises(ValueError):
            m.decode_image(b'long',{'encoding':'binary','mime':'image/png'})

    def test_uidvalidity_checked_before_fetch(self):
        mailbox=Mock()
        mailbox.select.return_value=('OK',[])
        mailbox.response.return_value=('UIDVALIDITY',[b'new'])
        with patch.object(m.mail,'fetch') as fetch, self.assertRaisesRegex(ValueError,'uidvalidity_changed'):
            m.fetch_image(mailbox,('Sent','old',123),{})
        fetch.assert_not_called()
        mailbox.select.assert_called_once_with('"Sent"',readonly=True)

    def test_header_change_rejected(self):
        mailbox=Mock()
        mailbox.select.return_value=('OK',[])
        mailbox.response.return_value=('UIDVALIDITY',[b'7'])
        with patch.object(m.mail,'fetch',return_value=[(b'',b'To: changed@example.test\r\n\r\n')]),self.assertRaisesRegex(ValueError,'source_headers_changed'):
            m.fetch_image(mailbox,('Sent','7',123),{'headers':{'To':'original@example.test'}})

    def test_all_image_reads_use_peek(self):
        mailbox=Mock()
        mailbox.select.return_value=('OK',[])
        mailbox.response.return_value=('UIDVALIDITY',[b'7'])
        encoded=base64.b64encode(JPEG)
        structure=['image','jpeg',None,None,None,'base64',len(encoded)]
        metadata={'headers':{'To':'a@example.test'},'structure':structure,
                  'image':{'section':'2','mime':'image/jpeg','encoding':'base64','transfer_bytes':len(encoded)}}
        responses=[[(b'',b'To: a@example.test\r\n\r\n')],[b'BODYSTRUCTURE ("image" "jpeg" NIL NIL NIL "base64" '+str(len(encoded)).encode()+b')'],[(b'',encoded)]]
        with patch.object(m.mail,'fetch',side_effect=responses) as fetch:
            self.assertEqual(m.fetch_image(mailbox,('Sent','7',123),metadata),(JPEG,'.jpg'))
            commands=[call.args[2] for call in fetch.call_args_list]
            self.assertTrue(all('BODY.PEEK[' in request or request=='(BODYSTRUCTURE)' for request in commands))

    def test_cached_download_checks_binding_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m,'MEDIA',Path(directory)),closing(m.connect()) as db:
                db.execute('INSERT INTO media (id,source,account,source_key,source_revision,person_id,identity,direction,part,metadata,state) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           ('one','email','own','key','rev','p1','customer@example.test','outbound','1','{}','downloaded_unclassified'))
                db.commit()
                with patch.object(m,'resolve',return_value={'status':'verified','person_id':'p2'}), patch.object(m.imaplib,'IMAP4_SSL') as connection,self.assertRaisesRegex(ValueError,'identity_binding_changed'):
                    m.download(db,'one')
                connection.assert_not_called()

if __name__=='__main__':
    unittest.main()
