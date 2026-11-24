"""Checagem antes de gravar: o que vai falhar (ou ficar lento) se a live começar agora.

Cada item: id, level ('ok' | 'aviso' | 'erro'), title, detail, action (opcional: onde corrigir).
Nada aqui altera dados; só lê perfil, ferramentas, disco e a capacidade medida pelo engine.
"""
import json

from . import deps,media
from .engine import whisper_plan


def _item(id,level,title,detail,action=None):
    item=dict(id=id,level=level,title=title,detail=detail)
    if action:item['action']=action
    return item


def webcam(profile):
    if profile.get('content_mode','live')!='live':
        return _item('webcam','ok','Webcam','Este perfil é de vídeo/podcast; a webcam não é necessária.')
    if profile.get('camera_rect'):
        return _item('webcam','ok','Webcam marcada','O layout de live (câmera + jogo) e a leitura de reações estão disponíveis.')
    return _item('webcam','aviso','Webcam não marcada',
                 'Sem a webcam marcada, as prévias e as exportações de live falham e os cortes saem sem a leitura do rosto. '
                 'Marque em Ajustes → Webcam e quadro (dá para marcar depois que a primeira imagem da live chegar). '
                 'Depois de marcar, os pedaços já gravados são reanalisados.','settings:cam')


def transcription(profile,engine,devices=None):
    device,_=whisper_plan(profile,devices)
    if getattr(engine,'cuda_broken',False):device='cpu'
    model=profile.get('model','base')
    cap=engine.capacity()
    if device=='cuda':
        return _item('transcricao','ok','Transcrição na placa de vídeo',f'Modelo {model}. É o caminho mais rápido para acompanhar várias lives.')
    detail=f'Modelo {model} no processador. Em computadores mais antigos isso pode não acompanhar várias lives ao mesmo tempo.'
    level='aviso' if model not in ('tiny','base') else 'ok'
    if cap.get('rtf') is not None:
        detail+=f" Medido neste PC: {round(cap['rtf']*60)} s de transcrição por minuto de live"
        if cap['lives']>=1:detail+=f"; com {max(cap['lives'],1)} live(s) abertas seriam {round(cap['needed']*60)} s por minuto"
        detail+='.'
        if cap.get('ok') is False:level='aviso'
    else:
        detail+=' Ainda não há medição; ela aparece depois das primeiras transcrições.'
    if level=='aviso' and model not in ('tiny','base'):
        detail+=' Para várias lives, troque para o modelo tiny ou base em Ajustes antes de começar (mudar o modelo no meio faz reanalisar o que já foi gravado).'
    return _item('transcricao',level,'Transcrição no processador',detail,'settings:adv' if level=='aviso' else None)


def disk(store,profile,lives):
    free=media.free_bytes(store.root)/1024**3
    need=float(profile.get('min_free_gb',5))
    rows=store.rows('SELECT size FROM segments ORDER BY rowid DESC LIMIT 60')
    detail=f'{free:.1f} GB livres (reserva mínima do perfil: {need:g} GB).'
    if rows:
        per_min=sum(r['size'] for r in rows)/len(rows)/1024**2        # cada segmento tem 1 min
        hours=(free-need)/max(per_min*60*max(lives,1)/1024,0.001)
        detail+=f' Pelos pedaços já gravados (~{per_min:.0f} MB por minuto por live), cabem cerca de {max(hours,0):.1f} h com {max(lives,1)} live(s) ao mesmo tempo.'
    if free<need+1:return _item('disco','erro','Pouco espaço em disco',detail+' A análise e as exportações vão pausar.')
    if free<need+10:return _item('disco','aviso','Espaço em disco apertado',detail)
    return _item('disco','ok','Espaço em disco',detail)


def tools():
    status=media.tool_status();missing=[k for k,v in status.items() if not v]
    if missing:
        return _item('ferramentas','erro','Ferramentas ausentes',', '.join(missing)+' não encontrado(s). Rode o INSTALAR.bat de novo'+
                     (' — sem o streamlink não dá para capturar lives.' if 'streamlink' in missing else '.'),'tools')
    return _item('ferramentas','ok','Ferramentas','ffmpeg, ffprobe e streamlink encontrados.')


def dependencies():
    miss=deps.missing()
    if not miss:return None
    req=[d for d in miss if d['required']]
    return _item('dependencias','aviso' if req else 'ok','Pacotes ausentes' if req else 'Pacotes opcionais ausentes',' · '.join(d['message'] for d in miss),'tools')


