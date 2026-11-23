import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import denoise, editing, media, qc
from liveclips.store import DEFAULT_PROFILE

MODEL = Path('/tmp/bd.rnnn')  # só existe onde o modelo já foi baixado; os outros testes não dependem dele


def ffmpeg(*args):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', *args], check=True)


class Denoise(unittest.TestCase):
    def test_fetch_verifies_hash_and_is_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                denoise.fetch(root, opener=lambda url: b'arquivo errado')
            self.assertFalse(denoise.status(root)['ready'])
            self.assertFalse(list((Path(root) / 'models').glob('*')))
            with self.assertRaises(ValueError):
                denoise.fetch(root, opener=lambda url: (_ for _ in ()).throw(OSError('sem rede')))

    @unittest.skipUnless(MODEL.is_file() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == denoise.SHA256, 'modelo não baixado')
    def test_fetch_accepts_the_real_model(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(denoise.fetch(root, opener=lambda url: MODEL.read_bytes())['ready'])
            self.assertTrue(denoise.fetch(root, opener=lambda url: b'nao deve chamar')['ready'])  # já instalado


class Render(unittest.TestCase):
    def source(self, root, volume=1.0):
        out = Path(root) / 'fonte.ts'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30:duration=8',
               '-f', 'lavfi', '-i', f'sine=f=300:sample_rate=48000:duration=8,volume={volume}',
               '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(out))
        return out

    def candidate(self, source, voice):
        base = dict(DEFAULT_PROFILE, camera_rect=[0, 0, .25, .25], min_free_gb=.1, threads=2)
        plan = editing.plan_edits({'start': 0, 'end': 8}, {}, profile=base)
        plan['decisions'] = []
        parts = [{'path': str(source), 'sha': media.sha_file(source), 'seq': 0, 'in': 0.0, 'out': 8.0, 'global_start': 0, 'global_end': 8, 'group_id': 'g'}]
        project = dict(version=1, voice=voice)
        return {'id': 'x' + voice.get('mode', 'n'), 'start': 0, 'end': 8, 'parts': parts, 'profile': base,
                'data': {'edit_plan': plan, 'edit_overrides': {}, 'editorial_audit': {}, 'project': project}}

    def test_peak_limiter_keeps_true_peak_below_the_target_on_hot_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = media.render(self.candidate(self.source(temp, volume=8), dict(clean=False)), [], temp, False, pipeline='single', root=temp)
            measured = qc.measure_loudness(clip)
            self.assertIsNotNone(measured)
            self.assertLess(measured['input_tp'], -.9)

    def test_neural_without_model_falls_back_and_says_so(self):
        with tempfile.TemporaryDirectory() as temp:
            captured = {}
            real = media.voice_mode

            def spy(project, root, scratch, meta, *rest):
                value = real(project, root, scratch, meta, *rest)
                captured['mode'] = value
                captured['warning'] = meta.get('voice_warning')
                return value
            media.voice_mode = spy
            try:
                clip = media.render(self.candidate(self.source(temp), dict(clean=True, mode='neural')), [], temp, False, pipeline='single', root=temp)
            finally:
                media.voice_mode = real
            self.assertTrue(clip.is_file())
            self.assertIs(captured['mode'], True)
            self.assertIn('não instalado', captured['warning'])

    @unittest.skipUnless(MODEL.is_file(), 'modelo não baixado')
    def test_neural_mode_renders_with_the_installed_model(self):
        with tempfile.TemporaryDirectory() as temp:
            denoise.path(temp).parent.mkdir(parents=True)
            denoise.path(temp).write_bytes(MODEL.read_bytes())
            clip = media.render(self.candidate(self.source(temp), dict(clean=True, mode='neural')), [], temp, False, pipeline='single', root=temp)
            self.assertTrue(clip.is_file())
            self.assertTrue(media.probe(clip)['has_audio'])


if __name__ == '__main__':
    unittest.main()
