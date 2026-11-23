"""Regras do negócio: contas, assinaturas, licenças assinadas, uso e cotas, cobrança, auditoria e LGPD.

Tudo recebe o relógio (`clock`) para ser testável. O estado de uma assinatura é DERIVADO dos dados e da hora
(ver `effective`): não depende de uma tarefa agendada ter rodado para que um atraso bloqueie o acesso.
"""
import calendar
import datetime as dt
import json
import re
import secrets
import time

from . import mail as mailer
from . import security as sec

DAY=86400.0

DEFAULTS=dict(trial_days=7,grace_days=5,signup_open=True,token_ttl_hours=72,terms_version='2026-11',privacy_version='2026-11',
              support_email='',pix_key='',pix_name='',public_url='http://127.0.0.1:8800',download_url='',billing_provider='manual',
              reset_minutes=60,session_hours=12,admin_session_hours=8,trust_proxy=False,renewal_reminder_days=3,
              trial_reminder_days=2,brand='Hook’s')

SETTING_KEYS=tuple(DEFAULTS)

# Planos de partida. Os números são ILUSTRATIVOS e ficam em rascunho (inativos, preço 0) até você definir o preço no painel.
SEED_PLANS=[
    dict(code='teste',name='Teste grátis',price_cents=0,max_lives=1,hours_month=3,clips_month=10,max_streamers=1,max_devices=1,trial=1,active=1,public=0,sort=0,
         description='Período de avaliação'),
    dict(code='basico',name='Básico',price_cents=0,max_lives=1,hours_month=40,clips_month=60,max_streamers=1,max_devices=1,trial=0,active=0,public=1,sort=1,
         description='Rascunho: defina o preço e ative.'),
    dict(code='pro',name='Pro',price_cents=0,max_lives=2,hours_month=120,clips_month=200,max_streamers=3,max_devices=2,trial=0,active=0,public=1,sort=2,
         description='Rascunho: defina o preço e ative.'),
    dict(code='agencia',name='Agência',price_cents=0,max_lives=4,hours_month=400,clips_month=800,max_streamers=10,max_devices=3,trial=0,active=0,public=1,sort=3,
         description='Rascunho: defina o preço e ative.'),
]

USAGE_KINDS=dict(analise_s=7200.0,clipe=1.0,live=1.0)   # tipo -> máximo por evento
OK_STATES=('teste','ativa','atraso','cancelada')

STATE_TEXT=dict(
    teste='Período de teste.',ativa='Assinatura ativa.',atraso='Pagamento em atraso: regularize para não perder o acesso.',
    cancelada='Assinatura cancelada; vale até o fim do período pago.',suspensa='Assinatura suspensa.',
    expirada='Assinatura vencida ou teste encerrado. Seus clipes continuam acessíveis; novas lives e exportações estão bloqueadas.')

EMAIL=re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,}$')


class Bad(Exception):
    def __init__(self,message,code='invalido',status=400):
        super().__init__(message);self.code=code;self.status=status


def uid():return secrets.token_hex(8)


def to_int(value,field,lo=None,hi=None):
    """Número inteiro vindo de fora (JSON ou URL). Qualquer coisa que não seja número vira mensagem clara, nunca erro 500."""
    if isinstance(value,bool):raise Bad(f'Valor inválido em {field}.',field)
    try:
        number=int(value) if not isinstance(value,float) else int(value) if value==value and abs(value)<1e15 else None
    except (TypeError,ValueError,OverflowError):number=None
    if number is None or abs(number)>2**62:raise Bad(f'Valor inválido em {field}.',field)
    if (lo is not None and number<lo) or (hi is not None and number>hi):raise Bad(f'{field} fora do intervalo permitido.',field)
    return number


def to_cents(value,field='valor'):
    """Valor em reais (número ou texto com vírgula) → centavos inteiros positivos."""
    if isinstance(value,bool) or value is None:raise Bad('Informe o valor recebido.',field)
    try:
        reais=float(str(value).replace(',','.')) if not isinstance(value,(int,float)) else float(value)
        if reais!=reais or abs(reais)>1e9:raise ValueError
        return int(round(reais*100))
    except (TypeError,ValueError,OverflowError) as exc:raise Bad(f'Valor inválido em {field}.',field) from exc


def add_months(ts,months):
    d=dt.datetime.fromtimestamp(ts,dt.timezone.utc)
    month=d.month-1+months;year=d.year+month//12;month=month%12+1
    day=min(d.day,calendar.monthrange(year,month)[1])
    return d.replace(year=year,month=month,day=day).timestamp()


def fmt_date(ts):
    return dt.datetime.fromtimestamp(ts,dt.timezone(dt.timedelta(hours=-3))).strftime('%d/%m/%Y') if ts else ''


def money(cents):
    value=f'{(cents or 0)/100:,.2f}'
    return 'R$ '+value.replace(',','X').replace('.',',').replace('X','.')


PERMS=dict(
    dono={'*'},
    financeiro={'ver','pagamento','ajuste','cortesia','plano_cliente','cancelar','exportar'},
    suporte={'ver','dispositivo','nota','senha','estender_teste','lgpd'},
)


