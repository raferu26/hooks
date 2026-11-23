"""Captura independente com encerramento do pipe e proteção de disco."""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import os
import json
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlsplit

from . import atomic
from . import media
from .chat import TwitchChatCapture,twitch_channel

QUALITY_FALLBACKS={
    '480p':'480p,480p60,360p,720p,720p60,best',
    '720p':'720p,720p60,480p,480p60,best',
    '720p60':'720p60,720p,480p60,480p,best',
    '1080p':'1080p,1080p60,720p60,720p,480p60,480p,best',
    '1080p60':'1080p60,1080p,720p60,720p,480p60,480p,best',
    # Streamlink tenta cada nome na ordem. Assim 1440p só é escolhido quando
    # realmente existe; não fazemos upscale de uma live limitada a 1080p.
    '1440p':'1440p,1440p60,1080p60,1080p,720p60,720p,best',
    '1440p60':'1440p60,1440p,1080p60,1080p,720p60,720p,best',
    'best':'best',
}


def streamlink_options(url):
    # Algumas redes Windows anunciam uma rota IPv6 que encontra a live, mas
    # expira ao abrir os segmentos. As tentativas sao do proprio Streamlink e
    # nao duplicam sessoes nem arquivos no LiveClips.
    options=['--ipv4','--retry-open','3','--stream-segment-attempts','5','--http-timeout','20']
    if twitch_channel(url):options.append('--twitch-supported-codecs=h264,h265')
    return options


FAILURE_HINTS=(
    ('no playable streams','Não há transmissão no ar nesse link agora. A live pode ter acabado, ainda não ter começado, ser só para membros ou estar privada. Abra o link no navegador para conferir.'),
    ('unable to open url','Não consegui abrir o link. Confira se ele está completo e se a internet está funcionando.'),
    ('no plugin can handle url','O Hook’s não reconhece esse tipo de link. Use o link da live (YouTube, Twitch, Kick…), não o de um canal ou playlist.'),
    ('sign in','A plataforma pede login para essa live (idade, membros ou verificação anti-robô). Se a live é pública no navegador, atualize o streamlink.'),
    ('403','A plataforma recusou o acesso (403). Pode ser bloqueio temporário por muitos testes seguidos, ou o streamlink está desatualizado.'),
    ('429','A plataforma limitou os acessos (muitos testes seguidos). Espere alguns minutos e tente de novo.'),
)


def explain_failure(stdout,stderr):
    """Motivo real da falha do streamlink. Com --json o erro vem no STDOUT (o stderr costuma ficar vazio), por isso lemos os dois
    e traduzimos os casos comuns; o texto original continua no fim para diagnóstico."""
    raw=''
    try:
        data=__import__('json').loads(stdout or b'{}')
        raw=str(data.get('error') or '').strip()
    except (ValueError,TypeError,AttributeError):pass
    err=(stderr or b'').decode('utf-8',errors='replace')[-700:].strip()
    detail=' '.join(x for x in (raw,err) if x).strip()
    if not detail:return 'A plataforma não disponibilizou uma transmissão acessível e não informou o motivo.'
    low=detail.lower()
    for key,hint in FAILURE_HINTS:
        if key in low:return hint+' (Detalhe: '+detail[:300]+')'
    return detail[:700]


def inspect_url(url,quality='best',timeout=45):
    parsed=urlsplit(str(url))
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Cole o link público completo da live, começando com https://.')
    command=[media.tool('streamlink'),'--json',*streamlink_options(url),str(url)]
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    try:cp=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,creationflags=flags)
    except subprocess.TimeoutExpired:raise RuntimeError('O teste do link demorou demais. A plataforma pode exigir login ou verificação.')
    if cp.returncode:
        raise RuntimeError(explain_failure(cp.stdout,cp.stderr))
    try:data=__import__('json').loads(cp.stdout)
    except (ValueError,TypeError):raise RuntimeError('A plataforma respondeu sem uma lista válida de qualidades.')
    streams=data.get('streams') or {};available=[name for name in streams if name not in ('best','worst')]
    preferred=QUALITY_FALLBACKS.get(quality,'best').split(',')
    selected=next((name for name in preferred if name in streams),None)
    if selected in ('best','worst'):
        selected=(streams.get(selected) or {}).get('quality') or selected
    metadata=data.get('metadata') or {};plugin=data.get('plugin') or parsed.hostname
    warnings=[]
    if not available:warnings.append('Nenhuma qualidade nomeada foi informada.')
    if twitch_channel(url) and not os.environ.get('LIVECLIPS_TWITCH_TOKEN'):
        warnings.append('Vídeo disponível; chat ainda não conectado à conta Twitch.')
    return {'plugin':plugin,'author':metadata.get('author') or twitch_channel(url) or '',
            'title':metadata.get('title') or '','category':metadata.get('category') or '',
            'qualities':available,'selected':selected or 'indisponível','warnings':warnings,
            'chat_supported':bool(twitch_channel(url))}


