"""Serviço local do painel. Não hospeda na internet nem envia arquivos."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import threading
import time
from urllib.parse import urlparse,parse_qs

from . import atomic
from . import studio_api
from . import licensing
from . import syncaudio
from . import deps,__version__,agents,analytics,assets,brand,denoise,grade,learning,markers,media,music,ollama,safety,sfx,subtitles,support,variants
from . import engine as engine_module
from .captions import STYLE_NAMES,caption_terms,lines_from_transcript
from . import project as project_module
from .capture import CaptureManager
from .editorial import audit,source_info
from .engine import Engine
from .editing import plan_edits,cuts_for,EDITOR_PRESETS,remap_for,auto_replays,timing_for
from .recovery import create_backup
from .store import Store,REJECT_REASONS
from .timeline import build_timeline,plan,shifted_transcript


def _mtime(path):
    try:return path.stat().st_mtime_ns
    except OSError:return 0


def preview_info(item,data):
    """Estado da prévia para o editor. `ready`: a prévia é desta versão. `stale`: existe uma prévia anterior
    no disco, que continua tocando (marcada como desatualizada) enquanto a nova não fica pronta."""
    ready=item['preview_status']=='ready' and item['preview_version']==item['version']
    path=item.get('preview_path') or ''
    stale=bool(not ready and path and Path(path).is_file())
    info=dict(status=item['preview_status'],ready=ready,stale=stale,available=ready or stale,version=item['preview_version'] if (ready or stale) else 0)
    if stale and data.get('preview_timing'):info['timing']=data['preview_timing']
    return info


def quality_catalog():
    from .telemetry import MODES
    return [dict(id=k,label=v['label'],note=v['note']) for k,v in MODES.items()]


def friendly_error(exc):
    """Texto que a pessoa consegue entender: sem 'KeyError', sem '[Errno 13]'. O detalhe técnico fica no registro de erros."""
    import errno
    if isinstance(exc,KeyError):
        field=exc.args[0] if exc.args else ''
        return f'Faltou um dado nesta solicitação ({field}). Atualize a página e tente de novo.'
    if isinstance(exc,PermissionError):
        return 'O Windows negou o acesso'+(f' a {exc.filename}' if getattr(exc,'filename',None) else '')+'. Feche o arquivo se ele estiver aberto em outro programa.'
    if isinstance(exc,FileNotFoundError):
        return 'Arquivo ou pasta não encontrado'+(f': {exc.filename}' if getattr(exc,'filename',None) else '')+'.'
    if isinstance(exc,OSError) and getattr(exc,'errno',None)==errno.ENOSPC:
        return 'O disco está cheio. Libere espaço e tente de novo.'
    return str(exc)


class App:
    def __init__(self,root,legacy_root=None,worker=True):
        self.store=Store(root)
        try:support.setup_logging(self.store.root)
        except OSError:pass
        self.last_backup=''
        if worker:threading.Thread(target=self._auto_backup,daemon=True,name='backup-inicial').start()
        self.legacy_root=Path(legacy_root or root).resolve()
        self.engine=Engine(self.store);self.capture=CaptureManager(self.store)
        self.license=licensing.Licensing(self.store.root,Path(__file__).parent,__version__)
        self.engine.license=self.license;self.capture.license=self.license
        self.license.lives_provider=lambda:len(self.capture.state())
        if worker and self.license.enforced and self.license.data.get('device_token'):self.license.start()
        self.token=secrets.token_urlsafe(32)
        self.action_lock=threading.RLock()
        self.closing=False
        self.quit_callback=None
        self._facts={}
        if worker:self.engine.start()

    def legacy_sessions(self):
        folder=self.legacy_root/'segmentos'
        if not folder.is_dir():return []
        return [dict(name=p.name,count=sum(1 for _ in p.glob('segmento_*.ts')))
                for p in sorted(folder.iterdir(),reverse=True) if p.is_dir() and any(p.glob('segmento_*.ts'))]

    def activity(self):
        """O que o Hook’s está fazendo agora. Quem fecha a janela usa isto para decidir se encerra sozinho."""
        try:exporting=self.store.rows("SELECT COUNT(*) AS n FROM candidates WHERE status IN ('approved','exporting')")[0]['n']
        except Exception:exporting=0
        try:analyzing=bool(self.engine.state().get('busy'))
        except Exception:analyzing=False
        return dict(capturas=len(self.capture.state()),analisando=analyzing,exportando=int(exporting))

    def _auto_backup(self,every_s=6*3600):
        """Backup ao abrir, em segundo plano e só se o último automático tiver mais de 6 h (o painel não espera por isso)."""
        try:
            folder=self.store.root/'backups'
            recent=[p.stat().st_mtime for p in folder.glob('LiveClips-automatico-*.zip')] if folder.is_dir() else []
            if recent and time.time()-max(recent)<every_s:
                self.last_backup=str(max(folder.glob('LiveClips-automatico-*.zip'),key=lambda p:p.stat().st_mtime));return
            self.last_backup=str(create_backup(self.store.root,'automatico',keep=5))
        except (OSError,ValueError,sqlite3.Error) as exc:
            try:self.store.event('backup','Backup automático não concluído: '+str(exc))
            except Exception:pass

    def _session_facts(self,s,meta_file):
        """Números derivados dos trechos de uma sessão (linha do tempo, análise, resolução)."""
        meta=source_info(s['path'])
        rows=self.store.rows('SELECT seq,sha,duration,signature,status FROM segments WHERE session=? ORDER BY seq',(s['id'],))
        timeline=build_timeline(rows)
        analyzed_until=0.0
        for row in timeline:
            if row['status']!='done':break
            analyzed_until=row['end']
        wh=None
        if rows:
            try:
                signature=json.loads(rows[-1]['signature'])
                if len(signature)>=3 and int(signature[1])>0 and int(signature[2])>0:wh=(int(signature[1]),int(signature[2]))
            except (ValueError,TypeError,json.JSONDecodeError):pass
        return dict(source_url=meta.get('url',''),capture_end=self.capture_end(s),content_mode=meta.get('mode','live'),
                    reframe_mode=meta.get('reframe_mode','conservative'),registered=len(rows),
                    analyzed=sum(r['status']=='done' for r in rows),duration=round(timeline[-1]['end'],2) if timeline else 0,
                    analyzed_until=round(analyzed_until,3),breaks=sum(r['discontinuity'] for r in timeline),
                    waiting_next=bool(not s['closed'] and rows and rows[-1]['status']=='done'),
                    source_resolution=f'{wh[0]}×{wh[1]}' if wh else '',_wh=wh)

    def state(self):
        streamers=self.store.rows('SELECT * FROM streamers ORDER BY name')
        for s in streamers:s['profile']=json.loads(s['profile'])
        profiles={s['id']:s['profile'] for s in streamers}
        sessions=self.store.rows('SELECT * FROM sessions ORDER BY created DESC')
        running={c['session'] for c in self.capture.state()}
        aggregate={r['session']:(r['n'],r['done'],r['total'],r['last'],r['bytes']) for r in self.store.rows(
            "SELECT session,COUNT(*) AS n,SUM(status='done') AS done,ROUND(SUM(duration),3) AS total,MAX(seq) AS last,SUM(size) AS bytes "
            "FROM segments GROUP BY session")}
        review_stats=self.store.review_stats()
        live_ids={s['id'] for s in sessions}
        for stale in [k for k in self._facts if k not in live_ids]:self._facts.pop(stale,None)
        for s in sessions:
            meta_file=Path(s['path'])/'fonte.json';end_file=Path(s['path'])/'captura_fim.json'
            s['capture_running']=s['id'] in running
            s['files']=0;s['last_file_age_s']=None
            if not s['closed']:
                try:
                    files=list(Path(s['source']).glob('segmento_*.ts'))
                    s['files']=len(files)
                    if files:s['last_file_age_s']=round(max(0.0,time.time()-max(f.stat().st_mtime for f in files)),1)
                except OSError:pass
            # Uma sessão encerrada não muda sozinha: os números derivados ficam guardados enquanto o conjunto
            # de trechos (contagem, analisados, duração, tamanho) e os dois arquivos de apoio forem os mesmos.
            key=(aggregate.get(s['id']),_mtime(meta_file),_mtime(end_file))
            cached=self._facts.get(s['id'])
            if s['closed'] and cached and cached[0]==key:facts=cached[1]
            else:
                facts=self._session_facts(s,meta_file)
                if s['closed']:self._facts[s['id']]=(key,facts)
                else:self._facts.pop(s['id'],None)
            s.update({k:v for k,v in facts.items() if not k.startswith('_')})
            s['review']=review_stats.get(s['id']) or dict(accepted=0,rejected=0,pending=0,reasons={},rate=None)
            s['source_available']=Path(s['source']).exists()
            s['completed']=bool(s['closed'] and facts['registered'] and facts['analyzed']==facts['registered'])
            s['camera_source_resolution']='';s['camera_upscale']=False
            wh=facts['_wh']
            if wh:
                rect=profiles.get(s['streamer'],{}).get('camera_rect')
                if rect:
                    try:
                        camera_width=max(1,round(wh[0]*float(rect[2])));camera_height=max(1,round(wh[1]*float(rect[3])))
                        s['camera_source_resolution']=f'{camera_width}×{camera_height}'
                        s['camera_upscale']=camera_width<1080 or camera_height<640
                    except (ValueError,TypeError,IndexError):pass
        candidates=self.store.panel_candidates(500)
        for row in candidates:
            row['has_preview']=row['preview_status']=='ready' and row['preview_version']==row['version']
            row['has_export']=row['status']=='done' and bool(row['export_path'])
        tools=media.tool_status();backup_folder=self.store.root/'backups'
        backups=[dict(name=path.name,size=path.stat().st_size,created=path.stat().st_mtime)
                 for path in sorted(backup_folder.glob('*.zip'),key=lambda item:item.stat().st_mtime,reverse=True)[:10]] if backup_folder.is_dir() else []
        return dict(reject_reasons=REJECT_REASONS,version=__version__,root=str(self.store.root),streamers=streamers,sessions=sessions,
                    candidates=candidates,legacy=self.legacy_sessions(),paused=self.store.setting('paused'),
                    worker=self.engine.state(),engine_mode=self.engine.mode(),camera_suggestions={x['id']:self.store.setting('camera_sugestao:'+x['id']) for x in streamers if self.store.setting('camera_sugestao:'+x['id'])},export_workers=self.engine.export_workers(),captures=self.capture.state(),capture_limit=self.capture.limit(),license=self.license.public(),activity=self.activity(),free_gb=round(media.free_bytes(self.store.root)/1024**3,2),
                    tools={name:bool(path) for name,path in tools.items()},tool_paths=tools,dependencies=deps.missing(),
                    brand_fonts=brand.fonts(self.store.root),luts=grade.luts(self.store.root),
                    regeneration=self.store.setting('regeneration') or {},backups=backups,
                    learning={r['id']:self.store.learning_summary(r['id']) for r in streamers},
                    events=self.store.rows('SELECT * FROM events ORDER BY id DESC LIMIT 8'))

    def engine_report(self):
        """Linhas para o pacote de diagnóstico: modo, pistas, capacidade medida e situação de cada sessão."""
        lines=[]
        try:
            w=self.engine.state();cap=w.get('capacity') or {}
            lines.append(f"Modo de trabalho: {w.get('mode')} · exportações simultâneas: {self.engine.export_workers()}")
            lines.append(f"Capacidade medida: {cap.get('rtf')} s de transcrição por s de live · lives abertas: {cap.get('lives')} · acompanha: {cap.get('ok')}")
            for lane in w.get('lanes',[]):lines.append(f"  pista {lane['lane']}: {lane.get('stage')} — {lane.get('detail')} ({lane.get('elapsed_s')} s)")
            for row in self.store.rows('SELECT id,name,status,closed,enabled FROM sessions ORDER BY created DESC LIMIT 12'):
                segs=self.store.segments(row['id'])
                lines.append(f"  sessão {row['name']}: {row['status']} · {'encerrada' if row['closed'] else 'aberta'} · {len(segs)} segmentos · "
                             f"{sum(1 for x in segs if x['status']=='done')} analisados")
        except Exception as exc:lines.append('Relatório das pistas indisponível: '+str(exc)[:120])
        return lines

    def license_action(self,path,payload):
        """Fora do action_lock: falam com a rede e não devem travar o resto do painel."""
        L=self.license
        try:
            if path=='/api/license/login':return dict(license=L.login(str(payload['email']).strip(),str(payload['password'])))
            if path=='/api/license/register':
                return dict(license=L.register(str(payload['name']).strip(),str(payload['email']).strip(),str(payload['password']),bool(payload.get('accept_terms'))))
            if path=='/api/license/forgot':L.forgot(str(payload['email']).strip());return dict(ok=True)
            if path=='/api/license/logout':
                if self.capture.state():raise ValueError('Encerre as capturas em andamento antes de sair da conta.')
                L.logout();return dict(license=L.public())
            if path=='/api/license/refresh':
                ok,message=L.sync(len(self.capture.state()))
                return dict(ok=ok,message=message,license=L.public())
        except ConnectionError as exc:raise ValueError(str(exc)) from exc
        raise ValueError('Ação de assinatura desconhecida.')

    def action(self,path,payload):
        if path=='/api/app/quit':
            if self.quit_callback is None:raise RuntimeError('Encerrar por aqui só funciona quando o Hook’s foi aberto pelo atalho ou pelo ABRIR_LIVECLIPS.bat.')
            activity=self.activity();self.quit_callback();return dict(ok=True,activity=activity)
        if path.startswith('/api/license/'):
            if self.closing:raise RuntimeError('O aplicativo está encerrando.')
            return self.license_action(path,payload)
        if path.startswith('/api/music/') or path in ('/api/image/remove','/api/image/variants','/api/image/batch','/api/system/check','/api/denoise/status','/api/denoise/fetch','/api/support/bundle'):
            if self.closing:raise RuntimeError('O aplicativo está encerrando.')
            return self.music_action(path,payload)
        with self.action_lock:
            if self.closing:raise RuntimeError('O aplicativo está encerrando. As capturas estão sendo finalizadas.')
            s=self.store
            if path=='/api/demo':
                from . import demo
                return demo.create(s)
            if path=='/api/streamer':return dict(id=s.create_streamer(payload['name']))
            if path=='/api/profile':return s.save_profile(payload['streamer'],payload['profile'])
            if path=='/api/regenerate':return dict(replaced=s.regenerate(payload['streamer'],'reclassificação com o perfil e aprendizado atuais'))
            if path=='/api/backup/create':return dict(path=str(create_backup(s.root,'manual',keep=20)))
            if path=='/api/tools/check':return dict(paths=media.tool_status())
            if path=='/api/pause':return dict(paused=s.setting('paused',bool(payload['paused'])))
            if path=='/api/camera/detect':
                from . import camera_detect
                session=s.session(payload['session'])
                if (s.streamer(session['streamer'])['profile'] or {}).get('ai_mode')=='sem_ia':
                    raise ValueError('No modo sem IA a webcam não é detectada sozinha: marque a região em Ajustes → Webcam e quadro.')
                files=sorted(Path(session['source']).glob('segmento_*.ts')) if Path(session['source']).is_dir() else [Path(session['source'])]
                files=[f for f in files if f.is_file()]
                if not files:raise ValueError('Esta sessão ainda não tem vídeo gravado. Espere o primeiro pedaço.')
                return camera_detect.detect(files[0])
            if path=='/api/camera/accept':
                suggestion=s.setting('camera_sugestao:'+payload['streamer'])
                if not suggestion:raise ValueError('Não há sugestão de webcam para este streamer.')
                profile=s.streamer(payload['streamer'])['profile']
                s.save_profile(payload['streamer'],dict(profile,camera_rect=suggestion['rect']))
                with s.connect(True) as c:c.execute('DELETE FROM settings WHERE key=?',('camera_sugestao:'+payload['streamer'],))
                s.event('webcam','Sugestão de webcam aplicada.');return dict(rect=suggestion['rect'])
            if path=='/api/camera/dismiss':
                with s.connect(True) as c:c.execute('DELETE FROM settings WHERE key=?',('camera_sugestao:'+payload['streamer'],))
                return dict(ok=True)
            if path=='/api/preflight':
                from . import preflight
                return preflight.run(s,self.engine,self.capture,payload['streamer'])
            if path=='/api/engine/mode':
                lanes='unico' if payload.get('lanes')=='unico' else 'pistas'
                workers=2 if int(payload.get('export_workers') or 1)>=2 else 1
                s.setting('lanes',lanes);s.setting('export_workers',workers)
                s.event('desempenho','Modo de trabalho: '+('pista única' if lanes=='unico' else 'pistas separadas')+f' · {workers} exportação(ões) ao mesmo tempo')
                return dict(lanes=lanes,export_workers=workers)
            if path=='/api/import':
                name=payload['name']
                if name not in [x['name'] for x in self.legacy_sessions()]:raise ValueError('Gravação antiga não encontrada.')
                sid=s.new_session(payload['streamer'],name,self.legacy_root/'segmentos'/name,bool(payload.get('closed',True)))
                # Importar é um vínculo somente leitura. Somente o perfil é copiado.
                streamer=s.streamer(payload['streamer'])
                if not streamer['profile']['camera_rect']:
                    for stage in ('agentes_etapa7','agentes_etapa6','agentes_etapa5','agentes'):
                        old=self.legacy_root/stage/name/'perfil_tiktok.json'
                        if old.is_file():
                            try:
                                profile=streamer['profile'];profile['camera_rect']=json.loads(old.read_text(encoding='utf-8-sig'))['camera_rect']
                                s.save_profile(streamer['id'],profile)
                            except (ValueError,KeyError):pass
                            break
                session=s.session(sid)
                atomic.write_json(Path(session['path'])/'vinculo_origem.json',dict(source=session['source'],read_only=True),indent=2)
                s.event('importação','Gravação vinculada a '+streamer['name']+'; originais preservados.')
                return dict(id=sid)
            if path=='/api/video/import':
                self.license.check_active()
                return self.import_video(payload)
            if path=='/api/video/url':
                self.license.check_active()
                url=str(payload['url']).strip()
                from . import videodl
                if videodl.is_youtube(url):
                    # Vídeo comum do YouTube: baixa o arquivo (yt-dlp). Só uma live segue pelo caminho de gravação.
                    found=videodl.inspect(url)
                    if not found['live']:return self.start_video_download(payload,url,found)
                checked=self.capture.inspect(url,payload['streamer'])
                meta={k:str(checked.get(k,'')).strip()[:500] for k in ('title','author','plugin','category')}
                reframe=str(payload.get('reframe_mode','conservative'))
                if reframe not in ('conservative','dynamic','speaker','rastreio'):raise ValueError('Enquadramento de vídeo inválido.')
                if reframe=='rastreio' and not s.streamer(payload['streamer'])['profile'].get('track_roi'):
                    raise ValueError('Marque no perfil a região a acompanhar antes de usar o enquadramento por rastreio.')
                meta.update(mode='video',reframe_mode=reframe)
                sid=self.capture.start(payload['streamer'],url,meta)
                s.setting('paused',False)
                s.event('vídeo','Vídeo por link iniciado em modo análise: '+(meta['title'] or url))
                return dict(id=sid,source=checked)
            if path=='/api/capture/start':
                self.license.check_start_live(len(self.capture.state()))
                meta={k:str(payload.get(k,'')).strip()[:500] for k in ('title','author','plugin','category')}
                sid=self.capture.start(payload['streamer'],payload['url'],meta)
                self.license.record('live',1,'live:'+str(sid))
                if payload.get('analyze',True):s.setting('paused',False)
                return dict(id=sid)
            if path=='/api/capture/test':return self.capture.inspect(payload['url'],payload['streamer'])
            if path=='/api/capture/stop':self.capture.stop(payload['session']);return dict(ok=True)
            if path=='/api/capture/stop-all':self.capture.stop_all();return dict(ok=True)
            if path=='/api/capture/limit':return dict(limit=self.capture.set_limit(payload['limit']))
            if path=='/api/session':
                session=s.session(payload['session'])
                if payload.get('closed') is not None and any(item['session']==session['id'] for item in self.capture.state()):
                    raise ValueError('Encerre a captura pelo botão Encerrar captura para finalizar o arquivo.')
                with s.connect(True) as c:
                    if 'closed' in payload:c.execute('UPDATE sessions SET closed=? WHERE id=?',(int(bool(payload['closed'])),session['id']))
                    if 'enabled' in payload:c.execute("UPDATE sessions SET enabled=?,error='',status=CASE WHEN status='error' THEN 'idle' ELSE status END WHERE id=?",
                                                    (int(bool(payload['enabled'])),session['id']))
                return dict(ok=True)
            if path=='/api/session/external-audio':
                return self.link_external_audio(s.session(payload['session']),str(payload.get('path') or ''))
            if path=='/api/session/external-audio/clear':
                syncaudio.unlink(s.session(payload['session'])['path']);return self.markers_state(s.session(payload['session']))
            if path=='/api/session/markers':
                return self.markers_state(s.session(payload['session']))
            if path=='/api/session/marker':
                return self.add_marker(s.session(payload['session']),payload)
            if path=='/api/session/markers/import':
                return self.import_markers(s.session(payload['session']),payload)
            if path=='/api/session/markers/clear':
                for name in markers.FILES:(Path(s.session(payload['session'])['path'])/name).unlink(missing_ok=True)
                return self.markers_state(s.session(payload['session']))
            if path=='/api/session/subtitles/import':
                return self.import_subtitles(s.session(payload['session']),payload)
            if path=='/api/session/subtitles/paste':
                return self.paste_subtitles(s.session(payload['session']),payload)
            if path=='/api/session/subtitles/clear':
                folder=Path(s.session(payload['session'])['path'])/'legendas'
                for f in folder.glob('*') if folder.is_dir() else []:
                    if f.is_file() and f.suffix.lower() in subtitles.EXTENSIONS:f.unlink(missing_ok=True)
                return self.markers_state(s.session(payload['session']))
            if path=='/api/render/cancel':
                return dict(result=self.engine.cancel_render(str(payload['candidate'])))
            if path=='/api/session/retry':
                s.retry_session(payload['session']);return dict(ok=True)
            if path=='/api/session/archive':
                session=s.session(payload['session'])
                if any(item['session']==session['id'] for item in self.capture.state()):
                    raise ValueError('Encerre a captura antes de arquivar esta sessão.')
                s.archive_session(session['id'],bool(payload.get('archived',True)));return dict(ok=True)
            if path=='/api/session/relink':
                session=s.session(payload['session'])
                if any(item['session']==session['id'] for item in self.capture.state()):
                    raise ValueError('Encerre a captura antes de trocar a origem.')
                return dict(source=s.relink_session(session['id'],payload['path']))
            if path=='/api/frame':
                s.session(payload['session'])
                with s.connect(True) as c:c.execute("UPDATE sessions SET frame_status='queued',frame_error='' WHERE id=?",(payload['session'],))
                return dict(ok=True)
            if path=='/api/manual':
                session=s.session(payload['session']);candidate_id,created=self.make_manual(session,float(payload['start']),float(payload['end']))
                s.event('corte manual',session['name']+' · '+candidate_id)
                return dict(id=candidate_id,created=created)
            if path=='/api/variant/ab':return self.variant_ab(payload['id'])
            if path=='/api/variant/series':return self.variant_series(payload['id'],payload.get('at'))
            if path=='/api/review':return self.review(payload)
            if path=='/api/review/batch':return self.review_batch(payload)
            if path=='/api/delivery/retry':
                item=s.candidate(payload['id'])
                if item['status']!='done' or not item['export_path']:raise ValueError('Só dá para entregar um corte já exportado.')
                result=self.engine.deliver_one(item['id'],item['export_path'])
                if result is None:raise ValueError('Defina a pasta de entrega em Ajustes → Entrega antes de tentar.')
                return dict(delivery=result)
            if path=='/api/delivery/ready':
                streamer=s.streamer(payload['streamer'])
                if not streamer['profile'].get('delivery_folder'):raise ValueError('Defina e salve a pasta de entrega antes.')
                threading.Thread(target=self.engine.deliver_ready,args=(streamer['id'],),daemon=True,name='entrega-prontos').start()
                return dict(started=True)
            if path=='/api/project/get':return self.project_get(payload['id'])
            if path=='/api/project/save':return self.project_save(payload)
            if path=='/api/performance/save':
                item=s.candidate(payload['id']);perf=s.save_performance(item['id'],payload)
                return dict(performance=perf,summary=s.learning_summary(item['streamer']))
            if path=='/api/publication':return self.publication(payload['id'])
            if path=='/api/analytics/preview':return self.analytics_preview(payload)
            if path=='/api/analytics/apply':return self.analytics_apply(payload)
            if path=='/api/learning/details':return self.learning_details(payload['streamer'])
            if path=='/api/learning/accept-term':
                terms=s.accept_term(payload['streamer'],payload.get('term',''))
                return dict(learned_terms=terms,details=self.learning_details(payload['streamer']))
            if path=='/api/captions/from-text':return self.captions_from_text(payload)
            if path=='/api/captions/refine':
                s.candidate(payload['id']);self.engine.queue_refine(payload['id'],payload.get('model') or None)
                return dict(ok=True)
            if path=='/api/open-folder':
                target=Path(s.session(payload['session'])['path']).resolve()
                if not target.is_relative_to(s.root):raise ValueError('Pasta inválida.')
                if os.name=='nt':os.startfile(str(target))
                return dict(path=str(target))
            if path=='/api/plan/get':return studio_api.plan_view(s,payload['id'])
            if path=='/api/converse':return studio_api.talk(s,payload)
            if path=='/api/approve':return studio_api.approve(s,payload['id'])
            if path=='/api/package/build':return studio_api.build_package(s,payload['id'])
            if path=='/api/package/project':return studio_api.save_project(s,payload['id'],payload.get('include_sources',False),payload.get('dry_run',False))
            if path=='/api/package/reopen':
                from . import export_pack
                return export_pack.reopen(Path(str(payload['folder'])),payload.get('search') or [])
            if path.startswith('/api/context/'):return studio_api.context_action(s,path,payload)
            if path=='/api/memory/list':return studio_api.memory_list(s,payload)
            if path.startswith('/api/memory/'):return studio_api.memory_action(s,path,payload)
            if path.startswith('/api/references/'):return studio_api.references_action(s,path,payload)
            if path=='/api/telemetry':return studio_api.telemetry_report(s)
            raise ValueError('Ação não encontrada.')


    BATCH_LIMIT=50

    def review_batch(self,payload):
        """Aprova ou rejeita vários cortes pendentes de uma vez, um por um e sem atalhos: cada corte passa pelas
        mesmas regras da revisão individual (cota do plano, análise completa, confirmação editorial). O que não puder
        ser decidido em lote volta na lista com o motivo; o resto segue."""
        action=payload.get('action')
        if action not in ('approve','reject'):raise ValueError('Ação em lote inválida. Use aprovar ou rejeitar.')
        ids=payload.get('ids')
        if not isinstance(ids,list) or not ids or not all(isinstance(x,str) for x in ids):raise ValueError('Escolha pelo menos um corte.')
        ids=list(dict.fromkeys(ids))
        if len(ids)>self.BATCH_LIMIT:raise ValueError(f'No máximo {self.BATCH_LIMIT} cortes por vez.')
        reason=str(payload.get('reason') or '')
        results=[]
        for cid in ids:
            try:item=self.store.candidate(cid)
            except Exception:results.append(dict(id=cid,ok=False,error='Corte não encontrado.'));continue
            if item['status']!='pending':results.append(dict(id=cid,ok=False,error='Este corte já foi decidido.'));continue
            music=((item.get('data') or {}).get('project') or {}).get('music')
            if action=='approve' and music and not music.get('authorized'):
                results.append(dict(id=cid,ok=False,error='Tem música sem a confirmação de direito de uso. Abra o corte no estúdio.'));continue
            try:
                self.review(dict(id=cid,version=item['version'],start=item['start'],end=item['end'],action=action,
                                 reason=reason,editorial_confirmed=False))
                results.append(dict(id=cid,ok=True))
            except Exception as exc:
                results.append(dict(id=cid,ok=False,error=str(exc)))
        return dict(results=results,done=sum(1 for r in results if r['ok']),failed=sum(1 for r in results if not r['ok']))

    def review(self,payload):
        s=self.store
        item=s.candidate(payload['id'])
        if payload.get('action') in ('approve','retry') and item['status'] not in ('approved','exporting'):
            waiting=s.rows("SELECT COUNT(*) n FROM candidates WHERE status IN ('approved','exporting')")[0]['n']
            self.license.check_export(waiting)   # cota de clipes do plano (aprovados na fila contam)
        transcript=None
        if payload['action']=='reject':
            parts=item['parts'];payload['start']=item['start'];payload['end']=item['end']
        else:
            timeline=build_timeline(s.segments(item['session']))
            parts=plan(timeline,payload['start'],payload['end'],item['group_id'])
            included=[r for r in timeline if r['seq'] in {p['seq'] for p in parts}]
            waiting=[r for r in included if r['status']!='done']
            if waiting:
                raise ValueError(f'Aguarde a análise: {len(waiting)} de {len(included)} trechos deste intervalo ainda não foram analisados, '
                                 'e sem isso as legendas ficariam erradas. Isso acontece quando a análise está pausada ou foi refeita '
                                 'porque o perfil mudou (modelo, idioma, vocabulário, enquadramento da câmera ou sensibilidade). '
                                 'Retome a análise e tente de novo.')
            transcript=shifted_transcript(included)
        profile=dict(s.streamer(item['streamer'])['profile'] if payload.get('use_current_profile',True) else item['profile'])
        profile['content_mode']=item['data'].get('content_mode',profile.get('content_mode','live'))
        profile['reframe_mode']=item['data'].get('reframe_mode',profile.get('reframe_mode','conservative'))
        if payload['action'] in ('approve','retry') and payload.get('quality_mode'):
            # Modo de qualidade escolhido na hora de exportar este corte (o padrão continua no perfil).
            from .telemetry import MODES
            if payload['quality_mode'] not in MODES:raise ValueError('Modo de qualidade desconhecido.')
            profile['quality_mode']=payload['quality_mode']
        version=s.review(item['id'],payload['version'],payload['start'],payload['end'],parts,payload['action'],profile,transcript,
                         bool(payload.get('editorial_confirmed')),payload.get('edit_overrides'),
                         payload.get('reason') if payload['action']=='reject' else '')
        self.record_case(item,payload)
        return dict(version=version)

    @staticmethod
    def capture_end(session):
        try:return json.loads((Path(session['path'])/'captura_fim.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):return None

    def record_case(self,item,payload):
        """Guarda aprovações/rejeições como casos de aprendizado (nunca derruba a revisão se falhar)."""
        kind={'approve':'approved','reject':'rejected'}.get(payload.get('action'))
        if not kind:return
        try:
            from .context_store import ContextStore
            intel=(item.get('data') or {}).get('intelligence') or {}
            ContextStore(self.store.root).add_case(kind,item['session'],creator=item.get('streamer',''),event_refs=[item['id']],
                candidate=item['id'],human_intervals=[[float(payload['start']),float(payload['end'])]] if kind=='approved' else None,
                reason=str(payload.get('reason') or ''),coverage=(intel.get('rosto') or {}).get('level'))
        except Exception:pass

    def music_exists(self,music_id):
        try:music.get(self.store.root,music_id);return True
        except ValueError:return False

    def image_exists(self,image_id):
        try:assets.get(self.store.root,image_id);return True
        except ValueError:return False

    def make_manual(self,session,start,end,extra=None,project=None,allow_overlap=False):
        """Cria um corte pelo tempo (usado pelo corte manual, pela série em partes e pelas variações)."""
        s=self.store
        if not all(math.isfinite(v) for v in (start,end)) or start<0 or not 1<=end-start<=90:
            raise ValueError('O corte manual deve durar entre 1 e 90 segundos.')
        timeline=build_timeline(s.segments(session['id']))
        parts=plan(timeline,start,end)
        included=[row for row in timeline if row['seq'] in {part['seq'] for part in parts}]
        if not included or any(row['status']!='done' for row in included):
            raise ValueError('Escolha um intervalo que já esteja analisado para preservar falas e legendas.')
        transcript=shifted_transcript(included)
        source=source_info(session['path']);profile=dict(s.streamer(session['streamer'])['profile'])
        profile['content_mode']=source.get('mode','live')
        profile['reframe_mode']=source.get('reframe_mode','conservative')
        data=dict(start=start,end=end,group_id=parts[0]['group_id'],score=0.0,
                  reasons=['Corte manual criado por você'],components={},context_files=[p['seq'] for p in parts],
                  transcript_segments=transcript,
                  transcript=' '.join(row['text'] for row in transcript if row['start']<end and row['end']>start),
                  content_mode=profile['content_mode'],reframe_mode=profile['reframe_mode'])
        data['editorial_audit']=audit(data,profile,source)
        data['edit_plan']=plan_edits(data,{},transcript=transcript,profile=profile)
        data['hook']=agents.hook_analysis(transcript,start,end)
        data.update(extra or {})
        if project:data['project']=project
        return s.create_manual(session['id'],data,parts,profile,allow_overlap=allow_overlap)

    def variant_ab(self,candidate_id):
        """Cópia do corte com a abertura invertida, para postar as duas e comparar os números."""
        s=self.store;item=s.candidate(candidate_id);data=item['data']
        if data.get('variant_of'):raise ValueError('Esse corte já é uma variação. Crie o teste a partir do corte original.')
        duration=item['end']-item['start']
        project,change=variants.ab_project(project_module.project_of(item),data.get('hook'),duration)
        project=project_module.clean(project,duration)
        session=s.session(item['session']);group=data.get('ab',{}).get('group') or item['id']
        label_a=dict(group=group,label='A',change='abertura original' if not data.get('project',{}).get('teaser') else 'com abertura (teaser)')
        new_id,created=self.make_manual(session,item['start'],item['end'],
                                         extra=dict(variant_of=item['id'],ab=dict(group=group,label='B',change=change),
                                                    reasons=['Variação B do teste de abertura: '+change]),
                                         project=project,allow_overlap=True)
        with s.connect(True) as c:
            row=c.execute('SELECT data FROM candidates WHERE id=?',(item['id'],)).fetchone()
            d=json.loads(row['data']);d['ab']=label_a
            c.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(d),item['id']))
        s.event('teste A/B','Variação B criada: '+change)
        return dict(id=new_id,created=created,change=change)

    def variant_series(self,candidate_id,at=None):
        """Divide um corte longo em Parte 1/2 e Parte 2/2 num ponto natural (ou no tempo `at`, em segundos absolutos)."""
        s=self.store;item=s.candidate(candidate_id);data=item['data']
        if data.get('series'):raise ValueError('Esse corte já faz parte de uma série.')
        transcript=data.get('transcript_segments',[]);start,end=item['start'],item['end']
        if at in (None,''):
            split=variants.best_split(transcript,start,end)
            if not split:raise ValueError('O corte precisa ter pelo menos %d segundos para dividir em duas partes de ao menos %d s.'%(2*variants.MIN_PART,variants.MIN_PART))
            at=split['at'];reason=split['reason']
        else:
            at=float(at);reason='Ponto escolhido por você.'
            if at-start<variants.MIN_PART or end-at<variants.MIN_PART:raise ValueError('Cada parte precisa ter pelo menos %d segundos.'%variants.MIN_PART)
        session=s.session(item['session']);ids=[]
        for number,(a,b) in enumerate(((start,at),(at,end)),1):
            project=project_module.clean(dict(titles=[variants.part_title(number,2,a,b)]),b-a)
            new_id,_=self.make_manual(session,a,b,extra=dict(series=dict(group=item['id'],part=number,of=2,split_at=at),
                                                             reasons=[f'Parte {number}/2 de uma série. '+reason]),
                                       project=project,allow_overlap=True)
            ids.append(new_id)
        s.event('série','Corte dividido em duas partes: '+reason)
        return dict(ids=ids,at=at,reason=reason)

    def analytics_preview(self,payload):
        """Lê o CSV do TikTok Studio e propõe a ligação de cada linha com um clipe exportado. Não grava nada."""
        s=self.store;streamer=payload['streamer'];s.streamer(streamer)
        rows,warnings=analytics.parse(str(payload.get('text','')))
        done=[s.decode(dict(r)) for r in s.rows("SELECT * FROM candidates WHERE streamer=? AND status='done' ORDER BY created DESC LIMIT 300",(streamer,))]
        proposals=analytics.match(rows,done)
        options=[dict(id=c['id'],label=(c['data'].get('reasons') or ['clipe'])[0][:60],start=c['start'],end=c['end'],
                      has_performance=bool(c['data'].get('performance'))) for c in done]
        return dict(items=proposals,warnings=warnings,candidates=options)

    def analytics_apply(self,payload):
        """Grava os números das ligações que você confirmou (cada uma é validada como se fosse digitada)."""
        s=self.store;saved,errors=0,[]
        for pair in payload.get('pairs',[]):
            row=pair.get('row') or {}
            try:
                s.candidate(pair['id'])
                s.save_performance(pair['id'],dict(views=row.get('views'),likes=row.get('likes'),comments=row.get('comments'),
                                                   shares=row.get('shares'),saves=row.get('saves'),watch_pct=row.get('watch_pct'),
                                                   url=row.get('url',''),note='importado do CSV'))
                saved+=1
            except (ValueError,KeyError) as exc:errors.append(dict(id=pair.get('id'),error=str(exc)))
        streamers={s.candidate(p['id'])['streamer'] for p in payload.get('pairs',[]) if p.get('id') and p['id'] not in [e['id'] for e in errors]}
        return dict(saved=saved,errors=errors,summaries={sid:s.learning_summary(sid) for sid in streamers})

    def learning_details(self,streamer_id):
        """O que o sistema aprendeu: seus hábitos de edição, a calibração da confiança e o desempenho por estilo."""
        s=self.store;s.streamer(streamer_id)
        return dict(habits=s.habits(streamer_id),calibration=s.confidence_table(streamer_id),styles=s.style_report(streamer_id),
                    ab=learning.ab_report(s.ab_items(streamer_id)),acceptance=s.acceptance_history(streamer_id),
                    learned_terms=s.streamer(streamer_id)['profile'].get('learned_terms',''))

    def project_get(self,candidate_id):
        """Tudo que o editor precisa para abrir um corte: projeto, legendas editáveis, sugestões e catálogos."""
        s=self.store;item=s.candidate(candidate_id)
        data=item['data'];start,end=item['start'],item['end'];length=end-start
        transcript=data.get('transcript_segments',[])
        profile=dict(s.streamer(item['streamer'])['profile'])
        saved=project_module.project_of(item)
        current=saved or project_module.empty()
        captions=current.get('captions') or {}
        auto_lines,fixes=lines_from_transcript(transcript,start,end,caption_terms(profile),corrections=profile.get('corrections',''))
        lines=captions.get('lines')
        track=current.get('music')
        beats=[];track_info=None
        if track:
            try:
                info=music.get(s.root,track['id']);track_info=music.public(info)
                beats=music.beat_times(info,track.get('start',0),track.get('start',0)+length)
            except ValueError:track=None
        suggestions=agents.analyze_candidate(transcript,start,end)
        timing=timing_for(item)
        applied=cuts_for(item)
        return dict(
            id=item['id'],version=item['version'],status=item['status'],start=start,end=end,duration=round(length,3),
            session=item['session'],score=item['score'],reasons=data.get('reasons',[]),
            project=current,saved=bool(saved),
            lines=lines if lines is not None else auto_lines,lines_edited=lines is not None,
            auto_lines=auto_lines,vocabulary_fixes=fixes,
            suggestions=suggestions,beats=beats,music=track_info,timing=timing,
            overrides=data.get('edit_overrides',{}),audit=data.get('editorial_audit',{}),hook=data.get('hook'),
            confidence=data.get('confidence'),refinement=data.get('refinement'),edges=data.get('edges'),
            refine=data.get('refine') or {},llm_titles=data.get('llm_titles') or [],
            cut_warnings=safety.analyze_cuts(transcript,start,end,applied),
            decisions=data.get('edit_plan',{}).get('decisions',[]),
            preview=preview_info(item,data),
            error=item['error'],profile=dict(style=profile.get('editorial_style','clean'),caption_style=profile.get('caption_style','auto'),
                                             font_size=profile.get('font_size'),caption_margin=profile.get('caption_margin'),
                                             caption_color=profile.get('caption_color'),content_mode=item['data'].get('content_mode','live'),
                                             second_pass=profile.get('second_pass','off'),quality_mode=profile.get('quality_mode','equilibrado'),
                                             brand_font=(profile.get('brand') or {}).get('caption_font','')),
            catalog=dict(styles=[dict(id=k,label=v['label']) for k,v in EDITOR_PRESETS.items()],
                         caption_styles=list(STYLE_NAMES),sfx=sfx.catalog(),zoom_curves=list(project_module.ZOOM_CURVES),
                         title_styles=list(project_module.TITLE_STYLES),layouts=list(project_module.LAYOUTS),
                         pip_corners=list(project_module.PIP_CORNERS),formats=list(project_module.FORMATS),
                         speed_range=list(project_module.SPEED_RANGE),freeze_range=list(project_module.FREEZE_RANGE),
                         quality_modes=quality_catalog()),
            images=assets.library(s.root),performance=data.get('performance'),
            camera=bool(profile.get('camera_rect')),encoder=profile.get('video_encoder','cpu'))

    def project_save(self,payload):
        s=self.store;item=s.candidate(payload['id']);version=int(payload['version'])
        moved=False
        if 'start' in payload and 'end' in payload:
            start,end=float(payload['start']),float(payload['end'])
            if abs(start-item['start'])>.0001 or abs(end-item['end'])>.0001:
                moved=True
                action='save' if 'project' in payload else 'preview'
                version=self.review(dict(id=item['id'],version=version,start=start,end=end,action=action,
                                         use_current_profile=False))['version']
        if 'project' not in payload:
            # Só mudou os limites: o projeto já foi reajustado (rebase) e a prévia enfileirada pelo review.
            if not moved:raise ValueError('Nada para salvar.')
            return dict(version=version)
        new_version=s.save_project(item['id'],version,payload.get('project'),bool(payload.get('preview',True)),self.music_exists,self.image_exists,
                                   learn=bool(payload.get('learn',True)))
        return dict(version=new_version)

    def publication(self,candidate_id):
        """Texto do pacote de publicação do clipe exportado (legenda, hashtags, créditos)."""
        item=self.store.candidate(candidate_id)
        if item['status']!='done' or not item.get('export_path'):raise ValueError('Exporte o clipe para gerar o pacote de publicação.')
        file=Path(item['export_path']).parent/'publicacao.txt'
        if not file.is_file():raise ValueError('Esse clipe foi exportado antes do pacote de publicação existir. Exporte de novo.')
        return dict(text=file.read_text(encoding='utf-8'))

    def system_check(self,payload):
        """Placa de vídeo, CUDA e Ollama disponíveis neste computador (testes reais; pode levar alguns segundos)."""
        from . import hardware
        url=str(payload.get('url') or '')
        try:models=ollama.models(url or None)
        except ValueError as exc:return dict(error=str(exc))
        return dict(encoders=hardware.status(),cuda=engine_module.cuda_devices(),ollama=dict(models=models,running=bool(models)))

    def music_action(self,path,payload):
        """Rotas de música: ficam fora do bloqueio principal porque baixar pode demorar."""
        root=self.store.root
        if path=='/api/system/check':return self.system_check(payload)
        if path=='/api/music/list':return dict(items=music.library(root),status=music.status(),images=assets.library(root))
        if path=='/api/music/inspect':return music.inspect(str(payload.get('url','')))
        if path=='/api/music/fetch':
            item=music.fetch(root,str(payload.get('url','')));self.store.event('música',item['title'])
            return dict(item=item)
        if path=='/api/support/bundle':
            file=support.bundle(root,self.store,__version__,media.tool_status(),extra=self.engine_report());self.store.event('diagnóstico','Pacote gerado: '+file.name)
            return dict(ok=True,name=file.name,path=str(file),folder=str(file.parent))
        if path=='/api/denoise/status':return denoise.status(root)
        if path=='/api/denoise/fetch':
            result=denoise.fetch(root);self.store.event('áudio','Modelo de redução de ruído instalado.');return result
        if path=='/api/music/remove':music.remove(root,str(payload.get('id','')));return dict(ok=True)
        if path=='/api/image/remove':assets.remove(root,str(payload.get('id','')));return dict(ok=True)
        if path=='/api/image/variants':
            from . import imagerecipe
            imagerecipe.prune(root);return dict(items=[{k:v for k,v in i.items() if k!='file'} for i in imagerecipe.catalog(root)])
        if path=='/api/image/batch':
            # Receita em lote (P21): lê os arquivos informados e grava só em <dados>/imagens/lotes/<data>; fontes intactas.
            from . import imagerecipe
            paths=payload.get('paths')
            if not isinstance(paths,list) or not paths or len(paths)>200:raise ValueError('Informe de 1 a 200 arquivos de imagem.')
            out=Path(root)/'imagens'/'lotes'/time.strftime('%Y%m%d-%H%M%S')
            report=imagerecipe.batch([str(p) for p in paths],payload.get('recipe') or {},out)
            self.store.event('imagem','Lote de imagens: %d ok, %d com erro'%(sum(1 for r in report if r['ok']),sum(1 for r in report if not r['ok'])))
            return dict(folder=str(out),items=report)
        raise ValueError('Ação não encontrada.')

    # ---- Modo sem IA: marcadores e legendas prontas (P04/P14) ----
    def markers_state(self,session):
        found,warnings=markers.for_session(session['path']);subs,sub_warnings=subtitles.for_session(session['path'])
        return dict(markers=found,subtitles=dict(count=len(subs),first=subs[0]['start'] if subs else None,last=subs[-1]['end'] if subs else None),
                    warnings=warnings+sub_warnings,external_audio=self.external_state(session))

    @staticmethod
    def external_state(session):
        try:return json.loads((Path(session['path'])/syncaudio.FILE).read_text(encoding='utf-8'))
        except (OSError,ValueError):return None

    def link_external_audio(self,session,path):
        """Vincula um áudio gravado à parte (P06). Só para sessões de um único arquivo; recusa quando a correlação não é clara."""
        file=Path(path)
        if not path or not file.is_absolute() or not file.is_file():raise ValueError('Informe o caminho completo de um arquivo de áudio que exista neste computador.')
        if file.suffix.lower() not in ('.wav','.mp3','.m4a','.aac','.flac','.ogg','.opus','.mp4','.mkv','.mov'):raise ValueError('Formato de áudio não reconhecido.')
        segments=self.store.segments(session['id'])
        if len(segments)!=1:raise ValueError('O áudio externo só funciona em sessões de um único arquivo (vídeo local). Em lives, o corte vem de vários pedaços.')
        record=syncaudio.link(session['path'],segments[0]['path'],file)
        self.store.event('áudio externo',('Sincronizado (deslocamento '+str(record['offset'])+' s).') if record['ok'] else 'Recusado: '+record.get('reason',''))
        return dict(self.markers_state(session),linked=record)

    def add_marker(self,session,payload):
        """Atalho 'marcar este momento': usa o relógio do PC contra o horário de gravação dos pedaços. É uma estimativa e vem rotulada assim."""
        label=str(payload.get('label') or '')[:80]
        if payload.get('time') not in (None,''):
            seconds=markers.clock(payload['time']);approx=False
        else:
            epoch=float(payload.get('epoch') or time.time())
            timeline=build_timeline(self.store.segments(session['id']))
            if not timeline:raise ValueError('Esta sessão ainda não tem pedaço gravado. Espere o primeiro pedaço fechar para marcar pelo relógio, ou informe o tempo.')
            seconds=markers.epoch_to_session(timeline,epoch);approx=False
            if seconds is None:
                last=timeline[-1];end_epoch=float(last['mtime'])/1e9
                if 0<epoch-end_epoch<=1800:seconds=round(last['end']+(epoch-end_epoch),3);approx=True   # momento ainda no pedaço aberto
                else:raise ValueError('Esse instante está fora da gravação desta sessão.')
        item=markers._item(seconds,label,payload.get('pre'),payload.get('post'),source='atalho' if payload.get('time') in (None,'') else 'manual')
        file=Path(session['path'])/'marcadores.json'
        try:current=json.loads(file.read_text(encoding='utf-8-sig')) if file.is_file() else []
        except ValueError:current=[]
        if not isinstance(current,list):current=[]
        current.append(dict(time=item['time'],label=item['label'],pre=item['pre'],post=item['post'],source=item['source'],approx=approx))
        if len(current)>markers.MAX_MARKERS:raise ValueError('Marcadores demais nesta sessão.')
        tmp=file.with_suffix('.tmp');tmp.write_text(json.dumps(current,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(file)
        self.store.event('marcador','Momento marcado em '+str(item['time'])+' s'+(' (estimado)' if approx else ''))
        return dict(self.markers_state(session),added=item,approx=approx)

    def import_markers(self,session,payload):
        name=str(payload.get('name') or 'marcadores.json');suffix=Path(name).suffix.lower()
        if suffix not in ('.json','.csv','.txt'):raise ValueError('Use um arquivo .json, .csv ou .txt de marcadores.')
        text=str(payload.get('content') or '')
        found=markers.parse(text,name)
        if not found:raise ValueError('Não encontrei nenhum marcador nesse arquivo.')
        target=Path(session['path'])/('marcadores'+suffix)
        atomic.write_text(target,text);self.store.event('marcador',str(len(found))+' marcador(es) importado(s)')
        return dict(self.markers_state(session),imported=len(found))

    def start_video_download(self,payload,url,found):
        """Baixa um vídeo do YouTube em segundo plano (progresso e cancelamento na bandeja) e, ao terminar, importa como arquivo."""
        from . import videodl
        s=self.store
        reframe=str(payload.get('reframe_mode','conservative'))
        if reframe not in ('conservative','dynamic','speaker','rastreio'):raise ValueError('Enquadramento de vídeo inválido.')
        profile=s.streamer(payload['streamer'])['profile']
        if reframe=='rastreio' and not profile.get('track_roi'):
            raise ValueError('Marque no perfil a região a acompanhar antes de usar o enquadramento por rastreio.')
        media.require_space(s.root,profile['min_free_gb'],2*1024**3)
        title=found['title'] or url
        key='download:'+secrets.token_hex(4)
        task=self.engine.board.start(key,'download',title[:80])
        task.phase('Preparando o download',0,2)
        shown={'stage':''}
        def progress(fraction,stage):
            if stage!=shown['stage']:
                shown['stage']=stage
                task.phase(stage,2,92) if stage.startswith('Baixando') else task.phase(stage,92,96)
            task.report(fraction)
        def work():
            try:
                path=videodl.download(url,s.root/'downloads',on_progress=progress,cancelled=task.cancel.is_set)
                task.phase('Enviando para análise',96,99)
                name=(title[:70]+' ['+(found['id'] or path.stem)+']').replace('/','-').replace('\\','-')
                self.import_video(dict(payload,path=str(path),name=name,title=title,url=url,reframe_mode=reframe))
                s.event('vídeo','Vídeo do YouTube baixado e enviado para análise: '+title[:120])
                task.finish('concluido')
            except videodl.DownloadCancelled:
                task.finish('cancelado','Download cancelado. Nada foi adicionado.')
                s.event('vídeo','Download cancelado: '+title[:120])
            except Exception as exc:
                task.finish('falhou',str(exc))
                s.event('vídeo','Falha ao baixar o vídeo: '+str(exc)[:200])
        threading.Thread(target=work,name='download-video',daemon=True).start()
        return dict(download=key,title=title,source=dict(found,plugin='youtube'))

    def import_video(self,payload):
        s=self.store
        source=Path(str(payload['path'])).expanduser().resolve()
        if not source.is_file() or source.suffix.casefold() not in ('.mp4','.mkv','.mov','.webm','.ts','.m4v'):
            raise ValueError('Escolha um arquivo de vídeo MP4, MKV, MOV, WEBM, TS ou M4V existente.')
        media.probe(source)
        name=payload.get('name') or source.stem
        reframe=str(payload.get('reframe_mode','conservative'))
        if reframe not in ('conservative','dynamic','speaker','rastreio'):raise ValueError('Enquadramento de vídeo inválido.')
        if reframe=='rastreio' and not s.streamer(payload['streamer'])['profile'].get('track_roi'):
            raise ValueError('Marque no perfil a região a acompanhar antes de usar o enquadramento por rastreio.')
        sid=s.new_session(payload['streamer'],name,source,closed=True)
        session=s.session(sid)
        info=dict(mode='video',reframe_mode=reframe,url=str(payload.get('url') or ''),title=str(payload.get('title') or source.stem)[:500],
                  author=s.streamer(payload['streamer'])['name'],file=str(source))
        atomic.write_json(Path(session['path'])/'fonte.json',info,indent=2)
        s.setting('paused',False);s.event('vídeo','Vídeo vinculado sem copiar o original: '+source.name)
        risks=[]
        try:
            from . import inventory
            found=inventory.describe(source);risks=found['risks']
            atomic.write_json(Path(session['path'])/'inventario.json',found,indent=2)
            for r in risks:s.event('mídia: '+r['id'],r['message'][:160])
        except Exception:pass   # o inventário informa riscos; nunca impede a importação
        return dict(id=sid,riscos=risks)

    def _clip_envelope(self,session,start,end):
        """Envelope de energia (dBFS, passo fixo) do trecho [start,end] da sessão, juntando os arquivos que o cobrem."""
        import numpy as np
        from . import technical,timeline
        rows=timeline.build_timeline(self.store.segments(session['id']))
        parts=timeline.plan(rows,start,end)
        dbs=[];step=technical.WINDOW
        for part in parts:
            db,step=technical.envelope(part['path'],part['in'],part['out']-part['in']);dbs.append(db)
        return (np.concatenate(dbs) if dbs else np.zeros(0,dtype=np.float32)),step

    def captions_from_text(self,payload):
        """Legenda do corte a partir do texto do usuário (sem reconhecimento de fala). Devolve linhas no formato do Estúdio (tempos em
        segundos desde o início do corte, na linha do tempo original), com `timing:'estimado'` (energia/pausas/sílabas) ou `'toques'`
        (o usuário marcou o início das frases). NÃO grava nada: o Estúdio aplica, mostra e o usuário confirma."""
        from . import captions_text
        item=self.store.candidate(payload['id']);session=self.store.session(item['session'])
        start,end=float(item['start']),float(item['end'])
        if not captions_text.split_phrases(payload.get('text')):raise ValueError('Cole ou digite o texto da legenda.')
        taps=[start+float(t) for t in (payload.get('taps') or []) if t is not None][:400]
        db,step=self._clip_envelope(session,start,end)
        result=captions_text.build(str(payload.get('text') or ''),db,step,offset=start,taps=taps or None,clip_end=end)
        lines=[dict(start=round(x['start']-start,3),end=round(x['end']-start,3),text=x['text'],
                    words=[dict(start=round(w['start']-start,3),end=round(w['end']-start,3),word=w['word']) for w in x['words']])
               for x in result['segments']]
        return dict(lines=lines,warnings=result['warnings'],timing='toques' if taps else 'estimado',duration=round(end-start,3),
                    speech=[[round(a-start,3),round(b-start,3)] for a,b in result['spans']])

    def paste_subtitles(self,session,payload):
        """Legenda a partir do texto colado pelo usuário (sem reconhecimento de fala): distribui as frases no tempo de fala detectado
        por energia. `start`/`end` (tempo da sessão) delimitam o trecho; `taps` (opcional) fixam o início de cada frase. Gera um SRT em
        `legendas/` e devolve o estado de marcadores/legendas com `warnings` e `timing:'estimado'`."""
        from . import captions_text
        start=float(payload['start']);end=float(payload['end'])
        if not 0<=start<end or end-start>600:raise ValueError('Escolha um trecho de até 10 minutos.')
        if not captions_text.split_phrases(payload.get('text')):raise ValueError('Cole ou digite o texto da legenda.')
        db,step=self._clip_envelope(session,start,end)
        result=captions_text.build(str(payload.get('text') or ''),db,step,offset=start,taps=payload.get('taps') or None,clip_end=end)
        folder=Path(session['path'])/'legendas';folder.mkdir(exist_ok=True)
        atomic.write_text(folder/'legenda_texto_colado.srt',result['srt'])
        self.store.event('legenda','Legenda por texto colado: '+str(len(result['segments']))+' frases (tempos estimados, origem: texto do usuário)')
        return dict(self.markers_state(session),imported=len(result['segments']),warnings=result['warnings'],timing='toques' if payload.get('taps') else 'estimado')

    def import_subtitles(self,session,payload):
        name=Path(str(payload.get('name') or 'legenda.srt')).name
        if Path(name).suffix.lower() not in subtitles.EXTENSIONS:raise ValueError('Use um arquivo de legenda .srt, .vtt ou .ass.')
        text=str(payload.get('content') or '');found=subtitles.parse(text.encode('utf-8'),name)
        if not found:raise ValueError('Não encontrei falas nesse arquivo de legenda.')
        folder=Path(session['path'])/'legendas';folder.mkdir(exist_ok=True)
        safe=''.join(c for c in name if c.isalnum() or c in ' -_.')[:80] or 'legenda.srt'
        atomic.write_text(folder/safe,text);self.store.event('legenda','Legenda importada: '+str(len(found))+' falas (origem: arquivo do usuário)')
        return dict(self.markers_state(session),imported=len(found))

    def receive_upload(self,kind,name,stream,length):
        """Recebe um arquivo bruto (música ou imagem) e o registra na biblioteca."""
        import tempfile
        if kind=='font':return self.receive_font(name,stream,length)
        if kind=='lut':return self.receive_lut(name,stream,length)
        limit=music.MAX_UPLOAD if kind=='music' else assets.MAX_IMAGE
        if kind not in ('music','image'):raise ValueError('Tipo de arquivo inválido.')
        if not 0<length<=limit:raise ValueError('Arquivo vazio ou grande demais.')
        suffix=Path(name).suffix.lower()[:8]
        folder=self.store.root/'tmp';folder.mkdir(exist_ok=True)
        media.require_space(self.store.root,1,extra=length*3)
        with tempfile.TemporaryDirectory(prefix='envio_',dir=folder) as temp:
            file=Path(temp)/('arquivo'+suffix)
            with file.open('wb') as out:
                remaining=length
                while remaining:
                    block=stream.read(min(1024*1024,remaining))
                    if not block:raise ValueError('O envio foi interrompido.')
                    out.write(block);remaining-=len(block)
            if kind=='music':item=music.import_file(self.store.root,file,Path(name).stem)
            else:item=assets.import_image(self.store.root,file,Path(name).stem)
        self.store.event('arquivo enviado',item.get('title') or item.get('name',''))
        return dict(item=item)

    def receive_lut(self,name,stream,length):
        """LUT .cube 3D do kit de cor: validada antes de entrar em `luts` dentro da pasta de dados."""
        if Path(name).suffix.lower()!='.cube':raise ValueError('Use um arquivo de LUT .cube.')
        if not 0<length<=grade.MAX_LUT_BYTES:raise ValueError('Arquivo de LUT vazio ou grande demais.')
        stem=''.join(c for c in Path(name).stem if c.isalnum() or c in ' -_.')[:60].strip() or 'lut'
        folder=self.store.root/'luts';folder.mkdir(exist_ok=True)
        target=folder/(stem+'.cube');pending=target.with_suffix('.tmp');remaining=length
        with pending.open('wb') as out:
            while remaining:
                block=stream.read(min(1024*1024,remaining))
                if not block:pending.unlink(missing_ok=True);raise ValueError('O envio foi interrompido.')
                out.write(block);remaining-=len(block)
        try:size,_=grade.read_cube(pending)
        except (grade.LutError,OSError) as exc:pending.unlink(missing_ok=True);raise ValueError(str(exc))
        pending.replace(target);self.store.event('cor','LUT instalada: '+target.name)
        return dict(item=dict(file=target.name,size=size))

    def receive_font(self,name,stream,length):
        """Fonte (.ttf/.otf) do kit de marca: vai para a pasta `fontes` dentro da pasta de dados."""
        suffix=Path(name).suffix.lower()
        if suffix not in ('.ttf','.otf'):raise ValueError('Use um arquivo de fonte .ttf ou .otf.')
        if not 0<length<=30*1024**2:raise ValueError('Arquivo de fonte vazio ou grande demais.')
        stem=''.join(c for c in Path(name).stem if c.isalnum() or c in ' -_.')[:60].strip() or 'fonte'
        folder=self.store.root/'fontes';folder.mkdir(exist_ok=True)
        target=folder/(stem+suffix);pending=target.with_suffix(suffix+'.tmp');remaining=length
        with pending.open('wb') as out:
            while remaining:
                block=stream.read(min(1024*1024,remaining))
                if not block:pending.unlink(missing_ok=True);raise ValueError('O envio foi interrompido.')
                out.write(block);remaining-=len(block)
        pending.replace(target)
        found=[f for f in brand.fonts(self.store.root) if f['file']==target.name]
        if not found:target.unlink(missing_ok=True);raise ValueError('Não consegui ler essa fonte. Tente outro arquivo.')
        self.store.event('fonte',found[0]['family'])
        return dict(item=found[0])

    def media_file(self,kind,key,n=None):
        if kind=='music':return music.path_of(self.store.root,key)
        if kind=='image':return assets.path_of(self.store.root,key)
        if kind=='frame':path=self.store.session(key)['frame_path']
        elif kind=='sample':
            row=self.store.candidate(key)
            if row['status']!='done' or not row['export_path']:raise ValueError('Este corte ainda não foi exportado.')
            number=int(n or 1)
            if not 1<=number<=9:raise ValueError('Amostra inválida.')
            path=str(Path(row['export_path']).parent/'amostras'/f'amostra_{number}.jpg')
        else:
            row=self.store.candidate(key)
            # A prévia anterior continua disponível (desatualizada) até a nova ficar pronta.
            if kind=='preview' and row['preview_path']:path=row['preview_path']
            elif kind=='export' and row['status']=='done':path=row['export_path']
            else:raise ValueError('Vídeo ainda não está pronto para esta revisão.')
        if not path:raise ValueError('Mídia ainda indisponível.')
        file=Path(path).resolve()
        if not file.is_relative_to(self.store.root) or not file.is_file():raise ValueError('Mídia não encontrada.')
        return file

    def style_demo(self,style):
        return media.style_demo(self.store.root,style)

    def close(self):
        with self.action_lock:
            self.closing=True
            try:self.capture.stop_all('Aplicativo encerrado; capturas finalizadas.')
            finally:
                self.engine.stop.set()
                try:self.license.close()
                except Exception:pass


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

        def authorized(self):
            return self.headers.get('X-LiveClips-Token')==app.token

        def respond(self,status,body,content_type='application/json; charset=utf-8',cookie=False,state_tag=None):
            data=json.dumps(body,ensure_ascii=False).encode() if isinstance(body,(dict,list)) else body
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; frame-ancestors 'none'; connect-src 'self'")
            if state_tag:self.send_header('X-State-Tag',state_tag)
            if cookie:self.send_header('Set-Cookie',f'lc_session={app.token}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers();self.wfile.write(data)

        def do_GET(self):
            if not self.valid_host():return self.respond(403,dict(error='Origem local inválida.'))
            url=urlparse(self.path)
            try:
                if url.path=='/':
                    html=(Path(__file__).parent/'static/index.html').read_text(encoding='utf-8')
                    return self.respond(200,html.replace('__BOOT_TOKEN__',json.dumps(app.token)).encode(),'text/html; charset=utf-8',True)
                if url.path=='/api/renders':
                    if not self.authorized():return self.respond(403,dict(error='Reabra o painel pela janela do Hook’s.'))
                    return self.respond(200,dict(renders=app.engine.renders()))
                if url.path=='/api/state':
                    if not self.authorized():return self.respond(403,dict(error='Reabra o painel pela janela do Hook’s.'))
                    # Só reenvia o painel quando algo mudou: o navegador manda a etiqueta da última resposta.
                    data=json.dumps(app.state(),ensure_ascii=False).encode()
                    tag=hashlib.sha1(data).hexdigest()[:16]
                    if self.headers.get('X-State-Tag')==tag:return self.respond(200,dict(unchanged=True,tag=tag))
                    return self.respond(200,data,state_tag=tag)
                if url.path.startswith('/media/'):
                    cookies=self.headers.get('Cookie','').split('; ')
                    if 'lc_session='+app.token not in cookies:return self.respond(403,dict(error='Sessão do painel inválida.'))
                    query=parse_qs(url.query);kind=url.path.rsplit('/',1)[-1]
                    if kind=='style-demo':file=app.style_demo(query.get('style',[''])[0])
                    else:
                        if kind not in ('preview','export','frame','music','image','sample'):raise ValueError('Mídia inválida.')
                        file=app.media_file(kind,query.get('id',[''])[0],query.get('n',['1'])[0] if kind=='sample' else None)
                    kinds={'frame':'image/jpeg','sample':'image/jpeg','music':'audio/mp4','image':{'.png':'image/png','.webp':'image/webp'}.get(file.suffix,'image/jpeg')}
                    return self.send_file(file,kinds.get(kind,'video/mp4'))
                return self.respond(404,dict(error='Página não encontrada.'))
            except (ValueError,KeyError,OSError,RuntimeError) as exc:return self.respond(400,dict(error=str(exc)))

        def send_file(self,file,content_type):
            size=file.stat().st_size;start=0;end=size-1;status=200
            range_header=self.headers.get('Range')
            if range_header:
                import re
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header.strip())
                if not match or not any(match.groups()):return self.respond(416,dict(error='Intervalo inválido.'))
                left,right=match.groups()
                if left:start=int(left);end=min(end,int(right)) if right else end
                else:start=max(0,size-int(right))
                if start>end or start>=size:return self.respond(416,dict(error='Intervalo fora do arquivo.'))
                status=206
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(end-start+1))
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            try:
                with file.open('rb') as f:
                    f.seek(start);remaining=end-start+1
                    while remaining:
                        block=f.read(min(65536,remaining))
                        if not block:break
                        self.wfile.write(block);remaining-=len(block)
            except (BrokenPipeError,ConnectionResetError):pass

        def do_POST(self):
            def reject(message):
                try:length=int(self.headers.get('Content-Length','0'))
                except ValueError:length=0
                # No Windows, fechar o socket com um corpo pequeno ainda não
                # lido pode gerar reset em vez da resposta 403 esperada.
                if 0<length<1048576:self.rfile.read(length)
                else:self.close_connection=True
                return self.respond(403,dict(error=message))
            if not self.valid_host() or not self.authorized():return reject('Ação local não autorizada.')
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                return reject('Origem inválida.')
            try:
                length=int(self.headers.get('Content-Length','0'))
                url=urlparse(self.path)
                if url.path=='/api/upload':
                    query=parse_qs(url.query)
                    result=app.receive_upload(query.get('kind',[''])[0],query.get('name',['arquivo'])[0],self.rfile,length)
                    return self.respond(200,result)
                if not 0<length<1048576:raise ValueError('Pedido inválido ou grande demais.')
                value=json.loads(self.rfile.read(length))
                if not isinstance(value,dict):raise ValueError('Pedido inválido.')
                result=app.action(urlparse(self.path).path,value)
                self.respond(200,result)
            except (ValueError,KeyError,OSError,RuntimeError) as exc:self.respond(400,dict(error=friendly_error(exc)))
            except Exception as exc:
                app.store.event('erro do painel',str(exc));support.log_error('Erro no painel em '+self.path,exc);self.respond(500,dict(error='Não foi possível concluir. Veja o aviso de atividade no painel.'))
    return Handler


def server(app,port=8765):
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    return LocalServer(('127.0.0.1',port),handler_for(app))
