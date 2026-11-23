"""Assinatura no aplicativo: login, licença assinada, cotas do plano e fila de uso.

O Hook’s continua rodando no computador do cliente. Este módulo só fala com o servidor de contas (hooks_cloud):
- recebe uma licença assinada (Ed25519) e confere com a chave pública que vem junto do programa;
- guarda o uso (horas analisadas, clipes exportados, lives iniciadas) numa fila local e envia de tempos em tempos;
- decide o que o plano permite: iniciar live, aprovar clipe, analisar.

Regras de produto:
- uma live em andamento nunca é interrompida por licença ou cota;
- cota de horas esgotada pausa só a ANÁLISE; a gravação continua;
- sem internet o programa segue até a licença vencer (72 h por padrão);
- sem `cloud_config.json` ativando `enforce`, o programa roda no modo livre (sem login, sem limites).
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:      # sem a biblioteca não dá para conferir a assinatura: o modo livre continua funcionando
    Ed25519PublicKey = None
    InvalidSignature = Exception

SYNC_EVERY = 15 * 60
CLOCK_SLACK = 10 * 60
MAX_QUEUE = 5000
BATCH = 400
SENT_KEEP = 20000


class LicenseError(ValueError):
    """Mensagem pronta para o cliente (o painel mostra o texto como está)."""


def _b64d(text):
    text = str(text)
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def verify_token(token, public_keys):
    """Confere a assinatura e devolve a carga. ValueError se inválida."""
    if Ed25519PublicKey is None:
        raise ValueError('Biblioteca de assinatura ausente.')
    try:
        version, body, sig = str(token).split('.')
        if version != 'v1':
            raise ValueError('versão')
        payload = json.loads(_b64d(body))
        raw = base64.b64decode(public_keys[payload['kid']])
        Ed25519PublicKey.from_public_bytes(raw).verify(_b64d(sig), body.encode('ascii'))
        return payload
    except (ValueError, KeyError, TypeError, InvalidSignature) as exc:
        raise ValueError('Licença inválida.') from exc


def device_fingerprint(fallback):
    """Identifica o computador sem coletar nada pessoal: id de máquina do sistema, com sal próprio."""
    raw = ''
    try:
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                raw = str(winreg.QueryValueEx(key, 'MachineGuid')[0])
        else:
            for candidate in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
                if Path(candidate).is_file():
                    raw = Path(candidate).read_text().strip()
                    break
    except Exception:
        raw = ''
    return hashlib.sha256(('hooks|' + (raw or fallback)).encode()).hexdigest()


def read_config(package_dir, root):
    """cloud_config.json: o da pasta de dados vale mais que o do pacote."""
    config = dict(server_url='', public_keys={}, enforce=False, terms_url='', privacy_url='', support_url='', portal_url='')
    for folder in (Path(package_dir), Path(root)):
        file = folder / 'cloud_config.json'
        try:
            data = json.loads(file.read_text(encoding='utf-8-sig'))
            if isinstance(data, dict):
                config.update({k: v for k, v in data.items() if k in config})
        except (OSError, ValueError):
            continue
    config['server_url'] = str(config['server_url'] or '').strip().rstrip('/')
    if not isinstance(config['public_keys'], dict):
        config['public_keys'] = {}
    config['enforce'] = bool(config['enforce'])
    return config


def safe_server(url):
    parts = urlsplit(url)
    if not parts.hostname:
        return False
    if parts.scheme == 'https':
        return True
    return parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost')


def default_transport(method, url, headers, body, timeout=12):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict({'Content-Type': 'application/json'}, **headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read(200_000) or b'{}')
        except ValueError:
            return err.code, {}


class Licensing:
    def __init__(self, root, package_dir, version, clock=time.time, transport=None, start_thread=False):
        self.root = Path(root)
        self.version = version
        self.clock = clock
        self.transport = transport or default_transport
        self.config = read_config(package_dir, root)
        self.file = self.root / 'licenca.json'
        self.lock = threading.RLock()
        self.syncing = threading.Lock()
        self.data = self._load()
        self.stop_event = threading.Event()
        self.thread = None
        if start_thread and self.enforced and self.data.get('device_token'):
            self.start()

    # ───── estado salvo ─────
    def _load(self):
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data.setdefault('outbox', [])
                data.setdefault('seq', 0)
                return data
        except (OSError, ValueError):
            pass
        return dict(outbox=[], seq=0, install=secrets.token_hex(6), local_id=secrets.token_hex(16))

    def _save(self):
        self.data.setdefault('install', secrets.token_hex(6))
        self.data.setdefault('local_id', secrets.token_hex(16))
        tmp = self.file.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.file)

    @property
    def enforced(self):
        return bool(self.config['enforce'] and self.config['server_url'] and self.config['public_keys'])

    # ───── leitura da licença ─────
    def payload(self):
        token = self.data.get('license')
        if not token:
            return None
        try:
            return verify_token(token, self.config['public_keys'])
        except ValueError:
            return None

    def status(self):
        """Situação atual, calculada na hora (nada fica congelado no último sincronismo)."""
        now = self.clock()
        if not self.enforced:
            return dict(mode='livre', ok=True, state='livre', message='Modo livre: sem login e sem limites.', needs_login=False)
        if not self.data.get('license'):
            return dict(mode='assinatura', ok=False, state='sem_login', needs_login=True, message='Entre com a sua conta para usar o Hook’s.')
        p = self.payload()
        if not p:
            return dict(mode='assinatura', ok=False, state='invalida', needs_login=True, message='A licença deste computador não é válida. Entre de novo.')
        if now < float(self.data.get('last_seen') or 0) - CLOCK_SLACK:
            return dict(mode='assinatura', ok=False, state='relogio', needs_login=False, payload=p,
                        message='A data do computador está atrasada em relação ao último uso. Corrija o relógio e conecte-se à internet.')
        if now > float(p.get('exp') or 0):
            return dict(mode='assinatura', ok=False, state='offline', needs_login=False, payload=p,
                        message='Faz tempo que o programa não confirma a assinatura. Conecte-se à internet para renovar a licença.')
        return dict(mode='assinatura', ok=bool(p.get('ok')), state=p.get('state'), needs_login=False, payload=p, message=p.get('msg') or '')

    def _pending(self):
        pend = {'analise_s': 0.0, 'clipe': 0, 'live': 0}
        for e in self.data['outbox']:
            if e['kind'] in pend:
                pend[e['kind']] += e['amount']
        return pend

    def usage(self, p=None):
        p = p or self.payload() or {}
        base = p.get('usage') or {}
        pend = self._pending()
        return dict(horas=round(float(base.get('horas') or 0) + pend['analise_s'] / 3600, 3),
                    clipes=int(base.get('clipes') or 0) + int(pend['clipe']), lives=int(base.get('lives') or 0) + int(pend['live']))

    def public(self):
        """O que o painel mostra. Nunca inclui token, senha nem a licença bruta."""
        with self.lock:
            st = self.status()
            p = st.get('payload') or {}
            out = dict(mode=st['mode'], ok=st['ok'], state=st['state'], message=st['message'], needs_login=st['needs_login'],
                       enforced=self.enforced, server_configured=bool(self.config['server_url']),
                       terms_url=self.config['terms_url'] or (self.config['server_url'] + '/termos' if self.config['server_url'] else ''),
                       privacy_url=self.config['privacy_url'] or (self.config['server_url'] + '/privacidade' if self.config['server_url'] else ''),
                       portal_url=self.config['portal_url'] or (self.config['server_url'] + '/conta' if self.config['server_url'] else ''),
                       support_url=self.config['support_url'], pending_events=len(self.data['outbox']),
                       last_sync=self.data.get('last_sync'), last_error=self.data.get('last_error', ''))
            if p:
                use = self.usage(p)
                lim = p.get('limits') or {}
                out.update(email=p.get('email'), name=p.get('nome'), plan=p.get('plan'), plan_name=p.get('plano'), limits=lim, usage=use,
                           period=p.get('periodo'), cancel_at_period_end=bool(p.get('cancela')), valid_until=p.get('exp'),
                           hours_ratio=round(use['horas'] / lim['horas'], 3) if lim.get('horas') else 0,
                           clips_ratio=round(use['clipes'] / lim['clipes'], 3) if lim.get('clipes') else 0)
            return out

    # ───── portas: o que o plano permite ─────
    def check_active(self):
        if not self.enforced:
            return
        st = self.status()
        if not st['ok']:
            raise LicenseError(self._block_text(st))

    @staticmethod
    def _block_text(st):
        state = st['state']
        if state in ('sem_login', 'invalida'):
            return 'Entre com a sua conta em Assinatura para continuar.'
        if state == 'expirada':
            return 'Sua assinatura venceu. Renove em Minha conta para voltar a usar.'
        if state == 'suspensa':
            return 'Sua assinatura está suspensa. ' + (st.get('message') or '')
        return st.get('message') or 'A assinatura não está ativa.'

    def max_lives(self):
        if not self.enforced:
            return 5
        p = (self.status().get('payload') or {})
        return max(1, int((p.get('limits') or {}).get('lives') or 1))

    def check_start_live(self, active_now):
        if not self.enforced:
            return
        self.check_active()
        limit = self.max_lives()
        if active_now >= limit:
            plan = (self.payload() or {}).get('plano', 'atual')
            raise LicenseError(f'O plano {plan} permite {limit} live(s) ao mesmo tempo. Encerre uma captura ou mude de plano em Minha conta.')

    def check_export(self, pending=0):
        """Aprovar um clipe: precisa de assinatura ativa e de cota (conta também os já aprovados que ainda não exportaram)."""
        if not self.enforced:
            return
        self.check_active()
        with self.lock:
            p = self.payload() or {}
            limit = int((p.get('limits') or {}).get('clipes') or 0)
            used = self.usage(p)['clipes']
        if used + max(0, int(pending)) >= limit:
            raise LicenseError(f'Você usou {used} de {limit} clipes deste período'
                               + (f' (mais {pending} aprovado(s) na fila)' if pending else '') + '. Faça upgrade em Minha conta ou espere a renovação.')

    def allow_analysis(self):
        """False pausa só a análise; a gravação das lives continua."""
        if not self.enforced:
            return True
        with self.lock:
            st = self.status()
            if not st['ok']:
                return False
            p = st.get('payload') or {}
            limit = float((p.get('limits') or {}).get('horas') or 0)
            return self.usage(p)['horas'] < limit

    def analysis_block_reason(self):
        if not self.enforced:
            return ''
        st = self.status()
        if not st['ok']:
            return self._block_text(st)
        if not self.allow_analysis():
            return 'A cota de horas de live deste período acabou. A gravação continua; a análise volta quando o plano renovar ou subir.'
        return ''

    # ───── uso ─────
    def record(self, kind, amount, event_id):
        """Entra na fila local (rápido, sem rede). Idempotente por id."""
        if not self.enforced or not self.data.get('device_token'):
            return False
        amount = float(amount)
        if amount <= 0:
            return False
        eid = f"{self.data.get('install', 'x')}:{event_id}"
        with self.lock:
            if eid in self.data.get('sent', ()) or any(e['id'] == eid for e in self.data['outbox']):
                return False            # já na fila ou já enviado: refazer a análise de um trecho não cobra de novo
            self.data['seq'] += 1
            self.data['outbox'].append(dict(id=eid, kind=kind, amount=amount, at=self.clock(), seq=self.data['seq']))
            if len(self.data['outbox']) > MAX_QUEUE:
                self.data['outbox'] = self.data['outbox'][-MAX_QUEUE:]
            self.data['last_seen'] = max(float(self.data.get('last_seen') or 0), self.clock())
            self._save()
        return True

    # ───── rede ─────
    def _call(self, method, path, body=None, token=''):
        if not safe_server(self.config['server_url']):
            raise LicenseError('O endereço do servidor de contas precisa começar com https://.')
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        try:
            status, data = self.transport(method, self.config['server_url'] + path, headers, body)
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            raise ConnectionError('Sem conexão com o servidor de contas. Confira a internet e tente de novo.') from exc
        return status, data

    def _fingerprint(self):
        return device_fingerprint(self.data.get('local_id') or secrets.token_hex(16))

    def _accept(self, token):
        """Só aceita licença com assinatura válida. Atualiza o relógio visto."""
        p = verify_token(token, self.config['public_keys'])
        self.data['license'] = token
        self.data['last_seen'] = max(float(self.data.get('last_seen') or 0), self.clock(), float(p.get('iat') or 0))
        self.data['last_sync'] = self.clock()
        self.data['last_error'] = ''
        return p

    def register(self, name, email, password, accept_terms):
        if not self.enforced:
            raise LicenseError('Este programa está em modo livre: não precisa de conta.')
        status, data = self._call('POST', '/v1/register', dict(name=name, email=email, password=password, accept_terms=bool(accept_terms)))
        if status not in (200, 201):
            raise LicenseError(data.get('error') or 'Não foi possível criar a conta.')
        return self.login(email, password)

    def login(self, email, password):
        if not self.enforced:
            raise LicenseError('Este programa está em modo livre: não precisa de conta.')
        status, data = self._call('POST', '/v1/activate', dict(email=email, password=password, fingerprint=self._fingerprint(),
                                                                device_name=os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME') or 'Computador',
                                                                os=os.name, app_version=self.version))
        if status != 200:
            raise LicenseError(data.get('error') or 'Não foi possível entrar.')
        with self.lock:
            try:
                self._accept(data['license'])
            except (ValueError, KeyError) as exc:
                raise LicenseError('O servidor devolveu uma licença que não confere com este programa. Verifique a chave pública em cloud_config.json.') from exc
            self.data['device_token'] = data['device_token']
            self.data['email'] = data.get('email', email)
            self._save()
        self.start()
        return self.public()

    def forgot(self, email):
        if not self.enforced:
            return
        self._call('POST', '/v1/password/forgot', dict(email=email))

    def logout(self):
        token = self.data.get('device_token')
        if token and self.enforced:
            try:
                self._call('POST', '/v1/deactivate', {}, token)
            except (ConnectionError, LicenseError):
                pass
        with self.lock:
            for key in ('device_token', 'license', 'email', 'last_sync', 'last_error'):
                self.data.pop(key, None)
            self.data['outbox'] = []
            self.data['sent'] = []
            self._save()

    def sync(self, lives=0):
        """Envia o uso pendente e troca a licença por uma nova. Devolve (ok, mensagem)."""
        if not self.enforced or not self.data.get('device_token'):
            return False, 'Sem login.'
        if not self.syncing.acquire(blocking=False):
            return False, 'Sincronização em andamento.'
        try:
            with self.lock:
                batch = list(self.data['outbox'][:BATCH])
                token = self.data['device_token']
            try:
                status, data = self._call('POST', '/v1/sync', dict(events=[dict(kind=e['kind'], amount=e['amount'], id=e['id'], at=e['at']) for e in batch],
                                                                   info=dict(lives=int(lives), version=self.version)), token)
            except ConnectionError as exc:
                with self.lock:
                    self.data['last_error'] = str(exc)
                    self._save()
                return False, str(exc)
            with self.lock:
                if status in (401, 403):
                    # computador removido da conta ou senha trocada: precisa entrar de novo
                    for key in ('device_token', 'license'):
                        self.data.pop(key, None)
                    self.data['last_error'] = data.get('error') or 'Este computador foi removido da conta. Entre de novo.'
                    self._save()
                    return False, self.data['last_error']
                if status != 200:
                    self.data['last_error'] = data.get('error') or f'O servidor respondeu {status}.'
                    self._save()
                    return False, self.data['last_error']
                sent = {e['id'] for e in batch}
                try:
                    self._accept(data['license'])
                except (ValueError, KeyError):
                    self.data['last_error'] = 'Licença recebida não confere com a chave pública.'
                    self._save()
                    return False, self.data['last_error']
                self.data['outbox'] = [e for e in self.data['outbox'] if e['id'] not in sent]
                self.data['sent'] = (list(self.data.get('sent', [])) + sorted(sent))[-SENT_KEEP:]
                self._save()
            return True, 'ok'
        finally:
            self.syncing.release()

    # ───── segundo plano ─────
    def start(self, lives_provider=None):
        self.lives_provider = lives_provider or getattr(self, 'lives_provider', lambda: 0)
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='licenca')
        self.thread.start()

    def _loop(self):
        wait = 3
        while not self.stop_event.wait(wait):
            if self.enforced and self.data.get('device_token'):
                try:
                    ok, _ = self.sync(self.lives_provider())
                except Exception:
                    ok = False
                wait = SYNC_EVERY if ok else 120
            else:
                wait = 60

    def close(self):
        self.stop_event.set()
        if self.enforced and self.data.get('device_token'):
            try:
                self.sync(0)
            except Exception:
                pass
