"""Ranking explicavel de momentos. Pontuacao heuristica, nao probabilidade de viralizar."""
import math
import re
import unicodedata
from collections import Counter

from .intelligence import classify_moment,narrative_scores,priority_bonus,text_evidence


def normal(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', str(text).casefold())
                   if unicodedata.category(c) != 'Mn')
    return ' '.join(re.findall(r'\w+', text))


REACTIONS = ('meu deus', 'nao acredito', 'que isso', 'caraca', 'caramba', 'impossivel',
             'inacreditavel', 'que susto', 'ta maluco', 'voce viu', 'olha isso',
             'no way', 'oh my god', 'what the', 'insane')
PLAYS = ('ganhei', 'ganhamos', 'vitoria', 'clutch', 'headshot', 'matei', 'eliminei',
         'consegui', 'perdemos', 'ganhando', 'ultimo', 'victory', 'win')
HUMOR = ('kkkk', 'hahaha', 'morri de rir', 'que vergonha', 'trolei', 'troll',
         'bugou', 'do nada', 'nao e possivel', 'olha esse cara')
TENSION = ('cuidado', 'corre', 'vai vai', 'calma', 'socorro', 'atras', 'ultimo',
           'agora', 'quase', 'nao nao', 'espera')
OUTCOMES = ('deu certo', 'nao deu', 'acabou', 'morri', 'perdi', 'ganhei',
            'consegui', 'foi', 'era isso', 'pronto')
STORIES = ('eu acho', 'na minha opiniao', 'o problema', 'a verdade', 'aconteceu',
           'quando eu', 'por que', 'porque', 'aprendi', 'percebi', 'o segredo',
           'nao sabia', 'ninguem')


def hits(text, terms):
    padded = ' ' + normal(text) + ' '
    return [term for term in terms if ' '+term+' ' in padded]


def limpar(segments, length):
    clean = []
    for seg in segments:
        try:
            a, b = float(seg['start']), float(seg['end'])
            text = ' '.join(str(seg['text']).split())
            if not (math.isfinite(a) and math.isfinite(b)) or b <= a or not text:
                continue
            a, b = max(0, a), min(length, b)
            if b > a:
                clean.append(dict(seg, start=a, end=b, text=text))
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(clean, key=lambda s: s['start'])


def coverage(segments, start, end):
    total, cursor = 0.0, start
    for seg in segments:
        a, b = max(start, seg['start']), min(end, seg['end'])
        if b > max(a, cursor):
            total += b-max(a, cursor)
            cursor = b
    return total/max(.1, end-start)


def frases_alinhadas(segments):
    result = []
    for seg in segments:
        words = []
        for word in seg.get('words') or []:
            try:
                a, b = float(word['start']), float(word['end'])
                text = str(word['word']).strip()
                if math.isfinite(a) and math.isfinite(b) and b > a and text:
                    words.append({'start': a, 'end': b, 'word': text})
            except (ValueError, KeyError, TypeError):
                continue
        if not words:
            result.append(seg)
            continue
        group = []
        for word in sorted(words, key=lambda w:w['start']):
            if group and word['start']-group[-1]['end'] > .6:
                result.append({'start':group[0]['start'],'end':group[-1]['end'],
                               'text':' '.join(w['word'] for w in group),'words':group})
                group=[]
            group.append(word)
            if len(group)>=8 or re.search(r'[.!?]$',word['word']):
                result.append({'start':group[0]['start'],'end':group[-1]['end'],
                               'text':' '.join(w['word'] for w in group),'words':group})
                group=[]
        if group:
            result.append({'start':group[0]['start'],'end':group[-1]['end'],
                           'text':' '.join(w['word'] for w in group),'words':group})
    return result


