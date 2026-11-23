"""Pacote de publicação: legenda, hashtags e créditos prontos para colar. Nada é publicado daqui."""
from collections import Counter
import re
import unicodedata

from . import agents

STOP = set('''que para com uma por mais mas como isso esse essa aqui agora tambem muito entao quando porque ainda depois
antes onde sobre fazer tinha foram sendo pelo pela nosso nossa voce voces gente cara tipo coisa assim ficar deixa vamos
fiz fez tem vai vou era ser estar estou esta estao tudo todo toda alguem ninguem nada algo mesmo mesma outra outro'''.split())


def _plain(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()


def keyword_tags(transcript, start, end, limit=3):
    """Palavras mais repetidas na fala do clipe (sugestão simples, sempre para você conferir)."""
    counts = Counter()
    display = {}
    for segment in transcript or []:
        if float(segment.get('end', 0)) <= start or float(segment.get('start', 0)) >= end:
            continue
        for word in re.findall(r'[^\W\d_]{5,18}', segment.get('text', '')):
            key = _plain(word)
            if key in STOP:
                continue
            counts[key] += 1
            display.setdefault(key, key)
    return ['#' + word for word, n in counts.most_common(limit) if n >= 2]


def hashtag_line(profile, extra):
    chosen = []
    for tag in re.findall(r'#?[\wÀ-ÿ]+', str(profile.get('hashtags', ''))) + list(extra):
        tag = '#' + tag.lstrip('#')
        if tag.lower() not in [t.lower() for t in chosen]:
            chosen.append(tag)
    return ' '.join(chosen[:8])


def build(candidate, assets=(), formats=None):
    """Texto de `publicacao.txt`."""
    data = candidate.get('data') or {}
    profile = candidate.get('profile') or {}
    start, end = float(candidate['start']), float(candidate['end'])
    transcript = data.get('transcript_segments') or []
    project = data.get('project') or {}
    options = [t['text'] for t in project.get('titles', []) if t.get('text')]
    if transcript:
        options += [t['text'] for t in agents.suggest_titles(transcript, start, end) if t['text'] not in options]
    options = options[:4]
    source = (data.get('editorial_audit') or {}).get('source', {})
    lines = ['PACOTE DE PUBLICAÇÃO (revise antes de postar)', '']
    lines.append('LEGENDA — sugestões:')
    lines += [f'  {i}. {o}' for i, o in enumerate(options, 1)] or ['  (sem sugestão: o clipe não tem fala suficiente)']
    lines += ['', 'HASHTAGS: ' + (hashtag_line(profile, keyword_tags(transcript, start, end)) or '(defina suas hashtags fixas em Ajustes)')]
    credit = []
    if source.get('author'):
        credit.append(f"Streamer/canal: {source['author']}")
    if source.get('title'):
        credit.append(f"Transmissão original: {source['title']}")
    if source.get('url'):
        credit.append(f"Link: {source['url']}")
    if profile.get('credit_note'):
        credit.append(str(profile['credit_note']))
    lines += ['', 'CRÉDITOS PARA A LEGENDA:'] + (['  ' + c for c in credit] or ['  (sem dados de origem)'])
    for item in assets:
        if item.get('kind') == 'music' and item.get('title'):
            lines += ['', 'MÚSICA: ' + item['title'] + (f" — {item['uploader']}" if item.get('uploader') else '')
                      + (f" ({item['url']})" if item.get('url') else ''),
                      '  Atenção: o TikTok pode silenciar ou reivindicar músicas comerciais em contas comuns. '
                      'Prefira a biblioteca de sons do próprio TikTok ou músicas livres de direitos.']
    if formats:
        lines += ['', 'ARQUIVOS EXTRAS: ' + ', '.join(f'clipe_{f}.mp4' for f in formats)]
    lines += ['', 'Para registrar o desempenho depois da postagem, abra o clipe no Estúdio, aba Publicar, e digite os números: o sistema aprende com isso.']
    return '\n'.join(lines)
