"""Edição local por conversa (P16/F27): frases em português viram mudanças TIPADAS no projeto.

Princípios: o texto nunca vira comando de shell nem código; cada pedido vira uma operação de uma lista fechada, é
validado por `project.clean` (os mesmos limites do editor) e fica numa pilha com desfazer. O que não for entendido é
devolvido como pergunta, nunca adivinhado. Mudanças grandes pedem confirmação. Nada aqui renderiza ou publica.
"""
import copy
import re

from . import project as projectlib

NUMBER = r'(\d{1,2}:\d{2}(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(?:s|seg|segundos?)?'
RANGE = re.compile(r'(?:de|do|dos|entre|a partir d[eo])\s+' + NUMBER + r'\s*(?:a|ao|até|até\s+o|e|-)\s+' + NUMBER, re.I)
POINT = re.compile(r'(?:aos|aos\s+|em|no|na|perto\s+d[eo]|por\s+volta\s+d[eo])\s*(?:segundo\s+)?' + NUMBER, re.I)
FOR_SECONDS = re.compile(r'por\s+(\d+(?:[.,]\d+)?)\s*(?:s|seg|segundos?)', re.I)
BIG_CUT = .25          # corte que remove mais que isso do clipe pede confirmação
SFX_SOFTER = .6


def seconds(text):
    text = text.replace(',', '.')
    if ':' in text:
        m, s = text.split(':', 1)
        return int(m) * 60 + float(s)
    return float(text)


def _span(text):
    m = RANGE.search(text)
    if not m:
        return None
    a, b = seconds(m.group(1)), seconds(m.group(2))
    return (a, b) if b > a else None


def _point(text):
    m = POINT.search(text)
    return seconds(m.group(1)) if m else None


def clauses(text):
    parts = re.split(r'\s*(?:;|\.\s+|\bdepois\b|\be também\b)\s*', text.strip())
    return [p for p in parts if p.strip()]


def interpret(text, duration):
    """Frase -> dict(changes, questions, undo). Cada mudança: op, args, text, destructive."""
    low = ' ' + text.lower().strip() + ' '
    changes, questions = [], []
    if re.search(r'\b(refaz|refazer)\b', low):
        return dict(changes=[], questions=[], undo=False, redo=True)
    if re.search(r'\b(desfaz|desfazer|volta atrás|volta a anterior)\b', low):
        return dict(changes=[], questions=[], undo=True)
    for raw in clauses(text):
        c = ' ' + raw.lower() + ' '
        span, point = _span(c), _point(c)
        slow = bool(re.search(r'câmera lenta|camera lenta|devagar|mais lento', c))
        fast = bool(re.search(r'acelera|mais rápido|mais rapido|rápido', c))
        if re.search(r'sem (?:os )?efeitos? sonoros?|tira (?:os )?(?:efeitos? sonoros?|sons)|sem sfx', c):
            changes.append(dict(op='limpar_sfx', args={}, text='Remover todos os efeitos sonoros.', destructive=False))
        elif re.search(r'efeitos? sonoros?.*(baix|menos|suav)|(baix|diminu|abaix).*efeitos? sonoros?', c):
            changes.append(dict(op='sfx_mais_baixo', args={}, text='Baixar o volume dos efeitos sonoros.', destructive=False))
        elif re.search(r'sem zoom|tira (?:o|os) zooms?|remove (?:o|os) zooms?', c):
            changes.append(dict(op='limpar_zooms', args={}, text='Remover os zooms.', destructive=False))
        elif re.search(r'replay|repete|repetir', c):
            if not span:
                questions.append('Qual trecho repetir? Diga algo como "replay de 12 a 15".')
            else:
                rate = .5 if slow else 1.0
                changes.append(dict(op='replay', args=dict(start=span[0], end=span[1], rate=rate),
                                    text=f'Repetir {span[0]:g}–{span[1]:g} s' + (' em câmera lenta' if slow else '') + ' logo após o trecho.', destructive=False))
        elif re.search(r'congela|congelar|pausa a imagem', c):
            at = point if point is not None else (span[0] if span else None)
            if at is None:
                questions.append('Em que instante congelar a imagem? Diga algo como "congela aos 14 s".')
            else:
                length = FOR_SECONDS.search(c)
                changes.append(dict(op='congelar', args=dict(at=at, duration=seconds(length.group(1)) if length else 1.0),
                                    text=f'Congelar a imagem aos {at:g} s.', destructive=False))
        elif slow or fast:
            if not span:
                questions.append('Em que trecho mudar a velocidade? Diga algo como "câmera lenta de 12 a 15".')
            else:
                rate = .5 if slow else 1.5
                changes.append(dict(op='velocidade', args=dict(start=span[0], end=span[1], rate=rate),
                                    text=f'Velocidade {rate:g}× entre {span[0]:g} e {span[1]:g} s.', destructive=False))
        elif re.search(r'\b(corta|cortar|remove|remover|tira|tirar|apaga|apagar)\b', c):
            if not span:
                questions.append('Qual trecho cortar? Diga algo como "corta de 8 a 11".')
            else:
                big = (span[1] - span[0]) / max(float(duration), 1) > BIG_CUT
                changes.append(dict(op='cortar', args=dict(start=span[0], end=span[1]),
                                    text=f'Cortar de {span[0]:g} a {span[1]:g} s.' + (' (corte grande)' if big else ''), destructive=big))
        else:
            questions.append(f'Não entendi "{raw.strip()[:60]}". Posso cortar, mudar velocidade, repetir (replay), congelar, tirar zoom ou baixar efeitos sonoros.')
    return dict(changes=changes, questions=questions, undo=False)


