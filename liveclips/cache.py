"""Cache de medições caras (P24), por conteúdo do arquivo (SHA-256) e parâmetros.

Só guarda resultados determinísticos (ex.: análise técnica de um segmento). A chave inclui a versão do algoritmo, então
mudar o algoritmo invalida sozinho. Arquivo corrompido vira "não achei" (nunca erro). Limite de itens com descarte dos
mais antigos. Apagar a pasta `cache` é sempre seguro."""
import hashlib
import json
import os
from pathlib import Path
import time

MAX_ITEMS = 2000
MAX_BYTES = 400 * 1024


def _file(root, kind, sha, params):
    key = hashlib.sha256(json.dumps([kind, sha, params], sort_keys=True, default=str).encode()).hexdigest()[:40]
    return Path(root) / 'cache' / kind / (key + '.json')


def get(root, kind, sha, params=None):
    path = _file(root, kind, sha, params)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('sha') != sha or data.get('kind') != kind:
            return None
        os.utime(path, None)
        return data['value']
    except (OSError, ValueError, KeyError, AttributeError):
        return None


def put(root, kind, sha, value, params=None):
    path = _file(root, kind, sha, params)
    try:
        text = json.dumps(dict(kind=kind, sha=sha, at=int(time.time()), value=value), ensure_ascii=False)
        if len(text) > MAX_BYTES:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)
        _trim(path.parent)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _trim(folder):
    try:
        files = sorted(Path(folder).glob('*.json'), key=lambda f: f.stat().st_mtime)
        for old in files[:max(0, len(files) - MAX_ITEMS)]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def clear(root):
    """Apaga o cache inteiro. -> quantidade de arquivos removidos."""
    count = 0
    base = Path(root) / 'cache'
    if base.is_dir():
        for file in base.rglob('*.json'):
            try:
                file.unlink(); count += 1
            except OSError:
                pass
    return count