class Service:
    def __init__(self,db,keyring,clock=time.time,hash_params=None,mail=None,asaas=None):
        self.db=db;self.keys=keyring;self.clock=clock;self.params=hash_params;self.mail=mail;self.asaas=asaas
        if not self.db.one("SELECT value FROM meta WHERE key='ip_salt'"):
            with self.db.connect(True) as c:c.execute("INSERT OR IGNORE INTO meta VALUES('ip_salt',?)",(secrets.token_hex(16),))
        self.salt=self.db.one("SELECT value FROM meta WHERE key='ip_salt'")['value']
        if not self.db.rows('SELECT code FROM plans LIMIT 1'):self.seed()

    # ───── base ─────
    def now(self):return self.clock()

    def seed(self):
        with self.db.connect(True) as c:
            for p in SEED_PLANS:
                c.execute('INSERT OR IGNORE INTO plans(code,name,price_cents,max_lives,hours_month,clips_month,max_streamers,max_devices,trial,active,public,sort,description,created)'
                          ' VALUES(:code,:name,:price_cents,:max_lives,:hours_month,:clips_month,:max_streamers,:max_devices,:trial,:active,:public,:sort,:description,:t)',dict(p,t=self.now()))

    def setting(self,key):return self.db.setting(key,DEFAULTS.get(key))

    def settings(self):return {k:self.setting(k) for k in SETTING_KEYS}

    def iphash(self,ip):return sec.digest(self.salt+str(ip or ''))[:16]

    def audit(self,actor,action,target='',detail=None,ip=''):
        with self.db.connect(True) as c:
            c.execute('INSERT INTO audit(at,actor,action,target,detail,ip_hash) VALUES(?,?,?,?,?,?)',
                      (self.now(),actor,action,target,json.dumps(detail or {},ensure_ascii=False,default=str)[:4000],self.iphash(ip) if ip else ''))

    def queue_email(self,account_id,template,ctx,dedupe=None):
        acc=self.db.one('SELECT * FROM accounts WHERE id=?',(account_id,))
        if not acc or acc['status']=='excluida':return False
        base=dict(nome=(acc['name'] or '').split(' ')[0] or 'tudo bem',portal=self.setting('public_url').rstrip('/')+'/conta',
                  suporte=self.setting('support_email') or 'o suporte',download=self.setting('download_url'))
        subject,body=mailer.render(template,dict(base,**ctx))
        try:
            with self.db.connect(True) as c:
                c.execute('INSERT INTO outbox(account_id,to_email,template,subject,body,created,dedupe) VALUES(?,?,?,?,?,?,?)',
                          (account_id,acc['email'],template,subject,body,self.now(),dedupe))
            return True
        except Exception as exc:
            if 'UNIQUE' in str(exc):return False
            raise

    # ───── limites de tentativas ─────
    def throttled(self,key,limit,window):
        now=self.now()
        n=self.db.one('SELECT COUNT(*) n FROM attempts WHERE key=? AND at>?',(key,now-window))['n']
        return n>=limit

    def fail(self,key):
        with self.db.connect(True) as c:c.execute('INSERT INTO attempts VALUES(?,?)',(key,self.now()))

    def clear(self,key):
        with self.db.connect(True) as c:c.execute('DELETE FROM attempts WHERE key=?',(key,))

    # ───── contas ─────
    def plan(self,code):
        p=self.db.one('SELECT * FROM plans WHERE code=?',(code,))
        if not p:raise Bad('Plano não encontrado.','plano',404)
        return p

    def register(self,email,password,name,accept_terms,ip='',source='app'):
        if not self.setting('signup_open'):raise Bad('Cadastros fechados no momento. Fale com o suporte.','cadastro_fechado',403)
        email=str(email or '').strip().lower();name=str(name or '').strip()[:120]
        if not EMAIL.match(email):raise Bad('Informe um e-mail válido.','email')
        if not name:raise Bad('Informe seu nome.','nome')
        problem=sec.password_problem(password,email)
        if problem:raise Bad(problem,'senha')
        if not accept_terms:raise Bad('É preciso aceitar os Termos de Uso e a Política de Privacidade.','termos')
        key='reg:'+self.iphash(ip)
        if ip and self.throttled(key,5,3600):raise Bad('Muitos cadastros deste endereço. Tente de novo mais tarde.','limite',429)
        if self.db.one('SELECT id FROM accounts WHERE email=?',(email,)):
            # Mesma resposta de sucesso não revelaria a conta; aqui o aplicativo precisa saber, então a mensagem é direta.
            raise Bad('Já existe uma conta com este e-mail. Use “Entrar”.','email_existe',409)
        if ip:self.fail(key)
        now=self.now();aid=uid();days=int(self.setting('trial_days'))
        with self.db.connect(True) as c:
            c.execute('INSERT INTO accounts(id,email,name,pw_hash,terms_version,terms_at,privacy_version,created,source) VALUES(?,?,?,?,?,?,?,?,?)',
                      (aid,email,name,sec.hash_password(password,self.params),self.setting('terms_version'),now,self.setting('privacy_version'),now,source))
            c.execute("INSERT INTO subscriptions(id,account_id,plan_code,status,period_start,period_end,trial_end,created,updated,provider) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (uid(),aid,'teste','teste',now,now+days*DAY,now+days*DAY,now,now,self.setting('billing_provider')))
        self.audit('cliente:'+aid,'cadastro',aid,dict(email=email,origem=source),ip)
        self.queue_email(aid,'boas_vindas',dict(dias_teste=days,fim_teste=fmt_date(now+days*DAY)))
        return self.account(aid)

    def account(self,aid):
        acc=self.db.one('SELECT * FROM accounts WHERE id=?',(aid,))
        if not acc:raise Bad('Conta não encontrada.','conta',404)
        return acc

    def authenticate(self,email,password,ip=''):
        email=str(email or '').strip().lower()
        ek='login:'+email;ik='loginip:'+self.iphash(ip)
        if self.throttled(ek,8,900) or (ip and self.throttled(ik,40,900)):
            raise Bad('Muitas tentativas. Aguarde alguns minutos e tente de novo.','limite',429)
        acc=self.db.one('SELECT * FROM accounts WHERE email=?',(email,))
        if not acc or acc['status']!='ativa' or not acc['pw_hash']:
            sec.burn_time(str(password),self.params);self.fail(ek)
            if ip:self.fail(ik)
            raise Bad('E-mail ou senha incorretos.','credenciais',401)
        if not sec.verify_password(str(password),acc['pw_hash']):
            self.fail(ek)
            if ip:self.fail(ik)
            raise Bad('E-mail ou senha incorretos.','credenciais',401)
        self.clear(ek)
        with self.db.connect(True) as c:
            if sec.needs_rehash(acc['pw_hash'],self.params):c.execute('UPDATE accounts SET pw_hash=? WHERE id=?',(sec.hash_password(password,self.params),acc['id']))
            c.execute('UPDATE accounts SET last_login=? WHERE id=?',(self.now(),acc['id']))
        return acc

    def change_password(self,aid,old,new,ip=''):
        acc=self.account(aid)
        if not sec.verify_password(str(old),acc['pw_hash']):raise Bad('A senha atual está incorreta.','credenciais',401)
        self._set_password(acc,new,ip)

    def _set_password(self,acc,new,ip=''):
        problem=sec.password_problem(new,acc['email'])
        if problem:raise Bad(problem,'senha')
        with self.db.connect(True) as c:
            c.execute('UPDATE accounts SET pw_hash=? WHERE id=?',(sec.hash_password(new,self.params),acc['id']))
            c.execute('DELETE FROM user_sessions WHERE account_id=?',(acc['id'],))
        self.audit('cliente:'+acc['id'],'senha_alterada',acc['id'],{},ip)
        self.queue_email(acc['id'],'senha_alterada',{})

    def request_reset(self,email,ip=''):
        """Sempre responde igual, exista ou não a conta."""
        email=str(email or '').strip().lower()
        if ip and self.throttled('reset:'+self.iphash(ip),5,3600):return
        if ip:self.fail('reset:'+self.iphash(ip))
        acc=self.db.one("SELECT * FROM accounts WHERE email=? AND status='ativa'",(email,))
        if acc:self._reset_link(acc,'cliente')

    def _reset_link(self,acc,by):
        token=sec.new_token();minutes=int(self.setting('reset_minutes'))
        with self.db.connect(True) as c:
            c.execute('INSERT INTO resets VALUES(?,?,?,0)',(sec.digest(token),acc['id'],self.now()+minutes*60))
        link=self.setting('public_url').rstrip('/')+'/conta#reset='+token
        self.queue_email(acc['id'],'redefinir_senha',dict(link=link,minutos=minutes))
        self.audit(by,'reset_solicitado',acc['id'])
        return link

    def confirm_reset(self,token,new,ip=''):
        row=self.db.one('SELECT * FROM resets WHERE token_hash=? AND used=0 AND expires>?',(sec.digest(str(token)),self.now()))
        if not row:raise Bad('Link inválido ou vencido. Peça um novo.','link',400)
        acc=self.account(row['account_id']);self._set_password(acc,new,ip)
        with self.db.connect(True) as c:c.execute('UPDATE resets SET used=1 WHERE token_hash=?',(row['token_hash'],))

    # ───── sessões do portal do cliente ─────
    def portal_login(self,email,password,ip=''):
        acc=self.authenticate(email,password,ip)
        token=sec.new_token();csrf=sec.new_token(16);now=self.now()
        with self.db.connect(True) as c:
            c.execute('INSERT INTO user_sessions VALUES(?,?,?,?,?,?)',(sec.digest(token),acc['id'],csrf,now+int(self.setting('session_hours'))*3600,now,self.iphash(ip)))
        return token,csrf,acc

    def portal_session(self,token):
        if not token:return None
        row=self.db.one('SELECT * FROM user_sessions WHERE token_hash=? AND expires>?',(sec.digest(token),self.now()))
        return row

    def portal_logout(self,token):
        with self.db.connect(True) as c:c.execute('DELETE FROM user_sessions WHERE token_hash=?',(sec.digest(token),))

    # ───── assinatura: estado derivado ─────
    def subscription(self,aid):
        sub=self.db.one('SELECT * FROM subscriptions WHERE account_id=?',(aid,))
        if not sub:raise Bad('Assinatura não encontrada.','assinatura',404)
        return sub

    def grace(self,sub):
        return int(sub['grace_days'] if sub['grace_days'] is not None else self.setting('grace_days'))

    def effective(self,sub,now=None):
        """Estado real agora: teste, ativa, atraso, cancelada, suspensa ou expirada."""
        now=self.now() if now is None else now
        st=sub['status']
        if st=='suspensa':return 'suspensa'
        if st=='teste':return 'teste' if now<=sub['trial_end'] else 'expirada'
        end=sub['period_end'] or 0
        if st=='cancelada':return 'cancelada' if now<=end else 'expirada'
        if st=='expirada':return 'expirada'
        if now<=end:return 'ativa'
        if now<=end+self.grace(sub)*DAY:return 'atraso'
        return 'expirada'

    def window(self,sub):
        """Janela de cota: o período atual (no teste, o próprio teste). Passou do fim sem renovar? a janela continua a mesma."""
        if sub['status']=='teste':return sub['created'],sub['trial_end']
        return sub['period_start'] or sub['created'],sub['period_end'] or sub['created']

    def limits(self,sub,plan,now=None):
        now=self.now() if now is None else now
        start,end=self.window(sub)
        adj={'horas':0.0,'clipes':0.0}
        for a in self.db.rows('SELECT kind,amount FROM adjustments WHERE account_id=? AND valid_from<=? AND valid_until>=?',(sub['account_id'],now,now)):
            adj[a['kind']]=adj.get(a['kind'],0.0)+a['amount']
        return dict(lives=plan['max_lives'],horas=round(plan['hours_month']+adj['horas'],3),clipes=int(plan['clips_month']+adj['clipes']),
                    canais=plan['max_streamers'],dispositivos=plan['max_devices'])

    def usage(self,sub):
        start,_=self.window(sub)
        rows=self.db.rows('SELECT kind,SUM(amount) total,COUNT(*) n FROM usage_events WHERE account_id=? AND at_server>=? GROUP BY kind',(sub['account_id'],start))
        got={r['kind']:r['total'] for r in rows}
        return dict(horas=round((got.get('analise_s') or 0)/3600,4),clipes=int(got.get('clipe') or 0),lives=int(got.get('live') or 0))

    def entitlement(self,aid,now=None):
        now=self.now() if now is None else now
        sub=self.subscription(aid);plan=self.plan(sub['plan_code']);state=self.effective(sub,now)
        start,end=self.window(sub)
        message=STATE_TEXT[state]
        if state=='suspensa' and sub['suspended_reason']:message+=' Motivo: '+sub['suspended_reason']+'.'
        if state=='atraso':message+=' Vale até '+fmt_date(end+self.grace(sub)*DAY)+'.'
        return dict(state=state,ok=state in OK_STATES,message=message,plan=plan['code'],plan_name=plan['name'],limits=self.limits(sub,plan,now),
                    usage=self.usage(sub),period=[start,end],cancel_at_period_end=bool(sub['cancel_at_period_end']),
                    grace_until=(end+self.grace(sub)*DAY) if state=='atraso' else None,provider=sub['provider'])

    # ───── dispositivos e licença ─────
    def issue(self,account,device,now=None):
        now=self.now() if now is None else now
        ent=self.entitlement(account['id'],now);ttl=int(self.setting('token_ttl_hours'))*3600
        payload=dict(v=1,acc=account['id'],dev=device['id'],email=account['email'],nome=account['name'],plan=ent['plan'],plano=ent['plan_name'],
                     state=ent['state'],ok=ent['ok'],msg=ent['message'],limits=ent['limits'],usage=ent['usage'],periodo=ent['period'],
                     cancela=ent['cancel_at_period_end'],iat=now,exp=now+ttl,termos=self.setting('terms_version'))
        return self.keys.sign(payload)

    def activate(self,email,password,fingerprint,name='',os_name='',version='',ip=''):
        if not str(fingerprint or '').strip():raise Bad('Dispositivo sem identificação.','dispositivo')
        acc=self.authenticate(email,password,ip)
        sub=self.subscription(acc['id']);plan=self.plan(sub['plan_code']);now=self.now();fp=sec.digest(str(fingerprint))[:32]
        existing=self.db.one('SELECT * FROM devices WHERE account_id=? AND fingerprint=?',(acc['id'],fp))
        active=self.db.one('SELECT COUNT(*) n FROM devices WHERE account_id=? AND revoked=0 AND (fingerprint!=?)',(acc['id'],fp))['n']
        if active>=plan['max_devices']:
            raise Bad(f"O plano {plan['name']} permite {plan['max_devices']} computador(es) e todos já estão em uso. Remova um em Minha conta (portal) e tente de novo.",'limite_dispositivos',403)
        token=sec.new_token()
        with self.db.connect(True) as c:
            if existing:
                c.execute('UPDATE devices SET token_hash=?,revoked=0,name=?,os=?,app_version=?,last_seen=?,ip_hash=? WHERE id=?',
                          (sec.digest(token),str(name)[:80],str(os_name)[:60],str(version)[:30],now,self.iphash(ip),existing['id']));did=existing['id']
            else:
                did=uid()
                c.execute('INSERT INTO devices(id,account_id,fingerprint,name,os,app_version,token_hash,created,last_seen,ip_hash) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (did,acc['id'],fp,str(name)[:80],str(os_name)[:60],str(version)[:30],sec.digest(token),now,now,self.iphash(ip)))
        device=self.db.one('SELECT * FROM devices WHERE id=?',(did,))
        self.audit('cliente:'+acc['id'],'dispositivo_ativado',did,dict(nome=name,so=os_name),ip)
        return dict(device_token=token,license=self.issue(acc,device),email=acc['email'],name=acc['name'])

    def device_by_token(self,token):
        if not token:raise Bad('Ative este computador de novo.','nao_autorizado',401)
        dev=self.db.one('SELECT * FROM devices WHERE token_hash=?',(sec.digest(str(token)),))
        if not dev or dev['revoked']:raise Bad('Este computador foi removido da conta. Entre de novo.','dispositivo_revogado',401)
        acc=self.db.one('SELECT * FROM accounts WHERE id=?',(dev['account_id'],))
        if not acc or acc['status']!='ativa':raise Bad('Conta indisponível.','conta',401)
        return dev,acc

    def sync(self,token,events=None,info=None,ip=''):
        """Uma chamada só: recebe os eventos de uso pendentes, atualiza o dispositivo e devolve a licença nova."""
        dev,acc=self.device_by_token(token);info=info or {};now=self.now()
        accepted=self.record_usage(acc['id'],dev['id'],events or [])
        with self.db.connect(True) as c:
            c.execute('UPDATE devices SET last_seen=?,active_lives=?,app_version=?,ip_hash=? WHERE id=?',
                      (now,max(0,min(10,int(info.get('lives') or 0))),str(info.get('version') or dev['app_version'])[:30],self.iphash(ip),dev['id']))
        self.usage_alerts(acc['id'])
        dev=self.db.one('SELECT * FROM devices WHERE id=?',(dev['id'],))
        return dict(license=self.issue(acc,dev),accepted=accepted)

    def deactivate(self,token):
        dev,acc=self.device_by_token(token)
        with self.db.connect(True) as c:c.execute('UPDATE devices SET revoked=1 WHERE id=?',(dev['id'],))
        self.audit('cliente:'+acc['id'],'dispositivo_removido',dev['id'])

    def devices(self,aid):
        return self.db.rows('SELECT id,name,os,app_version,created,last_seen,revoked,active_lives FROM devices WHERE account_id=? ORDER BY created',(aid,))

    def revoke_device(self,aid,did,actor=None):
        row=self.db.one('SELECT * FROM devices WHERE id=? AND account_id=?',(did,aid))
        if not row:raise Bad('Computador não encontrado.','dispositivo',404)
        with self.db.connect(True) as c:c.execute('UPDATE devices SET revoked=1 WHERE id=?',(did,))
        self.audit(actor or 'cliente:'+aid,'dispositivo_revogado',did)

    # ───── uso ─────
    def record_usage(self,aid,did,events):
        now=self.now();ok=0
        for e in list(events)[:500]:
            try:
                kind=str(e['kind']);eid=str(e['id'])[:80];amount=float(e['amount']);at=float(e.get('at') or now)
            except (KeyError,TypeError,ValueError):continue
            if kind not in USAGE_KINDS or not eid or not 0<amount<=USAGE_KINDS[kind]:continue
            at=min(at,now+DAY)
            meta=json.dumps({k:str(v)[:60] for k,v in (e.get('meta') or {}).items()} if isinstance(e.get('meta'),dict) else {})
            with self.db.connect(True) as c:
                c.execute('INSERT OR IGNORE INTO usage_events VALUES(?,?,?,?,?,?,?,?)',(aid+':'+eid,aid,did,kind,amount,at,now,meta)).rowcount
            ok+=1   # já recebido antes também conta como aceito: o aplicativo pode apagar da fila
        return ok

    def usage_alerts(self,aid):
        try:
            sub=self.subscription(aid);plan=self.plan(sub['plan_code']);start,end=self.window(sub)
            lim=self.limits(sub,plan);use=self.usage(sub)
            for resource,key in (('horas de live','horas'),('clipes exportados','clipes')):
                if not lim[key]:continue
                ratio=use[key]/lim[key]
                for level,template in ((1.0,'cota_100'),(0.8,'cota_80')):
                    if ratio>=level:
                        if self.queue_email(aid,template,dict(recurso=resource,plano=plan['name'],fim=fmt_date(end)),dedupe=f'{aid}:{int(start)}:{key}:{template}'):
                            self.audit('sistema','cota_'+('100' if level>=1 else '80'),aid,dict(recurso=key,usado=use[key],limite=lim[key]))
                        break
        except Bad:pass

    # ───── pagamentos e períodos ─────
    def _period_after_payment(self,sub,now,months=1,days=None):
        """Quem paga atrasado ou adiantado não ganha nem perde tempo: o novo período começa onde o anterior terminou.
        Depois da tolerância (ou saindo do teste) o período começa agora."""
        end_old=sub['period_end'] or 0
        continuing=sub['status']!='teste' and end_old>0 and now<=end_old+self.grace(sub)*DAY
        start=end_old if continuing else now
        end=add_months(start,months) if days is None else start+days*DAY
        return start,end

    def apply_payment(self,aid,amount_cents,method,ref='',provider='manual',provider_id=None,plan_code=None,actor='sistema',paid_at=None,description='',note='',days=None,payment_id=None):
        """Registra um pagamento (idempotente por provider+provider_id) e estende o período."""
        sub=self.subscription(aid);now=self.now()
        if provider_id:
            dup=self.db.one("SELECT * FROM payments WHERE provider=? AND provider_id=? AND status='pago'",(provider,provider_id))
            if dup:return dict(payment=dup,duplicate=True)
        code=plan_code or sub['plan_code']
        if code=='teste':raise Bad('Escolha um plano pago para este pagamento.','plano')
        plan=self.plan(code)
        start,end=self._period_after_payment(sub,now,1,days)
        pid=payment_id or uid()
        with self.db.connect(True) as c:
            existing=c.execute('SELECT id FROM payments WHERE id=?',(pid,)).fetchone() if payment_id else None
            if existing:
                c.execute("UPDATE payments SET status='pago',paid_at=?,method=?,period_start=?,period_end=?,amount_cents=?,plan_code=?,note=? WHERE id=?",
                          (paid_at or now,method,start,end,amount_cents,code,note,pid))
            else:
                c.execute('INSERT INTO payments(id,account_id,subscription_id,provider,provider_id,plan_code,amount_cents,status,method,due_at,paid_at,period_start,period_end,description,note,created)'
                          " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,aid,sub['id'],provider,provider_id,code,amount_cents,'pago',method,now,paid_at or now,start,end,description or plan['name'],note,now))
            keep_suspended=sub['status']=='suspensa' and actor=='webhook'   # um aviso automático não desfaz uma suspensão feita por uma pessoa
            c.execute("UPDATE subscriptions SET plan_code=?,status=?,period_start=?,period_end=?,suspended_reason=?,cancel_at_period_end=0,updated=? WHERE account_id=?",
                      (code,'suspensa' if keep_suspended else 'ativa',start,end,sub['suspended_reason'] if keep_suspended else '',now,aid))
        self.audit(actor,'pagamento_registrado',aid,dict(valor=amount_cents,metodo=method,ref=ref,plano=code,periodo_fim=end))
        if amount_cents>0:self.queue_email(aid,'pagamento_recebido',dict(valor=money(amount_cents),plano=plan['name'],fim=fmt_date(end)))
        return dict(payment=self.db.one('SELECT * FROM payments WHERE id=?',(pid,)),duplicate=False)

    def payments(self,aid):
        return self.db.rows('SELECT * FROM payments WHERE account_id=? ORDER BY created DESC',(aid,))

    def create_charge(self,aid,plan_code,actor='cliente'):
        """Cobrança manual pendente (Pix pela chave). O pagamento só vale quando um administrador confirma ou o provedor avisa."""
        plan=self.plan(plan_code)
        if not plan['active'] or plan['price_cents']<=0 or plan['trial']:raise Bad('Este plano ainda não está disponível para assinatura.','plano_indisponivel')
        sub=self.subscription(aid);now=self.now();pid=uid()
        pending=self.db.one("SELECT * FROM payments WHERE account_id=? AND status='pendente' AND provider='manual' AND plan_code=?",(aid,plan_code))
        if pending:return pending
        with self.db.connect(True) as c:
            c.execute("INSERT INTO payments(id,account_id,subscription_id,provider,plan_code,amount_cents,status,due_at,description,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (pid,aid,sub['id'],'manual',plan_code,plan['price_cents'],'pendente',now+3*DAY,'Assinatura '+plan['name'],now))
        self.audit(actor+':'+aid if actor=='cliente' else actor,'cobranca_criada',aid,dict(plano=plan_code,valor=plan['price_cents']))
        return self.db.one('SELECT * FROM payments WHERE id=?',(pid,))

    def how_to_pay(self,payment):
        key=self.setting('pix_key');name=self.setting('pix_name')
        if not key:return 'Fale com o suporte para combinar o pagamento.'
        return (f"Pague {money(payment['amount_cents'])} por Pix para a chave {key}"+(f' ({name})' if name else '')+
                f". Use o código {payment['id'][:8].upper()} na descrição. Depois da confirmação sua assinatura é liberada.")

    def confirm_manual_payment(self,payment_id,actor,method='pix',ref='',note=''):
        p=self.db.one('SELECT * FROM payments WHERE id=?',(payment_id,))
        if not p:raise Bad('Cobrança não encontrada.','pagamento',404)
        if p['status']=='pago':raise Bad('Esta cobrança já está paga.','pagamento_pago',409)
        return self.apply_payment(p['account_id'],p['amount_cents'],method,ref,'manual',None,p['plan_code'],actor,note=note,payment_id=p['id'])

    # ───── ações de assinatura (usadas pelo painel) ─────
    def _touch(self,aid,**fields):
        sets=','.join(k+'=?' for k in fields)
        with self.db.connect(True) as c:c.execute(f'UPDATE subscriptions SET {sets},updated=? WHERE account_id=?',(*fields.values(),self.now(),aid))

    def suspend(self,aid,reason,actor):
        self._touch(aid,status='suspensa',suspended_reason=str(reason)[:200]);self.audit(actor,'suspensa',aid,dict(motivo=reason))
        self.queue_email(aid,'assinatura_suspensa',dict(motivo=(': '+reason) if reason else ''))

    def reactivate(self,aid,actor):
        sub=self.subscription(aid)
        self._touch(aid,status='teste' if sub['plan_code']=='teste' else 'ativa',suspended_reason='')
        self.audit(actor,'reativada',aid)

    def extend_trial(self,aid,days,actor):
        try:days=to_int(days,'dias')
        except Bad:raise Bad('Informe de 1 a 90 dias.','dias') from None
        if not 1<=days<=90:raise Bad('Informe de 1 a 90 dias.','dias')
        sub=self.subscription(aid);now=self.now()
        base=max(sub['trial_end'] or now,now)
        self._touch(aid,plan_code='teste',status='teste',trial_end=base+days*DAY,period_end=base+days*DAY,suspended_reason='')
        self.audit(actor,'teste_estendido',aid,dict(dias=days))

    def courtesy(self,aid,days,plan_code,reason,actor):
        try:days=to_int(days,'dias')
        except Bad:raise Bad('Informe de 1 a 365 dias.','dias') from None
        if not 1<=days<=365:raise Bad('Informe de 1 a 365 dias.','dias')
        if not str(reason or '').strip():raise Bad('Explique o motivo da cortesia.','motivo')
        sub=self.subscription(aid)
        return self.apply_payment(aid,0,'cortesia',str(reason)[:120],'cortesia',None,plan_code or (sub['plan_code'] if sub['plan_code']!='teste' else 'basico'),actor,description='Cortesia: '+str(reason)[:100],days=days)

    def change_plan(self,aid,plan_code,actor):
        plan=self.plan(plan_code);sub=self.subscription(aid)
        if plan['trial']:raise Bad('Use “estender teste” para o plano de teste.','plano')
        fields=dict(plan_code=plan_code)
        if sub['status']=='teste':
            now=self.now();fields.update(status='ativa',period_start=now,period_end=add_months(now,1))   # troca manual sai do teste e abre um ciclo
        self._touch(aid,**fields);self.audit(actor,'plano_alterado',aid,dict(de=sub['plan_code'],para=plan_code))

    def cancel(self,aid,actor,immediately=False):
        sub=self.subscription(aid)
        if sub['status']=='teste':
            self._touch(aid,status='expirada',trial_end=self.now()-1);self.audit(actor,'teste_cancelado',aid);return
        self._touch(aid,status='cancelada',cancel_at_period_end=1)
        if immediately:self._touch(aid,period_end=self.now()-1)
        self.audit(actor,'cancelada',aid,dict(imediato=immediately))
        self.queue_email(aid,'assinatura_cancelada',dict(fim=fmt_date(sub['period_end'])))

    def adjust(self,aid,kind,amount,reason,actor):
        if kind not in ('horas','clipes'):raise Bad('Escolha horas ou clipes.','tipo')
        amount=float(amount)
        if not -10000<amount<=10000 or amount==0:raise Bad('Quantidade inválida.','quantidade')
        if not str(reason or '').strip():raise Bad('Explique o motivo do ajuste.','motivo')
        sub=self.subscription(aid);start,end=self.window(sub);now=self.now()
        until=max(end,now)+self.grace(sub)*DAY
        with self.db.connect(True) as c:
            c.execute('INSERT INTO adjustments VALUES(?,?,?,?,?,?,?,?,?)',(uid(),aid,kind,amount,start,until,str(reason)[:200],actor,now))
        self.audit(actor,'ajuste_cota',aid,dict(tipo=kind,quantidade=amount,motivo=reason))

    def set_grace(self,aid,days,actor):
        with self.db.connect(True) as c:c.execute('UPDATE subscriptions SET grace_days=? WHERE account_id=?',(None if days in (None,'') else to_int(days,'dias',0,365),aid))
        self.audit(actor,'tolerancia_alterada',aid,dict(dias=days))

    def add_note(self,aid,text,actor):
        text=str(text or '').strip()[:1000]
        if not text:raise Bad('Escreva a nota.','nota')
        with self.db.connect(True) as c:c.execute('INSERT INTO notes VALUES(?,?,?,?,?)',(uid(),aid,actor,text,self.now()))
        self.audit(actor,'nota',aid)

    # ───── LGPD ─────
    def privacy_request(self,aid,kind,note=''):
        if kind not in ('exportacao','exclusao','correcao'):raise Bad('Tipo de pedido inválido.','tipo')
        open_=self.db.one("SELECT id FROM privacy_requests WHERE account_id=? AND kind=? AND status='aberta'",(aid,kind))
        if open_:return open_['id']
        rid=uid();now=self.now()
        with self.db.connect(True) as c:c.execute('INSERT INTO privacy_requests VALUES(?,?,?,?,?,?,?,?)',(rid,aid,kind,'aberta',now,now+15*DAY,None,str(note)[:500]))
        self.audit('cliente:'+aid,'lgpd_pedido',rid,dict(tipo=kind))
        self.queue_email(aid,'lgpd_recebido',dict(tipo={'exportacao':'cópia dos dados','exclusao':'exclusão da conta','correcao':'correção de dados'}[kind],prazo=fmt_date(now+15*DAY)))
        return rid

    def export_account(self,aid):
        acc=self.account(aid)
        data=dict(conta={k:acc[k] for k in ('id','email','name','doc','phone','status','terms_version','terms_at','privacy_version','created','last_login')},
                  assinatura=self.db.one('SELECT * FROM subscriptions WHERE account_id=?',(aid,)),pagamentos=self.payments(aid),
                  dispositivos=self.devices(aid),uso=self.db.rows('SELECT kind,amount,at_server FROM usage_events WHERE account_id=? ORDER BY at_server',(aid,)),
                  pedidos_lgpd=self.db.rows('SELECT * FROM privacy_requests WHERE account_id=?',(aid,)),gerado_em=self.now())
        return data

    def delete_account(self,aid,actor):
        """Anonimiza a conta e apaga uso, dispositivos e mensagens. Pagamentos ficam (guarda fiscal) sem dados pessoais diretos."""
        acc=self.account(aid)
        with self.db.connect(True) as c:
            c.execute("UPDATE accounts SET email=?,name='Conta excluída',pw_hash='',doc='',phone='',status='excluida' WHERE id=?",(f'excluida+{aid}@invalid',aid))
            for table in ('devices','user_sessions','usage_events','adjustments','notes','resets'):c.execute(f'DELETE FROM {table} WHERE account_id=?',(aid,))
            c.execute('DELETE FROM outbox WHERE account_id=?',(aid,))
            c.execute("UPDATE subscriptions SET status='expirada',period_end=?,trial_end=? WHERE account_id=?",(self.now()-1,self.now()-1,aid))
            c.execute("UPDATE privacy_requests SET status='concluida',done_at=? WHERE account_id=? AND kind='exclusao' AND status='aberta'",(self.now(),aid))
        self.audit(actor,'conta_excluida',aid)
        return acc['email']

    # ───── rotina periódica ─────
    def run_jobs(self):
        """Avisos de ciclo de vida e limpeza. Seguro rodar quantas vezes quiser: cada aviso tem chave de deduplicação."""
        now=self.now();sent=0
        for sub in self.db.rows("SELECT s.*,a.status astatus FROM subscriptions s JOIN accounts a ON a.id=s.account_id WHERE a.status='ativa'"):
            aid=sub['account_id'];state=self.effective(sub,now);plan=self.plan(sub['plan_code'])
            end=(sub['trial_end'] if sub['status']=='teste' else sub['period_end']) or 0
            if state=='teste' and end-now<=int(self.setting('trial_reminder_days'))*DAY:
                sent+=self.queue_email(aid,'teste_acabando',dict(fim=fmt_date(end)),dedupe=f'{aid}:teste_acabando:{int(end)}')
            if sub['status']=='teste' and state=='expirada':
                sent+=self.queue_email(aid,'teste_acabou',{},dedupe=f'{aid}:teste_acabou:{int(end)}')
            if state=='ativa' and sub['provider']=='manual' and not sub['cancel_at_period_end'] and end-now<=int(self.setting('renewal_reminder_days'))*DAY and sub['plan_code']!='teste' and plan['price_cents']>0:
                charge=self.create_charge(aid,sub['plan_code'],'sistema')
                sent+=self.queue_email(aid,'cobranca_proxima',dict(plano=plan['name'],valor=money(plan['price_cents']),vencimento=fmt_date(end),como_pagar=self.how_to_pay(charge)),dedupe=f'{aid}:cobranca:{int(end)}')
            if state=='atraso':
                charge=self.db.one("SELECT * FROM payments WHERE account_id=? AND status='pendente' ORDER BY created DESC",(aid,))
                sent+=self.queue_email(aid,'pagamento_atrasado',dict(plano=plan['name'],limite=fmt_date(end+self.grace(sub)*DAY),como_pagar=self.how_to_pay(charge) if charge else ''),dedupe=f'{aid}:atraso:{int(end)}')
        with self.db.connect(True) as c:
            c.execute('DELETE FROM attempts WHERE at<?',(now-86400,))
            c.execute('DELETE FROM user_sessions WHERE expires<?',(now,));c.execute('DELETE FROM admin_sessions WHERE expires<?',(now,))
            c.execute('DELETE FROM resets WHERE expires<?',(now-86400,))
        flushed=self.mail.flush(self.db,now=self.clock) if self.mail else None
        return dict(avisos=sent,email=flushed)
