"""Super administração: login com permissões e 2 etapas, métricas, clientes, planos, configurações e filas."""
import datetime as dt

from . import security as sec
from .service import Bad,DAY,PERMS,SETTING_KEYS,to_int,uid

ROLES=tuple(PERMS)
BOOL_KEYS={'signup_open','trust_proxy'}
INT_KEYS={'trial_days':(1,90),'grace_days':(0,30),'token_ttl_hours':(1,720),'reset_minutes':(10,1440),'session_hours':(1,72),
          'admin_session_hours':(1,24),'renewal_reminder_days':(1,15),'trial_reminder_days':(1,15)}


class Admin:
    def __init__(self,service):
        self.s=service;self.db=service.db

    # ───── administradores ─────
    def create_admin(self,email,name,password,role,by='cli'):
        email=str(email or '').strip().lower()
        if role not in ROLES:raise Bad('Papel inválido.','papel')
        problem=sec.password_problem(password,email)
        if problem:raise Bad(problem,'senha')
        if self.db.one('SELECT id FROM admins WHERE email=?',(email,)):raise Bad('Já existe um administrador com este e-mail.','email_existe',409)
        aid=uid()
        with self.db.connect(True) as c:
            c.execute('INSERT INTO admins(id,email,name,pw_hash,role,created) VALUES(?,?,?,?,?,?)',(aid,email,str(name)[:80],sec.hash_password(password,self.s.params),role,self.s.now()))
        self.s.audit('admin:'+by,'admin_criado',aid,dict(email=email,papel=role))
        return aid

    def login(self,email,password,code='',ip=''):
        email=str(email or '').strip().lower();ek='adminlogin:'+email
        if self.s.throttled(ek,6,900) or (ip and self.s.throttled('adminip:'+self.s.iphash(ip),30,900)):
            raise Bad('Muitas tentativas. Aguarde alguns minutos.','limite',429)
        adm=self.db.one('SELECT * FROM admins WHERE email=? AND active=1',(email,))
        good=bool(adm) and sec.verify_password(str(password),adm['pw_hash'])
        if not adm:sec.burn_time(str(password),self.s.params)
        if good and adm['totp_on'] and not sec.totp_ok(adm['totp_secret'],code,self.s.now()):
            if not str(code or '').strip():raise Bad('Digite o código do aplicativo autenticador.','totp',401)
            good=False
        if not good:
            self.s.fail(ek)
            if ip:self.s.fail('adminip:'+self.s.iphash(ip))
            self.s.audit('anonimo','admin_login_falhou',email,{},ip)
            raise Bad('E-mail, senha ou código incorretos.','credenciais',401)
        self.s.clear(ek)
        token=sec.new_token();csrf=sec.new_token(16);now=self.s.now()
        with self.db.connect(True) as c:
            c.execute('INSERT INTO admin_sessions VALUES(?,?,?,?,?,?)',(sec.digest(token),adm['id'],csrf,now+int(self.s.setting('admin_session_hours'))*3600,now,self.s.iphash(ip)))
            c.execute('UPDATE admins SET last_login=? WHERE id=?',(now,adm['id']))
        self.s.audit('admin:'+adm['email'],'admin_login',adm['id'],{},ip)
        return token,csrf,adm

    def session(self,token):
        if not token:return None
        row=self.db.one('SELECT * FROM admin_sessions WHERE token_hash=? AND expires>?',(sec.digest(token),self.s.now()))
        if not row:return None
        adm=self.db.one('SELECT * FROM admins WHERE id=? AND active=1',(row['admin_id'],))
        return dict(row,admin=adm) if adm else None

    def logout(self,token):
        with self.db.connect(True) as c:c.execute('DELETE FROM admin_sessions WHERE token_hash=?',(sec.digest(token),))

    @staticmethod
    def require(admin,perm):
        allowed=PERMS.get(admin['role'],set())
        if '*' not in allowed and perm not in allowed:raise Bad('Seu papel não permite esta ação.','sem_permissao',403)

    def begin_totp(self,admin):
        secret=sec.totp_secret()
        with self.db.connect(True) as c:c.execute('UPDATE admins SET totp_secret=?,totp_on=0 WHERE id=?',(secret,admin['id']))
        return dict(secret=secret,uri=sec.totp_uri(secret,admin['email']))

    def confirm_totp(self,admin,code):
        row=self.db.one('SELECT * FROM admins WHERE id=?',(admin['id'],))
        if not row['totp_secret'] or not sec.totp_ok(row['totp_secret'],code,self.s.now()):raise Bad('Código incorreto. Confira a hora do celular.','totp')
        with self.db.connect(True) as c:c.execute('UPDATE admins SET totp_on=1 WHERE id=?',(admin['id'],))
        self.s.audit('admin:'+admin['email'],'admin_2fa_ativada',admin['id'])

    def change_password(self,admin,old,new):
        row=self.db.one('SELECT * FROM admins WHERE id=?',(admin['id'],))
        if not sec.verify_password(str(old),row['pw_hash']):raise Bad('A senha atual está incorreta.','credenciais',401)
        problem=sec.password_problem(new,row['email'])
        if problem:raise Bad(problem,'senha')
        with self.db.connect(True) as c:
            c.execute('UPDATE admins SET pw_hash=? WHERE id=?',(sec.hash_password(new,self.s.params),admin['id']))
            c.execute('DELETE FROM admin_sessions WHERE admin_id=?',(admin['id'],))
        self.s.audit('admin:'+admin['email'],'admin_senha_alterada',admin['id'])

    def admins(self):
        return self.db.rows('SELECT id,email,name,role,totp_on,active,created,last_login FROM admins ORDER BY created')

    def set_admin(self,actor,admin_id,active=None,role=None,new_password=None):
        self.require(actor,'*')
        row=self.db.one('SELECT * FROM admins WHERE id=?',(admin_id,))
        if not row:raise Bad('Administrador não encontrado.','admin',404)
        if row['id']==actor['id'] and (active is False or (role and role!=row['role'])):raise Bad('Você não pode remover o próprio acesso de dono.','proprio')
        with self.db.connect(True) as c:
            if active is not None:c.execute('UPDATE admins SET active=? WHERE id=?',(int(bool(active)),admin_id))
            if role:
                if role not in ROLES:raise Bad('Papel inválido.','papel')
                c.execute('UPDATE admins SET role=? WHERE id=?',(role,admin_id))
            if new_password:
                problem=sec.password_problem(new_password,row['email'])
                if problem:raise Bad(problem,'senha')
                c.execute('UPDATE admins SET pw_hash=?,totp_on=0,totp_secret=\'\' WHERE id=?',(sec.hash_password(new_password,self.s.params),admin_id))
            if active is False or new_password:c.execute('DELETE FROM admin_sessions WHERE admin_id=?',(admin_id,))
        self.s.audit('admin:'+actor['email'],'admin_alterado',admin_id,dict(ativo=active,papel=role,senha=bool(new_password)))

    # ───── clientes ─────
    def _row(self,r,detail=False):
        sub=self.db.one('SELECT * FROM subscriptions WHERE account_id=?',(r['id'],))
        if not sub:return None
        plan=self.s.plan(sub['plan_code']);now=self.s.now();state=self.s.effective(sub,now)
        start,end=self.s.window(sub);lim=self.s.limits(sub,plan,now);use=self.s.usage(sub)
        out=dict(id=r['id'],email=r['email'],nome=r['name'],criado=r['created'],ultimo_login=r['last_login'],conta=r['status'],estado=state,plano=plan['code'],
                 plano_nome=plan['name'],fim=end,provider=sub['provider'],cancela=bool(sub['cancel_at_period_end']),
                 horas=use['horas'],horas_lim=lim['horas'],clipes=use['clipes'],clipes_lim=lim['clipes'],preco=plan['price_cents'])
        last=self.db.one("SELECT paid_at,amount_cents FROM payments WHERE account_id=? AND status='pago' ORDER BY paid_at DESC",(r['id'],))
        out['ultimo_pagamento']=last['paid_at'] if last else None
        out['pagante']=bool(last and last['amount_cents']>0)
        if detail:
            out.update(doc=r['doc'],telefone=r['phone'],termos=r['terms_version'],termos_em=r['terms_at'],origem=r['source'],assinatura=sub,limites=lim,uso=use,
                       janela=[start,end],tolerancia=self.s.grace(sub),mensagem=self.s.entitlement(r['id'],now)['message'])
        return out

    def customers(self,q='',state='',plan='',page=1,size=25):
        rows=self.db.rows("SELECT * FROM accounts WHERE status!='excluida' ORDER BY created DESC")
        q=str(q or '').strip().casefold()
        out=[]
        for r in rows:
            if q and q not in r['email'].casefold() and q not in (r['name'] or '').casefold() and q!=r['id']:continue
            item=self._row(r)
            if not item:continue
            if state and item['estado']!=state:continue
            if plan and item['plano']!=plan:continue
            out.append(item)
        size=max(5,min(100,to_int(size,'tamanho')));page=max(1,to_int(page,'página'));total=len(out)
        return dict(total=total,page=page,size=size,items=out[(page-1)*size:page*size])

    def customer(self,aid):
        r=self.s.account(aid);item=self._row(r,True)
        item['dispositivos']=self.s.devices(aid);item['pagamentos']=self.s.payments(aid)
        item['notas']=self.db.rows('SELECT * FROM notes WHERE account_id=? ORDER BY created DESC',(aid,))
        item['auditoria']=self.db.rows('SELECT at,actor,action,detail FROM audit WHERE target=? ORDER BY id DESC LIMIT 60',(aid,))
        item['ajustes']=self.db.rows('SELECT * FROM adjustments WHERE account_id=? ORDER BY created DESC LIMIT 20',(aid,))
        item['uso_recente']=self.db.rows('SELECT kind,amount,at_server FROM usage_events WHERE account_id=? ORDER BY at_server DESC LIMIT 12',(aid,))
        item['pedidos_lgpd']=self.db.rows('SELECT * FROM privacy_requests WHERE account_id=? ORDER BY created DESC',(aid,))
        return item

    # ───── métricas ─────
    def metrics(self):
        now=self.s.now();tz=dt.timezone(dt.timedelta(hours=-3))
        month_start=dt.datetime.fromtimestamp(now,tz).replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
        counts={k:0 for k in ('teste','ativa','atraso','cancelada','suspensa','expirada')};mrr=0;payers=0;ending=[];late=[];near=[];lives=0
        for r in self.db.rows("SELECT * FROM accounts WHERE status='ativa'"):
            c=self._row(r)
            if not c:continue
            counts[c['estado']]+=1
            if c['estado'] in ('ativa','atraso') and c['pagante']:mrr+=c['preco'];payers+=1
            if c['estado']=='teste' and 0<=c['fim']-now<=3*DAY:ending.append(dict(id=c['id'],email=c['email'],fim=c['fim']))
            if c['estado']=='atraso':late.append(dict(id=c['id'],email=c['email'],fim=c['fim'],plano=c['plano_nome']))
            for key,lim in (('horas','horas_lim'),('clipes','clipes_lim')):
                if c[lim] and c[key]/c[lim]>=0.8 and c['estado'] in ('teste','ativa','atraso'):
                    near.append(dict(id=c['id'],email=c['email'],recurso=key,usado=c[key],limite=c[lim]));break
        revenue=self.db.one("SELECT COALESCE(SUM(amount_cents),0) v FROM payments WHERE status='pago' AND paid_at>=?",(month_start,))['v']
        new30=self.db.one('SELECT COUNT(*) n FROM accounts WHERE created>?',(now-30*DAY,))['n']
        cancel30=self.db.one("SELECT COUNT(*) n FROM audit WHERE action IN ('cancelada','teste_cancelado') AND at>?",(now-30*DAY,))['n']
        pending_charges=self.db.one("SELECT COUNT(*) n FROM payments WHERE status='pendente'")['n']
        lives=self.db.one('SELECT COALESCE(SUM(active_lives),0) n FROM devices WHERE revoked=0 AND last_seen>?',(now-600,))['n']
        devices_on=self.db.one('SELECT COUNT(*) n FROM devices WHERE revoked=0 AND last_seen>?',(now-600,))['n']
        return dict(estados=counts,contas=sum(counts.values()),mrr_cents=mrr,pagantes=payers,receita_mes_cents=revenue,novos_30d=new30,cancelamentos_30d=cancel30,
                    teste_acabando=ending,em_atraso=late,perto_do_limite=near[:20],cobrancas_pendentes=pending_charges,lives_agora=lives,computadores_online=devices_on,
                    lgpd_abertos=self.db.one("SELECT COUNT(*) n FROM privacy_requests WHERE status='aberta'")['n'],
                    lgpd_vencidos=self.db.one("SELECT COUNT(*) n FROM privacy_requests WHERE status='aberta' AND due_at<?",(now,))['n'],
                    webhooks_com_erro=self.db.one("SELECT COUNT(*) n FROM webhook_events WHERE status='erro'")['n'],
                    emails_pendentes=self.db.one("SELECT COUNT(*) n FROM outbox WHERE status='pendente'")['n'],
                    planos_sem_preco=[p['name'] for p in self.db.rows("SELECT name FROM plans WHERE active=0 AND trial=0")],
                    smtp=bool(self.s.mail and self.s.mail.configured),provedor=self.s.setting('billing_provider'),pix_configurado=bool(self.s.setting('pix_key')))

    # ───── planos e configurações ─────
    def plans(self):return self.db.rows('SELECT * FROM plans ORDER BY sort,code')

    def save_plan(self,actor,data):
        self.require(actor,'*')
        code=str(data.get('code') or '').strip().lower()
        if not code or not code.replace('_','').replace('-','').isalnum():raise Bad('Código do plano inválido (use letras e números).','codigo')
        try:
            vals=dict(name=str(data['name']).strip()[:60],price_cents=int(data.get('price_cents') or 0),max_lives=int(data['max_lives']),hours_month=float(data['hours_month']),
                      clips_month=int(data['clips_month']),max_streamers=int(data['max_streamers']),max_devices=int(data['max_devices']),active=int(bool(data.get('active'))),
                      public=int(bool(data.get('public',True))),sort=int(data.get('sort') or 0),description=str(data.get('description') or '')[:300])
        except (KeyError,ValueError,TypeError) as exc:raise Bad('Preencha todos os campos do plano com números válidos.','plano') from exc
        if not vals['name'] or min(vals['price_cents'],vals['hours_month'],vals['clips_month'])<0 or not 1<=vals['max_lives']<=5 or not 1<=vals['max_devices']<=20:
            raise Bad('Valores do plano fora do permitido (lives de 1 a 5, computadores de 1 a 20, sem números negativos).','plano')
        old=self.db.one('SELECT * FROM plans WHERE code=?',(code,))
        if vals['active'] and not (old and old['trial']) and vals['price_cents']<=0:raise Bad('Defina um preço maior que zero para ativar o plano.','preco')
        with self.db.connect(True) as c:
            if old:
                c.execute('UPDATE plans SET name=:name,price_cents=:price_cents,max_lives=:max_lives,hours_month=:hours_month,clips_month=:clips_month,max_streamers=:max_streamers,'
                          'max_devices=:max_devices,active=:active,public=:public,sort=:sort,description=:description WHERE code=:code',dict(vals,code=code))
            else:
                c.execute('INSERT INTO plans(code,name,price_cents,max_lives,hours_month,clips_month,max_streamers,max_devices,trial,active,public,sort,description,created)'
                          ' VALUES(:code,:name,:price_cents,:max_lives,:hours_month,:clips_month,:max_streamers,:max_devices,0,:active,:public,:sort,:description,:t)',dict(vals,code=code,t=self.s.now()))
        self.s.audit('admin:'+actor['email'],'plano_salvo',code,dict(vals,antes=old and {k:old[k] for k in ('price_cents','hours_month','clips_month','max_lives')}))

    def save_settings(self,actor,data):
        self.require(actor,'*')
        changed={}
        for key,value in data.items():
            if key not in SETTING_KEYS:continue
            if key in BOOL_KEYS:value=bool(value)
            elif key in INT_KEYS:
                try:value=int(value)
                except (TypeError,ValueError) as exc:raise Bad(f'Valor inválido em {key}.','config') from exc
                lo,hi=INT_KEYS[key]
                if not lo<=value<=hi:raise Bad(f'{key} deve ficar entre {lo} e {hi}.','config')
            elif key=='billing_provider':
                if value not in ('manual','asaas'):raise Bad('Provedor de cobrança inválido.','config')
            else:value=str(value or '').strip()[:300]
            if self.s.setting(key)!=value:changed[key]=value;self.db.set_setting(key,value)
        if changed:self.s.audit('admin:'+actor['email'],'configuracao_alterada','config',changed)
        return self.s.settings()

    # ───── listas ─────
    def payments(self,status='',limit=100):
        sql="SELECT p.*,a.email FROM payments p LEFT JOIN accounts a ON a.id=p.account_id"
        args=[]
        if status:sql+=' WHERE p.status=?';args.append(status)
        return self.db.rows(sql+' ORDER BY p.created DESC LIMIT ?',(*args,int(limit)))

    def audit_list(self,target='',action='',limit=200):
        sql='SELECT * FROM audit WHERE 1=1';args=[]
        if target:sql+=' AND target=?';args.append(target)
        if action:sql+=' AND action=?';args.append(action)
        return self.db.rows(sql+' ORDER BY id DESC LIMIT ?',(*args,int(limit)))

    def webhooks(self,limit=100):
        return self.db.rows('SELECT id,provider,event_id,type,status,error,received,processed FROM webhook_events ORDER BY id DESC LIMIT ?',(int(limit),))

    def outbox(self,status='',limit=100):
        sql='SELECT o.id,o.account_id,o.to_email,o.template,o.subject,o.body,o.status,o.tries,o.created,o.sent_at,o.error FROM outbox o'
        args=[]
        if status:sql+=' WHERE status=?';args.append(status)
        return self.db.rows(sql+' ORDER BY id DESC LIMIT ?',(*args,int(limit)))

    def mark_sent(self,actor,outbox_id):
        with self.db.connect(True) as c:c.execute("UPDATE outbox SET status='enviado',sent_at=? WHERE id=?",(self.s.now(),to_int(outbox_id,'id')))
        self.s.audit('admin:'+actor['email'],'email_marcado_enviado',str(outbox_id))

    def privacy(self,status=''):
        sql='SELECT r.*,a.email FROM privacy_requests r LEFT JOIN accounts a ON a.id=r.account_id'
        args=[]
        if status:sql+=' WHERE r.status=?';args.append(status)
        return self.db.rows(sql+' ORDER BY r.created DESC',tuple(args))

    def finish_privacy(self,actor,request_id,note='',refuse=False):
        row=self.db.one('SELECT * FROM privacy_requests WHERE id=?',(request_id,))
        if not row:raise Bad('Pedido não encontrado.','pedido',404)
        with self.db.connect(True) as c:
            c.execute('UPDATE privacy_requests SET status=?,done_at=?,note=? WHERE id=?',('recusada' if refuse else 'concluida',self.s.now(),str(note)[:500],request_id))
        self.s.audit('admin:'+actor['email'],'lgpd_pedido_encerrado',request_id,dict(recusado=refuse))
