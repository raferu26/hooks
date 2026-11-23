"""Decisões profissionais de edição, determinísticas e reversíveis."""
from copy import deepcopy
import math
import re
import unicodedata

from . import safety as _safety


# `pace` é só o rótulo mostrado ao revisor. `breath` (margem de respiro ao encurtar
# pausas) e o look de cada estilo são parâmetros reais usados na edição e no render.
EDITOR_PRESETS = {
    'clean': dict(label='Limpo', zoom=False, zoom_max=1.05, spacing=9, breath=.22,
                  silence=False, silence_gap=1.8, silence_remove=.7, pace='calmo'),
    'gameplay': dict(label='Gameplay', zoom=True, zoom_max=1.08, spacing=7, breath=.14,
                     silence=True, silence_gap=1.45, silence_remove=.65, pace='rápido'),
    'reaction': dict(label='Reação', zoom=True, zoom_max=1.11, spacing=5.5, breath=.16,
                     silence=False, silence_gap=1.8, silence_remove=.55, pace='expressivo'),
    'podcast': dict(label='Podcast', zoom=True, zoom_max=1.055, spacing=10, breath=.22,
                    silence=True, silence_gap=1.25, silence_remove=1.15, pace='conversacional', cadence=1.07),
    'interview': dict(label='Entrevista', zoom=True, zoom_max=1.045, spacing=12, breath=.24,
                      silence=True, silence_gap=1.5, silence_remove=.9, pace='natural', cadence=1.06),
    'hype': dict(label='Hype', zoom=True, zoom_max=1.12, spacing=4.5, breath=.12,
                 silence=True, silence_gap=1.05, silence_remove=.55, pace='intenso', cadence=1.11),
    'creative': dict(label='Criativo', zoom=True, zoom_max=1.10, spacing=5.5, breath=.16,
                     silence=True, silence_gap=1.3, silence_remove=.75, pace='dinâmico', cadence=1.09),
    'storytelling': dict(label='Storytelling', zoom=True, zoom_max=1.06, spacing=10, breath=.26,
                         silence=True, silence_gap=1.55, silence_remove=.7, pace='narrativo', cadence=1.06),
    'educational': dict(label='Educacional', zoom=True, zoom_max=1.045, spacing=13, breath=.24,
                        silence=True, silence_gap=1.45, silence_remove=.7, pace='didático', cadence=1.06),
    'commentary': dict(label='Comentário', zoom=True, zoom_max=1.06, spacing=9, breath=.18,
                       silence=True, silence_gap=1.35, silence_remove=.7, pace='argumentativo', cadence=1.08),
    'meme': dict(label='Meme', zoom=True, zoom_max=1.13, spacing=4.5, breath=.12,
                 silence=True, silence_gap=1.1, silence_remove=.6, pace='cômico rápido', cadence=1.12),
    'cinematic': dict(label='Cinemático', zoom=False, zoom_max=1.04, spacing=14, breath=.28,
                      silence=False, silence_gap=2, silence_remove=.5, pace='dramático'),
    'funny': dict(label='Momentos engraçados', zoom=True, zoom_max=1.08, spacing=6, breath=.16,
                  silence=True, silence_gap=1.35, silence_remove=.65, pace='cômico', cadence=1.08),
}

# Identidade visual de cada estilo. `curve`: formato do punch de zoom (veja motion.py);
# `push`: avanço lento contínuo (zoom final, só quando o usuário mantém o zoom automático);
# `grade`: correção de cor leve, aplicada no quadro vertical inteiro antes das legendas;
# `caption`: estilo de legenda usado quando o perfil está em "Automático".
# As intensidades de cor são escolhas de projeto (cerca de 65% das amostras antigas do
# painel); ajuste aqui se preferir mais ou menos contraste.
LOOKS = {
    'clean': dict(curve='smooth', push=None, caption='clean', grade=None),
    'gameplay': dict(curve='snap', push=None, caption='impact',
                     grade=dict(contrast=1.06, saturation=1.12, sharpen=.3)),
    'reaction': dict(curve='pop', push=None, caption='dynamic',
                     grade=dict(contrast=1.03, saturation=1.06)),
    'podcast': dict(curve='smooth', push=None, caption='clean',
                    grade=dict(contrast=1.03, saturation=.9)),
    'interview': dict(curve='smooth', push=None, caption='minimal',
                      grade=dict(contrast=1.05, saturation=.85)),
    'hype': dict(curve='beat', push=None, caption='impact',
                 grade=dict(contrast=1.11, saturation=1.28, sharpen=.4)),
    'creative': dict(curve='pop', push=None, caption='pop',
                     grade=dict(contrast=1.07, saturation=1.18)),
    'storytelling': dict(curve='smooth', push=1.035, caption='clean',
                         grade=dict(contrast=1.05, saturation=.98)),
    'educational': dict(curve='smooth', push=None, caption='box',
                        grade=dict(contrast=1.03, saturation=.92)),
    'commentary': dict(curve='snap', push=None, caption='dynamic',
                       grade=dict(contrast=1.06, saturation=1.02)),
    'meme': dict(curve='beat', push=None, caption='impact',
                 grade=dict(contrast=1.1, saturation=1.25)),
    'cinematic': dict(curve='smooth', push=1.05, caption='minimal',
                      grade=dict(contrast=1.12, saturation=.82, brightness=-.02, vignette=True)),
    'funny': dict(curve='pop', push=None, caption='dynamic',
                  grade=dict(contrast=1.04, saturation=1.12)),
}
FILLERS = {'a','ah','ai','eh','e','hm','hmm','tipo','ne','né','assim','entao','então'}


