"""Textos dos e-mails e envio. Sem SMTP configurado, as mensagens ficam na caixa de saída para você enviar à mão."""
import os
import smtplib
import ssl
import time
from email.message import EmailMessage

TEMPLATES={
 'boas_vindas':('Bem-vindo ao Hook’s','Olá, {nome}!\n\nSua conta foi criada e o teste de {dias_teste} dias já está valendo até {fim_teste}.\n\nBaixe o Hook’s, abra o programa e entre com este e-mail e a senha que você criou.\n{download}\n\nSe precisar de ajuda: {suporte}\n'),
 'teste_acabando':('Seu teste do Hook’s termina em breve','Olá, {nome}.\n\nSeu teste termina em {fim}. Para continuar clipando sem interrupção, escolha um plano em {portal}.\n\nO que você já gerou continua com você.\n'),
 'teste_acabou':('Seu teste do Hook’s terminou','Olá, {nome}.\n\nO teste terminou. Seus clipes continuam acessíveis, mas novas lives e exportações ficam bloqueadas até você assinar um plano em {portal}.\n'),
 'pagamento_recebido':('Pagamento recebido','Olá, {nome}.\n\nRecebemos {valor} do plano {plano}. Sua assinatura está ativa até {fim}.\n\nObrigado!\n'),
 'cobranca_proxima':('Sua mensalidade do Hook’s vence em breve','Olá, {nome}.\n\nSua mensalidade do plano {plano} ({valor}) vence em {vencimento}.\n\n{como_pagar}\n'),
 'pagamento_atrasado':('Pagamento em atraso','Olá, {nome}.\n\nNão identificamos o pagamento do plano {plano}. Você pode continuar usando até {limite}; depois disso novas lives e exportações serão bloqueadas.\n\n{como_pagar}\n'),
 'assinatura_suspensa':('Assinatura suspensa','Olá, {nome}.\n\nSua assinatura foi suspensa{motivo}. Seus clipes continuam acessíveis. Para reativar, fale com {suporte} ou acesse {portal}.\n'),
 'assinatura_cancelada':('Assinatura cancelada','Olá, {nome}.\n\nSua assinatura foi cancelada e continua valendo até {fim}. Depois disso, o acesso a novas exportações é encerrado.\n'),
 'cota_80':('Você usou 80% do seu plano','Olá, {nome}.\n\nVocê usou 80% de {recurso} do plano {plano} neste ciclo (renova em {fim}). Para não parar no meio de uma live, veja as opções em {portal}.\n'),
 'cota_100':('Limite do plano atingido','Olá, {nome}.\n\nVocê atingiu o limite de {recurso} do plano {plano}. Novas análises/exportações ficam em pausa até {fim} ou até você mudar de plano em {portal}.\nO que já foi gravado continua salvo no seu computador.\n'),
 'redefinir_senha':('Redefinir sua senha','Olá, {nome}.\n\nPara criar uma nova senha, abra o link (vale por {minutos} minutos):\n{link}\n\nSe não foi você, ignore esta mensagem.\n'),
 'senha_alterada':('Sua senha foi alterada','Olá, {nome}.\n\nA senha da sua conta foi alterada. Se não foi você, responda a este e-mail agora.\n'),
 'lgpd_recebido':('Recebemos seu pedido sobre dados pessoais','Olá, {nome}.\n\nRegistramos seu pedido ({tipo}). Respondemos até {prazo}.\n'),
 'conta_excluida':('Sua conta foi excluída','Olá.\n\nSua conta e os dados pessoais foram removidos. Registros fiscais de pagamentos são mantidos pelo prazo da lei.\n'),
}


def render(template,ctx):
    subject,body=TEMPLATES[template]
    class Safe(dict):
        def __missing__(self,key):return ''
    data=Safe({k:('' if v is None else v) for k,v in ctx.items()})
    return subject.format_map(data),body.format_map(data)


class Mailer:
    """Lê SMTP do ambiente: HOOKS_SMTP_HOST, HOOKS_SMTP_PORT, HOOKS_SMTP_USER, HOOKS_SMTP_PASS, HOOKS_SMTP_FROM."""
    def __init__(self,env=None,factory=None):
        env=os.environ if env is None else env
        self.host=env.get('HOOKS_SMTP_HOST','');self.port=int(env.get('HOOKS_SMTP_PORT','587') or 587)
        self.user=env.get('HOOKS_SMTP_USER','');self.password=env.get('HOOKS_SMTP_PASS','');self.sender=env.get('HOOKS_SMTP_FROM',self.user)
        self.factory=factory

    @property
    def configured(self):return bool(self.host and self.sender)

    def send(self,to,subject,body):
        message=EmailMessage();message['From']=self.sender;message['To']=to;message['Subject']=subject;message.set_content(body)
        if self.factory:return self.factory(message)
        if self.port==465:
            with smtplib.SMTP_SSL(self.host,self.port,context=ssl.create_default_context(),timeout=20) as s:
                if self.user:s.login(self.user,self.password)
                s.send_message(message)
        else:
            with smtplib.SMTP(self.host,self.port,timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                if self.user:s.login(self.user,self.password)
                s.send_message(message)

    def flush(self,db,limit=50,now=time.time):
        """Envia as pendentes. Falhas ficam registradas e são tentadas de novo até 5 vezes."""
        if not self.configured:return dict(sent=0,failed=0,configured=False)
        sent=failed=0
        for row in db.rows("SELECT * FROM outbox WHERE status='pendente' AND tries<5 ORDER BY id LIMIT ?",(limit,)):
            try:
                self.send(row['to_email'],row['subject'],row['body'])
                with db.connect(True) as c:c.execute("UPDATE outbox SET status='enviado',sent_at=?,tries=tries+1,error='' WHERE id=?",(now(),row['id']));sent+=1
            except Exception as exc:
                with db.connect(True) as c:c.execute("UPDATE outbox SET tries=tries+1,error=?,status=CASE WHEN tries+1>=5 THEN 'erro' ELSE status END WHERE id=?",(str(exc)[:300],row['id']));failed+=1
        return dict(sent=sent,failed=failed,configured=True)
