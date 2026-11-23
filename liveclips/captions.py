"""Legendas ASS: frases curtas, destaque por palavra sem piscar e estilos de edição.

Estilos: os quatro clássicos (dynamic, clean, bold, minimal) mantêm exatamente a
aparência da V7. Os novos (impact, pop, box) acrescentam entrada animada, ênfase
na palavra falada no pico do momento e, no impact, caixa alta.
"""
import difflib
import math
import re
import textwrap
import unicodedata

# size: ajuste sobre a fonte do perfil; outline/shadow em pixels da grade 720x1280.
CAPTION_STYLES = {
    'dynamic': dict(size=0, outline=3, shadow=1),
    'clean': dict(size=-3, outline=2, shadow=1),
    'bold': dict(size=5, outline=4, shadow=2, cap=68),
    'minimal': dict(size=-6, outline=2, shadow=0),
    'impact': dict(size=8, outline=5, shadow=2, cap=70, upper=True, pop=True, emphasis=1.16,
                   max_words=3, max_chars=18, keywords=True),
    'pop': dict(size=2, outline=3, shadow=1, pop=True, emphasis=1.12, keywords=True),
    'box': dict(size=-2, outline=9, shadow=0, box=True, max_chars=24),
}
STYLE_NAMES = tuple(CAPTION_STYLES) + ('auto',)


def tempo(seconds):
    value = max(0, round(seconds * 100))
    hours, value = divmod(value, 360000)
    minutes, value = divmod(value, 6000)
    seconds, centis = divmod(value, 100)
    return f'{hours}:{minutes:02}:{seconds:02}.{centis:02}'


def seguro(text):
    return ' '.join(str(text).split()).replace('\\', '＼').replace('{', '｛').replace('}', '｝')


def grupos(words, max_words=4, max_chars=26):
    group = []
    for word in words:
        if group and (len(group) >= max_words or
                      len(' '.join(w['text'] for w in group + [word])) > max_chars or
                      word['start'] - group[-1]['end'] > .45):
            yield group
            group = []
        group.append(word)
    if group:
        yield group


WEAK = {'a', 'o', 'as', 'os', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas', 'por',
        'para', 'pra', 'com', 'que', 'e', 'ou', 'se', 'mas', 'ao', 'the', 'of', 'to', 'and', 'in', 'on'}
HOOK_WORDS = {'nunca', 'sempre', 'ninguem', 'segredo', 'erro', 'mentira', 'verdade', 'incrivel', 'impossivel', 'gratis',
              'dinheiro', 'perigo', 'cuidado', 'urgente', 'milhao', 'melhor', 'pior', 'primeiro', 'ultimo'}
KEYWORD_COLOR = r'{\c&H3CC8FF&}'


def plain(value):
    value = unicodedata.normalize('NFKD', str(value).lower())
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in value if not unicodedata.combining(c)))


def smart_groups(words, max_words=4, max_chars=26):
    """Quebra por frase, vírgula e pausa; evita terminar uma linha em artigo ou preposição."""
    group = []
    for word in words:
        if group:
            gap = word['start'] - group[-1]['end']
            last = group[-1]['text']
            hard = last.rstrip('"\u201d\u2019)\u00bb').endswith(('.', '!', '?', '\u2026'))
            soft = len(group) >= 2 and last.endswith((',', ';', ':'))
            full = len(group) >= max_words or len(' '.join(w['text'] for w in group + [word])) > max_chars
            if hard or soft or gap > .35 or full:
                if full and not (hard or soft) and gap <= .35 and len(group) > 1 and plain(last) in WEAK:
                    carry = group.pop()
                    yield group
                    group = [carry]
                else:
                    yield group
                    group = []
        group.append(word)
    if group:
        yield group


def caption_terms(profile):
    """Dicionário usado na legenda: o do streamer mais os termos aprendidos com as suas correções."""
    profile = profile or {}
    return ', '.join(x for x in (str(profile.get('vocabulary', '')), str(profile.get('learned_terms', '')), str(profile.get('memory_terms', ''))) if x.strip())


def vocabulary_terms(vocabulary):
    return [t.strip() for t in re.split(r'[,\n;]', str(vocabulary or '')) if t.strip()]


def parse_corrections(text):
    """Regras 'errado => certo', uma por linha (também vale ->, → ou =). Devolve [(palavras_normalizadas, certo, errado)]."""
    rules = []
    for line in str(text or '').splitlines()[:200]:
        sep = next((s for s in ('=>', '->', '→', '=') if s in line), None)
        if not sep:
            continue
        wrong, right = (x.strip() for x in line.split(sep, 1))
        right = right[:40]
        tokens = [plain(w) for w in wrong.split()]
        tokens = [t for t in tokens if t]
        if tokens and len(tokens) <= 4 and right:
            rules.append((tokens, right, wrong))
    rules.sort(key=lambda r: -len(r[0]))
    return rules


