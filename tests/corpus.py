"""Conjunto pequeno e determinístico de mídias locais para validar a qualidade real dos cortes (rodada complementar).

Tudo é gerado com FFmpeg a partir de fórmulas, então qualquer pessoa reproduz os mesmos arquivos. Os instantes e as cores
abaixo são o GABARITO: os testes derivam as expectativas daqui, não do que o render devolveu.

Fonte G (gameplay com webcam, 1280x720, 30 fps, 40 s)
  tempo    áudio                                    imagem
  0–5      silêncio
  5–9      fala baixa  (amplitude .15)              
  9–12     pausa
  12–18    fala alta   (amplitude .80)
  18–20    silêncio
  20,0–20,1 bipe de 2 kHz                           clarão branco na área do jogo (3 quadros) — referência de sincronismo
  22–27    fala média  (amplitude .30)
  27–34    silêncio                                 29–32: webcam laranja (reação silenciosa marcada)
  34–38    fala média  (amplitude .30)
  14,0–14,6: fundo da webcam azul (movimento da webcam junto de um pico de voz -> zoom automático).
  Webcam em (0, .3, .25, .3) = x 0–320, y 216–432, verde com um quadrado magenta 60x60 no centro.
  Jogo: quadrado vermelho 80x80 que vai e volta (x 440–760, 500 px/s) — movimento rápido contínuo.
Fonte N (vídeo sem webcam, 1280x720, 30 s): barra azul 16 px na esquerda e amarela 16 px na direita (detectam recorte lateral).
Fonte V (vertical 720x1280, 30 s): quatro quadrados de canto (vermelho, verde, azul, amarelo) de 48 px e um quadrado branco 96x96 no centro.
"""
import json
from pathlib import Path

from liveclips import media

G_CAM = dict(rect=[0, .3, .25, .3], green='0x00c040', orange='0xff8000', face='0xff00ff')
G_TIMELINE = dict(low=(5, 9), loud=(12, 18), beep=20.0, medium_a=(22, 27), reaction=(29, 32), silence_long=(27, 34), medium_b=(34, 38))
G_MARKER = dict(time=30, label='Reação silenciosa', pre=25, post=8)      # janela 5–38 s: inclui a fala baixa
G_SRT = ('1\n00:00:05,000 --> 00:00:09,000\nFala baixa do começo\n\n2\n00:00:12,000 --> 00:00:18,000\nFala alta e animada\n\n'
         '3\n00:00:22,000 --> 00:00:27,000\nFala média antes da reação\n\n4\n00:00:34,000 --> 00:00:38,000\nFala depois da reação\n')

_AMP = ("if(between(t,5,9),.15,if(between(t,12,18),.8,if(between(t,22,27),.3,if(between(t,34,38),.3,0))))")
_SYLLABLES = "(.65+.35*sin(2*PI*4*t))"
G_AUDIO = f"aevalsrc='sin(2*PI*300*t)*{_AMP}*{_SYLLABLES}+sin(2*PI*2000*t)*if(between(t,20,20.1),.5,0)':s=48000:d=40"


def _ffmpeg(*args, timeout=300):
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', *args], timeout=timeout)


def make_g(path):
    base = (f"color=c=0x203040:s=1280x720:r=30:d=40,"
            f"drawbox=x=0:y=216:w=320:h=216:color={G_CAM['green']}:t=fill,"
            f"drawbox=x=0:y=216:w=320:h=216:color=0x0040ff:t=fill:enable='between(t,14,14.6)',"
            f"drawbox=x=0:y=216:w=320:h=216:color={G_CAM['orange']}:t=fill:enable='between(t,29,32)',"
            f"drawbox=x=130:y=294:w=60:h=60:color={G_CAM['face']}:t=fill,"
            f"drawbox=x=440:y=20:w=400:h=30:color=yellow:t=fill[bg];"
            f"color=c=red:s=80x80:r=30:d=40[sq];[bg][sq]overlay=x='440+abs(mod(t*500,640)-320)':y=300:eval=frame,"
            f"drawbox=x=320:y=0:w=960:h=720:color=white:t=fill:enable='between(t,20,20.1)'")
    _ffmpeg('-f', 'lavfi', '-i', base, '-f', 'lavfi', '-i', G_AUDIO, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30',
            '-c:a', 'aac', '-b:a', '128k', '-f', 'mpegts', str(path))
    return path


def make_n(path):
    video = ("color=c=0x303030:s=1280x720:r=30:d=30,drawbox=x=0:y=0:w=16:h=720:color=0x0040ff:t=fill,"
             "drawbox=x=1264:y=0:w=16:h=720:color=yellow:t=fill[bg];color=c=red:s=90x90:r=30:d=30[sq];"
             "[bg][sq]overlay=x='200+abs(mod(t*300,800)-400)':y=300:eval=frame")
    audio = "aevalsrc='sin(2*PI*260*t)*if(between(t,3,10),.5,if(between(t,13,28),.5,0))*(.65+.35*sin(2*PI*4*t))':s=48000:d=30"
    _ffmpeg('-f', 'lavfi', '-i', video, '-f', 'lavfi', '-i', audio, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30',
            '-c:a', 'aac', '-b:a', '128k', '-f', 'mpegts', str(path))
    return path


def make_v(path):
    video = ("color=c=0x303030:s=720x1280:r=30:d=30,drawbox=x=0:y=0:w=48:h=48:color=red:t=fill,drawbox=x=672:y=0:w=48:h=48:color=0x00c000:t=fill,"
             "drawbox=x=0:y=1232:w=48:h=48:color=0x0040ff:t=fill,drawbox=x=672:y=1232:w=48:h=48:color=yellow:t=fill,"
             "drawbox=x=312:y=592:w=96:h=96:color=white:t=fill")
    audio = "aevalsrc='sin(2*PI*260*t)*if(between(t,2,14),.5,if(between(t,17,28),.5,0))*(.65+.35*sin(2*PI*4*t))':s=48000:d=30"
    _ffmpeg('-f', 'lavfi', '-i', video, '-f', 'lavfi', '-i', audio, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30',
            '-c:a', 'aac', '-b:a', '128k', '-f', 'mpegts', str(path))
    return path


def make_dark(source, path):
    """Mesma fonte G, mas escura e com pouco contraste (para provar a correção automática de cor)."""
    _ffmpeg('-i', str(source), '-vf', 'eq=brightness=-0.10:contrast=0.85', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30',
            '-c:a', 'copy', '-f', 'mpegts', str(path))
    return path


def make_all(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return dict(g=make_g(folder / 'g_gameplay_webcam.ts'), n=make_n(folder / 'n_sem_webcam.ts'), v=make_v(folder / 'v_vertical.ts'))
