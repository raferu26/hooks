"""Banco do servidor (SQLite com WAL). Uma conexão curta por operação, como no aplicativo."""
from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION=1

# Mudanças de estrutura depois da versão 1: {versão: [comandos SQL]}. Nunca edite uma entrada já publicada; acrescente a próxima.
# O SCHEMA acima descreve o banco NOVO (já na versão mais recente); cada migração leva um banco antigo até lá.
MIGRATIONS={}


class SchemaTooNew(RuntimeError):
    """O banco foi criado por uma versão mais nova do servidor. Abrir mesmo assim poderia corromper dados."""

SCHEMA='''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS plans(code TEXT PRIMARY KEY,name TEXT,price_cents INTEGER DEFAULT 0,max_lives INTEGER,hours_month REAL,
    clips_month INTEGER,max_streamers INTEGER,max_devices INTEGER DEFAULT 1,trial INTEGER DEFAULT 0,active INTEGER DEFAULT 1,
    public INTEGER DEFAULT 1,sort INTEGER DEFAULT 0,description TEXT DEFAULT '',created REAL);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,email TEXT UNIQUE COLLATE NOCASE,name TEXT,pw_hash TEXT,
    status TEXT DEFAULT 'ativa',doc TEXT DEFAULT '',phone TEXT DEFAULT '',terms_version TEXT,terms_at REAL,privacy_version TEXT,
    created REAL,last_login REAL,source TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS subscriptions(id TEXT PRIMARY KEY,account_id TEXT UNIQUE,plan_code TEXT,status TEXT,
    period_start REAL,period_end REAL,trial_end REAL,cancel_at_period_end INTEGER DEFAULT 0,
    grace_days INTEGER,provider TEXT DEFAULT 'manual',provider_customer TEXT DEFAULT '',provider_sub TEXT DEFAULT '',
    suspended_reason TEXT DEFAULT '',pending_plan TEXT DEFAULT '',created REAL,updated REAL);
CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY,account_id TEXT,subscription_id TEXT,provider TEXT,provider_id TEXT,
    plan_code TEXT,amount_cents INTEGER,status TEXT,method TEXT DEFAULT '',due_at REAL,paid_at REAL,period_start REAL,
    period_end REAL,description TEXT DEFAULT '',link TEXT DEFAULT '',note TEXT DEFAULT '',created REAL);
CREATE UNIQUE INDEX IF NOT EXISTS payments_provider ON payments(provider,provider_id) WHERE provider_id IS NOT NULL AND provider_id!='';
CREATE INDEX IF NOT EXISTS payments_account ON payments(account_id,created);
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,account_id TEXT,fingerprint TEXT,name TEXT,os TEXT,app_version TEXT,
    token_hash TEXT UNIQUE,created REAL,last_seen REAL,revoked INTEGER DEFAULT 0,active_lives INTEGER DEFAULT 0,ip_hash TEXT DEFAULT '',
    UNIQUE(account_id,fingerprint));
CREATE TABLE IF NOT EXISTS user_sessions(token_hash TEXT PRIMARY KEY,account_id TEXT,csrf TEXT,expires REAL,created REAL,ip_hash TEXT);
CREATE TABLE IF NOT EXISTS usage_events(event_id TEXT PRIMARY KEY,account_id TEXT,device_id TEXT,kind TEXT,amount REAL,
    at_client REAL,at_server REAL,meta TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS usage_account ON usage_events(account_id,kind,at_server);
CREATE TABLE IF NOT EXISTS adjustments(id TEXT PRIMARY KEY,account_id TEXT,kind TEXT,amount REAL,valid_from REAL,valid_until REAL,
    reason TEXT,by_admin TEXT,created REAL);
CREATE TABLE IF NOT EXISTS admins(id TEXT PRIMARY KEY,email TEXT UNIQUE COLLATE NOCASE,name TEXT,pw_hash TEXT,role TEXT,
    totp_secret TEXT DEFAULT '',totp_on INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created REAL,last_login REAL);
CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,admin_id TEXT,csrf TEXT,expires REAL,created REAL,ip_hash TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,at REAL,actor TEXT,action TEXT,target TEXT,detail TEXT,ip_hash TEXT);
CREATE INDEX IF NOT EXISTS audit_target ON audit(target,id);
CREATE TABLE IF NOT EXISTS webhook_events(id INTEGER PRIMARY KEY AUTOINCREMENT,provider TEXT,event_id TEXT,type TEXT,payload TEXT,
    status TEXT,error TEXT DEFAULT '',received REAL,processed REAL,UNIQUE(provider,event_id));
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT,to_email TEXT,template TEXT,subject TEXT,
    body TEXT,status TEXT DEFAULT 'pendente',tries INTEGER DEFAULT 0,created REAL,sent_at REAL,error TEXT DEFAULT '',dedupe TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_dedupe ON outbox(dedupe) WHERE dedupe IS NOT NULL;
CREATE TABLE IF NOT EXISTS privacy_requests(id TEXT PRIMARY KEY,account_id TEXT,kind TEXT,status TEXT DEFAULT 'aberta',created REAL,
    due_at REAL,done_at REAL,note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS attempts(key TEXT,at REAL);
CREATE INDEX IF NOT EXISTS attempts_key ON attempts(key,at);
CREATE TABLE IF NOT EXISTS resets(token_hash TEXT PRIMARY KEY,account_id TEXT,expires REAL,used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,account_id TEXT,admin TEXT,text TEXT,created REAL);
'''


