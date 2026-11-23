"""E2E do Estúdio 0.19: autosave, prévia anterior, inspetor contextual, 3 pistas, atalhos, exportação com modo."""
import json, os, sys, time
from playwright.sync_api import sync_playwright

PORT = os.environ.get('PORT', '8790')
OUT = os.environ.get('OUT', '/tmp/shots10')
os.makedirs(OUT, exist_ok=True)
res = {}
fails = []


def wait(pg, expr, timeout=8000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            if pg.evaluate(expr): return True
        except Exception:
            pass
        pg.wait_for_timeout(50)
    raise TimeoutError(expr)


def check(name, cond, info=''):
    res[name] = bool(cond)
    if not cond:
        fails.append(f'{name} {info}')


with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    errs = []
    pg.on('console', lambda m: errs.append(m.type + ': ' + m.text) if m.type in ('error',) else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
    pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1500)
    t0 = time.time()
    pg.click('[data-clip]')
    wait(pg, "typeof ST!=='undefined'&&ST.open&&!!ST.data")
    res['abrir_estudio_ms'] = round((time.time() - t0) * 1000)
    for i in range(60):
        if pg.evaluate("ST.data.preview.ready"): break
        pg.wait_for_timeout(1000)
    check('previa_inicial_pronta', pg.evaluate("ST.data.preview.ready"))
    pg.wait_for_timeout(800)
    # área do vídeo
    box = pg.evaluate("(()=>{const r=document.getElementById('phone').getBoundingClientRect();return [r.width,r.height]})()")
    res['video_px'] = box; res['video_pct_tela'] = round(box[0] * box[1] / (1440 * 900) * 100, 1)
    check('video_maior_que_12pct', res['video_pct_tela'] > 12, res['video_pct_tela'])
    # barra superior em uma linha
    bar_h = pg.evaluate("document.querySelector('#studio .sbar').getBoundingClientRect().height")
    res['barra_altura_px'] = bar_h; check('barra_uma_linha', bar_h < 52, bar_h)
    # 3 pistas por padrão
    heads = pg.evaluate("[...document.querySelectorAll('#tlHeads div')].map(x=>x.textContent).filter(Boolean)")
    res['pistas_padrao'] = heads
    check('tres_pistas', heads == ['Vídeo', 'Legendas', 'Áudio'] or set(['Vídeo', 'Legendas', 'Áudio']) <= set(heads), heads)
    # sem abas, com seções
    check('sem_abas', pg.evaluate("!document.querySelector('#stRight [role=tab]')"))
    secs = pg.evaluate("[...document.querySelectorAll('.sec-h b')].map(x=>x.textContent)")
    res['secoes'] = secs
    check('sugestoes_renomeado', 'Sugestões' in secs and not any('Agente' in s for s in secs), secs)
    pg.screenshot(path=f'{OUT}/01_estudio.png')

    # ── edição: selecionar trecho na régua e dar zoom (cliques medidos)
    tl = pg.evaluate("(()=>{const r=document.getElementById('tl').getBoundingClientRect();return [r.left,r.top]})()")
    pps = pg.evaluate("ST.pps")
    x1, x2 = tl[0] + 2 * pps, tl[0] + 5 * pps
    pg.mouse.move(x1, tl[1] + 10); pg.mouse.down(); pg.mouse.move(x2, tl[1] + 10, steps=6); pg.mouse.up()
    pg.wait_for_timeout(200)
    check('selecao_no_inspetor', pg.evaluate("!!document.querySelector('#stRight .insp-item [data-op=zoom]')"))
    pg.screenshot(path=f'{OUT}/02_selecao.png')
    t1 = time.time()
    pg.click('#stRight [data-op=zoom]')
    wait(pg, "ST.proj.zooms.length===1")
    res['zoom_resposta_ms'] = round((time.time() - t1) * 1000)
    heads2 = pg.evaluate("[...document.querySelectorAll('#tlHeads div')].map(x=>x.textContent).filter(Boolean)")
    check('pista_zoom_aparece', 'Zoom' in heads2, heads2)
    check('inspetor_mostra_zoom', pg.evaluate("document.querySelector('#stRight .insp-item b').textContent==='Zoom'"))
    check('estado_nao_salvo', 'não salvas' in pg.evaluate("document.getElementById('stState').textContent"))
    # autosave: em até 4 s fica Salvo, desfazer continua disponível
    wait(pg, "document.getElementById('stState').textContent==='Salvo'", 8000)
    check('autosave_salvo', True)
    check('desfazer_preservado_apos_autosave', pg.evaluate("ST.undo.length>0"))
    # prévia anterior continua tocando enquanto a nova é gerada
    pv = pg.evaluate("ST.data.preview")
    res["previa_apos_editar"] = pv
    check("previa_marcada_anterior", (not pv.get("ready")) and pv.get("stale"), pv)
    check("barra_nao_diz_atualizada", pg.evaluate("document.getElementById('stPrev').textContent").find("atualizada")<0)
    check('previa_anterior_disponivel', pv.get('available'), pv)
    pg.screenshot(path=f'{OUT}/03_zoom_salvo.png')
    for i in range(60):
        if pg.evaluate("ST.data.preview.ready&&!ST.dirty"): break
        pg.wait_for_timeout(1000)
    check('previa_nova_pronta_sozinha', pg.evaluate("ST.data.preview.ready"))
    res['segundos_ate_previa_nova'] = i + 1
    # desfazer volta o zoom
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(150)
    check('ctrl_z', pg.evaluate("ST.proj.zooms.length===0"))
    pg.keyboard.press('Control+Shift+z'); pg.wait_for_timeout(150)
    check('ctrl_shift_z', pg.evaluate("ST.proj.zooms.length===1"))
    # Delete remove o item selecionado
    pg.evaluate("ST.item={kind:'zoom',id:ST.proj.zooms[0].id};drawRight()")
    pg.keyboard.press('Delete'); pg.wait_for_timeout(150)
    check('delete_remove', pg.evaluate("ST.proj.zooms.length===0"))
    # seções: abrir Legendas
    pg.click('[data-sec=caps]'); pg.wait_for_timeout(150)
    check('secao_abre', pg.evaluate("!!document.querySelector('#stRight [data-f=\"captions.enabled\"]')"))
    pg.screenshot(path=f'{OUT}/04_legendas.png')
    # atalhos
    pg.keyboard.press('?'); pg.wait_for_timeout(200)
    check('atalhos_dialogo', pg.evaluate("document.getElementById('keysDialog').open"))
    pg.screenshot(path=f'{OUT}/05_atalhos.png')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
    # Ctrl+Enter uma vez não exporta
    st_before = pg.evaluate("ST.data.status")
    pg.keyboard.press('Control+Enter'); pg.wait_for_timeout(400)
    check('ctrl_enter_pede_confirmacao', pg.evaluate("ST.open") and pg.evaluate("ST.data.status") == st_before)
    # foco no vídeo: F recolhe a linha do tempo e amplia a prévia; volta ao normal; não age em campo de texto
    a0 = pg.evaluate("(()=>{const r=document.getElementById('phone').getBoundingClientRect();return r.width*r.height})()")
    pg.keyboard.press('f'); pg.wait_for_timeout(250)
    a1 = pg.evaluate("(()=>{const r=document.getElementById('phone').getBoundingClientRect();return r.width*r.height})()")
    res['foco_ganho_area_pct'] = round((a1 / a0 - 1) * 100, 1)
    check('foco_amplia_previa', a1 > a0 * 1.15, [a0, a1])
    check('foco_oculta_linha_do_tempo', pg.evaluate("document.getElementById('tlWrap').getBoundingClientRect().height===0"))
    check('foco_botao_estado', pg.evaluate("document.getElementById('tlFold').getAttribute('aria-pressed')==='true'"))
    pg.keyboard.press('f'); pg.wait_for_timeout(250)
    a2 = pg.evaluate("(()=>{const r=document.getElementById('phone').getBoundingClientRect();return r.width*r.height})()")
    check('foco_volta_ao_normal', abs(a2 - a0) < 2 and pg.evaluate("document.getElementById('tlWrap').getBoundingClientRect().height>60"), [a0, a2])
    pg.click('#tlFold'); pg.wait_for_timeout(200); pg.reload(); pg.wait_for_timeout(1500)
    pg.click('[data-clip]'); wait(pg, "typeof ST!=='undefined'&&ST.open&&!!ST.data"); pg.wait_for_timeout(300)
    check('foco_lembrado_ao_reabrir', pg.evaluate("document.getElementById('studio').classList.contains('tl-folded')"))
    pg.keyboard.press('f'); pg.wait_for_timeout(250)
    check('foco_desligado_pela_tecla', pg.evaluate("!document.getElementById('studio').classList.contains('tl-folded')"))
    pg.click('[data-sec=caps]'); pg.wait_for_timeout(150)
    fld = pg.evaluate("(()=>{const e=document.querySelector('#stRight input[type=text],#stRight textarea');if(e){e.focus();return true}return false})()")
    if fld:
        pg.keyboard.type('f'); pg.wait_for_timeout(150)
        check('foco_ignora_digitacao', pg.evaluate("!document.getElementById('studio').classList.contains('tl-folded')"))
        pg.evaluate("document.activeElement.blur()")
    # seletor de qualidade
    modes = pg.evaluate("[...document.querySelectorAll('#stQuality option')].map(o=>o.value)")
    check('quatro_modos_no_exportar', modes == ['rapido', 'equilibrado', 'qualidade', 'entrega'], modes)
    # todas as pistas
    pg.click('#tlAll'); pg.wait_for_timeout(150)
    allh = pg.evaluate("[...document.querySelectorAll('#tlHeads div')].map(x=>x.textContent).filter(Boolean)")
    check('todas_as_pistas', len(allh) == 7, allh)
    pg.click('#tlAll')
    # 1180px e 1024px: barra sem quebra
    for w in (1280, 1024):
        pg.set_viewport_size({'width': w, 'height': 800}); pg.wait_for_timeout(300)
        h = pg.evaluate("document.querySelector('#studio .sbar').getBoundingClientRect().height")
        sw = pg.evaluate("document.querySelector('#studio .sbar').scrollWidth<=document.querySelector('#studio .sbar').clientWidth+1")
        check(f'barra_{w}px', h < 52 and sw, (h, sw))
        pg.screenshot(path=f'{OUT}/06_{w}.png')
    pg.set_viewport_size({'width': 1440, 'height': 900}); pg.wait_for_timeout(300)
    # sair salva e fecha
    pg.evaluate("ST.proj.titles.push({id:'tq',text:'Teste saída',start:1,end:3,style:'big',position:'top',color:'#FFFFFF'});changed()")
    pg.click('#stBack'); pg.wait_for_timeout(1500)
    check('sair_fecha', not pg.evaluate("ST.open"))
    res['console_errors'] = errs
    check('sem_erros_console', not errs, errs)
    b.close()

res['falhas'] = fails
print(json.dumps(res, ensure_ascii=False, indent=1))
sys.exit(1 if fails else 0)
