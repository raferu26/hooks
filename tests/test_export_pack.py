import json
import tempfile
import unittest
from pathlib import Path

from liveclips import export_pack as pack, plan as planlib
from tests.test_review import make_plan


class StateTests(unittest.TestCase):
    ok = dict(level='ok', review=dict(veredito='revisao_humana', bloqueia_pronto=False))

    def test_no_report_is_in_review(self):
        self.assertEqual('em_revisao', pack.delivery_state(None))

    def test_blocking_review_keeps_in_review_even_if_approved(self):
        blocked = dict(level='atencao', review=dict(veredito='bloqueado', bloqueia_pronto=True))
        self.assertEqual('em_revisao', pack.delivery_state(blocked, approval=dict(video_sha='x'), package_ok=True, video_sha='x'))

    def test_clean_without_approval_is_ready_for_review(self):
        self.assertEqual('pronto_para_revisao', pack.delivery_state(self.ok, video_sha='x'))

    def test_approval_of_other_version_does_not_count(self):
        self.assertEqual('pronto_para_revisao', pack.delivery_state(self.ok, approval=dict(video_sha='old'), video_sha='new'))

    def test_approved_needs_package_to_be_publishable(self):
        self.assertEqual('aprovado', pack.delivery_state(self.ok, approval=dict(video_sha='x'), video_sha='x', package_ok=False))
        self.assertEqual('pronto_para_publicar', pack.delivery_state(self.ok, approval=dict(video_sha='x'), video_sha='x', package_ok=True))

    def test_unavailable_review_is_not_ready(self):
        self.assertEqual('em_revisao', pack.delivery_state(dict(level='ok', review=dict(veredito='indisponivel')), video_sha='x'))


class PackageTests(unittest.TestCase):
    def make(self, tmp):
        folder = Path(tmp)
        (folder / 'saida.mp4').write_bytes(b'video-bytes')
        plan = make_plan([(0, 0, 4, 1.0, 0), (0, 4, 6, 0.5, 0), (0, 6, 6.05, 1.0, 1.0)])
        (folder / 'plano.json').write_text(json.dumps(plan), encoding='utf-8')
        return folder, plan

    def test_build_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, plan = self.make(tmp)
            data = pack.build(folder, folder / 'saida.mp4')
            self.assertIn('linha_do_tempo.otio', data['arquivos'])
            self.assertEqual(pack.sha256(folder / 'saida.mp4'), data['video_sha256'])
            ok, problems = pack.verify(folder)
            self.assertTrue(ok, problems)

    def test_verify_detects_change_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, _ = self.make(tmp)
            pack.build(folder, folder / 'saida.mp4')
            (folder / 'saida.mp4').write_bytes(b'outro')
            (folder / 'plano.json').unlink()
            ok, problems = pack.verify(folder)
            self.assertFalse(ok)
            self.assertEqual(2, len(problems))

    def test_verify_without_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(pack.verify(tmp)[0])


class OtioTests(unittest.TestCase):
    def test_structure_and_effects(self):
        plan = make_plan([(0, 0, 4, 1.0, 0), (0, 4, 6, 0.5, 0), (0, 6, 6.05, 1.0, 1.0)])
        data = pack.otio(plan)
        video = data['tracks']['children'][0]['children']
        self.assertEqual(3, len(video))
        self.assertEqual('LinearTimeWarp', video[1]['effects'][0]['effect_name'])
        self.assertEqual(.5, video[1]['effects'][0]['time_scalar'])
        self.assertEqual('FreezeFrame', video[2]['effects'][0]['effect_name'])
        self.assertEqual(planlib.digest(plan), data['metadata']['liveclips']['plan_digest'])

    def test_library_can_read_it(self):
        try:
            import opentimelineio as otio_lib
        except ImportError:
            self.skipTest('opentimelineio não instalado')
        plan = make_plan([(0, 0, 4, 1.0, 0), (0, 4, 6, 0.5, 0)])
        timeline = otio_lib.adapters.read_from_string(json.dumps(pack.otio(plan)), 'otio_json')
        clips = list(timeline.find_clips())
        self.assertEqual(4, len(clips))               # vídeo + áudio
        self.assertAlmostEqual(4.0, clips[0].source_range.duration.to_seconds(), places=3)
        self.assertAlmostEqual(4.0, clips[1].source_range.duration.to_seconds(), places=3)   # 2 s de fonte a 0,5x ocupam 4 s na saída