def preset_for(profile=None):
    name=str((profile or {}).get('editorial_style','clean'))
    return name,dict(EDITOR_PRESETS.get(name,EDITOR_PRESETS['clean']))


def look_for(profile=None):
    """Look do estilo escolhido; `auto_grade` desligado remove só a correção de cor."""
    name,_=preset_for(profile)
    look=deepcopy(LOOKS.get(name,LOOKS['clean']))
    if profile is not None and not profile.get('auto_grade',True):look['grade']=None
    return look


def look_of_plan(plan):
    """Look gravado no plano; planos antigos (v3) herdam o look do próprio estilo."""
    look=(plan or {}).get('look')
    if isinstance(look,dict):return look
    return deepcopy(LOOKS.get((plan or {}).get('preset','clean'),LOOKS['clean']))


def grade_filters(grade):
    """Cadeia de filtros FFmpeg da correção de cor (vazia se não houver)."""
    if not grade:return ''
    parts=[];contrast=float(grade.get('contrast',1));saturation=float(grade.get('saturation',1))
    brightness=float(grade.get('brightness',0))
    if (contrast,saturation,brightness)!=(1.,1.,0.):
        parts.append(f'eq=contrast={contrast:g}:saturation={saturation:g}:brightness={brightness:g}')
    sharpen=float(grade.get('sharpen',0))
    if sharpen>0:parts.append(f'unsharp=5:5:{min(1.0,sharpen):g}:5:5:0')
    if grade.get('vignette'):parts.append('vignette=PI/5')
    from . import grade as colorlib
    extra=colorlib.filters(grade)
    if extra:parts.append(extra)
    return ','.join(parts)


def _plain(value):
    value=unicodedata.normalize('NFKD',str(value).lower())
    return ''.join(char for char in value if not unicodedata.combining(char))


def _words(transcript,start,end):
    result=[]
    for segment in transcript or []:
        for word in segment.get('words') or []:
            try:a,b=float(word['start']),float(word['end'])
            except (KeyError,TypeError,ValueError):continue
            text=' '.join(str(word.get('word','')).split())
            if text and math.isfinite(a+b) and b>a and b>start and a<end:
                normalized=re.sub(r'[^a-z0-9à-ÿ]+','',_plain(text))
                result.append({'start':max(start,a),'end':min(end,b),'text':text,'normal':normalized})
    return sorted(result,key=lambda row:(row['start'],row['end']))


def _decision(kind,start,end,enabled,reason,label,confidence=.8,requires_review=False,extra=None):
    item={'id':f'{kind}:{start:.3f}:{end:.3f}','kind':kind,'start':round(start,3),'end':round(end,3),
          'enabled':bool(enabled),'label':label,'reason':reason,'confidence':round(float(confidence),3),
          'requires_review':bool(requires_review)}
    if extra:item.update(extra)
    return item


def _safe_silences(transcript,start,end,preset,enabled):
    words=_words(transcript,start,end);result=[]
    for left,right in zip(words,words[1:]):
        gap=right['start']-left['end']
        if gap<preset['silence_gap']:continue
        breath=float(preset.get('breath',.18));a=left['end']+breath;b=min(right['start']-breath,a+preset['silence_remove'])
        if a-start<.75 or end-b<.75 or b-a<.25:continue
        result.append(_decision('silence',a-start,b-start,enabled,
            f'Pausa de {gap:.1f}s entre duas falas; preservadas margens de respiração.',
            'Encurtar pausa',min(.98,.62+gap*.1)))
        if len(result)>=6:break
    return result


SILENCE_POLICIES={
    # min: duração mínima do silêncio medido; residual: pausa que SEMPRE fica; edge_only: só mexe no começo e no fim do corte
    'bordas':dict(min=.8,residual=.35,edge_only=True),
    'pausas_longas':dict(min=1.5,residual=.55,edge_only=False),
    'dinamica':dict(min=.95,residual=.35,edge_only=False)}
SILENCE_PROTECT_MARGIN=.5      # nenhum corte de pausa chega a menos que isto de um trecho protegido


