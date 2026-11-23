"""0.19 · E1: salvar não apaga a prévia, salvamento automático não ensina a memória, mapa de tempo da prévia."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liveclips.app import App,preview_info
from liveclips.editing import timing_for
from tests.helpers import setup_session,candidate


class SalvarPreviaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False);self.addCleanup(self.app.close)
        _streamer,self.sid,_profile=setup_session(self.app.store)
        self.item,_=candidate(self.app.store,self.sid,50,78)
        self.file=Path(self.app.store.session(self.sid)['path'])/'previa_antiga.mp4';self.file.write_bytes(b'video')
        with self.app.store.connect(True) as c:
            c.execute("UPDATE candidates SET preview_status='ready',preview_version=version,preview_path=? WHERE id=?",
                      (str(self.file),self.item['id']))

    def current(self):return self.app.store.candidate(self.item['id'])

    def save(self,project,**kw):
        row=self.current()
        return self.app.project_save(dict(id=row['id'],version=row['version'],project=project,**kw))

    def test_salvar_sem_previa_mantem_a_anterior_como_desatualizada(self):
        self.save(dict(titles=[dict(text='Oi',start=0,end=2)]),preview=False)
        row=self.current()
        self.assertEqual(row['preview_path'],str(self.file))
        self.assertNotEqual(row['preview_version'],row['version'])
        info=preview_info(row,row['data'])
        self.assertFalse(info['ready']);self.assertTrue(info['stale']);self.assertTrue(info['available'])
        # a mídia antiga continua servida enquanto a nova não existe
        self.assertEqual(self.app.media_file('preview',row['id']),self.file.resolve())
        self.assertTrue(self.app.project_get(row['id'])['preview']['stale'])

    def test_pedir_previa_enfileira_sem_apagar_o_arquivo(self):
        self.save(dict(zooms=[]),preview=True)
        row=self.current()
        self.assertEqual(row['preview_status'],'queued');self.assertEqual(row['preview_path'],str(self.file))
        self.assertEqual(self.app.media_file('preview',row['id']),self.file.resolve())

    def test_prévia_apagada_do_disco_nao_e_oferecida(self):
        self.save(dict(zooms=[]),preview=False);self.file.unlink()
        row=self.current();info=preview_info(row,row['data'])
        self.assertFalse(info['stale']);self.assertFalse(info['available'])

    def test_autosave_nao_ensina_e_o_salvamento_explicito_aprende_a_diferenca_inteira(self):
        calls=[]
        with patch.object(self.app.store,'_learn_from_save',side_effect=lambda cid,old,new:calls.append((old,new))):
            self.save(dict(titles=[dict(text='Um',start=0,end=2)]),preview=False,learn=False)
            self.save(dict(titles=[dict(text='Dois',start=0,end=2)]),preview=False,learn=False)
            self.assertEqual(calls,[])
            self.assertIn('learn_base',self.current()['data'])
            self.save(dict(titles=[dict(text='Três',start=0,end=2)]),preview=False)
        self.assertEqual(len(calls),1)
        old,new=calls[0]
        self.assertIsNone(old)  # o ponto de partida é o projeto antes do primeiro salvamento automático
        self.assertEqual(new['titles'][0]['text'],'Três')
        self.assertNotIn('learn_base',self.current()['data'])

    def test_salvamento_explicito_sem_autosave_continua_aprendendo(self):
        calls=[]
        with patch.object(self.app.store,'_learn_from_save',side_effect=lambda cid,old,new:calls.append((old,new))):
            self.save(dict(titles=[dict(text='A',start=0,end=2)]),preview=False)
            self.save(dict(titles=[dict(text='B',start=0,end=2)]),preview=False)
        self.assertEqual([c[1]['titles'][0]['text'] for c in calls],['A','B'])
        self.assertEqual(calls[1][0]['titles'][0]['text'],'A')

    def test_mapa_de_tempo_unico_para_editor_e_previa(self):
        self.save(dict(cuts=[dict(start=2,end=4)],speeds=[dict(start=10,end=12,rate=2)]),preview=False)
        row=self.current()
        timing=timing_for(row)
        self.assertEqual(self.app.project_get(row['id'])['timing'],timing)
        self.assertTrue(any(c['kind']=='manual' and c['start']==2 for c in timing['cuts']))
        self.assertEqual(timing['speeds'][0]['rate'],2)

    def test_mudar_limites_preserva_a_previa_anterior(self):
        row=self.current()
        self.app.project_save(dict(id=row['id'],version=row['version'],start=52,end=76))
        row=self.current()
        self.assertEqual(row['preview_path'],str(self.file))
        self.assertEqual(row['preview_status'],'queued')

    def test_salvar_o_mesmo_projeto_mantem_a_previa_atual(self):
        self.save(dict(titles=[dict(text='Oi',start=0,end=2)]),preview=False)
        with self.app.store.connect(True) as c:c.execute('UPDATE candidates SET preview_version=version WHERE id=?',(self.item['id'],))
        same=self.current()['data']['project']
        self.save(same,preview=False)
        row=self.current()
        self.assertEqual(row['preview_version'],row['version'])
        self.assertTrue(preview_info(row,row['data'])['ready'])

    def test_exportar_com_modo_escolhido_e_modo_invalido(self):
        with self.assertRaisesRegex(ValueError,'Modo de qualidade'):
            row=self.current()
            self.app.review(dict(id=row['id'],version=row['version'],start=row['start'],end=row['end'],action='approve',quality_mode='ultra'))
        catalog=self.app.project_get(self.item['id'])['catalog']['quality_modes']
        self.assertEqual([m['id'] for m in catalog],['rapido','equilibrado','qualidade','entrega'])


if __name__=='__main__':unittest.main()