def apply_corrections(words, corrections):
    """Troca o que o streamer já marcou como errado pela grafia certa, sem mexer nos tempos.
    Uma regra de várias palavras vira uma palavra só, do começo da primeira ao fim da última."""
    rules = parse_corrections(corrections) if isinstance(corrections, str) else corrections
    if not rules or not words:
        return words, []
    out, changes, i = [], [], 0
    keys = [plain(w['text']) for w in words]
    while i < len(words):
        hit = next((r for r in rules if keys[i:i + len(r[0])] == r[0]), None)
        if not hit:
            out.append(words[i]);i += 1;continue
        n = len(hit[0]);first, last = words[i], words[i + n - 1]
        pre = re.match(r'^(\W*)', first['text']).group(1)
        suf = re.search(r'(\W*)$', last['text']).group(1)
        merged = dict(first, text=pre + hit[1] + suf, end=last['end'])
        if any('p' in w for w in words[i:i + n]):
            merged['p'] = min(w.get('p', 1) for w in words[i:i + n])
        if merged['text'] != first['text'] or n > 1:
            changes.append(dict(de=' '.join(w['text'] for w in words[i:i + n]).strip(), para=hit[1], time=round(float(first['start']), 2)))
        out.append(merged);i += n
    return out, changes


def fix_vocabulary(words, vocabulary):
    """Corrige nomes parecidos com o dicionário do streamer. Devolve (palavras, correções)."""
    singles = {plain(t): t for t in vocabulary_terms(vocabulary) if ' ' not in t and len(plain(t)) >= 4}
    if not singles:
        return words, []
    fixed, changes = [], []
    for word in words:
        match = re.match(r'^(\W*)(.*?)(\W*)$', word['text'], re.S)
        prefix, core, suffix = match.groups()
        n = plain(core)
        replacement = None
        if len(n) >= 4 and n not in singles:
            for candidate in difflib.get_close_matches(n, list(singles), n=1, cutoff=.82):
                related = candidate.startswith(n) or n.startswith(candidate)
                if abs(len(candidate) - len(n)) <= 2 and not related:
                    replacement = singles[candidate]
        if replacement:
            changes.append(dict(de=core, para=replacement, time=round(float(word['start']), 2)))
            word = dict(word, text=prefix + replacement + suffix)
        fixed.append(word)
    return fixed, changes


def keyword_indexes(words, vocabulary=''):
    """Palavras que merecem cor própria: números, SIGLAS, termos de gancho e do dicionário."""
    terms = {plain(t) for t in vocabulary_terms(vocabulary) if len(plain(t)) >= 3}
    chosen, last = set(), -5
    for index, word in enumerate(words):
        core = re.sub(r'^\W+|\W+$', '', word['text'])
        n = plain(core)
        hit = (bool(re.search(r'\d', core)) or (core.isalpha() and core.isupper() and len(core) >= 3) or
               n in HOOK_WORDS or n in terms or word['text'].endswith('!'))
        if hit and index - last >= 2:
            chosen.add(index)
            last = index
    return chosen


def lines_from_transcript(segments, start, end, vocabulary='', max_words=5, max_chars=30, corrections=''):
    """Linhas editáveis de legenda (tempos relativos ao início do clipe) + correções do dicionário."""
    words = []
    for seg in segments or []:
        for w in seg.get('words') or []:
            try:
                a, b = float(w['start']), float(w['end'])
            except (KeyError, TypeError, ValueError):
                continue
            text = seguro(w.get('word', ''))
            if math.isfinite(a + b) and b > a and text and b > start and a < end:
                row = {'start': max(start, a), 'end': min(end, b), 'text': text}
                if w.get('p') is not None:
                    row['p'] = w['p']
                words.append(row)
    words.sort(key=lambda w: w['start'])
    words, forced = apply_corrections(words, corrections)
    words, changes = fix_vocabulary(words, vocabulary)
    changes = forced + changes
    lines = []
    for group in smart_groups(words, max_words, max_chars):
        lines.append(dict(start=round(group[0]['start'] - start, 3), end=round(group[-1]['end'] - start, 3),
                          text=' '.join(w['text'] for w in group),
                          words=[dict(start=round(w['start'] - start, 3), end=round(w['end'] - start, 3), word=w['text'],
                                      **({'p': w['p']} if 'p' in w else {}))
                                 for w in group]))
    if not words:  # transcrição sem palavras temporizadas: usa as frases
        for seg in segments or []:
            a, b = max(start, float(seg['start'])), min(end, float(seg['end']))
            if b > a and str(seg.get('text', '')).strip():
                lines.append(dict(start=round(a - start, 3), end=round(b - start, 3), text=seguro(seg['text']), words=[]))
    return lines, changes