def _audio_silences(silences,start,end,policy_name,enabled,protected_spans=()):
    """Decisões de encurtar pausa a partir do silêncio MEDIDO no áudio (modo sem transcrição, P05).

    Conservador por padrão: política `pausas_longas`, pausa residual preservada, margem de 0,75 s nas pontas do corte,
    nada perto de trecho protegido e, se a medida não for confiável (jogo/música altos), a decisão nasce desligada
    e pede revisão. Silêncio não é falta de conteúdo: o revisor pode ligar ou desligar cada decisão."""
    policy=SILENCE_POLICIES.get(policy_name,SILENCE_POLICIES['pausas_longas']);result=[]
    for item in silences or []:
        try:a,b=float(item['start']),float(item['end'])
        except (KeyError,TypeError,ValueError):continue
        if b<=start or a>=end:continue
        a,b=max(a,start),min(b,end)
        if b-a<policy['min']:continue
        if policy['edge_only'] and not (a-start<1.5 or end-b<1.5):continue
        left=a+policy['residual']/2;right=b-policy['residual']/2
        if left-start<.75 and not policy['edge_only']:continue
        if end-right<.75 and not policy['edge_only']:continue
        if right-left<.25:continue
        if any(left<hi+SILENCE_PROTECT_MARGIN and right>lo-SILENCE_PROTECT_MARGIN for lo,hi in protected_spans):continue
        reliable=bool(item.get('confiavel',True))
        result.append(_decision('silence',left-start,right-start,enabled and reliable,
            f'Silêncio medido de {b-a:.1f}s ({item.get("method","áudio")}); pausa residual de {policy["residual"]:.2f}s preservada.'
            +('' if reliable else ' Medida pouco confiável (áudio alto ao fundo): decisão desligada, confira.'),
            'Encurtar pausa',.7 if reliable else .4,requires_review=not reliable,
            extra={'origin':'medida_de_audio','method':item.get('method',''),'policy':policy_name}))
        if len(result)>=6:break
    return result


def _num(value):
    try:return math.isfinite(float(value))
    except (TypeError,ValueError):return False


def _without_speech(silences,speech,pad=.2):
    """Tira de cada silêncio medido os trechos em que uma legenda indica fala (com folga `pad`); parte que sobra < 0,3 s some."""
    result=[]
    for item in silences or []:
        try:pieces=[(float(item['start']),float(item['end']))]
        except (KeyError,TypeError,ValueError):continue
        for lo,hi in speech:
            lo-=pad;hi+=pad;rest=[]
            for a,b in pieces:
                if hi<=a or lo>=b:rest.append((a,b));continue
                if lo>a:rest.append((a,lo))
                if hi<b:rest.append((hi,b))
            pieces=rest
        result.extend(dict(item,start=a,end=b) for a,b in pieces if b-a>=.3)
    return result


REPLAY_MODES={'off':None,'normal':1.0,'lento':.5}
REPLAY_BEFORE,REPLAY_AFTER=1.5,2.5          # ação antes do ponto marcado e resultado depois (segundos de fonte)
REPLAY_MAX_ADDED=8.0                        # tempo máximo que o replay acrescenta ao corte
CLIP_MAX={'short':58.0,'narrative':88.0}    # mesmos limites de markers.LIMITS
REPLAY_MAX_SHARE=.25                        # e no máximo esta fração da duração do corte


def _auto_replay(candidate,profile,decisions,start,end):
    """Replay automático (P10): no máximo UM por corte, só para momento que a pessoa marcou (nunca deduzido de movimento).

    Pega a ação e o desfecho em volta do marcador, repete logo depois do trecho original, em câmera lenta e mudo por padrão
    (modo `lento`) ou em velocidade normal com o áudio original (`normal`). Recusa, com o motivo gravado, quando não cabe no
    limite do corte, quando passa por uma pausa que será cortada ou quando a pessoa já definiu replays no projeto."""
    mode=str(profile.get('auto_replay','off') or 'off')
    rate=REPLAY_MODES.get(mode)
    if rate is None:return []
    def refused(reason,at=0.0):
        return [dict(_decision('replay',at,at+.01,False,'Recusado: '+reason,'Replay do momento marcado',.5),rate=rate,after=at+.01,mute=True,refused=True)]
    marks=[float(m['time']) for m in candidate.get('markers') or [] if _num(m.get('time')) and start<=float(m['time'])<=end]
    if not marks:return refused('o replay só entra em corte com um momento marcado por você.')
    if (candidate.get('project') or {}).get('replays'):return refused('o projeto já tem replay definido por você.')
    mark=min(marks)-start
    a=round(max(0.0,mark-REPLAY_BEFORE),3);b=round(min(end-start,mark+REPLAY_AFTER),3)
    if b-a<1.0:return refused('não há trecho suficiente em volta do marcador.',a)
    added=(b-a)/rate
    high=CLIP_MAX.get(candidate.get('clip_format','short'),58.0)
    if added>REPLAY_MAX_ADDED or added>REPLAY_MAX_SHARE*(end-start):return refused(f'o replay acrescentaria {added:.1f}s e passaria do limite de {min(REPLAY_MAX_ADDED,REPLAY_MAX_SHARE*(end-start)):.1f}s.',a)
    removed=sum(min(end-start,float(d['end']))-max(0.0,float(d['start'])) for d in decisions if d.get('kind') in ('silence','repetition') and d.get('enabled'))
    if (end-start)-removed+added>high:return refused(f'o corte com o replay passaria de {high:g}s.',a)
    for item in decisions:
        if item.get('kind') in ('silence','repetition') and item.get('enabled') and item['start']<b and item['end']>a:
            return refused('o trecho do replay inclui uma pausa que será cortada; o replay repetiria a pausa.',a)
    mute=rate!=1.0
    return [dict(_decision('replay',a,b,True,
        f'Replay {"em câmera lenta ("+format(rate,"g")+"x) e mudo" if mute else "em velocidade normal, com o áudio original"} do momento marcado, logo depois do trecho original.',
        'Replay do momento marcado',1.0),rate=rate,after=b,mute=mute)]


