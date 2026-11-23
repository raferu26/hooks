"""Cobrança: Asaas (assinaturas + webhooks) ou pagamento manual por Pix. Só usa campos confirmados na documentação do Asaas.

Confirmados na documentação (docs.asaas.com): cabeçalho `access_token` nas chamadas; `POST /v3/customers` (name, cpfCnpj, email,
externalReference); `POST /v3/subscriptions` (customer, billingType, value, nextDueDate, cycle, description, externalReference);
`GET /v3/subscriptions/{id}/payments`; webhook com cabeçalho `asaas-access-token` e corpo {id, event, dateCreated, payment{...}};
eventos PAYMENT_CREATED/CONFIRMED/RECEIVED/OVERDUE/REFUNDED/DELETED. NÃO confirmados (teste no sandbox antes de vender): o campo do
link de pagamento (`invoiceUrl`), o `DELETE /v3/subscriptions/{id}` e o endereço de produção.
"""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

from . import __version__
from . import security as sec
from .service import Bad,money,uid

BASES=dict(sandbox='https://api-sandbox.asaas.com',prod='https://api.asaas.com')   # produção: confirme na documentação


def valid_cpf(value):
    d=[int(x) for x in value if x.isdigit()]
    if len(d)!=11 or len(set(d))==1:return False
    for n in (9,10):
        total=sum(d[i]*(n+1-i) for i in range(n));check=(total*10)%11%10
        if d[n]!=check:return False
    return True


def valid_cnpj(value):
    d=[int(x) for x in value if x.isdigit()]
    if len(d)!=14 or len(set(d))==1:return False
    for n in (12,13):
        weights=[5,4,3,2,9,8,7,6,5,4,3,2][-n:] if n==12 else [6,5,4,3,2,9,8,7,6,5,4,3,2]
        total=sum(d[i]*weights[i] for i in range(n));check=total%11;check=0 if check<2 else 11-check
        if d[n]!=check:return False
    return True


def clean_doc(value):
    digits=''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(digits)==11 and valid_cpf(digits) or len(digits)==14 and valid_cnpj(digits):return digits
    raise Bad('CPF ou CNPJ inválido. Confira os números.','documento')


def http_transport(method,url,headers,body):
    request=urllib.request.Request(url,data=body,method=method,headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=20) as r:return r.status,json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as exc:
        try:data=json.loads(exc.read() or b'{}')
        except ValueError:data={}
        return exc.code,data


