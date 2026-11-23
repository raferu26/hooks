"""Testes de qualidade: simulam o que aconteceu de verdade com o Rafa (gravação que cai, falha de placa, fila parada)
para que nada disso volte a acontecer em silêncio."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from liveclips import media
from liveclips.app import App
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store


def make_ts(path, seconds=6, seed=1):
    """Um .ts de verdade, pequeno mas acima do mínimo de 128 KB que o programa exige."""
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=s=640x360:r=15:d={seconds}',
                    '-f', 'lavfi', '-i', f'sine=frequency={300 + seed * 50}:duration={seconds}', '-c:v', 'libx264', '-b:v', '1500k',
                    '-preset', 'ultrafast', '-c:a', 'aac', '-f', 'mpegts', str(path)], check=True)
    old = time.time() - 120
    os.utime(path, (old, old))


def fake_model():
    words = lambda a, b, t: SimpleNamespace(start=a, end=b, word=t, probability=.9)
    seg = lambda a, b, t: SimpleNamespace(start=a, end=b, text=t, words=[words(a, b, t)])
    model = MagicMock()
    model.transcribe.side_effect = lambda *a, **k: (iter([seg(.5, 3.0, 'eu garanto que passo essa fase hoje'), seg(3.5, 5.5, 'perdi de novo que absurdo')]),
                                                    SimpleNamespace(language='pt'))
    return model


class LiveRecordingFlowTests(unittest.TestCase):
    """Gravação simulada: o programa cadastra e analisa enquanto a live ainda grava, e termina tudo ao encerrar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.streamer = self.store.create_streamer('DAVA JONAS')
        self.profile = dict(DEFAULT_PROFILE, min_free_gb=.5, whisper_device='cpu')
        self.store.save_profile(self.streamer, self.profile)
        self.sid = self.store.new_session(self.streamer, 'AO_VIVO', closed=False)
        self.session = self.store.session(self.sid)
        self.store.setting('paused', False)
        self.engine = Engine(self.store)

    def drain(self, limit=60):
        steps = 0
        with patch.object(self.engine, 'get_model', return_value=fake_model()), patch('liveclips.engine.extrair', return_value=dict(audio=[], motion=[], warnings=[])):
            while steps < limit and self.engine.work_once():
                steps += 1
        return steps

    def test_live_segments_are_registered_and_analyzed_while_recording_keeps_going(self):
        for i in range(3):
            make_ts(Path(self.session['source']) / f'segmento_{i:05}.ts', seed=i)
        self.drain()
        rows = self.store.segments(self.sid)
        self.assertEqual([0, 1], [r['seq'] for r in rows])             # o último arquivo ainda está sendo gravado
        self.assertTrue(all(r['status'] == 'done' for r in rows))
        self.assertNotEqual('error', self.store.session(self.sid)['status'])
        make_ts(Path(self.session['source']) / 'segmento_00003.ts', seed=3)   # a gravação continua: chega mais um pedaço
        self.drain()
        self.assertEqual([0, 1, 2], [r['seq'] for r in self.store.segments(self.sid)])

    def test_closing_the_recording_registers_the_last_segment_and_finishes_everything(self):
        for i in range(2):
            make_ts(Path(self.session['source']) / f'segmento_{i:05}.ts', seed=i)
        self.drain()
        with self.store.connect(True) as c:
            c.execute('UPDATE sessions SET closed=1 WHERE id=?', (self.sid,))
        self.drain()
        rows = self.store.segments(self.sid)
        self.assertEqual(2, len(rows))
        self.assertTrue(all(r['status'] == 'done' for r in rows))
        state = App(self.tmp.name, worker=False).state()
        s = next(x for x in state['sessions'] if x['id'] == self.sid)
        self.assertTrue(s['completed'])
        self.assertTrue(self.store.rows('SELECT 1 FROM centers WHERE session=?', (self.sid,)))     # sugestões foram feitas
        json.dumps(state)                                                                        # o estado inteiro é serializável

    def test_a_cuda_failure_on_the_first_segment_does_not_stop_the_recording_from_being_registered(self):
        profile = dict(self.profile, whisper_device='cuda')
        self.store.save_profile(self.streamer, profile)
        for i in range(3):
            make_ts(Path(self.session['source']) / f'segmento_{i:05}.ts', seed=i)
        broken = MagicMock()
        broken.transcribe.side_effect = RuntimeError('Library cublas64_12.dll is not found or cannot be loaded')
        with patch.object(self.engine, 'get_model', return_value=broken), patch('liveclips.engine.extrair', return_value=dict(audio=[], motion=[], warnings=[])), \
                patch('liveclips.engine.whisper_plan', return_value=('cuda', 'float16')):
            for _ in range(12):
                self.engine.work_once()
        # mesmo com a transcrição falhando, os pedaços gravados foram cadastrados (não ficou "0/0 partes")
        self.assertEqual([0, 1], [r['seq'] for r in self.store.segments(self.sid)])
        # e o programa caiu para o processador sozinho, em vez de deixar a sessão com erro
        self.assertTrue(self.engine.cuda_broken)

    def test_open_live_is_analyzed_before_an_old_session(self):
        old = self.store.new_session(self.streamer, 'ANTIGA', closed=True)
        old_session = self.store.session(old)
        make_ts(Path(old_session['source']) / 'segmento_00000.ts', seed=9)
        for i in range(3):
            make_ts(Path(self.session['source']) / f'segmento_{i:05}.ts', seed=i)
        order = []
        real = self.engine.analyze_one

        def spy(session, profile):
            result = real(session, profile)
            if result:                       # só conta quando de fato analisou algo (chamadas vazias não valem)
                order.append(session['id'])
            return result
        with patch.object(self.engine, 'analyze_one', side_effect=spy):
            self.drain()
        live_positions = [i for i, s in enumerate(order) if s == self.sid]
        old_positions = [i for i, s in enumerate(order) if s == old]
        self.assertTrue(live_positions and old_positions)
        self.assertLess(max(live_positions), min(old_positions))


class StateInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(self.tmp.name, worker=False)
        self.streamer = self.app.store.create_streamer('X')
        self.app.store.save_profile(self.streamer, dict(DEFAULT_PROFILE, min_free_gb=.5))

    def test_open_session_without_a_running_capture_is_reported_as_not_recording(self):
        sid = self.app.store.new_session(self.streamer, 'S', closed=False)
        s = next(x for x in self.app.state()['sessions'] if x['id'] == sid)
        self.assertFalse(s['closed'])
        self.assertFalse(s['capture_running'])           # a interface usa isso para avisar "marcada ao vivo, mas sem gravação"

    def test_running_capture_and_recent_file_age_are_exposed(self):
        sid = self.app.store.new_session(self.streamer, 'S', closed=False)
        session = self.app.store.session(sid)
        (Path(session['source']) / 'segmento_00000.ts').write_bytes(b'x' * 10)
        self.app.capture.captures[self.streamer] = SimpleNamespace(state=lambda: dict(session=sid, chat='off'))
        s = next(x for x in self.app.state()['sessions'] if x['id'] == sid)
        self.assertTrue(s['capture_running'])
        self.assertEqual(1, s['files'])
        self.assertLess(s['last_file_age_s'], 30)

    def test_capture_that_ended_by_itself_is_visible_in_the_session(self):
        sid = self.app.store.new_session(self.streamer, 'S', closed=True)
        session = self.app.store.session(sid)
        (Path(session['path']) / 'captura_fim.json').write_text(json.dumps(dict(by='automatico', reason='caiu', at='2026-11-19T09:44:00-03:00')), encoding='utf-8')
        s = next(x for x in self.app.state()['sessions'] if x['id'] == sid)
        self.assertEqual('automatico', s['capture_end']['by'])


class UiContractTests(unittest.TestCase):
    """A interface precisa conhecer os campos que o servidor manda (evita 'o botão sumiu' por renomear campo)."""

    def test_built_page_uses_the_live_fields_the_server_sends(self):
        page = (Path(__file__).resolve().parents[1] / 'liveclips' / 'static' / 'index.html').read_text(encoding='utf-8')
        for token in ('capture_running', 'capture_end', 'last_file_age_s', 'source_url', 'stopcap', 'resumecap', 'Parar gravação', 'Retomar gravação', '/api/preflight', '/api/engine/mode', 'workerLanes', 'perfMode', 'análise ${lag} min atrás', '/api/camera/detect', '/api/camera/accept', 'camAuto'):
            self.assertIn(token, page, token)
        self.assertIn('x.closed]', page)           # o seletor de conteúdo reage a closed (antes ficava com "ao vivo" velho)

    def test_live_bar_classes_do_not_collide_with_absolute_overlay_css(self):
        """Regressão 0.14: a barra usava a classe 'live', que no CSS é a legenda do editor (position:absolute; inset:0)
        e cobria a tela toda. Nenhuma classe da barra pode ter regra posicionada própria no CSS."""
        import re
        page = (Path(__file__).resolve().parents[1] / 'liveclips' / 'static' / 'index.html').read_text(encoding='utf-8')
        css = re.search(r'<style>(.*?)</style>', page, re.S).group(1)
        m = re.search(r"function liveBar\(s\)\{(.*?)\n\s*return `(.*?)`\}", page, re.S)
        self.assertIsNotNone(m)
        used = set()
        for cls in re.findall(r'class="([^"]+)"', m.group(2)):
            used.update(re.findall(r"[a-z][a-z0-9-]*", re.sub(r'\$\{.*?\}', ' ', cls)))
        used.update(re.findall(r"'([a-z][a-z0-9-]*)'", m.group(2)))
        for cls in used:
            for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
                if re.search(r'position\s*:\s*(absolute|fixed)', body) and re.search(r'(^|,)\s*\.%s\s*(,|$)' % re.escape(cls), sel.strip()):
                    self.fail('classe da barra "%s" colide com regra posicionada: %s' % (cls, sel.strip()))


if __name__ == '__main__':
    unittest.main()