def auto_replays(candidate):
    """Replays automáticos ligados, no formato do projeto (tempo do clipe). Se a pessoa definiu replays no projeto, os dela valem."""
    from .project import project_of
    if (project_of(candidate) or {}).get('replays'):return []
    plan=candidate.get('data',{}).get('edit_plan',{})
    shift=float(plan.get('source_start',candidate['start']))-float(candidate['start'])
    duration=float(candidate['end'])-float(candidate['start']);result=[]
    for item in decisions_for(candidate):
        if item.get('kind')!='replay' or not item.get('enabled') or item.get('refused'):continue
        a=max(0.0,float(item['start'])+shift);b=min(duration,float(item['end'])+shift)
        if b-a>=.4:result.append(dict(id=item['id'],start=round(a,3),end=round(b,3),rate=float(item.get('rate',.5)),
                                      after=round(min(duration,float(item.get('after',b))+shift),3),mute=bool(item.get('mute',True))))
    return result[:1]


def _safe_repetitions(transcript,start,end,enabled):
    words=_words(transcript,start,end);result=[];fillers={_plain(x) for x in FILLERS}
    for left,right in zip(words,words[1:]):
        if not left['normal'] or left['normal']!=right['normal'] or left['normal'] not in fillers:continue
        if right['start']-left['end']>.3 or left['end']-left['start']>.8:continue
        a=max(start,left['start']-.04);b=min(end,left['end']+.04)
        result.append(_decision('repetition',a-start,b-start,enabled,
            f'Repetição imediata do apoio de fala “{left["text"]}”; confira a naturalidade.',
            'Remover repetição curta',.72,requires_review=True))
        if len(result)>=4:break
    return result


# Orçamento de efeitos visuais por janela de 10 s: edição profissional é mais contida que a amadora.
EFFECT_BUDGET={'hype':3,'meme':3,'creative':3,'gameplay':3,'reaction':3,'funny':3,'cinematic':1,'clean':2}
BUDGET_WINDOW=10.0


def _habit_factor(habits,kind):
    try:value=float((habits or {}).get('effect_factor',{}).get(kind,1))
    except (TypeError,ValueError):return 1.0
    return max(.25,min(1.0,value))


def apply_budget(punches,decisions,duration,preset_name,preset,habits=None):
    """Limita efeitos por janela de 10 s e varia a força de zooms seguidos.

    Fica com as decisões de maior confiança; as demais continuam na lista, desligadas e com o motivo,
    para o revisor religar se quiser. Se você costuma apagar zooms, o limite diminui sozinho.
    """
    limit=max(1,round(EFFECT_BUDGET.get(preset_name,2)*_habit_factor(habits,'zoom')))
    visual=[d for d in decisions if d.get('kind') in ('zoom','overlay','sfx') and d.get('enabled')]
    kept=[]
    for item in sorted(visual,key=lambda d:(-float(d.get('confidence',.5)),d['start'])):
        window=max((sum(1 for k in kept+[item] if a<=k['start']<a+BUDGET_WINDOW)
                    for a in [item['start']-BUDGET_WINDOW*f for f in (0,.25,.5,.75,1)]),default=1)
        if window>limit:
            item['enabled']=False;item['budget']=True
            item['reason']=item['reason']+' Desligado pelo orçamento de efeitos (máximo '+str(limit)+' a cada 10 s).'
        else:kept.append(item)
    zooms=[d for d in decisions if d.get('kind')=='zoom' and d.get('enabled')]
    zooms.sort(key=lambda d:d['start']);ceiling=preset['zoom_max']+.02;by_id={p.get('decision_id'):p for p in punches}
    previous=None
    for item in zooms:
        value=float(item.get('zoom',1.05))
        if previous is not None and abs(value-previous)<.008:
            value=value-.012 if value+.012>ceiling else value+.012
            value=round(max(1.02,min(ceiling,value)),3);item['zoom']=value
            if item['id'] in by_id:by_id[item['id']]['zoom']=value
        previous=value
    return punches,decisions


