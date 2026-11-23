"""Senhas, tokens, TOTP e limite de tentativas. Nada aqui guarda segredo em texto puro."""
import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time

# OWASP (Password Storage Cheat Sheet): scrypt com N=2^15, r=8, p=3 é uma das combinações equivalentes aceitas.
# Os testes trocam isto por parâmetros baratos; o formato guarda os parâmetros usados em cada hash.
SCRYPT=dict(n=2**15,r=8,p=3)


def hash_password(password,params=None):
    p=params or SCRYPT
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode('utf-8'),salt=salt,n=p['n'],r=p['r'],p=p['p'],maxmem=256*1024*1024,dklen=32)
    return 'scrypt$%d$%d$%d$%s$%s'%(p['n'],p['r'],p['p'],base64.b64encode(salt).decode(),base64.b64encode(digest).decode())


def verify_password(password,stored):
    try:
        kind,n,r,p,salt,digest=stored.split('$')
        if kind!='scrypt':return False
        salt=base64.b64decode(salt);digest=base64.b64decode(digest)
        calc=hashlib.scrypt(password.encode('utf-8'),salt=salt,n=int(n),r=int(r),p=int(p),maxmem=256*1024*1024,dklen=len(digest))
    except (ValueError,TypeError):return False
    return hmac.compare_digest(calc,digest)


def needs_rehash(stored,params=None):
    p=params or SCRYPT
    try:_,n,r,pp=stored.split('$')[:4]
    except ValueError:return True
    return (int(n),int(r),int(pp))!=(p['n'],p['r'],p['p'])


_DUMMY=None


def burn_time(password,params=None):
    """Gasta o mesmo tempo de uma conferência real quando o e-mail não existe, para não revelar quem tem conta."""
    global _DUMMY
    if _DUMMY is None or needs_rehash(_DUMMY,params):_DUMMY=hash_password('x',params)
    verify_password(password,_DUMMY)


COMMON={'123456','1234567','12345678','123456789','1234567890','qwerty','qwertyuiop','password','senha123','senha1234','1q2w3e4r','abc12345',
        'abcd1234','iloveyou','admin123','brasil123','mudar123','12345678910','00000000','11111111'}


def password_problem(password,email=''):
    """Regra do NIST/OWASP: o que vale é o tamanho, sem exigir símbolos. Devolve a mensagem ou ''."""
    if not isinstance(password,str) or len(password)<10:return 'A senha precisa ter pelo menos 10 caracteres.'
    if len(password)>200:return 'A senha é longa demais (máximo 200 caracteres).'
    low=password.casefold()
    if low in COMMON or len(set(low))<4:return 'Essa senha é muito comum. Escolha uma frase mais longa.'
    if email and low==email.casefold():return 'A senha não pode ser igual ao e-mail.'
    return ''


def new_token(size=32):return secrets.token_urlsafe(size)


def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def same(a,b):return hmac.compare_digest(str(a).encode(),str(b).encode())


def b64e(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def b64d(text):return base64.urlsafe_b64decode(text+'='*(-len(text)%4))


# ───── TOTP (RFC 6238) para a verificação em duas etapas do super admin ─────
def totp_secret():return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def totp_code(secret,at=None,step=30,digits=6):
    key=base64.b32decode(secret.upper()+'='*(-len(secret)%8))
    counter=int((time.time() if at is None else at)//step)
    mac=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest()
    offset=mac[-1]&15
    value=(struct.unpack('>I',mac[offset:offset+4])[0]&0x7fffffff)%10**digits
    return str(value).zfill(digits)


def totp_ok(secret,code,at=None,window=1):
    code=str(code or '').strip().replace(' ','')
    if not code.isdigit() or len(code)!=6:return False
    now=time.time() if at is None else at
    return any(same(totp_code(secret,now+d*30),code) for d in range(-window,window+1))


def totp_uri(secret,account,issuer='Hooks'):
    from urllib.parse import quote
    return f'otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}'


class RateLimiter:
    """Balde simples por chave, em memória: protege rotas públicas contra rajadas."""
    def __init__(self,clock=time.time):
        self.clock=clock;self.hits={};self.lock=threading.Lock()

    def allow(self,key,limit,seconds):
        now=self.clock()
        with self.lock:
            recent=[t for t in self.hits.get(key,[]) if now-t<seconds]
            if len(recent)>=limit:
                self.hits[key]=recent;return False
            recent.append(now);self.hits[key]=recent
            if len(self.hits)>20000:self.hits={k:v for k,v in self.hits.items() if v and now-v[-1]<seconds}
            return True