def _ass_color(hex_rgb):
    value = str(hex_rgb or '#FFFFFF').lstrip('#')
    return f'&H00{value[4:6]}{value[2:4]}{value[0:2]}'.upper()


def _luma(hex_rgb):
    value = str(hex_rgb or '#FFFFFF').lstrip('#')
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (.299 * r + .587 * g + .114 * b) / 255


def title_blocks(titles, vscale=1.0, fscale=1.0, font='Arial'):
    """Estilos e eventos ASS dos títulos (tempos já no relógio final do clipe)."""
    styles, events = [], []
    for index, item in enumerate(titles or []):
        text = seguro(item['text'])
        a, b = float(item['start']), float(item['end'])
        if b <= a or tempo(a) == tempo(b):
            continue
        kind, position = item.get('style', 'big'), item.get('position', 'top')
        align, margin = {'top': (8, 170), 'center': (5, 0), 'bottom': (2, 430)}.get(position, (8, 170))
        if item.get('margin_frac') is not None and position == 'top':   # título automático abaixo da webcam: fração da altura do quadro
            margin = max(0, min(900, round(float(item['margin_frac']) * 1280)))
        margin = int(margin * vscale)
        color = item.get('color', '#FFFFFF')
        name = f'Titulo{index}'
        if kind == 'bar':
            ink = '&H00101010' if _luma(color) > .55 else '&H00FFFFFF'
            styles.append(f'Style: {name},{font},{int(50 * fscale)},{ink},{ink},{_ass_color(color)},&H00000000,-1,0,0,0,100,100,0,0,3,14,0,{align},60,60,{margin},1')
            wrap = 22
        elif kind == 'top':
            styles.append(f'Style: {name},{font},{int(36 * fscale)},{_ass_color(color)},{_ass_color(color)},&H99000000,&H80000000,-1,0,0,0,100,100,1,0,3,10,0,{align},60,60,{margin},1')
            wrap = 30
        else:
            styles.append(f'Style: {name},{font},{int(66 * fscale)},{_ass_color(color)},{_ass_color(color)},&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,{align},50,50,{margin},1')
            wrap = 16
        shown = r'\N'.join(textwrap.wrap(text.upper() if kind == 'big' else text, width=wrap)[:3])
        pop = r'{\fad(140,180)\fscx86\fscy86\t(0,170,\fscx100\fscy100)}' if kind != 'top' else r'{\fad(160,160)}'
        events.append(f'Dialogue: 1,{tempo(a)},{tempo(b)},{name},,0,0,0,,{pop}{shown}')
    return styles, events


def resolve_style(caption_style, look=None):
    """`auto` segue o estilo da edição; nomes desconhecidos voltam ao dynamic."""
    if caption_style == 'auto':
        caption_style = (look or {}).get('caption', 'dynamic')
    return caption_style if caption_style in CAPTION_STYLES else 'dynamic'


def emphasis_indexes(words, times, tolerance=.8):
    """Índice da palavra mais próxima de cada instante de pico (ênfase explicável)."""
    chosen = set()
    for moment in times or []:
        try:
            moment = float(moment)
        except (TypeError, ValueError):
            continue
        best, distance = None, tolerance
        for index, word in enumerate(words):
            gap = 0 if word['start'] <= moment <= word['end'] else min(abs(word['start'] - moment),
                                                                       abs(word['end'] - moment))
            if gap <= distance:
                best, distance = index, gap
        if best is not None:
            chosen.add(best)
    return chosen


