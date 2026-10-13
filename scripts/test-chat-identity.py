import json
import pathlib
import tempfile
import unittest
from chat_identity import resolve

class Tests(unittest.TestCase):
    def test_verified_and_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'bindings.json'
            one = {'channel':'email','identity':'buyer@example.com','person_id':'P1',
                   'active':True,'verification':{'source':'human_confirmation'}}
            path.write_text(json.dumps({'bindings':[one]}))
            self.assertEqual(resolve('email', 'BUYER@example.com', path)['person_id'], 'P1')
            self.assertEqual(resolve('email', 'Buyer Name', path)['status'], 'unverified')
            path.write_text(json.dumps({'bindings':[one,dict(one,person_id='P2')]}))
            self.assertEqual(resolve('email','buyer@example.com',path)['status'],'conflict')
    def test_no_name_or_inactive_matching(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'bindings.json'
            one = {'channel':'email','identity':'buyer@example.com','person_id':'P1',
                   'active':False,'verification':{'source':'human_confirmation'}}
            path.write_text(json.dumps({'bindings':[one]}))
            self.assertIsNone(resolve('email','buyer@example.com',path)['person_id'])

if __name__ == '__main__': unittest.main()
