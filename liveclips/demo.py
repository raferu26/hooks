"""Modo demonstração: um streamer 'Exemplo' com um vídeo de teste de 70 s e um corte já sugerido.
Serve para conhecer o editor, a revisão e a exportação sem esperar uma live nem baixar modelos de voz.
Nada aqui usa internet; o vídeo é gerado pelo próprio FFmpeg (imagem de teste e um tom)."""
import json
from pathlib import Path

from . import media
from .store import DEFAULT_PROFILE
from .timeline import build_timeline, plan

NAME = 'Exemplo'
DURATION = 70

# Fala de exemplo, claramente fictícia, só para a legenda e o editor terem o que mostrar.
LINES = [
    (12.0, 15.5, 'Isto é um vídeo de demonstração do Hook’s.'),
    (15.8, 19.5, 'Aqui você vê como fica a legenda no corte.'),
    (20.0, 24.0, 'Abra o Estúdio para trocar o estilo, o título e o enquadramento.'),
    (24.5, 28.5, 'Depois aprove: a exportação sai em vertical, pronta para publicar.'),
    (29.0, 33.0, 'Nada disso usa a sua live; é só um exemplo para testar.'),
]


def make_video(target, seconds=DURATION):
    target = Path(target)
    command = [media.tool('ffmpeg'), '-y', '-v', 'error',
               '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}',
               '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}:sample_rate=48000',
               '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30', '-c:a', 'aac', '-b:a', '96k',
               '-f', 'mpegts', str(target)]
    try:media.run(command, timeout=180)
    except RuntimeError as exc:raise ValueError('Não foi possível gerar o vídeo de demonstração: ' + str(exc)[-200:])
    return target


def create(store):
    """Cria (uma vez) o streamer e a sessão de demonstração. Se já existir, devolve os mesmos ids."""
    found = store.rows('SELECT id FROM streamers WHERE name=?', (NAME,))
    if found:
        sid = (store.rows('SELECT id FROM sessions WHERE streamer=? ORDER BY created LIMIT 1', (found[0]['id'],)) or [{}])[0].get('id')
        return dict(streamer=found[0]['id'], session=sid, created=False)
    streamer = store.create_streamer(NAME)
    profile = dict(DEFAULT_PROFILE, content_mode='video', second_pass='off', min_free_gb=.5)
    store.save_profile(streamer, profile)
    sid = store.new_session(streamer, 'Vídeo de exemplo')
    session = store.session(sid)
    file = make_video(Path(session['source']) / 'segmento_00000.ts')
    info = media.probe(file)
    stat = file.stat()
    data = {'segments': [], 'signals': {'audio': [], 'motion': [], 'warnings': []}}
    with store.connect(True) as c:
        c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns,
                   'done', json.dumps(data)))
    rows = build_timeline(store.segments(sid))
    group = next(r['group_id'] for r in rows if r['start'] <= 10 < r['end'])
    start, end = 10.0, 36.0
    transcript = [dict(start=a, end=b, text=t, words=[]) for a, b, t in LINES]
    cand = dict(start=start, end=end, group_id=group, score=9.0, reasons=['Exemplo para conhecer o programa'],
                transcript=' '.join(t for _, _, t in LINES), transcript_segments=transcript, demo=True)
    parts = plan(rows, start, end, group)
    store.propose(sid, cand, parts, store.streamer(streamer)['profile'])
    store.event('demonstração', 'Streamer de exemplo criado.')
    return dict(streamer=streamer, session=sid, created=True)
