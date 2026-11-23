"""Mede a área do vídeo no Estúdio em vários tamanhos de janela (P02). Uso: ui/fresh.sh 8790 && PORT=8790 python3 validacao/medir_layout.py
Saída: JSON com largura×altura do vídeo, razão (deve ser 9/16 = 0,5625), % da janela e altura da linha do tempo."""
import json, os
from playwright.sync_api import sync_playwright
PORT = os.environ.get('PORT', '8790')
SIZES = [(1280, 720), (1366, 768), (1440, 900), (1920, 1080)]
out = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    for W, H in SIZES:
        pg = b.new_page(viewport={'width': W, 'height': H}); pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1200)
        pg.click('[data-clip]'); pg.wait_for_function("ST.open&&!!ST.data"); pg.wait_for_timeout(700)
        r = pg.evaluate("""()=>{const g=s=>document.querySelector(s).getBoundingClientRect();const p=g('#phone'),v=g('#stVideo');
          return {w:p.width,h:p.height,video_w:v.width,video_h:v.height,tl:g('#tlWrap').height,overflow_x:document.documentElement.scrollWidth>innerWidth}}""")
        out.append(dict(janela=f'{W}x{H}', video=f"{round(r['w'])}x{round(r['h'])}", razao=round(r['w'] / r['h'], 4),
                        area_pct=round(r['w'] * r['h'] / (W * H) * 100, 1), linha_do_tempo_px=round(r['tl']), rolagem_horizontal=r['overflow_x']))
        pg.close()
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