def make_ass(segments, start, end, font_size=46, margin=260, color='00E8FF', style='dynamic',
             emphasis=None, smart=False, keep_lines=False, vocabulary='', titles=None, captions=True, canvas=None, font='Arial',
             corrections=''):
    """`canvas`: (largura, altura) em pixels quando não é 1080x1920 (1:1, 4:5, 16:9). `smart`: quebras por frase/pausa e dicionário. `keep_lines`: cada segmento é uma linha (editor).
    `titles`: títulos na tela (veja title_blocks). `captions=False` gera só os títulos."""
    spec = CAPTION_STYLES.get(style, CAPTION_STYLES['dynamic'])
    size = int(font_size) + spec['size']
    size = min(spec.get('cap', 10_000), max(24, size)) if style != 'dynamic' else int(font_size)
    border = 3 if spec.get('box') else 1
    outline_color = '&H66101010' if spec.get('box') else '&H00101010'
    play_y, vscale, fscale = 1280, 1.0, 1.0
    if canvas and tuple(canvas) != (1080, 1920):
        play_y = max(2, round(720 * canvas[1] / canvas[0]))
        vscale = max(.3, play_y / 1280)
        fscale = .75 if canvas[0] > canvas[1] else 1.0
        size = max(20, int(size * fscale))
        margin = max(30, int(int(margin) * vscale))
    title_styles, title_events = title_blocks(titles, vscale, fscale, font)
    header = (
        f'[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: {play_y}\nWrapStyle: 0\n'
        'ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, '
        'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Principal,{font},{size},&H00FFFFFF,&H00FFFFFF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,'
        f'{border},{spec["outline"]},{spec["shadow"]},2,70,90,{int(margin)},1\n'
        + ''.join(line + '\n' for line in title_styles) +
        '\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    events = []
    cursor = 0.0
    highlight, white = r'{\c&H' + color + '&}', r'{\c&HFFFFFF&}'
    grow = spec.get('emphasis', 1.0)
    use_keywords = bool(spec.get('keywords')) and smart

    def shape(text):
        return text.upper() if spec.get('upper') else text

    def event(a, b, text):
        nonlocal cursor
        a, b = max(0, a - start, cursor), min(end, b) - start
        if b <= a or tempo(a) == tempo(b):
            return False
        events.append(f'Dialogue: 0,{tempo(a)},{tempo(b)},Principal,,0,0,0,,{text}')
        cursor = b
        return True

    def render_word(word, active, strong, keyword=False):
        text = shape(word['text'])
        if strong and grow > 1:
            scale = round(grow * 100)
            text = rf'{{\fscx{scale}\fscy{scale}}}{text}{{\fscx100\fscy100}}'
        if active:
            return highlight + text + white
        if keyword:
            return KEYWORD_COLOR + text + white
        return text

    popup = r'{\fscx84\fscy84\t(0,90,\fscx106\fscy106)\t(90,170,\fscx100\fscy100)}' if spec.get('pop') else ''
    for seg in (sorted(segments, key=lambda s: float(s['start'])) if captions else []):
        if float(seg['end']) <= start or float(seg['start']) >= end:
            continue
        words = []
        for w in seg.get('words') or []:
            a, b = float(w['start']), float(w['end'])
            text = seguro(w.get('word', ''))
            if math.isfinite(a) and math.isfinite(b) and b > a and text and b > start and a < end:
                row = {'start': max(start, a), 'end': min(end, b), 'text': text}
                if w.get('p') is not None:
                    row['p'] = w['p']
                words.append(row)
        if not words:
            # Legado: sem inventar precisao por palavra. Mostra a frase sem destaque.
            text = shape(seguro(seg['text']))
            a, b = max(start, float(seg['start'])), min(end, float(seg['end']))
            lines = textwrap.wrap(text, width=spec.get('max_chars', 26))
            chunks = [lines[i:i+2] for i in range(0, len(lines), 2)]
            for i, lines in enumerate(chunks):
                event(a + (b-a)*i/len(chunks), a + (b-a)*(i+1)/len(chunks), r'\N'.join(lines))
            continue
        words.sort(key=lambda w: w['start'])
        words, _ = apply_corrections(words, corrections)
        if smart and not keep_lines:
            words, _ = fix_vocabulary(words, vocabulary)
        strong = emphasis_indexes(words, emphasis)
        keys = keyword_indexes(words, vocabulary) if use_keywords else set()
        base = {id(w): i for i, w in enumerate(words)}
        if keep_lines:
            groups = [words]
        elif smart:
            groups = smart_groups(words, spec.get('max_words', 4), spec.get('max_chars', 26))
        else:
            groups = grupos(words, spec.get('max_words', 4), spec.get('max_chars', 26))
        for group in groups:
            first = True
            for i, word in enumerate(group):
                a = word['start']
                # O destaque segue até a próxima palavra: sem quadro "apagado" entre palavras.
                b = group[i+1]['start'] if i+1 < len(group) else word['end']
                line = ' '.join(render_word(w, j == i, base[id(w)] in strong, base[id(w)] in keys)
                                for j, w in enumerate(group))
                if event(a, b, (popup if first else '') + line):
                    first = False
    return header + '\n'.join(events + title_events) + '\n'
