import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from liveclips import media, syncaudio


def bursts(seconds, seed=1):
    """Envelope aleatório com 'sílabas': padrão único, sem repetição."""
    rng = np.random.RandomState(seed)
    n = int(seconds * 50)
    env = np.abs(rng.randn(n)) * (rng.rand(n) > .6)
    return (env - env.mean()) / env.std()


class Correlate(unittest.TestCase):
    def test_known_offset_positive_and_negative(self):
        ref = bursts(90)
        other = ref[250:]               # other começa 5 s depois do início de ref
        result = syncaudio.correlate(ref, other)
        self.assertTrue(result['ok'], result)
        self.assertAlmostEqual(result['offset'], -5.0, places=1)       # t_other = t_ref - 5
        back = syncaudio.correlate(other, ref)
        self.assertAlmostEqual(back['offset'], 5.0, places=1)

    def test_unrelated_audio_is_refused(self):
        result = syncaudio.correlate(bursts(90, 1), bursts(90, 2))
        self.assertFalse(result['ok']); self.assertIn('correlação', result['reason'])

    def test_repetitive_sound_is_refused_as_ambiguous(self):
        t = np.arange(0, 4500)
        loop = np.tile(np.concatenate([np.ones(10), np.zeros(40)]), 90)[:4500].astype('float32')
        loop = (loop - loop.mean()) / loop.std()
        result = syncaudio.correlate(loop, loop[100:])
        self.assertFalse(result['ok'])
        self.assertTrue(len(t))

    def test_little_overlap_refused(self):
        result = syncaudio.correlate(bursts(60)[:300], bursts(60)[:300])
        self.assertFalse(result['ok']); self.assertIn('em comum', result['reason'])


class WithFiles(unittest.TestCase):
    def make(self, path, seconds, skip=0.0, noise=0.0):
        rng = np.random.RandomState(7)
        rate = 8000
        n = int(seconds * rate)
        gate = np.repeat((rng.rand(int(seconds * 4) + 1) > .45).astype('float32'), rate // 4)[:n]
        wave = (rng.randn(n) * .3 * gate).astype('float32')
        wave = wave[int(skip * rate):]
        wave = wave + rng.randn(len(wave)).astype('float32') * noise
        pcm = (np.clip(wave, -1, 1) * 32767).astype('<i2').tobytes()
        raw = Path(str(path) + '.raw'); raw.write_bytes(pcm)
        media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 's16le', '-ar', str(rate), '-ac', '1', '-i', str(raw), str(path)], timeout=60)

    def test_file_pair_with_offset_and_noise(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'a.wav', Path(temp) / 'b.wav'
            self.make(a, 80)
            self.make(b, 80, skip=3.0, noise=.05)
            result = syncaudio.measure(a, b)
            self.assertTrue(result['ok'], result)
            self.assertAlmostEqual(result['offset'], -3.0, delta=.08)

    def test_constant_tone_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            tone = Path(temp) / 't.wav'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=f=300:d=40', str(tone)], timeout=60)
            result = syncaudio.measure(tone, tone)
            self.assertFalse(result['ok'])

    def test_link_records_refusal_and_load_requires_ok(self):
        with tempfile.TemporaryDirectory() as temp:
            tone = Path(temp) / 't.wav'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=f=300:d=40', str(tone)], timeout=60)
            record = syncaudio.link(temp, tone, tone)
            self.assertFalse(record['ok'])
            self.assertTrue(json.loads((Path(temp) / syncaudio.FILE).read_text(encoding='utf-8'))['reason'])
            self.assertIsNone(syncaudio.load(temp))


if __name__ == '__main__':
    unittest.main()


class InRender(unittest.TestCase):
    """O áudio externo sincronizado substitui o do vídeo na exportação real (a prova é a frequência do áudio exportado)."""
    def test_external_audio_replaces_video_audio(self):
        import subprocess
        from liveclips.app import App
        rate = 8000
        rng = np.random.RandomState(11)
        seconds = 60
        gate = np.repeat((rng.rand(seconds * 4 + 1) > .45).astype('float32'), rate // 4)[:seconds * rate]
        t = np.arange(len(gate)) / rate
        noise = (rng.randn(len(gate)) * .3 * gate).astype('float32')
        tone = (np.sin(2 * np.pi * 1000 * t) * .4 * gate).astype('float32')
        skip = 3.0
        with tempfile.TemporaryDirectory() as temp:
            def wav(name, data):
                raw = Path(temp) / (name + '.raw'); raw.write_bytes((np.clip(data, -1, 1) * 32767).astype('<i2').tobytes())
                out = Path(temp) / (name + '.wav')
                media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 's16le', '-ar', str(rate), '-ac', '1', '-i', str(raw), '-ar', '48000', str(out)], timeout=60)
                return out
            video_audio = wav('v', noise)
            external = wav('e', tone[int(skip * rate):])         # gravação externa começou 3 s depois
            app = App(temp, worker=False); self.addCleanup(app.close)
            store = app.store
            streamer = store.create_streamer('Ext')
            store.save_profile(streamer, dict(__import__('liveclips.store', fromlist=['x']).DEFAULT_PROFILE, content_mode='video', min_free_gb=.5, second_pass='off', cover=False))
            sid = store.new_session(streamer, 'v'); session = store.session(sid)
            file = Path(session['source']) / 'segmento_00000.ts'
            media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds}', '-i', str(video_audio),
                       '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', '-f', 'mpegts', str(file)], timeout=200)
            info = media.probe(file); stat = file.stat()
            with store.connect(True) as c:
                c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns, 'done', '{}'))
            linked = app.action('/api/session/external-audio', dict(session=sid, path=str(external)))['linked']
            self.assertTrue(linked['ok'], linked)
            self.assertAlmostEqual(linked['offset'], -skip, delta=.1)
            with self.assertRaises(ValueError):
                app.action('/api/session/external-audio', dict(session=sid, path='relativo.wav'))
            from liveclips.timeline import build_timeline, plan
            rows = build_timeline(store.segments(sid)); group = rows[0]['group_id']
            store.propose(sid, dict(start=10.0, end=30.0, group_id=group, score=9, reasons=['t'], transcript='x', transcript_segments=[]),
                          plan(rows, 10.0, 30.0, group), store.streamer(streamer)['profile'])
            item = store.rows('SELECT id,version,start,end,parts FROM candidates')[0]
            store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve', editorial_confirmed=True)
            app.engine.do_render(item['id'], False)
            done = store.candidate(item['id'])
            self.assertEqual(done['status'], 'done', done.get('error'))
            folder = Path(done['export_path']); folder = folder if folder.is_dir() else folder.parent
            manifest = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertNotIn('recuo', manifest)
            self.assertAlmostEqual(manifest['external_audio']['offset'], -skip, delta=.1)
            pcm = subprocess.run([media.tool('ffmpeg'), '-v', 'error', '-i', str(folder / 'clipe.mp4'), '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'],
                                 stdout=subprocess.PIPE, timeout=60).stdout
            data = np.frombuffer(pcm, '<i2').astype('float32')
            spectrum = np.abs(np.fft.rfft(data[8000:8000 * 15]))
            peak = float(np.argmax(spectrum[50:])) + 50
            hertz = peak * 8000 / (8000 * 14)
            self.assertAlmostEqual(hertz, 1000, delta=40)     # tom de 1 kHz do áudio externo, não o ruído do vídeo
