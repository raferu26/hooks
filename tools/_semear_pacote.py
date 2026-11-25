"""Cria dados de teste (streamer, sessão, vídeo sintético de reação, cortes) usando o código do PACOTE EXTRAÍDO. Uso: python _semear_pacote.py PASTA_DO_PACOTE PASTA_DE_DADOS
Vídeo 1280x720, 12 s: conteúdo à esquerda PARADO o tempo todo; webcam (canto superior direito) em movimento; um tom de áudio."""
import subprocess
import sys
from pathlib import Path

pkg, root = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
sys.path.insert(0, str(pkg))
from liveclips import media
from liveclips.editing import plan_edits
from liveclips.store import DEFAULT_PROFILE, Store
from liveclips.timeline import build_timeline, plan

assert Path(media.__file__).resolve().is_relative_to(pkg), 'o semeador está usando código de FORA do pacote'
DUR = 12
store = Store(root)
streamer = store.create_streamer('CORINGA')
profile = dict(DEFAULT_PROFILE, min_free_gb=.1, content_mode='video')
store.save_profile(streamer, profile)
sid = store.new_session(streamer, 'REACAO DE TESTE')
session = store.session(sid)
video = Path(session['source']) / 'segmento_00000.ts'
graph = ("testsrc2=s=768x720:r=30,trim=end_frame=1,loop=loop=-1:size=1,setpts=N/(30*TB)[c];"
         "testsrc2=s=300x300:r=30,hue=h=t*120[w];color=c=0x303030:s=1280x720:r=30[bg];[bg][c]overlay=0:0[x];[x][w]overlay=940:30")
subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-filter_complex', graph, '-f', 'lavfi', '-i', f'sine=frequency=300:duration={DUR}',
                '-t', str(DUR), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(video)], check=True)
info = media.probe(video)
stat = video.stat()
with store.connect(True) as c:
    c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
              (sid, 0, str(video.resolve()), media.sha_file(video), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns, 'done', '{}'))
rows = build_timeline(store.segments(sid))
group = rows[0]['group_id']
ids = []
for a, b in ((1, 11), (0.5, 6)):
    data = dict(start=a, end=b, group_id=group, score=5, reasons=['teste'], transcript='x', transcript_text='x')
    data['edit_plan'] = plan_edits(data, {}, transcript=[], profile=profile)
    key, _ = store.propose(sid, data, plan(rows, a, b, group), dict(profile))
    ids.append(key)
print('SEMEADO', sid, ' '.join(ids))