def director_report(decisions,preset_name,limit=None,shielded=()):
    """Resumo do diretor (P22): o que entrou, o que foi recusado e por quê. Só lê as decisões; não muda nada."""
    refused=[];accepted={}
    for item in decisions:
        kind=item.get('kind','?')
        if item.get('enabled'):accepted[kind]=accepted.get(kind,0)+1
        else:refused.append(dict(kind=kind,at=round(float(item.get('start',0)),2),
                                 cause='orçamento' if item.get('budget') else 'proteção' if item.get('protected') else 'configuração' if 'Desligado:' in str(item.get('reason','')) else 'regra',
                                 reason=str(item.get('reason',''))[:240]))
    for item in shielded or []:refused.append(dict(kind='corte',at=None,cause='proteção',reason=str(item.get('motivo',''))[:240]))
    return dict(preset=preset_name,budget_per_window=limit,window_seconds=BUDGET_WINDOW,accepted=accepted,refused=refused[:40],
                refused_total=len(refused))


def plan_edits(candidate,signals,transcript=None,profile=None,habits=None,protected=None,protected_spans=None):
    """Planeja ritmo e efeitos; nenhuma decisão fica escondida do revisor."""
    profile=profile or candidate.get('profile') or {}
    preset_name,preset=preset_for(profile)
    start,end=float(candidate['start']),float(candidate['end'])
    visual=list(signals.get('motion',[]))+list(signals.get('behavior',[]));supported=[]
    for audio in signals.get('audio',[]):
        try:at=float(audio['time']);strength=float(audio['strength'])
        except (KeyError,TypeError,ValueError):continue
        if not (math.isfinite(at+strength) and start<=at<end and strength>=1.2):continue
        nearby=[point for point in visual if abs(float(point.get('time',-999))-at)<=1.5 and
                float(point.get('strength',0))>=1]
        if nearby:supported.append((audio,max(nearby,key=lambda point:float(point.get('strength',0)))))
    punches=[];decisions=[]
    zoom_enabled=bool(profile.get('auto_zoom',preset['zoom'])) and preset['zoom']
    for audio,visual_point in sorted(supported,key=lambda item:-float(item[0]['strength'])):
        relative=max(0,float(audio['time'])-start-.2)
        if any(abs(relative-point['start'])<preset['spacing'] for point in punches):continue
        confidence=float(visual_point.get('confidence',.65))
        zoom=min(preset['zoom_max'],1.035+max(0,float(audio['strength'])-1.2)*.02+
                 max(0,confidence-.55)*.05)
        point={'start':round(relative,3),'end':round(min(end-start,relative+.85),3),
               'zoom':round(zoom,3),'reason':'Áudio e mudança visual ocorreram juntos.'}
        decision=_decision('zoom',point['start'],point['end'],zoom_enabled,
            'Áudio e mudança visual se confirmaram; aproximação curta e centralizada.'+('' if zoom_enabled else ' Desligado: o estilo "'+preset_name+'" ou o perfil não usa zoom automático.'),
            'Aproximação sutil',confidence,extra={'zoom':point['zoom']})
        point['decision_id']=decision['id'];punches.append(point);decisions.append(decision)
        if len(punches)>=5:break
    if profile.get('auto_cadence',False) and preset.get('cadence') and transcript:
        from .agents import cadence_punches
        for point in cadence_punches(transcript,start,end,preset,existing=punches,zoom=preset['cadence']):
            decision=_decision('zoom',point['start'],point['end'],zoom_enabled,
                'Plano fechado na frase; alterna com o plano aberto para dar ritmo à fala.',
                'Plano fechado (ritmo)',.7,extra={'zoom':point['zoom']})
            point['decision_id']=decision['id'];punches.append(point);decisions.append(decision)
    silence_enabled=bool(profile.get('auto_silence',preset['silence'])) and preset['silence']
    measured=(signals.get('technical') or {}).get('silence')
    if transcript and _words(transcript,start,end):decisions.extend(_safe_silences(transcript,start,end,preset,silence_enabled))
    elif measured:
        # Sem tempo por palavra (por exemplo, legenda importada): a pausa vem do silêncio MEDIDO no áudio, e o que a legenda
        # indica como fala é descontado dela. Legenda é só texto com horário: não prova silêncio, mas marca onde há fala.
        spans=[(float(lo),float(hi)) for lo,hi in (protected_spans or candidate.get('protected') or [])]
        speech=[(float(x['start']),float(x['end'])) for x in transcript or [] if _num(x.get('start')) and _num(x.get('end'))]
        decisions.extend(_audio_silences(_without_speech(measured,speech),start,end,profile.get('silence_policy','pausas_longas'),
                                         bool(profile.get('auto_silence',True)),spans))
    decisions.extend(_safe_repetitions(transcript,start,end,bool(profile.get('auto_repetition',False))))
    decisions=_safety.filter_decisions(decisions,transcript,start,end) if transcript else decisions
    shielded=[]
    if protected:
        from .narrative_skill import filter_decisions as _protect
        decisions,shielded=_protect(decisions,protected,start)
    punches,decisions=apply_budget(punches,decisions,end-start,preset_name,preset,habits)
    decisions.extend(_auto_replay(candidate,profile,decisions,start,end))
    director=director_report(decisions,preset_name,max(1,round(EFFECT_BUDGET.get(preset_name,2)*_habit_factor(habits,'zoom'))),shielded)
    strongest=punches[0] if punches else None
    if strongest and profile.get('auto_sfx') and profile.get('sfx_path'):
        decisions.append(_decision('sfx',strongest['start'],strongest['end'],True,
            'Efeito fornecido pelo usuário no pico multimodal mais forte.','Efeito sonoro',.8,
            extra={'path':profile['sfx_path']}))
    if strongest and profile.get('auto_overlay') and profile.get('overlay_path'):
        decisions.append(_decision('overlay',strongest['start'],min(end-start,strongest['start']+1.5),True,
            'Imagem fornecida pelo usuário no pico multimodal mais forte.','Imagem ou meme',.8,
            extra={'path':profile['overlay_path']}))
    if profile.get('auto_music') and profile.get('music_authorized') and profile.get('music_path'):
        decisions.append(_decision('music',0,end-start,True,
            'Trilha marcada pelo usuário como autorizada; volume reduzido sob a voz.',
            'Música autorizada',1,extra={'path':profile['music_path'],'volume':profile.get('music_volume',.08)}))
    return {'version':4,'preset':preset_name,'preset_label':preset['label'],'pace':preset['pace'],
            'look':look_for(profile),
            'source_start':start,'punches':sorted(punches,key=lambda point:point['start']),
            'decisions':sorted(decisions,key=lambda item:(item['start'],item['kind'])),
            'protected_pauses':shielded,'director':director,
            'policy':'Cada decisão pode ser desligada. Efeitos reforçam o conteúdo; nunca criam um momento falso.'}


