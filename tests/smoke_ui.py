"""Fumaça de navegador (manual): abre cada tela e cada aba e falha se houver erro de JavaScript.
Uso: python tests/smoke_ui.py PORTA   (com o servidor rodando)   — requer playwright + Chrome."""
import sys
from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else '8765'
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    pg.on('pageerror', lambda e: errors.append('PAGEERROR ' + str(e)))
    pg.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    pg.goto(f'http://127.0.0.1:{PORT}/'); pg.wait_for_timeout(1500)
    for nav in pg.eval_on_selector_all('[data-nav]', 'els=>[...new Set(els.filter(e=>!e.classList.contains("hide")).map(e=>e.dataset.nav))]'):
        try:
            pg.click(f'[data-nav="{nav}"]', timeout=2000); pg.wait_for_timeout(400)
        except Exception as exc:
            errors.append(f'nav {nav}: {exc}')
    for pane in pg.eval_on_selector_all('[data-pane-go]', 'els=>els.map(e=>e.dataset.paneGo)'):
        try:
            pg.click('[data-nav="settings"]', timeout=2000); pg.click(f'[data-pane-go="{pane}"]', timeout=2000); pg.wait_for_timeout(200)
        except Exception as exc:
            errors.append(f'pane {pane}: {exc}')
    try:
        pg.click('[data-nav="clips"]', timeout=2000); pg.wait_for_timeout(500)
        pg.click('[data-clip]', timeout=3000); pg.wait_for_timeout(2000)
        for tab in pg.eval_on_selector_all('[data-tab]', 'els=>els.map(e=>e.dataset.tab)'):
            pg.click(f'[data-tab="{tab}"]', timeout=2000); pg.wait_for_timeout(300)
    except Exception as exc:
        errors.append('studio: ' + str(exc))
    print('\n'.join(errors) or 'SEM ERROS DE JAVASCRIPT')
    b.close()
sys.exit(1 if errors else 0)
