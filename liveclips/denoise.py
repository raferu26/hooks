"""Modelo de redução de ruído por rede neural (RNNoise) para o filtro `arnndn` do FFmpeg.

O modelo NÃO vai dentro do programa: é baixado uma vez, com verificação de integridade (SHA-256), para a
pasta de dados. O arquivo vem do repositório GregorR/rnnoise-models ("beguiling-drafter", feito para voz em
gravação com ruído de fundo); o autor declara que os arquivos de modelo não são sujeitos a direitos autorais.
Qualidade em fala real não foi medida aqui; ouça o resultado antes de usar em tudo.
"""
import hashlib
from pathlib import Path
import urllib.request

URL = 'https://raw.githubusercontent.com/GregorR/rnnoise-models/master/beguiling-drafter-2018-08-30/bd.rnnn'
SHA256 = 'ae3f7411e1e6a884f839a4a145c394408398f09854dbc1216ee02faafc98a17b'
NAME = 'rnnoise_bd.rnnn'
MAX_BYTES = 2_000_000


def path(root):
    return Path(root) / 'models' / NAME


def sha_ok(file):
    try:
        return hashlib.sha256(Path(file).read_bytes()).hexdigest() == SHA256
    except OSError:
        return False


def status(root):
    file = path(root)
    return dict(ready=file.is_file() and sha_ok(file), url=URL, size=file.stat().st_size if file.is_file() else 0)


def fetch(root, opener=None):
    """Baixa e confere o modelo. `opener(url)` devolve os bytes (injetável nos testes). Levanta ValueError em português."""
    file = path(root)
    if status(root)['ready']:
        return status(root)
    file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if opener:
            data = opener(URL)
        else:
            with urllib.request.urlopen(URL, timeout=60) as response:
                data = response.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ValueError('Não consegui baixar o modelo de redução de ruído (sem internet ou GitHub bloqueado): ' + str(exc)[:120]) from exc
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('O arquivo baixado não bate com o modelo esperado (verificação SHA-256 falhou). Nada foi instalado.')
    tmp = file.with_suffix('.baixando')
    tmp.write_bytes(data)
    tmp.replace(file)
    return status(root)
