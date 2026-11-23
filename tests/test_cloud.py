"""Servidor SaaS (hooks_cloud): contas, licença, cotas, cobrança, webhook, painel, segurança e LGPD."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from hooks_cloud import keys as ckeys, security as sec
from hooks_cloud.service import Bad, DAY
from hooks_cloud.web import Cloud, serve

CHEAP = dict(n=2 ** 4, r=1, p=1)
PW = 'Uma-Senha-Boa-2026'


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def add(self, days=0, seconds=0):
        self.t += days * DAY + seconds


def make(env=None, transport=None):
    clock = Clock()
    tmp = tempfile.TemporaryDirectory()
    cloud = Cloud(Path(tmp.name), env=env if env is not None else {}, clock=clock, hash_params=CHEAP, asaas_transport=transport)
    cloud.tmp = tmp
    cloud.clock = clock
    return cloud


def enable_plans(cloud):
    with cloud.db.connect(True) as c:
        c.execute("UPDATE plans SET price_cents=9900,active=1 WHERE code='basico'")
        c.execute("UPDATE plans SET price_cents=19900,active=1 WHERE code='pro'")


def signup(cloud, email='ana@x.com', name='Ana Souza', ip='1.1.1.1'):
    return cloud.service.register(email, PW, name, True, ip)


def activate(cloud, email='ana@x.com', fp='PC-1'):
    return cloud.service.activate(email, PW, fp, 'Notebook', 'Windows', '0.16', '1.1.1.1')


def ev(kind, amount, eid):
    return dict(kind=kind, amount=amount, id=eid)


class SecurityTests(unittest.TestCase):
    def test_password_hash_roundtrip_and_rules(self):
        h = sec.hash_password('segredo-bem-longo', CHEAP)
        self.assertTrue(sec.verify_password('segredo-bem-longo', h))
        self.assertFalse(sec.verify_password('outra', h))
        self.assertNotEqual(h, sec.hash_password('segredo-bem-longo', CHEAP))
        self.assertTrue(sec.password_problem('curta1'))
        self.assertTrue(sec.password_problem('1234567890'))
        self.assertTrue(sec.password_problem('12345678910', 'x@y.com'))
        self.assertFalse(sec.password_problem('Cavalo-Verde-Lua-91', 'x@y.com'))

    def test_totp_rfc6238_vector(self):
        secret = base64_secret = __import__('base64').b32encode(b'12345678901234567890').decode()
        self.assertEqual(sec.totp_code(secret, 59), '287082')
        self.assertTrue(sec.totp_ok(secret, '287082', 59))
        self.assertFalse(sec.totp_ok(secret, '000000', 59))

    def test_rate_limiter(self):
        t = [0.0]
        rl = sec.RateLimiter(lambda: t[0])
        self.assertTrue(all(rl.allow('k', 3, 10) for _ in range(3)))
        self.assertFalse(rl.allow('k', 3, 10))
        t[0] = 11
        self.assertTrue(rl.allow('k', 3, 10))

    def test_license_signature(self):
        cloud = make()
        pub = {cloud.keys.kid: cloud.keys.public_b64}
        token = cloud.keys.sign(dict(a=1))
        self.assertEqual(ckeys.verify(token, pub)['a'], 1)
        head, body, sig = token.split('.')
        forged = '.'.join((head, ckeys.b64e(json.dumps(dict(a=2, kid=cloud.keys.kid)).encode()), sig))
        with self.assertRaises(ValueError):
            ckeys.verify(forged, pub)
        other = make()
        with self.assertRaises(ValueError):
            ckeys.verify(token, {cloud.keys.kid: other.keys.public_b64})


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.c = make()
        self.s = self.c.service

    def test_register_validations(self):
        with self.assertRaises(Bad):
            self.s.register('invalido', PW, 'X', True)
        with self.assertRaises(Bad):
            self.s.register('a@b.com', 'curta', 'X', True)
        with self.assertRaises(Bad):
            self.s.register('a@b.com', PW, 'X', False)
        signup(self.c)
        with self.assertRaises(Bad):
            signup(self.c, 'ANA@x.com')

    def test_register_creates_trial_and_welcome_mail(self):
        acc = signup(self.c)
        ent = self.s.entitlement(acc['id'])
        self.assertEqual(ent['state'], 'teste')
        self.assertTrue(ent['ok'])
        self.assertEqual(ent['plan'], 'teste')
        mails = self.c.db.rows('SELECT template FROM outbox')
        self.assertIn('boas_vindas', [m['template'] for m in mails])

    def test_signup_can_be_closed(self):
        self.c.db.set_setting('signup_open', False)
        with self.assertRaises(Bad) as cm:
            signup(self.c)
        self.assertEqual(cm.exception.status, 403)

    def test_login_lockout_and_unknown_email_same_message(self):
        signup(self.c)
        msgs = set()
        for _ in range(8):
            with self.assertRaises(Bad) as cm:
                self.s.authenticate('ana@x.com', 'errada-errada', '2.2.2.2')
            msgs.add(str(cm.exception))
        with self.assertRaises(Bad) as locked:
            self.s.authenticate('ana@x.com', PW, '2.2.2.2')
        self.assertEqual(locked.exception.status, 429)
        with self.assertRaises(Bad) as unknown:
            self.s.authenticate('nao@existe.com', 'qualquer-coisa-1', '3.3.3.3')
        self.assertIn(str(unknown.exception), msgs)
        self.c.clock.add(seconds=16 * 60)
        self.assertEqual(self.s.authenticate('ana@x.com', PW, '2.2.2.2')['email'], 'ana@x.com')

    def test_password_reset_flow(self):
        acc = signup(self.c)
        self.s.request_reset('ana@x.com', '1.1.1.1')
        self.s.request_reset('ninguem@x.com', '1.1.1.1')   # não revela se existe
        mail = self.c.db.one("SELECT body FROM outbox WHERE template='redefinir_senha'")
        token = mail['body'].split('reset=')[1].split()[0].strip()
        self.s.confirm_reset(token, 'Nova-Senha-Forte-77', '1.1.1.1')
        with self.assertRaises(Bad):
            self.s.confirm_reset(token, 'Outra-Senha-Forte-88', '1.1.1.1')     # uso único
        self.assertEqual(self.s.authenticate('ana@x.com', 'Nova-Senha-Forte-77')['id'], acc['id'])
        self.assertIsNotNone(self.c.db.one("SELECT 1 FROM outbox WHERE template='senha_alterada'"))

    def test_reset_expires(self):
        signup(self.c)
        self.s.request_reset('ana@x.com')
        token = self.c.db.one("SELECT body FROM outbox WHERE template='redefinir_senha'")['body'].split('reset=')[1].split()[0].strip()
        self.c.clock.add(seconds=2 * 3600)
        with self.assertRaises(Bad):
            self.s.confirm_reset(token, 'Nova-Senha-Forte-77')


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.c = make()
        self.s = self.c.service
        enable_plans(self.c)
        self.acc = signup(self.c)
        self.pub = {self.c.keys.kid: self.c.keys.public_b64}

    def lic(self, token):
        return ckeys.verify(token, self.pub)

    def test_activate_returns_verifiable_license(self):
        out = activate(self.c)
        data = self.lic(out['license'])
        self.assertEqual(data['state'], 'teste')
        self.assertEqual(data['email'], 'ana@x.com')
        self.assertEqual(data['exp'] - data['iat'], 72 * 3600)
        self.assertTrue(data['ok'])

    def test_device_limit_and_replace(self):
        activate(self.c, fp='PC-1')
        with self.assertRaises(Bad) as cm:
            activate(self.c, fp='PC-2')
        self.assertEqual(cm.exception.code, 'limite_dispositivos')
        activate(self.c, fp='PC-1')                      # mesmo computador reativa sem gastar vaga
        dev = self.s.devices(self.acc['id'])[0]
        self.s.revoke_device(self.acc['id'], dev['id'])
        activate(self.c, fp='PC-2')                      # vaga liberada

    def test_revoked_device_loses_access(self):
        out = activate(self.c)
        dev = self.s.devices(self.acc['id'])[0]
        self.s.revoke_device(self.acc['id'], dev['id'])
        with self.assertRaises(Bad) as cm:
            self.s.sync(out['device_token'])
        self.assertEqual(cm.exception.status, 401)

    def test_sync_usage_is_idempotent_and_limited(self):
        out = activate(self.c)
        tok = out['device_token']
        events = [ev('analise_s', 3600, 'a1'), ev('clipe', 1, 'c1'), ev('clipe', 1, 'c2'), ev('live', 1, 'l1')]
        r = self.s.sync(tok, events, dict(lives=2, version='0.16'))
        self.assertEqual(r['accepted'], 4)
        r = self.s.sync(tok, events)                     # reenvio não duplica
        data = self.lic(r['license'])
        self.assertAlmostEqual(data['usage']['horas'], 1.0, places=3)
        self.assertEqual(data['usage']['clipes'], 2)
        self.assertEqual(data['usage']['lives'], 1)
        bad = [ev('analise_s', 99999, 'x1'), ev('clipe', -1, 'x2'), ev('inventado', 1, 'x3'), dict(kind='clipe', amount=1)]
        self.assertEqual(self.s.sync(tok, bad)['accepted'], 0)

    def test_two_accounts_same_event_id_do_not_collide(self):
        signup(self.c, 'bia@x.com', 'Bia')
        a = activate(self.c, 'ana@x.com')
        b = activate(self.c, 'bia@x.com', fp='PC-9')
        self.s.sync(a['device_token'], [ev('clipe', 1, 'same')])
        self.s.sync(b['device_token'], [ev('clipe', 1, 'same')])
        self.assertEqual(self.c.db.one("SELECT COUNT(*) n FROM usage_events WHERE kind='clipe'")['n'], 2)

    def test_state_machine_trial_to_expired(self):
        out = activate(self.c)
        self.assertEqual(self.lic(self.s.sync(out['device_token'])['license'])['state'], 'teste')
        self.c.clock.add(days=7, seconds=10)
        d = self.lic(self.s.sync(out['device_token'])['license'])
        self.assertEqual(d['state'], 'expirada')
        self.assertFalse(d['ok'])

    def test_payment_then_grace_then_expiry(self):
        out = activate(self.c)
        self.s.apply_payment(self.acc['id'], 9900, 'pix', 'ref1', plan_code='basico', actor='admin:t')
        st = lambda: self.lic(self.s.sync(out['device_token'])['license'])['state']
        self.assertEqual(st(), 'ativa')
        self.c.clock.add(days=32)
        self.assertEqual(st(), 'atraso')
        self.c.clock.add(days=6)
        self.assertEqual(st(), 'expirada')

    def test_paying_late_continues_old_period(self):
        sub0 = self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r1', plan_code='basico', actor='t')['payment']
        self.c.clock.add(days=32)                        # 2 dias de atraso, dentro da tolerância
        p2 = self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r2', plan_code='basico', actor='t')['payment']
        self.assertEqual(p2['period_start'], sub0['period_end'])
        self.c.clock.add(days=40)                        # passou da tolerância: recomeça de hoje
        p3 = self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r3', plan_code='basico', actor='t')['payment']
        self.assertEqual(p3['period_start'], self.c.clock.t)

    def test_plan_limits_come_from_plan_and_adjustments(self):
        self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        ent = self.s.entitlement(self.acc['id'])
        self.assertEqual(ent['limits']['clipes'], 60)
        self.s.adjust(self.acc['id'], 'clipes', 15, 'cortesia', 'admin:t')
        self.assertEqual(self.s.entitlement(self.acc['id'])['limits']['clipes'], 75)
        self.c.clock.add(days=40)                        # ajuste vale só no período (+ tolerância)
        self.assertEqual(self.s.entitlement(self.acc['id'])['limits']['clipes'], 60)

    def test_usage_resets_with_new_period(self):
        out = activate(self.c)
        self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        self.s.sync(out['device_token'], [ev('clipe', 1, 'c1')])
        self.assertEqual(self.s.entitlement(self.acc['id'])['usage']['clipes'], 1)
        self.c.clock.add(days=31)
        self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r2', plan_code='basico', actor='t')
        self.assertEqual(self.s.entitlement(self.acc['id'])['usage']['clipes'], 0)

    def test_quota_alerts_80_and_100_once(self):
        out = activate(self.c)
        self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        self.s.sync(out['device_token'], [ev('clipe', 1, f'c{i}') for i in range(48)])
        self.s.sync(out['device_token'], [])
        self.assertEqual(self.c.db.one("SELECT COUNT(*) n FROM outbox WHERE template='cota_80'")['n'], 1)
        self.s.sync(out['device_token'], [ev('clipe', 1, f'd{i}') for i in range(12)])
        self.assertEqual(self.c.db.one("SELECT COUNT(*) n FROM outbox WHERE template='cota_100'")['n'], 1)

    def test_suspend_reactivate_cancel(self):
        out = activate(self.c)
        self.s.apply_payment(self.acc['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        self.s.suspend(self.acc['id'], 'abuso', 'admin:t')
        d = self.lic(self.s.sync(out['device_token'])['license'])
        self.assertEqual(d['state'], 'suspensa')
        self.assertIn('abuso', d['msg'])
        self.s.reactivate(self.acc['id'], 'admin:t')
        self.assertEqual(self.s.entitlement(self.acc['id'])['state'], 'ativa')
        self.s.cancel(self.acc['id'], 'cliente')
        self.assertEqual(self.s.entitlement(self.acc['id'])['state'], 'cancelada')
        self.assertTrue(self.s.entitlement(self.acc['id'])['ok'])       # vale até o fim do período
        self.c.clock.add(days=32)
        self.assertEqual(self.s.entitlement(self.acc['id'])['state'], 'expirada')

    def test_courtesy_and_trial_extension(self):
        self.s.extend_trial(self.acc['id'], 5, 'admin:t')
        self.c.clock.add(days=10)
        self.assertEqual(self.s.entitlement(self.acc['id'])['state'], 'teste')
        self.s.courtesy(self.acc['id'], 30, 'pro', 'parceria', 'admin:t')
        ent = self.s.entitlement(self.acc['id'])
        self.assertEqual((ent['state'], ent['plan']), ('ativa', 'pro'))
        self.assertEqual(self.c.db.one("SELECT COUNT(*) n FROM payments WHERE amount_cents>0")['n'], 0)

    def test_inactive_plan_cannot_be_sold(self):
        with self.assertRaises(Bad):
            self.s.create_charge(self.acc['id'], 'agencia')
        with self.assertRaises(Bad):
            self.s.create_charge(self.acc['id'], 'teste')


class BillingTests(unittest.TestCase):
    def test_manual_charge_and_confirmation_idempotent(self):
        c = make()
        s = c.service
        enable_plans(c)
        acc = signup(c)
        s.db.set_setting('pix_key', 'pix@jb.com')
        r = c.billing.checkout(acc['id'], 'basico')
        self.assertEqual(r['tipo'], 'manual')
        self.assertIn('pix@jb.com', r['instrucoes'])
        self.assertEqual(s.entitlement(acc['id'])['state'], 'teste')      # só o pagamento libera
        s.confirm_manual_payment(r['pagamento_id'], 'admin:t')
        self.assertEqual(s.entitlement(acc['id'])['state'], 'ativa')
        with self.assertRaises(Bad):
            s.confirm_manual_payment(r['pagamento_id'], 'admin:t')
        self.assertEqual(s.db.one("SELECT COUNT(*) n FROM payments WHERE status='pago'")['n'], 1)

    def asaas_cloud(self):
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, body))
            if url.endswith('/customers'):
                return 200, dict(id='cus_1')
            if url.endswith('/subscriptions'):
                return 200, dict(id='sub_1', paymentLink='https://pay/x')
            if '/subscriptions/sub_1/payments' in url:
                return 200, dict(data=[dict(invoiceUrl='https://pay/inv')])
            return 200, dict()
        c = make(env=dict(HOOKS_ASAAS_KEY='k', HOOKS_ASAAS_WEBHOOK_TOKEN='tok-secreto-123'), transport=transport)
        c.service.db.set_setting('billing_provider', 'asaas')
        enable_plans(c)
        return c, calls

    def hook(self, c, event, payment, eid, token='tok-secreto-123'):
        raw = json.dumps(dict(id=eid, event=event, payment=payment)).encode()
        return c.billing.webhook({'asaas-access-token': token}, raw)

    def test_checkout_asaas_needs_document_then_creates(self):
        c, calls = self.asaas_cloud()
        acc = signup(c)
        with self.assertRaises(Bad) as cm:
            c.billing.checkout(acc['id'], 'basico')
        self.assertEqual(cm.exception.code, 'documento')
        c.billing.save_profile(acc['id'], doc='529.982.247-25')
        r = c.billing.checkout(acc['id'], 'basico')
        self.assertEqual((r['tipo'], r['link']), ('asaas', 'https://pay/inv'))
        self.assertEqual(c.service.subscription(acc['id'])['provider_sub'], 'sub_1')

    def test_invalid_document_rejected(self):
        c = make()
        acc = signup(c)
        with self.assertRaises(Bad):
            c.billing.save_profile(acc['id'], doc='111.111.111-11')

    def test_webhook_token_idempotency_and_flow(self):
        c, _ = self.asaas_cloud()
        acc = signup(c)
        c.billing.save_profile(acc['id'], doc='529.982.247-25')
        c.billing.checkout(acc['id'], 'basico')
        pay = dict(id='pay_1', subscription='sub_1', customer='cus_1', value=99.0, billingType='PIX', dueDate='2026-12-01')
        self.assertEqual(self.hook(c, 'PAYMENT_CREATED', pay, 'e1', token='errado')[0], 401)
        self.assertEqual(c.service.db.one('SELECT COUNT(*) n FROM webhook_events')['n'], 0)
        self.assertEqual(self.hook(c, 'PAYMENT_CREATED', pay, 'e1')[0], 200)
        self.assertEqual(c.service.entitlement(acc['id'])['state'], 'teste')
        self.assertEqual(self.hook(c, 'PAYMENT_RECEIVED', pay, 'e2')[0], 200)
        self.assertEqual(c.service.entitlement(acc['id'])['state'], 'ativa')
        self.assertTrue(self.hook(c, 'PAYMENT_RECEIVED', pay, 'e2')[1].get('duplicado'))
        self.hook(c, 'PAYMENT_CONFIRMED', pay, 'e3')                      # outro aviso do mesmo pagamento
        self.assertEqual(c.service.db.one("SELECT COUNT(*) n FROM payments WHERE status='pago'")['n'], 1)

    def test_webhook_refund_suspends_and_unknown_is_visible_error(self):
        c, _ = self.asaas_cloud()
        acc = signup(c)
        c.billing.save_profile(acc['id'], doc='529.982.247-25')
        c.billing.checkout(acc['id'], 'basico')
        pay = dict(id='pay_1', subscription='sub_1', customer='cus_1', value=99.0, billingType='PIX')
        self.hook(c, 'PAYMENT_RECEIVED', pay, 'e1')
        self.hook(c, 'PAYMENT_REFUNDED', pay, 'e2')
        self.assertEqual(c.service.entitlement(acc['id'])['state'], 'suspensa')
        self.hook(c, 'PAYMENT_RECEIVED', dict(id='p2', subscription='sub_x', value=10), 'e3')
        self.assertEqual(c.service.db.one("SELECT status FROM webhook_events WHERE event_id='e3'")['status'], 'erro')

    def test_webhook_without_token_configured_is_closed(self):
        c = make()
        self.assertEqual(c.billing.webhook({}, b'{}')[0], 503)

    def test_valid_docs(self):
        from hooks_cloud.billing import valid_cnpj, valid_cpf
        self.assertTrue(valid_cpf('529.982.247-25'))
        self.assertFalse(valid_cpf('529.982.247-24'))
        self.assertTrue(valid_cnpj('11.222.333/0001-81'))
        self.assertFalse(valid_cnpj('11.222.333/0001-80'))


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.c = make()
        self.a = self.c.admin
        self.a.create_admin('dono@x.com', 'Dono', 'Senha-Dono-Forte-1', 'dono', 'teste')
        self.a.create_admin('fin@x.com', 'Fin', 'Senha-Fin-Forte-1', 'financeiro', 'teste')
        self.a.create_admin('sup@x.com', 'Sup', 'Senha-Sup-Forte-1', 'suporte', 'teste')

    def login(self, email, pw, code=''):
        token, csrf, adm = self.a.login(email, pw, code, '9.9.9.9')
        return self.a.session(token)['admin']

    def test_login_and_wrong_password(self):
        self.assertEqual(self.login('dono@x.com', 'Senha-Dono-Forte-1')['role'], 'dono')
        with self.assertRaises(Bad):
            self.a.login('dono@x.com', 'errada-errada-1', '', '9.9.9.9')

    def test_roles(self):
        dono, fin, sup = (self.login(e, p) for e, p in (('dono@x.com', 'Senha-Dono-Forte-1'), ('fin@x.com', 'Senha-Fin-Forte-1'), ('sup@x.com', 'Senha-Sup-Forte-1')))
        self.a.require(dono, 'excluir')
        self.a.require(fin, 'pagamento')
        with self.assertRaises(Bad):
            self.a.require(fin, '*')
        with self.assertRaises(Bad):
            self.a.require(sup, 'pagamento')
        self.a.require(sup, 'nota')
        with self.assertRaises(Bad):
            self.a.save_plan(fin, dict(code='x'))

    def test_totp_required_after_enabled(self):
        adm = self.login('dono@x.com', 'Senha-Dono-Forte-1')
        info = self.a.begin_totp(adm)
        self.a.confirm_totp(adm, sec.totp_code(info['secret'], self.c.clock.t))
        with self.assertRaises(Bad) as cm:
            self.a.login('dono@x.com', 'Senha-Dono-Forte-1', '', '9.9.9.9')
        self.assertEqual(cm.exception.code, 'totp')
        with self.assertRaises(Bad):
            self.a.login('dono@x.com', 'Senha-Dono-Forte-1', '000000', '9.9.9.9')
        self.c.clock.add(seconds=40)
        self.a.login('dono@x.com', 'Senha-Dono-Forte-1', sec.totp_code(info['secret'], self.c.clock.t), '9.9.9.9')

    def test_session_expires_and_logout(self):
        token, csrf, adm = self.a.login('dono@x.com', 'Senha-Dono-Forte-1', '', '9.9.9.9')
        self.assertTrue(self.a.session(token))
        self.a.logout(token)
        self.assertFalse(self.a.session(token))
        token, *_ = self.a.login('dono@x.com', 'Senha-Dono-Forte-1', '', '9.9.9.9')
        self.c.clock.add(days=2)
        self.assertFalse(self.a.session(token))

    def test_cannot_remove_own_owner_access(self):
        dono = self.login('dono@x.com', 'Senha-Dono-Forte-1')
        with self.assertRaises(Bad):
            self.a.set_admin(dono, dono['id'], active=False)

    def test_plan_rules(self):
        dono = self.login('dono@x.com', 'Senha-Dono-Forte-1')
        base = dict(code='vip', name='VIP', price_cents=0, max_lives=2, hours_month=10, clips_month=10, max_streamers=1, max_devices=1, active=True)
        with self.assertRaises(Bad):
            self.a.save_plan(dono, base)                      # ativo sem preço
        self.a.save_plan(dono, dict(base, price_cents=5000))
        with self.assertRaises(Bad):
            self.a.save_plan(dono, dict(base, price_cents=5000, max_lives=9))
        with self.assertRaises(Bad):
            self.a.save_plan(dono, dict(base, code='a b!'))

    def test_settings_validation_and_audit(self):
        dono = self.login('dono@x.com', 'Senha-Dono-Forte-1')
        with self.assertRaises(Bad):
            self.a.save_settings(dono, dict(trial_days=0))
        with self.assertRaises(Bad):
            self.a.save_settings(dono, dict(billing_provider='paypal'))
        self.a.save_settings(dono, dict(trial_days=14, grace_days=3, pix_key='k@k.com', chave_inexistente='x'))
        self.assertEqual(self.c.service.setting('trial_days'), 14)
        self.assertEqual(self.a.audit_list('config', 'configuracao_alterada')[0]['actor'], 'admin:dono@x.com')

    def test_metrics_and_customer_detail(self):
        enable_plans(self.c)
        s = self.c.service
        a1, a2 = signup(self.c), signup(self.c, 'bia@x.com', 'Bia')
        s.apply_payment(a1['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        m = self.a.metrics()
        self.assertEqual((m['mrr_cents'], m['pagantes'], m['estados']['ativa'], m['estados']['teste']), (9900, 1, 1, 1))
        self.assertEqual(m['receita_mes_cents'], 9900)
        det = self.a.customer(a1['id'])
        self.assertEqual(det['estado'], 'ativa')
        self.assertEqual(len(det['pagamentos']), 1)
        found = self.a.customers(q='bia')
        self.assertEqual(found['total'], 1)
        self.assertEqual([x['email'] for x in self.a.customers(state='ativa')['items']], [a1['email']])

    def test_pagination(self):
        for i in range(12):
            signup(self.c, f'u{i}@x.com', f'U{i}', f'10.0.0.{i}')
        p = self.a.customers(page=2, size=5)
        self.assertEqual((p['total'], len(p['items']), p['page']), (12, 5, 2))


class PrivacyTests(unittest.TestCase):
    def test_export_delete_and_retention(self):
        c = make()
        s = c.service
        enable_plans(c)
        acc = signup(c)
        out = activate(c)
        s.apply_payment(acc['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        s.sync(out['device_token'], [ev('clipe', 1, 'c1')])
        data = s.export_account(acc['id'])
        self.assertEqual(data['conta']['email'], 'ana@x.com')
        self.assertNotIn('pw_hash', json.dumps(data))
        rid = s.privacy_request(acc['id'], 'exclusao')
        self.assertEqual(s.privacy_request(acc['id'], 'exclusao'), rid)        # não duplica pedido aberto
        s.delete_account(acc['id'], 'admin:t')
        row = c.db.one('SELECT * FROM accounts WHERE id=?', (acc['id'],))
        self.assertEqual((row['status'], row['name'], row['doc']), ('excluida', 'Conta excluída', ''))
        self.assertNotIn('ana@x.com', row['email'])
        self.assertEqual(c.db.one('SELECT COUNT(*) n FROM usage_events')['n'], 0)
        self.assertEqual(c.db.one('SELECT COUNT(*) n FROM payments')['n'], 1)    # guarda fiscal
        self.assertEqual(c.db.one('SELECT status FROM privacy_requests WHERE id=?', (rid,))['status'], 'concluida')
        with self.assertRaises(Bad):
            s.authenticate('ana@x.com', PW)
        signup(c)                                                                 # e-mail volta a ficar livre

    def test_invalid_request_kind(self):
        c = make()
        acc = signup(c)
        with self.assertRaises(Bad):
            c.service.privacy_request(acc['id'], 'qualquer')

    def test_legal_pages_are_flagged_drafts(self):
        from hooks_cloud.web import legal
        self.assertIn(b'RASCUNHO', legal(make(), 'termos'))


class AutoBackupTests(unittest.TestCase):
    def run_at(self, c, when, keep=3):
        """Roda o backup no relógio simulado e acerta a data do arquivo para o mesmo relógio."""
        import os
        name = c.auto_backup(keep=keep, now=when)
        if name:
            os.utime(c.root / 'backups' / name, (when, when))
        return name

    def test_daily_backup_keeps_last_n_and_skips_when_recent(self):
        c = make()
        base = 1_800_000_000.0
        first = self.run_at(c, base)
        self.assertTrue(first and first.startswith('auto_'))
        self.assertIsNone(self.run_at(c, base + 3600))                           # menos de 20 h: não repete
        for i in range(1, 6):
            self.assertTrue(self.run_at(c, base + i * 86400))
        folder = c.root / 'backups'
        self.assertEqual(len(list(folder.glob('auto_*.sqlite3'))), 3)
        import sqlite3
        newest = max(folder.glob('auto_*.sqlite3'), key=lambda f: f.name)
        self.assertGreater(sqlite3.connect(newest).execute("select count(*) from plans").fetchone()[0], 0)

    def test_favicon_is_served(self):
        c = make()
        c.clock = __import__('time').time
        srv = serve(c, '127.0.0.1', 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        data = urllib.request.urlopen(f'http://127.0.0.1:{srv.server_address[1]}/favicon.ico', timeout=5).read()
        self.assertEqual(data[:4], b'\x00\x00\x01\x00')


class JobsTests(unittest.TestCase):
    def test_lifecycle_emails_dedupe(self):
        c = make()
        s = c.service
        enable_plans(c)
        acc = signup(c)
        c.clock.add(days=5)
        s.run_jobs()
        s.run_jobs()
        n = lambda t: c.db.one('SELECT COUNT(*) n FROM outbox WHERE template=?', (t,))['n']
        self.assertEqual(n('teste_acabando'), 1)
        c.clock.add(days=3)
        s.run_jobs()
        self.assertEqual(n('teste_acabou'), 1)
        s.apply_payment(acc['id'], 9900, 'pix', 'r', plan_code='basico', actor='t')
        c.clock.add(days=28)
        s.run_jobs()
        s.run_jobs()
        self.assertEqual(n('cobranca_proxima'), 1)
        self.assertEqual(c.db.one("SELECT COUNT(*) n FROM payments WHERE status='pendente'")['n'], 1)
        c.clock.add(days=5)
        s.run_jobs()
        self.assertEqual(n('pagamento_atrasado'), 1)

    def test_mail_flush_with_smtp_and_failure(self):
        sent = []

        class Fake:
            def __init__(self, fail):
                self.fail = fail

            def send(self, to, subject, body):
                if self.fail:
                    raise RuntimeError('smtp fora')
                sent.append(to)
        env = dict(HOOKS_SMTP_HOST='h', HOOKS_SMTP_FROM='x@y.com')
        c = make(env=env)
        c.mail.send = Fake(False).send
        signup(c)
        self.assertEqual(c.mail.flush(c.db, now=c.clock)['sent'], 1)
        self.assertEqual(sent, ['ana@x.com'])
        c.mail.send = Fake(True).send
        signup(c, 'b@x.com', 'B')
        r = c.mail.flush(c.db, now=c.clock)
        self.assertEqual((r['sent'], r['failed']), (0, 1))
        self.assertEqual(c.db.one("SELECT status FROM outbox WHERE to_email='b@x.com'")['status'], 'pendente')

    def test_without_smtp_mail_stays_queued(self):
        c = make()
        signup(c)
        self.assertFalse(c.mail.flush(c.db, now=c.clock)['configured'])
        self.assertEqual(c.db.one("SELECT COUNT(*) n FROM outbox WHERE status='pendente'")['n'], 1)

    def test_backup_is_valid_sqlite(self):
        import sqlite3
        c = make()
        signup(c)
        target = Path(c.tmp.name) / 'b.sqlite3'
        c.db.backup(target)
        con = sqlite3.connect(target)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0], 1)
        con.close()


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = make(env={'HOOKS_ASAAS_WEBHOOK_TOKEN': 'tok-secreto-123'})
        cls.c.clock = __import__('time').time          # servidor real usa o relógio real
        cls.c.service.clock = cls.c.clock
        cls.c.limiter.clock = cls.c.clock
        enable_plans(cls.c)
        cls.c.admin.create_admin('dono@x.com', 'Dono', 'Senha-Dono-Forte-1', 'dono', 'teste')
        cls.srv = serve(cls.c, '127.0.0.1', 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, method, path, data=None, headers=None, raw=False):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method=method,
                                     data=json.dumps(data).encode() if data is not None else (b'' if method == 'POST' else None),
                                     headers=dict({'Content-Type': 'application/json'}, **(headers or {})))
        try:
            resp = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as err:
            resp = err
        body = resp.read()
        out = body if raw else (json.loads(body) if body else {})
        return resp.status if hasattr(resp, 'status') else resp.code, out, resp.headers

    def test_admin_bad_input_is_400_never_500(self):
        """Regressão da auditoria da 0.16: lixo nos campos do painel não pode virar erro 500."""
        st, body, h = self.call('POST', '/admin/api/login', {'email': 'dono@x.com', 'password': 'Senha-Dono-Forte-1'})
        self.assertEqual(st, 200)
        cookie = h['Set-Cookie'].split(';')[0]
        hdr = {'Cookie': cookie, 'X-CSRF': body['csrf']}
        original = self.c.limiter.allow
        self.c.limiter.allow = lambda *a, **k: True        # o teste manda centenas de pedidos; sem isto o limite por IP responderia 429 e esconderia falhas
        self.addCleanup(setattr, self.c.limiter, 'allow', original)
        junk = [None, '', 'abc', -1, 10 ** 30, 1.5, float(1e308), True, [], {}, ['a'], {'a': 1}, 'a' * 3000]
        routes = ['/customer/extend-trial', '/customer/courtesy', '/customer/grace', '/customer/mark-paid', '/customer/change-plan',
                  '/customer/suspend', '/customer/cancel', '/customer/delete', '/customer/export', '/webhook/reprocess',
                  '/outbox/mark-sent', '/privacy/finish', '/customer/reset-link', '/customer/device-revoke']
        bad = []
        for route in routes:
            for field in ('id', 'dias', 'valor', 'plano'):
                for value in junk:
                    payload = {'id': 'x', field: value} if field != 'id' else {'id': value}
                    st, _, _ = self.call('POST', '/admin/api' + route, payload, headers=hdr)
                    if st >= 500 or st == 429:
                        bad.append((route, field, str(value)[:15], st))
        self.assertEqual(bad, [])
        st, _, _ = self.call('GET', '/admin/api/customers?size=abc&page=xyz', headers=hdr)
        self.assertEqual(st, 400)

    def test_health_pages_and_headers(self):
        st, body, h = self.call('GET', '/healthz')
        self.assertEqual((st, body['ok']), (200, True))
        for page in ('/conta', '/admin', '/termos', '/privacidade'):
            st, body, h = self.call('GET', page, raw=True)
            self.assertEqual(st, 200, page)
            self.assertIn('Content-Security-Policy', h)
            self.assertEqual(h['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.call('GET', '/nada')[0], 404)

    def test_public_plans_hide_drafts(self):
        st, body, _ = self.call('GET', '/v1/plans')
        codes = [p['code'] for p in body['planos']]
        self.assertEqual(sorted(codes), ['basico', 'pro'])

    def test_app_flow_register_activate_sync(self):
        st, body, _ = self.call('POST', '/v1/register', dict(email='http1@x.com', password=PW, name='Http Um', accept_terms=True))
        self.assertEqual(st, 201)
        st, act, _ = self.call('POST', '/v1/activate', dict(email='http1@x.com', password=PW, fingerprint='fp-http', device_name='PC', os='Windows', app_version='0.16'))
        self.assertEqual(st, 200)
        lic = ckeys.verify(act['license'], {self.c.keys.kid: self.c.keys.public_b64})
        self.assertEqual(lic['state'], 'teste')
        auth = {'Authorization': 'Bearer ' + act['device_token']}
        st, syn, _ = self.call('POST', '/v1/sync', dict(events=[ev('clipe', 1, 'h1')], info=dict(lives=1)), auth)
        self.assertEqual((st, syn['accepted']), (200, 1))
        self.assertEqual(ckeys.verify(syn['license'], {self.c.keys.kid: self.c.keys.public_b64})['usage']['clipes'], 1)
        self.assertEqual(self.call('POST', '/v1/sync', dict(events=[]), {'Authorization': 'Bearer falso'})[0], 401)
        self.assertEqual(self.call('POST', '/v1/activate', dict(email='http1@x.com', password='errada-errada-1', fingerprint='z'))[0], 401)

    def test_error_responses_hide_internals(self):
        st, body, _ = self.call('POST', '/v1/register', dict(email='x'))
        self.assertEqual(st, 400)
        self.assertNotIn('Traceback', json.dumps(body))
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/v1/register', data=b'{ruim', method='POST')
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 400)

    def test_body_limit(self):
        st, body, _ = self.call('POST', '/v1/register', dict(email='a@b.com', name='x' * 300000, password=PW, accept_terms=True))
        self.assertEqual(st, 413)

    def session(self, path, data, cookie_name):
        st, body, h = self.call('POST', path, data)
        self.assertEqual(st, 200, body)
        cookie = [v for k, v in h.items() if k.lower() == 'set-cookie'][0]
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        return cookie.split(';')[0], body['csrf']

    def test_portal_csrf_and_cookie_flow(self):
        self.call('POST', '/v1/portal/register', dict(email='port@x.com', password=PW, name='Port', accept_terms=True))
        ck, csrf = self.session('/v1/portal/login', dict(email='port@x.com', password=PW), 'hk_portal')
        self.assertEqual(self.call('GET', '/v1/portal/me')[0], 401)
        st, me, _ = self.call('GET', '/v1/portal/me', headers={'Cookie': ck})
        self.assertEqual((st, me['conta']['email'], me['assinatura']['state']), (200, 'port@x.com', 'teste'))
        self.assertEqual(self.call('POST', '/v1/portal/profile', dict(name='Novo'), {'Cookie': ck})[0], 403)           # sem CSRF
        self.assertEqual(self.call('POST', '/v1/portal/profile', dict(name='Novo'), {'Cookie': ck, 'X-CSRF': 'errado'})[0], 403)
        st, _, _ = self.call('POST', '/v1/portal/profile', dict(name='Novo Nome', phone='(41) 99999-0000'), {'Cookie': ck, 'X-CSRF': csrf})
        self.assertEqual(st, 200)
        st, ex, _ = self.call('GET', '/v1/portal/export', headers={'Cookie': ck})
        self.assertEqual(ex['conta']['name'], 'Novo Nome')
        st, r, _ = self.call('POST', '/v1/portal/checkout', dict(plan='basico'), {'Cookie': ck, 'X-CSRF': csrf})
        self.assertEqual((st, r['tipo']), (200, 'manual'))
        self.call('POST', '/v1/portal/logout', {}, {'Cookie': ck, 'X-CSRF': csrf})
        self.assertEqual(self.call('GET', '/v1/portal/me', headers={'Cookie': ck})[0], 401)

    def test_admin_requires_login_csrf_and_role(self):
        self.assertEqual(self.call('GET', '/admin/api/metrics')[0], 401)
        ck, csrf = self.session('/admin/api/login', dict(email='dono@x.com', password='Senha-Dono-Forte-1'), 'hk_admin')
        st, m, _ = self.call('GET', '/admin/api/metrics', headers={'Cookie': ck})
        self.assertEqual(st, 200)
        self.assertIn('mrr_cents', m)
        self.assertEqual(self.call('POST', '/admin/api/jobs/run', {}, {'Cookie': ck})[0], 403)
        self.assertEqual(self.call('POST', '/admin/api/jobs/run', {}, {'Cookie': ck, 'X-CSRF': csrf})[0], 200)
        st, v, _ = self.call('GET', '/admin/api/settings', headers={'Cookie': ck})
        self.assertNotIn('chave_privada', json.dumps(v))
        self.assertTrue(v['chave_publica'])
        # sessão do portal não abre o painel
        self.call('POST', '/v1/portal/register', dict(email='port2@x.com', password=PW, name='P2', accept_terms=True))
        pk, pcsrf = self.session('/v1/portal/login', dict(email='port2@x.com', password=PW), 'hk_portal')
        self.assertEqual(self.call('GET', '/admin/api/metrics', headers={'Cookie': pk.replace('hk_portal', 'hk_admin')})[0], 401)

    def test_admin_actions_over_http(self):
        self.call('POST', '/v1/register', dict(email='cli@x.com', password=PW, name='Cli', accept_terms=True))
        ck, csrf = self.session('/admin/api/login', dict(email='dono@x.com', password='Senha-Dono-Forte-1'), 'hk_admin')
        h = {'Cookie': ck, 'X-CSRF': csrf}
        aid = self.call('GET', '/admin/api/customers?q=cli@x.com', headers=h)[1]['items'][0]['id']
        self.assertEqual(self.call('POST', '/admin/api/customer/mark-paid', dict(id=aid, valor=99, plano='basico', metodo='pix'), h)[0], 200)
        det = self.call('GET', f'/admin/api/customer?id={aid}', headers=h)[1]
        self.assertEqual(det['estado'], 'ativa')
        self.assertEqual(self.call('POST', '/admin/api/customer/mark-paid', dict(id=aid, valor=0, plano='basico'), h)[0], 400)
        self.assertEqual(self.call('POST', '/admin/api/customer/delete', dict(id=aid, confirmar='outro@x.com'), h)[0], 400)
        link = self.call('POST', '/admin/api/customer/reset-link', dict(id=aid), h)[1]['link']
        self.assertIn('reset=', link)
        self.assertEqual(self.call('POST', '/admin/api/customer/delete', dict(id=aid, confirmar='cli@x.com'), h)[0], 200)

    def test_webhook_over_http(self):
        body = dict(id='evt-http', event='PAYMENT_RECEIVED', payment=dict(id='p', subscription='s'))
        self.assertEqual(self.call('POST', '/webhooks/asaas', body, {'asaas-access-token': 'errado'})[0], 401)
        self.assertEqual(self.call('POST', '/webhooks/asaas', body, {'asaas-access-token': 'tok-secreto-123'})[0], 200)


if __name__ == '__main__':
    unittest.main()
