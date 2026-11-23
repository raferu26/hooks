"""Importa o CSV de análises do TikTok Studio e liga cada linha a um clipe exportado.

O formato do CSV NÃO é documentado pelo TikTok e pode mudar (uma referência de terceiros cita as colunas
Video title, Video link, Post time, Total likes, Total comments, Total shares, Total views; versões em
português usam nomes diferentes). Por isso o leitor aceita vários nomes de coluna, em português e inglês, e
SEMPRE mostra as ligações propostas para você confirmar antes de gravar qualquer número.
"""
import csv
import io
import re
import unicodedata

SYNONYMS = {
    'title': ('video title', 'title', 'titulo do video', 'titulo', 'descricao', 'description', 'caption', 'legenda', 'video description',
              'descricao do video'),
    'url': ('video link', 'link', 'url', 'video url', 'link do video', 'post link'),
    'posted': ('post time', 'posted', 'data de publicacao', 'data da publicacao', 'create time', 'date', 'data', 'hora da publicacao',
               'publicado em'),
    'views': ('total views', 'views', 'video views', 'visualizacoes', 'visualizacoes de video', 'total de visualizacoes', 'plays',
              'visualizacoes do video'),
    'likes': ('total likes', 'likes', 'curtidas', 'total de curtidas'),
    'comments': ('total comments', 'comments', 'comentarios', 'total de comentarios'),
    'shares': ('total shares', 'shares', 'compartilhamentos', 'total de compartilhamentos'),
    'saves': ('total saves', 'saves', 'bookmarks', 'favorites', 'favoritos', 'salvamentos', 'total de salvamentos', 'adicoes aos favoritos',
              'total bookmarks'),
    'watch_pct': ('watched full video rate', 'full video watched rate', 'completion rate', 'taxa de conclusao', 'taxa de visualizacao completa',
                  'assistiu o video inteiro', 'watched full video'),
}
STOP = set('''que para com uma por mais mas como isso esse essa aqui agora tambem muito entao quando porque ainda depois antes onde sobre
fazer tinha foram sendo pelo pela nosso nossa voce voces gente cara tipo coisa assim ficar deixa vamos fiz fez tem vai vou era ser estar
estou esta estao tudo todo toda alguem ninguem nada algo mesmo mesma outra outro the and for with that this you your from have are was
fyp foryou parati viral'''.split())
MIN_TITLE = .5
MIN_MARGIN = .15


def plain(text):
    return unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower().strip()


def number(value):
    """'1,234' '1.234' '12.5K' '1,2 mil' '45%' → float. Levanta ValueError se não for número."""
    text = plain(value).replace('%', '').replace(' ', '') if value is not None else ''
    if not text or text in ('-', '--', 'n/a'):
        raise ValueError('vazio')
    mult = 1.0
    for suffix, factor in (('mil', 1e3), ('mi', 1e6), ('k', 1e3), ('m', 1e6), ('b', 1e9)):
        if text.endswith(suffix):
            text, mult = text[:-len(suffix)], factor
            break
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.') if text.rfind(',') > text.rfind('.') else text.replace(',', '')
    elif ',' in text:
        head, _, tail = text.rpartition(',')
        text = head.replace(',', '') + '.' + tail if len(tail) != 3 or mult != 1.0 else head.replace(',', '') + tail
    elif text.count('.') > 1 or (text.count('.') == 1 and len(text.rpartition('.')[2]) == 3 and mult == 1.0):
        text = text.replace('.', '')
    return float(text) * mult


def _columns(header):
    names = [plain(h) for h in header]
    found = {}
    for key, options in SYNONYMS.items():
        for option in options:
            if option in names:
                found[key] = names.index(option)
                break
    return found