class DB:
    def __init__(self,path,migrations=None,version=None):
        self.path=str(path)
        target=SCHEMA_VERSION if version is None else version
        steps=MIGRATIONS if migrations is None else migrations
        existed=Path(self.path).is_file() and Path(self.path).stat().st_size>0
        with self.connect() as c:
            c.executescript(SCHEMA)
        current=self.schema_version(existed,target)
        if current>target:
            raise SchemaTooNew(f'O banco está na versão {current}, mas este servidor só entende até a {target}. Use o servidor mais novo.')
        if current<target:
            if existed:self.safety_copy(current)
            self.migrate(current,target,steps)
        else:
            with self.connect(True) as c:c.execute("INSERT OR IGNORE INTO meta VALUES('schema_version',?)",(str(target),))

    def schema_version(self,existed=True,latest=SCHEMA_VERSION):
        """Versão gravada no banco. Banco novo (sem registro) já nasce na mais recente; banco antigo sem registro é a versão 1."""
        row=self.one("SELECT value FROM meta WHERE key='schema_version'")
        if row:return int(row['value'])
        return 1 if existed else latest

    def safety_copy(self,version):
        """Cópia ao lado do banco antes de mexer na estrutura: se uma migração falhar, nada se perde."""
        target=Path(self.path).with_name(Path(self.path).name+f'.antes-v{version}')
        if not target.exists():self.backup(target)
        return target

    def migrate(self,current,target,steps):
        """Cada versão roda numa transação própria; se falhar, desfaz aquela e para (o banco fica na última versão boa)."""
        for version in range(current+1,target+1):
            if version not in steps:raise RuntimeError(f'Falta a migração para a versão {version}.')
            with self.connect(True) as c:
                for statement in steps[version]:c.execute(statement)
                c.execute("INSERT OR REPLACE INTO meta VALUES('schema_version',?)",(str(version),))

    @contextmanager
    def connect(self,write=False):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        try:
            if write:c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:
            c.rollback();raise
        finally:c.close()

    def rows(self,sql,args=()):
        with self.connect() as c:return [dict(r) for r in c.execute(sql,args)]

    def one(self,sql,args=()):
        found=self.rows(sql,args)
        return found[0] if found else None

    def setting(self,key,default=None):
        row=self.one('SELECT value FROM settings WHERE key=?',(key,))
        return json.loads(row['value']) if row else default

    def set_setting(self,key,value):
        with self.connect(True) as c:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))

    def backup(self,target):
        """Cópia consistente do banco com o recurso de backup do próprio SQLite (seguro com o servidor ligado)."""
        import sqlite3 as s
        src=s.connect(self.path);dst=s.connect(str(target))
        try:src.backup(dst)
        finally:dst.close();src.close()
        return str(target)
