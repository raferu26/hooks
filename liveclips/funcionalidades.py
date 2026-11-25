"""O que esta versão DECLARA ter, e a verificação de que está de fato no produto (backend + interface + render).

Existe porque uma versão já foi entregue relatando recursos que os testes de desenvolvimento aprovavam mas que o usuário não via. Aqui a
verificação roda sobre o que está INSTALADO (catálogo, HTML distribuído, rotas, FFmpeg real) e é usada por três lugares: o autoteste do
instalador (`selfcheck`), o diagnóstico (`/api/diagnostico`, DIAGNOSTICO_WINDOWS.bat) e o bloqueio de empacotamento (`tools/empacotar_release.py`)."""
import subprocess
import tempfile
from pathlib import Path

from . import composition

ROOT = Path(__file__).resolve().parent.parent
LAYOUT_IDS = ('cam_compacta', 'cam_ampliada', 'cam_flutuante', 'cam_embaixo', 'foco_reacao', 'dueto', 'duas_cams', 'cinema')
MAIN_IDS = ('cam_compacta', 'cam_ampliada', 'cam_flutuante')

# id → rótulo. O empacotador grava esta lista em BUILD_INFO.json e o autoteste confere cada item no produto instalado.
EXPECTED = {
    'layouts_8': 'Oito layouts de reação (3 principais + 5 em "Mais layouts")',
    'selecao_regioes': 'Seleção visual de webcam e conteúdo no quadro original',
    'previa_imediata': 'Prévia imediata da composição',
    'presets': 'Layouts salvos (salvar, renomear, duplicar, excluir, aplicar)',
    'aplicar_cortes': 'Aplicar a outros cortes',
    'cenas': 'Cenas de reação por intervalo (timeline, transição suave)',
    'mascaras': 'Ocultar regiões à mão (desfocar ou cobrir)',
    'sugestoes': 'Sugestões determinísticas de troca de layout',
}

# Marcadores que TÊM de existir no HTML distribuído (uma coisa por recurso; nomes vêm de ui/reacao.js).
UI_MARKERS = {
    'layouts_8': ['data-rxl', 'Mais layouts', 'Layout de reação'] + [f'{i}:' for i in LAYOUT_IDS],
    'selecao_regioes': ['rxOpenPicker', 'rxImg', 'rx-h', '/media/srcframe'],
    'previa_imediata': ['rxCanvas', '/api/composition/resolve'],
    'presets': ['preset-save', 'preset-rename', 'preset-dup', 'preset-del', 'preset-apply', '/api/composition/presets'],
    'aplicar_cortes': ['apply-all', '/api/composition/apply'],
    'cenas': ['scene-add', 'rxSceneEditor', "blk('scene'"],
    'mascaras': ['mask-add', 'mask-edit'],
    'sugestoes': ['/api/composition/suggest', 'sug-ok', 'sug-no'],
}



def check_catalog():
    cat = composition.catalog()
    ids = [l['id'] for l in cat['layouts']]
    main = [l['id'] for l in cat['layouts'] if l['group'] == 'main']
    problems = []
    if sorted(ids) != sorted(LAYOUT_IDS):
        problems.append(f'catálogo com {len(ids)} layouts: {ids}')
    if tuple(main) != MAIN_IDS:
        problems.append(f'principais fora do esperado: {main}')
    return not problems, f'{len(ids)} layouts no catálogo ({len(main)} principais)' if not problems else '; '.join(problems)


def check_ui(html_path=None):
    """O HTML que o servidor entrega contém os controles de cada recurso declarado?"""
    path = Path(html_path or ROOT / 'liveclips' / 'static' / 'index.html')
    try:
        html = path.read_text(encoding='utf-8')
    except OSError as exc:
        return False, f'interface não encontrada: {exc}'
    missing = {k: [m for m in marks if m not in html] for k, marks in UI_MARKERS.items()}
    missing = {k: v for k, v in missing.items() if v}
    return not missing, 'interface contém todos os controles esperados' if not missing else 'faltam na interface: ' + '; '.join(f'{k}={v[:3]}' for k, v in missing.items())