def parse(text):
    """→ (linhas, avisos). Cada linha: dict(title, url, posted, views, likes, comments, shares, saves, watch_pct?)."""
    text = text.lstrip('﻿')
    if not text.strip():
        raise ValueError('O arquivo está vazio.')
    sample = text[:2000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=',;\t').delimiter
    except csv.Error:
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    # o cabeçalho pode não ser a primeira linha (alguns exports trazem título do relatório antes)
    header_index = next((i for i, r in enumerate(rows[:6]) if 'views' in _columns(r) or 'title' in _columns(r) and len(_columns(r)) >= 3), None)
    if header_index is None:
        raise ValueError('Não reconheci as colunas. Preciso de pelo menos o título (ou link) e as visualizações do vídeo. '
                         'Se for um CSV do TikTok Studio, use a aba Conteúdo (por vídeo), não a Visão geral.')
    cols = _columns(rows[header_index])
    if 'views' not in cols or not ({'title', 'url'} & set(cols)):
        raise ValueError('Faltou a coluna de visualizações ou a de título/link. Use o CSV da aba Conteúdo (por vídeo).')
    out, warnings = [], []
    for n, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not any(c.strip() for c in row):
            continue

        def get(key):
            i = cols.get(key)
            return row[i].strip() if i is not None and i < len(row) else ''
        try:
            item = dict(title=get('title'), url=get('url'), posted=get('posted'), views=int(number(get('views'))))
        except ValueError:
            warnings.append(f'Linha {n} ignorada: visualizações ilegíveis.')
            continue
        for key in ('likes', 'comments', 'shares', 'saves'):
            try:
                item[key] = int(number(get(key)))
            except ValueError:
                item[key] = 0
        try:
            watch = number(get('watch_pct'))
            if 0 <= watch <= 1.0 and '%' not in get('watch_pct'):
                watch *= 100
            if 0 <= watch <= 100:
                item['watch_pct'] = round(watch, 1)
        except ValueError:
            pass
        out.append(item)
    if not out:
        raise ValueError('O arquivo não tem nenhuma linha de vídeo com visualizações.')
    missing = [k for k in ('likes', 'comments', 'shares', 'saves') if k not in cols]
    if missing:
        warnings.append('Colunas não encontradas (ficaram como 0): ' + ', '.join(missing) + '.')
    return out, warnings


def tokens(text):
    return {w for w in re.findall(r'[a-z0-9]{3,}', plain(text)) if w not in STOP}


def candidate_texts(candidate):
    """Textos que podem aparecer na legenda que você postou: títulos do projeto/sugeridos e as primeiras falas."""
    from . import agents
    data = candidate.get('data') or {}
    start, end = float(candidate['start']), float(candidate['end'])
    transcript = data.get('transcript_segments') or []
    texts = [t.get('text', '') for t in (data.get('project') or {}).get('titles', [])]
    texts += list(data.get('llm_titles') or [])
    try:
        texts += [t['text'] for t in agents.suggest_titles(transcript, start, end)]
    except Exception:
        pass
    words = [w.get('word', '') for s in transcript if s['end'] > start and s['start'] < end for w in (s.get('words') or [])]
    texts.append(' '.join(words[:60]) or str(data.get('transcript', ''))[:400])
    return texts


def match(rows, candidates):
    """Propõe a ligação linha → clipe. Só liga com evidência: mesmo link já registrado, ou título parecido com
    margem sobre o segundo colocado. O resto fica sem ligação para você escolher."""
    pool = []
    for c in candidates:
        perf = (c.get('data') or {}).get('performance') or {}
        pool.append(dict(id=c['id'], url=perf.get('url', '').strip(), tokens=set().union(*(tokens(t) for t in candidate_texts(c))),
                         has_performance=bool(perf)))
    result = []
    for index, row in enumerate(rows):
        found = None
        if row['url']:
            for p in pool:
                if p['url'] and p['url'].rstrip('/') == row['url'].rstrip('/'):
                    found = dict(id=p['id'], score=1.0, margin=1.0, reason='mesmo link já registrado')
                    break
        if not found:
            want = tokens(row['title'])
            if len(want) >= 2:
                scored = sorted(((len(want & p['tokens']) / len(want), p['id']) for p in pool), reverse=True)
                if scored and scored[0][0] >= MIN_TITLE:
                    margin = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0)
                    if margin >= MIN_MARGIN:
                        found = dict(id=scored[0][1], score=round(scored[0][0], 2), margin=round(margin, 2), reason='título parecido com a fala do clipe')
        result.append(dict(index=index, row=row, match=found))
    return result
