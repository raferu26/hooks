"""Telemetria local e modos de qualidade (P12/F25/F26).

Tudo fica no computador do usuário (`telemetria.jsonl`, uma linha por etapa), sem envio externo. Serve para achar o
gargalo real com percentis (p50/p95), não médias. Os modos trocam apenas parâmetros de codificação e do laço de revisão;
nenhum modo desliga a checagem de qualidade.
"""
import json
import math
import time
from contextlib import contextmanager
from pathlib import Path

# Modos de qualidade da exportação final (0.19: aplicados de verdade no caminho principal, não só no plano B).
# `crf`/`preset`: libx264 (CPU). Parâmetros por placa de vídeo ficam em `hardware.mode_arguments`.
# `revisoes` = limite de correções automáticas (máx. 2, regra do dossiê). `audio` = AAC em kbit/s.
# `cpu_only`: o modo ignora a placa de vídeo e usa o x264 (codificadores de placa não são equivalentes ao x264
# lento na mesma taxa; o modo Entrega existe para o arquivo que vai ao ar e prioriza a imagem sobre o tempo).
MODES = {
    'rapido': dict(label='Rápido', preset='veryfast', crf=21, x264='', audio=128, revisoes=0, cpu_only=False,
                   note='Exporta mais depressa. Arquivo maior e um pouco mais granulado em cenas com muito movimento.'),
    'equilibrado': dict(label='Equilibrado', preset='medium', crf=18, x264='', audio=160, revisoes=1, cpu_only=False,
                        note='Padrão: boa imagem em tempo razoável (mesmo ajuste das versões anteriores).'),
    'qualidade': dict(label='Qualidade', preset='slow', crf=16, x264='aq-mode=3', audio=192, revisoes=2, cpu_only=False,
                      note='Mais lento. Menos blocos em fundos escuros e degradês. Com placa de vídeo usa o ajuste mais caprichado dela.'),
    'entrega': dict(label='Entrega', preset='slower', crf=15, x264='aq-mode=3', audio=192, revisoes=2, cpu_only=True,
                    note='O mais lento: sempre na CPU (x264), para o arquivo que vai ao ar. Pode levar várias vezes o tempo do vídeo.'),
}
DEFAULT_MODE = 'equilibrado'


def mode_of(name):
    return MODES.get(name) or MODES[DEFAULT_MODE]


def mode_name(name):
    return name if name in MODES else DEFAULT_MODE


def encode_args(profile):
    """(preset, crf) do x264 na exportação final para o perfil."""
    mode = mode_of((profile or {}).get('quality_mode'))
    return mode['preset'], str(mode['crf'])


def cpu_args(name):
    """Argumentos completos do libx264 para o modo."""
    mode = mode_of(name)
    args = ['-c:v', 'libx264', '-preset', mode['preset'], '-crf', str(mode['crf'])]
    if mode['x264']:
        args += ['-x264-params', mode['x264']]
    return args


def audio_bitrate(profile):
    return str(mode_of((profile or {}).get('quality_mode'))['audio']) + 'k'


def percentile(values, q):
    """Percentil por interpolação linear; lista vazia -> None."""
    data = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * q
    low = int(math.floor(pos))
    high = min(low + 1, len(data) - 1)
    return data[low] + (data[high] - data[low]) * (pos - low)


class Telemetry:
    def __init__(self, root):
        self.path = Path(root) / 'telemetria.jsonl'

    def record(self, stage, seconds, **extra):
        row = dict(at=time.strftime('%Y-%m-%dT%H:%M:%S'), stage=stage, seconds=round(float(seconds), 3), **extra)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        except OSError:
            pass            # telemetria nunca derruba o trabalho

    @contextmanager
    def stage(self, name, **extra):
        started = time.perf_counter()
        status = 'ok'
        try:
            yield
        except Exception:
            status = 'erro'
            raise
        finally:
            self.record(name, time.perf_counter() - started, status=status, **extra)

    def rows(self, limit=5000):
        try:
            lines = self.path.read_text(encoding='utf-8').splitlines()[-limit:]
        except OSError:
            return []
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def report(self):
        return summarize(self.rows())


def summarize(rows):
    """Por etapa: contagem, p50, p95, máximo e taxa de erro; e a etapa que mais pesa no tempo total."""
    stages = {}
    for r in rows:
        stages.setdefault(r.get('stage', '?'), []).append(r)
    out = {}
    for name, items in stages.items():
        secs = [i['seconds'] for i in items]
        out[name] = dict(n=len(items), p50=round(percentile(secs, .5), 2), p95=round(percentile(secs, .95), 2), max=round(max(secs), 2),
                         total=round(sum(secs), 2), erros=sum(1 for i in items if i.get('status') == 'erro'))
    gargalo = max(out, key=lambda k: out[k]['total']) if out else None
    return dict(etapas=out, gargalo=gargalo, amostras=len(rows),
                aviso='Poucas amostras: percentis ainda instáveis.' if len(rows) < 20 else None)
