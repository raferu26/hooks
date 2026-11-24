"""Pacotes Python de que recursos do Hook's dependem. Sem eles o recurso não funciona: o app avisa em vez de falhar em silêncio (KI-10).

Só confere se o pacote existe (`find_spec`), sem importá-lo. `missing()` devolve apenas o que falta."""
from importlib.util import find_spec

# id, módulo, nome no pip, obrigatório?, o que deixa de funcionar
DEPENDENCIES = (
    ('opencv', 'cv2', 'opencv-contrib-python', True,
     'capas automáticas, correção de cor por histograma, rastreio de região e leitura da webcam'),
    ('numpy', 'numpy', 'numpy', True, 'medidas de imagem usadas por capas, cor e rastreio'),
    ('yt_dlp', 'yt_dlp', 'yt-dlp', True, 'baixar vídeos por link (YouTube e outros)'),
    ('opentimelineio', 'opentimelineio', 'opentimelineio', False, 'o arquivo linha_do_tempo.otio do pacote de exportação'),
)


def _present(module):
    try:return find_spec(module) is not None
    except (ImportError, ValueError):return False


def status():
    """Todas as dependências: [{id, module, pip, required, present, impact}]."""
    return [dict(id=i, module=m, pip=p, required=r, present=_present(m), impact=t) for i, m, p, r, t in DEPENDENCIES]


def missing():
    """Só as que faltam, com texto pronto para o usuário."""
    out = []
    for d in status():
        if d['present']:continue
        d['message'] = ('Falta o pacote %s: sem ele deixam de funcionar %s. Rode o INSTALAR.bat de novo (ou: pip install %s).'
                        % (d['pip'], d['impact'], d['pip']))
        out.append(d)
    return out
