"""Assinatura dentro do Hook’s: licença, cotas, fila de uso, portas e integração com o App."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from hooks_cloud.web import Cloud, serve
from liveclips import licensing
from liveclips.app import App
from liveclips.licensing import LicenseError, Licensing
from tests.helpers import candidate, setup_session

CHEAP = dict(n=2 ** 4, r=1, p=1)
PW = 'Uma-Senha-Boa-2026'


class Server:
    """Servidor de contas de verdade, em porta livre, para o cliente conversar."""
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cloud = Cloud(Path(self.tmp.name), env={}, hash_params=CHEAP)
        with self.cloud.db.connect(True) as c:
            c.execute("UPDATE plans SET price_cents=9900,active=1,max_lives=2,hours_month=1,clips_month=2 WHERE code='basico'")
        self.http = serve(self.cloud, '127.0.0.1', 0)
        self.url = f'http://127.0.0.1:{self.http.server_address[1]}'
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.keys = {self.cloud.keys.kid: self.cloud.keys.public_b64}

    def config(self, **extra):
        return dict(server_url=self.url, public_keys=self.keys, enforce=True, **extra)

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.tmp.cleanup()

    def pay(self, email='ana@x.com', plan='basico'):
        acc = self.cloud.db.one('SELECT id FROM accounts WHERE email=?', (email,))
        self.cloud.service.apply_payment(acc['id'], 9900, 'pix', 'r', plan_code=plan, actor='t')
        return acc['id']


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [time.time()]
        with self.server.cloud.db.connect(True) as c:
            c.execute('DELETE FROM attempts')

    def write_config(self, **extra):
        (self.root / 'cloud_config.json').write_text(json.dumps(self.server.config(**extra)))

    def lic(self, **kw):
        return Licensing(self.root, self.root / 'pacote', '0.16-test', clock=lambda: self.now[0], **kw)

    def signed_in(self, email, name='Ana'):
        self.write_config()
        lic = self.lic()
        lic.register(name, email, PW, True)
        return lic


class FreeModeTests(Base):
    def test_without_config_everything_is_allowed(self):
        lic = self.lic()
        self.assertFalse(lic.enforced)
        self.assertEqual(lic.public()['mode'], 'livre')
        lic.check_active(); lic.check_start_live(99); lic.check_export(999)
        self.assertTrue(lic.allow_analysis())
        self.assertFalse(lic.record('clipe', 1, 'x'))
        self.assertEqual(lic.max_lives(), 5)
        with self.assertRaises(LicenseError):
            lic.login('a@b.com', PW)

    def test_enforce_without_keys_stays_free(self):
        (self.root / 'cloud_config.json').write_text(json.dumps(dict(server_url='https://x.com', enforce=True)))
        self.assertFalse(self.lic().enforced)

    def test_data_folder_config_overrides_package(self):
        (self.root / 'pacote').mkdir()
        (self.root / 'pacote' / 'cloud_config.json').write_text(json.dumps(dict(server_url='https://a.com', enforce=False)))
        (self.root / 'cloud_config.json').write_text(json.dumps(dict(server_url='https://b.com')))
        self.assertEqual(self.lic().config['server_url'], 'https://b.com')


class LoginTests(Base):
    def test_needs_login_then_login_ok(self):
        self.write_config()
        lic = self.lic()
        st = lic.public()
        self.assertEqual((st['state'], st['needs_login'], st['ok']), ('sem_login', True, False))
        with self.assertRaises(LicenseError):
            lic.check_active()
        lic.register('Ana', 'login1@x.com', PW, True)
        st = lic.public()
        self.assertEqual((st['state'], st['ok'], st['email'], st['plan']), ('teste', True, 'login1@x.com', 'teste'))
        self.assertNotIn('device_token', json.dumps(st))
        self.assertNotIn('license', st)
        lic.check_active()

    def test_wrong_password_and_terms(self):
        self.write_config()
        lic = self.lic()
        lic.register('Ana', 'login2@x.com', PW, True)
        other = self.lic()
        with self.assertRaises(LicenseError) as cm:
            other.login('login2@x.com', 'senha-errada-12')
        self.assertIn('incorretos', str(cm.exception))
        with self.assertRaises(LicenseError):
            other.register('X', 'login3@x.com', PW, False)

    def test_state_persists_across_restarts(self):
        lic = self.signed_in('persist@x.com')
        again = self.lic()
        self.assertEqual(again.public()['email'], 'persist@x.com')
        again.check_active()

    def test_tampered_license_is_invalid(self):
        lic = self.signed_in('tamper@x.com')
        data = json.loads((self.root / 'licenca.json').read_text())
        head, body, sig = data['license'].split('.')
        evil = json.loads(licensing._b64d(body))
        evil['plan'] = 'agencia'
        evil['limits']['clipes'] = 99999
        data['license'] = '.'.join((head, licensing.base64.urlsafe_b64encode(json.dumps(evil).encode()).decode().rstrip('='), sig))
        (self.root / 'licenca.json').write_text(json.dumps(data))
        st = self.lic().public()
        self.assertEqual(st['state'], 'invalida')
        self.assertFalse(st['ok'])

    def test_wrong_public_key_is_reported(self):
        other = Cloud(Path(tempfile.mkdtemp()), env={}, hash_params=CHEAP)
        (self.root / 'cloud_config.json').write_text(json.dumps(dict(server_url=self.server.url, enforce=True,
                                                                     public_keys={other.keys.kid: other.keys.public_b64})))
        with self.assertRaises(LicenseError) as cm:
            self.lic().register('Ana', 'key@x.com', PW, True)
        self.assertIn('chave pública', str(cm.exception))

    def test_server_url_must_be_https_unless_local(self):
        self.assertTrue(licensing.safe_server('https://contas.exemplo.com'))
        self.assertTrue(licensing.safe_server('http://127.0.0.1:8800'))
        self.assertFalse(licensing.safe_server('http://contas.exemplo.com'))
        self.assertFalse(licensing.safe_server('ftp://x.com'))
        (self.root / 'cloud_config.json').write_text(json.dumps(dict(server_url='http://contas.exemplo.com', enforce=True, public_keys=self.server.keys)))
        with self.assertRaises(LicenseError):
            self.lic().login('a@b.com', PW)

    def test_offline_login_is_a_clear_error(self):
        (self.root / 'cloud_config.json').write_text(json.dumps(dict(server_url='http://127.0.0.1:1', enforce=True, public_keys=self.server.keys)))
        with self.assertRaises(ConnectionError):
            self.lic().login('a@b.com', PW)


class UsageAndGatesTests(Base):
    def test_events_flow_idempotent_and_pending_counts(self):
        lic = self.signed_in('uso1@x.com')
        self.server.pay('uso1@x.com')
        self.assertTrue(lic.sync()[0])
        self.assertEqual(lic.public()['limits']['clipes'], 2)
        self.assertTrue(lic.record('clipe', 1, 'clip:A:1'))
        self.assertFalse(lic.record('clipe', 1, 'clip:A:1'))         # mesmo clipe, mesma versão: não duplica
        self.assertEqual(lic.public()['usage']['clipes'], 1)        # já aparece, antes de enviar
        self.assertEqual(lic.public()['pending_events'], 1)
        self.assertTrue(lic.sync()[0])
        self.assertEqual(lic.public()['pending_events'], 0)
        self.assertEqual(lic.public()['usage']['clipes'], 1)        # não soma duas vezes depois de enviar
        again = self.lic()
        again.record('clipe', 1, 'clip:A:1')                         # mesmo install, reinício: id igual
        self.assertEqual(again.public()['pending_events'], 0)

    def test_export_gate_counts_queue(self):
        lic = self.signed_in('uso2@x.com')
        self.server.pay('uso2@x.com')
        lic.sync()
        lic.check_export(0)
        lic.check_export(1)
        with self.assertRaises(LicenseError) as cm:
            lic.check_export(2)
        self.assertIn('clipes', str(cm.exception))
        lic.record('clipe', 1, 'c1')
        lic.record('clipe', 1, 'c2')
        with self.assertRaises(LicenseError):
            lic.check_export(0)

    def test_analysis_pauses_when_hours_run_out_but_live_gate_still_works(self):
        lic = self.signed_in('uso3@x.com')
        self.server.pay('uso3@x.com')
        lic.sync()
        self.assertTrue(lic.allow_analysis())
        lic.record('analise_s', 3000, 'a:1:1')
        self.assertTrue(lic.allow_analysis())                       # 0,83 h de 1 h
        lic.record('analise_s', 700, 'a:1:2')
        self.assertFalse(lic.allow_analysis())
        self.assertIn('gravação continua', lic.analysis_block_reason())
        lic.check_start_live(0)                                      # iniciar live segue valendo; só a análise pausa

    def test_live_limit_comes_from_plan(self):
        lic = self.signed_in('uso4@x.com')
        self.server.pay('uso4@x.com')
        lic.sync()
        self.assertEqual(lic.max_lives(), 2)
        lic.check_start_live(1)
        with self.assertRaises(LicenseError) as cm:
            lic.check_start_live(2)
        self.assertIn('2 live(s)', str(cm.exception))

    def test_trial_limits_then_expired_blocks_new_work(self):
        lic = self.signed_in('uso5@x.com')
        acc = self.server.cloud.db.one("SELECT id FROM accounts WHERE email='uso5@x.com'")['id']
        self.server.cloud.service.suspend(acc, 'teste', 'admin:t')
        lic.sync()
        st = lic.public()
        self.assertEqual((st['state'], st['ok']), ('suspensa', False))
        with self.assertRaises(LicenseError):
            lic.check_start_live(0)
        with self.assertRaises(LicenseError):
            lic.check_export(0)
        self.assertFalse(lic.allow_analysis())

    def test_courtesy_unblocks_after_sync(self):
        lic = self.signed_in('uso6@x.com')
        acc = self.server.cloud.db.one("SELECT id FROM accounts WHERE email='uso6@x.com'")['id']
        self.server.cloud.service.suspend(acc, 'x', 'admin:t')
        lic.sync()
        self.assertFalse(lic.public()['ok'])
        self.server.cloud.service.reactivate(acc, 'admin:t')
        lic.sync()
        self.assertTrue(lic.public()['ok'])


class OfflineAndClockTests(Base):
    def test_offline_until_license_expires(self):
        lic = self.signed_in('off1@x.com')
        self.assertTrue(lic.public()['ok'])
        self.now[0] += 71 * 3600
        lic.check_active()                                           # ainda dentro das 72 h
        self.now[0] += 2 * 3600
        st = lic.public()
        self.assertEqual((st['state'], st['ok']), ('offline', False))
        with self.assertRaises(LicenseError):
            lic.check_start_live(0)

    def test_sync_failure_keeps_working_and_reports_error(self):
        lic = self.signed_in('off2@x.com')
        lic.transport = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError('sem rede'))
        ok, msg = lic.sync()
        self.assertFalse(ok)
        self.assertIn('Sem conexão', msg)
        self.assertTrue(lic.public()['ok'])
        self.assertIn('Sem conexão', lic.public()['last_error'])

    def test_clock_rollback_blocks(self):
        lic = self.signed_in('clk@x.com')
        lic.record('live', 1, 'l1')                                  # registra "visto agora"
        self.now[0] -= 3600
        st = lic.public()
        self.assertEqual((st['state'], st['ok']), ('relogio', False))
        self.now[0] += 3600
        self.assertTrue(lic.public()['ok'])

    def test_device_removed_from_account_requires_login(self):
        lic = self.signed_in('rm@x.com')
        acc = self.server.cloud.db.one("SELECT id FROM accounts WHERE email='rm@x.com'")['id']
        dev = self.server.cloud.service.devices(acc)[0]
        self.server.cloud.service.revoke_device(acc, dev['id'])
        ok, msg = lic.sync()
        self.assertFalse(ok)
        self.assertEqual(lic.public()['state'], 'sem_login')

    def test_logout_clears_everything(self):
        lic = self.signed_in('lo@x.com')
        lic.record('live', 1, 'l1')
        lic.logout()
        self.assertEqual(lic.public()['state'], 'sem_login')
        data = json.loads((self.root / 'licenca.json').read_text())
        self.assertNotIn('device_token', data)
        self.assertEqual(data['outbox'], [])
        acc = self.server.cloud.db.one("SELECT id FROM accounts WHERE email='lo@x.com'")['id']
        self.assertTrue(self.server.cloud.service.devices(acc)[0]['revoked'])

    def test_second_computer_blocked_by_plan(self):
        self.signed_in('dev@x.com')
        other_root = Path(tempfile.mkdtemp())
        (other_root / 'cloud_config.json').write_text(json.dumps(self.server.config()))
        other = Licensing(other_root, other_root / 'p', 'x', clock=lambda: self.now[0])
        with patch.object(licensing, 'device_fingerprint', return_value='outro-pc'):
            with self.assertRaises(LicenseError) as cm:
                other.login('dev@x.com', PW)
        self.assertIn('computador', str(cm.exception))

    def test_fingerprint_is_stable_and_hashed(self):
        a = licensing.device_fingerprint('semente')
        self.assertEqual(a, licensing.device_fingerprint('semente'))
        self.assertEqual(len(a), 64)


class AppIntegrationTests(Base):
    def make_app(self):
        self.write_config()
        app = App(self.root, worker=False)
        self.addCleanup(app.close)
        return app

    def test_state_exposes_license_without_secrets(self):
        app = self.make_app()
        st = app.state()
        self.assertEqual(st['license']['state'], 'sem_login')
        app.action('/api/license/register', dict(name='Ana', email='app1@x.com', password=PW, accept_terms=True))
        st = app.state()
        self.assertEqual(st['license']['email'], 'app1@x.com')
        blob = json.dumps(st)
        self.assertNotIn('device_token', blob)
        self.assertNotIn(self.server.keys[self.server.cloud.keys.kid], blob.replace('"public_keys"', ''))

    def test_gates_block_actions_without_login(self):
        app = self.make_app()
        streamer, sid, _ = setup_session(app.store)
        with self.assertRaises(ValueError) as cm:
            app.action('/api/capture/start', dict(streamer=streamer, url='https://twitch.tv/x'))
        self.assertIn('Entre com a sua conta', str(cm.exception))
        with self.assertRaises(ValueError):
            app.action('/api/video/url', dict(streamer=streamer, url='https://youtube.com/watch?v=x'))
        with self.assertRaises(ValueError):
            app.action('/api/video/import', dict(streamer=streamer, path=str(self.root / 'x.mp4')))
        item, _ = candidate(app.store, sid)
        with self.assertRaises(ValueError):
            app.review(dict(id=item['id'], version=item['version'], start=10, end=30, action='approve'))
        self.assertEqual(app.store.candidate(item['id'])['status'], 'pending')

    def test_review_approval_counts_quota(self):
        app = self.make_app()
        app.action('/api/license/register', dict(name='Ana', email='app2@x.com', password=PW, accept_terms=True))
        self.server.pay('app2@x.com')
        app.license.sync()
        streamer, sid, _ = setup_session(app.store)
        a, _ = candidate(app.store, sid, 10, 30)
        b, _ = candidate(app.store, sid, 40, 60)
        c, _ = candidate(app.store, sid, 5, 8)
        with patch.object(app.store, 'review', return_value=2) as review:
            for item in (a, b):
                app.review(dict(id=item['id'], version=item['version'], start=item['start'], end=item['end'], action='approve'))
            self.assertEqual(review.call_count, 2)
        with app.store.connect(True) as conn:
            conn.execute("UPDATE candidates SET status='approved' WHERE id IN (?,?)", (a['id'], b['id']))
        with self.assertRaises(ValueError) as cm:
            app.review(dict(id=c['id'], version=c['version'], start=5, end=8, action='approve'))
        self.assertIn('Faça upgrade', str(cm.exception))

    def test_capture_limit_is_min_of_user_and_plan(self):
        app = self.make_app()
        app.action('/api/license/register', dict(name='Ana', email='app3@x.com', password=PW, accept_terms=True))
        self.assertEqual(app.capture.limit(), 1)                      # teste: 1 live
        self.server.pay('app3@x.com')
        app.license.sync()
        self.assertEqual(app.capture.limit(), 2)
        app.store.setting('capture_limit', 1)
        self.assertEqual(app.capture.limit(), 1)

    def test_capture_start_records_live_event(self):
        app = self.make_app()
        app.action('/api/license/register', dict(name='Ana', email='app4@x.com', password=PW, accept_terms=True))
        streamer, sid, _ = setup_session(app.store)
        with patch.object(app.capture, 'start', return_value='sess1'), patch.object(app.capture, 'state', return_value=[]):
            app.action('/api/capture/start', dict(streamer=streamer, url='https://twitch.tv/x'))
        self.assertEqual([e['kind'] for e in app.license.data['outbox']], ['live'])

    def test_analysis_is_paused_by_hour_quota(self):
        app = self.make_app()
        app.action('/api/license/register', dict(name='Ana', email='app5@x.com', password=PW, accept_terms=True))
        self.server.pay('app5@x.com')
        app.license.sync()
        app.license.record('analise_s', 3700, 'a:x:1')                # passou de 1 h
        streamer, sid, _ = setup_session(app.store, status='new')
        session = app.store.session(sid)
        profile = app.store.streamer(streamer)['profile']
        self.assertFalse(app.engine.analyze_one(session, profile))
        self.assertTrue(all(r['status'] == 'new' for r in app.store.segments(sid)))     # nada foi mexido

    def test_logout_refused_while_capturing(self):
        app = self.make_app()
        app.action('/api/license/register', dict(name='Ana', email='app6@x.com', password=PW, accept_terms=True))
        with patch.object(app.capture, 'state', return_value=[dict(session='s')]):
            with self.assertRaises(ValueError):
                app.action('/api/license/logout', {})
        self.assertEqual(app.license.public()['email'], 'app6@x.com')

    def test_free_mode_app_has_no_limits(self):
        app = App(self.root / 'livre', worker=False)
        self.addCleanup(app.close)
        self.assertEqual(app.state()['license']['mode'], 'livre')
        self.assertEqual(app.capture.limit(), 5)


if __name__ == '__main__':
    unittest.main()
