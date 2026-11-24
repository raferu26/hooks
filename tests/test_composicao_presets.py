"""Presets de layout de reação e aplicação a vários cortes (API real, vídeos sintéticos)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import composition as C
from liveclips import media
from liveclips.app import App
from liveclips.store import DEFAULT_PROFILE
from liveclips.timeline import build_timeline, plan

REG = dict(webcam=dict(x=.62, y=.05, w=.34, h=.36), conteudo=dict(x=0, y=0, w=.6, h=1))


def comp(layout='cam_ampliada', regions=REG, **params):
    return C.clean(dict(layout=layout, regions=regions, params=params))


class Presets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_builtin_presets_exist_and_cannot_carry_regions(self):
        items = C.list_presets(self.temp.name)
        self.assertEqual(sum(1 for i in items if i['builtin']), 7)
        self.assertTrue(all(not i['has_regions'] and i['layout'] in C.LAYOUTS for i in items))

    def test_save_rename_duplicate_delete_roundtrip_on_disk(self):
        saved = C.save_preset(self.temp.name, '  Meu   layout Coringa ', comp(split=.5), source=(1920, 1080), with_regions=True)
        self.assertEqual(saved['name'], 'Meu layout Coringa')
        self.assertTrue((Path(self.temp.name) / C.PRESET_FILE).exists())
        C.rename_preset(self.temp.name, saved['id'], 'Coringa 2')
        copy = C.duplicate_preset(self.temp.name, saved['id'])
        self.assertEqual(copy['name'], 'Coringa 2 (cópia)')
        names = [i['name'] for i in C.list_presets(self.temp.name) if not i['builtin']]
        self.assertEqual(names, ['Coringa 2', 'Coringa 2 (cópia)'])
        C.delete_preset(self.temp.name, saved['id'])
        self.assertEqual([i['name'] for i in C.list_presets(self.temp.name) if not i['builtin']], ['Coringa 2 (cópia)'])
        with self.assertRaises(ValueError):
            C.delete_preset(self.temp.name, 'nao-existe')

    def test_name_rules(self):
        C.save_preset(self.temp.name, 'A', comp())
        with self.assertRaises(ValueError):
            C.save_preset(self.temp.name, 'a', comp())      # nome repetido (sem diferenciar maiúsculas)
        with self.assertRaises(ValueError):
            C.save_preset(self.temp.name, '   ', comp())
        with self.assertRaises(ValueError):
            C.save_preset(self.temp.name, 'B', None)

    def test_regions_only_apply_to_sources_with_similar_aspect(self):
        C.save_preset(self.temp.name, 'canal', comp(), source=(1920, 1080), with_regions=True)
        C.save_preset(self.temp.name, 'sem regiões', comp(), source=(1920, 1080), with_regions=False)
        same = {i['name']: i['compatible'] for i in C.list_presets(self.temp.name, (1280, 720))}
        self.assertTrue(same['canal'])
        self.assertFalse(same['sem regiões'])
        other = {i['name']: i['compatible'] for i in C.list_presets(self.temp.name, (1080, 1920))}
        self.assertFalse(other['canal'])                       # vídeo vertical: não reaproveita coordenadas

    def test_corrupt_preset_file_is_ignored_not_fatal(self):
        (Path(self.temp.name) / C.PRESET_FILE).write_text('{ quebrado', encoding='utf-8')
        self.assertEqual(sum(1 for i in C.list_presets(self.temp.name) if not i['builtin']), 0)
        C.save_preset(self.temp.name, 'novo', comp())            # e continua gravando

    def test_limit(self):
        for n in range(C.PRESET_LIMIT):
            C.save_preset(self.temp.name, f'p{n}', comp())
        with self.assertRaises(ValueError):
            C.save_preset(self.temp.name, 'extra', comp())


def make_video(path, size='1280x720', seconds=40):
    subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=s={size}:r=15:d={seconds}',
                    '-f', 'lavfi', '-i', f'sine=frequency=300:duration={seconds}', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
                    '-shortest', str(path)], check=True)


class ApplyToCuts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(self.temp.name, worker=False)
        self.addCleanup(self.app.close)
        s = self.app.store
        streamer = s.create_streamer('CORINGA')
        profile = dict(DEFAULT_PROFILE, min_free_gb=.5, content_mode='video')
        s.save_profile(streamer, profile)
        sid = s.new_session(streamer, 'REACAO')
        self.file = Path(s.session(sid)['source']) / 'segmento_00000.ts'
        make_video(self.file)
        info = media.probe(self.file)
        with s.connect(True) as c:
            c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (sid, 0, str(self.file.resolve()), media.sha_file(self.file), info['duration'], info['signature'],
                       self.file.stat().st_size, self.file.stat().st_mtime_ns, 'done', '{}'))
        rows = build_timeline(s.segments(sid))
        group = rows[0]['group_id']
        self.ids = []
        for a, b in ((2, 12), (14, 24), (26, 36)):
            data = dict(start=a, end=b, group_id=group, score=5, reasons=['teste'], transcript='x')
            key, _ = s.propose(sid, data, plan(rows, a, b, group), dict(profile))
            self.ids.append(key)

    def project_of(self, key):
        return (self.app.store.candidate(key)['data'].get('project') or {}).get('composition')

    def test_source_frame_is_the_original_horizontal_frame(self):
        frame = self.app.source_frame(self.ids[0], 3)
        self.assertEqual(frame.suffix, '.jpg')
        out = subprocess.run([media.tool('ffprobe'), '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(frame)],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, '1280,720')

    def test_resolve_endpoint_returns_the_render_plan(self):
        result = self.app.action('/api/composition/resolve', dict(id=self.ids[0], composition=dict(layout='cam_ampliada', regions=REG)))
        self.assertEqual(result['source'], [1280, 720])
        self.assertTrue(result['plan']['ready'])
        direct = C.resolve(comp(), 1280, 720)
        self.assertEqual([(l['role'], list(l['crop']), list(l['size']), list(l['pos'])) for l in result['plan']['layers']],
                         [(l['role'], list(l['crop']), list(l['size']), list(l['pos'])) for l in direct['layers']])

    def test_apply_to_selected_cuts_and_whole_session(self):
        r = self.app.action('/api/composition/apply', dict(id=self.ids[0], composition=dict(layout='cam_ampliada', regions=REG), targets=[self.ids[1]]))
        self.assertEqual(r['applied'], [self.ids[1]])
        self.assertEqual(self.project_of(self.ids[1])['layout'], 'cam_ampliada')
        self.assertIsNone(self.project_of(self.ids[2]))             # os não marcados ficam intactos
        r = self.app.action('/api/composition/apply', dict(id=self.ids[0], composition=dict(layout='cinema', regions=REG), targets='session'))
        self.assertEqual(sorted(r['applied']), sorted(self.ids[1:]))
        self.assertEqual(self.project_of(self.ids[2])['layout'], 'cinema')

    def test_apply_skips_exported_cuts_and_reports_why(self):
        with self.app.store.connect(True) as c:
            c.execute("UPDATE candidates SET status='done' WHERE id=?", (self.ids[1],))
        r = self.app.action('/api/composition/apply', dict(id=self.ids[0], composition=dict(layout='cam_ampliada', regions=REG), targets=self.ids[1:]))
        self.assertEqual(r['applied'], [self.ids[2]])
        self.assertEqual(r['skipped'][0]['id'], self.ids[1])
        self.assertIn('exportado', r['skipped'][0]['reason'])
        self.assertIsNone(self.project_of(self.ids[1]))

    def test_apply_validates_input(self):
        for bad in (dict(composition=None, targets='session'), dict(composition=dict(layout='cam_ampliada'), targets=[]),
                    dict(composition=dict(layout='x'), targets='session')):
            with self.assertRaises(ValueError):
                self.app.action('/api/composition/apply', dict(id=self.ids[0], **bad))

    def test_missing_source_is_an_error_not_a_crash(self):
        self.file.unlink()
        with self.assertRaises((ValueError, OSError, RuntimeError)):
            self.app.action('/api/composition/resolve', dict(id=self.ids[0], composition=dict(layout='cam_ampliada', regions=REG)))


if __name__ == '__main__':
    unittest.main()
