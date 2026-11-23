"""Efeitos sonoros próprios, sintetizados pelo FFmpeg na primeira vez que são usados.

Não há arquivos de terceiros: cada som é gerado por uma expressão matemática, então não
existe questão de licença. Ficam em `<dados>/efeitos/`.
"""
from pathlib import Path

from . import media

# nome -> (rótulo, duração em segundos, expressão lavfi)
EFFECTS = {
    'whoosh': ('Whoosh (transição)', .7,
               "aevalsrc='0.55*sin(2*PI*(180*t+2400*t*t))*sin(PI*t/0.7)*sin(PI*t/0.7)':d=0.7:s=44100"),
    'pop': ('Pop (destaque)', .25,
            "aevalsrc='0.8*sin(2*PI*(520+900*t)*t)*exp(-22*t)':d=0.25:s=44100"),
    'ding': ('Ding (acerto)', 1.0,
             "aevalsrc='0.55*(sin(2*PI*1318*t)+0.4*sin(2*PI*2637*t))*exp(-5*t)':d=1.0:s=44100"),
    'boom': ('Impacto grave', 1.1,
             "aevalsrc='0.95*sin(2*PI*(62-30*t)*t)*exp(-4.2*t)':d=1.1:s=44100"),
    'riser': ('Subida de tensão', 1.4,
              "aevalsrc='0.45*sin(2*PI*(200*t+700*t*t))*(t/1.4)':d=1.4:s=44100"),
    'click': ('Clique', .12,
              "aevalsrc='0.7*sin(2*PI*1800*t)*exp(-60*t)':d=0.12:s=44100"),
}


def folder(root):
    path = Path(root) / 'efeitos'
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure(root, name):
    """Gera (se faltar) e devolve o caminho do efeito."""
    if name not in EFFECTS:
        raise ValueError('Efeito sonoro desconhecido.')
    target = folder(root) / (name + '.wav')
    if target.is_file() and target.stat().st_size > 1000:
        return target
    temp = target.with_suffix('.tmp.wav')
    media.run([media.tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
               '-i', EFFECTS[name][2], '-ac', '2', '-c:a', 'pcm_s16le', str(temp)], timeout=60)
    temp.replace(target)
    return target


def catalog():
    return [dict(id=key, label=value[0], seconds=value[1]) for key, value in EFFECTS.items()]
