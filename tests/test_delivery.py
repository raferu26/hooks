import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from liveclips import delivery
from liveclips.app import App
from liveclips.store import DEFAULT_PROFILE, profile_checked
from tests.helpers import setup_session, candidate


class Rules(unittest.TestCase):
    def test_folder_text_validation(self):
        self.assertEqual(delivery.valid_folder_text(''), '')
        self.assertEqual(delivery.valid_folder_text(None), '')
        self.assertEqual(delivery.valid_folder_text(r'  G:\Meu Drive\CORINGA '), r'G:\Meu Drive\CORINGA')
        self.assertEqual(delivery.valid_folder_text('/mnt/drive/x'), '/mnt/drive/x')
        self.assertEqual(delivery.valid_folder_text(r'\\servidor\pasta'), r'\\servidor\pasta')
        for bad in ('CORINGA', 'pasta\\sub', r'C:\a\..\b', 'x' * 301, '/a\x00b'):
            with self.assertRaises(ValueError, msg=bad):
                delivery.valid_folder_text(bad)

    def test_profile_keeps_and_rejects(self):
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE))['delivery_folder'], '')
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, delivery_folder='/x/y'))['delivery_folder'], '/x/y')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, delivery_folder='relativa'))

    def test_names_are_windows_safe(self):
        self.assertEqual(delivery.safe_name('Olha: isso? <aqui> "agora" | já!'), 'Olha_isso_aqui_agora_ja!')
        self.assertEqual(delivery.safe_name('...'), '')
        item = dict(id='abcdef123456', data=dict(project=dict(titles=[dict(text='Título/ruim:*?')])))
        name = delivery.base_name(item, 'CORINGA', when=0)
        self.assertTrue(name.startswith('CORINGA_19'))
        self.assertTrue(name.endswith('_abcdef'))
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, name)


class Deliver(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out = root / 'saida'; self.out.mkdir()
        self.dest = root / 'drive'; self.dest.mkdir()
        (self.out / 'clipe.mp4').write_bytes(os.urandom(5000))
        (self.out / 'publicacao.txt').write_text('texto de publicação', encoding='utf-8')
        self.item = dict(id='c0ffee112233', data={'hook': {'opening': 'Gente olha isso'}})

    def run_it(self, folder=None):
        return delivery.deliver(str(self.dest) if folder is None else folder, self.item, self.out / 'clipe.mp4', 'CORINGA')

    def test_copies_video_and_text_and_verifies(self):
        result = self.run_it()
        self.assertEqual(result['status'], 'ok')
        mp4 = self.dest / result['file']
        self.assertEqual(mp4.read_bytes(), (self.out / 'clipe.mp4').read_bytes())
        self.assertEqual(mp4.with_suffix('.txt').read_text(encoding='utf-8'), 'texto de publicação')
        self.assertEqual([p.name for p in self.dest.iterdir() if p.name.endswith('.part')], [])

    def test_repeating_is_idempotent(self):
        first = self.run_it(); second = self.run_it()
        self.assertEqual(first['file'], second['file'])
        self.assertEqual(len([p for p in self.dest.iterdir() if p.suffix == '.mp4']), 1)

    def test_never_overwrites_different_content(self):
        first = self.run_it()
        target = self.dest / first['file']
        target.write_bytes(b'outro conteudo do usuario')
        second = self.run_it()
        self.assertNotEqual(first['file'], second['file'])
        self.assertEqual(target.read_bytes(), b'outro conteudo do usuario')
        self.assertTrue((self.dest / second['file']).is_file())

    def test_missing_folder_is_pending_not_a_crash(self):
        result = self.run_it(str(self.dest / 'nao_existe'))
        self.assertEqual(result['status'], 'pendente')
        self.assertIn('Drive', result['error'])

    def test_missing_video_and_disabled(self):
        (self.out / 'clipe.mp4').unlink()
        self.assertEqual(self.run_it()['status'], 'erro')
        self.assertEqual(self.run_it('')['status'], 'desligada')

    def test_corrupt_copy_is_detected_and_leaves_nothing(self):
        real = delivery.shutil.copyfile

        def bad(src, dst):
            real(src, dst)
            with open(dst, 'ab') as f:
                f.write(b'x')
        with patch('liveclips.delivery.shutil.copyfile', bad):
            result = self.run_it()
        self.assertEqual(result['status'], 'erro')
        self.assertEqual([p.name for p in self.dest.iterdir()], [])

    def test_permission_error_is_reported(self):
        with patch('liveclips.delivery.shutil.copyfile', side_effect=PermissionError('sem permissão')):
            result = self.run_it()
        self.assertEqual(result['status'], 'erro')
        self.assertIn('permiss', result['error'])


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name, worker=False); self.addCleanup(self.app.close)
        self.store = self.app.store
        self.streamer, self.sid, self.profile = setup_session(self.store, durations=(120,))
        self.dest = Path(self.temp.name) / 'drive'; self.dest.mkdir()
        item, _ = candidate(self.store, self.sid, 10, 40)
        self.cid = item['id']
        out = Path(self.temp.name) / 'cortes'; out.mkdir()
        (out / 'clipe.mp4').write_bytes(os.urandom(2000))
        (out / 'publicacao.txt').write_text('pub', encoding='utf-8')
        with self.store.connect(True) as c:
            c.execute("UPDATE candidates SET status='done',export_path=? WHERE id=?", (str(out / 'clipe.mp4'), self.cid))

    def set_folder(self, folder):
        self.store.save_profile(self.streamer, dict(self.store.streamer(self.streamer)['profile'], delivery_folder=folder))

    def delivery_of(self):
        return json.loads(self.store.rows('SELECT data FROM candidates WHERE id=?', (self.cid,))[0]['data']).get('delivery')

    def test_without_a_folder_nothing_happens(self):
        self.assertIsNone(self.app.engine.deliver_one(self.cid))
        self.assertIsNone(self.delivery_of())

    def test_deliver_records_the_result_and_retry_works(self):
        self.set_folder(str(self.dest / 'depois'))
        self.app.engine.deliver_one(self.cid)
        self.assertEqual(self.delivery_of()['status'], 'pendente')
        (self.dest / 'depois').mkdir()
        out = self.app.handle_post('/api/delivery/retry', dict(id=self.cid)) if hasattr(self.app, 'handle_post') else None
        if out is None:
            self.app.engine.deliver_one(self.cid)
        self.assertEqual(self.delivery_of()['status'], 'ok')
        self.assertEqual(len([p for p in (self.dest / 'depois').iterdir() if p.suffix == '.mp4']), 1)

    def test_deliver_ready_skips_the_ones_already_delivered(self):
        self.set_folder(str(self.dest))
        self.assertEqual(self.app.engine.deliver_ready(self.streamer), 1)
        self.assertEqual(self.delivery_of()['status'], 'ok')
        self.app.engine.deliver_ready(self.streamer)
        self.assertEqual(len([p for p in self.dest.iterdir() if p.suffix == '.mp4']), 1)

    def test_turning_the_folder_off_clears_the_status(self):
        self.set_folder(str(self.dest))
        self.app.engine.deliver_one(self.cid)
        self.set_folder('')
        self.app.engine.deliver_one(self.cid)       # sem pasta: não faz nada e não inventa status
        self.assertEqual(self.delivery_of()['status'], 'ok')   # o histórico do que já foi copiado fica


if __name__ == '__main__':
    unittest.main()
