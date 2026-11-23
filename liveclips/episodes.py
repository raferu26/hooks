"""Detecção de episódios, desfechos, retomadas, ironia e piadas internas a partir da transcrição (N08, N09).

Regras explícitas, não um modelo: o objetivo é registrar PROMESSAS, TENTATIVAS e PERGUNTAS abertas e relacioná-las a
desfechos com intervalo e citação. Relação temporal não é causa; ironia é sempre hipótese com alternativa; piada
interna só vira candidata (confirmação é humana). Texto da fala é dado: nada aqui executa ou obedece o que foi dito.
"""
import re

from .intelligence import normalize

PROMISE = (
    r'\bnao vou (?:perder|morrer|errar|cair|falhar|dar mole)\b', r'\bdessa vez eu (?:consigo|passo|ganho)\b',
    r'\bhoje eu (?:consigo|passo|ganho|zero)\b', r'\beu (?:garanto|prometo)\b', r'\bvou (?:conseguir|passar|ganhar)\b',
    r'\bnao tem como (?:errar|perder)\b', r'\bessa e facil\b', r'\bpra mim e facil\b', r'\bsem chance de eu (?:perder|errar)\b',
)
ATTEMPT = (r'\bde novo\b', r'\bmais uma vez\b', r'\boutra vez\b', r'\bvou tentar\b', r'\bla vou eu\b', r'\bvamos la\b', r'\bbora la\b')
FAIL = (r'\bperdi\b', r'\bmorri\b', r'\bcai\b', r'\berrei\b', r'\bnao deu\b', r'\bfalhei\b', r'\bque droga\b', r'\bestragou\b',
        r'\bperdemos\b', r'\bfui eliminado\b', r'\bdeu ruim\b')
SUCCESS = (r'\bconsegui\b', r'\bpassei\b', r'\bganhei\b', r'\bdeu certo\b', r'\bconseguimos\b', r'\bganhamos\b')
QUOTE = (r'\bele disse\b', r'\bela disse\b', r'\bele falou\b', r'\bela falou\b', r'\bo chat (?:disse|falou)\b', r'\bdiz que\b',
         r'\bcomo diz o\b', r'\bfulano disse\b', r'\bme disseram\b', r'\bfalou que\b')
CONTEXT_SWITCH = (r'\bvamos (?:pro|para o) proximo jogo\b', r'\bmudei de jogo\b', r'\bagora vou jogar\b', r'\btroquei de jogo\b',
                  r'\bproximo jogo\b', r'\bvoltei pro\b', r'\bagora vamos de\b')
CAUSAL = (r'\bpor isso\b', r'\bpor causa d[eoa]\b', r'\bpor conta d[eoa]\b', r'\bentao\b.*\bporque\b', r'\bporque\b')
POSITIVE_LITERAL = (r'\bque maravilha\b', r'\bperfeito\b', r'\botimo\b', r'\bgenial\b', r'\badorei\b', r'\bmuito bom\b',
                    r'\bque beleza\b', r'\bexcelente\b')
QUESTION_OPEN = (r'\bo que (?:e|foi) isso\b', r'\bsera que\b', r'\bcomo (?:assim|eu faco)\b', r'\bquem (?:e|foi)\b',
                 r'\bpor que\b.*\?')
LAUGH = re.compile(r'\b(?:k{3,}|(?:ha){3,}|(?:he){3,}|risos|risada)\b')
STOP = set('de a o e que do da em um uma para com nao os as se por mais mas ao ele ela eu voce e ja so tem foi era isso essa esse '
           'aqui la vai vou ta ne tipo entao ai como pra na no dos das seu sua meu minha muito mais'.split())
# Referências que dependem de contexto anterior.
REFERENCE = {'de_novo': (r'\bde novo\b', r'\bmais uma vez\b', r'\boutra vez\b', r'\ba mesma coisa\b'),
             'como_eu_falei': (r'\bcomo eu (?:falei|disse|avisei)\b', r'\blembra (?:que|do) eu\b'),
             'aquilo': (r'\baquilo\b', r'\baquela coisa\b', r'\baquele negocio\b')}


