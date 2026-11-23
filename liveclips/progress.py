"""Progresso REAL das tarefas de render (prévia/exportação) e cancelamento seguro.

O percentual vem do FFmpeg (`-progress pipe:1`, campo `out_time_us` dividido pela duração que ele vai produzir). Não há
temporizador inventando número: etapa sem medida (preparar, capa, qualidade, entrega) aparece como indeterminada.

Uma tarefa = um corte numa execução (`task_id` único por execução). O quadro devolve só a execução mais recente de cada
corte, então evento atrasado de uma execução anterior nunca aparece como se fosse da atual. O percentual nunca recua dentro
da mesma execução (um plano B ou uma nova tentativa só faz a barra esperar). Só chega a 100% em `finish()`, que o motor chama
depois de o arquivo estar gravado, conferido e entregue."""
import subprocess
import tempfile
import threading
import time
import os
from contextlib import contextmanager

STATES = ('na_fila', 'preparando', 'processando', 'finalizando', 'concluido', 'cancelado', 'falhou')
ACTIVE = ('preparando', 'processando', 'finalizando')
MIN_STEP = 0.5            # variação mínima (pontos percentuais) para publicar uma atualização
MIN_GAP = 0.25            # e intervalo mínimo entre atualizações, em segundos
ETA_MIN_PERCENT = 12.0    # estimativa só depois de uma fração mínima do trabalho medido...
ETA_MIN_SECONDS = 8.0     # ...e de tempo suficiente para a velocidade ser estável
KEEP_FINISHED = 120.0     # quanto tempo uma tarefa terminada continua visível


class Cancelled(Exception):
    """A pessoa cancelou a tarefa; o trabalho foi encerrado e os temporários dela removidos."""


class Task:
    def __init__(self, candidate, kind, number, label=''):
        self.id = f'{candidate}:{number}'
        self.candidate = candidate
        self.kind = kind                    # 'exportacao' | 'previa'
        self.label = label
        self.state = 'preparando'
        self.stage = 'Preparando o corte'
        self.percent = 0.0
        self.determinate = False            # há medida real nesta etapa?
        self.started = time.time()
        self.ended = None
        self.error = ''
        self.cancel = threading.Event()
        self.proc = None
        self.lo, self.hi = 0.0, 5.0
        self._last = (0.0, 0.0)
        self._lock = threading.Lock()
        self.version = 0                    # sobe a cada mudança publicada (a interface só redesenha quando muda)
        self.eta_base = None                # (percent, tempo) do início da primeira etapa medida

    # -- escrita (só pelo motor/render) -------------------------------------------------------------------------------
    def phase(self, stage, lo, hi, state='processando'):
        """Começa uma etapa que ocupa [lo, hi] da barra. O percentual atual nunca fica abaixo do que já foi mostrado."""
        with self._lock:
            self.stage = stage
            self.state = state if self.state not in ('concluido', 'cancelado', 'falhou') else self.state
            self.lo, self.hi = float(lo), float(hi)
            self.determinate = False
            self.version += 1

    def report(self, fraction):
        """Fração real (0-1) da etapa atual, medida pelo FFmpeg. Publica com limite de frequência e sem retrocesso."""
        fraction = max(0.0, min(1.0, float(fraction)))
        now = time.time()
        with self._lock:
            value = self.lo + (self.hi - self.lo) * fraction
            if value <= self.percent:
                self.determinate = True
                return
            if value - self._last[0] < MIN_STEP and now - self._last[1] < MIN_GAP and fraction < 1.0:
                return
            self.percent = min(99.0, value)
            self.determinate = True
            if self.eta_base is None and self.percent >= 5.0:
                self.eta_base = (self.percent, now)
            self._last = (self.percent, now)
            self.version += 1

    def requeue(self, reason):
        with self._lock:
            self.state = 'na_fila'
            self.stage = reason
            self.determinate = False
            self.version += 1

    def finish(self, state, error=''):
        with self._lock:
            self.state = state
            self.error = error[-400:]
            self.ended = time.time()
            if state == 'concluido':
                self.percent = 100.0
                self.stage = 'Pronto'
            elif state == 'cancelado':
                self.stage = 'Cancelado'
            elif state == 'falhou':
                self.stage = 'Falhou'
            self.determinate = state == 'concluido'
            self.version += 1

    # -- leitura ------------------------------------------------------------------------------------------------------
    def eta(self):
        """Segundos restantes, só com base suficiente: velocidade medida entre duas leituras reais e parte já concluída."""
        if self.state not in ACTIVE or not self.determinate or self.eta_base is None:
            return None
        base_percent, base_time = self.eta_base
        spent = time.time() - base_time
        done = self.percent - base_percent
        if self.percent < ETA_MIN_PERCENT or spent < ETA_MIN_SECONDS or done <= 0:
            return None
        return max(0, round(spent * (100.0 - self.percent) / done))

    def snapshot(self):
        with self._lock:
            end = self.ended or time.time()
            return dict(task=self.id, candidate=self.candidate, kind=self.kind, label=self.label, state=self.state,
                        stage=self.stage, percent=round(self.percent, 1), determinate=self.determinate,
                        elapsed_s=round(end - self.started), eta_s=self.eta() if not self.ended else None,
                        error=self.error, version=self.version, can_cancel=self.state in ACTIVE)


