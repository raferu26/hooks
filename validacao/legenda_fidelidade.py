"""Fidelidade da legenda: prévia ao vivo (HTML no Estúdio) × exportação (ASS/libass), medida em pixels de tinta sobre fundo preto.
Uso: ui/fresh.sh 8790 && PORT=8790 python3 validacao/legenda_fidelidade.py
Abre o Estúdio, isola a legenda ao vivo (esconde o vídeo), fotografa o telefone e mede a caixa da tinta; gera o ASS da MESMA linha com os
mesmos parâmetros (`liveCaptionLook`) pelo gerador real (`captions.make_ass`), renderiza com o FFmpeg/libass e mede igual. Compara largura,
altura e distância da base (em % da altura do quadro). Só tamanho/posição: não compara cor nem contorno. Fonte: a que o sistema resolve para 'Arial'."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveclips import captions, media

PORT = os.environ.get('PORT', '8790')


def ink(path, thr=150):
    a = np.array(Image.open(path).convert('RGB')).max(axis=2)
    ys, xs = np.where(a > thr)
    if not len(xs):
        return None
    return dict(w=int(xs.max() - xs.min()), h=int(ys.max() - ys.min()), bottom=int(a.shape[0] - ys.max()), H=int(a.shape[0]), W=int(a.shape[1]))


def ass_ink(look, base, text, font, tmp):
    segs = [dict(start=0.0, end=2.0, text=text, words=[])]
    ass = captions.make_ass(segs, 0, 2, font_size=base, margin=look['margin'], style=look['style'], font=font, keep_lines=True)
    (tmp / 'c.ass').write_text(ass, encoding='utf-8')
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=black:s=1080x1920:d=1:r=10',
                    '-vf', f"ass={tmp / 'c.ass'}", '-frames:v', '1', str(tmp / 'ass.png')], check=True)
    return ink(tmp / 'ass.png')


def measure(pg, style=None):
    tmp = Path(tempfile.mkdtemp(prefix='hk_cap_'))
    if style:
        pg.evaluate("(s)=>{ST.proj.captions.style=s;drawLive()}", style)
    info = pg.evaluate("""()=>{ST.lines[0]=Object.assign({},ST.lines[0],{text:'Hook agora',words:[]});const l=ST.lines[0];const t=l.start+.15;   /* 2 palavras: cabe numa linha nos dois e não ativa a quebra por palavras do ASS (mede só tamanho e posição) */seekClip(t);drawLive();
      const look=liveCaptionLook();return {look,base:(ST.proj.captions.size??ST.data.profile.font_size??46),text:l.text,t,font:getComputedStyle(document.querySelector('#live .cap')||document.body).fontFamily}}""")
    pg.wait_for_timeout(400)
    ok = pg.evaluate("!!document.querySelector('#live .cap')")
    if not ok:
        return dict(erro='legenda ao vivo não apareceu')
    pg.evaluate("""()=>{document.getElementById('stVideo').style.visibility='hidden';const p=document.getElementById('phone');p.style.background='#000';
      for(const s of ['stStale','stBusy','stWait','safe'])document.getElementById(s)?.classList.add('hide')}""")
    pg.wait_for_timeout(200)
    pg.locator('#phone').screenshot(path=str(tmp / 'html.png'))
    im = Image.open(tmp / 'html.png'); scale = 1080 / im.width; im.resize((1080, round(im.height * scale))).save(tmp / 'html1080.png')
    h = ink(tmp / 'html1080.png'); a = ass_ink(info['look'], info['base'], info['text'], 'Arial', tmp)   # o exportador soma o deslocamento do estilo ao tamanho BASE
    pg.evaluate("document.getElementById('stVideo').style.visibility='';")
    out = dict(texto=info['text'], estilo=info['look']['style'], tamanho=info['look']['size'], margem=info['look']['margin'], fonte_html=info['font'][:60],
               html=dict(largura=h['w'], altura=h['h'], base_pct=round(h['bottom'] / h['H'] * 100, 2)),
               ass=dict(largura=a['w'], altura=a['h'], base_pct=round(a['bottom'] / a['H'] * 100, 2)))
    out['razao_largura_html_sobre_ass'] = round(h['w'] / a['w'], 3)
    out['razao_altura_html_sobre_ass'] = round(h['h'] / a['h'], 3)
    out['diferenca_base_pontos_pct'] = round(out['html']['base_pct'] - out['ass']['base_pct'], 2)
    return out


def title_ass_ink(kind, position, text, tmp):
    ass = captions.make_ass([], 0, 3, titles=[dict(start=0, end=3, text=text, style=kind, position=position, color='#FFFFFF')], captions=False, font='Arial')
    (tmp / 't.ass').write_text(ass, encoding='utf-8')
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=black:s=1080x1920:d=3:r=10', '-vf', f"ass={tmp / 't.ass'}",
                    '-ss', '1.5', '-frames:v', '1', str(tmp / 'tass.png')], check=True)
    return ink(tmp / 'tass.png')


def measure_title(pg, kind, position, text='Titulo de teste agora'):
    """Título na prévia (HTML) × título no ASS: largura, altura e posição do topo (em % da altura) da tinta clara."""
    tmp = Path(tempfile.mkdtemp(prefix='hk_ttl_'))
    pg.evaluate("""([k,p,t])=>{ST.proj.captions.enabled=false;ST.proj.titles=[{id:'t1',text:t,start:0,end:600,style:k,position:p,color:'#ffffff'}];seekClip(1.0);drawLive()}""", [kind, position, text])
    pg.wait_for_timeout(400)
    if not pg.evaluate("!!document.querySelector('#live .ttl')"):
        return dict(erro='título ao vivo não apareceu')
    pg.evaluate("""()=>{document.getElementById('stVideo').style.visibility='hidden';const p=document.getElementById('phone');p.style.background='#000';
      for(const s of ['stStale','stBusy','stWait','safe'])document.getElementById(s)?.classList.add('hide')}""")
    pg.wait_for_timeout(200)
    pg.locator('#phone').screenshot(path=str(tmp / 'html.png'))
    im = Image.open(tmp / 'html.png'); im.resize((1080, round(im.height * 1080 / im.width))).save(tmp / 'h1080.png')
    pg.evaluate("document.getElementById('stVideo').style.visibility='';")
    h = ink_box(tmp / 'h1080.png'); a = ink_box(title_ass_png(kind, position, text, tmp))
    return dict(estilo=kind, posicao=position, razao_largura=round(h['w'] / a['w'], 3), razao_altura=round(h['h'] / a['h'], 3),
                diferenca_topo_pontos_pct=round(h['top'] / h['H'] * 100 - a['top'] / a['H'] * 100, 2), html=h, ass=a)


def ink_box(path, thr=150):
    arr = np.array(Image.open(path).convert('RGB')).max(axis=2); ys, xs = np.where(arr > thr)
    return dict(w=int(xs.max() - xs.min()), h=int(ys.max() - ys.min()), top=int(ys.min()), H=int(arr.shape[0]))


def title_ass_png(kind, position, text, tmp):
    title_ass_ink(kind, position, text, tmp)
    return tmp / 'tass.png'


if __name__ == '__main__':
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900}); pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1500)
        pg.click('[data-clip]')
        for _ in range(150):
            if pg.evaluate("typeof ST!=='undefined'&&ST.open&&!!ST.data&&ST.data.preview.available"): break
            pg.wait_for_timeout(200)
        pg.wait_for_timeout(500)
        styles = os.environ.get('ESTILOS', 'dynamic').split(',')
        res = []
        for st in styles:
            r = measure(pg, st if len(styles) > 1 or st != 'dynamic' else None)
            res.append(dict(estilo=st, **{k: r[k] for k in r if k.startswith('razao') or k.startswith('diferenca') or k == 'erro'}))
        if os.environ.get('TITULOS'):
            res = [{k: v for k, v in measure_title(pg, k, p).items() if k not in ('html', 'ass')} for k, p in (('big', 'top'), ('top', 'top'), ('bar', 'center'), ('big', 'bottom'))]
        print(json.dumps(res if len(res) > 1 else measure(pg), ensure_ascii=False, indent=1)); b.close()