def _any(patterns, text):
    return [p for p in patterns if re.search(p, text)]


def _ev(seg, quote=None):
    return dict(kind='fala', start=round(float(seg['start']), 3), end=round(float(seg['end']), 3),
                quote=(quote if quote is not None else str(seg.get('text', '')))[:160],
                **({'seq': seg['seq']} if seg.get('seq') is not None else {}))


def sentences(transcript):
    """Cada segmento vira uma frase com texto normalizado; descarta segmentos vazios."""
    out = []
    for seg in sorted(transcript or [], key=lambda s: float(s['start'])):
        text = str(seg.get('text', '')).strip()
        if text:
            out.append(dict(seg, text=text, plain=normalize(text)))
    return out


def detect(transcript, *, window_s=900.0):
    """Devolve dict(episodios, relacoes, mudancas_de_contexto, ironia).

    episodios: promessa/tentativa/pergunta com `key` estável (idempotente), citação e prazo de revisão.
    relacoes: resolve/contradiz entre uma promessa e um desfecho posterior, SEMPRE temporais, salvo conectivo causal
    explícito na mesma frase do desfecho. Fala citada ("ele disse que não vou perder") não abre promessa."""
    rows = sentences(transcript)
    episodes, relations, switches, irony = [], [], [], []
    open_promises = []     # (index em episodes)
    for seg in rows:
        plain = seg['plain']
        quoted = bool(_any(QUOTE, plain))
        t0 = float(seg['start'])
        if _any(CONTEXT_SWITCH, plain):
            switches.append(dict(time=round(t0, 3), evidence=_ev(seg)))
            for i in open_promises:
                episodes[i].setdefault('closed_by', 'mudou_atividade')
            open_promises = []
        if not quoted and _any(PROMISE, plain):
            episodes.append(dict(kind='promessa', text=seg['text'][:200], opened=round(t0, 3), expect='sucesso',
                                 key=f'promessa|{round(t0, 1)}', evidence=[_ev(seg)]))
            open_promises.append(len(episodes) - 1)
        if not quoted and _any(ATTEMPT, plain) and not _any(PROMISE, plain):
            episodes.append(dict(kind='tentativa', text=seg['text'][:200], opened=round(t0, 3), expect='resultado',
                                 key=f'tentativa|{round(t0, 1)}', evidence=[_ev(seg)]))
        if _any(QUESTION_OPEN, plain) and not quoted:
            episodes.append(dict(kind='pergunta', text=seg['text'][:200], opened=round(t0, 3), expect='resposta',
                                 key=f'pergunta|{round(t0, 1)}', evidence=[_ev(seg)]))
        outcome = 'falha' if _any(FAIL, plain) else 'sucesso' if _any(SUCCESS, plain) else None
        if outcome and not quoted:
            live = [i for i in open_promises if episodes[i]['kind'] == 'promessa' and t0 - episodes[i]['opened'] <= window_s]
            if live:
                i = live[-1]
                causal = bool(_any(CAUSAL, plain))
                kind = 'contradiz' if outcome == 'falha' else 'resolve'
                relations.append(dict(kind=kind, src=episodes[i]['key'], dst=f'desfecho|{round(t0, 1)}',
                                      outcome=outcome, temporal_only=not causal, confidence=.55 if not causal else .7,
                                      evidence=[dict(episodes[i]['evidence'][0]), _ev(seg)],
                                      alternatives=['A fala pode se referir a outra tentativa ou a outro assunto.']))
                episodes[i]['resolved_at'] = round(t0, 3)
                episodes[i]['resolution'] = seg['text'][:200]
                episodes[i]['outcome'] = outcome
                open_promises = [k for k in open_promises if k != i]
        # Ironia: elogio literal logo depois de uma falha (hipótese; sem prosódia disponível).
        if _any(POSITIVE_LITERAL, plain) and not quoted:
            prev = [r for r in rows if 0 < t0 - float(r['end']) <= 6 and _any(FAIL, r['plain'])]
            if prev or any(rel['kind'] == 'contradiz' and 0 <= t0 - float(rel['evidence'][-1]['end']) <= 6 for rel in relations):
                irony.append(dict(time=round(t0, 3), hypothesis='ironia_ou_humor_de_situacao', status='hipotese',
                                  evidence=[_ev(prev[-1]) if prev else relations[-1]['evidence'][-1], _ev(seg)],
                                  alternatives=['elogio sincero', 'ironia', 'resignação'],
                                  limits='Sem prosódia disponível; só o contraste entre o que foi dito e o que aconteceu.'))
    return dict(episodios=episodes, relacoes=relations, mudancas_de_contexto=switches, ironia=irony)


