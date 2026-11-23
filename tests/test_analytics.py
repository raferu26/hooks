import json
import unittest

from liveclips import analytics
from tests import test_studio_api as _studio


class Parsing(unittest.TestCase):
    def test_numbers(self):
        n = analytics.number
        self.assertEqual(n('1,234'), 1234)
        self.assertEqual(n('1.234'), 1234)
        self.assertEqual(n('1.234.567'), 1234567)
        self.assertEqual(n('12,5'), 12.5)
        self.assertEqual(n('12.5K'), 12500)
        self.assertEqual(n('1,2 mil'), 1200)
        self.assertEqual(n('45%'), 45)
        for bad in ('', '-', 'abc'):
            with self.assertRaises(ValueError):
                n(bad)

    def test_english_export_with_report_title_line(self):
        text = ('Content report\nTime;Video title;Video link;Post time;Total likes;Total comments;Total shares;Total views\n'
                '2026-11-01;Jogada incrível no último minuto #fyp;https://tiktok.com/@a/video/1;2026-10-30;120;8;15;"3,400"\n'
                ';;;;;;;\n')
        rows, warnings = analytics.parse(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['views'], rows[0]['likes'], rows[0]['shares']), (3400, 120, 15))
        self.assertTrue(any('saves' in w for w in warnings))

    def test_portuguese_headers_and_comma_delimiter(self):
        text = 'Título do vídeo,Link do vídeo,Visualizações,Curtidas,Comentários,Compartilhamentos,Salvamentos,Taxa de conclusão\nTeste de título bom,,"1.500",100,5,3,7,12%\n'
        rows, _ = analytics.parse(text)
        self.assertEqual(rows[0]['views'], 1500)
        self.assertEqual(rows[0]['saves'], 7)
        self.assertEqual(rows[0]['watch_pct'], 12.0)

    def test_unknown_layout_gets_a_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            analytics.parse('Date,Video views,Profile views\n2026-11-01,100,20\n')
        self.assertIn('Conteúdo', str(ctx.exception))
        with self.assertRaises(ValueError):
            analytics.parse('')


class Api(unittest.TestCase):
    setUp = _studio.StudioApiTests.setUp
    close = _studio.StudioApiTests.close
    post = _studio.StudioApiTests.post

    def make_done(self, words, start=10.5):
        ws = [dict(start=start + i * .4, end=start + .35 + i * .4, word=w) for i, w in enumerate(words.split())]
        data = self.item['data']
        data['transcript_segments'] = [dict(start=ws[0]['start'], end=ws[-1]['end'], text=words, words=ws)]
        with self.app.store.connect(True) as c:
            c.execute("UPDATE candidates SET data=?,status='done',export_path='x.mp4' WHERE id=?", (json.dumps(data), self.item['id']))

    def test_preview_matches_by_title_and_apply_records_performance(self):
        self.make_done('Gente olha isso aqui agora porque ninguem acredita nisso')
        csv = 'Video title,Video link,Total views,Total likes,Total comments,Total shares,Total saves\nOlha isso aqui agora ninguem acredita,https://t/1,2500,200,10,20,30\nOutro video qualquer sobre culinaria,https://t/2,900,10,1,1,0\n'
        code, got = self.post('/api/analytics/preview', dict(streamer=self.streamer, text=csv))
        self.assertEqual(code, 200)
        self.assertEqual(got['items'][0]['match']['id'], self.item['id'])
        self.assertIsNone(got['items'][1]['match'])
        self.assertEqual(self.app.store.candidate(self.item['id'])['data'].get('performance'), None)  # prévia não grava
        code, res = self.post('/api/analytics/apply', dict(pairs=[dict(id=self.item['id'], row=got['items'][0]['row'])]))
        self.assertEqual((code, res['saved'], res['errors']), (200, 1, []))
        perf = self.app.store.candidate(self.item['id'])['data']['performance']
        self.assertEqual((perf['views'], perf['likes'], perf['saves']), (2500, 200, 30))
        # linha inválida não derruba as outras
        bad = dict(views=0)
        code, res = self.post('/api/analytics/apply', dict(pairs=[dict(id=self.item['id'], row=bad), dict(id=self.item['id'], row=got['items'][0]['row'])]))
        self.assertEqual(res['saved'], 1)
        self.assertEqual(len(res['errors']), 1)

    def test_ambiguous_titles_are_not_auto_matched(self):
        self.make_done('gente olha isso aqui agora porque ninguem acredita')
        rows = [dict(title='olha', url='', views=10, likes=0, comments=0, shares=0, saves=0)]
        cand = self.app.store.decode(dict(self.app.store.rows('SELECT * FROM candidates WHERE id=?', (self.item['id'],))[0]))
        self.assertIsNone(analytics.match(rows, [cand])[0]['match'])  # título curto demais para ligar com segurança


if __name__ == '__main__':
    unittest.main()
