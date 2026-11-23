"""Servidor HTTP: API do aplicativo, portal do cliente, painel do super admin e webhook. Biblioteca padrão apenas.

Atrás de um proxy com HTTPS (Caddy/Nginx) em produção. As senhas e tokens nunca aparecem nos logs.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import sqlite3
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse,parse_qs

from . import __version__
from .admin import Admin
from .billing import Billing,asaas_from_env
from .db import DB
from .keys import Keyring
from .mail import Mailer
from .security import RateLimiter,same
from .service import Bad,Service,to_cents,to_int

STATIC=Path(__file__).parent/'static'
MAX_BODY=262144


class Cloud:
    """Monta tudo a partir de uma pasta de dados."""
    def __init__(self,root,env=None,clock=time.time,hash_params=None,asaas_transport=None,mail_factory=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        env=os.environ if env is None else env
        self.db=DB(self.root/'hooks_cloud.sqlite3')
        self.keys=Keyring(self.root/'chave_privada.pem')
        self.mail=Mailer(env,mail_factory)
        self.service=Service(self.db,self.keys,clock,hash_params,self.mail)
        self.admin=Admin(self.service)
        self.billing=Billing(self.service,asaas_from_env(env,asaas_transport),env.get('HOOKS_ASAAS_WEBHOOK_TOKEN',''))
        self.limiter=RateLimiter(clock)
        self.stop=threading.Event()

    def auto_backup(self,keep=14,min_hours=20,now=None):
        """Backup diário do banco em backups/auto_*.sqlite3, mantendo os últimos `keep`. Não inclui a chave privada: guarde-a à parte."""
        folder=self.root/'backups';folder.mkdir(parents=True,exist_ok=True)
        now=time.time() if now is None else now
        old=sorted(folder.glob('auto_*.sqlite3'),key=lambda f:f.name)
        if old and now-old[-1].stat().st_mtime<min_hours*3600:return None
        target=folder/time.strftime('auto_%Y%m%d_%H%M%S.sqlite3',time.localtime(now))
        self.db.backup(target)
        try:os.chmod(target,0o600)
        except OSError:pass
        for f in sorted(folder.glob('auto_*.sqlite3'),key=lambda f:f.name)[:-keep]:
            try:f.unlink()
            except OSError:pass
        self.service.audit('sistema','backup_automatico',target.name)
        return target.name

    def start_jobs(self,every=900):
        def loop():
            while True:
                try:self.service.run_jobs()
                except Exception as exc:print('Falha nas tarefas periódicas:',exc,flush=True)
                try:self.auto_backup()
                except Exception as exc:print('Falha no backup automático:',exc,flush=True)
                if self.stop.wait(every):break
        t=threading.Thread(target=loop,daemon=True,name='tarefas');t.start();return t


class Request:
    def __init__(self,handler,cloud):
        self.h=handler;self.cloud=cloud;url=urlparse(handler.path);self.path=url.path.rstrip('/') or '/'
        self.query={k:v[0] for k,v in parse_qs(url.query).items()}
        self.headers=handler.headers
        self.cookies={}
        for part in (handler.headers.get('Cookie') or '').split(';'):
            if '=' in part:k,v=part.strip().split('=',1);self.cookies[k]=v
        peer=handler.client_address[0]
        forwarded=(handler.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        self.ip=forwarded if forwarded and cloud.service.setting('trust_proxy') else peer
        self._json=None

    def body(self):
        try:length=int(self.headers.get('Content-Length') or 0)
        except ValueError:raise Bad('Pedido inválido.','pedido')
        if length<0 or length>MAX_BODY:raise Bad('Pedido grande demais.','tamanho',413)
        return self.h.rfile.read(length) if length else b''

    def json(self):
        if self._json is None:
            raw=self.body()
            try:self._json=json.loads(raw) if raw else {}
            except ValueError:raise Bad('JSON inválido.','json')
            if not isinstance(self._json,dict):raise Bad('JSON inválido.','json')
        return self._json

    def bearer(self):
        value=self.headers.get('Authorization') or ''
        return value[7:].strip() if value.lower().startswith('bearer ') else ''


def page(name):
    return (STATIC/name).read_bytes()


def legal(cloud,name):
    """Termos e política: um arquivo .md na pasta de dados (textos/) tem prioridade sobre o rascunho que acompanha o programa."""
    import html
    custom=cloud.root/'textos'/(name+'.md');source=custom if custom.is_file() else STATIC/(name+'.md')
    lines=source.read_text(encoding='utf-8').splitlines();out=[];listing=False
    for line in lines:
        text=html.escape(line.strip())
        if listing and not line.lstrip().startswith(('- ','* ')):out.append('</ul>');listing=False
        if line.startswith('# '):out.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line.startswith('## '):out.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line.lstrip().startswith(('- ','* ')):
            if not listing:out.append('<ul>');listing=True
            out.append('<li>'+html.escape(line.lstrip()[2:])+'</li>')
        elif text:out.append('<p>'+text+'</p>')
    if listing:out.append('</ul>')
    body='\n'.join(out)
    return ('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(name.capitalize())+'</title>'
            '<style>body{font:16px/1.65 system-ui,Segoe UI,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1a1a22}h1{font-size:28px}h2{margin-top:28px}</style>'+body).encode()


def make_handler(cloud):
    svc=cloud.service;adm=cloud.admin;bill=cloud.billing

    def https():return svc.setting('public_url').startswith('https://')

    class Handler(BaseHTTPRequestHandler):
        server_version='HooksCloud';sys_version=''
        def log_message(self,*args):pass

        def send(self,status,body,ctype='application/json; charset=utf-8',cookies=(),extra=None):
            data=json.dumps(body,ensure_ascii=False,default=str).encode() if isinstance(body,(dict,list)) else body
            self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Frame-Options','DENY')
            if ctype.startswith('text/html'):
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if https():self.send_header('Strict-Transport-Security','max-age=31536000')
            for c in cookies:self.send_header('Set-Cookie',c)
            for k,v in (extra or {}).items():self.send_header(k,v)
            self.end_headers();self.wfile.write(data)

        def cookie(self,name,value,hours=12,path='/'):
            flags=f'; HttpOnly; SameSite=Strict; Path={path}'+('; Secure' if https() else '')
            return f'{name}={value}; Max-Age={int(hours*3600) if value else 0}'+flags

        def dispatch(self,method):
            req=Request(self,cloud)
            try:
                if not cloud.limiter.allow('ip:'+req.ip,300,60):raise Bad('Muitas requisições. Aguarde um instante.','limite',429)
                result=self.route(method,req)
                if result is None:raise Bad('Não encontrado.','nao_encontrado',404)
                self.send(*result) if isinstance(result,tuple) else self.send(200,result)
            except Bad as exc:
                self.send(exc.status,dict(error=str(exc),code=exc.code))
            except (BrokenPipeError,ConnectionResetError):pass
            except (TypeError,ValueError,OverflowError,sqlite3.InterfaceError,sqlite3.ProgrammingError) as exc:
                svc.audit('sistema','entrada_invalida',req.path,dict(erro=str(exc)[:200]))
                self.send(400,dict(error='Dados inválidos. Confira os campos e tente de novo.',code='invalido'))
            except Exception as exc:
                svc.audit('sistema','erro_interno',req.path,dict(erro=str(exc)[:200]))
                self.send(500,dict(error='Erro interno. Tente de novo em instantes.',code='interno'))

        def do_GET(self):self.dispatch('GET')
        def do_POST(self):self.dispatch('POST')

        # ───── roteamento ─────
        def route(self,method,r):
            p=r.path
            if method=='GET':
                if p=='/healthz':return dict(ok=True,versao=__version__)
                if p=='/':return 302,b'','text/plain',(),{'Location':'/conta'}
                if p=='/favicon.ico':return 200,page('favicon.ico'),'image/x-icon',(),{'Cache-Control':'public, max-age=86400'}
                if p=='/conta':return 200,page('portal.html'),'text/html; charset=utf-8'
                if p=='/admin':return 200,page('admin.html'),'text/html; charset=utf-8'
                if p=='/v1/plans':return self.public_plans()
                if p in ('/termos','/privacidade'):return 200,legal(cloud,p[1:]),'text/html; charset=utf-8'
            if p=='/webhooks/asaas' and method=='POST':
                status,body=bill.webhook(r.headers,r.body());return status,body
            if p.startswith('/v1/portal'):return self.portal(method,r)
            if p.startswith('/admin/api'):return self.admin(method,r)
            if p.startswith('/v1/') and method=='POST':return self.app_api(r)
            return None

        def public_plans(self):
            return dict(planos=[dict(code=x['code'],name=x['name'],price_cents=x['price_cents'],max_lives=x['max_lives'],hours_month=x['hours_month'],clips_month=x['clips_month'],
                                     max_streamers=x['max_streamers'],max_devices=x['max_devices'],description=x['description'])
                                for x in adm.plans() if x['active'] and x['public'] and not x['trial']])

        # ───── API do aplicativo ─────
        def app_api(self,r):
            p=r.path;d=r.json()
            if p=='/v1/register':
                acc=svc.register(d.get('email'),d.get('password'),d.get('name'),d.get('accept_terms'),r.ip,'app')
                return 201,dict(ok=True,email=acc['email'])
            if p=='/v1/activate':
                return svc.activate(d.get('email'),d.get('password'),d.get('fingerprint'),d.get('device_name',''),d.get('os',''),d.get('app_version',''),r.ip)
            if p in ('/v1/sync','/v1/license/refresh'):
                if not cloud.limiter.allow('sync:'+r.bearer()[:12],120,60):raise Bad('Muitas sincronizações.','limite',429)
                return svc.sync(r.bearer(),d.get('events'),d.get('info'),r.ip)
            if p=='/v1/deactivate':svc.deactivate(r.bearer());return dict(ok=True)
            if p=='/v1/password/forgot':svc.request_reset(d.get('email'),r.ip);return dict(ok=True,mensagem='Se o e-mail existir, enviamos o link para criar uma nova senha.')
            return None

        # ───── portal do cliente ─────
        def portal_ctx(self,r,write):
            s=svc.portal_session(r.cookies.get('hk_portal'))
            if not s:raise Bad('Entre na sua conta.','nao_autorizado',401)
            if write and not same(r.headers.get('X-CSRF') or '',s['csrf']):raise Bad('Sessão inválida. Recarregue a página.','csrf',403)
            return s

        def portal(self,method,r):
            p=r.path;sub=p[len('/v1/portal'):]
            if method=='POST' and sub=='/login':
                if not cloud.limiter.allow('plogin:'+r.ip,20,300):raise Bad('Muitas tentativas.','limite',429)
                d=r.json();token,csrf,acc=svc.portal_login(d.get('email'),d.get('password'),r.ip)
                return 200,dict(ok=True,csrf=csrf),'application/json; charset=utf-8',[self.cookie('hk_portal',token,int(svc.setting('session_hours')),'/')]
            if method=='POST' and sub=='/reset':
                d=r.json();svc.confirm_reset(d.get('token'),d.get('password'),r.ip);return dict(ok=True)
            if method=='POST' and sub=='/forgot':
                svc.request_reset(r.json().get('email'),r.ip);return dict(ok=True,mensagem='Se o e-mail existir, enviamos o link para criar uma nova senha.')
            if method=='POST' and sub=='/register':
                d=r.json();svc.register(d.get('email'),d.get('password'),d.get('name'),d.get('accept_terms'),r.ip,'portal');return 201,dict(ok=True)
            s=self.portal_ctx(r,method=='POST');aid=s['account_id']
            if method=='GET' and sub=='/me':return dict(self.portal_me(aid),csrf=s['csrf'])
            if method=='GET' and sub=='/export':
                body=json.dumps(svc.export_account(aid),ensure_ascii=False,default=str,indent=2).encode()
                svc.audit('cliente:'+aid,'lgpd_exportacao',aid,{},r.ip)
                return 200,body,'application/json; charset=utf-8',(),{'Content-Disposition':'attachment; filename="meus-dados-hooks.json"'}
            if method!='POST':return None
            d=r.json()
            if sub=='/logout':svc.portal_logout(r.cookies.get('hk_portal'));return 200,dict(ok=True),'application/json; charset=utf-8',[self.cookie('hk_portal','',0,'/')]
            if sub=='/profile':bill.save_profile(aid,d.get('doc'),d.get('phone'),d.get('name'));return dict(ok=True)
            if sub=='/password':svc.change_password(aid,d.get('old'),d.get('new'),r.ip);return dict(ok=True)
            if sub=='/checkout':return bill.checkout(aid,d.get('plan'),d.get('billing_type','UNDEFINED'))
            if sub=='/device/revoke':svc.revoke_device(aid,d.get('id'));return dict(ok=True)
            if sub=='/cancel':
                bill.cancel_remote(aid);svc.cancel(aid,'cliente:'+aid);return dict(ok=True)
            if sub=='/privacy':return dict(ok=True,id=svc.privacy_request(aid,d.get('kind'),d.get('note','')))
            return None

        def portal_me(self,aid):
            acc=svc.account(aid);ent=svc.entitlement(aid)
            pending=svc.db.rows("SELECT id,plan_code,amount_cents,due_at FROM payments WHERE account_id=? AND status='pendente' AND provider='manual' ORDER BY created DESC",(aid,))
            for x in pending:x['instrucoes']=svc.how_to_pay(x)
            return dict(conta=dict(email=acc['email'],nome=acc['name'],doc=acc['doc'],telefone=acc['phone'],criada=acc['created'],termos=acc['terms_version'],termos_em=acc['terms_at']),assinatura=ent,
                        dispositivos=svc.devices(aid),pagamentos=svc.payments(aid)[:30],pendentes=pending,planos=self.public_plans()['planos'],
                        pedidos=svc.db.rows('SELECT id,kind,status,created,due_at FROM privacy_requests WHERE account_id=? ORDER BY created DESC',(aid,)),
                        provedor=svc.setting('billing_provider'),suporte=svc.setting('support_email'),download=svc.setting('download_url'))

        # ───── super admin ─────
        def admin_ctx(self,r,write):
            s=adm.session(r.cookies.get('hk_admin'))
            if not s:raise Bad('Entre como administrador.','nao_autorizado',401)
            if write and not same(r.headers.get('X-CSRF') or '',s['csrf']):raise Bad('Sessão inválida. Recarregue a página.','csrf',403)
            return s['admin']

        def admin(self,method,r):
            sub=r.path[len('/admin/api'):]
            if method=='POST' and sub=='/login':
                if not cloud.limiter.allow('alogin:'+r.ip,15,300):raise Bad('Muitas tentativas.','limite',429)
                d=r.json();token,csrf,a=adm.login(d.get('email'),d.get('password'),d.get('code',''),r.ip)
                return 200,dict(ok=True,csrf=csrf,admin=dict(email=a['email'],name=a['name'],role=a['role'],totp=bool(a['totp_on']))),'application/json; charset=utf-8',[self.cookie('hk_admin',token,int(svc.setting('admin_session_hours')),'/admin')]
            a=self.admin_ctx(r,method=='POST');who='admin:'+a['email'];q=r.query
            if method=='GET':
                if sub=='/me':
                    s=adm.session(r.cookies.get('hk_admin'))
                    return dict(email=a['email'],name=a['name'],role=a['role'],totp=bool(a['totp_on']),versao=__version__,csrf=s['csrf'])
                adm.require(a,'ver')
                if sub=='/metrics':return adm.metrics()
                if sub=='/customers':return adm.customers(q.get('q',''),q.get('state',''),q.get('plan',''),q.get('page',1),q.get('size',25))
                if sub=='/customer':return adm.customer(q.get('id',''))
                if sub=='/plans':return dict(planos=adm.plans())
                if sub=='/settings':
                    adm.require(a,'*');return dict(config=svc.settings(),smtp=cloud.mail.configured,asaas=bool(cloud.billing.client),webhook=bool(cloud.billing.webhook_token),chave_publica=cloud.keys.public_b64,kid=cloud.keys.kid)
                if sub=='/payments':adm.require(a,'pagamento');return dict(pagamentos=adm.payments(q.get('status','')))
                if sub=='/audit':return dict(eventos=adm.audit_list(q.get('target',''),q.get('action','')))
                if sub=='/webhooks':adm.require(a,'*');return dict(eventos=adm.webhooks())
                if sub=='/outbox':return dict(emails=adm.outbox(q.get('status','')))
                if sub=='/privacy':adm.require(a,'lgpd');return dict(pedidos=adm.privacy(q.get('status','')))
                if sub=='/admins':adm.require(a,'*');return dict(admins=adm.admins())
                return None
            if method!='POST':return None
            d=r.json();aid=d.get('id') or d.get('account')
            if aid is not None and not isinstance(aid,str):raise Bad('Identificador inválido.','id')
            if sub=='/logout':adm.logout(r.cookies.get('hk_admin'));return 200,dict(ok=True),'application/json; charset=utf-8',[self.cookie('hk_admin','',0,'/admin')]
            if sub=='/password':adm.change_password(a,d.get('old'),d.get('new'));return dict(ok=True)
            if sub=='/totp/begin':return adm.begin_totp(a)
            if sub=='/totp/confirm':adm.confirm_totp(a,d.get('code'));return dict(ok=True)
            if sub=='/customer/mark-paid':
                adm.require(a,'pagamento');cents=to_cents(d.get('valor'))
                if cents<=0:raise Bad('Informe o valor recebido.','valor')
                return svc.apply_payment(aid,cents,d.get('metodo','pix'),str(d.get('ref',''))[:80],'manual',None,d.get('plano') or None,who,note=str(d.get('nota',''))[:200])
            if sub=='/customer/confirm-charge':adm.require(a,'pagamento');return svc.confirm_manual_payment(d.get('payment'),who,d.get('metodo','pix'),str(d.get('ref',''))[:80])
            if sub=='/customer/suspend':adm.require(a,'cancelar');svc.suspend(aid,d.get('motivo',''),who);return dict(ok=True)
            if sub=='/customer/reactivate':adm.require(a,'cancelar');svc.reactivate(aid,who);return dict(ok=True)
            if sub=='/customer/extend-trial':adm.require(a,'estender_teste');svc.extend_trial(aid,d.get('dias'),who);return dict(ok=True)
            if sub=='/customer/courtesy':adm.require(a,'cortesia');svc.courtesy(aid,d.get('dias'),d.get('plano'),d.get('motivo'),who);return dict(ok=True)
            if sub=='/customer/change-plan':adm.require(a,'plano_cliente');svc.change_plan(aid,d.get('plano'),who);return dict(ok=True)
            if sub=='/customer/cancel':adm.require(a,'cancelar');bill.cancel_remote(aid);svc.cancel(aid,who,bool(d.get('imediato')));return dict(ok=True)
            if sub=='/customer/adjust':adm.require(a,'ajuste');svc.adjust(aid,d.get('tipo'),d.get('quantidade'),d.get('motivo'),who);return dict(ok=True)
            if sub=='/customer/grace':adm.require(a,'cortesia');svc.set_grace(aid,d.get('dias'),who);return dict(ok=True)
            if sub=='/customer/note':adm.require(a,'nota');svc.add_note(aid,d.get('texto'),who);return dict(ok=True)
            if sub=='/customer/reset-link':adm.require(a,'senha');return dict(link=svc._reset_link(svc.account(aid),who))
            if sub=='/customer/device-revoke':adm.require(a,'dispositivo');svc.revoke_device(aid,d.get('device'),who);return dict(ok=True)
            if sub=='/customer/delete':
                adm.require(a,'*')
                if d.get('confirmar')!=svc.account(aid)['email']:raise Bad('Digite o e-mail da conta para confirmar a exclusão.','confirmacao')
                svc.delete_account(aid,who);return dict(ok=True)
            if sub=='/customer/export':adm.require(a,'exportar');return svc.export_account(aid)
            if sub=='/plan/save':adm.save_plan(a,d);return dict(planos=adm.plans())
            if sub=='/settings/save':return dict(config=adm.save_settings(a,d))
            if sub=='/webhook/reprocess':adm.require(a,'*');return dict(status=bill.reprocess(to_int(d.get('id'),'id'),a))
            if sub=='/outbox/mark-sent':adm.require(a,'ver');adm.mark_sent(a,d.get('id'));return dict(ok=True)
            if sub=='/outbox/flush':adm.require(a,'*');return cloud.mail.flush(svc.db,now=svc.clock)
            if sub=='/privacy/finish':adm.require(a,'lgpd');adm.finish_privacy(a,d.get('id'),d.get('nota',''),bool(d.get('recusar')));return dict(ok=True)
            if sub=='/admins/create':adm.require(a,'*');return dict(id=adm.create_admin(d.get('email'),d.get('name'),d.get('password'),d.get('role'),a['email']))
            if sub=='/admins/set':adm.set_admin(a,d.get('id'),d.get('active'),d.get('role'),d.get('password'));return dict(ok=True)
            if sub=='/jobs/run':adm.require(a,'*');return svc.run_jobs()
            if sub=='/backup':
                adm.require(a,'*');folder=cloud.root/'backups';folder.mkdir(exist_ok=True)
                target=folder/time.strftime('hooks_cloud_%Y%m%d_%H%M%S.sqlite3');cloud.db.backup(target);svc.audit(who,'backup',str(target.name));return dict(arquivo=target.name)
            return None
    return Handler


def serve(cloud,host='127.0.0.1',port=8800):
    class S(ThreadingHTTPServer):
        daemon_threads=True
    return S((host,port),make_handler(cloud))