class Capture:
    def __init__(self,store):
        self.store=store;self.guard=threading.RLock();self.current=None

    def state(self):
        with self.guard:
            return {'session':self.current['session'],'chat':self.current['chat'].status} if self.current else None

    def start(self,streamer_id,url,source_meta=None):
        parsed=urlsplit(str(url))
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Cole o link público completo da live, começando com https://.')
        with self.guard:
            if self.current:raise ValueError('Já existe uma captura aberta. Encerre-a antes de iniciar outra.')
            profile=self.store.streamer(streamer_id)['profile']
            media.require_space(self.store.root,profile['min_free_gb'],500*1024**2)
            streamlink=media.tool('streamlink');ffmpeg=media.tool('ffmpeg')
            name=dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')
            sid=self.store.new_session(streamer_id,name,closed=False)
            session=self.store.session(sid);source=Path(session['source'])
            meta=dict(source_meta or {});meta.setdefault('mode','live')
            meta.update(url=str(url),captured_at=dt.datetime.now().astimezone().isoformat())
            atomic.write_json(Path(session['path'])/'fonte.json',meta,indent=2)
            log=(Path(session['path'])/'captura.log').open('ab',buffering=0)
            producer=None;consumer=None
            flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            try:
                producer=subprocess.Popen([streamlink,*streamlink_options(url),'--stdout',url,QUALITY_FALLBACKS[profile['capture_quality']]],
                                          stdout=subprocess.PIPE,stderr=log,creationflags=flags)
                consumer=subprocess.Popen([ffmpeg,'-nostdin','-hide_banner','-loglevel','warning','-fflags','+genpts',
                    '-i','pipe:0','-map','0:v:0?','-map','0:a:0?','-c','copy','-f','segment','-segment_time','60',
                    '-segment_format','mpegts','-reset_timestamps','1',str(source/'segmento_%05d.ts')],
                    stdin=producer.stdout,stdout=log,stderr=log,creationflags=flags)
                producer.stdout.close()
                chat=TwitchChatCapture(url if meta.get('mode')=='live' else '',session['path']);chat.start()
                current=dict(session=sid,streamer=streamer_id,producer=producer,consumer=consumer,chat=chat,log=log,stopping=False,
                             min_gb=profile['min_free_gb'])
                self.current=current
                with self.store.connect(True) as c:
                    c.execute("UPDATE sessions SET status='capturing',closed=0 WHERE id=?",(sid,))
                threading.Thread(target=self.monitor,args=(current,),daemon=True).start()
                self.store.event('captura','Captura iniciada em '+self.store.streamer(streamer_id)['name']+'/'+name)
                return sid
            except Exception:
                if producer and producer.poll() is None:producer.terminate();producer.wait(timeout=10)
                if consumer and consumer.poll() is None:consumer.terminate();consumer.wait(timeout=10)
                log.close()
                with self.store.connect(True) as c:
                    c.execute("UPDATE sessions SET status='error',closed=1,error='Falha ao iniciar captura.' WHERE id=?",(sid,))
                raise

    def stop(self,reason='Captura encerrada pelo usuário.',error=False,auto=False):
        with self.guard:
            current=self.current
            if not current or current['stopping']:return
            current['stopping']=True;current['auto']=bool(auto)
        producer,consumer=current['producer'],current['consumer']
        failed=bool(error)
        try:
            if producer.poll() is None:
                producer.terminate()
                try:producer.wait(timeout=10)
                except subprocess.TimeoutExpired:producer.kill();producer.wait(timeout=5)
            # O FFmpeg recebe EOF e pode finalizar o último .ts.
            try:consumer.wait(timeout=15)
            except subprocess.TimeoutExpired:
                consumer.terminate()
                try:consumer.wait(timeout=5)
                except subprocess.TimeoutExpired:consumer.kill();consumer.wait(timeout=5)
            if error is None:failed=producer.returncode!=0 or consumer.returncode!=0
        except (OSError,subprocess.SubprocessError) as exc:
            failed=True;reason+=' Não foi possível finalizar normalmente: '+str(exc)
            for process in (producer,consumer):
                try:
                    if process.poll() is None:process.kill();process.wait(timeout=5)
                except (OSError,subprocess.SubprocessError):pass
        finally:
            current['chat'].stop();self.finish(current,reason,failed)

    def finish(self,current,message,error=False):
        with self.guard:
            if self.current is not current:return
            current['log'].close();self.current=None
            self.write_end(current,message,error)
            with self.store.connect(True) as c:
                c.execute('UPDATE sessions SET status=?,closed=1,error=? WHERE id=?',
                          ('capture_error' if error else 'idle',message if error else '',current['session']))
        self.store.event('captura',self.store.streamer(current['streamer'])['name']+' · '+message)

    def write_end(self,current,message,error):
        """Registra COMO a gravação terminou (você ou sozinha), para a tela poder avisar e oferecer retomar."""
        try:
            session=self.store.session(current['session'])
            codes=[current['producer'].returncode,current['consumer'].returncode]
            data=dict(at=dt.datetime.now().astimezone().isoformat(),by='automatico' if current.get('auto') else 'usuario',
                      reason=message,error=bool(error),codigos=codes)
            atomic.write_json(Path(session['path'])/'captura_fim.json',data)
        except Exception:pass

    def monitor(self,current):
        while True:
            with self.guard:
                if self.current is not current or current['stopping']:return
            if media.free_bytes(self.store.root)<current['min_gb']*1024**3:
                self.stop('Captura encerrada automaticamente por espaço baixo. Os arquivos foram preservados.',auto=True);return
            if current['consumer'].poll() is not None or current['producer'].poll() is not None:
                self.stop('A gravação parou sozinha: a live pode ter acabado ou a conexão caiu. Confira captura.log.',error=None,auto=True);return
            time.sleep(2)


