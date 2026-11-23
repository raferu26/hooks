"""Títulos por dados (P15): um modelo de texto com campos preenchidos a partir do que o programa já sabe do corte.

Campos: {rotulo} (rótulo do marcador), {streamer}, {data}, {numero} (ordem do corte na sessão), {sessao}.
Campo sem valor some junto com os separadores vizinhos; nada é inventado e o texto nunca passa do limite do título."""
import re
import time

FIELDS = ('rotulo', 'streamer', 'data', 'numero', 'sessao')
MAX_TEMPLATE = 90
MAX_TITLE = 60
PATTERN = re.compile(r'\{([a-z_]+)\}')
SEPARATORS = ' -–—:|·•,/'


def validate(template):
    """Texto do modelo -> texto limpo ou ValueError com o motivo."""
    text = ' '.join(str(template or '').split())
    if len(text) > MAX_TEMPLATE:
        raise ValueError('O modelo de título tem texto demais.')
    for name in PATTERN.findall(text):
        if name not in FIELDS:
            raise ValueError('Campo desconhecido no título: {' + name + '}. Use ' + ', '.join('{' + f + '}' for f in FIELDS) + '.')
    stripped = PATTERN.sub('', text)
    if '{' in stripped or '}' in stripped:
        raise ValueError('Chaves soltas no modelo de título.')
    return text


def render(template, values):
    """Preenche o modelo. -> texto (pode ser vazio se nenhum campo tiver valor)."""
    text = validate(template)
    if not text:
        return ''
    pieces, last = [], 0
    for match in PATTERN.finditer(text):
        pieces.append(('lit', text[last:match.start()]))
        value = ' '.join(str(values.get(match.group(1)) or '').split())
        pieces.append(('field', value))
        last = match.end()
    pieces.append(('lit', text[last:]))
    # campo vazio leva junto o separador que o acompanha
    result = []
    for index, (kind, value) in enumerate(pieces):
        if kind == 'field' and not value:
            if result and result[-1][0] == 'lit':
                result[-1] = ('lit', result[-1][1].rstrip(SEPARATORS + ' ') + ' ')
            if index + 1 < len(pieces) and pieces[index + 1][0] == 'lit':
                pieces[index + 1] = ('lit', pieces[index + 1][1].lstrip(SEPARATORS + ' '))
            continue
        result.append((kind, value))
    out = ' '.join(''.join(v for _, v in result).split()).strip(SEPARATORS + ' ')
    if len(out) > MAX_TITLE:
        out = out[:MAX_TITLE - 1].rstrip() + '…'
    return out


def values_for(candidate, streamer_name='', session_name='', number=None, when=None):
    data = candidate.get('data') or {}
    labels = [m.get('label') for m in data.get('markers') or [] if m.get('label')]
    return dict(rotulo=labels[0] if labels else '', streamer=streamer_name, sessao=session_name,
                numero=('Parte ' + str(number)) if number else '',
                data=time.strftime('%d/%m', time.localtime(time.time() if when is None else when)))


def title_entry(text, duration):
    """Título automático: os primeiros segundos do corte, no estilo padrão."""
    return dict(id='auto', text=text, start=0.0, end=round(min(3.5, max(1.0, float(duration))), 2), style='big', position='top', color='#FFFFFF')
