"""Ligação das opções ao renderizador: cada opção ligada no perfil precisa aparecer no filtergraph que o FFmpeg recebe de verdade,
e NÃO pode aparecer quando está desligada. Um teste de função isolada não prova isso; aqui o render real é o juiz.

Dois renders do mesmo corte (fonte escura do conjunto): tudo ligado x tudo desligado. O corte tem pausas cortadas (emendas),
um trecho em câmera lenta (projeto), webcam, áudio, marcador e legenda importada."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import media
from tests import corpus
from tests.test_corpus_cortes import Case
from tests.test_noai_mode import Blocker

PROJECT = dict(speeds=[dict(start=3, end=5, rate=.5)])
CUBE = 'LUT_3D_SIZE 2\n' + '\n'.join(f'{r} {g} {b}' for b in (0, 1) for g in (0, 1) for r in (0, 1)) + '\n'
BLUR = [dict(x=.45, y=.05, w=.2, h=.06)]

# opção do perfil -> (trecho que só pode existir no filtergraph se a opção chegou ao renderizador)
TOKENS = {
    'voice_preset=natural': 'acompressor',
    'lut': 'lut3d=file=',
    'slow_interp=mistura': 'minterpolate',
    'stabilize=leve': 'deshake',
    'auto_music': 'sidechaincompress',
    'cut_fade=suave': 'afade=t=in:st=0:d=0.02',
    'blur_regions': 'boxblur',
    'auto_color=histograma': 'eq=gamma',
    'motion_level=leve': '/motion/',
}


def spy_run(log):
    original = media.run

    def wrapper(args, *a, **k):
        log.append(' '.join(str(x) for x in args))
        return original(args, *a, **k)
    return wrapper


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.blocker = Blocker()
        sys.meta_path.insert(0, cls.blocker)
        root = Path(cls.temp.name)
        cls.sources = corpus.make_all(root / 'midias')
        cls.dark = corpus.make_dark(cls.sources['g'], root / 'midias' / 'g_escura.ts')
        music = root / 'trilha.wav'
        media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=60:sample_rate=48000', '-ac', '2', str(music)], timeout=60)

        def prepare(store, base):
            (store.root / 'luts').mkdir(exist_ok=True)
            (store.root / 'luts' / 'teste.cube').write_text(CUBE, encoding='utf-8')
        common = dict(srt=corpus.G_SRT, marker=corpus.G_MARKER, project=PROJECT, prepare=prepare, camera_rect=corpus.G_CAM['rect'], title_template='',
                      with_preview=False)
        cls.logs = dict(on=[], off=[])
        with mock.patch.object(media, 'run', spy_run(cls.logs['on'])):
            cls.on = Case(root / 'on', cls.dark, voice_preset='natural', auto_color='histograma', lut='teste.cube', lut_strength=1.0, cut_fade='suave',
                          slow_interp='mistura', stabilize='leve', auto_music=True, music_authorized=True, music_path=str(music), music_volume=.1,
                          blur_regions=BLUR, motion_level='leve', **common)
        with mock.patch.object(media, 'run', spy_run(cls.logs['off'])):
            cls.off = Case(root / 'off', cls.dark, voice_preset='off', **common)
        cls.text = {k: '\n'.join(v) for k, v in cls.logs.items()}

    @classmethod
    def tearDownClass(cls):
        sys.meta_path.remove(cls.blocker)
        cls.temp.cleanup()

    def manifest(self, case):
        return json.loads((case.folder / 'manifesto.json').read_text(encoding='utf-8'))

    def test_00_both_rendered_without_models(self):
        for case in (self.on, self.off):
            self.assertEqual(case.done['status'], 'done', case.done.get('error'))
        self.assertEqual(self.blocker.attempts, [])
        self.assertTrue(self.text['on'] and self.text['off'], 'nenhum comando capturado')

    def test_01_every_option_reaches_the_renderer(self):
        missing = [f'{option} -> {token}' for option, token in TOKENS.items() if token not in self.text['on']]
        self.assertEqual(missing, [], f'opção ligada que não chegou ao filtergraph: {missing}')

    def test_02_nothing_leaks_when_the_options_are_off(self):
        leaked = [f'{option} -> {token}' for option, token in TOKENS.items() if token in self.text['off']]
        self.assertEqual(leaked, [], f'efeito presente com a opção desligada: {leaked}')

    def test_03_no_retreat_and_the_reports_exist(self):
        on = self.manifest(self.on)
        self.assertNotIn('recuo', on, on.get('recuo'))
        self.assertTrue(on.get('color_report'))
        self.assertNotIn('recuo', self.manifest(self.off))

    def test_04_colour_correction_changes_the_picture(self):
        import cv2
        import numpy as np

        def luma(case):
            cap = cv2.VideoCapture(str(case.video))
            cap.set(cv2.CAP_PROP_POS_MSEC, 4000)
            ok, frame = cap.read()
            cap.release()
            self.assertTrue(ok)
            return float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))        # quadro inteiro: contraste maior escurece o fundo e clareia o resto
        on, off = luma(self.on), luma(self.off)
        self.assertGreater(on, off + 2, (on, off))        # fonte escura: a correção (gama + contraste) levanta o quadro

    def test_05_music_is_audible_in_the_cut_pause(self):
        import numpy as np
        from tests import medidas
        samples = medidas.audio(self.on.video)
        w = medidas.windows(samples)
        tone = np.abs(np.fft.rfft(w, axis=1))[:, 2] / medidas.WINDOW        # 200–300 Hz: a trilha é 220 Hz
        base = medidas.windows(medidas.audio(self.off.video))
        base_tone = np.abs(np.fft.rfft(base, axis=1))[:, 2] / medidas.WINDOW
        quiet = np.where(base_tone < 1e-4)[0]                              # janelas sem voz no render sem música
        self.assertGreater(len(quiet), 100)
        n = min(len(tone), len(base_tone))
        quiet = quiet[quiet < n]
        self.assertGreater(float(np.median(tone[quiet])), 1e-3)            # com música, esse silêncio tem trilha

    def test_06_slow_motion_and_seams_are_in_the_plan(self):
        plan = self.on.plan
        kinds = [s['kind'] for s in plan['segments']]
        self.assertTrue(any(k in ('speed', 'velocidade', 'slow') for k in kinds) or any(abs(float(str(s.get('speed', '1')).split('/')[-1] or 1)) > 1 for s in plan['segments']),
                        kinds)


if __name__ == '__main__':
    unittest.main()