class CaptureManager:
    """Uma captura independente por streamer, até cinco simultâneas."""
    def __init__(self,store):
        self.store=store;self.guard=threading.RLock();self.captures={}

    license=None

    def limit(self):
        mine=int(self.store.setting('capture_limit') or 5)
        return min(mine,self.license.max_lives()) if self.license is not None else mine

    def state(self):
        with self.guard:
            result=[]
            for streamer,capture in self.captures.items():
                current=capture.state()
                if current:
                    result.append(dict(current,streamer=streamer))
            return result

    def set_limit(self,value):
        value=int(value)
        if not 1<=value<=5:raise ValueError('Escolha um limite entre 1 e 5 lives.')
        with self.guard:
            if len(self.state())>value:
                raise ValueError('Encerre algumas capturas antes de reduzir esse limite. Nenhuma live foi interrompida.')
            self.store.setting('capture_limit',value)
        return value

    def inspect(self,url,streamer):
        profile=self.store.streamer(streamer)['profile']
        return inspect_url(url,profile['capture_quality'])

    def start(self,streamer,url,source_meta=None):
        with self.guard:
            active=self.state()
            if any(item['streamer']==streamer for item in active):
                raise ValueError('Este streamer já está sendo capturado. Os outros perfis continuam disponíveis.')
            if len(active)>=self.limit():
                raise ValueError('Limite de lives simultâneas atingido. Encerre uma captura ou ajuste o limite no painel.')
            capture=Capture(self.store)
            sid=capture.start(streamer,url,source_meta)
            self.captures[streamer]=capture
            return sid

    def stop(self,session,reason='Captura encerrada pelo usuário.'):
        with self.guard:
            matches=[]
            for cap in self.captures.values():
                current=cap.state()
                if current and current['session']==session:matches.append(cap)
        for cap in matches:cap.stop(reason)

    def stop_all(self,reason='Todas as capturas foram encerradas pelo usuário.'):
        with self.guard:active=[cap for cap in self.captures.values() if cap.state()]
        if active:
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda cap:cap.stop(reason),active))
