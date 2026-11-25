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


def identity(root=ROOT):
    """Quem sou eu: versão, commit e PASTA de instalação. Gravado em `servidor.json` para que um atalho não abra, sem saber, o servidor de
    OUTRA instalação que continua rodando sobre a mesma pasta de dados (causa-raiz do relato "os layouts não aparecem")."""
    info = read(root)
    return dict(versao=info['version'], commit=info['commit'], install=str(Path(root).resolve()))


def ui_build(path=None):
    """Identificador do HTML da interface (meta `ui-build`) e se ele confere com o conteúdo (recalcula como o build faz)."""
    import hashlib
    import re
    try:
        html = Path(path or ROOT / 'liveclips' / 'static' / 'index.html').read_text(encoding='utf-8')
    except OSError:
        return dict(id='', confere=False)
    found = re.search(r'<meta name="ui-build" content="([0-9a-f]*)">', html)
    if not found:
        return dict(id='', confere=False)
    blank = html.replace(found.group(0), '<meta name="ui-build" content="">', 1)
    return dict(id=found.group(1), confere=hashlib.sha256(blank.encode('utf-8')).hexdigest()[:12] == found.group(1))
