"""Exemplo completo do documento (P00-P27), no caminho real de geração, em modo sem IA.

Vídeo local + perfil do criador + dois marcadores + legenda pronta com horário -> pausa reduzida com mapa de tempo, layout com
webcam, replay do momento marcado, voz, música com ducking, legendas remapeadas, título e capa de modelo, variante extra,
verificação de qualidade e registro de operações e recusas. Depois, falhas forçadas: a entrega vira uma versão mais simples
e válida, com o motivo registrado."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from liveclips import editing, media
from liveclips.engine import Engine
from liveclips.store import DEFAULT_PROFILE, Store

from tests.test_noai_mode import Blocker

SRT = ('1\n00:00:46,000 --> 00:00:50,000\nPrimeira fala importada\n\n2\n00:00:51,000 --> 00:00:54,000\nSegunda fala importada\n\n'
       '3\n00:01:00,000 --> 00:01:03,000\nTerceira fala depois da pausa\n\n4\n00:01:25,000 --> 00:01:28,000\nFala do segundo marcador\n')
# áudio: mudo no começo e no fim (dá contraste à medida de silêncio), pausa de 5 s entre 54 e 59 s, trecho forte entre 40 e 48 s
AUDIO = "sine=frequency=300:duration=100:sample_rate=48000,volume='if(lt(t,12),0,if(gt(t,94),0,if(between(t,54,59),0,if(gt(t,40),if(lt(t,48),1.0,0.4),0.4))))':eval=frame"


def build(root, **profile):
    """Monta sessão com a fonte, os dois marcadores e a legenda; devolve (store, engine, id do corte dos marcadores)."""
    root = Path(root)
    store = Store(str(root / 'dados'))
    streamer = store.create_streamer('Exemplo')
    music = root / 'trilha.wav'
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=60:sample_rate=48000', '-ac', '2', str(music)], timeout=60)
    entrega = root / 'entrega'
    entrega.mkdir()
    base = dict(DEFAULT_PROFILE, ai_mode='sem_ia', editorial_style='gameplay', camera_rect=[0, .3, .25, .3], min_free_gb=.5, second_pass='off',
                voice_preset='natural', title_template='{rotulo}', auto_silence=True, auto_replay='lento', auto_music=True, music_authorized=True,
                music_path=str(music), music_volume=.1, delivery_folder=str(entrega), cover=True, cover_template='destaque')
    store.save_profile(streamer, dict(base, **profile))
    sid = store.new_session(streamer, 'exemplo')
    session = store.session(sid)
    file = Path(session['source']) / 'segmento_00000.ts'
    media.run([media.tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30:duration=100', '-f', 'lavfi', '-i', AUDIO,
               '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '30', '-c:a', 'aac', '-b:a', '96k', '-f', 'mpegts', str(file)], timeout=240)
    info = media.probe(file)
    stat = file.stat()
    with store.connect(True) as c:
        c.execute('INSERT INTO segments(session,seq,path,sha,duration,signature,size,mtime,status,data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (sid, 0, str(file.resolve()), media.sha_file(file), info['duration'], info['signature'], stat.st_size, stat.st_mtime_ns, 'new', '{}'))
    Path(session['path'], 'marcadores.json').write_text(json.dumps(
        [dict(time=50, label='Pedido do chat', pre=8, post=14), dict(time=85, label='Final da jogada', pre=6, post=8)]), encoding='utf-8')
    Path(session['path'], 'legendas').mkdir(exist_ok=True)
    Path(session['path'], 'legendas', 'fala.srt').write_text(SRT, encoding='utf-8')
    engine = Engine(store)
    current = store.streamer(streamer)['profile']
    engine.analyze_one(store.session(sid), current)
    engine.suggest_one(store.session(sid), current)
    for row in store.rows('SELECT id FROM candidates WHERE streamer=?', (streamer,)):
        if store.candidate(row['id'])['data'].get('origin') == 'marcador':
            return store, engine, row['id']
    raise AssertionError('nenhum corte de marcador')


def approve(store, item_id):
    item = store.candidate(item_id)
    store.review(item_id, item['version'], item['start'], item['end'], item['parts'] if isinstance(item['parts'], list) else json.loads(item['parts']),
                 'approve', editorial_confirmed=True)


def folder_of(done):
    path = Path(done['export_path'])
    return path if path.is_dir() else path.parent


class Pure(unittest.TestCase):
    def candidate(self, **extra):
        return dict(start=42.0, end=93.0, markers=[dict(time=50.0, label='x')], clip_format='short', **extra)

    def test_replay_off_by_default_and_needs_a_marker(self):
        self.assertEqual(editing._auto_replay(self.candidate(), {}, [], 42.0, 93.0), [])
        refused = editing._auto_replay(dict(start=42.0, end=93.0, markers=[]), dict(auto_replay='lento'), [], 42.0, 93.0)
        self.assertFalse(refused[0]['enabled'])
        self.assertIn('momento marcado', refused[0]['reason'])

    def test_replay_fits_and_is_slow_and_muted(self):
        got = editing._auto_replay(self.candidate(), dict(auto_replay='lento'), [], 42.0, 80.0)[0]
        self.assertTrue(got['enabled'])
        self.assertEqual((got['start'], got['end'], got['rate'], got['mute']), (6.5, 10.5, .5, True))
        normal = editing._auto_replay(self.candidate(), dict(auto_replay='normal'), [], 42.0, 80.0)[0]
        self.assertEqual((normal['rate'], normal['mute']), (1.0, False))

    def test_replay_refused_when_over_limit_or_crossing_a_cut_or_project_has_one(self):
        over = editing._auto_replay(self.candidate(), dict(auto_replay='lento'), [], 42.0, 93.0)[0]      # 51 s + 8 s > 58 s
        self.assertFalse(over['enabled'])
        self.assertIn('passaria', over['reason'])
        cut = [dict(kind='silence', enabled=True, start=7.0, end=9.0, id='s')]
        crossing = editing._auto_replay(self.candidate(), dict(auto_replay='lento'), cut, 42.0, 80.0)[0]
        self.assertFalse(crossing['enabled'])
        self.assertIn('pausa', crossing['reason'])
        mine = editing._auto_replay(self.candidate(project=dict(replays=[1])), dict(auto_replay='lento'), [], 42.0, 80.0)[0]
        self.assertFalse(mine['enabled'])

    def test_replay_budget_counts_the_pause_that_is_cut(self):
        cut = [dict(kind='silence', enabled=True, start=20.0, end=25.0, id='s')]
        self.assertTrue(editing._auto_replay(self.candidate(), dict(auto_replay='lento'), cut, 42.0, 93.0)[0]['enabled'])

    def test_measured_silence_minus_speech_from_subtitles(self):
        out = editing._without_speech([dict(start=54.0, end=59.0, method='m')], [(51.0, 54.0), (60.0, 63.0)])
        self.assertEqual([(round(x['start'], 2), round(x['end'], 2)) for x in out], [(54.2, 59.0)])
        self.assertEqual(editing._without_speech([dict(start=54.0, end=57.0)], [(50.0, 60.0)]), [])

    def test_segment_without_words_is_split_around_a_replay(self):
        remap = editing.Remap(30.0, [], replays=[dict(id='r', start=4.0, end=8.0, rate=.5, after=8.0)])
        rows = editing.retime_transcript([dict(start=106.0, end=110.0, text='fala', words=[])], 100.0, 130.0, remap)
        original = [r for r in rows if not r.get('replay')]
        self.assertEqual(len(original), 2)                                   # até o replay e depois dele
        self.assertAlmostEqual(original[0]['end'], 8.0, places=2)
        self.assertGreater(original[1]['start'], 8.0 + 8.0 - .1)             # retoma só depois dos 8 s do replay
        self.assertEqual(len([r for r in rows if r.get('replay')]), 1)


class Ladder(unittest.TestCase):
    def test_missing_automatic_music_falls_to_step_two_and_is_recorded(self):
        calls = []
        def fake(candidate, *a):
            calls.append(candidate.get('data', {}).get('edit_overrides'))
            if not calls[-1]:
                raise ValueError('Um recurso de edição não foi encontrado: x.wav')
            return 'ok'
        candidate = dict(profile=dict(voice_preset='off'), start=0, end=10,
                         data=dict(edit_plan=dict(decisions=[dict(id='music:0:10', kind='music', enabled=True, start=0, end=10)])))
        meta = {}
        with mock.patch.object(media, '_render_single', fake):
            self.assertEqual(media._single_ladder(candidate, [], None, Path(tempfile.mkdtemp()), None, [], {}, meta), 'ok')
        self.assertEqual(meta['recuo']['modulos'], ['música automática'])
        self.assertEqual(calls[-1], {'music:0:10': False})

    def test_other_value_errors_are_not_swallowed(self):
        with mock.patch.object(media, '_render_single', side_effect=ValueError('As decisões removeriam todo o corte.')):
            with self.assertRaises(ValueError):
                media._single_ladder(dict(profile=dict(voice_preset='natural')), [], None, Path(tempfile.mkdtemp()), None, [], {}, {})

    def test_voice_failure_keeps_automatic_music(self):
        seen = []
        def fake(candidate, *a):
            seen.append((candidate['profile']['voice_preset'], bool(candidate.get('data', {}).get('edit_overrides'))))
            if candidate['profile']['voice_preset'] != 'off':
                raise RuntimeError('filtro de voz')
            return 'ok'
        candidate = dict(profile=dict(voice_preset='natural'), start=0, end=10,
                         data=dict(edit_plan=dict(decisions=[dict(id='music:0:10', kind='music', enabled=True, start=0, end=10)])))
        meta = {}
        with mock.patch.object(media, '_render_single', fake):
            media._single_ladder(candidate, [], None, Path(tempfile.mkdtemp()), None, [], {}, meta)
        self.assertEqual(seen, [('natural', False), ('off', False)])        # a música só sai se o degrau 1 não bastar
        self.assertEqual(meta['recuo']['modulos'], ['tratamento de voz'])


class CompleteExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.blocker = Blocker()
        sys.meta_path.insert(0, cls.blocker)
        cls.store, cls.engine, cls.item = build(cls.temp.name, export_formats=['1x1'], export_srt=True, motion_level='leve')
        cls.planned = cls.store.candidate(cls.item)
        approve(cls.store, cls.item)
        cls.engine.do_render(cls.item, False)
        cls.done = cls.store.candidate(cls.item)

    @classmethod
    def tearDownClass(cls):
        sys.meta_path.remove(cls.blocker)
        cls.temp.cleanup()

    def decisions(self):
        return {d['kind']: d for d in self.planned['data']['edit_plan']['decisions']}

    def test_no_model_was_loaded(self):
        self.assertEqual(self.blocker.attempts, [])

    def test_both_markers_became_one_cut_with_origin_and_imported_captions(self):
        data = self.planned['data']
        self.assertEqual(data['origin'], 'marcador')
        self.assertEqual([m['label'] for m in data['markers']], ['Pedido do chat', 'Final da jogada'])
        self.assertEqual(data['transcript_segments_origin'], 'importada')
        self.assertFalse(data.get('heuristic'))

    def test_plan_has_pause_reduction_replay_music_and_a_refusals_log(self):
        d = self.decisions()
        self.assertTrue(d['silence']['enabled'])
        self.assertEqual(d['silence']['origin'], 'medida_de_audio')
        self.assertTrue(d['replay']['enabled'])
        self.assertEqual((d['replay']['rate'], d['replay']['mute']), (.5, True))
        self.assertTrue(d['music']['enabled'])
        director = self.planned['data']['edit_plan']['director']
        self.assertIn('refused', director)
        self.assertGreaterEqual(director['accepted'].get('replay', 0), 1)
        # a pausa cortada não toca os trechos protegidos em volta dos marcadores
        start = self.planned['start']
        for lo, hi in self.planned['data']['protected']:
            self.assertFalse(d['silence']['start'] + start < hi and d['silence']['end'] + start > lo, (lo, hi))

    def test_render_done_with_expected_duration_and_time_map(self):
        self.assertEqual(self.done['status'], 'done', self.done.get('error'))
        d = self.decisions()
        total = self.planned['end'] - self.planned['start']
        expected = total - (d['silence']['end'] - d['silence']['start']) + (d['replay']['end'] - d['replay']['start']) / d['replay']['rate']
        info = media.probe(folder_of(self.done) / 'clipe.mp4')
        self.assertAlmostEqual(info['duration'], expected, delta=.5)
        self.assertEqual((info['width'], info['height']), (1080, 1920))
        self.assertTrue(info['has_audio'])
        plan = json.loads((folder_of(self.done) / 'plano.json').read_text(encoding='utf-8'))
        kinds = [s['kind'] for s in plan['segments']]
        self.assertEqual(kinds.count('replay'), 1)
        replay = next(s for s in plan['segments'] if s['kind'] == 'replay')
        self.assertTrue(replay['mute'])
        self.assertEqual(replay['speed'], '1/2')
        self.assertAlmostEqual(plan['output']['duration_ticks'] / plan['output']['tps'], info['duration'], delta=.5)

    def test_captions_follow_the_time_map_and_do_not_show_another_instant(self):
        import re
        text = (folder_of(self.done) / 'legendas.ass').read_text(encoding='utf-8-sig')
        def seconds(value):
            h, m, s = value.split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
        rows = [(seconds(a), seconds(b), t.replace('\\N', ' ').upper()) for a, b, t in
                re.findall(r'Dialogue: 0,([\d:.]+),([\d:.]+),Principal,,0,0,0,,(.*)', text)]
        d = self.decisions()
        cut = d['silence']['end'] - d['silence']['start']
        added = (d['replay']['end'] - d['replay']['start']) / d['replay']['rate']
        third = next(r for r in rows if 'TERCEIRA' in r[2])
        self.assertAlmostEqual(third[0], (60 - 42) - cut + added, delta=.4)         # 18 s do clipe, menos a pausa, mais o replay
        replay_start = d['replay']['after'] + 0.0
        during = [r for r in rows if replay_start - .05 <= r[0] < replay_start + added - .05]
        # durante o replay (6,5 s a 10,5 s do clipe), só aparece texto que existe nesse trecho: a ponta da 1ª fala e a 2ª fala
        self.assertEqual([r[2].split()[0] for r in during], ['PRIMEIRA', 'SEGUNDA'])
        for r in rows:
            self.assertFalse(replay_start + .1 < r[0] and r[1] > replay_start + added + .1 and r[0] < replay_start + added - .1, r)

    def test_cover_title_variant_srt_and_quality_check(self):
        folder = folder_of(self.done)
        self.assertTrue((folder / 'capa_9x16.jpg').is_file())
        manifest = json.loads((folder / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['variants'], {'1x1': 'ok'})
        self.assertNotIn('recuo', manifest)
        self.assertTrue((folder / 'clipe_1x1.mp4').is_file() and (folder / 'legendas_1x1.srt').is_file())
        self.assertIn('PEDIDO DO CHAT', (folder / 'legendas.ass').read_text(encoding='utf-8-sig').upper())
        report = self.done['data']['qc']
        self.assertNotEqual(report['level'], 'erro', report['summary'])
        self.assertEqual(self.blocker.attempts, [])

    def test_automatic_cut_is_not_published_by_itself(self):
        self.assertNotIn(self.done['status'], ('published', 'publicado'))
        manifest = json.loads((folder_of(self.done) / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest['editorial']['requires_review'])


class Fallbacks(unittest.TestCase):
    def run_failure(self, mutate=None, **profile):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store, engine, item = build(temp.name, **profile)
        if mutate:
            mutate(Path(temp.name))
        approve(store, item)
        return store, engine, item

    def test_effect_failure_delivers_the_simpler_version_and_says_so(self):
        original = media._with_color
        def broken(look, profile, *a, **k):
            if profile.get('auto_color', 'off') != 'off':
                raise RuntimeError('filtro de cor quebrado')
            return original(look, profile, *a, **k)
        store, engine, item = self.run_failure(auto_color='histograma')
        with mock.patch.object(media, '_with_color', broken):
            engine.do_render(item, False)
        done = store.candidate(item)
        self.assertEqual(done['status'], 'done', done.get('error'))
        manifest = json.loads((folder_of(done) / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertIn('cor automática', manifest['recuo']['modulos'])
        self.assertIn('filtro de cor quebrado', manifest['recuo']['motivo'])
        info = media.probe(folder_of(done) / 'clipe.mp4')
        self.assertEqual((info['width'], info['height'], info['has_audio']), (1080, 1920, True))
        self.assertIn('recuo', [i['id'] for i in done['data']['qc']['items']])
        plan = json.loads((folder_of(done) / 'plano.json').read_text(encoding='utf-8'))
        self.assertEqual([s['kind'] for s in plan['segments']].count('replay'), 1)       # a edição principal continua

    def test_missing_music_file_delivers_without_music_and_says_so(self):
        store, engine, item = self.run_failure(mutate=lambda root: (root / 'trilha.wav').unlink())
        engine.do_render(item, False)
        done = store.candidate(item)
        self.assertEqual(done['status'], 'done', done.get('error'))
        manifest = json.loads((folder_of(done) / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['recuo']['modulos'], ['música automática'])
        self.assertTrue(media.probe(folder_of(done) / 'clipe.mp4')['has_audio'])


if __name__ == '__main__':
    unittest.main()
