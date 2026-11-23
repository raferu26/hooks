"""Chaves Ed25519 que assinam as licenças. A chave privada fica só no servidor; o aplicativo leva só a pública."""
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from .security import b64d,b64e


class Keyring:
    def __init__(self,path,kid='k1'):
        self.path=Path(path);self.kid=kid
        if self.path.is_file():
            self.private=serialization.load_pem_private_key(self.path.read_bytes(),password=None)
        else:
            self.private=Ed25519PrivateKey.generate()
            self.path.parent.mkdir(parents=True,exist_ok=True)
            pem=self.private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
            fd=os.open(self.path,flags,0o600)
            with os.fdopen(fd,'wb') as handle:handle.write(pem)

    @property
    def public_b64(self):
        raw=self.private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode()

    def sign(self,payload):
        """Licença = v1.<carga em base64url>.<assinatura>. Assina os bytes exatos da carga, sem normalizar JSON."""
        body=b64e(json.dumps(dict(payload,kid=self.kid),separators=(',',':'),sort_keys=True,ensure_ascii=False).encode('utf-8'))
        return 'v1.'+body+'.'+b64e(self.private.sign(body.encode('ascii')))


def verify(token,public_keys):
    """Confere a assinatura e devolve a carga. public_keys: {kid: chave pública em base64}. Levanta ValueError se inválida."""
    try:
        version,body,sig=str(token).split('.')
        if version!='v1':raise ValueError('versão')
        payload=json.loads(b64d(body))
        raw=base64.b64decode(public_keys[payload['kid']])
        Ed25519PublicKey.from_public_bytes(raw).verify(b64d(sig),body.encode('ascii'))
        return payload
    except (ValueError,KeyError,TypeError,InvalidSignature) as exc:
        raise ValueError('Licença inválida.') from exc