def _overrides(candidate):
    raw=candidate.get('data',{}).get('edit_overrides',{})
    return raw if isinstance(raw,dict) else {}


def decisions_for(candidate):
    plan=candidate.get('data',{}).get('edit_plan',{});overrides=_overrides(candidate);result=[]
    for item in plan.get('decisions',[]):
        value=dict(item)
        if value.get('id') in overrides:value['enabled']=bool(overrides[value['id']])
        result.append(value)
    return result


def punches_for(candidate):
    plan=candidate.get('data',{}).get('edit_plan',{});decisions={item['id']:item for item in decisions_for(candidate)}
    shift=float(plan.get('source_start',candidate['start']))-float(candidate['start'])
    duration=float(candidate['end'])-float(candidate['start']);result=[]
    for point in plan.get('punches',[]):
        decision=decisions.get(point.get('decision_id'))
        if decision is not None and not decision.get('enabled'):continue
        try:a=max(0,float(point['start'])+shift);b=min(duration,float(point['end'])+shift)
        except (KeyError,TypeError,ValueError):continue
        if b>a:result.append(dict(point,start=round(a,3),end=round(b,3)))
    from .project import project_of,zooms_of
    result.extend(zooms_of(project_of(candidate),duration))
    result.sort(key=lambda point:point['start'])
    return result


def cuts_for(candidate):
    duration=float(candidate['end'])-float(candidate['start']);result=[]
    for item in decisions_for(candidate):
        if item.get('kind') not in ('silence','repetition') or not item.get('enabled'):continue
        try:a=max(0,float(item['start']));b=min(duration,float(item['end']))
        except (KeyError,TypeError,ValueError):continue
        if b-a>=.08:result.append({'start':a,'end':b,'kind':item['kind'],'id':item['id']})
    from .project import cuts_of,project_of
    result.extend(item for item in cuts_of(project_of(candidate)) if item['end']-item['start']>=.08)
    result=[dict(item,start=max(0,item['start']),end=min(duration,item['end'])) for item in result]
    result.sort(key=lambda row:row['start']);merged=[]
    for item in result:
        if merged and item['start']<=merged[-1]['end']+.03:merged[-1]['end']=max(merged[-1]['end'],item['end'])
        else:merged.append(dict(item))
    return merged


def keep_intervals(duration,cuts):
    cursor=0.;result=[]
    for cut in cuts:
        if cut['start']>cursor+.04:result.append((cursor,cut['start']))
        cursor=max(cursor,cut['end'])
    if duration>cursor+.04:result.append((cursor,duration))
    return result


