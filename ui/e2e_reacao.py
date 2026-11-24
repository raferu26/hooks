"""E2E do Layout de reação: escolher layout → marcar webcam e conteúdo no quadro ORIGINAL → prévia imediata → ajustes →
desfazer → salvar/reabrir → prévia em vídeo (rascunho) com a composição."""
import json, os, subprocess, sys, time
from playwright.sync_api import sync_playwright

PORT = os.environ.get('PORT', '8791')
OUT = os.environ.get('OUT', '/tmp/shots_reacao')
os.makedirs(OUT, exist_ok=True)
res, fails = {}, []


def wait(pg, expr, timeout=15000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            if pg.evaluate(expr): return True
        except Exception:
            pass
        pg.wait_for_timeout(60)
    raise TimeoutError(expr)


def check(name, cond, info=''):
    res[name] = bool(cond)
    if not cond: fails.append(f'{name} {info}')


def drag(pg, fx0, fy0, fx1, fy1):
    b = pg.evaluate("(()=>{const r=document.getElementById('rxImg').getBoundingClientRect();return[r.left,r.top,r.width,r.height]})()")
    x0, y0 = b[0] + fx0 * b[2], b[1] + fy0 * b[3]
    x1, y1 = b[0] + fx1 * b[2], b[1] + fy1 * b[3]
    pg.mouse.move(x0, y0); pg.mouse.down(); pg.mouse.move((x0 + x1) / 2, (y0 + y1) / 2, steps=4); pg.mouse.move(x1, y1, steps=4); pg.mouse.up()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    errs = []
    pg.on('console', lambda m: errs.append(m.type + ': ' + m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
    pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1500)
    pg.click('[data-clip]')
    wait(pg, "typeof ST!=='undefined'&&ST.open&&!!ST.data")
    pg.click('[data-sec="frame"]')
    wait(pg, "!!document.querySelector('[data-rxl=\"cam_ampliada\"]')")
    check('tres_layouts_iniciais', pg.evaluate("document.querySelectorAll('.layout-grid')[0].querySelectorAll('[data-rxl]').length")==3)
    check('mais_layouts_fechado', pg.evaluate("!document.querySelector('[data-rxl=\"cinema\"]')"))
    pg.click('[data-rx="more"]')
    check('mais_layouts_abre_5', pg.evaluate("['cam_embaixo','foco_reacao','dueto','duas_cams','cinema'].every(k=>!!document.querySelector('[data-rxl=\"'+k+'\"]'))"))
    pg.click('[data-rxl="cam_ampliada"]')
    wait(pg, "!!document.getElementById('rxModal')&&document.getElementById('rxImg').complete&&document.getElementById('rxImg').naturalWidth>100")
    nat = pg.evaluate("[document.getElementById('rxImg').naturalWidth,document.getElementById('rxImg').naturalHeight]")
    check('quadro_original_horizontal', nat[0] > nat[1] * 1.7, nat)           # 16:9, sem o crop 9:16
    pg.screenshot(path=f'{OUT}/1_seletor_webcam.png')
    drag(pg, .62, .06, .96, .42)                                             # webcam: canto superior direito
    r = pg.evaluate("RX.picker.rect")
    check('coordenadas_webcam', abs(r['x'] - .62) < .01 and abs(r['y'] - .06) < .01 and abs(r['w'] - .34) < .015 and abs(r['h'] - .36) < .015, r)
    pg.screenshot(path=f'{OUT}/2_webcam_marcada.png')
    # redimensionar pelo canto e mover
    pg.evaluate("1")
    hb = pg.evaluate("(()=>{const r=document.querySelector('.rx-h.se').getBoundingClientRect();return[r.left+r.width/2,r.top+r.height/2]})()")
    pg.mouse.move(*hb); pg.mouse.down(); pg.mouse.move(hb[0] + 15, hb[1] + 10, steps=3); pg.mouse.up()
    r2 = pg.evaluate("RX.picker.rect")
    check('redimensiona_pelo_canto', r2['w'] > r['w'] and r2['h'] > r['h'] and abs(r2['x'] - r['x']) < .003, r2)
    pg.keyboard.press('Control+z')
    r3 = pg.evaluate("RX.picker.rect")
    check('desfazer_no_seletor', abs(r3['w'] - r['w']) < .003, r3)
    pg.keyboard.press('Enter')
    wait(pg, "!!document.getElementById('rxModal')&&RX.picker&&RX.picker.role==='conteudo'&&document.getElementById('rxImg').naturalWidth>100")
    check('segue_para_conteudo', True)
    drag(pg, .02, .03, .60, .97)
    pg.screenshot(path=f'{OUT}/3_conteudo_marcado.png')
    pg.click('#rxOk')
    wait(pg, "!document.getElementById('rxModal')&&!!ST.proj.composition&&Object.keys(ST.proj.composition.regions).length===2")
    reg = pg.evaluate("ST.proj.composition.regions")
    check('regioes_salvas_no_projeto', abs(reg['webcam']['x'] - .62) < .01 and abs(reg['conteudo']['w'] - .58) < .015, reg)
    wait(pg, "!!document.getElementById('rxCanvas')")
    wait(pg, "(()=>{const c=document.getElementById('rxCanvas'),g=c.getContext('2d');const d=g.getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=40)if(d[i]+d[i+1]+d[i+2]>60)n++;return n>200})()")
    check('previa_imediata_desenhada', True)
    plan = pg.evaluate("RX.plan")
    check('previa_usa_plano_do_servidor', plan and plan['ready'] and [l['role'] for l in plan['layers']] == ['conteudo', 'webcam'] and plan['layers'][1]['size'] == [1080, 864], plan and plan['layers'])
    pg.screenshot(path=f'{OUT}/4_painel_ajuste.png')
    # ajuste de divisão (conferir que muda o plano e o projeto)
    pg.evaluate("(()=>{const e=document.querySelector('[data-rxf=\"split\"]');e.value=.55;e.dispatchEvent(new Event('change',{bubbles:true}))})()")
    wait(pg, "ST.proj.composition.params.split===.55")
    wait(pg, "RX.plan&&RX.plan.layers.find(l=>l.role==='webcam').size[1]===1056")
    check('ajuste_divisao_muda_plano', True)
    pg.click('[data-rxfit="content:fit"]')
    wait(pg, "ST.proj.composition.params.content_fit==='fit'")
    wait(pg, "RX.plan&&RX.plan.layers.find(l=>l.role==='conteudo').hidden===0")
    check('mostrar_inteiro_nao_corta', True)
    # desfazer / refazer do Estúdio
    pg.evaluate("undo()")
    check('undo_estudio_reverte_fit', pg.evaluate("ST.proj.composition.params.content_fit!=='fit'"))
    pg.evaluate("redo()")
    check('redo_estudio_refaz_fit', pg.evaluate("ST.proj.composition.params.content_fit==='fit'"))
    # presets: salvar, listar, aplicar um pronto
    wait(pg, "!!document.getElementById('rxPreset')")
    pg.fill('#rxPresetName', 'Meu layout teste')
    pg.check('#rxPresetRegions')
    pg.click('[data-rx="preset-save"]')
    wait(pg, "(RX.presets||[]).some(p=>p.name==='Meu layout teste'&&p.has_regions&&p.compatible)")
    check('preset_salvo_com_regioes', True)
    pg.select_option('#rxPreset', 'b:cinema')
    pg.click('[data-rx="preset-apply"]')
    wait(pg, "ST.proj.composition.layout==='cinema'&&Object.keys(ST.proj.composition.regions).length===2")
    check('preset_pronto_mantem_regioes_ja_marcadas', True)
    pg.select_option('#rxPreset', [o for o in pg.evaluate("RX.presets.filter(p=>p.name==='Meu layout teste').map(p=>p.id)")][0])
    pg.click('[data-rx="preset-apply"]')
    wait(pg, "ST.proj.composition.layout==='cam_ampliada'&&ST.proj.composition.params.split===.55")
    check('preset_salvo_restaura_ajustes', True)
    # aplicar a outros cortes
    if pg.evaluate("!!document.querySelector('[data-rx=\"apply-toggle\"]')"):
        pg.click('[data-rx="apply-toggle"]')
        pg.click('[data-rx="apply-all"]')
        pg.wait_for_timeout(1500)
        applied = pg.evaluate("(async()=>{const me=state.candidates.find(x=>x.id===ST.id);const o=state.candidates.filter(x=>x.session===me.session&&x.id!==ST.id&&x.status!=='replaced');const out=[];for(const c of o){const r=await api('/api/project/get',{id:c.id});out.push(!!(r.project&&r.project.composition))}return out})()")
        check('aplicou_aos_outros_cortes', applied and all(applied), applied)
    pg.screenshot(path=f'{OUT}/4b_presets.png')
    # ocultar uma região do conteúdo (máscara manual)
    pg.click('[data-rx="mask-add"]')
    wait(pg, "!!document.getElementById('rxModal')&&String(RX.picker.role).startsWith('mask:')&&document.getElementById('rxImg').naturalWidth>100")
    drag(pg, .10, .55, .30, .80)
    pg.click('#rxOk')
    wait(pg, "(ST.proj.composition.masks||[]).length===1&&!document.getElementById('rxModal')")
    pg.select_option('[data-rxm$=":kind"]', 'cover')
    wait(pg, "ST.proj.composition.masks[0].kind==='cover'")
    wait(pg, "RX.plan&&(RX.plan.masks||[]).length===1&&RX.plan.masks[0].kind==='cover'")
    check('mascara_manual_marcada_e_no_plano', True)
    pg.screenshot(path=f'{OUT}/4d_mascara.png')
    pg.evaluate("undo()"); pg.evaluate("undo()")
    check('undo_da_mascara', pg.evaluate("(ST.proj.composition.masks||[]).length===0"))
    pg.evaluate("redo()"); pg.evaluate("redo()")
    wait(pg, "(ST.proj.composition.masks||[]).length===1")
    # cenas de reação: criar na seleção, aparecer na timeline, trocar transição
    pg.evaluate("ST.sel={a:1.0,b:4.0}")
    pg.click('[data-rx="scene-add"]')
    wait(pg, "(ST.proj.composition.scenes||[]).length===1")
    check('cena_criada_na_selecao', pg.evaluate("(()=>{const s=ST.proj.composition.scenes[0];return s.start===1&&s.end===4&&s.layout==='foco_reacao'})()"))
    check('cena_aparece_na_timeline', pg.evaluate("!!document.querySelector('.blk.scene')&&!!document.querySelector('[data-row=\"scene\"]')"))
    wait(pg, "ST.item&&ST.item.kind==='scene'")
    pg.select_option('[data-f="composition.scenes.0.fade"]', '0.3')
    wait(pg, "ST.proj.composition.scenes[0].fade===.3")
    check('transicao_suave_definida', True)
    pg.click('[data-rx="suggest"]')
    wait(pg, "RX.sug!==null&&!RX.suggesting", 60000)
    check('sugestoes_mostram_regra_e_aviso', pg.evaluate("!!RX.sug.rule&&/pixels/i.test(RX.sug.disclaimer)&&/Heurística|movimento/.test(document.getElementById('stRight').innerText)"))
    pg.screenshot(path=f'{OUT}/4c_cenas.png')
    pg.evaluate("undo()")
    check('undo_da_transicao', pg.evaluate("ST.proj.composition.scenes[0].fade!==.3"))
    pg.evaluate("redo()")
    pg.keyboard.press('Escape')
    # salvar e reabrir
    wait(pg, "!ST.dirty&&!ST.saving", 20000)
    pg.reload(); pg.wait_for_timeout(1500)
    pg.click('[data-clip]')
    wait(pg, "typeof ST!=='undefined'&&ST.open&&!!ST.data")
    got = pg.evaluate("ST.proj.composition")
    check('persistiu_apos_reabrir', got and got['layout'] == 'cam_ampliada' and got['params']['split'] == .55 and 'conteudo' in got['regions'], got)
    check('cenas_persistiram', got and len(got.get('scenes', [])) == 1 and got['scenes'][0]['fade'] == .3, got)
    # prévia em vídeo (rascunho) com a composição
    pg.click('[data-sec="frame"]') if not pg.evaluate("ST.secs.has('frame')") else None
    wait(pg, "ST.data.preview&&ST.data.preview.available&&ST.data.preview.ready", 120000)
    cand = pg.evaluate("ST.id")
    pg.screenshot(path=f'{OUT}/5_previa_video.png')
    # remover composição volta ao padrão
    pg.click('[data-rx="remove"]')
    wait(pg, "ST.proj.composition===null")
    check('remover_volta_ao_padrao', True)
    check('sem_erros_de_console', not errs, errs[:5])
    b.close()
print(json.dumps(res, indent=1, ensure_ascii=False))
print('FALHAS:', fails if fails else 'nenhuma')
sys.exit(1 if fails else 0)
