"""O SaaS precisa ser visível: vincular o programa ao servidor liga o login; desligar volta ao modo livre."""
import json
import tempfile
import unittest
from pathlib import Path

from hooks_cloud.__main__ import main as cloud_main
from liveclips import licensing


class SaasVisivelTests(unittest.TestCase):
    def test_vincular_liga_login_e_desligar_volta_ao_modo_livre(self):
        with tempfile.TemporaryDirectory() as server, tempfile.TemporaryDirectory() as app, tempfile.TemporaryDirectory() as pkg:
            self.assertEqual(cloud_main(['--pasta', server, 'vincular', '--programa', app]), 0)
            config = json.loads((Path(app) / 'cloud_config.json').read_text(encoding='utf-8'))
            self.assertTrue(config['enforce'])
            self.assertEqual(config['server_url'], 'http://127.0.0.1:8800')
            self.assertEqual(len(config['public_keys']), 1)
            read = licensing.read_config(pkg, app)
            self.assertTrue(read['enforce'] and read['public_keys'])
            self.assertEqual(cloud_main(['--pasta', server, 'vincular', '--programa', app, '--desligar']), 0)
            self.assertFalse((Path(app) / 'cloud_config.json').exists())
            self.assertFalse(licensing.read_config(pkg, app)['enforce'])

    def test_bats_do_saas_existem_com_crlf(self):
        root = Path(__file__).resolve().parent.parent
        for name in ('SAAS_LOCAL.bat', 'DESLIGAR_SAAS_LOCAL.bat', 'SERVIDOR_SAAS.bat'):
            data = (root / name).read_bytes()
            self.assertIn(b'\r\n', data, name)
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''), name)


if __name__ == '__main__':
    unittest.main()