def slots(capture,store):
    running=len(capture.state());limit=capture.limit()
    if running>=limit:
        return _item('limite','erro','Limite de lives atingido',f'{running} de {limit} lives em captura. Aumente em Adicionar → Lives em captura ou encerre uma.')
    return _item('limite','ok','Lives em captura',f'{running} de {limit} em captura agora; cabe mais {limit-running}.')


def _model_cached(name):
    """True se o modelo de voz já está no computador. None se o faster-whisper nem está instalado."""
    try:from faster_whisper.utils import download_model
    except ImportError:return None
    try:
        download_model(name,local_files_only=True)
        return True
    except Exception:return False


def _internet(host='huggingface.co',port=443,timeout=3.0):
    import socket
    try:
        socket.create_connection((host,port),timeout=timeout).close()
        return True
    except OSError:return False


def models(profile,cached=_model_cached,online=_internet):
    """Modelos de voz que o perfil vai usar: se ainda não foram baixados, a 1ª análise/exportação depende de internet."""
    wanted=[profile.get('model','base')]
    second=profile.get('second_pass','off')
    if second and second!='off' and second not in wanted:wanted.append(second)
    missing=[];unknown=False
    for name in wanted:
        state=cached(name)
        if state is None:unknown=True
        elif not state:missing.append(name)
    if unknown:return _item('modelos','erro','Reconhecimento de voz não instalado','O faster-whisper não foi encontrado. Rode o INSTALAR.bat de novo.','tools')
    if not missing:return _item('modelos','ok','Modelos de voz','Já estão no computador: '+', '.join(wanted)+'.')
    detail='Ainda não foram baixados: '+', '.join(missing)+'. O primeiro uso baixa o modelo (de dezenas a centenas de MB, conforme o tamanho).'
    if online():return _item('modelos','aviso','Modelo de voz será baixado',detail+' A internet respondeu; a análise espera o download terminar.')
    return _item('modelos','erro','Modelo de voz ausente e sem internet',detail+' Sem internet agora a análise e a legenda precisa não conseguem começar.')


def delivery(profile):
    from pathlib import Path
    folder=profile.get('delivery_folder') or ''
    if not folder:return None
    try:exists=Path(folder).is_dir()
    except OSError:exists=False
    if exists:return _item('entrega','ok','Pasta de entrega','A pasta existe; os cortes prontos serão copiados para ela.')
    return _item('entrega','aviso','Pasta de entrega não encontrada',
                 'Os cortes ficam guardados e entram na pasta quando ela aparecer. Se for do Google Drive para computador, abra o aplicativo do Drive.','settings:deliver')


def estimate(store,engine):
    """Quanto custa uma hora de conteúdo neste PC, a partir do que já foi medido. Nada medido = nenhum item (sem chute)."""
    parts=[]
    rows=store.rows('SELECT size FROM segments ORDER BY rowid DESC LIMIT 60')
    if rows:parts.append(f"cada hora de live ocupa cerca de {sum(r['size'] for r in rows)/len(rows)/1024**2*60/1024:.1f} GB")
    try:rtf=engine.capacity().get('rtf')
    except Exception:rtf=None
    if rtf:parts.append(f'a transcrição de uma hora leva cerca de {rtf*60:.0f} min')
    ratios=[]
    for row in store.rows("SELECT data FROM candidates WHERE status='done' AND data LIKE '%\"render\"%' ORDER BY created DESC LIMIT 30"):
        try:ratios.append(float(json.loads(row['data'])['render']['ratio']))
        except (KeyError,TypeError,ValueError):continue
    if ratios:
        ratios.sort();parts.append(f'exportar um corte leva cerca de {ratios[len(ratios)//2]:.1f}× a duração dele (mediana de {len(ratios)})')
    if not parts:return None
    return _item('estimativa','ok','Estimativa neste computador','Pelo que já foi medido aqui: '+'; '.join(parts)+'. É média, não garantia.')


def run(store,engine,capture,streamer_id,devices=None):
    profile=store.streamer(streamer_id)['profile']
    lives=len(capture.state())+1
    checks=[tools(),dependencies(),slots(capture,store),webcam(profile),transcription(profile,engine,devices),models(profile),disk(store,profile,lives),delivery(profile),estimate(store,engine)]
    checks=[c for c in checks if c]
    worst='erro' if any(c['level']=='erro' for c in checks) else 'aviso' if any(c['level']=='aviso' for c in checks) else 'ok'
    return dict(level=worst,checks=checks)