class InterchangeTests(unittest.TestCase):
    """P26: marcadores, limites declarados e conferência com a biblioteca oficial."""
    project = dict(zooms=[dict(id='z1', start=1.0, end=2.0, zoom=1.2)], titles=[dict(id='t1', start=0.0, end=2.0, style='x', position='top')])

    def plan(self):
        return make_plan([(0, 0, 4, 1.0, 0), (0, 4, 6, 0.5, 0), (0, 6, 6.05, 1.0, 1.0)], project=self.project)

    def test_effects_become_markers_on_video_track(self):
        data = pack.otio(self.plan())
        markers = data['tracks']['children'][0]['markers']
        self.assertEqual(sorted(m['name'] for m in markers), ['punch_in: z1', 'titulo_contexto: t1'])
        self.assertEqual(data['tracks']['children'][1]['markers'], [])

    def test_library_reads_cuts_markers_and_duration(self):
        try:
            import opentimelineio as lib
        except ImportError:
            self.skipTest('opentimelineio não instalado')
        plan = self.plan()
        timeline = lib.adapters.read_from_string(json.dumps(pack.otio(plan)), 'otio_json')
        video = timeline.video_tracks()[0]
        self.assertEqual(3, len(list(video.find_clips())))
        self.assertEqual(2, len(video.markers))
        fps = plan['output']['fps']['num'] / plan['output']['fps']['den']
        self.assertAlmostEqual(video.duration().to_frames(), plan['output']['duration_frames'], delta=1)
        self.assertAlmostEqual(video.duration().rate, fps, places=3)

    def test_build_writes_limits_and_records_library_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'saida.mp4').write_bytes(b'x')
            plan = self.plan()
            (folder / 'plano.json').write_text(json.dumps(plan), encoding='utf-8')
            (folder / 'manifesto.json').write_text(json.dumps(dict(profile=dict(voice_preset='natural', auto_color='histograma', lut='', cut_fade='off'))), encoding='utf-8')
            data = pack.build(folder, folder / 'saida.mp4')
            text = (folder / 'linha_do_tempo_limites.txt').read_text(encoding='utf-8')
            self.assertIn('NÃO LEVA', text)
            self.assertIn('zoom', text)
            self.assertIn('voice_preset', text)
            self.assertIn('Premiere', text)                      # não promete compatibilidade total
            self.assertTrue(any('Transições' in r for r in data['nao_transportado']))
            self.assertIn('linha_do_tempo_limites.txt', data['arquivos'])
            try:
                import opentimelineio  # noqa: F401
                self.assertTrue(data['otio_biblioteca']['ok'])
            except ImportError:
                self.assertIsNone(data['otio_biblioteca'])
            self.assertTrue(pack.verify(folder)[0])


class PortableProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.sources = base / 'fontes_originais'
        self.sources.mkdir()
        self.source = self.sources / 'gravação ção.ts'
        self.source.write_bytes(b'conteudo-da-fonte' * 1000)
        self.folder = base / 'corte'
        self.folder.mkdir()
        (self.folder / 'clipe.mp4').write_bytes(b'video')
        (self.folder / 'plano.json').write_text(json.dumps(make_plan([(0, 0, 4, 1.0, 0)])), encoding='utf-8')
        self.candidate = dict(id='c1', start=0, end=4, parts=[dict(path=str(self.source), sha=pack.sha256(self.source), **{'in': 0, 'out': 4})],
                              profile=dict(delivery_folder='C:/privado', ai_mode='sem_ia', voice_preset='natural'),
                              data=dict(project=dict(titles=[])))

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_reports_size_and_writes_nothing(self):
        report = pack.portable_project(self.folder, self.candidate, include_sources=True, dry_run=True)
        self.assertFalse(report['gravado'])
        self.assertEqual(report['bytes_referencias_somente'], self.source.stat().st_size)
        self.assertEqual(report['fontes'][0]['nome'], self.source.name)
        self.assertFalse((self.folder / pack.PROJECT_DIR).exists())

    def test_references_only_has_plan_profile_hashes_and_no_private_keys(self):
        report = pack.portable_project(self.folder, self.candidate)
        self.assertTrue(report['gravado'])
        self.assertEqual(report['bytes_fontes'], 0)
        data = json.loads((self.folder / pack.PROJECT_DIR / 'projeto.json').read_text(encoding='utf-8'))
        self.assertEqual(data['plan_digest'], planlib.digest(data['plan']))
        self.assertNotIn('delivery_folder', data['profile'])
        self.assertEqual(data['profile']['voice_preset'], 'natural')
        self.assertEqual(data['midias'][0]['sha256'], pack.sha256(self.source))
        self.assertFalse((self.folder / pack.PROJECT_DIR / 'fontes').exists())
        self.assertIn('clipe.mp4', data['exportados'])

    def test_reopen_ok_then_detects_changed_and_missing_and_relinks(self):
        pack.portable_project(self.folder, self.candidate)
        ok = pack.reopen(self.folder)
        self.assertTrue(ok['ok'], ok)
        self.assertEqual(ok['segmentos'], 1)
        self.source.write_bytes(b'outra coisa')
        self.assertEqual(pack.reopen(self.folder)['midias'][0]['estado'], 'alterada')
        moved = Path(self.temp.name) / 'novo_lugar'
        moved.mkdir()
        original = b'conteudo-da-fonte' * 1000
        (moved / self.source.name).write_bytes(original)
        self.source.unlink()
        again = pack.reopen(self.folder, search=[moved])
        self.assertTrue(again['ok'], again)                       # reencontrada em outra pasta, com o mesmo hash
        self.assertEqual(pack.reopen(self.folder)['midias'][0]['estado'], 'ausente')

    def test_include_sources_copies_and_survives_missing_original(self):
        report = pack.portable_project(self.folder, self.candidate, include_sources=True)
        self.assertEqual(report['bytes_fontes'], self.source.stat().st_size)
        before = pack.sha256(self.source)
        self.source.unlink()
        again = pack.reopen(self.folder)
        self.assertTrue(again['ok'], again)
        self.assertEqual(pack.sha256(self.folder / pack.PROJECT_DIR / 'fontes' / self.source.name), before)

    def test_tampered_plan_is_reported_and_missing_plan_refused(self):
        pack.portable_project(self.folder, self.candidate)
        file = self.folder / pack.PROJECT_DIR / 'projeto.json'
        data = json.loads(file.read_text(encoding='utf-8'))
        data['plan']['segments'][0]['source_out'] += 9000
        file.write_text(json.dumps(data), encoding='utf-8')
        self.assertFalse(pack.reopen(self.folder)['plano_integro'])
        (self.folder / 'plano.json').unlink()
        with self.assertRaises(ValueError):
            pack.portable_project(self.folder, self.candidate)
        with self.assertRaises(ValueError):
            pack.reopen(self.temp.name)


if __name__ == '__main__':
    unittest.main()