class Remap:
    """Tempo do clipe (antes dos cortes) -> tempo final: cortes, velocidade, congelamentos, replays e abertura (teaser).

    `speeds`: (início, fim, taxa). `freezes`: (instante, duração): a imagem para por `duração` segundos.
    `replays`: dicts (id, start, end, rate, after, mute): o trecho volta a aparecer logo depois de `after`.
    `pieces` guarda só a primeira ocorrência de cada instante (usada por `map`); `sequence` é a ordem real de saída,
    incluindo os replays (tuplas com um sexto campo: o dicionário do replay)."""

    def __init__(self,duration,cuts=(),speeds=(),lead=0.0,freezes=(),replays=()):
        self.cuts=[dict(c) for c in cuts];self.lead=float(lead);self.duration=float(duration)
        self.speeds=[(float(a),float(b),float(r)) for a,b,r in speeds]
        self.freezes=sorted((float(a),float(d)) for a,d in freezes)
        self.pieces=[];self.sequence=[];self.replays=[];cursor=0.0;pending=list(self.freezes)
        todo=[dict(r) for r in sorted(replays,key=lambda r:(float(r.get('after',r['end'])),float(r['start'])))]
        def emit_replays(upto,final=False):
            nonlocal cursor
            for item in list(todo):
                if not final and abs(float(item.get('after',item['end']))-upto)>1e-6:continue
                todo.remove(item)
                a=max(0.0,float(item['start']));b=min(self.duration,float(item['end']));rate=float(item.get('rate',1.0))
                if b-a<.2:continue
                row=dict(id=item.get('id'),start=a,end=b,rate=rate,mute=bool(item.get('mute',rate!=1.0)),out_start=cursor,after=float(item.get('after',item['end'])))
                cursor+=(b-a)/rate;row['out_end']=cursor
                self.replays.append(row);self.sequence.append((a,b,row['out_start'],rate,0.0,row))
        for a,b in keep_intervals(self.duration,self.cuts):
            replay_marks={float(r.get('after',r['end'])) for r in todo}
            marks=sorted({a,b}|{x for sa,sb,_ in self.speeds for x in (sa,sb) if a<x<b}|{t for t,_ in pending if a<t<b}
                         |{x for x in replay_marks if a<x<b})
            for x,y in zip(marks,marks[1:]):
                rate=next((r for sa,sb,r in self.speeds if sa<=(x+y)/2<sb),1.0)
                for t,d in [f for f in pending if abs(f[0]-x)<1e-9]:
                    # Congelamento: trecho de tamanho zero na fonte e `d` segundos na saída.
                    piece=(t,t,cursor,None,d);self.pieces.append(piece);self.sequence.append(piece);cursor+=d
                piece=(x,y,cursor,rate,0.0);self.pieces.append(piece);self.sequence.append(piece);cursor+=(y-x)/rate
                emit_replays(y)
            pending=[f for f in pending if not any(abs(f[0]-m)<1e-9 for m in marks)]
        emit_replays(0,final=True)
        self.length=cursor

    def map(self,value):
        value=float(value)
        for a,b,out,rate,hold in self.pieces:
            if rate is None:continue
            if value<a:return out+self.lead
            if value<=b:return out+(value-a)/rate+self.lead
        return self.length+self.lead

    def occurrences(self,value):
        """Todos os instantes de saída em que o instante `value` do clipe aparece (original e replays)."""
        value=float(value);result=[]
        for item in self.sequence:
            a,b,out,rate=item[:4]
            if rate is None or not a<=value<=b:continue
            result.append(round(out+(value-a)/rate+self.lead,6))
        return result


def remap_for(project,total,cuts,extra_replays=()):
    """(Remap, teaser, lead) a partir do projeto do clipe. Fonte única para o render, o editor e o plano."""
    teaser=None
    if project and project.get('teaser'):
        a=max(0.0,float(project['teaser']['start']));b=min(float(total),float(project['teaser']['end']))
        if b-a>=.8:teaser=(round(a,3),round(b,3))
    lead=(teaser[1]-teaser[0]) if teaser else 0.0
    project=project or {}
    remap=Remap(total,cuts,speeds=[(v['start'],v['end'],v['rate']) for v in project.get('speeds',[])],lead=lead,
                freezes=[(f['at'],f['duration']) for f in project.get('freezes',[])],replays=list(project.get('replays',[]))+list(extra_replays))
    return remap,teaser,lead


def timing_for(candidate):
    """Mapa de tempo (clipe ↔ vídeo final) do estado atual do corte. Usado pelo editor e gravado junto com cada
    prévia, para que uma prévia anterior continue navegável enquanto a nova é gerada."""
    from . import project as project_module
    length=float(candidate['end'])-float(candidate['start'])
    current=project_module.project_of(candidate) or project_module.empty()
    applied=cuts_for(candidate)
    auto=auto_replays(candidate)
    remap,_,lead=remap_for(current,length,applied,auto)
    return dict(cuts=[dict(start=round(c['start'],3),end=round(c['end'],3),kind=c.get('kind','manual')) for c in applied],
                lead=round(lead,3),
                speeds=[dict(start=v['start'],end=v['end'],rate=v['rate']) for v in current.get('speeds',[])],
                freezes=[dict(at=f['at'],duration=f['duration']) for f in current.get('freezes',[])],
                replays=current.get('replays') or auto,final_duration=round(lead+remap.length,2))


