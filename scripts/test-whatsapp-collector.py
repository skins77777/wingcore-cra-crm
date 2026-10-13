import importlib.util
import pathlib
import sqlite3
import unittest

spec = importlib.util.spec_from_file_location('collector', pathlib.Path(__file__).with_name('collect-whatsapp.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def sample(text='hello', outgoing=False):
    return {'key':{'id':'DEMO','remoteJid':'123@s.whatsapp.net','fromMe':outgoing},
            'message':{'conversation':text},'messageType':'conversation','messageTimestamp':123}

class Tests(unittest.TestCase):
    def test_replay_and_revision(self):
        db = sqlite3.connect(':memory:')
        module.initialize(db)
        self.assertEqual(module.save_rows(db, [sample()]), 1)
        self.assertEqual(module.save_rows(db, [sample()]), 0)
        self.assertEqual(module.save_rows(db, [sample('edited')]), 1)
        self.assertEqual(db.execute('SELECT count(*) FROM wa_versions').fetchone()[0], 2)
        self.assertEqual(db.execute('SELECT count(*) FROM wa_current').fetchone()[0], 1)
    def test_direction_identity(self):
        self.assertNotEqual(module.normalize(sample())[0], module.normalize(sample(outgoing=True))[0])
    def test_media_caption_unknown_timestamp(self):
        row = sample()
        row.update(message={'imageMessage':{'caption':'quote'}},messageType='imageMessage',messageTimestamp=None)
        value = module.normalize(row)
        self.assertEqual(value[5], None)
        self.assertEqual(value[7], 'quote')
        self.assertEqual(value[9], 'media_not_downloaded')
    def test_groups_excluded(self):
        row = sample(); row['key']['remoteJid'] = '123@g.us'
        self.assertIsNone(module.normalize(row))
    def test_invalid_identity(self):
        row = sample(); row['key']['fromMe'] = 'false'
        with self.assertRaises(ValueError): module.normalize(row)
    def test_protocol_unresolved(self):
        row = sample(); row.update(message={},messageType='protocolMessage')
        self.assertEqual(module.normalize(row)[9], 'revision_event_unresolved')

if __name__ == '__main__': unittest.main()
