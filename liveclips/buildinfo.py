"""Identificação do build e da variante. `BUILD_INFO.json` (na raiz do pacote) é gerado por `tools/empacotar_release.py`; no repositório de
desenvolvimento ele não existe e o build se identifica como 'desenvolvimento'. A variante 'sem_ia' (experimental) só existe quando o
pacote traz o arquivo `VARIANTE_SEM_IA`: ela muda o padrão de perfis NOVOS para `ai_mode='sem_ia'`; nada mais."""
import json
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parent.parent


def read(root=ROOT):
    info = dict(version=__version__, commit='desenvolvimento', variant='referencia', built='', includes=[])
    try:
        info.update(json.loads((Path(root) / 'BUILD_INFO.json').read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    info['variant'] = 'sem_ia' if (Path(root) / 'VARIANTE_SEM_IA').exists() else info.get('variant', 'referencia')
    info['label'] = f"{info['version']} · {info['commit'][:10]}" + (' · variante experimental sem IA' if info['variant'] == 'sem_ia' else '')
    return info


def is_sem_ia(root=ROOT):
    return (Path(root) / 'VARIANTE_SEM_IA').exists()
