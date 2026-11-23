"""Revisão editorial explicável. Informa riscos; não substitui decisão jurídica."""
import json
from pathlib import Path


def source_info(session_path):
    path=Path(session_path)/'fonte.json'
    if not path.is_file():return {}
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):return {}


def audit(candidate,profile,source=None):
    source=source or {}
    components=candidate.get('components',{})
    transcript=' '.join(str(candidate.get('transcript','')).split())
    checks=[]
    def add(key,label,status,detail):checks.append(dict(key=key,label=label,status=status,detail=detail))
    story=bool(components.get('preparacao_e_desfecho') or
               (components.get('reacao_na_fala') and len(transcript.split())>=10))
    add('story','História completa','ok' if story else 'warn',
        'Gancho, contexto e desfecho detectados.' if story else 'Confira se o corte faz sentido para quem não viu a live.')
    boundary=bool(candidate.get('boundary_warning'))
    add('fidelity','Fidelidade ao contexto','warn' if boundary else 'ok',
        'Existe fala atravessando um limite; revise sem mudar o sentido.' if boundary else
        'Nenhuma fala atravessando os limites foi detectada.')
    add('captions','Legendas','ok' if transcript else 'block',
        'Transcrição disponível; nomes, gramática e nuances ainda exigem revisão humana.' if transcript else
        'Não há transcrição suficiente para uma legenda fiel.')
    add('speakers','Falantes','warn',
        'Identificação automática de falantes ainda não é confiável; use nome/símbolo e cor, nunca só cor.')
    credited=bool(source.get('url') and source.get('title'))
    add('credits','Créditos da fonte','ok' if credited else 'warn',
        'Link e título da transmissão serão incluídos na entrega.' if credited else
        'Preencha ou confira link e título da transmissão antes de publicar.')
    policy=profile.get('permission_policy','review')
    add('rights','Política do streamer','block' if policy=='blocked' else 'ok' if policy=='allowed' else 'warn',
        {'blocked':'Exportação bloqueada pelo perfil editorial.',
         'allowed':'Perfil marcado como permitido; políticas externas ainda se aplicam.',
         'review':'Autorização/política precisa ser conferida antes da publicação.'}[policy])
    style=profile.get('editorial_style','clean')
    transformed=style in ('funny','gameplay','reaction','podcast','interview','hype','creative',
                          'storytelling','educational','commentary','meme','cinematic')
    add('originality','Valor editorial','ok' if transformed else 'warn',
        'Preset prevê transformação editorial além do corte simples.' if transformed else
        'Edição limpa preserva o momento; confirme se há transformação suficiente para a plataforma.')
    serious=any(term in transcript.casefold() for term in ('eu acho','minha opinião','serio','sério','denúncia','acus'))
    if serious:add('nuance','Nuance ou tema sério','warn','Revisão humana obrigatória: não simplifique nem dramatize esta fala.')
    blocked=any(item['status']=='block' for item in checks)
    warnings=sum(item['status']=='warn' for item in checks)
    return dict(status='block' if blocked else 'review' if warnings else 'ready',checks=checks,
                requires_review=blocked or warnings>0,source=source,
                principle='Valorizar o criador, preservar a intenção e acrescentar valor sem distorcer.')