def check_routes():
    """As rotas novas estão registradas no servidor desta instalação?"""
    src = (ROOT / 'liveclips' / 'app.py').read_text(encoding='utf-8')
    missing = [r for r in ('/api/composition/resolve', '/api/composition/presets', '/api/composition/apply', '/api/composition/suggest') if r not in src]
    if "'srcframe'" not in src:
        missing.append('/media/srcframe')
    return not missing, 'rotas de composição registradas' if not missing else 'rotas ausentes: ' + ', '.join(missing)


def check_presets(root):
    items = composition.list_presets(root)
    builtin = [i for i in items if i['builtin']]
    return len(builtin) == 7 and all(i['layout'] in LAYOUT_IDS for i in builtin), f'{len(builtin)} presets prontos registrados'


def check_render(ffmpeg='ffmpeg', timeout=120):
    """Os oito layouts rodam no FFmpeg DESTA máquina (filtros presentes, filtergraph aceito) e saem em 1080x1920."""
    from . import media
    ffmpeg = media.tool('ffmpeg') if ffmpeg == 'ffmpeg' else ffmpeg
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
    reg = dict(webcam=dict(x=.62, y=.05, w=.34, h=.34), conteudo=dict(x=0, y=0, w=.6, h=1), webcam2=dict(x=.3, y=.05, w=.3, h=.3))
    bad = []
    with tempfile.TemporaryDirectory(prefix='hooks_func_') as tmp:
        src = Path(tmp) / 'fonte.mp4'
        cp = subprocess.run([ffmpeg, '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=10:d=1', '-c:v', 'libx264',
                             '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(src)], capture_output=True, timeout=timeout, creationflags=flags)
        if cp.returncode:
            return False, 'não gerou a mídia de teste: ' + cp.stderr.decode('utf-8', 'replace')[-200:]
        for layout in LAYOUT_IDS:
            comp = composition.clean(dict(layout=layout, regions=reg, masks=[dict(kind='blur', region=dict(x=.1, y=.1, w=.1, h=.1))],
                                          scenes=[dict(id='a', start=.2, end=.8, layout='cinema', fade=.2)] if layout != 'cinema' else []), 1)
            segs = composition.segments(comp, [(0, 1, 0, 1)], 1, 10)
            graph = composition.video_graph(comp, 640, 360, fps=10, segs=segs) + ';[base]format=gray[o]'
            cp = subprocess.run([ffmpeg, '-nostdin', '-loglevel', 'error', '-i', str(src), '-filter_complex', graph, '-map', '[o]', '-frames:v', '2',
                                 '-f', 'rawvideo', '-'], capture_output=True, timeout=timeout, creationflags=flags)
            if cp.returncode or len(cp.stdout) != 2 * 1080 * 1920:
                bad.append(f'{layout}: ' + (cp.stderr.decode('utf-8', 'replace')[-120:] or f'{len(cp.stdout)} bytes'))
    return not bad, 'os 8 layouts renderizam (com máscara e cena) em 1080x1920' if not bad else '; '.join(bad)[:600]


def declared(build=None):
    """Recursos declarados pelo BUILD_INFO (ou todos, em desenvolvimento)."""
    from . import buildinfo
    info = build or buildinfo.read()
    return [k for k in info.get('funcionalidades_esperadas', list(EXPECTED)) if k in EXPECTED]


def run_all(root=None, render=True):
    """[(passo, ok, detalhe)] — usado pelo autoteste, pelo diagnóstico e pelo empacotador."""
    out = [('catalogo_8_layouts', *check_catalog()), ('interface_com_controles', *check_ui()), ('rotas_registradas', *check_routes())]
    if root is not None:
        out.append(('presets_prontos', *check_presets(root)))
    if render:
        out.append(('render_8_layouts', *check_render()))
    return out