class AsaasClient:
    def __init__(self,api_key,env='sandbox',transport=None):
        self.key=api_key;self.base=BASES.get(env,BASES['sandbox']);self.transport=transport or http_transport

    def call(self,method,path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        headers={'access_token':self.key,'Content-Type':'application/json','User-Agent':'HooksCloud/'+__version__}
        status,result=self.transport(method,self.base+path,headers,body)
        if status>=400:
            errors=result.get('errors') if isinstance(result,dict) else None
            text=(errors[0].get('description') if errors else '') or f'HTTP {status}'
            raise Bad('O provedor de pagamento recusou: '+str(text)[:200],'provedor',502)
        return result

    def create_customer(self,name,doc,email,ref):return self.call('POST','/v3/customers',dict(name=name,cpfCnpj=doc,email=email,externalReference=ref))

    def create_subscription(self,customer,billing_type,cents,due,description,ref):
        return self.call('POST','/v3/subscriptions',dict(customer=customer,billingType=billing_type,value=round(cents/100,2),nextDueDate=due,cycle='MONTHLY',
                                                           description=description[:500],externalReference=ref))

    def subscription_payments(self,sub_id):return self.call('GET',f'/v3/subscriptions/{sub_id}/payments')

    def cancel_subscription(self,sub_id):return self.call('DELETE',f'/v3/subscriptions/{sub_id}')


def asaas_from_env(env=None,transport=None):
    env=os.environ if env is None else env
    key=env.get('HOOKS_ASAAS_KEY','')
    return AsaasClient(key,env.get('HOOKS_ASAAS_ENV','sandbox'),transport) if key else None


def _date_ts(text):
    try:return dt.datetime.strptime(str(text)[:10],'%Y-%m-%d').replace(hour=15,tzinfo=dt.timezone.utc).timestamp()   # 12h em Brasília
    except ValueError:return None


class Billing:
    def __init__(self,service,client=None,webhook_token=None):
        self.s=service;self.db=service.db;self.client=client
        self.webhook_token=webhook_token if webhook_token is not None else os.environ.get('HOOKS_ASAAS_WEBHOOK_TOKEN','')

    # ───── perfil de cobrança ─────
    def save_profile(self,aid,doc=None,phone=None,name=None):
        sets=[];args=[]
        if doc not in (None,''):sets.append('doc=?');args.append(clean_doc(doc))
        if phone is not None:sets.append('phone=?');args.append(''.join(ch for ch in str(phone) if ch.isdigit() or ch=='+')[:20])
        if name:sets.append('name=?');args.append(str(name).strip()[:120])
        if sets:
            with self.db.connect(True) as c:c.execute('UPDATE accounts SET '+','.join(sets)+' WHERE id=?',(*args,aid))
            self.s.audit('cliente:'+aid,'perfil_alterado',aid,{})

    # ───── assinar ─────
    def checkout(self,aid,plan_code,billing_type='UNDEFINED'):
        plan=self.s.plan(plan_code);acc=self.s.account(aid);sub=self.s.subscription(aid)
        if not plan['active'] or plan['trial'] or plan['price_cents']<=0:raise Bad('Este plano ainda não está disponível para assinatura.','plano_indisponivel')
        if billing_type not in ('UNDEFINED','PIX','BOLETO','CREDIT_CARD'):raise Bad('Forma de pagamento inválida.','pagamento')
        if self.s.setting('billing_provider')!='asaas':
            pay=self.s.create_charge(aid,plan_code)
            return dict(tipo='manual',pagamento_id=pay['id'],valor=money(pay['amount_cents']),instrucoes=self.s.how_to_pay(pay),codigo=pay['id'][:8].upper())
        if not self.client:raise Bad('Cobrança automática não configurada. Fale com o suporte.','provedor_indisponivel',503)
        if not acc['doc']:raise Bad('Informe seu CPF ou CNPJ em “Meus dados” para gerar a cobrança.','documento')
        customer=sub['provider_customer']
        if not customer:
            customer=self.client.create_customer(acc['name'],acc['doc'],acc['email'],aid).get('id','')
            if not customer:raise Bad('O provedor não devolveu o cliente.','provedor',502)
        today=dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%Y-%m-%d')
        if sub['provider_sub']:
            try:self.client.cancel_subscription(sub['provider_sub'])
            except Bad:pass
        made=self.client.create_subscription(customer,billing_type,plan['price_cents'],today,'Hook’s '+plan['name'],f'{aid}:{plan_code}')
        link=made.get('paymentLink') or ''
        try:
            listing=self.client.subscription_payments(made['id'])
            first=(listing.get('data') or [{}])[0]
            link=first.get('invoiceUrl') or link
        except Bad:pass
        with self.db.connect(True) as c:
            c.execute("UPDATE subscriptions SET provider='asaas',provider_customer=?,provider_sub=?,pending_plan=?,updated=? WHERE account_id=?",
                      (customer,made['id'],plan_code,self.s.now(),aid))
        self.s.audit('cliente:'+aid,'assinatura_criada_asaas',aid,dict(plano=plan_code,tipo=billing_type))
        return dict(tipo='asaas',link=link,valor=money(plan['price_cents']))

    def cancel_remote(self,aid):
        sub=self.s.subscription(aid)
        if sub['provider']=='asaas' and sub['provider_sub'] and self.client:
            try:self.client.cancel_subscription(sub['provider_sub'])
            except Bad as exc:self.s.audit('sistema','cancelamento_remoto_falhou',aid,dict(erro=str(exc)))

    # ───── webhook ─────
    def webhook(self,headers,raw):
        """Guarda o evento e processa. Responde 200 mesmo se o processamento falhar (fica visível no painel) para não pausar a fila do Asaas."""
        if not self.webhook_token:return 503,dict(error='webhook não configurado')
        given=headers.get('asaas-access-token') or headers.get('Asaas-Access-Token') or ''
        if not sec.same(given,self.webhook_token):
            self.s.audit('anonimo','webhook_recusado','asaas',{})
            return 401,dict(error='não autorizado')
        try:
            body=json.loads(raw);event_id=str(body['id']);kind=str(body['event'])
        except (ValueError,KeyError,TypeError):return 400,dict(error='corpo inválido')
        with self.db.connect(True) as c:
            got=c.execute("INSERT OR IGNORE INTO webhook_events(provider,event_id,type,payload,status,received) VALUES('asaas',?,?,?,'recebido',?)",
                          (event_id,kind,raw.decode('utf-8','replace')[:20000],self.s.now())).rowcount
        if not got:return 200,dict(ok=True,duplicado=True)
        row=self.db.one("SELECT * FROM webhook_events WHERE provider='asaas' AND event_id=?",(event_id,))
        self.process(row)
        return 200,dict(ok=True)

    def process(self,row):
        status='processado';error=''
        try:
            result=self._apply(json.loads(row['payload']))
            if result=='ignorado':status='ignorado'
        except Exception as exc:
            status='erro';error=str(exc)[:300]
        with self.db.connect(True) as c:c.execute('UPDATE webhook_events SET status=?,error=?,processed=? WHERE id=?',(status,error,self.s.now(),row['id']))
        return status

    def reprocess(self,webhook_id,actor):
        row=self.db.one('SELECT * FROM webhook_events WHERE id=?',(webhook_id,))
        if not row:raise Bad('Evento não encontrado.','webhook',404)
        self.s.audit('admin:'+actor['email'],'webhook_reprocessado',str(webhook_id))
        return self.process(row)

    def _find_sub(self,payment):
        ref=payment.get('subscription')
        sub=self.db.one('SELECT * FROM subscriptions WHERE provider_sub=?',(ref,)) if ref else None
        if not sub and payment.get('customer'):sub=self.db.one('SELECT * FROM subscriptions WHERE provider_customer=?',(payment['customer'],))
        return sub

    def _apply(self,body):
        kind=str(body.get('event'));payment=body.get('payment') or {}
        if not kind.startswith('PAYMENT_') or not payment.get('id'):return 'ignorado'
        sub=self._find_sub(payment)
        if not sub:raise ValueError('cobrança de uma assinatura que não existe aqui: '+str(payment.get('subscription') or payment.get('customer')))
        aid=sub['account_id'];pid=str(payment['id']);cents=int(round(float(payment.get('value') or 0)*100))
        plan_code=sub['pending_plan'] or sub['plan_code']
        known=self.db.one("SELECT * FROM payments WHERE provider='asaas' AND provider_id=?",(pid,))
        due=_date_ts(payment.get('dueDate'))

        def upsert(status):
            with self.db.connect(True) as c:
                if known:c.execute('UPDATE payments SET status=?,amount_cents=? WHERE id=?',(status,cents or known['amount_cents'],known['id']))
                else:c.execute('INSERT INTO payments(id,account_id,subscription_id,provider,provider_id,plan_code,amount_cents,status,method,due_at,description,link,created)'
                               ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid(),aid,sub['id'],'asaas',pid,plan_code,cents,status,
                                str(payment.get('billingType') or '').lower(),due,str(payment.get('description') or 'Assinatura')[:200],str(payment.get('invoiceUrl') or ''),self.s.now()))

        if kind in ('PAYMENT_CREATED','PAYMENT_UPDATED'):
            if not known:upsert('pendente')
            return 'ok'
        if kind in ('PAYMENT_CONFIRMED','PAYMENT_RECEIVED'):
            result=self.s.apply_payment(aid,cents,str(payment.get('billingType') or 'asaas').lower(),pid,'asaas',pid,plan_code,'webhook',description=str(payment.get('description') or ''),payment_id=known['id'] if known else None)
            if not result['duplicate']:
                with self.db.connect(True) as c:c.execute("UPDATE subscriptions SET pending_plan='' WHERE account_id=?",(aid,))
            return 'ok'
        if kind=='PAYMENT_OVERDUE':
            upsert('atrasado');return 'ok'
        if kind in ('PAYMENT_REFUNDED','PAYMENT_CHARGEBACK_REQUESTED','PAYMENT_CHARGEBACK_DISPUTE'):
            upsert('estornado');self.s.suspend(aid,'pagamento estornado ou contestado','webhook');return 'ok'
        if kind=='PAYMENT_DELETED':
            upsert('cancelado');return 'ok'
        if kind=='PAYMENT_CREDIT_CARD_CAPTURE_REFUSED':
            upsert('atrasado');self.s.audit('webhook','cartao_recusado',aid,dict(pagamento=pid));return 'ok'
        return 'ignorado'
