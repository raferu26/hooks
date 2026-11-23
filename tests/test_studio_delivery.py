import json
import tempfile
import unittest
from pathlib import Path

from liveclips import export_pack, studio_api
from liveclips.store import Store
from tests.test_review import make_plan
from tests.test_second_pass import make_session


class StudioApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'd')
        self.streamer, _, self.cid = make_session(self.store)
        self.folder = Path(self.tmp.name) / 'saida'
        self.folder.mkdir()
        self.video = self.folder / 'clipe.mp4'
        self.video.write_bytes(b'video-falso')
        (self.folder / 'plano.json').write_text(json.dumps(make_plan([(0, 0, 4, 1.0, 0)])), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, level='ok', review=None):
        with self.store.connect(True) as c:
            c.execute("UPDATE candidates SET status='done',export_path=? WHERE id=?", (str(self.video), self.cid))
        self.store.set_qc(self.cid, dict(level=level, items=[], review=review or dict(veredito='revisao_humana', bloqueia_pronto=False, resumo='ok')))

    def test_plan_view_before_export_is_empty_not_invented(self):
        view = studio_api.plan_view(self.store, self.cid)
        self.assertIsNone(view['plano'])
        self.assertIsNone(view['revisao'])
        self.assertEqual('em_revisao', view['estado'])
        self.assertTrue(view['capacidades'])

    def test_full_delivery_flow(self):
        self.export()
        view = studio_api.plan_view(self.store, self.cid)
        self.assertEqual(1, view['plano']['resumo']['trechos'])
        self.assertEqual('pronto_para_revisao', view['estado'])
        record = studio_api.approve(self.store, self.cid)
        self.assertEqual(export_pack.sha256(self.video), record['video_sha'])
        self.assertEqual('aprovado', studio_api.plan_view(self.store, self.cid)['estado'])      # falta o pacote
        built = studio_api.build_package(self.store, self.cid)
        self.assertEqual('pronto_para_publicar', built['estado'])
        self.video.write_bytes(b'outro-conteudo')                                              # arquivo mudou depois da aprovação
        self.assertEqual('pronto_para_revisao', studio_api.plan_view(self.store, self.cid)['estado'])

    def test_approve_requires_export_and_no_critical_failure(self):
        with self.assertRaises(ValueError):
            studio_api.approve(self.store, self.cid)
        self.export(level='atencao', review=dict(veredito='bloqueado', bloqueia_pronto=True))
        with self.assertRaises(ValueError):
            studio_api.approve(self.store, self.cid)
        self.assertEqual('em_revisao', studio_api.plan_view(self.store, self.cid)['estado'])

    def test_conversation_proposes_without_saving(self):
        r = studio_api.talk(self.store, dict(id=self.cid, text='corta de 1 a 2'))
        self.assertEqual(1, len(r['aplicado']))
        self.assertEqual([dict(start=1.0, end=2.0)], r['projeto']['cuts'])
        self.assertIsNone(self.store.candidate(self.cid)['data'].get('project'))               # nada salvo sem o clique do usuário
        self.assertTrue(r['pode_desfazer'])
        r = studio_api.talk(self.store, dict(id=self.cid, action='undo'))
        self.assertEqual([], r['projeto']['cuts'])
        self.assertTrue(r['pode_refazer'])
        with self.assertRaises(ValueError):
            studio_api.talk(self.store, dict(id=self.cid, text=''))
        with self.assertRaises(ValueError):
            studio_api.talk(self.store, dict(id=self.cid, action='apagar tudo'))

    def test_memory_vocabulary_and_forget(self):
        out = studio_api.memory_action(self.store, '/api/memory/vocabulary', dict(streamer=self.streamer, term='Koringa'))
        self.assertIn('Koringa', out['vocabulario'])
        items = studio_api.memory_list(self.store, dict(namespace='vocabulario'))['itens']
        self.assertTrue(items)
        studio_api.memory_action(self.store, '/api/memory/forget', dict(id=items[0]['id']))
        self.assertNotIn('Koringa', self.store.memory.vocabulary(self.streamer))
        with self.assertRaises(ValueError):
            studio_api.memory_action(self.store, '/api/memory/forget', dict(id='nao-existe'))

    def test_references_roundtrip_and_validation(self):
        ref = dict(url='https://example.com/v', platform='tiktok', niche='fps', region='BR', observed_at=1.0, kind='hipotese',
                   structure='gancho e reação', inference_limits='amostra pequena', techniques=['zoom'])
        import time
        ref['observed_at'] = time.time() - 100
        studio_api.references_action(self.store, '/api/references/add', dict(reference=ref))
        out = studio_api.references_action(self.store, '/api/references/query', dict(niche='fps'))
        self.assertEqual(1, len(out['itens']))
        self.assertEqual(['punch_in'], out['sugestoes'][0]['aplicar'])
        with self.assertRaises(ValueError):
            studio_api.references_action(self.store, '/api/references/add', dict(reference=dict(ref, url='')))

    def test_telemetry_report_lists_modes(self):
        out = studio_api.telemetry_report(self.store)
        self.assertIn('equilibrado', out['modos'])


if __name__ == '__main__':
    unittest.main()


class ConversationFromScreenTests(unittest.TestCase):
    def test_conversation_starts_from_unsaved_screen_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'd')
            _, _, cid = make_session(store)
            screen = studio_api.projectlib.clean(dict(zooms=[dict(id='z1', start=2, end=4, zoom=1.2)]), 12)
            r = studio_api.talk(store, dict(id=cid, text='corta de 5 a 6', project=screen))
            self.assertEqual(1, len(r['projeto']['zooms']))            # o que estava na tela foi preservado
            self.assertEqual(1, len(r['projeto']['cuts']))
            r = studio_api.talk(store, dict(id=cid, text='sem zoom', project=r['projeto']))
            self.assertEqual([], r['projeto']['zooms'])
            self.assertEqual(1, len(r['projeto']['cuts']))
            with self.assertRaises(ValueError):
                studio_api.talk(store, dict(id=cid, text='corta de 1 a 2', project=dict(cuts=[dict(start=5, end=1)])))