def joke_candidates(transcript, chat=None, *, min_repeats=3):
    """Expressões repetidas pelo próprio streamer, com risada ou eco do chat por perto. São CANDIDATAS: a confirmação é humana."""
    rows = sentences(transcript)
    grams = {}
    for seg in rows:
        toks = [t for t in seg['plain'].split() if t not in STOP and len(t) > 2]
        seen = set()
        for n in (2, 3):
            for i in range(len(toks) - n + 1):
                g = ' '.join(toks[i:i + n])
                if g not in seen:
                    seen.add(g)
                    grams.setdefault(g, []).append(seg)
    out = []
    for g, segs in grams.items():
        if len(segs) < min_repeats:
            continue
        support = []
        for s in segs:
            near_laugh = any(LAUGH.search(r['plain']) for r in rows if abs(float(r['start']) - float(s['end'])) <= 3)
            near_chat = any(abs(float(m.get('time', -99)) - float(s['end'])) <= 6 and g.split()[0] in normalize(m.get('text', ''))
                            for m in chat or [])
            if near_laugh or near_chat:
                support.append(s)
        if support:
            out.append(dict(termo=g, repeticoes=len(segs), apoio=len(support), status='candidata',
                            estabelecida_em=_ev(segs[0]), evidence=[_ev(s) for s in segs[:3]],
                            limits='Candidata a piada interna: só vale como fato depois de confirmação humana.'))
    out.sort(key=lambda j: (-j['apoio'], -j['repeticoes'], j['termo']))
    return out[:10]


def references_in(text):
    """Quais referências dependentes de contexto a fala usa (para buscar a origem antes de cortar)."""
    plain = normalize(text)
    return [name for name, pats in REFERENCE.items() if _any(pats, plain)]


def persist(ctx, session, transcript, *, creator='', window_s=900.0):
    """Grava no ContextStore (idempotente). Devolve contagens do que foi criado."""
    found = detect(transcript, window_s=window_s)
    ids = {}
    created = dict(episodios=0, relacoes=0, hipoteses=0)
    for ep in found['episodios']:
        eid, new = ctx.upsert_episode(session, ep['kind'], ep['text'], ep['opened'], key=ep['key'], creator=creator,
                                      expect=ep['expect'], evidence=ep['evidence'])
        ids[ep['key']] = eid
        created['episodios'] += new
        if ep.get('closed_by') == 'mudou_atividade' and not ep.get('resolved_at'):
            ctx.resolve_episode(eid, ep['opened'], 'a atividade mudou antes do desfecho', outcome='revisar')
        elif ep.get('resolved_at') is not None:
            row = next((e for e in ctx.episodes(session) if e['id'] == eid), None)
            if row and row['status'] == 'aberto':
                ctx.resolve_episode(eid, ep['resolved_at'], ep['resolution'], outcome='resolvido')
    for rel in found['relacoes']:
        src = ids.get(rel['src'])
        if not src:
            continue
        _, new = ctx.add_relation(session, src, rel['dst'], rel['kind'], rel['evidence'], temporal_only=rel['temporal_only'],
                                  confidence=rel['confidence'], alternatives=rel['alternatives'])
        created['relacoes'] += new
    existing = {f['text'] for f in ctx.facts(session, include_inactive=True)}
    for h in found['ironia']:
        text = f"Possível ironia/humor de situação perto de {h['time']}s: {h['evidence'][-1]['quote']}"[:400]
        if text in existing:
            continue
        ctx.add_fact(session, 'hipotese', text, h['evidence'], creator=creator, expires_at=ctx.clock() + 86400, source='episodes')
        created['hipoteses'] += 1
    return created
