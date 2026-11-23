"""Processamento local, montagem precisa e exportação em pasta atômica."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from . import progress
from .editing import (auto_replays,EDITOR_PRESETS,LOOKS,remap_for,camera_zoom_filter,cuts_for,decisions_for,effective_look,grade_filters,
                      keep_intervals,punches_for,retime_points,retime_transcript)
from .project import project_of,title_color_bgr
from .captions import caption_terms,make_ass,resolve_style

RENDERER_VERSION='0.13.0-plano-1'
LOUDNESS=dict(I=-16,LRA=11,TP=-1.5)


def run(args, timeout=900, cwd=None):
    duration=progress.take_duration()
    if duration:      # codificação de uma tarefa com progresso: lê o progresso estruturado do FFmpeg e responde ao cancelamento
        progress.run_ffmpeg(args,cwd=cwd,duration=duration,timeout=timeout);return b''
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    cp=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                      timeout=timeout,creationflags=flags)
    if cp.returncode:
        raise RuntimeError(cp.stderr.decode('utf-8',errors='replace')[-1800:] or 'A ferramenta de vídeo encerrou com erro.')
    return cp.stdout


def find_tool(name):
    """Localiza ferramentas instaladas normalmente ou junto do Streamlink/WinGet."""
    executable=name+'.exe' if os.name=='nt' and not name.lower().endswith('.exe') else name
    custom=os.environ.get('LIVECLIPS_'+name.upper())
    candidates=[]
    if custom:candidates.append(Path(custom).expanduser())
    found=shutil.which(name)
    if found:candidates.append(Path(found))
    package_root=Path(__file__).resolve().parents[1]
    candidates.extend((Path(sys.executable).parent/executable,Path(sys.executable).resolve().parent/executable,   # sem resolver: venv com atalho simbólico
                       package_root/'tools'/executable,package_root/'bin'/executable))
    if os.name=='nt':
        local=Path(os.environ.get('LOCALAPPDATA',''))
        program_data=Path(os.environ.get('ProgramData',r'C:\ProgramData'))
        candidates.extend((
            local/'Programs'/'Streamlink'/'bin'/executable,
            local/'Programs'/'Streamlink'/'ffmpeg'/executable,
            local/'Programs'/'Streamlink'/'ffmpeg'/'bin'/executable,
            program_data/'chocolatey'/'bin'/executable,
        ))
        packages=local/'Microsoft'/'WinGet'/'Packages'
        if packages.is_dir():
            candidates.extend(packages.glob('Gyan.FFmpeg*/*/bin/'+executable))
            candidates.extend(packages.glob('BtbN.FFmpeg*/*/bin/'+executable))
    seen=set()
    for candidate in candidates:
        try:resolved=candidate.resolve()
        except OSError:continue
        key=os.path.normcase(str(resolved))
        if key in seen:continue
        seen.add(key)
        if resolved.is_file():return str(resolved)
    return None


def tool(name):
    path=find_tool(name)
    if not path:raise RuntimeError(name+' não foi encontrado. Instale a ferramenta e reabra o Hook’s.')
    return path


def tool_status():
    return {name:find_tool(name) for name in ('ffmpeg','ffprobe','streamlink')}


def _unreadable(path,exc):
    """Mensagem em português para um arquivo que o ffprobe não consegue abrir (o texto técnico fica no final)."""
    name=Path(str(path)).name
    try:size=Path(str(path)).stat().st_size
    except OSError:return RuntimeError('Não consegui abrir '+name+': o arquivo não existe mais ou está sem permissão de leitura.')
    if size==0:return RuntimeError('O arquivo '+name+' está vazio (0 bytes). Confira se a cópia ou o download terminou.')
    return RuntimeError('O arquivo '+name+' não é um vídeo legível ou está corrompido. Detalhe técnico: '+str(exc)[-160:])


def probe(path):
    command=[tool('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)]
    try:data=json.loads(run(command,60))
    except RuntimeError as exc:raise _unreadable(path,exc) from None
    video=next((s for s in data.get('streams',[]) if s['codec_type']=='video'),None)
    audio=next((s for s in data.get('streams',[]) if s['codec_type']=='audio'),None)
    if not video:raise ValueError('O segmento não contém vídeo válido.')
    try:duration=float(data.get('format',{}).get('duration') or video.get('duration') or 0)
    except (TypeError,ValueError):duration=0.0
    # Capturas continuam chegando em segmentos curtos; o modo vídeo pode
    # vincular episódios e podcasts de até seis horas sem alterar o original.
    if not math.isfinite(duration) or not .1<duration<21600:raise ValueError('Duração de vídeo inválida ou acima de seis horas.')
    key=[video.get(k) for k in ('codec_name','width','height','avg_frame_rate')]
    key += [audio.get(k) if audio else None for k in ('codec_name','sample_rate','channels')]
    try:
        numerator,denominator=str(video.get('avg_frame_rate','0/1')).split('/',1)
        fps=float(numerator)/float(denominator)
        if not math.isfinite(fps) or not 1 <= fps <= 240:fps=30.0
    except (ValueError,ZeroDivisionError):
        fps=30.0
    return dict(duration=duration,width=int(video['width']),height=int(video['height']),
                fps=fps,has_audio=audio is not None,signature=json.dumps(key),video_codec=video.get('codec_name'),pix_fmt=video.get('pix_fmt'),
                audio_codec=audio.get('codec_name') if audio else None)


def audio_duration(path):
    """Duração (s) de um arquivo de áudio; levanta ValueError se não houver áudio legível."""
    data=json.loads(run([tool('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],60))
    if not any(s['codec_type']=='audio' for s in data.get('streams',[])):raise ValueError('O arquivo não contém áudio.')
    value=float(data.get('format',{}).get('duration',0))
    if not math.isfinite(value) or value<=0:raise ValueError('Duração de áudio inválida.')
    return value


_SHA_CACHE={}


def sha_file_cached(path):
    """Mesmo hash de sha_file, sem reler o arquivo enquanto tamanho e data de modificação continuam iguais.
    A primeira conferência de cada original continua lendo tudo (é ela que detecta troca de conteúdo); prévias e
    exportações seguintes do mesmo vídeo não relêem gigabytes a cada vez."""
    file=Path(path);before=file.stat();key=(str(file.resolve()),before.st_size,before.st_mtime_ns)
    hit=_SHA_CACHE.get(key)
    if hit:return hit
    value=sha_file(file);after=file.stat()
    if (after.st_size,after.st_mtime_ns)==(before.st_size,before.st_mtime_ns):   # mudou durante a leitura: não guarda
        if len(_SHA_CACHE)>=64:_SHA_CACHE.pop(next(iter(_SHA_CACHE)))
        _SHA_CACHE[key]=value
    return value


def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def visual_fingerprint(parts):
    """dHash de um quadro central para reconhecer o mesmo corte recodificado."""
    if not parts:
        return None
    durations=[max(0.0,float(p['out'])-float(p['in'])) for p in parts]
    target=sum(durations)/2
    chosen=parts[-1];local=float(chosen['in'])
    cursor=0.0
    for index,(part,duration) in enumerate(zip(parts,durations)):
        if target < cursor+duration or index==len(parts)-1:
            chosen=part;local=float(part['in'])+max(0.0,target-cursor);break
        cursor+=duration
    raw=run([tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-ss',str(local),
             '-i',str(chosen['path']),'-frames:v','1','-vf','scale=9:8:flags=area,format=gray',
             '-f','rawvideo','-pix_fmt','gray','pipe:1'],90)
    if len(raw) < 72:
        return None
    bits=0
    for row in range(8):
        base=row*9
        for col in range(8):
            bits=(bits<<1) | int(raw[base+col] > raw[base+col+1])
    return f'{bits:016x}'


def free_bytes(path):
    return shutil.disk_usage(path).free


class LowSpace(RuntimeError):
    pass


def require_space(path, min_gb=3, extra=0):
    free=free_bytes(path)
    if free < float(min_gb)*1024**3+extra:
        raise LowSpace(f'Espaço baixo: {free/1024**3:.1f} GB livres. Libere espaço ou ajuste a reserva no perfil. Nenhum vídeo foi apagado.')
    return free


def frame(source, target, at=2):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    run([tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(at),
         '-i',str(source),'-frames:v','1','-vf','scale=960:-2:flags=lanczos',str(target)],90)
    return target


def clip_audio(parts,target):
    """Áudio mono 16 kHz do corte inteiro (todos os trechos de origem em sequência), para transcrever de novo."""
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    args=[tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y']
    for part in parts:
        args+=['-ss',f"{float(part['in']):.6f}",'-to',f"{float(part['out']):.6f}",'-i',str(part['path'])]
    if len(parts)==1:
        args+=['-vn','-ac','1','-ar','16000',str(target)]
    else:
        chain=''.join(f'[{i}:a]' for i in range(len(parts)))
        args+=['-filter_complex',f'{chain}concat=n={len(parts)}:v=0:a=1[a]','-map','[a]','-ac','1','-ar','16000',str(target)]
    run(args,600)
    return target


def style_demo(root,style):
    """Amostra leve e livre de direitos: mesma cor, curva de zoom e legenda do render real."""
    if style not in EDITOR_PRESETS:raise ValueError('Estilo de edição inválido.')
    folder=Path(root)/'cache'/'demos_editor_v2';folder.mkdir(parents=True,exist_ok=True)
    target=folder/(style+'.mp4')
    if target.is_file() and target.stat().st_size>1000:return target
    look=LOOKS[style];fps=30;length=6.0
    punches=[dict(start=2.0,end=2.85,zoom=min(1.12,EDITOR_PRESETS[style]['zoom_max']))] if EDITOR_PRESETS[style]['zoom'] else []
    words=[('isso',.4),('foi',.9),('absurdo',1.3),('meu',2.2),('deus',2.6),('não',3.4),('acredito',3.9)]
    segment=dict(start=.4,end=4.5,text=' '.join(w for w,_ in words),
                 words=[dict(start=t,end=t+.42,word=w) for w,t in words])
    ass=make_ass([segment],0,length,32,170,'00E8FF',resolve_style('auto',look),emphasis=[2.2])
    (folder/(style+'.ass')).write_text(ass,encoding='utf-8-sig')
    base=('testsrc2=size=360x640:rate=30:duration=6,'
          'drawbox=x=0:y=0:w=360:h=188:color=0x102a45:t=fill,'
          'drawbox=x=16:y=18:w=150:h=150:color=0x4da3ff@0.42:t=fill')
    chain=base+camera_zoom_filter(punches,fps,360,640,curve=look['curve'],push=look.get('push'),duration=length)
    grade=grade_filters(look.get('grade'))
    chain+=(','+grade if grade else '')+f',ass={style}.ass,format=yuv420p'
    run([tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-f','lavfi','-i',chain,
         '-an','-c:v','libx264','-preset','veryfast','-crf','28','-movflags','+faststart',target.name],120,cwd=str(folder))
    (folder/(style+'.ass')).unlink(missing_ok=True)
    return target


def assemble(parts, scratch, threads=3):
    """Normaliza só as fatias necessárias; não supõe segmentos de 60 segundos."""
    if not parts:raise ValueError('Nenhuma mídia para montar.')
    if len(parts)==1:
        return Path(parts[0]['path']),parts[0]['in'],parts[0]['out']-parts[0]['in']
    files=[]
    first=probe(parts[0]['path'])
    # Preserva até 1440p. A V6 reduzia toda montagem entre arquivos para
    # 1280 px antes do recorte da webcam, destruindo detalhes que a exportação
    # vertical tentava ampliar novamente.
    width=min(2560,first['width'])//2*2
    height=max(2,round(first['height']*width/first['width']/2)*2)
    output_fps=60 if first.get('fps',30)>=50 else 30
    for i,part in enumerate(parts):
        info=probe(part['path'])
        target=Path(scratch)/f'parte_{i:03}.mkv'
        duration=part['out']-part['in']
        # O seek vem depois da entrada para decodificar desde o keyframe anterior.
        # O seek rápido antes de -i fazia alguns arquivos H.264 começarem vários
        # segundos atrasados ao atravessar a fronteira entre segmentos.
        args=[tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y',
              '-threads',str(threads),'-i',str(part['path']),'-ss',str(part['in'])]
        if not info['has_audio']:args += ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        args += ['-t',str(duration),'-map','0:v:0','-map','0:a:0' if info['has_audio'] else '1:a:0',
                 '-vf',f'scale={width}:{height}:flags=lanczos,setsar=1,fps={output_fps}',
                 '-c:v','libx264','-preset','veryfast','-crf','15','-threads',str(threads),
                 '-c:a','aac','-ar','48000','-ac','2','-b:a','160k',str(target)]
        run(args)
        files.append(target.name)
    manifest=Path(scratch)/'partes.txt'
    manifest.write_text(''.join(f"file '{name}'\n" for name in files),encoding='utf-8')
    joined=Path(scratch)/'unido.mkv'
    run([tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-f','concat',
         '-safe','1','-i',manifest.name,'-c','copy',joined.name],cwd=scratch)
    return joined,0,sum(p['out']-p['in'] for p in parts)


def compact_source(source,offset,duration,cuts,scratch,threads=3):
    """Remove apenas intervalos aprovados e mantém áudio/vídeo sincronizados."""
    intervals=keep_intervals(duration,cuts)
    # Mesmo sem cortes internos, normalize trechos que começam no meio da fonte.
    # Assim overlays, música e efeitos começam em zero junto com o clipe, em vez
    # de herdarem o relógio do vídeo longo e desaparecerem ou saírem de sincronia.
    if (not cuts or len(intervals)==1 and intervals[0]==(0.,duration)) and abs(offset)<.001:
        return source,offset,duration
    if not intervals or sum(b-a for a,b in intervals)<1:raise ValueError('As decisões removeriam todo o corte.')
    info=probe(source);filters=[];inputs=[]
    for index,(a,b) in enumerate(intervals):
        filters.append(f'[0:v]trim=start={offset+a}:end={offset+b},setpts=PTS-STARTPTS[v{index}]')
        inputs.append(f'[v{index}]')
        if info['has_audio']:
            filters.append(f'[0:a]atrim=start={offset+a}:end={offset+b},asetpts=PTS-STARTPTS[a{index}]')
            inputs.append(f'[a{index}]')
    target=Path(scratch)/'compactado.mkv';count=len(intervals)
    filters.append(''.join(inputs)+f'concat=n={count}:v=1:a={1 if info["has_audio"] else 0}[v]'+('[a]' if info['has_audio'] else ''))
    args=[tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-threads',str(threads),
          '-i',str(source),'-filter_complex',';'.join(filters),'-map','[v]']
    if info['has_audio']:args += ['-map','[a]']
    args += ['-c:v','libx264','-preset','ultrafast','-crf','12','-pix_fmt','yuv420p']
    if info['has_audio']:args += ['-c:a','aac','-b:a','192k']
    args += [str(target)]
    run(args,cwd=scratch)
    return target,0,sum(b-a for a,b in intervals)


def edit_assets(candidate,root=None,final=False):
    """Aceita somente recursos locais explicitamente habilitados e suportados."""
    limits={'overlay':(('.png','.jpg','.jpeg','.webp'),20*1024**2),
            'sfx':(('.wav','.mp3','.m4a','.aac','.flac','.ogg'),100*1024**2),
            'music':(('.wav','.mp3','.m4a','.aac','.flac','.ogg'),500*1024**2)}
    result=[]
    for item in decisions_for(candidate):
        if not item.get('enabled') or item.get('kind') not in limits:continue
        path=Path(str(item.get('path',''))).expanduser()
        extensions,maximum=limits[item['kind']]
        try:resolved=path.resolve(strict=True)
        except (OSError,RuntimeError):raise ValueError('Um recurso de edição não foi encontrado: '+str(path))
        if resolved.suffix.lower() not in extensions or not resolved.is_file() or resolved.stat().st_size>maximum:
            raise ValueError('Um recurso de edição tem formato ou tamanho inválido: '+str(path))
        value=dict(item,path=str(resolved));result.append(value)
    extra=project_assets(candidate,root,final)
    if any(item['kind']=='music' for item in extra):result=[item for item in result if item['kind']!='music']
    return result+extra


def project_assets(candidate,root,final):
    """Música, efeitos e imagens escolhidos no editor (o projeto manda sobre o plano automático)."""
    project=project_of(candidate);result=[]
    if not project:return result
    duration=float(candidate['end'])-float(candidate['start'])
    chosen=project.get('music')
    if chosen:
        if root is None:raise ValueError('Pasta de dados indisponível para localizar a música.')
        from . import music as library
        item=library.get(root,chosen['id'])
        if final and not chosen.get('authorized'):
            raise ValueError('Confirme que você tem autorização para usar a música escolhida antes de exportar.')
        result.append(dict(kind='music',id='project:music',path=str(library.path_of(root,chosen['id'])),start=0.0,end=duration,
                           volume=chosen['volume'],offset=chosen['start'],fade_in=chosen['fade_in'],fade_out=chosen['fade_out'],
                           duck=chosen['duck'],title=item['title'],uploader=item.get('uploader',''),url=item.get('url','')))
    for index,item in enumerate(project.get('overlays',[])):
        if root is None:raise ValueError('Pasta de dados indisponível para localizar as imagens.')
        from . import assets as images
        try:path=images.path_of(root,item['image'])
        except ValueError:raise ValueError('Uma imagem usada no clipe saiu da biblioteca. Troque ou remova a imagem no editor.') from None
        result.append(dict(kind='overlay',id=f'project:img{index}',path=str(path),start=float(item['start']),end=float(item['end']),
                           x=float(item['x']),y=float(item['y']),scale=float(item['scale']),opacity=float(item['opacity']),
                           **{k:item[k] for k in ('key','mask','blend') if k in item}))
    for index,effect in enumerate(project.get('sfx',[])):
        if root is None:raise ValueError('Pasta de dados indisponível para gerar os efeitos sonoros.')
        from . import sfx as effects
        path=effects.ensure(root,effect['kind']);seconds=effects.EFFECTS[effect['kind']][1]
        result.append(dict(kind='sfx',id=f'project:sfx{index}',path=str(path),start=float(effect['at']),
                           end=float(effect['at'])+seconds,volume=float(effect.get('volume',.6))))
    return result


def srt(segments,start,end):
    def clock(t):
        ms=max(0,round(t*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    lines=[]
    for seg in segments:
        a,b=max(start,float(seg['start'])),min(end,float(seg['end']))
        if b<=a:continue
        lines += [str(len(lines)//4+1),clock(a-start)+' --> '+clock(b-start),str(seg['text']).replace('\n',' '),'']
    return '\n'.join(lines)


def signature(candidate):
    value={k:candidate[k] for k in ('id','start','end','parts','profile')}
    value['captions']=candidate.get('data',{}).get('transcript_segments',[])
    value['edit_plan']=candidate.get('data',{}).get('edit_plan',{})
    value['edit_overrides']=candidate.get('data',{}).get('edit_overrides',{})
    value['project']=candidate.get('data',{}).get('project')
    if candidate.get('data',{}).get('auto_title'):value['auto_title']=candidate['data']['auto_title']   # só entra quando existe: assinaturas antigas não mudam
    if candidate.get('data',{}).get('motion_context'):value['motion_context']=candidate['data']['motion_context']   # idem: só entra quando existe
    value['renderer_version']=RENDERER_VERSION
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def receipt(candidate, exports):
    target=Path(exports)/(candidate['id']+'_'+signature(candidate)[:12])
    manifest=target/'manifesto.json'
    if manifest.is_file() and (target/'clipe.mp4').is_file():
        data=json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('signature')==signature(candidate) and sha_file(target/'clipe.mp4')==data.get('video_sha'):
            return target/'clipe.mp4'
    return None


def dynamic_reframe_plan(source,offset,duration,info,step=1.5):
    """Amostra cenas/rostos localmente; ausência ou grupo aberto preserva o quadro."""
    try:
        import cv2
    except ImportError:
        return []
    if info['width']/info['height'] <= 9/16+.02:
        return []
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened() or cascade.empty():return []
    points=[];smooth=None;previous=None;t=0.0
    crop_ratio=(info['height']*9/16)/info['width']
    try:
        while t<duration and len(points)<180:
            cap.set(cv2.CAP_PROP_POS_MSEC,(offset+t)*1000)
            ok,frame=cap.read()
            if not ok:break
            height,width=frame.shape[:2];scale=min(1.0,640/max(1,width))
            small=cv2.resize(frame,(max(2,int(width*scale)),max(2,int(height*scale))))
            gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
            scene_frame=cv2.resize(gray,(32,18))
            scene=previous is not None and float(cv2.absdiff(previous,scene_frame).mean())>24
            previous=scene_frame
            faces=cascade.detectMultiScale(gray,scaleFactor=1.12,minNeighbors=5,
                                            minSize=(max(24,int(45*scale)),max(24,int(45*scale))))
            face=False;target=.5
            if len(faces):
                left=min(x for x,y,w,h in faces)/small.shape[1]
                right=max(x+w for x,y,w,h in faces)/small.shape[1]
                # Um grupo que não cabe confortavelmente volta ao quadro integral.
                if right-left <= crop_ratio*.88:
                    weights=[max(1,w*h) for x,y,w,h in faces]
                    target=sum((x+w/2)*weight for (x,y,w,h),weight in zip(faces,weights))/sum(weights)/small.shape[1]
                    face=True
            if face:
                smooth=target if smooth is None or scene else smooth*.68+target*.32
            else:
                smooth=None
            points.append(dict(start=round(t,3),end=round(min(duration,t+step),3),
                               face=face,x=round(smooth if smooth is not None else .5,5),scene=scene))
            t+=step
    finally:cap.release()
    return points


def reframe_points(profile,source,offset,duration,info):
    """Plano de enquadramento: 'speaker' segue quem fala (se for uma cena de 2–3 pessoas); senão, o rastreio comum.
    No modo sem IA não há detecção de rosto: o enquadramento fica no padrão do perfil."""
    if profile.get('reframe_mode')=='rastreio':
        # Rastreio clássico (fluxo óptico) da região marcada no perfil; não usa IA e vale no modo sem IA.
        from . import track
        try:return track.track_plan(source,offset,duration,info,profile.get('track_roi'))
        except Exception:return []
    if profile.get('ai_mode')=='sem_ia':return []
    if profile.get('reframe_mode')=='speaker':
        from . import speaker
        try:points=speaker.speaker_plan(source,offset,duration,info)
        except Exception:points=[]
        if points:return points
    return dynamic_reframe_plan(source,offset,duration,info)


CANVAS={'9x16':(1080,1920),'1x1':(1080,1080),'4x5':(1080,1350),'16x9':(1920,1080)}


def video_filters(output_fps,info,plan=None,source='0:v',canvas=(1080,1920),mode='fit',focus=.5,draft=False):
    """Quadro seguro; sobrepõe close rastreado apenas em intervalos confiáveis.

    `mode`: 'fit' (inteiro, fundo desfocado) ou 'fill' (preenche e corta, com `focus` horizontal 0-1)."""
    W,H=canvas
    if mode=='fill':
        crop=f'crop={W}:{H}' if abs(focus-.5)<1e-6 else f"crop={W}:{H}:x='(iw-ow)*{focus:g}':y='(ih-oh)/2'"
        return (f'[{source}]fps={output_fps},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,{crop},'
                'setsar=1,format=yuv420p[base]')
    vertical=(W,H)==(1080,1920)
    face_points=[p for p in (plan or []) if p['face']] if vertical else []
    scaled_width=max(W,round(info['width']*H/info['height']/2)*2)
    dynamic=bool(face_points and scaled_width>W)
    split='split=3[bg][fg][zoom]' if dynamic else 'split=2[bg][fg]'
    if draft:   # rascunho: o fundo é só um borrão; borra em 1/4 do tamanho e amplia (medido ~2,4x mais rápido, mesmo quadro final)
        w4,h4=max(2,round(W/8)*2),max(2,round(H/8)*2)
        blur=(f'scale={w4}:{h4}:force_original_aspect_ratio=increase:flags=bilinear,crop={w4}:{h4},'
              f'gblur=sigma=7,scale={W}:{H}:flags=bilinear')
    else:
        blur=f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},gblur=sigma=28'
    common=(f'[{source}]fps={output_fps},{split};'
            f'[bg]{blur}[blur];'
            f'[fg]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1[front];'
            '[blur][front]overlay=(W-w)/2:(H-h)/2[safe]')
    if not dynamic:return common+';[safe]setsar=1,format=yuv420p[base]'
    center=max(0,(scaled_width-1080)//2);expr=str(center)
    for index in range(len(plan)-1,-1,-1):
        point=plan[index]
        if not point['face']:continue
        target=max(0,min(scaled_width-1080,round(point['x']*scaled_width-540)))
        following=plan[index+1] if index+1<len(plan) and plan[index+1]['face'] else point
        next_target=max(0,min(scaled_width-1080,round(following['x']*scaled_width-540)))
        span=max(.01,point['end']-point['start'])
        value=f'{target}+({next_target-target})*max(0,min(1,(t-{point["start"]})/{span}))'
        expr=f'if(lt(t,{point["end"]}),{value},{expr})'
    enabled='+'.join(f'between(t,{p["start"]},{p["end"]})' for p in face_points)
    return (common+f';[zoom]scale=-2:1920:flags=lanczos,crop=1080:1920:x=\'{expr}\':y=0,setsar=1[close];'
                   f'[safe][close]overlay=0:0:enable=\'{enabled}\',setsar=1,format=yuv420p[base]')


def run_stderr(args,timeout=600,cwd=None):
    """Executa e devolve o stderr (onde o FFmpeg escreve medições como o loudnorm)."""
    duration=progress.take_duration()
    if duration:return progress.run_ffmpeg(args,cwd=cwd,duration=duration,timeout=timeout,capture_stderr=True)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    cp=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,creationflags=flags)
    if cp.returncode:raise RuntimeError(cp.stderr.decode('utf-8',errors='replace')[-1800:] or 'A medição de áudio falhou.')
    return cp.stderr.decode('utf-8',errors='replace')


def loudnorm_filter(measured=None):
    base=f"loudnorm=I={LOUDNESS['I']}:LRA={LOUDNESS['LRA']}:TP={LOUDNESS['TP']}"
    if not measured:return base
    return (base+f":measured_I={measured['input_i']}:measured_LRA={measured['input_lra']}"
            f":measured_TP={measured['input_tp']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true")


def linear_feasible(measured):
    """Ganho linear só quando o pico verdadeiro resultante cabe no limite (0,3 dB de folga para o AAC).

    Sem margem, o loudnorm cairia no modo dinâmico, que em testes sintéticos deixou o pico
    verdadeiro perto de 0 dBTP após a codificação. Nesse caso mantemos o método da V7.
    """
    gain=LOUDNESS['I']-measured['input_i']
    return measured['input_tp']+gain<=LOUDNESS['TP']-.3


def parse_loudness(text):
    """Extrai o JSON do loudnorm; devolve None para silêncio ou valores fora do domínio."""
    start,end=text.rfind('{'),text.rfind('}')
    if start<0 or end<start:return None
    try:data=json.loads(text[start:end+1])
    except ValueError:return None
    try:values={key:float(data[key]) for key in ('input_i','input_tp','input_lra','input_thresh','target_offset')}
    except (KeyError,TypeError,ValueError):return None
    if not all(math.isfinite(v) for v in values.values()) or not -70<values['input_i']<0:return None
    return values


def source_pieces(parts,intervals,strict=True):
    """Converte intervalos do clipe (tempo contínuo das partes) em trechos locais de cada arquivo."""
    spans=[];cursor=0.0
    for index,part in enumerate(parts):
        length=float(part['out'])-float(part['in']);spans.append((index,cursor,cursor+length,float(part['in'])));cursor+=length
    pieces=[]
    for a,b in intervals:
        for index,low,high,local in spans:
            x,y=max(a,low),min(b,high)
            if y-x>.02:pieces.append((index,round(local+(x-low),4),round(local+(y-low),4)))
    if not pieces and strict:raise ValueError('As decisões removeriam todo o corte.')
    return pieces


def locate(parts,moment):
    """(parte, tempo local no arquivo) de um instante do clipe."""
    cursor=0.0
    for index,part in enumerate(parts):
        length=float(part['out'])-float(part['in'])
        if moment<=cursor+length+1e-6 or index==len(parts)-1:
            return index,round(float(part['in'])+min(max(moment-cursor,0.0),length),4)
        cursor+=length


def plan_pieces(parts,remap,teaser=None):
    """Trechos (parte, início, fim, velocidade, congelar) na ordem final: abertura, depois o clipe.

    `congelar` > 0 marca um quadro parado (início/fim apontam para o quadro); velocidade vem do Remap."""
    pieces=[]
    if teaser:pieces += [(i,a,b,1.0,0.0) for i,a,b in source_pieces(parts,[teaser])]
    for item in remap.sequence:
        x,y,_,rate,hold=item[:5]
        if rate is None:
            index,local=locate(parts,x);start=max(0.0,round(local-.04,4))
            pieces.append((index,start,round(local+.2,4),1.0,round(hold,4)))
        elif len(item)>5:   # replay: mesmo trecho de novo, com o áudio original ou mudo
            pieces += [(i,a,b,rate,0.0,bool(item[5]['mute'])) for i,a,b in source_pieces(parts,[(x,y)],strict=False)]
        else:
            pieces += [(i,a,b,rate,0.0) for i,a,b in source_pieces(parts,[(x,y)],strict=False)]
    if not pieces:raise ValueError('As decisões removeriam todo o corte.')
    return pieces


def tempo_chain(rate):
    """`atempo` só aceita 0,5 a 2 por etapa em FFmpeg antigos: divide em etapas seguras."""
    steps=[];value=float(rate)
    while value>2.0:steps.append('atempo=2.0');value/=2.0
    while value<.5:steps.append('atempo=0.5');value*=2.0
    steps.append(f'atempo={value:.6f}')
    return ','.join(steps)


CUT_FADES={'off':0.0,'suave':0.02,'media':0.04}


def cut_fade(profile):
    """Duração (s) do fade curto de áudio em cada emenda entre trechos (tira estalos; 0 = como antes)."""
    return CUT_FADES.get((profile or {}).get('cut_fade','off'),0.0)


INTERP_MODES={'off':None,'mistura':'blend','movimento':'mci'}
INTERP_MAX_SECONDS=6.0     # câmera lenta mais longa que isso não é interpolada (custo e artefatos)


def slow_interp(profile):
    """Modo de interpolação da câmera lenta do perfil (None = repetir quadros, como antes)."""
    return INTERP_MODES.get((profile or {}).get('slow_interp','off'))


STABILIZE={'off':None,'leve':'deshake=rx=16:ry=16:edge=mirror','forte':'deshake=rx=32:ry=32:edge=mirror'}


def stabilize_filter(profile,meta=None):
    """Estabilização leve de câmera na mão (P18), de uma passada. Desligada por padrão; sem o filtro, segue sem estabilizar e avisa."""
    mode=(profile or {}).get('stabilize','off');text=STABILIZE.get(mode)
    if not text:return ''
    if not has_filter('deshake'):
        if meta is not None:meta['stabilize_skipped']='O FFmpeg deste computador não tem o filtro de estabilização.'
        return ''
    return text


def build_source(parts,infos,pieces,video=True,audio=True,fade=0.0,interp=None,external=None):
    """Filtergraph único: apara, normaliza e une os trechos mantidos direto das fontes originais.

    Substitui assemble + compact_source (2 a 3 recodificações) por uma só passada: o clipe
    é codificado uma única vez, no render final. Retorna (argumentos de entrada, filtros).
    """
    multi=len(parts)>1;first=infos[0]
    width=min(2560,first['width'])//2*2;height=max(2,round(first['height']*width/first['width']/2)*2)
    fps=60 if first.get('fps',30)>=50 else 30
    # Arquivos longos (vídeo local): busca grossa na entrada para não decodificar desde o início.
    args=[];seek={};order={}
    for number,part_index in enumerate(sorted({piece[0] for piece in pieces})):
        starts=[piece[1] for piece in pieces if piece[0]==part_index]
        coarse=0
        if infos[part_index]['duration']>180 and min(starts)>60:coarse=int(min(starts))-5
        seek[part_index]=coarse;order[part_index]=number
        if coarse:args += ['-ss',str(coarse)]
        args += ['-i',str(parts[part_index]['path'])]
    ext_input=None
    if external and audio and len(parts)==1:      # áudio gravado à parte (P06): entra no lugar do áudio do arquivo, pelo deslocamento medido
        ext_input=len(order);args += ['-i',str(external['path'])]
    filters=[];joined=[]
    for n,piece in enumerate(pieces):
        index,a,b=piece[:3];rate=float(piece[3]) if len(piece)>3 else 1.0;hold=float(piece[4]) if len(piece)>4 else 0.0
        k=order[index];offset=seek[index];a,b=round(a-offset,4),round(b-offset,4)
        if video:
            chain=f'[{k}:v:0]trim=start={a}:end={b},setpts=PTS-STARTPTS'
            if hold:chain+=f',fps={fps},trim=end_frame=1,tpad=stop_mode=clone:stop_duration={hold:g},trim=duration={hold:g},setpts=PTS-STARTPTS'
            elif abs(rate-1)>.001:
                chain+=f',setpts=(PTS-STARTPTS)/{rate:g}'
                if interp and rate<1 and (b-a)/rate<=INTERP_MAX_SECONDS:chain+=f',minterpolate=fps={fps}:mi_mode={interp}'
            if multi:
                info=infos[index]
                if (info['width'],info['height'])!=(width,height):chain+=f',scale={width}:{height}:flags=lanczos'
                chain+=f',setsar=1,fps={fps}'
            filters.append(chain+f'[v{n}]');joined.append(f'[v{n}]')
        if audio:
            if hold:
                filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={hold:g},asetpts=PTS-STARTPTS[a{n}]')
            elif len(piece)>5 and piece[5]:
                filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={round((b-a)/rate,4)},asetpts=PTS-STARTPTS[a{n}]')
            elif ext_input is not None:
                span=round((b-a)/rate,4);speed=f',{tempo_chain(rate)}' if abs(rate-1)>.001 else ''
                s0,e0=a+float(external['offset']),b+float(external['offset']);lead=max(0.0,-s0);s0=max(0.0,s0)
                pad=f',adelay={round(lead*1000)}:all=1' if lead>0 else ''
                shape=''
                if fade>0 and len(pieces)>1 and span>fade*4:
                    if n>0:shape+=f',afade=t=in:st=0:d={fade:g}'
                    if n<len(pieces)-1:shape+=f',afade=t=out:st={round(span-fade,4):g}:d={fade:g}'
                filters.append(f'[{ext_input}:a:0]atrim=start={s0:g}:end={max(s0+.05,e0):g},asetpts=PTS-STARTPTS{pad}{speed},aresample=48000,'
                               f'aformat=sample_fmts=fltp:channel_layouts=stereo,apad=whole_dur={span:g},atrim=duration={span:g}{shape}[a{n}]')
            elif infos[index]['has_audio']:
                speed=f',{tempo_chain(rate)}' if abs(rate-1)>.001 else ''
                shape=''
                span=(b-a)/rate
                if fade>0 and len(pieces)>1 and span>fade*4:   # emenda entre trechos: sobe/desce em milissegundos, sem mexer na duração
                    if n>0:shape+=f',afade=t=in:st=0:d={fade:g}'
                    if n<len(pieces)-1:shape+=f',afade=t=out:st={round(span-fade,4):g}:d={fade:g}'
                filters.append(f'[{k}:a:0]atrim=start={a}:end={b},asetpts=PTS-STARTPTS{speed},aresample=48000,'
                               f'aformat=sample_fmts=fltp:channel_layouts=stereo{shape}[a{n}]')
            else:
                filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={round((b-a)/rate,4)},asetpts=PTS-STARTPTS[a{n}]')
            joined.append(f'[a{n}]')
    outs=('[srcv]' if video else '')+('[srca]' if audio else '')
    filters.append(''.join(joined)+f'concat=n={len(pieces)}:v={int(video)}:a={int(audio)}{outs}')
    return args,';'.join(filters)


def voice_mode(project,root,scratch,meta,profile=None):
    """'neural' | True (limpeza leve) | False. Copia o modelo para a pasta de trabalho (o FFmpeg lê por nome relativo)."""
    from . import denoise
    voice=(project or {}).get('voice') or {}
    if not voice.get('clean'):return False
    if voice.get('mode')!='neural':return True
    if (profile or {}).get('ai_mode')=='sem_ia':
        meta['voice_warning']='Modo sem IA: usei a limpeza clássica de ruído (sem modelo neural).'
        return True
    if root and denoise.status(root)['ready']:
        import shutil
        shutil.copyfile(denoise.path(root),Path(scratch)/'rnnoise.rnnn')
        return 'neural'
    meta['voice_warning']='Modelo de redução de ruído neural não instalado; usei a limpeza leve.'
    return True


_FILTERS={}


def has_filter(name):
    """O FFmpeg deste computador tem o filtro? (cache por processo; falha de leitura = não tem)."""
    if not _FILTERS:
        try:
            out=run([tool('ffmpeg'),'-hide_banner','-filters'],timeout=30).decode('utf-8',errors='replace')
            for line in out.splitlines():
                parts=line.split()
                if len(parts)>=2 and len(parts[0])<=4:_FILTERS[parts[1]]=True
        except Exception:_FILTERS['__erro__']=True
    return bool(_FILTERS.get(name))


# Cadeia de voz clássica (P12): equalização suave, de-esser e compressor. Sem modelo, sem IA.
VOICE_PRESETS={
    'off':[],
    'natural':[('equalizer','equalizer=f=250:t=q:w=1.0:g=-1.5'),('equalizer','equalizer=f=3500:t=q:w=1.2:g=1.5'),
               ('deesser','deesser=i=0.3:m=0.5:f=0.5'),('acompressor','acompressor=threshold=-20dB:ratio=2.5:attack=20:release=250:makeup=2')],
    'forte':[('equalizer','equalizer=f=200:t=q:w=1.0:g=-3'),('equalizer','equalizer=f=3800:t=q:w=1.2:g=3'),
             ('deesser','deesser=i=0.5:m=0.6:f=0.5'),('acompressor','acompressor=threshold=-24dB:ratio=3.5:attack=15:release=200:makeup=4')],
}


def voice_filters(profile,meta=None):
    """Trecho de filtros da cadeia de voz do perfil. Filtro ausente neste FFmpeg é pulado e registrado em `meta['voice_skipped']`."""
    preset=(profile or {}).get('voice_preset','off')
    chosen=[];skipped=[]
    for name,text in VOICE_PRESETS.get(preset,[]):
        (chosen if has_filter(name) else skipped).append(text if has_filter(name) else name)
    if skipped and meta is not None:meta['voice_skipped']=skipped
    return (','+','.join(chosen)) if chosen else ''


def audio_chain(source,indexed,profile,duration,loudnorm,voice_clean=False,meta=None):
    """Voz (opcionalmente limpa) + música (com ducking e fades) + efeitos, terminando em [aout]."""
    base=f'[{source}]aresample=48000'
    if voice_clean=='neural':base+=',highpass=f=70,arnndn=m=rnnoise.rnnn:mix=.9'   # modelo copiado para a pasta de trabalho
    elif voice_clean:base+=',highpass=f=70,afftdn=nr=12:nf=-45:tn=1'
    base+=voice_filters(profile,meta)
    filters=base+'[voice]';audio='voice';number=0
    for index,asset in indexed:
        if asset['kind']=='music':
            volume=max(.02,min(.6,float(asset.get('volume',profile.get('music_volume',.08)))))
            offset=max(0.0,float(asset.get('offset',0)));fade_in=float(asset.get('fade_in',0));fade_out=float(asset.get('fade_out',0))
            chain=f'[{index}:a]atrim=start={offset:g}:duration={duration:g},asetpts=PTS-STARTPTS'
            if fade_in>0:chain+=f',afade=t=in:st=0:d={fade_in:g}'
            if fade_out>0:chain+=f',afade=t=out:st={max(0,duration-fade_out):g}:d={fade_out:g}'
            filters+=f';{chain},volume={volume}[music{number}]'
            if asset.get('duck',True):
                # Um rótulo de saída só pode ser consumido uma vez: divide a voz entre o detector e a mistura.
                filters+=f';[{audio}]asplit=2[side{number}][keep{number}]'
                filters+=f';[music{number}][side{number}]sidechaincompress=threshold=.06:ratio=8:attack=20:release=350[duck{number}]'
                filters+=f';[keep{number}][duck{number}]amix=inputs=2:duration=first:dropout_transition=0[mix{number}]'
            else:
                filters+=f';[{audio}][music{number}]amix=inputs=2:duration=first:dropout_transition=0[mix{number}]'
            audio=f'mix{number}';number+=1
        elif asset['kind']=='sfx':
            delay=max(0,round(float(asset['start'])*1000));volume=float(asset.get('volume',.55))
            filters+=f';[{index}:a]atrim=0:{max(.1,asset["end"]-asset["start"])},asetpts=PTS-STARTPTS,adelay={delay}:all=1,volume={volume}[sfx{number}]'
            filters+=f';[{audio}][sfx{number}]amix=inputs=2:duration=first:dropout_transition=0[mix{number}]';audio=f'mix{number}';number+=1
    return filters+f';[{audio}]{loudnorm},alimiter=limit=.84:attack=3:release=60:level=0[aout]'   # trava de pico (~-1,5 dBFS)


LIVE_LAYOUTS=('cam_top','split','game_pip','cam_full')
VIDEO_LAYOUTS=('fit','fill')


def resolve_layout(profile,layout,canvas):
    """Layout efetivo para esse conteúdo e esse quadro (modos que não se aplicam voltam ao padrão)."""
    layout=layout or {};W,H=canvas;video=profile.get('content_mode','live')=='video'
    mode=layout.get('mode')
    if video:
        default='fill' if H>=W and (W,H)!=(1080,1920) else 'fit'
        mode=mode if mode in VIDEO_LAYOUTS else default
    elif W>H:mode='wide'
    else:mode=mode if mode in LIVE_LAYOUTS else 'cam_top'
    return dict(mode=mode,focus=float(layout.get('focus',.5)),pip=layout.get('pip','tr'),pip_size=float(layout.get('pip_size',.36)))


def _rounded(size,radius):
    """Máscara de canto arredondado (canal alfa) para a câmera pequena."""
    inner=f'(abs(X-{size}/2)-({size}/2-{radius}))';inner_y=f'(abs(Y-{size}/2)-({size}/2-{radius}))'
    return (f"geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':a='if(gt({inner},0)*gt({inner_y},0),"
            f"if(lte(hypot({inner},{inner_y}),{radius}),255,0),255)'")


def live_filters(profile,info,punches,look,fps,duration,push,supersample,canvas,layout,vsrc):
    """Câmera + jogo no quadro vertical (ou 1:1, 4:5) segundo o layout."""
    if not profile.get('camera_rect'):raise ValueError('A webcam deste streamer não está marcada. Vá em Ajustes → Webcam e quadro, marque a webcam e salve; depois tente de novo.')
    W,H=canvas;mode=layout['mode'];focus=layout['focus']
    x,y,w,h=profile['camera_rect']
    cw=max(4,int(info['width']*w)//2*2);ch=max(4,int(info['height']*h)//2*2)
    cx=min(int(info['width']*x)//2*2,info['width']-cw);cy=min(int(info['height']*y)//2*2,info['height']-ch)

    def zoom(width,height):
        return camera_zoom_filter(punches,fps,width=width,height=height,curve=look.get('curve','smooth'),push=push,
                                  duration=duration,supersample=supersample)

    def cam(width,height):
        return (f'crop={cw}:{ch}:{cx}:{cy},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,'
                f'crop={width}:{height},setsar=1')

    def game(width,height):
        crop=f'crop={width}:{height}' if abs(focus-.5)<1e-6 else f"crop={width}:{height}:x='(iw-ow)*{focus:g}':y='(ih-oh)/2'"
        return f'scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,{crop},setsar=1'

    if mode=='cam_full':
        return f'[{vsrc}]fps={fps},{cam(W,H)}{zoom(W,H)},format=yuv420p[base]'
    if mode=='game_pip':
        size=max(120,int(W*layout['pip_size'])//2*2);radius=max(16,size//8);ring=size+8
        margin=40;corner=layout['pip']
        px=margin if corner[1]=='l' else W-size-margin
        py=int(H*.08) if corner[0]=='t' else H-size-int(H*.27)
        return (f'[{vsrc}]fps={fps},split=2[c][g];[g]{game(W,H)}{zoom(W,H)}[game];'
                f'[c]{cam(size,size)},format=yuva420p,{_rounded(size,radius)}[pip];'
                f'color=c=white:s={ring}x{ring}:d={duration:g}:r={fps},format=yuva420p,{_rounded(ring,radius+4)}[ring];'
                f'[game][ring]overlay={px-4}:{py-4}:shortest=1[ringed];'
                f'[ringed][pip]overlay={px}:{py}:shortest=1,setsar=1,format=yuv420p[base]')
    share=.5 if mode=='split' else 1/3
    cam_h=max(2,round(H*share/2)*2);game_h=H-cam_h
    return (f'[{vsrc}]fps={fps},split=2[c][g];[c]{cam(W,cam_h)}{zoom(W,cam_h)}[cam];'
            f'[g]{game(W,game_h)}[game];[cam][game]vstack=inputs=2,setsar=1,format=yuv420p[base]')


def blur_graph(regions,width,height,src,dst):
    """Borra regiões fixas da imagem de origem (frações 0–1). Devolve o trecho de filtergraph src→dst, ou '' sem regiões.

    Roda antes de qualquer corte, zoom ou layout: o que foi borrado não reaparece em nenhum plano."""
    boxes=[]
    for region in regions or []:
        try:x,y,w,h=[float(region[k]) for k in ('x','y','w','h')]
        except (KeyError,TypeError,ValueError):continue
        px=max(0,int(x*width)//2*2);py=max(0,int(y*height)//2*2)
        pw=min(width-px,int(round(w*width/2+.4))*2)//2*2;ph=min(height-py,int(round(h*height/2+.4))*2)//2*2
        if pw>=8 and ph>=8:boxes.append((px,py,pw,ph))
    if not boxes:return ''
    parts=[];current=src
    for number,(px,py,pw,ph) in enumerate(boxes):
        radius=max(2,min(pw,ph)//4);chroma=max(1,min(pw,ph)//8);last=number==len(boxes)-1
        out=dst if last else f'bl{number}'
        parts.append(f'[{current}]split=2[ba{number}][bb{number}]')
        parts.append(f'[bb{number}]crop={pw}:{ph}:{px}:{py},boxblur=luma_radius={radius}:luma_power=3:chroma_radius={chroma}:chroma_power=3[bc{number}]')
        parts.append(f'[ba{number}][bc{number}]overlay={px}:{py}[{out}]')
        current=out
    return ';'.join(parts)


def blur_regions(profile):
    return [r for r in (profile.get('blur_regions') or []) if isinstance(r,dict)]


def final_video(profile,info,output_fps,duration,vsrc,punches,assets,look,ass,first_extra,reframe_plan,push_enabled,supersample=None,flash=None,
                canvas=(1080,1920),layout=None,ass_name='legendas.ass',draft=False):
    """Quadro final (padrão 1080x1920): layout, zoom por punch, cor, imagens e legendas."""
    push=look.get('push') if push_enabled else None
    W,H=canvas;layout=resolve_layout(profile,layout,canvas);video=profile.get('content_mode','live')=='video'
    if video or layout['mode']=='wide':
        mode=layout['mode'] if layout['mode'] in VIDEO_LAYOUTS else 'fit'
        filters=video_filters(output_fps,info,reframe_plan,source=vsrc,canvas=canvas,mode=mode,focus=layout['focus'],draft=draft)
    else:
        filters=live_filters(profile,info,punches,look,output_fps,duration,push,supersample,canvas,layout,vsrc)
    if draft:filters=filters.replace('flags=lanczos','flags=bilinear')   # rascunho 540x960: reamostragem mais barata
    visual='base'
    if (video or layout['mode']=='wide') and (punches or push):
        effect=camera_zoom_filter(punches,output_fps,width=W,height=H,curve=look.get('curve','smooth'),
                                  push=push,duration=duration,supersample=supersample).lstrip(',')
        if effect:filters+=f';[{visual}]{effect}[styled]';visual='styled'
    grade=grade_filters(look.get('grade'))
    if grade:filters+=f';[{visual}]{grade}[graded]';visual='graded'
    if flash is not None:
        filters+=(f";[{visual}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.85:t=fill:"
                  f"enable='between(t,{max(0,flash-.05):g},{flash+.07:g})'[flashed]");visual='flashed'
    number=0
    for index,asset in first_extra:
        if asset['kind']!='overlay':continue
        if asset.get('layer'):
            # Mistura (screen/multiply): a camada já tem o tamanho do quadro e a posição/opacidade aplicadas.
            filters+=f';[{index}:v]scale={W}:{H},setsar=1,format=gbrp[ov{number}]'
            filters+=(f";[{visual}]format=gbrp[vb{number}];[vb{number}][ov{number}]blend=all_mode={asset['blend']}:shortest=1:"
                      f"enable='between(t,{asset['start']},{asset['end']})',format=yuv420p[visual{number}]")
        elif asset.get('motion'):
            # Gráfico animado com transparência (P27): já vem do tamanho da caixa; só posiciona e limita no tempo.
            filters+=f';[{index}:v]format=rgba[ov{number}]'
            filters+=(f";[{visual}][ov{number}]overlay=x={int(asset['px'])}:y={int(asset['py'])}:format=auto:eof_action=pass:"
                      f"enable='between(t,{asset['start']},{asset['end']})'[visual{number}]")
        elif 'x' in asset:
            # Imagem do editor: posição, tamanho e opacidade escolhidos clipe a clipe.
            width=max(16,int(W*float(asset.get('scale',.45)))//2*2);opacity=float(asset.get('opacity',1))
            chain=f'[{index}:v]scale={width}:-2'
            if opacity<.999:chain+=f',format=rgba,colorchannelmixer=aa={opacity:g}'
            filters+=f';{chain}[ov{number}]'
            filters+=(f";[{visual}][ov{number}]overlay=x='W*{float(asset['x']):g}-w/2':y='H*{float(asset['y']):g}-h/2':"
                      f"enable='between(t,{asset['start']},{asset['end']})'[visual{number}]")
        else:
            position=profile.get('overlay_position','center')
            y={'top':'120','center':'(H-h)/2','bottom':'H-h-360'}.get(position,'(H-h)/2')
            filters+=f';[{index}:v]scale=360:-1:force_original_aspect_ratio=decrease[ov{number}]'
            filters+=f';[{visual}][ov{number}]overlay=(W-w)/2:{y}:enable=\'between(t,{asset["start"]},{asset["end"]})\'[visual{number}]'
        visual=f'visual{number}';number+=1
    if 'Dialogue:' in ass:
        fonts=':fontsdir=fontes' if (profile.get('brand') or {}).get('caption_font') else ''
        filters+=f';[{visual}]ass={ass_name}{fonts}[out]';visual='out'
    return filters,visual


def extra_inputs(assets,start):
    extra=[];indexed=[];number=start
    for asset in assets:
        if asset['kind']=='overlay' and asset.get('motion'):extra += ['-itsoffset',f"{float(asset['start']):g}",'-i',asset['path']]   # gráfico animado (P27): vídeo com alfa
        elif asset['kind']=='overlay':extra += ['-loop','1','-i',asset['path']]
        elif asset['kind']=='music':extra += ['-stream_loop','-1','-i',asset['path']]
        else:extra += ['-i',asset['path']]
        indexed.append((number,asset));number+=1
    return extra,indexed


def peak_times(punches):
    """Instante do pico de cada punch (o plano o coloca 0,2 s depois do início)."""
    return [min(float(p['end']),float(p['start'])+.2) for p in punches]


def render(candidate, transcript, session_path, preview=False, pipeline='auto', root=None):
    """`preview`: False (exportação final), True (original horizontal, V7) ou 'draft' (rascunho vertical
    editado, 540x960, rápido). `pipeline`: 'auto' (uma passada, com retorno ao método antigo se falhar),
    'single' ou 'legacy'. `root`: pasta de dados (músicas e efeitos da biblioteca)."""
    if pipeline not in ('auto','single','legacy'):raise ValueError('Pipeline de render inválido.')
    mode='draft' if preview=='draft' else 'original' if preview else 'final'
    preview=mode!='final'
    profile=candidate['profile'];threads=profile['threads']
    session_path=Path(session_path)
    require_space(session_path,profile['min_free_gb'],extra=200*1024**2)
    parent=session_path/('previas' if preview else 'cortes')
    parent.mkdir(exist_ok=True)
    if not preview:
        restored=receipt(candidate,parent)
        if restored:return restored
    key=signature(candidate)
    final=parent/(candidate['id']+'_'+key[:12]+{'draft':'_rascunho','original':'_revisao','final':''}[mode])
    if preview and (final/'clipe.mp4').is_file():return final/'clipe.mp4'
    if final.exists():raise RuntimeError('Existe uma exportação incompleta com esse identificador. Os arquivos foram preservados para inspeção.')
    with tempfile.TemporaryDirectory(prefix='render_',dir=parent) as temp:
        progress.phase('Preparando o corte',0,5,'preparando')
        scratch=Path(temp);target=scratch/'entrega';target.mkdir();output=target/'clipe.mp4'
        extra_meta=dict(pipeline='preview' if mode=='original' else pipeline,loudness=None,fallback=None,root=root,mode=mode,
                        measure=mode!='draft',teaser_skipped=False)
        if mode!='original' and len(candidate['parts'])==1:
            from . import syncaudio
            linked=syncaudio.load(session_path)
            if linked:extra_meta['external_audio']=dict(path=linked['path'],offset=linked['offset'],confidence=linked.get('snr'))
        applied_cuts=[];reframe_plan=[];assets=[];look={}
        if mode=='original':
            source,offset,duration=assemble(candidate['parts'],scratch,threads)
            original_info=probe(source)
            privacy=blur_graph(blur_regions(profile),original_info['width'],original_info['height'],'0:v','srcb')
            scale_chain='scale=1280:-2:flags=lanczos,setsar=1,fps=30'
            video_args=['-filter_complex',f'{privacy};[srcb]{scale_chain}[vout]','-map','[vout]'] if privacy \
                else ['-vf',scale_chain,'-map','0:v:0']
            args=[tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-threads',str(threads),
                  '-i',str(source),'-ss',str(offset),'-t',str(duration),*video_args,'-map','0:a:0?',
                  '-c:v','libx264','-preset','veryfast','-crf','23']
            args += ['-threads',str(threads),'-pix_fmt','yuv420p','-profile:v','high',
                     '-c:a','aac','-b:a','160k','-movflags','+faststart',str(output)]
            progress.phase('Gerando a prévia',5,95)
            with progress.expect(duration):run(args,cwd=scratch)
        else:
            applied_cuts=cuts_for(candidate)
            if mode=='final':
                from . import multiformat
                count=len(multiformat.selected(profile,project_of(candidate)))
                extra_meta['progress_main_hi']=85.0 if count else 95.0
                extra_meta['progress_variants']=count
            look=effective_look(candidate)
            try:
                if pipeline=='legacy' and mode=='final':raise _UseLegacy()
                try:
                    result=_single_ladder(candidate,transcript,scratch,target,output,applied_cuts,look,extra_meta)
                except RuntimeError as exc:
                    if extra_meta.get('encoder','cpu')=='cpu':raise
                    # A placa de vídeo falhou no meio do render: refaz uma vez na CPU antes de qualquer plano B.
                    extra_meta['encoder_fallback']=f"{extra_meta['encoder']}: {str(exc)[-300:]}"
                    extra_meta['force_cpu']=True
                    for leftover in target.iterdir():leftover.unlink()
                    result=_single_ladder(candidate,transcript,scratch,target,output,applied_cuts,look,extra_meta)
                if mode=='final':
                    extra_meta['variants']=_render_variants(candidate,transcript,scratch,target,applied_cuts,look,extra_meta)
            except (_UseLegacy,RuntimeError) as exc:
                # Erros de configuração (ValueError) sobem direto; falha do FFmpeg volta ao método antigo.
                if pipeline=='single' or mode=='draft':raise
                if not isinstance(exc,_UseLegacy):extra_meta['fallback']=str(exc)[-400:]
                for leftover in target.iterdir():leftover.unlink()
                extra_meta['pipeline']='legacy'
                result=_render_legacy(candidate,transcript,scratch,target,output,applied_cuts,look,extra_meta)
            reframe_plan,assets,duration=result
        progress.phase('Conferindo o arquivo',95,96,'finalizando')
        actual=probe(output)
        if abs(actual['duration']-duration)>max(.7,duration*.03):
            raise RuntimeError('A duração do vídeo não confere. A exportação foi interrompida para preservar a revisão.')
        if mode=='final' and (actual['width'],actual['height']) != (1080,1920):
            raise RuntimeError('A resolução vertical final não confere. A exportação foi interrompida.')
        if extra_meta.get('plan'):
            from . import plan as planlib
            extra_meta['plan_delta_frames']=round(planlib.compare_duration(extra_meta['plan'],actual['duration']),2)
            (target/'plano.json').write_text(json.dumps(extra_meta['plan'],ensure_ascii=False,indent=1),encoding='utf-8')
        public_meta={k:v for k,v in extra_meta.items() if k not in ('root','measure','shared_loudness','force_cpu','progress_main_hi','progress_variants')}
        metadata=dict(signature=key,video_sha=sha_file(output),start=candidate['start'],end=candidate['end'],
                      parts=candidate['parts'],profile=profile,preview=preview,
                      editorial=candidate.get('data',{}).get('editorial_audit',{}),
                      reframe_plan=reframe_plan,edit_plan=candidate.get('data',{}).get('edit_plan',{}),
                      edit_overrides=candidate.get('data',{}).get('edit_overrides',{}),
                      project=candidate.get('data',{}).get('project'),
                      applied_cuts=applied_cuts,assets=[{k:v for k,v in item.items() if k!='path'} for item in assets],
                      renderer=RENDERER_VERSION,look=look,**public_meta)
        (target/'manifesto.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        if not preview:
            editorial=metadata['editorial'];source=editorial.get('source',{})
            credit_lines=['CRÉDITOS DO CLIPE',f"Streamer/canal: {source.get('author','')}",
                          f"Transmissão original: {source.get('title','')}",f"Link: {source.get('url','')}",
                          f"Trecho: {candidate['start']:.2f}s a {candidate['end']:.2f}s",
                          f"Observações: {profile.get('credit_note','')}"]
            for item in assets:
                if item['kind']=='music' and item.get('title'):
                    credit_lines.append(f"Música: {item['title']}"+(f" — {item['uploader']}" if item.get('uploader') else '')+
                                        (f" ({item['url']})" if item.get('url') else ''))
            (target/'creditos.txt').write_text('\n'.join(credit_lines),encoding='utf-8')
            from . import publish
            extra_files=[k for k,v in (extra_meta.get('variants') or {}).items() if v=='ok']
            (target/'publicacao.txt').write_text(publish.build(candidate,assets,extra_files),encoding='utf-8')
        target.replace(final)
    return final/'clipe.mp4'


class _UseLegacy(Exception):
    pass


def _render_variants(candidate,transcript,scratch,target,applied_cuts,look,meta):
    """Versões extras (1:1, 4:5, 16:9) do mesmo plano de edição: as do projeto (Estúdio) mais as automáticas do perfil.
    Cada arquivo é conferido depois de codificado (medidas, codec, pixel format, áudio, duração). Falha numa variante
    não derruba o vertical principal; arquivo inutilizável é apagado e o motivo vai ao manifesto."""
    from . import multiformat
    result={};notes={}
    formats=multiformat.selected(candidate.get('profile') or {},project_of(candidate))
    main=None
    if formats:
        try:main=probe(target/'clipe.mp4')
        except Exception:main=None
    first=float(meta.get('progress_main_hi',85.0));span=(95.0-first)/max(1,len(formats))
    for index,variant in enumerate(formats):
        output=target/f'clipe_{variant}.mp4'
        progress.phase(f'Gerando a versão {variant.replace("x",":")} ({index+1} de {len(formats)})',first+span*index,first+span*(index+1))
        try:
            _render_single(candidate,transcript,scratch,target,output,applied_cuts,look,meta,variant=variant)
            result[variant]='ok'
            if main:
                errors,warnings=multiformat.check_variant(output,variant,main,probe)
                if errors:
                    output.unlink(missing_ok=True);result[variant]='erro: validação — '+'; '.join(errors)[:300]
                elif warnings:notes[variant]=warnings
            ass=Path(scratch)/f'legendas_{variant}.ass'
            if result[variant]=='ok' and ass.is_file():
                shutil.copyfile(ass,target/ass.name)    # legenda própria da proporção, guardada com a exportação
                if (candidate.get('profile') or {}).get('export_srt'):
                    text=multiformat.srt_from_ass(ass.read_text(encoding='utf-8-sig'))
                    if text:(target/f'legendas_{variant}.srt').write_text(text,encoding='utf-8')
        except (RuntimeError,ValueError) as exc:
            output.unlink(missing_ok=True);result[variant]='erro: '+str(exc)[-300:]
    if notes:meta['variants_notes']=notes
    return result


def _caption_source(candidate,transcript):
    """Segmentos de legenda em tempo da fonte: linhas editadas no projeto ou a transcrição."""
    lines=((project_of(candidate) or {}).get('captions') or {}).get('lines')
    if lines is None:return transcript,False
    base=float(candidate['start']);segments=[]
    for line in lines:
        segments.append(dict(start=base+line['start'],end=base+line['end'],text=line['text'],
                             words=[dict(start=base+w['start'],end=base+w['end'],word=w['word']) for w in line.get('words') or []]))
    return segments,True


def camera_zone(profile,layout,canvas):
    """Fração da altura (0–1) que a webcam ocupa no TOPO do quadro, ou None quando ela não está no topo (ou não existe)."""
    W,H=canvas
    if profile.get('content_mode','live')!='live' or not profile.get('camera_rect') or W>H:return None
    mode=layout['mode']
    if mode=='cam_top':return 1/3
    if mode=='split':return .5
    if mode=='game_pip' and layout['pip'][0]=='t':
        size=max(120,int(W*layout['pip_size'])//2*2)
        return .08+(size+8)/H
    return None


def _titles(candidate,remap,lead=0.0,canvas=(1080,1920)):
    """Títulos na tela no relógio final (um título que começa em 0 também cobre a abertura).

    O título AUTOMÁTICO nunca cobre a webcam: quando ela ocupa o topo do quadro, o título desce para logo abaixo dela."""
    result=[]
    auto=(candidate.get('data') or {}).get('auto_title')
    profile=candidate.get('profile') or {}
    if auto and not (project_of(candidate) or {}).get('titles'):
        from . import titledata,brand
        entry=titledata.title_entry(auto,max(1.0,remap.length if hasattr(remap,'length') else 3.5))
        result=brand.apply_titles([dict(entry)],profile.get('brand'))
        zone=camera_zone(profile,resolve_layout(profile,(project_of(candidate) or {}).get('layout'),canvas),canvas)
        if zone is not None:
            result=[dict(t,margin_frac=round(zone+.025,4)) if t.get('position','top')=='top' else t for t in result]
        return result
    for title in (project_of(candidate) or {}).get('titles',[]):
        moved=retime_points([dict(start=title['start'],end=title['end'])],remap)
        if not moved:continue
        start=0.0 if lead and float(title['start'])<.3 else moved[0]['start']
        result.append(dict(title,start=start,end=moved[0]['end']))
    from . import brand
    return brand.apply_titles(result,profile.get('brand'))


def _write_captions(candidate,profile,transcript,duration,remap,punches,look,target,scratch,titles=(),smart=True,teaser=None,
                    canvas=None,name='legendas.ass',deliver=True,root=None,text=True):
    options=(project_of(candidate) or {}).get('captions') or {}
    source,keep=_caption_source(candidate,transcript)
    effective=retime_transcript(source,candidate['start'],candidate['end'],remap)
    if teaser:
        a=candidate['start']+teaser[0];b=candidate['start']+teaser[1]
        effective=retime_transcript(source,a,b,[])+effective
    style=resolve_style(options.get('style') or profile.get('caption_style','dynamic'),look)
    size=options.get('size') or profile['font_size'];margin=options.get('margin') or profile['caption_margin']
    color=title_color_bgr(options['color']) if options.get('color') else profile['caption_color']
    ass=make_ass(effective,0,duration,size,margin,color,style,emphasis=peak_times(punches),smart=smart,keep_lines=keep,
                 vocabulary=caption_terms(profile),corrections=profile.get('corrections',''),titles=titles if text else None,captions=options.get('enabled',True) and text,canvas=canvas,
                 font=(profile.get('brand') or {}).get('caption_font') or 'Arial')
    (scratch/name).write_text(ass,encoding='utf-8-sig')
    if (profile.get('brand') or {}).get('caption_font') and root:
        from . import brand
        brand.prepare_fonts(root,scratch)
    if deliver:
        (target/'legendas.ass').write_text(ass,encoding='utf-8-sig')
        (target/'legendas.srt').write_text(srt(effective,0,duration),encoding='utf-8-sig')
        try:
            from . import caption_track
            from .captions import vocabulary_terms
            (target/'legendas_revisao.json').write_text(caption_track.dump(caption_track.review_document(effective,vocabulary_terms(caption_terms(profile)))),encoding='utf-8')
        except Exception:pass   # o documento de revisão nunca impede a exportação
    return ass


def _video_codec(profile,draft,meta=None):
    """Codificador do vídeo: CPU (padrão), ou placa de vídeo quando escolhida e testada."""
    from . import hardware
    meta=meta if meta is not None else {}
    from .telemetry import mode_name
    mode=mode_name(profile.get('quality_mode'))
    kind,args=hardware.choose(profile.get('video_encoder','cpu'),draft=draft,force_cpu=bool(meta.get('force_cpu')),mode=mode)
    meta['encoder']=kind
    if not draft:meta['quality_mode']=mode;meta['video_args']=' '.join(args)
    return args


def _attach_plan(candidate,parts,pieces,duration,fps,canvas,project,teaser_count,meta):
    """Descreve em dados o que será renderizado (plano versionado) e confere o contrato. Nunca derruba o render."""
    try:
        from . import capabilities,plan as planlib
        decisions=[dict(id=d.get('id'),kind=d.get('kind'),enabled=d.get('enabled'),label=d.get('label'),reason=d.get('reason'),
                        confidence=d.get('confidence')) for d in decisions_for(candidate)]
        data=candidate.get('data',{})
        story=dict(intent=(data.get('function_map') or {}).get('chosen',{}).get('why'),preserve_chronology=(data.get('function_map') or {}).get('chosen',{}).get('id','cronologica')=='cronologica',
                   evidence_ids=[e.get('kind') for e in (data.get('function_map') or {}).get('evidence',[])])
        plan=planlib.build(candidate['id'],parts,pieces,duration,fps=fps,canvas=canvas,project=project,story=story,decisions=decisions,
                           memory_refs=[r['id'] if isinstance(r,dict) else r for r in data.get('memory_refs',[])],teaser_count=teaser_count,
                           profile_ref='perfil:'+str((candidate.get('profile') or {}).get('editorial_style','clean')))
        problems=planlib.validate(plan,registry=capabilities)
        meta['plan']=plan;meta['plan_sha']=planlib.digest(plan)
        if problems:meta['plan_warnings']=problems[:10]
    except Exception as exc:   # o plano é descrição; falhar nele não impede o vídeo
        meta['plan_warnings']=[dict(code='plano',where='/',message=str(exc)[:200])]


def _cut_audio(parts,infos,pieces,profile,meta,scratch):
    """Áudio do corte já montado (cortes, velocidades, fade), em WAV mono 16 kHz, para animar gráficos pelo som."""
    if not (any(item['has_audio'] for item in infos) or meta.get('external_audio')):raise ValueError('O corte não tem áudio para animar o gráfico.')
    args,graph=build_source(parts,infos,pieces,video=False,audio=True,fade=cut_fade(profile),external=meta.get('external_audio'))
    out=Path(scratch)/'motion_audio.wav'
    run([tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y',*args,'-filter_complex',graph,'-map','[srca]','-ac','1','-ar','16000',str(out)],cwd=scratch)
    return out


def motion_assets(candidate,profile,project,duration,canvas,scratch,meta,record,audio_provider):
    """Gráficos 2D por template (P27): explícitos do projeto + automáticos do perfil, dentro do orçamento. Falha de um gráfico
    não derruba o corte: o motivo vai para `meta['motion']` e o QC avisa. `record`: só o vertical principal grava o relatório."""
    from . import graphics2d as motion,cover
    level=profile.get('motion_level','off')
    explicit=list((project or {}).get('motion') or [])
    if level=='off' and not explicit:return []
    root=meta.get('root');warnings=[];items=[]
    for raw in explicit:
        try:items.append(motion.clean(raw,duration))
        except motion.MotionError as exc:warnings.append(f"Gráfico ignorado: {exc}")
    if level!='off':
        data=candidate.get('data') or {}
        titled=any(float(t.get('start',0))<3.0 for t in ((project or {}).get('titles') or [])) or bool(data.get('auto_title'))
        items+=motion.automatic_items(data.get('motion_context'),duration,titled)
    accepted,decisions=motion.apply_budget(items,duration,level)
    out=[];files=[];audio=None
    if accepted and not root:
        warnings.append('Gráficos animados exigem a pasta de dados; nenhum foi aplicado.');accepted=[]
    font=cover.font_path(root) if root else None
    for number,item in enumerate(accepted):
        try:
            arg=None
            if item['template']=='pulso_audio':
                if audio is None:audio=motion.read_audio(audio_provider())
                arg=(audio,item['start'])
            made=motion.render_item(item,canvas,root,level,font,arg)
            x,y,w,h=made['box'];end=round(item['start']+item['duration'],3)
            if made['kind']=='video':
                out.append(dict(kind='overlay',id=f'motion:{number}',path=made['path'],motion=True,px=x,py=y,w=w,h=h,start=item['start'],end=end))
            else:
                out.append(dict(kind='overlay',id=f'motion:{number}',path=made['path'],start=item['start'],end=end,x=round((x+w/2)/canvas[0],4),
                                y=round((y+h/2)/canvas[1],4),scale=w/canvas[0],opacity=1.0))
            files.append(dict(template=item['template'],start=item['start'],duration=item['duration'],kind=made['kind'],cached=made['cached']))
        except (motion.MotionError,ValueError,OSError,RuntimeError) as exc:
            warnings.append(f"Gráfico \"{item['template']}\" não aplicado: {str(exc)[:120]}")
    if record:meta['motion']=dict(level=level,aplicados=files,decisoes=decisions,avisos=warnings,versao=motion.VERSION)
    elif warnings:meta.setdefault('overlay_warnings',[]).extend(warnings)
    return out


def brand_assets(profile,meta,duration,canvas,scratch):
    """Logo e cartões do kit de marca (tempo final) e fontes do streamer na pasta de trabalho."""
    from . import brand
    kit=profile.get('brand') or {};root=(meta or {}).get('root')
    if not root:return []
    items,warnings=brand.assets(kit,root,duration,canvas)
    if warnings and isinstance(meta,dict):meta.setdefault('brand_warnings',[]).extend(warnings)
    return items


def prepare_overlays(assets,scratch,canvas,meta=None):
    """Reduz cada imagem uma vez, no tamanho final, para o FFmpeg não reescalar uma imagem enorme a cada quadro.
    Chave de cor, máscara e mistura (P16) também são resolvidas aqui; se falharem, a imagem entra sem elas e o aviso vai ao registro."""
    result=[]
    for item in assets:
        if item['kind']=='overlay' and 'x' in item:
            width=max(16,int(canvas[0]*float(item.get('scale',.45)))//2*2)
            target=Path(scratch)/f'imagem_{len(result)}.png'
            special=item.get('key') or item.get('mask') or item.get('blend') in ('screen','multiply')
            if special:
                from . import keying
                try:
                    if item.get('blend') in ('screen','multiply'):
                        keying.layer(item['path'],target.with_suffix('.layer.png'),canvas,item['x'],item['y'],item.get('scale',.45),item.get('opacity',1),
                                     item['blend'],item.get('key'),item.get('mask'))
                        result.append(dict(item,path=str(target.with_suffix('.layer.png')),layer=True));continue
                    keying.apply(item['path'],target,width,item.get('key'),item.get('mask'))
                    result.append(dict(item,path=str(target)));continue
                except Exception as exc:
                    if meta is not None:meta.setdefault('overlay_warnings',[]).append('Chave/máscara/mistura não aplicada: '+str(exc)[:100])
            try:
                run([tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-i',item['path'],
                     '-vf',f'scale=min({width}\\,iw):-2:flags=lanczos,format=rgba','-frames:v','1',str(target)],120)
                item=dict(item,path=str(target))
            except RuntimeError:pass
        result.append(item)
    return result


def _with_color(look,profile,pieces,scratch,meta):
    """Cor automática (P17): histograma e/ou LUT do perfil somados à cor do estilo. Falha = mantém a cor do estilo."""
    wants=profile.get('auto_color','off')=='histograma';lut=profile.get('lut') or ''
    if not wants and not lut:return look
    from . import grade as colorlib
    extra={};report=[]
    try:
        if wants:
            decided,reasons=colorlib.decide(colorlib.measure_frames(colorlib.sample_pieces(pieces)),profile.get('content_mode','live'))
            extra.update(decided);report+=reasons
        if lut:
            source=Path(meta.get('root') or '')/'luts'/lut
            if not meta.get('root') or not source.is_file():report.append('LUT "'+lut+'" não encontrada; não apliquei.')
            else:
                colorlib.prepare_lut(source,Path(scratch)/'look.cube',profile.get('lut_strength',1.0))
                extra['lut']='look.cube';report.append('LUT "'+lut+'" aplicada com intensidade '+format(float(profile.get('lut_strength',1.0)),'g')+'.')
    except Exception as exc:
        meta['color_report']=['Não consegui aplicar a cor automática ('+str(exc)[:100]+'); mantive a cor do estilo.'];return look
    meta['color_report']=report
    return dict(look,grade=colorlib.merge(look.get('grade'),extra))


# Módulos opcionais que, se o render falhar com eles ligados, são desligados numa segunda tentativa antes do plano B antigo (P25).
OPTIONAL_MODULES=(('tratamento de voz','voice_preset','off'),('cor automática','auto_color','off'),('LUT de cor','lut',''),('fade nas emendas','cut_fade','off'),('câmera lenta interpolada','slow_interp','off'),('estabilização','stabilize','off'),('gráficos animados','motion_level','off'))


AUTO_ASSET_NAMES={'music':'música automática','sfx':'efeito sonoro automático','overlay':'imagem automática'}
ASSET_ERROR='Um recurso de edição'


def _auto_asset_ids(candidate):
    """Decisões AUTOMÁTICAS do plano que dependem de um arquivo do perfil (música, efeito, imagem), ligadas hoje."""
    try:return [(d['id'],d['kind']) for d in decisions_for(candidate) if d.get('enabled') and d.get('kind') in AUTO_ASSET_NAMES]
    except (KeyError,TypeError,AttributeError):return []


def _single_ladder(candidate,transcript,scratch,target,output,applied_cuts,look,meta):
    """Render de uma passada; se falhar, tenta de novo com uma versão mais simples e registra o recuo (nunca em silêncio).

    Degraus, do menor para o maior corte: (1) sem os módulos opcionais do perfil (voz, cor, LUT, fades, câmera lenta
    interpolada, estabilização, gráficos animados) e sem o áudio externo; (2) além disso, sem a música, o efeito e a imagem
    que o PLANO AUTOMÁTICO escolheu a partir do perfil. Recurso que a pessoa escolheu no editor nunca é descartado em
    silêncio: se faltar, o erro continua e diz qual é. Arquivo de recurso ausente cai direto no degrau 2."""
    try:
        return _render_single(candidate,transcript,scratch,target,output,applied_cuts,look,meta)
    except (RuntimeError,ValueError) as exc:
        asset_problem=isinstance(exc,ValueError)
        if asset_problem and not str(exc).startswith(ASSET_ERROR):raise
        profile=candidate['profile']
        active=[] if asset_problem else [(name,key,off) for name,key,off in OPTIONAL_MODULES if profile.get(key,off)!=off]
        external=None if asset_problem else meta.get('external_audio')
        assets=_auto_asset_ids(candidate)
        if (not active and not external and not assets) or (not asset_problem and meta.get('encoder','cpu')!='cpu'):raise
        steps=[]
        if active or external:steps.append(([],active,external))
        if assets:steps.append((assets,active,external))
        for dropped,modules,ext in steps:
            for leftover in target.iterdir():leftover.unlink()
            reduced=dict(candidate,profile=dict(profile,**{key:off for _,key,off in modules}))
            if dropped:
                data=dict(candidate.get('data') or {})
                data['edit_overrides']=dict(_overrides_of(candidate),**{item:False for item,_ in dropped})
                reduced['data']=data
            if ext:meta.pop('external_audio',None)
            try:
                result=_render_single(reduced,transcript,scratch,target,output,applied_cuts,look,meta)
            except (RuntimeError,ValueError):
                if ext:meta['external_audio']=ext
                continue
            names=[name for name,_,_ in modules]+sorted({AUTO_ASSET_NAMES[kind] for _,kind in dropped})+(['áudio externo'] if ext else [])
            meta['recuo']=dict(modulos=names,motivo=str(exc)[-300:])
            return result
        raise exc


def _overrides_of(candidate):
    value=(candidate.get('data') or {}).get('edit_overrides')
    return value if isinstance(value,dict) else {}


def _render_single(candidate,transcript,scratch,target,output,applied_cuts,look,meta,variant=None):
    """Uma única codificação: trims + concat + layout + cor + legendas + áudio no mesmo filtergraph.

    `variant`: None (vertical 9:16) ou '1x1', '4x5', '16x9' (versões extras do mesmo projeto)."""
    profile=candidate['profile'];threads=profile['threads'];parts=candidate['parts']
    draft=meta.get('mode')=='draft';project=project_of(candidate)
    canvas=CANVAS[variant or '9x16'];name='legendas.ass' if not variant else f'legendas_{variant}.ass'
    infos=[probe(part['path']) for part in parts]
    total=sum(float(part['out'])-float(part['in']) for part in parts)
    intervals=keep_intervals(total,applied_cuts)
    if not intervals or sum(b-a for a,b in intervals)<1:raise ValueError('As decisões removeriam todo o corte.')
    remap,teaser,lead=remap_for(project,total,applied_cuts,auto_replays(candidate))
    pieces=plan_pieces(parts,remap,teaser)
    duration=round(lead+remap.length,4)
    look=_with_color(look,profile,[(parts[p[0]]['path'],p[1],p[2]) for p in pieces if not (len(p)>4 and p[4])],scratch,meta)
    teaser_count=len(source_pieces(parts,[teaser])) if teaser else 0
    first=infos[0];multi=len(parts)>1
    width=min(2560,first['width'])//2*2 if multi else first['width']
    height=max(2,round(first['height']*width/first['width']/2)*2) if multi else first['height']
    has_audio=any(item['has_audio'] for item in infos) or bool(meta.get('external_audio'))
    info=dict(width=width,height=height,fps=first.get('fps',30),has_audio=has_audio,duration=duration)
    output_fps=60 if info['fps']>=50 and not draft else 30
    if not variant and not draft:_attach_plan(candidate,parts,pieces,duration,output_fps,canvas,project,teaser_count,meta)
    punches=retime_points(punches_for(candidate),remap)
    assets=edit_assets(candidate,meta.get('root'),final=meta.get('mode')=='final')
    whoosh=[]
    if teaser and meta.get('root'):
        from . import sfx as effects
        whoosh=[dict(kind='sfx',id='teaser:whoosh',path=str(effects.ensure(meta['root'],'whoosh')),start=max(0.0,lead-.2),
                     end=lead+.5,volume=.5)]
    assets=[x for x in assets if x['kind']=='music']+retime_points([x for x in assets if x['kind']!='music'],remap)+whoosh
    assets+=brand_assets(profile,meta,duration,canvas,scratch)
    if not draft:
        assets+=motion_assets(candidate,profile,project,duration,canvas,scratch,meta,variant is None,
                              lambda:_cut_audio(parts,infos,pieces,profile,meta,scratch))
    assets=prepare_overlays(assets,scratch,canvas,meta)
    titles=_titles(candidate,remap,lead,canvas)
    ass=_write_captions(candidate,profile,transcript,duration,remap,punches,look,target,scratch,titles=titles,teaser=teaser,
                        canvas=canvas,name=name,deliver=variant is None,root=meta.get('root'),text=not draft)
    reframe_plan=[]
    if canvas==(1080,1920) and profile.get('content_mode','live')=='video' and profile.get('auto_reframe',True) \
            and profile.get('reframe_mode','conservative') in ('dynamic','speaker','rastreio'):
        cursor=0.0
        for index,a,b,rate,hold,*_ in pieces:
            if hold:cursor+=hold;continue
            for point in reframe_points(profile,parts[index]['path'],a,b-a,infos[index]):
                reframe_plan.append(dict(point,start=round(cursor+point['start']/rate,3),end=round(cursor+point['end']/rate,3)))
            cursor+=(b-a)/rate
        (target/'plano_enquadramento.json').write_text(json.dumps(reframe_plan,ensure_ascii=False,indent=2),encoding='utf-8')
    source_args,source_filters=build_source(parts,infos,pieces,video=True,audio=has_audio,fade=cut_fade(profile),interp=slow_interp(profile),external=meta.get('external_audio'))
    stable=stabilize_filter(profile,meta)
    vlabel='srcv'
    if stable:source_filters+=f';[srcv]{stable}[srcs]';vlabel='srcs'
    privacy=blur_graph(blur_regions(profile),width,height,vlabel,'srcb')
    if privacy:source_filters+=';'+privacy
    source_label='srcb' if privacy else vlabel
    inputs=sum(1 for item in source_args if item=='-i')
    extra,indexed=extra_inputs(assets,inputs)
    push_enabled=bool(profile.get('auto_zoom',True))
    layout=(project or {}).get('layout')
    video_graph,visual=final_video(profile,info,output_fps,duration,source_label,punches,assets,look,ass,indexed,
                                   reframe_plan,push_enabled,supersample=1 if draft else None,flash=lead if teaser else None,
                                   canvas=canvas,layout=layout,ass_name=name,draft=draft)
    if draft:
        video_graph+=f';[{visual}]scale=540:960:flags=fast_bilinear,setsar=1[draft]';visual='draft'
    graph=[source_filters,video_graph];audio_map=[]
    voice_clean=voice_mode(project,meta.get('root'),scratch,meta,profile)
    if has_audio:
        measured=None
        if variant:
            measured=meta.get('shared_loudness')
        elif meta.get('measure',True):
            measure_graph=build_source(parts,infos,pieces,video=False,audio=True,fade=cut_fade(profile),external=meta.get('external_audio'))[1]+';'+audio_chain(
                'srca',indexed,profile,duration,loudnorm_filter()+':print_format=json',voice_clean)
            progress.phase('Medindo o volume do áudio',5,20)
            try:
                with progress.expect(duration):
                    measured=parse_loudness(run_stderr([tool('ffmpeg'),'-nostdin','-hide_banner','-nostats','-loglevel','info','-y',
                        *source_args,*extra,'-filter_complex',measure_graph,'-map','[aout]','-vn','-f','null','-'],cwd=scratch))
            except (RuntimeError,OSError,subprocess.SubprocessError):measured=None
        reason=None
        if measured is None:reason='medição indisponível (silêncio, erro ou rascunho)'
        elif not linear_feasible(measured):reason='sem margem de pico para ganho linear; método da V7 mantido'
        usable=measured if measured is not None and linear_feasible(measured) else None
        if not variant:
            meta['loudness']=dict(mode='dois passes (linear)' if usable else 'uma passada (dinâmico)',target=LOUDNESS,
                                  measured=measured,reason=reason)
            meta['shared_loudness']=measured
        graph.append(audio_chain('srca',indexed,profile,duration,loudnorm_filter(usable),voice_clean,meta));audio_map=['-map','[aout]']
    codec_meta={'force_cpu':meta.get('force_cpu')}
    codec=_video_codec(profile,draft,codec_meta)
    if not variant:
        meta['encoder']=codec_meta['encoder']
        if not draft:meta['quality_mode']=codec_meta['quality_mode'];meta['video_args']=codec_meta['video_args']
    from .telemetry import audio_bitrate
    args=[tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-threads',str(threads),
          *source_args,*extra,'-t',str(duration),'-filter_complex_threads','1','-filter_complex',';'.join(graph),
          '-map',f'[{visual}]',*audio_map,*codec,
          '-threads',str(threads),'-pix_fmt','yuv420p','-profile:v','high',
          '-c:a','aac','-b:a',audio_bitrate(profile) if not draft else '96k','-movflags','+faststart',str(output)]
    if not variant:
        progress.phase('Aplicando as edições e codificando o vídeo',20 if has_audio and meta.get('measure',True) else 5,float(meta.get('progress_main_hi',95.0)))
    with progress.expect(duration):run(args,cwd=scratch)
    return reframe_plan,assets,duration


def _render_legacy(candidate,transcript,scratch,target,output,applied_cuts,look,meta=None):
    """Método da V7 (assemble + compact_source + render): mantido como rede de segurança.

    Não aplica a abertura (teaser); o manifesto registra `teaser_skipped`."""
    meta=meta if meta is not None else {}
    if project_of(candidate) and (project_of(candidate) or {}).get('teaser'):meta['teaser_skipped']=True
    profile=candidate['profile'];threads=profile['threads']
    source,offset,duration=assemble(candidate['parts'],scratch,threads)
    source,offset,duration=compact_source(source,offset,duration,applied_cuts,scratch,threads)
    punches=retime_points(punches_for(candidate),applied_cuts)
    assets=edit_assets(candidate,meta.get('root'),final=meta.get('mode')=='final')
    assets=[x for x in assets if x['kind']=='music']+retime_points([x for x in assets if x['kind']!='music'],applied_cuts)
    assets+=brand_assets(profile,meta,duration,(1080,1920),scratch)
    info=probe(source);output_fps=60 if info.get('fps',30)>=50 else 30
    look=_with_color(look,profile,[(source,offset,offset+duration)],scratch,meta if meta is not None else {})
    titles=_titles(candidate,applied_cuts)
    ass=_write_captions(candidate,profile,transcript,duration,applied_cuts,punches,look,target,scratch,titles=titles,smart=False,root=meta.get('root'))
    reframe_plan=[]
    if profile.get('content_mode','live')=='video' and profile.get('auto_reframe',True) and profile.get('reframe_mode','conservative') in ('dynamic','speaker','rastreio'):
        reframe_plan=reframe_points(profile,source,offset,duration,info)
        (target/'plano_enquadramento.json').write_text(json.dumps(reframe_plan,ensure_ascii=False,indent=2),encoding='utf-8')
    extra,indexed=extra_inputs(assets,1)
    privacy=blur_graph(blur_regions(profile),info['width'],info['height'],'0:v','srcb')
    video_graph,visual=final_video(profile,info,output_fps,duration,'srcb' if privacy else '0:v',punches,assets,look,ass,indexed,
                                   reframe_plan,bool(profile.get('auto_zoom',True)))
    voice_clean=voice_mode(project_of(candidate),(meta or {}).get('root'),scratch,meta if meta is not None else {},profile)
    graph=([privacy] if privacy else [])+[video_graph];audio_map='0:a:0?'
    if info['has_audio']:
        graph.append(audio_chain('0:a',indexed,profile,duration,loudnorm_filter(),voice_clean,meta));audio_map='[aout]'
    from .telemetry import audio_bitrate,cpu_args,mode_name
    meta['quality_mode']=mode_name(profile.get('quality_mode'))
    args=[tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-threads',str(threads),
          '-i',str(source),*extra,'-ss',str(offset),'-t',str(duration),'-filter_complex_threads','1',
          '-filter_complex',';'.join(graph),'-map',f'[{visual}]','-map',audio_map,
          *cpu_args(meta['quality_mode']),
          '-threads',str(threads),'-pix_fmt','yuv420p','-profile:v','high',
          '-c:a','aac','-b:a',audio_bitrate(profile),'-movflags','+faststart',str(output)]
    progress.phase('Refazendo com o método antigo (plano B)',5,95)
    with progress.expect(duration):run(args,cwd=scratch)
    return reframe_plan,assets,duration
