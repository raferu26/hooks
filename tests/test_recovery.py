import json
from pathlib import Path
import tempfile
import unittest
from zipfile import BadZipFile

from liveclips.recovery import create_backup,inspect_backup,restore_backup
from liveclips.store import Store
from tests.helpers import setup_session


class RecoveryTests(unittest.TestCase):
    def test_backup_restores_database_and_profile_with_safety_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);streamer,_sid,_profile=setup_session(store)
            store.setting('recovery_marker','antes')
            original_profile=Path(temp)/'CORINGA/perfil_v8.json'
            expected=json.loads(original_profile.read_text(encoding='utf-8'))
            backup=create_backup(temp,'manual')
            self.assertTrue(backup.is_file());self.assertEqual(inspect_backup(backup)['schema'],1)
            store.setting('recovery_marker','depois');original_profile.write_text('{}',encoding='utf-8')
            result=restore_backup(temp,backup)
            restored=Store(temp)
            self.assertEqual(restored.setting('recovery_marker'),'antes')
            self.assertTrue(restored.setting('paused'))
            self.assertEqual(restored.streamer(streamer)['profile'],expected)
            self.assertEqual(json.loads(original_profile.read_text(encoding='utf-8')),expected)
            self.assertTrue(Path(result['safety_backup']).is_file())

    def test_invalid_zip_is_rejected_without_touching_database(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);before=store.db.read_bytes()
            invalid=Path(temp)/'invalido.zip';invalid.write_bytes(b'nao e zip')
            with self.assertRaises(BadZipFile):
                inspect_backup(invalid)
            self.assertEqual(store.db.read_bytes(),before)


if __name__=='__main__':unittest.main()