def fallback_candidates(segments,length,signals,focus,max_candidates,priority,clip_format,
                        editorial_style,content_mode):
    """Evita uma mesa vazia sem fingir que conversa neutra e highlight forte.

    Os candidatos ficam explicitamente marcados como exploratorios, recebem
    pontuacao baixa e continuam dependendo da revisao humana.
    """
    target=32 if clip_format=='short' else 55
    limit=55 if clip_format=='short' else 88
    windows=[]
    for index,center in enumerate(segments):
        midpoint=(center['start']+center['end'])/2
        if focus and not focus[0] <= midpoint < focus[1]:continue
        start=max(0,center['start']-1);end=min(length,center['end']+.7)
        left=index-1;right=index+1
        while end-start<target and (left>=0 or right<len(segments)):
            before=segments[left] if left>=0 else None;after=segments[right] if right<len(segments) else None
            before_gap=start-before['end'] if before else 999
            after_gap=after['start']-end if after else 999
            if before and before_gap<=after_gap and end-max(0,before['start']-1)<=limit:
                start=max(0,before['start']-1);left-=1
            elif after and min(length,after['end']+.7)-start<=limit:
                end=min(length,after['end']+.7);right+=1
            else:break
        windows.append((round(start,2),round(end,2)))
    candidates=[]
    for start,end in sorted(set(windows)):
        included=[s for s in segments if s['start']<end and s['end']>start]
        text=' '.join(s['text'] for s in included);words=normal(text).split()
        if len(words)<10 or end-start<10:continue
        occupied=coverage(included,start,end);pivot=start+(end-start)*.48
        early=' '.join(s['text'] for s in included if s['start']<pivot)
        late=' '.join(s['text'] for s in included if s['end']>=pivot)
        audio=[p for p in signals.get('audio',[]) if start<=p['time']<end]
        motion=[p for p in signals.get('motion',[]) if start<=p['time']<end]
        behavior=[p for p in signals.get('behavior',[]) if start<=p['time']<end]
        chat=[p for p in signals.get('chat',[]) if start<=p['time']<end]
        evidence=text_evidence(text)
        has_outcome=bool(evidence['desfecho'])
        corroborated=any(abs(a['time']-p['time'])<=2.5 for a in audio for p in motion+behavior+chat)
        crescendo=max((p['strength'] for p in audio if p['time']>=pivot),default=0)>=1.1
        boundary=any(s['start']<start<s['end'] or s['start']<end<s['end'] for s in included)
        narrative=narrative_scores(early,late,occupied,crescendo=crescendo,
                                   corroborated=corroborated,boundary_warning=boundary,
                                   has_outcome=has_outcome)
        semantic=sum(bool(evidence[k]) for k in ('opiniao','historia','educacional','emocional','surpresa','humor'))
        punctuation=bool(re.search(r'[!?]',text))
        rhythm=min(1.5,len(words)/max(1,end-start)/2.5)
        score=1.2+occupied*1.6+min(1.4,max((p['strength'] for p in audio),default=0)*.5)
        score+=min(1.4,semantic*.45)+.5*punctuation+.7*corroborated+.5*rhythm
        moment=classify_moment(evidence,behavior=behavior if corroborated else [],
                               chat=chat if corroborated else [],crescendo=crescendo,
                               content_mode=content_mode)
        if max(moment['scores'].values(),default=0)<=0:
            moment={'type':'exploratorio','label':'Candidato exploratório · revise',
                    'confidence':.28,'scores':moment['scores']}
        else:
            moment['confidence']=min(.49,moment['confidence'])
        reasons=['Candidato exploratório: há fala completa, mas faltou evidência para classificá-lo como momento forte. Exige revisão humana.']
        if semantic:reasons.append('Há uma mudança de assunto ou pista editorial que merece revisão humana.')
        if audio:reasons.append('Existe variação de energia no áudio; pode ser voz, jogo ou música.')
        if corroborated:reasons.append('Áudio e mudança visual/comportamental ocorreram próximos.')
        reasons.append('Confiança limitada: não publique automaticamente sem assistir ao contexto.')
        candidates.append({'start':start,'end':end,'score':round(score,2),'transcript':text,
            'reasons':reasons,'components':{'candidato_exploratorio':round(score,3)},
            'speech_ratio':round(occupied,3),'boundary_warning':boundary,'priority':priority,
            'selection_version':'v6.8-comportamento-multimodal-narrativa',
            'moment_type':moment['type'],'moment_label':moment['label'],
            'moment_confidence':moment['confidence'],'moment_scores':moment['scores'],
            'narrative':narrative,'behavior_evidence':[], 'fallback':True,'low_confidence':True,
            'learned_weights':{},'clip_format':clip_format,'editorial_style':editorial_style,
            'content_mode':content_mode})
    candidates.sort(key=lambda c:(-c['score'],-c['narrative']['historia_completa'],c['start']))
    result=[]
    for candidate in candidates:
        if any(max(0,min(candidate['end'],x['end'])-max(candidate['start'],x['start'])) /
               min(candidate['end']-candidate['start'],x['end']-x['start'])>.5 for x in result):continue
        result.append(candidate)
        if len(result)>=min(2,max_candidates):break
    return result


