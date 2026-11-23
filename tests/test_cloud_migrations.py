import sqlite3
import tempfile
import unittest
from pathlib import Path

from hooks_cloud.db import DB, SchemaTooNew


def version(path):
    c = sqlite3.connect(path)
    try:
        return int(c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
    finally:
        c.close()


class Migrations(unittest.TestCase):
    def test_new_database_is_born_at_latest_version_without_running_steps(self):
        with tempfile.TemporaryDirectory() as t:
            ran = []
            DB(Path(t) / 'a.db', migrations={2: ['CREATE TABLE x(a)']}, version=2)
            self.assertEqual(version(Path(t) / 'a.db'), 2)
            c = sqlite3.connect(Path(t) / 'a.db')
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='x'").fetchone())
            c.close()

    def test_old_database_migrates_and_keeps_a_safety_copy(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'a.db'
            db = DB(path)
            db.set_setting('k', 1)
            DB(path, migrations={2: ['CREATE TABLE extra(a)', 'ALTER TABLE notes ADD COLUMN tag TEXT']}, version=2)
            self.assertEqual(version(path), 2)
            c = sqlite3.connect(path)
            self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE name='extra'").fetchone())
            c.close()
            copy = Path(t) / 'a.db.antes-v1'
            self.assertTrue(copy.is_file())
            self.assertEqual(version(copy), 1)
            self.assertEqual(DB(path, migrations={}, version=2).setting('k'), 1)

    def test_failed_step_rolls_back_and_database_stays_usable(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'a.db'
            DB(path)
            with self.assertRaises(sqlite3.Error):
                DB(path, migrations={2: ['CREATE TABLE ok2(a)', 'ALTER TABLE nao_existe ADD COLUMN b']}, version=2)
            self.assertEqual(version(path), 1)
            c = sqlite3.connect(path)
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='ok2'").fetchone())
            c.close()
            DB(path)  # o servidor atual ainda abre

    def test_missing_step_is_reported(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'a.db'
            DB(path)
            with self.assertRaises(RuntimeError):
                DB(path, migrations={}, version=3)
            self.assertEqual(version(path), 1)

    def test_database_from_newer_server_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'a.db'
            DB(path, migrations={2: []}, version=2)
            with self.assertRaises(SchemaTooNew):
                DB(path)

    def test_steps_run_in_order_across_several_versions(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'a.db'
            DB(path)
            DB(path, migrations={2: ['CREATE TABLE a2(x)'], 3: ['INSERT INTO a2 VALUES(7)']}, version=3)
            c = sqlite3.connect(path)
            self.assertEqual(c.execute('SELECT x FROM a2').fetchone()[0], 7)
            c.close()
            self.assertEqual(version(path), 3)


if __name__ == '__main__':
    unittest.main()