class Board:
    """Tarefas de render do motor. Só a execução mais recente de cada corte fica no quadro."""

    def __init__(self):
        self.tasks = {}
        self.counter = 0
        self.lock = threading.Lock()

    def start(self, candidate, kind, label=''):
        with self.lock:
            self.counter += 1
            task = Task(candidate, kind, self.counter, label)
            self.tasks[candidate] = task
            return task

    def discard(self, task):
        with self.lock:
            if self.tasks.get(task.candidate) is task:
                del self.tasks[task.candidate]

    def get(self, candidate):
        return self.tasks.get(candidate)

    def cancel(self, candidate):
        """Pede o cancelamento da execução ATUAL do corte. Devolve True se havia o que cancelar."""
        task = self.tasks.get(candidate)
        if not task or task.state not in ACTIVE:
            return False
        task.cancel.set()
        proc = task.proc
        if proc is not None:
            terminate(proc)
        return True

    def snapshot(self):
        now = time.time()
        with self.lock:
            for key in [k for k, t in self.tasks.items() if t.ended and now - t.ended > KEEP_FINISHED]:
                del self.tasks[key]
            tasks = list(self.tasks.values())
        return [t.snapshot() for t in sorted(tasks, key=lambda t: t.started)]


_local = threading.local()


@contextmanager
def scope(task):
    """Liga a tarefa à thread de render: as chamadas de FFmpeg dentro dela publicam progresso e respondem ao cancelamento."""
    previous = getattr(_local, 'task', None)
    _local.task = task
    try:
        yield task
    finally:
        _local.task = previous


def current():
    return getattr(_local, 'task', None)


def phase(stage, lo, hi, state='processando'):
    task = current()
    if task:
        task.phase(stage, lo, hi, state)
        check()


@contextmanager
def expect(duration):
    """Avisa à próxima chamada de `media.run`/`run_stderr` quantos segundos de vídeo ela vai produzir (para medir o progresso)."""
    if current() is None or not duration or duration <= 0:
        yield
        return
    _local.pending = float(duration)
    try:
        yield
    finally:
        _local.pending = None


def take_duration():
    value = getattr(_local, 'pending', None)
    _local.pending = None
    return value if current() is not None else None


def check():
    """Ponto de cancelamento entre etapas."""
    task = current()
    if task and task.cancel.is_set():
        raise Cancelled('Cancelado.')


def terminate(proc):
    """Encerra o processo e os filhos que ele criou; sem processo órfão."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    except OSError:
        pass


def run_ffmpeg(args, cwd=None, duration=None, timeout=900, capture_stderr=False):
    """Executa o FFmpeg lendo o progresso estruturado. Sem tarefa ativa, comporta-se como `media.run` (sem progresso).

    `duration`: duração (s) que este comando vai produzir; sem ela a etapa fica indeterminada. Devolve o stdout (ou o stderr
    quando `capture_stderr`). Erro do FFmpeg vira RuntimeError com o fim do stderr; cancelamento vira `Cancelled`."""
    task = current()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    cmd = list(args)
    if task:
        cmd[1:1] = ['-progress', 'pipe:1', '-nostats']
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=err, creationflags=flags, text=True, errors='replace',
                                stdin=subprocess.DEVNULL)
        if task:
            task.proc = proc
        timer = None
        killed = []

        def watchdog():
            killed.append(True)
            terminate(proc)
        if timeout:
            timer = threading.Timer(timeout, watchdog)
            timer.daemon = True
            timer.start()
        try:
            for line in proc.stdout:
                if task and task.cancel.is_set():
                    terminate(proc)
                    break
                if task and duration and line.startswith('out_time_us='):
                    try:
                        seconds = int(line.split('=', 1)[1]) / 1_000_000
                    except ValueError:
                        continue
                    if seconds >= 0:
                        task.report(seconds / duration)
            proc.wait()
        finally:
            if timer:
                timer.cancel()
            if proc.poll() is None:
                terminate(proc)
            if task:
                task.proc = None
            proc.stdout.close()
        err.seek(0)
        stderr = err.read().decode('utf-8', errors='replace')
    if task and task.cancel.is_set():
        raise Cancelled('Cancelado.')
    if killed:
        raise RuntimeError(f'O FFmpeg passou de {timeout} s e foi encerrado.')
    if proc.returncode:
        raise RuntimeError(stderr[-1800:] or 'A ferramenta de vídeo encerrou com erro.')
    if task and duration:
        task.report(1.0)
    return stderr if capture_stderr else ''