def rank(segments, length, signals=None, priority='equilibrio', focus=None, max_candidates=3,
         learned_weights=None,clip_format='short',editorial_style='clean',content_mode='live'):
    length = float(length)
    if not math.isfinite(length) or length < 10:
        return []
    segments = limpar(frases_alinhadas(limpar(segments, length)), length)
    signals = signals or {}
    learned_weights = learned_weights or {}
    min_duration,max_duration,target_duration=(12,42,24) if clip_format=='short' else (25,88,48)
    candidates = []
    windows = []
    for i, first in enumerate(segments):
        start = max(0, first['start']-1.5)
        endings = [s['end']+.6 for s in segments[i:] if min_duration <= s['end']+.6-start <= max_duration]
        if not endings:
            endings = [min(length, start+target_duration)]
        for finish in endings:
            end = min(length, finish)
            windows.append((start, end))
    # Reacoes sem frase reconhecida tambem podem virar candidatas, com duas modalidades.
    for audio in signals.get('audio', []):
        if audio['strength'] >= 1.2 and any(abs(audio['time']-m['time']) <= 2 and
                                           m['strength'] >= 1 for m in signals.get('motion', [])):
            end = min(length,audio['time']+12)
            start = max(0,min(audio['time']-6,end-12))
            windows.append((start,end))
    # Chat e rosto apenas abrem uma janela quando outra modalidade confirma.
    for point in signals.get('chat', []):
        corroborated=any(abs(point['time']-p['time'])<=3 for key in ('audio','motion','facial','behavior')
                         for p in signals.get(key,[]))
        if point['strength']>=1 and corroborated:
            windows.append((max(0,point['time']-12),min(length,point['time']+8)))
    for point in signals.get('behavior', []):
        corroborated=any(abs(point['time']-p['time'])<=2.5 for key in ('audio','motion','chat')
                         for p in signals.get(key,[]))
        if point.get('strength',0)>=1 and point.get('confidence',0)>=.55 and corroborated:
            windows.append((max(0,point['time']-10),min(length,point['time']+9)))
    for start, end in sorted(set(windows)):
            if focus and not focus[0] <= (start+end)/2 < focus[1]:
                continue
            if end-start < 10:
                continue
            included = [s for s in segments if s['start'] < end and s['end'] > start]
            text = ' '.join((' '.join(w['word'] for w in s['words']
                                      if w['start'] < end and w['end'] > start)
                             if s.get('words') else s['text']) for s in included)
            words = normal(text).split()
            evidence=text_evidence(text)
            react, plays = hits(text, REACTIONS), hits(text, PLAYS)
            humor = hits(text, HUMOR)
            stories = hits(text, STORIES)
            laughs = bool(re.search(r'\b(?:k{3,}|(?:ha){3,}|(?:he){3,}|risos|risada)\b', normal(text)))
            pivot=start+(end-start)*.48
            early_text=' '.join(s['text'] for s in included if s['start'] < pivot)
            late_text=' '.join(s['text'] for s in included if s['end'] >= pivot)
            tension=hits(early_text,TENSION)
            outcomes=hits(late_text,OUTCOMES)
            late_payoff=bool(outcomes or hits(late_text,PLAYS) or hits(late_text,REACTIONS) or
                             hits(late_text,HUMOR) or re.search(r'\b(?:k{3,}|(?:ha){3,}|risos|risada)\b',normal(late_text)))
            setup_payoff=bool(tension and late_payoff)
            # Considera picos somente proximos de fala; audio pode vir do jogo/musica.
            def near_speech(point):
                return any(s['start']-1 <= point['time'] <= s['end']+1 for s in included)
            audio = [p for p in signals.get('audio', []) if start <= p['time'] < end and near_speech(p)]
            motion = [p for p in signals.get('motion', []) if start <= p['time'] < end]
            facial = [p for p in signals.get('facial', []) if start <= p['time'] < end]
            behavior = [p for p in signals.get('behavior', []) if start <= p['time'] < end]
            chat = [p for p in signals.get('chat', []) if start <= p['time'] < end]
            coincide = any(abs(a['time']-m['time']) <= 2 for a in audio for m in motion)
            facial_confirmed=any(abs(f['time']-p['time'])<=2 for f in facial for p in (audio+motion+chat))
            chat_confirmed=any(abs(c['time']-p['time'])<=3 for c in chat for p in (audio+motion+facial+behavior))
            behavior_confirmed=[b for b in behavior if b.get('confidence',0)>=.55 and
                any(abs(b['time']-p['time'])<=2.5 for p in (audio+motion+chat))]
            raw_audio = [p for p in signals.get('audio', []) if start <= p['time'] < end]
            # Evento visual da tela só vale quando coincide com fala ou áudio (clarão pode ser tela de carregamento); corte de cena nunca vale.
            visual = [p for p in signals.get('visual', []) if start <= p['time'] < end and p.get('kind') in ('flash', 'rajada')
                      and any(abs(p['time']-q['time']) <= 3 for q in raw_audio+audio)]
            early_audio=[p['strength'] for p in raw_audio if p['time'] < pivot]
            late_audio=[p['strength'] for p in raw_audio if p['time'] >= pivot]
            crescendo=max(late_audio,default=0) >= max(1.0,max(early_audio,default=0)+.35)
            nonverbal = any(a['strength'] >= 1.2 and abs(a['time']-m['time']) <= 2 and
                            m['strength'] >= 1 for a in raw_audio for m in motion)
            if len(words) < 8 and not nonverbal:
                continue
            if nonverbal:
                audio = raw_audio
                coincide = True
            occupied = coverage(included, start, end)
            repeated = sum(n-1 for n in Counter(normal(s['text']) for s in included).values())/max(1,len(included))
            reaction_weight = 6 if priority == 'reacoes' else 3 if priority == 'jogadas' else 4.5
            play_weight = 6 if priority == 'jogadas' else 2 if priority == 'reacoes' else 4
            moment=classify_moment(evidence,laughs=laughs,behavior=behavior_confirmed,
                                   chat=chat if chat_confirmed else [],crescendo=crescendo,
                                   setup_payoff=setup_payoff,content_mode=content_mode)
            narrative=narrative_scores(early_text,late_text,occupied,crescendo=crescendo,
                                       corroborated=bool(coincide or facial_confirmed or chat_confirmed or behavior_confirmed),
                                       boundary_warning=any(s['start'] < end < s['end'] for s in included),
                                       has_outcome=bool(outcomes))
            parts = {'reacao_na_fala': min(3,len(react))*reaction_weight,
                     'jogada_na_fala': min(3,len(plays))*play_weight,
                     'humor_na_fala': min(2,len(humor))*3.5,
                     'risada_na_transcricao': 4 if laughs else 0,
                     'preparacao_e_desfecho': 5 if setup_payoff else 0,
                     'opiniao_na_fala': min(3,len(evidence['opiniao']))*3.4,
                     'historia_pessoal': min(3,len(evidence['historia']))*3.4,
                     'explicacao_util': min(3,len(evidence['educacional']))*3.6,
                     'reflexao_sensivel': min(3,len(evidence['emocional']))*3.2,
                     'opiniao_ou_historia': min(3,len(stories))*2.2 if content_mode=='video' else 0,
                     'variacao_audio': min(3, max((p['strength'] for p in audio),default=0))*1.5,
                     'crescendo_audio': 2.5 if crescendo else 0,
                     'evento_visual': min(3,max((p['strength'] for p in visual),default=0))*1.5,
                     'movimento_webcam': min(3,max((p['strength'] for p in motion),default=0))*.7,
                     'coincidencia_audio_webcam': 4 if coincide else 0,
                     'movimento_facial_breve': min(3,max((p['strength'] for p in facial),default=0))*1.2 if facial_confirmed else 0,
                     'comportamento_observavel': min(3,max((p['strength']*p.get('confidence',.5)
                                                           for p in behavior_confirmed),default=0))*2.0,
                     'reacao_chat': min(3,max((p['strength'] for p in chat),default=0))*1.8 if chat_confirmed else 0,
                     'estrutura_narrativa': narrative['historia_completa']*.42,
                     'afinidade_perfil': priority_bonus(priority,moment['type']),
                     'cobertura_fala': occupied*2,
                     'penalidade_silencio': -max(0,.4-occupied)*12,
                     'penalidade_repeticao': -repeated*8,
                     'ajuste_duracao': -abs((end-start)-target_duration)*.045}
            if editorial_style=='funny':parts['humor_na_fala']*=1.2;parts['risada_na_transcricao']*=1.2
            if editorial_style=='gameplay':parts['jogada_na_fala']*=1.18;parts['crescendo_audio']*=1.12;parts['evento_visual']*=1.3
            if editorial_style=='reaction':parts['reacao_na_fala']*=1.18;parts['comportamento_observavel']*=1.15
            if editorial_style=='podcast':parts['opiniao_na_fala']*=1.15;parts['historia_pessoal']*=1.15;parts['cobertura_fala']*=1.1
            if editorial_style=='interview':parts['opiniao_na_fala']*=1.12;parts['explicacao_util']*=1.12;parts['estrutura_narrativa']*=1.12
            if editorial_style=='hype':parts['variacao_audio']*=1.18;parts['crescendo_audio']*=1.2;parts['reacao_chat']*=1.12
            if editorial_style=='creative':parts['reacao_chat']*=1.12;parts['movimento_facial_breve']*=1.12;parts['comportamento_observavel']*=1.12
            if editorial_style=='storytelling':parts['historia_pessoal']*=1.2;parts['estrutura_narrativa']*=1.18;parts['preparacao_e_desfecho']*=1.15
            if editorial_style=='educational':parts['explicacao_util']*=1.22;parts['cobertura_fala']*=1.12;parts['estrutura_narrativa']*=1.08
            if editorial_style=='commentary':parts['opiniao_na_fala']*=1.2;parts['estrutura_narrativa']*=1.15;parts['cobertura_fala']*=1.08
            if editorial_style=='meme':parts['humor_na_fala']*=1.22;parts['risada_na_transcricao']*=1.18;parts['reacao_na_fala']*=1.12
            if editorial_style=='cinematic':parts['estrutura_narrativa']*=1.18;parts['crescendo_audio']*=1.12;parts['preparacao_e_desfecho']*=1.15
            # Preferências são aprendidas somente a partir das decisões deste
            # streamer e ficam limitadas para não apagar as regras de segurança.
            for name,value in list(parts.items()):
                if value>0:parts[name]=value*max(.75,min(1.30,float(learned_weights.get(name,1))))
            semantic_signal=any(evidence[k] for k in ('opiniao','historia','educacional','emocional','surpresa'))
            if not (react or plays or humor or laughs or setup_payoff or coincide or facial_confirmed or chat_confirmed or
                    behavior_confirmed or (semantic_signal and len(words)>=12)):
                # Conversa neutra nao e declarada highlight automaticamente.
                continue
            reasons = []
            if react: reasons.append('Expressoes de reacao: '+', '.join(react))
            if plays: reasons.append('Pistas de jogada na fala: '+', '.join(plays))
            if humor: reasons.append('Pistas de humor ou situação inesperada: '+', '.join(humor))
            if laughs: reasons.append('Risada indicada no texto da transcricao')
            if setup_payoff: reasons.append('Preparação e desfecho aparecem no mesmo contexto')
            if stories and content_mode=='video':reasons.append('Pista de opinião, explicação ou história: '+', '.join(stories))
            for key,label in (('opiniao','Opinião ou argumento'),('historia','História pessoal'),
                              ('educacional','Explicação ou aprendizado'),('emocional','Reflexão sensível'),
                              ('surpresa','Acontecimento inesperado')):
                if evidence[key]:reasons.append(label+': '+', '.join(evidence[key]))
            if audio: reasons.append('Variacao de energia no audio (pode ser jogo ou musica)')
            if crescendo: reasons.append('A energia do áudio cresce perto do desfecho')
            if motion: reasons.append('Movimento na regiao marcada como webcam (nao identifica emocao)')
            if coincide: reasons.append('Variacao de audio e movimento ocorreram a ate 2s de distancia')
            if facial_confirmed: reasons.append('Movimento facial breve confirmado por outra pista (não classifica emoção)')
            if behavior_confirmed:
                labels=[]
                for item in sorted(behavior_confirmed,key=lambda row:-row['strength']):
                    label=item.get('label') or item.get('cue') or 'movimento facial'
                    if label not in labels:labels.append(label)
                reasons.append('Movimentos observáveis confirmados por outro sinal: '+', '.join(labels[:3]))
            if chat_confirmed: reasons.append('Pico de mensagens/emotes no chat confirmado por áudio, fala ou vídeo')
            reasons.append('Estrutura: gancho %.1f · preparação %.1f · clímax %.1f · encerramento %.1f' %
                           (narrative['gancho'],narrative['preparacao'],narrative['climax'],narrative['encerramento']))
            if learned_weights: reasons.append('Preferências aprendidas com aprovações e rejeições deste streamer')
            truncated = any(s['start'] < end < s['end'] for s in included)
            if truncated: reasons.append('Limite do corte pode interromper fala; revise o final')
            candidates.append({'start': round(start,2), 'end': round(end,2),
                'score': round(sum(parts.values()),2), 'transcript': text,
                'reasons': reasons, 'components': {k:round(v,3) for k,v in parts.items()},
                'speech_ratio': round(occupied,3), 'boundary_warning': truncated,
                'priority': priority, 'selection_version': 'v6.8-comportamento-multimodal-narrativa',
                'moment_type':moment['type'],'moment_label':moment['label'],
                'moment_confidence':moment['confidence'],'moment_scores':moment['scores'],
                'narrative':narrative,
                'behavior_evidence':behavior_confirmed,
                'learned_weights': learned_weights,'clip_format':clip_format,'editorial_style':editorial_style,
                'content_mode':content_mode})
    candidates.sort(key=lambda c: (-c['score'], c['boundary_warning'], c['start'], c['end']))
    diverse = []
    for candidate in candidates:
        if candidate['score'] <= 0:
            continue
        if any(max(0,min(candidate['end'],x['end'])-max(candidate['start'],x['start'])) /
               min(candidate['end']-candidate['start'],x['end']-x['start']) > .5 for x in diverse):
            continue
        diverse.append(candidate)
        if len(diverse) >= max_candidates:
            break
    if not diverse and focus:
        return fallback_candidates(segments,length,signals,focus,max_candidates,priority,clip_format,
                                   editorial_style,content_mode)
    return diverse


def choose(segments, length, signals=None, priority='equilibrio'):
    ranked = rank(segments, length, signals, priority)
    return ranked[0] if ranked else None