def apply_change(project, change):
    """Aplica UMA mudança tipada a uma cópia. Levanta ValueError (mensagem para o usuário) se o editor recusar."""
    p = copy.deepcopy(project or projectlib.empty())
    op, a = change['op'], change['args']
    n = lambda key: len(p.get(key) or []) + 1
    if op == 'limpar_sfx':
        p['sfx'] = []
    elif op == 'sfx_mais_baixo':
        p['sfx'] = [dict(e, volume=max(.05, round(e.get('volume', .6) * SFX_SOFTER, 3))) for e in p.get('sfx') or []]
    elif op == 'limpar_zooms':
        p['zooms'] = []
    elif op == 'cortar':
        p.setdefault('cuts', []).append(dict(start=a['start'], end=a['end']))
    elif op == 'velocidade':
        p.setdefault('speeds', []).append(dict(id=f'c{n("speeds")}', start=a['start'], end=a['end'], rate=a['rate']))
    elif op == 'replay':
        p.setdefault('replays', []).append(dict(id=f'cr{n("replays")}', start=a['start'], end=a['end'], rate=a['rate'], after=a['end']))
    elif op == 'congelar':
        p.setdefault('freezes', []).append(dict(id=f'cf{n("freezes")}', at=a['at'], duration=a['duration']))
    else:
        raise ValueError('Operação desconhecida.')
    return p


class Conversation:
    """Pilha de versões do projeto neste clipe. `say` aplica o que for seguro e segura o que pede confirmação."""

    def __init__(self, project, duration):
        self.duration = float(duration)
        self.versions = [dict(project=copy.deepcopy(project or projectlib.empty()), note='versão inicial')]
        self.pending = []
        self.undone = []

    @property
    def project(self):
        return self.versions[-1]['project']

    def say(self, text):
        parsed = interpret(text, self.duration)
        if parsed.get('redo'):
            return dict(self.redo(), pergunta=[])
        if parsed['undo']:
            return dict(self.undo(), pergunta=[])
        applied, rejected, held = [], [], []
        for change in parsed['changes']:
            if change['destructive']:
                held.append(change)
                continue
            self._try(change, applied, rejected)
        self.pending = held
        return dict(aplicado=[c['text'] for c in applied], recusado=rejected, aguardando_confirmacao=[c['text'] for c in held],
                    pergunta=parsed['questions'], versao=len(self.versions) - 1)

    def confirm(self):
        applied, rejected = [], []
        for change in self.pending:
            self._try(change, applied, rejected)
        self.pending = []
        return dict(aplicado=[c['text'] for c in applied], recusado=rejected, versao=len(self.versions) - 1)

    def undo(self):
        if len(self.versions) <= 1:
            return dict(aplicado=[], recusado=['Não há o que desfazer.'], versao=0)
        gone = self.versions.pop()
        self.undone.append(gone)
        return dict(aplicado=['Desfeito: ' + gone['note']], recusado=[], versao=len(self.versions) - 1)

    def redo(self):
        if not self.undone:
            return dict(aplicado=[], recusado=['Não há o que refazer.'], versao=len(self.versions) - 1)
        back = self.undone.pop()
        self.versions.append(back)
        return dict(aplicado=['Refeito: ' + back['note']], recusado=[], versao=len(self.versions) - 1)

    def _try(self, change, applied, rejected):
        try:
            raw = apply_change(self.project, change)
            cleaned = projectlib.clean(raw, self.duration)
        except ValueError as exc:
            rejected.append(f'{change["text"]} — o editor recusou: {exc}')
            return
        self.versions.append(dict(project=cleaned, note=change['text']))
        self.undone = []        # uma nova mudança encerra o ramo desfeito
        applied.append(change)
