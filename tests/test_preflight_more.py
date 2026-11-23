import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from liveclips import preflight, recovery
from liveclips.store import Store, DEFAULT_PROFILE


class Models(unittest.TestCase):
    def test_all_cached_is_ok(self):
        item = preflight.models(dict(model='base', second_pass='small'), cached=lambda n: True, online=lambda: False)
        self.assertEqual(item['level'], 'ok')
        self.assertIn('small', item['detail'])

    def test_missing_with_internet_is_a_warning(self):
        item = preflight.models(dict(model='base', second_pass='small'), cached=lambda n: n == 'base', online=lambda: True)
        self.assertEqual(item['level'], 'aviso')
        self.assertIn('small', item['detail'])

    def test_missing_without_internet_is_an_error(self):
        item = preflight.models(dict(model='base', second_pass='off'), cached=lambda n: False, online=lambda: False)
        self.assertEqual(item['level'], 'erro')

    def test_library_not_installed_is_an_error_not_a_crash(self):
        item = preflight.models(dict(model='base'), cached=lambda n: None, online=lambda: True)
        self.assertEqual(item['level'], 'erro')

    def test_second_pass_off_or_same_model_is_not_checked_twice(self):
        calls = []
        preflight.models(dict(model='small', second_pass='small'), cached=lambda n: calls.append(n) or True)
        preflight.models(dict(model='base', second_pass='off'), cached=lambda n: calls.append(n) or True)
        self.assertEqual(calls, ['small', 'base'])


class DeliveryAndEstimate(unittest.TestCase):
    def test_delivery_item_only_when_a_folder_is_set(self):
        self.assertIsNone(preflight.delivery(dict()))
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(preflight.delivery(dict(delivery_folder=temp))['level'], 'ok')
            self.assertEqual(preflight.delivery(dict(delivery_folder=temp + '/nao'))['level'], 'aviso')

    def test_estimate_does_not_guess_without_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)

            class Eng:
                def capacity(self):
                    return {}
            self.assertIsNone(preflight.estimate(store, Eng()))

    def test_estimate_uses_what_was_measured(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            streamer = store.create_streamer('E')
            sid = store.new_session(streamer, 'S')
            with store.connect(True) as c:
                for q in range(3):
                    c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                              (sid, q, f'/x{q}', f's{q}', 60.0, '[]', 50 * 1024 ** 2, 1, 'done', '{}'))
                c.execute('INSERT INTO candidates(id,session,streamer,start,end,group_id,score,status,data,parts,profile,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                          ('k1', sid, streamer, 0, 30, 'g', 5, 'done', json.dumps(dict(render=dict(seconds=24, video_seconds=30, ratio=0.8))), '[]', '{}', 1))

            class Eng:
                def capacity(self):
                    return dict(rtf=0.25)
            item = preflight.estimate(store, Eng())
            self.assertIn('2.9 GB', item['detail'])     # 50 MB/min * 60 / 1024
            self.assertIn('15 min', item['detail'])     # 0.25 * 60
            self.assertIn('0.8×', item['detail'])


class BackupIsReadBack(unittest.TestCase):
    def test_good_backup_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            Store(temp).event('x', 'y')
            archive = recovery.create_backup(temp, 'teste')
            self.assertTrue(archive.is_file())

    def test_corrupted_write_is_removed_and_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            Store(temp).event('x', 'y')
            real = recovery._verify_written

            def broken(archive, counts):
                with open(archive, 'r+b') as f:
                    f.seek(40); f.write(b'\x00\x00\x00\x00\x00\x00\x00\x00')
                return real(archive, counts)
            with patch('liveclips.recovery._verify_written', broken):
                with self.assertRaises(Exception):
                    recovery.create_backup(temp, 'ruim')
            self.assertEqual(list((Path(temp) / 'backups').glob('LiveClips-ruim-*.zip')), [])

    def test_mismatching_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            Store(temp).event('x', 'y')
            with patch('liveclips.recovery._table_counts', side_effect=[{'events': 1}, {'events': 2}]):
                with self.assertRaises(ValueError):
                    recovery.create_backup(temp, 'dif')
            self.assertEqual(list((Path(temp) / 'backups').glob('LiveClips-dif-*.zip')), [])


if __name__ == '__main__':
    unittest.main()
