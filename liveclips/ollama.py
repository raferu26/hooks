"""Avaliador opcional de ganchos com um modelo local (Ollama). Desligado por padrão.

Nada sai do computador: o endereço precisa ser da própria máquina (127.0.0.1/localhost) e a
transcrição só é enviada para lá. Sem Ollama instalado ou com qualquer erro, o sistema continua
com o ranking normal. O modelo só reordena (±10% da nota) e nunca cria nem remove candidatos.
Formato da API conferido na documentação do Ollama: POST /api/generate (model, prompt, stream,
format, options) e GET /api/tags.
"""
import hashlib
import json
import re
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_URL = 'http://127.0.0.1:11434'
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1', '[::1]')
MAX_TEXT = 1800
SPREAD = .10


def checked_url(url):
    url = (url or DEFAULT_URL).strip().rstrip('/')
    parsed = urlparse(url)
    if parsed.scheme != 'http' or (parsed.hostname or '') not in [h.strip('[]') for h in LOCAL_HOSTS]:
        raise ValueError('O Ollama precisa estar neste computador (endereço 127.0.0.1 ou localhost). '
                         'Nenhum texto é enviado para a internet.')
    return url


def _call(url, path, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode('utf-8')
    request = Request(url + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def models(url=None, timeout=3):
    """Nomes dos modelos instalados, ou lista vazia se o Ollama não está rodando."""
    try:
        reply = _call(checked_url(url), '/api/tags', timeout=timeout)
        return [m['name'] for m in reply.get('models', []) if m.get('name')]
    except (URLError, OSError, ValueError, KeyError, TypeError):
        return []


RUBRIC = (('gancho', .30), ('autonomia', .25), ('clareza', .15), ('emocao', .15), ('fechamento', .15))
MAX_JUDGED = 8
_CACHE = {}


def prompt_for(text, style):
    return ('Você avalia trechos de falas de lives para virarem vídeos curtos de TikTok. '
            f'Estilo do canal: {style}. Leia a transcrição e responda SOMENTE em JSON, com números de 0 a 10 nos campos '
            '"gancho" (os primeiros segundos prendem a atenção), "autonomia" (o trecho faz sentido sem o contexto anterior), '
            '"clareza" (a ideia é fácil de entender), "emocao" (há humor, surpresa, tensão ou opinião forte) e '
            '"fechamento" (termina numa ideia completa), e "motivo" (uma frase curta em português). '
            'Seja crítico: 5 é mediano. Não invente fatos que não estejam no texto.\n\n'
            'Transcrição:\n' + text[:MAX_TEXT])


def _score_from(value):
    """Nota 0-10 a partir do critério por partes (ou do campo único "nota"); None se inválido."""
    if isinstance(value, dict) and all(k in value for k, _ in RUBRIC):
        parts = {k: float(value[k]) for k, _ in RUBRIC}
        if not all(0 <= v <= 10 for v in parts.values()):
            return None
        return round(sum(parts[k] * w for k, w in RUBRIC), 1), parts
    score = float(value['nota'])
    if not 0 <= score <= 10:
        return None
    return round(score, 1), {}


def evaluate(text, style='clean', model='', url=None, generate=None):
    """{'score': 0-10, 'parts': {...}, 'reason': str, 'model': str} ou None se não veio algo utilizável."""
    if not model:
        return None
    key = hashlib.sha256(f'{model}|{style}|{text[:MAX_TEXT]}'.encode()).hexdigest()
    if generate is None and key in _CACHE:
        return _CACHE[key]
    try:
        url = checked_url(url)
        call = generate or (lambda body: _call(url, '/api/generate', body, timeout=90))
        reply = call(dict(model=model, prompt=prompt_for(text, style), stream=False, format='json',
                          options=dict(temperature=0, seed=7)))
        value = json.loads(reply['response'])
        graded = _score_from(value)
        if graded is None:
            return None
        score, parts = graded
        result = dict(score=score, parts={k: round(v, 1) for k, v in parts.items()},
                      reason=' '.join(str(value.get('motivo', '')).split())[:200], model=model)
        if generate is None:
            _CACHE[key] = result
        return result
    except (URLError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _content_words(text):
    return {w for w in re.findall(r'\w+', str(text).casefold()) if len(w) > 3}


def titles(text, model='', url=None, generate=None, limit=3):
    """Até 3 títulos curtos sugeridos pelo modelo, só os que usam palavras realmente ditas no trecho."""
    if not model:
        return []
    try:
        url = checked_url(url)
        call = generate or (lambda body: _call(url, '/api/generate', body, timeout=90))
        prompt = ('Escreva 3 títulos curtos (até 6 palavras, em português) para o início de um vídeo de TikTok sobre o trecho '
                  'abaixo. Use apenas ideias e palavras que aparecem no trecho. Responda SOMENTE em JSON: '
                  '{"titulos": ["...", "...", "..."]}\n\nTranscrição:\n' + text[:MAX_TEXT])
        reply = call(dict(model=model, prompt=prompt, stream=False, format='json', options=dict(temperature=0, seed=7)))
        raw = json.loads(reply['response']).get('titulos', [])
    except (URLError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, AttributeError):
        return []
    spoken = _content_words(text)
    result = []
    for item in raw if isinstance(raw, list) else []:
        title = ' '.join(str(item).split()).strip(' "')
        words = _content_words(title)
        if not 2 <= len(title.split()) <= 8 or len(title) > 44 or not words:
            continue
        if len(words & spoken) / len(words) < .6 or title in result:
            continue
        result.append(title)
        if len(result) >= limit:
            break
    return result


def rerank(selected, profile, generate=None):
    """Reordena os candidatos pela nota do modelo local (±10%). Candidatos sem avaliação ficam como estão."""
    if not profile.get('ollama') or not profile.get('ollama_model'):
        return selected
    result = []
    for index, candidate in enumerate(selected):
        if index >= MAX_JUDGED:
            result.append(dict(candidate))
            continue
        verdict = evaluate(candidate.get('transcript', ''), profile.get('editorial_style', 'clean'),
                           profile['ollama_model'], profile.get('ollama_url'), generate)
        item = dict(candidate)
        if verdict:
            factor = 1 - SPREAD + SPREAD * 2 * verdict['score'] / 10
            item['llm'] = verdict
            item['score'] = round(float(item.get('score', 0)) * factor, 2)
            item.setdefault('reasons', []).append(
                f"Avaliação do modelo local ({verdict['model']}): {verdict['score']:.1f}/10"
                + (f" — {verdict['reason']}" if verdict['reason'] else ''))
        result.append(item)
    return sorted(result, key=lambda c: -float(c.get('score', 0)))