def _shift_time(value,cuts):
    if isinstance(cuts,Remap):return cuts.map(value)
    removed=0.
    for cut in cuts:
        if value>=cut['end']:removed+=cut['end']-cut['start']
        elif value>cut['start']:return cut['start']-removed
    return value-removed


def retime_transcript(transcript,start,end,cuts):
    result=[];gaps=getattr(cuts,'cuts',cuts)
    for segment in transcript or []:
        words=[]
        for word in segment.get('words') or []:
            try:a=max(start,float(word['start']));b=min(end,float(word['end']))
            except (KeyError,TypeError,ValueError):continue
            ra=a-start;rb=b-start
            if b<=a or any(ra>=c['start'] and rb<=c['end'] for c in gaps):continue
            words.append(dict(word,start=round(_shift_time(ra,cuts),3),end=round(_shift_time(rb,cuts),3)))
        try:sa=max(start,float(segment['start']))-start;sb=min(end,float(segment['end']))-start
        except (KeyError,TypeError,ValueError):continue
        if sb<=sa:continue
        breaks=sorted(r['after'] for r in getattr(cuts,'replays',[]) if r.get('after') is not None and sa<r['after']<sb)
        if breaks and not words:
            # Frase sem tempo por palavra que o replay interrompe: aparece até o ponto do replay e continua depois dele.
            # Sem isso a frase ficaria na tela durante todo o replay, mostrando texto de outro instante.
            edges=[sa]+breaks+[sb]
            for index,(x,y) in enumerate(zip(edges,edges[1:])):
                row=dict(segment,start=round(_shift_time(x+1e-6 if index else x,cuts),3),end=round(_shift_time(y,cuts),3),words=[])
                if row['end']>row['start']:result.append(row)
            continue
        row=dict(segment,start=round(_shift_time(sa,cuts),3),end=round(_shift_time(sb,cuts),3),words=words)
        if row['end']>row['start']:result.append(row)
    for replay in getattr(cuts,'replays',[]):
        result.extend(_replay_rows(transcript,start,end,replay,cuts.lead))
    result.sort(key=lambda r:r['start'])
    return result


def _replay_rows(transcript,start,end,replay,lead):
    """Palavras e frases que caem dentro de um replay, com os tempos da nova ocorrência (mesma conta de `Remap.map`)."""
    rows=[];ra,rb,rate,base=replay['start'],replay['end'],replay['rate'],replay['out_start']+lead
    def at(value):return base+(min(max(value,ra),rb)-ra)/rate
    for segment in transcript or []:
        try:sa=float(segment['start'])-start;sb=float(segment['end'])-start
        except (KeyError,TypeError,ValueError):continue
        if sb<=ra or sa>=rb:continue
        words=[]
        for word in segment.get('words') or []:
            try:wa=float(word['start'])-start;wb=float(word['end'])-start
            except (KeyError,TypeError,ValueError):continue
            if wb<=ra or wa>=rb:continue
            words.append(dict(word,start=round(at(wa),3),end=round(at(wb),3),replay=replay.get('id')))
        row=dict(segment,start=round(at(sa),3),end=round(at(sb),3),words=words,replay=replay.get('id'))
        if row['end']>row['start']+.04:rows.append(row)
    return rows


def retime_points(points,cuts):
    result=[]
    for point in points:
        value=dict(point,start=round(_shift_time(float(point['start']),cuts),3),
                   end=round(_shift_time(float(point['end']),cuts),3))
        if value['end']>value['start']+.04:result.append(value)
    return result


def effective_look(candidate):
    """Look do plano automático, com o estilo e a cor escolhidos à mão no editor."""
    from .project import project_of
    look=look_of_plan(candidate.get('data',{}).get('edit_plan',{}));project=project_of(candidate)
    if not project:return look
    look=deepcopy(look)
    if project.get('style'):
        look=deepcopy(LOOKS.get(project['style'],LOOKS['clean']))
        if not (candidate.get('profile') or {}).get('auto_grade',True):look['grade']=None
    grade=project.get('grade')
    if grade:look['grade']=dict(look.get('grade') or {},**grade)
    return look


def camera_zoom_filter(punches,fps,width=1080,height=640,curve='smooth',push=None,duration=None,supersample=None):
    """Zoom por quadro com curva própria em cada punch (veja motion.py)."""
    from .motion import zoompan_filter
    # Quadros grandes (vídeo vertical inteiro) usam supersample menor para não explodir o custo.
    sample=supersample or (2 if width*height<=1080*700 else 1.5)
    return zoompan_filter(punches,fps,width,height,curve=curve,push=(push,duration) if push and duration else None,
                          supersample=sample)
