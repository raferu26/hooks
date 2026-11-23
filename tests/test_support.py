import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from liveclips import support
from liveclips.app import App
from liveclips.store import Store


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Eta(unittest.TestCase):
    def test_no_guess_in_the_first_seconds_then_linear_estimate(self):
        clock = Clock()
        eta = support.Eta(clock)
        clock.now = 2
        self.assertIsNone(eta.update(.2)['eta'])
        clock.now = 60
        step = eta.update(.25)
        self.assertEqual((step['percent'], step['eta']), (25, 180))
        self.assertEqual(eta.update(1)['eta'], 0)

    def test_human_text(self):
        self.assertEqual(support.human(None), '')
        self.assertEqual(support.human(20), 'menos de 1 min')
        self.assertEqual(support.human(600), '~10 min')
        self.assertEqual(support.human(5400), '~1 h 30 min')


class Privacy(unittest.TestCase):
    def test_tokens_and_home_are_hidden(self):
        home = '/home/alguem'
        text = support.clean_text('GET https://x.tv/a?token=abc123&q=1 em /home/alguem/LiveClips', home)
        self.assertNotIn('abc123', text)
        self.assertNotIn('alguem', text)
        self.assertIn('q=1', text)


class Bundle(unittest.TestCase):
    def test_bundle_has_log_and_events_but_not_database_or_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            support.setup_logging(root)
            support.setup_logging(root)   # repetir não duplica
            support.log_error('algo falhou: token=segredo99', ValueError('boom'))
            store.event('erro', 'falha de teste')
            file = support.bundle(root, store, '9.9', {'ffmpeg': '/usr/bin/ffmpeg', 'ffprobe': None})
            with zipfile.ZipFile(file) as archive:
                names = archive.namelist()
                self.assertIn('sistema.txt', names)
                self.assertIn('eventos.txt', names)
                self.assertTrue(any(n.startswith('logs/') for n in names))
                self.assertFalse(any('sqlite' in n or 'perfil' in n for n in names))
                joined = '\n'.join(archive.read(n).decode('utf-8') for n in names)
            self.assertIn('falha de teste', joined)
            self.assertIn('ffprobe: FALTA', joined)
            self.assertNotIn('segredo99', joined)
            self.assertEqual(len(list((Path(root) / 'logs').glob('liveclips.log*'))), 1)
            store.close() if hasattr(store, 'close') else None


class Api(unittest.TestCase):
    def test_endpoint_creates_the_zip_and_progress_carries_eta(self):
        with tempfile.TemporaryDirectory() as root:
            app = App(root, worker=False)
            try:
                result = app.action('/api/support/bundle', {})
                self.assertTrue(Path(result['path']).is_file())
                app.engine.progress('Transcrevendo', 'x', percent=40, eta=300)
                info = app.engine.state()
                self.assertEqual((info['percent'], info['eta'], info['eta_text']), (40, 300, '~5 min'))
                app.engine.progress('Parado', '', False)
                self.assertNotIn('percent', app.engine.state())
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()
