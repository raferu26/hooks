"""Dados de exemplo para você experimentar o painel sem clientes de verdade. Tudo marcado com origem 'demo'."""
import secrets

from .service import DAY


def seed(cloud):
    s=cloud.service;now=s.now();made=[]
    # planos de exemplo ativos só na demonstração (preços ILUSTRATIVOS)
    with s.db.connect(True) as c:
        c.execute("UPDATE plans SET price_cents=9900,active=1 WHERE code='basico' AND price_cents=0")
        c.execute("UPDATE plans SET price_cents=19900,active=1 WHERE code='pro' AND price_cents=0")
        c.execute("UPDATE plans SET price_cents=49900,active=1 WHERE code='agencia' AND price_cents=0")
        c.execute("UPDATE plans SET description='Plano de demonstração.' WHERE code IN ('basico','pro','agencia') AND description LIKE 'Rascunho%'")
    cases=[('ana@demo.exemplo','Ana Streamer','teste',2,None),('bruno@demo.exemplo','Bruno Clips','pago','basico',10),('carla@demo.exemplo','Carla Games','pago','pro',25),
           ('diego@demo.exemplo','Diego Agência','pago','agencia',3),('eva@demo.exemplo','Eva Atrasada','atraso','pro',33),('fabio@demo.exemplo','Fábio Vencido','vencido','basico',60),
           ('gabi@demo.exemplo','Gabi Suspensa','suspensa','pro',15)]
    for email,name,kind,plan,days_ago in cases:
        if s.db.one('SELECT id FROM accounts WHERE email=?',(email,)):continue
        acc=s.register(email,secrets.token_urlsafe(14),name,True,'','demo');aid=acc['id'];made.append(email)
        with s.db.connect(True) as c:
            c.execute("UPDATE accounts SET source='demo' WHERE id=?",(aid,))
        if kind=='teste':
            with s.db.connect(True) as c:c.execute('UPDATE subscriptions SET trial_end=?,period_end=? WHERE account_id=?',(now+plan*DAY,now+plan*DAY,aid))
            continue
        price={'basico':9900,'pro':19900,'agencia':49900}[plan]
        s.apply_payment(aid,price,'pix','demo','manual',None,plan,'demo')
        shift=days_ago*DAY if days_ago else 0
        with s.db.connect(True) as c:
            c.execute('UPDATE subscriptions SET period_start=period_start-?,period_end=period_end-? WHERE account_id=?',(shift,shift,aid))
            c.execute('UPDATE payments SET paid_at=paid_at-? WHERE account_id=?',(shift,aid))
        if kind=='suspensa':s.suspend(aid,'teste do painel','demo')
        s.db.one('SELECT 1')
        # uso de exemplo
        sub=s.subscription(aid);lim=s.limits(sub,s.plan(plan))
        with s.db.connect(True) as c:
            horas=lim['horas']*(0.86 if kind=='pago' and plan=='pro' else 0.3);clipes=int(lim['clipes']*(0.9 if plan=='basico' else 0.35))
            c.execute('INSERT INTO usage_events VALUES(?,?,?,?,?,?,?,?)',(aid+':demo-h',aid,'demo','analise_s',horas*3600,now,now,'{}'))
            for i in range(min(clipes,40)):c.execute('INSERT INTO usage_events VALUES(?,?,?,?,?,?,?,?)',(f'{aid}:demo-c{i}',aid,'demo','clipe',1,now,now,'{}'))
    s.run_jobs()
    return f'{len(made)} clientes de demonstração criados. As senhas são aleatórias: entre pelo painel de administração.'
