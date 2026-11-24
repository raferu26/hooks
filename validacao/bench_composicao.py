"""Benchmark da composição de reação: tempo e memória de exportação/rascunho (referência x composição x cenas) e latências da API.

Uso: PYTHONPATH=. python3 validacao/bench_composicao.py [SEGUNDOS=20] [REPETICOES=3]   → validacao/resultados_composicao.json
Cada medição roda em um processo separado (memória de pico dos processos filhos = FFmpeg). Mídia sintética 1080p30."""
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
REG = dict(webcam=dict(x=.70, y=.04, w=.28, h=.30), conteudo=dict(x=0, y=0, w=.6, h=1))
VARIANTS = {
    'referencia': None,
    'composicao': dict(layout='cam_ampliada', regions=REG),
    'composicao_2_cenas': dict(layout='cam_ampliada', regions=REG,
                               scenes=[dict(id='a', start=4, end=9, layout='foco_reacao', fade=.3), dict(id='b', start=12, end=16, layout='cinema')]),
    'composicao_blur_cinema': dict(layout='cinema', regions=REG, params=dict(bg='blur')),
}

CHILD = r'''
import json, resource, sys, time
sys.path.insert(0, %(root)r)
from pathlib import Path
from liveclips import media, project, editing
from liveclips.store import DEFAULT_PROFILE
src, comp, mode, seconds, out = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], float(sys.argv[4]), sys.argv[5]
profile = dict(DEFAULT_PROFILE, camera_rect=[0, 0, .25, .25], min_free_gb=.1, threads=4, content_mode='video')
plan = editing.plan_edits({'start': 0, 'end': seconds}, {}, profile=profile); plan['decisions'] = []
parts = [{'path': src, 'sha': media.sha_file(Path(src)), 'seq': 0, 'in': 0.0, 'out': seconds, 'global_start': 0, 'global_end': seconds, 'group_id': 'g'}]
cand = {'id': 'bench', 'start': 0, 'end': seconds, 'parts': parts, 'profile': profile, 'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}}}
cand['data']['project'] = project.clean(dict(composition=comp) if comp else {}, seconds)
t0 = time.perf_counter()
clip = media.render(cand, [], out, 'draft' if mode == 'draft' else False, pipeline='single')
dt = time.perf_counter() - t0
print(json.dumps(dict(seconds=round(dt, 2), rss_mb=round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024), size_mb=round(Path(clip).stat().st_size / 1e6, 2))))
'''


def main():
    root = str(HERE.parent)
    results = dict(seconds_of_media=SECONDS, repetitions=REPS, cpu_count=os.cpu_count(), runs={})
    with tempfile.TemporaryDirectory() as temp:
        src = Path(temp) / 'fonte.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=s=1920x1080:r=30:d={SECONDS}', '-f', 'lavfi',
                        '-i', f'sine=f=300:d={SECONDS}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-c:a', 'aac', '-shortest', str(src)], check=True)
        for mode in ('final', 'draft'):
            for name, comp in VARIANTS.items():
                runs = []
                for n in range(REPS):
                    out = Path(temp) / f'{mode}_{name}_{n}'
                    out.mkdir()
                    r = subprocess.run([sys.executable, '-W', 'ignore', '-c', CHILD % dict(root=root), str(src), json.dumps(comp), mode, str(SECONDS), str(out)],
                                       capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=root))
                    if r.returncode:
                        runs.append(dict(error=r.stderr[-400:]))
                        continue
                    runs.append(json.loads(r.stdout.strip().splitlines()[-1]))
                ok = [x for x in runs if 'error' not in x]
                results['runs'][f'{mode}/{name}'] = dict(
                    median_seconds=statistics.median(x['seconds'] for x in ok) if ok else None,
                    max_rss_mb=max(x['rss_mb'] for x in ok) if ok else None, size_mb=ok[0]['size_mb'] if ok else None,
                    all_seconds=[x['seconds'] for x in ok], errors=[x['error'] for x in runs if 'error' in x])
                print(mode, name, results['runs'][f'{mode}/{name}'], flush=True)
        # latência do cálculo de camadas (o que a interface chama a cada ajuste)
        sys.path.insert(0, root)
        from liveclips import composition as C
        comp = C.clean(dict(layout='cam_ampliada', regions=REG, scenes=VARIANTS['composicao_2_cenas']['scenes']), SECONDS)
        t = time.perf_counter()
        for _ in range(2000):
            C.resolve(comp, 1920, 1080)
        results['resolve_ms'] = round((time.perf_counter() - t) / 2000 * 1000, 3)
        t = time.perf_counter()
        for _ in range(500):
            C.video_graph(comp, 1920, 1080, segs=C.segments(comp, [(0, SECONDS, 0, SECONDS)], SECONDS, 30))
        results['graph_build_ms'] = round((time.perf_counter() - t) / 500 * 1000, 3)
    (HERE / 'resultados_composicao.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
