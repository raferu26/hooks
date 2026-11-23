"""Estúdio V9: projeto editável, legendas inteligentes, agentes, música, efeitos e render do projeto."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from liveclips import agents, captions, editing, media, music, project, sfx
from liveclips.store import DEFAULT_PROFILE
from tests.test_editor_pro import HAS_FFMPEG, ffmpeg, gray_frames, np


def words_of(text, start=0.0, step=.36, length=.3):
    result, cursor = [], start
    for token in text.split():
        result.append(dict(start=round(cursor, 3), end=round(cursor + length, 3), word=token))
        cursor += step
    return result


def transcript_of(text, start=0.0):
    words = words_of(text, start)
    return [dict(start=words[0]['start'], end=words[-1]['end'], text=text, words=words)]


class ProjectTests(unittest.TestCase):
    def test_clean_merges_cuts_and_clamps_values(self):
        value = project.clean(dict(cuts=[dict(start=2, end=3), dict(start=2.9, end=4)], zooms=[dict(start=1, end=3, zoom=9)]), 20)
        self.assertEqual(value['cuts'], [dict(start=2.0, end=4.0)])
        self.assertEqual(value['zooms'][0]['zoom'], 1.15)

    def test_clean_rejects_bad_input(self):
        for bad in (dict(cuts=[dict(start='x', end=3)]), dict(cuts=[dict(start=0, end=19.5)]), dict(style='inexistente'),
                    dict(zooms=[dict(start=1, end=3, curve='xx')]), dict(titles=[dict(text='a', start=1, end=3, color='vermelho')]),
                    dict(captions=dict(style='nao')), dict(cuts=[dict(start=float('nan'), end=3)])):
            with self.assertRaises(ValueError, msg=str(bad)):
                project.clean(bad, 20)

    def test_music_must_exist_in_the_library(self):
        with self.assertRaises(ValueError):
            project.clean(dict(music=dict(id='abc')), 20, music_exists=lambda _id: False)
        ok = project.clean(dict(music=dict(id='abc', volume=5)), 20, music_exists=lambda _id: True)
        self.assertEqual(ok['music']['volume'], .6)
        self.assertFalse(ok['music']['authorized'])

    def test_retext_keeps_timing_when_text_is_unchanged_and_spreads_when_changed(self):
        words = words_of('uma frase curta')
        same = project.retext_line(dict(start=0, end=1.2, text='uma frase curta', words=words))
        self.assertEqual(same, words)
        changed = project.retext_line(dict(start=0, end=2, text='outra frase bem mais longa', words=words))
        self.assertEqual(len(changed), 5)
        self.assertAlmostEqual(changed[0]['start'], 0)
        self.assertAlmostEqual(changed[-1]['end'], 2, places=2)
        self.assertTrue(all(a['end'] <= b['start'] + 1e-6 for a, b in zip(changed, changed[1:])))

    def test_cuts_and_zooms_reach_the_render_plan(self):
        data = dict(project=project.clean(dict(cuts=[dict(start=3, end=4)], zooms=[dict(start=5, end=7, zoom=1.1)]), 20))
        candidate = dict(start=100, end=120, data=dict(edit_plan=dict(decisions=[], punches=[]), project=data['project']))
        self.assertEqual(editing.cuts_for(candidate)[0]['start'], 3)
        self.assertEqual(editing.punches_for(candidate)[0]['zoom'], 1.1)


class RemapTests(unittest.TestCase):
    def test_cuts_speed_and_lead(self):
        remap = editing.Remap(20, [dict(start=4, end=6)], speeds=[(10, 14, 2.0)], lead=1.5)
        self.assertAlmostEqual(remap.map(3), 4.5)
        self.assertAlmostEqual(remap.map(5), 5.5)  # dentro do corte: cola no ponto de junção
        self.assertAlmostEqual(remap.map(8), 7.5)  # 8 - 2 (corte) + 1.5 (abertura)
        self.assertAlmostEqual(remap.map(12), 10.5)  # 8 s de saída + 1 s (2 s a 2x) + 1.5
        self.assertAlmostEqual(remap.length, 16)  # 20 - corte 2 - economia de 2 s na faixa a 2x

    def test_legacy_list_of_cuts_still_works(self):
        cuts = [dict(start=2, end=3)]
        self.assertAlmostEqual(editing._shift_time(5, cuts), 4)


class SmartCaptionTests(unittest.TestCase):
    def test_breaks_on_sentences_and_avoids_weak_endings(self):
        words = [dict(start=w['start'], end=w['end'], text=w['word']) for w in words_of('eu nunca vi isso na minha vida. foi muito louco de verdade')]
        lines = [' '.join(w['text'] for w in g) for g in captions.smart_groups(words, 4, 26)]
        self.assertIn('na minha vida.', lines)
        self.assertFalse(any(line.split()[-1] in captions.WEAK for line in lines[:-1] if len(line.split()) > 1))

    def test_dictionary_fixes_close_names_but_not_plurals(self):
        tokens = [dict(start=i, end=i + .5, text=t) for i, t in enumerate(['o', 'Koringa', 'jogou', 'jogo'])]
        fixed, changes = captions.fix_vocabulary(tokens, 'Coringa, Jogos')
        texts = [w['text'] for w in fixed]
        self.assertEqual(texts, ['o', 'Coringa', 'jogou', 'jogo'])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['para'], 'Coringa')

    def test_keywords_get_their_own_color_only_in_expressive_styles(self):
        words = [dict(start=i * .4, end=i * .4 + .35, word=w) for i, w in enumerate('isso custou 5000 reais nunca mais'.split())]
        segments = [dict(start=0, end=3, text='x', words=words)]
        impact = captions.make_ass(segments, 0, 3, style='impact', smart=True)
        clean = captions.make_ass(segments, 0, 3, style='clean', smart=True)
        self.assertIn(captions.KEYWORD_COLOR, impact)
        self.assertNotIn(captions.KEYWORD_COLOR, clean)

    def test_titles_are_written_in_their_own_styles(self):
        ass = captions.make_ass([], 0, 5, titles=[dict(text='Isso mudou tudo', start=0, end=2.5, style='bar', position='top', color='#FFD400')],
                                captions=False)
        self.assertIn('Style: Titulo0', ass)
        self.assertIn('Dialogue: 1,0:00:00.00,0:00:02.50,Titulo0', ass)
        self.assertNotIn('Principal,,', ass.split('[Events]')[1])

    def test_editor_lines_keep_one_line_per_group(self):
        segments = transcript_of('fala galera tudo bem. então eu estava jogando e apareceu 100 mil!')
        lines, _ = captions.lines_from_transcript(segments, 0, 10)
        self.assertGreaterEqual(len(lines), 3)
        ass = captions.make_ass([dict(start=l['start'], end=l['end'], text=l['text'], words=l['words']) for l in lines], 0, 10, keep_lines=True, smart=True)
        self.assertEqual(ass.count('Dialogue:'), sum(len(l['words']) for l in lines))


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.words = words_of('Fala galera tudo bem. Então eu estava jogando e do nada apareceu 100 mil de dinheiro! '
                              'Você não vai acreditar nisso? Nunca vi isso na minha vida. Foi muito louco mesmo cara.', 1.8)
        self.transcript = [dict(start=1.8, end=self.words[-1]['end'], text='x', words=self.words)]
        self.end = self.words[-1]['end'] + 1

    def test_hook_flags_greeting_and_suggests_a_stronger_start(self):
        analysis = agents.hook_analysis(self.transcript, 0, self.end)
        self.assertLess(analysis['score'], 3)
        self.assertTrue(any('cumprimento' in issue for issue in analysis['issues']))
        self.assertTrue(analysis['suggestion'])
        self.assertGreater(analysis['suggestion']['start'], 2)

    def test_tighten_skips_greeting_and_trailing_silence(self):
        result = agents.tighten_bounds(self.transcript, 0, self.end + 3)
        self.assertGreater(result['start'], 2.5)
        self.assertLess(result['end'], self.end + 3)
        self.assertTrue(result['changes'])

    def test_tighten_never_creates_a_tiny_clip(self):
        short = transcript_of('oi tudo bem. certo então')
        self.assertEqual(agents.tighten_bounds(short, 0, 6)['start'], 0)

    def test_titles_are_real_phrases_from_the_speech(self):
        titles = agents.suggest_titles(self.transcript, 0, self.end)
        spoken = ' '.join(w['word'] for w in self.words).lower()
        self.assertTrue(titles)
        for item in titles:
            self.assertIn(item['text'].rstrip('…').lower().rstrip('.!?,'), spoken)
            self.assertLessEqual(len(item['text']), 45)

    def test_teaser_picks_a_later_strong_sentence(self):
        teaser = agents.suggest_teaser(self.transcript, 0, self.end, min_into=3)
        self.assertTrue(teaser)
        self.assertGreaterEqual(teaser['start'], 3)
        self.assertLessEqual(teaser['end'] - teaser['start'], 3.8)

    def test_cadence_alternates_and_never_overlaps(self):
        points = agents.cadence_punches(self.transcript, 0, self.end, {'zoom_max': 1.1})
        self.assertTrue(points)
        for a, b in zip(points, points[1:]):
            self.assertLess(a['end'], b['start'])
        self.assertTrue(all(1 < p['zoom'] <= 1.15 for p in points))

    def test_plan_edits_adds_cadence_only_when_enabled(self):
        base = dict(DEFAULT_PROFILE, editorial_style='podcast', auto_cadence=False)
        off = editing.plan_edits(dict(start=0, end=self.end), {}, transcript=self.transcript, profile=base)
        on = editing.plan_edits(dict(start=0, end=self.end), {}, transcript=self.transcript, profile=dict(base, auto_cadence=True))
        self.assertEqual(len(off['punches']), 0)
        self.assertGreater(len(on['punches']), 0)

    def test_snap_to_beats(self):
        self.assertEqual(agents.snap_to_beats([1.05, 2.4], [1.0, 1.5, 2.0], .2), [1.0, 2.4])


@unittest.skipUnless(HAS_FFMPEG, 'FFmpeg/ffprobe ou numpy não encontrados')
class MusicTests(unittest.TestCase):
    def click_track(self, path, seconds=40, loud_from=None):
        gain = '0.9' if loud_from is None else f"if(lt(t,{loud_from}),0.15,0.9)"
        ffmpeg('-f', 'lavfi', '-i', f"aevalsrc='{gain}*sin(2*PI*1500*t)*exp(-80*mod(t,0.5))':d={seconds}:s=22050", '-ac', '2', str(path))

    def test_url_validation(self):
        self.assertEqual(music.clean_url('https://youtu.be/dQw4w9WgXcQ?t=10'), 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(music.clean_url('youtube.com/watch?v=dQw4w9WgXcQ&list=PLx'), 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(music.clean_url('https://www.youtube.com/shorts/abcDEF12345'), 'https://www.youtube.com/watch?v=abcDEF12345')
        for bad in ('https://exemplo.com/a.mp3', 'ftp://youtube.com/watch?v=abcdefghijk', 'https://youtube.com/playlist?list=PL1',
                    'https://youtube.com.evil.com/watch?v=abcdefghijk', ''):
            with self.assertRaises(music.MusicError, msg=bad):
                music.clean_url(bad)

    def test_tempo_and_best_section_are_estimated(self):
        with tempfile.TemporaryDirectory() as temp:
            track = Path(temp) / 'clique.wav'
            self.click_track(track, 40, loud_from=22)
            info = music.analyze(track, clip_length=10)
            self.assertAlmostEqual(info['bpm'], 120, delta=2)
            self.assertGreater(info['bpm_confidence'], .2)
            self.assertGreaterEqual(info['best_start'], 18)
            self.assertEqual(len(info['waveform']), 240)
            beats = music.beat_times(info, 10, 12)
            self.assertEqual(len(beats), 4)
            self.assertAlmostEqual(beats[1] - beats[0], .5, places=2)

    def test_noise_has_no_tempo(self):
        with tempfile.TemporaryDirectory() as temp:
            track = Path(temp) / 'ruido.wav'
            ffmpeg('-f', 'lavfi', '-i', 'anoisesrc=d=30:c=white:a=0.3:r=22050', '-ac', '2', str(track))
            self.assertEqual(music.analyze(track)['bpm'], 0.0)

    def test_download_from_link_uses_the_library_and_caches(self):
        calls = []

        class FakeYDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                calls.append('info')
                return dict(id='dQw4w9WgXcQ', title='Faixa de teste', uploader='Canal', duration=20.0)

            def download(self, urls):
                calls.append('download')
                target = self.options['outtmpl'].replace('%(ext)s', 'webm')
                ffmpeg('-f', 'lavfi', '-i', 'sine=f=440:duration=20', target.replace('.webm', '.wav'))

        with tempfile.TemporaryDirectory() as root:
            item = music.fetch(root, 'https://youtu.be/dQw4w9WgXcQ', factory=FakeYDL)
            self.assertEqual(item['title'], 'Faixa de teste')
            self.assertNotIn('file', item)
            self.assertTrue(music.path_of(root, item['id']).is_file())
            again = music.fetch(root, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', factory=FakeYDL)
            self.assertEqual(again['id'], item['id'])
            self.assertEqual(calls, ['info', 'download'])
            self.assertEqual(len(music.library(root)), 1)
            music.remove(root, item['id'])
            self.assertEqual(music.library(root), [])

    def test_live_and_long_links_are_refused(self):
        class LiveYDL:
            def __init__(self, options): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def extract_info(self, url, download=False): return dict(id='x', title='t', duration=100, is_live=True)

        class LongYDL(LiveYDL):
            def extract_info(self, url, download=False): return dict(id='x', title='t', duration=60 * 60)

        with self.assertRaises(music.MusicError):
            music.inspect('https://youtu.be/dQw4w9WgXcQ', LiveYDL)
        with self.assertRaises(music.MusicError):
            music.inspect('https://youtu.be/dQw4w9WgXcQ', LongYDL)

    def test_download_errors_are_explained_in_portuguese(self):
        self.assertIn('Deno', music.explain(Exception('No supported JavaScript runtime could be found')))
        self.assertIn('privado', music.explain(Exception('Video unavailable. This video is private')))

    def test_local_file_import_converts_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            source = Path(other) / 'minha musica.wav'
            self.click_track(source, 12)
            first = music.import_file(root, source)
            second = music.import_file(root, source)
            self.assertEqual(first['id'], second['id'])
            self.assertEqual(first['origin'], 'arquivo')
            with self.assertRaises(music.MusicError):
                music.import_file(root, Path(other) / 'nao.exe')

    def test_every_sound_effect_is_generated(self):
        with tempfile.TemporaryDirectory() as root:
            for name, (_, seconds, _) in sfx.EFFECTS.items():
                path = sfx.ensure(root, name)
                self.assertAlmostEqual(media.audio_duration(path), seconds, delta=.1, msg=name)
            with self.assertRaises(ValueError):
                sfx.ensure(root, 'inexistente')


@unittest.skipUnless(HAS_FFMPEG, 'FFmpeg/ffprobe ou numpy não encontrados')
class StudioRenderTests(unittest.TestCase):
    def make_source(self, root, seconds=12):
        source = Path(root) / 'fonte.ts'
        flash = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(mod(t,2),1,1.1)'"
        audio = "sine=f=1000:sample_rate=48000:duration=%d,volume=volume=0:enable='not(between(mod(t,2),1,1.1))'" % seconds
        ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30:duration={seconds},{flash}', '-f', 'lavfi', '-i', audio,
               '-c:v', 'libx264', '-preset', 'veryfast', '-g', '60', '-crf', '24', '-c:a', 'aac', '-shortest', str(source))
        return source

    def candidate(self, source, proj=None, seconds=12, **profile):
        base = dict(DEFAULT_PROFILE, camera_rect=[0, 0, .25, .25], min_free_gb=.1, editorial_style='clean', threads=2, **profile)
        plan = editing.plan_edits(dict(start=0, end=seconds), {}, profile=base)
        parts = [dict(path=str(source), sha=media.sha_file(source), seq=0, **{'in': 0.0, 'out': float(seconds)},
                      global_start=0, global_end=seconds, group_id='g')]
        data = dict(edit_plan=plan, edit_overrides={}, editorial_audit={})
        if proj is not None:
            data['project'] = project.clean(proj, seconds, music_exists=lambda _id: True)
        return dict(id='studio', start=0, end=seconds, parts=parts, profile=base, data=data)

    def flashes(self, clip):
        frames = gray_frames(clip, 16, 30)
        level = frames.reshape(len(frames), -1).mean(axis=1)
        on = level > level.max() * .9
        return [i / 30 for i in range(1, len(on)) if on[i] and not on[i - 1]]

    def rms_between(self, clip, a, b):
        raw = subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(clip), '-vn', '-ac', '1', '-ar', '16000',
                              '-f', 's16le', '-'], capture_output=True, check=True).stdout
        samples = np.frombuffer(raw, np.int16).astype(float) / 32768
        part = samples[int(a * 16000):int(b * 16000)]
        return float(np.sqrt((part ** 2).mean()))

    def test_manual_cut_shortens_clip_and_keeps_sync(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            clip = media.render(self.candidate(source, dict(cuts=[dict(start=4, end=6)])), [], temp, False, pipeline='single', root=temp)
            self.assertAlmostEqual(media.probe(clip)['duration'], 10, delta=.1)
            for found, wanted in zip(self.flashes(clip), [1, 3, 5, 7, 9]):
                self.assertAlmostEqual(found, wanted, delta=.08)

    def test_draft_is_a_small_vertical_preview_with_all_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            proj = dict(cuts=[dict(start=4, end=6)], zooms=[dict(start=1, end=3, zoom=1.1)],
                        titles=[dict(text='Título de teste', start=0, end=3, style='big')])
            clip = media.render(self.candidate(source, proj), [], temp, 'draft', pipeline='single', root=temp)
            info = media.probe(clip)
            self.assertEqual((info['width'], info['height']), (540, 960))
            self.assertAlmostEqual(info['duration'], 10, delta=.1)
            self.assertIn('_rascunho', str(clip))
            # a prévia sai sem texto queimado: o navegador desenha legenda e título ao vivo por cima
            self.assertNotIn('Dialogue:', (clip.parent / 'legendas.ass').read_text(encoding='utf-8-sig'))

    def test_edited_caption_lines_replace_the_transcript(self):
        words = [dict(start=1.0 + i * .5, end=1.4 + i * .5, word=w) for i, w in enumerate(['isso', 'foi', 'ruim'])]
        transcript = [dict(start=1.0, end=2.4, text='isso foi ruim', words=words)]
        proj = dict(captions=dict(lines=[dict(start=1.0, end=2.4, text='ISSO FOI INCRÍVEL', words=[])]))
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            clip = media.render(self.candidate(source, proj), transcript, temp, False, pipeline='single', root=temp)
            ass = (clip.parent / 'legendas.ass').read_text(encoding='utf-8-sig')
            self.assertIn('INCRÍVEL', ass.upper())
            self.assertNotIn('RUIM', ass.upper())

    def test_captions_can_be_turned_off(self):
        words = [dict(start=1.0, end=1.4, word='oi')]
        transcript = [dict(start=1.0, end=1.4, text='oi', words=words)]
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            clip = media.render(self.candidate(source, dict(captions=dict(enabled=False))), transcript, temp, False, pipeline='single', root=temp)
            self.assertNotIn('Principal,,', (clip.parent / 'legendas.ass').read_text(encoding='utf-8-sig').split('[Events]')[1])

    def library_track(self, root, seconds=40):
        item = None

        class FakeYDL:
            def __init__(self, options): self.options = options
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False): return dict(id='abcdefghijk', title='Trilha', uploader='Autor', duration=seconds)
            def download(self, urls):
                ffmpeg('-f', 'lavfi', '-i', f'sine=f=440:duration={seconds}', self.options['outtmpl'].replace('%(ext)s', 'wav'))
        return music.fetch(root, 'https://youtu.be/abcdefghijk', factory=FakeYDL)

    def test_music_fills_silence_fades_in_and_is_credited(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            track = self.library_track(temp)
            proj = dict(music=dict(id=track['id'], start=3, volume=.3, fade_in=1.5, fade_out=1, authorized=True))
            clip = media.render(self.candidate(source, proj), [], temp, False, pipeline='single', root=temp)
            plain = media.render(self.candidate(source), [], temp, False, pipeline='single', root=temp)
            self.assertGreater(self.rms_between(clip, 4.2, 4.8), .02)
            self.assertLess(self.rms_between(plain, 4.2, 4.8), .005)
            self.assertLess(self.rms_between(clip, 0.0, .3), self.rms_between(clip, 4.2, 4.8) * .6)  # entrada gradual
            credits = (clip.parent / 'creditos.txt').read_text(encoding='utf-8')
            self.assertIn('Música: Trilha', credits)
            self.assertIn('abcdefghijk', credits)

    def test_music_without_authorization_blocks_the_export_but_not_the_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            track = self.library_track(temp)
            candidate = self.candidate(source, dict(music=dict(id=track['id'], authorized=False)))
            with self.assertRaises(ValueError):
                media.render(candidate, [], temp, False, pipeline='single', root=temp)
            self.assertTrue(media.render(candidate, [], temp, 'draft', pipeline='single', root=temp).is_file())

    def test_teaser_opens_the_video_with_a_later_moment(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            proj = dict(teaser=dict(start=8.8, end=10.0))
            clip = media.render(self.candidate(source, proj), [], temp, False, pipeline='single', root=temp)
            self.assertAlmostEqual(media.probe(clip)['duration'], 13.2, delta=.15)
            found = self.flashes(clip)
            self.assertAlmostEqual(found[0], .2, delta=.1)  # o flash de 9 s aparece logo na abertura
            manifest = json.loads((clip.parent / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertFalse(manifest['teaser_skipped'])

    def test_legacy_fallback_records_that_the_teaser_was_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.make_source(temp)
            clip = media.render(self.candidate(source, dict(teaser=dict(start=8.8, end=10.0))), [], temp, False, pipeline='legacy', root=temp)
            manifest = json.loads((clip.parent / 'manifesto.json').read_text(encoding='utf-8'))
            self.assertTrue(manifest['teaser_skipped'])
            self.assertAlmostEqual(media.probe(clip)['duration'], 12, delta=.15)

    def dummy(self, temp):
        file = Path(temp) / 'x.bin'
        file.write_bytes(b'0' * 100)
        return file

    def test_style_and_grade_override_from_the_project(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = self.candidate(self.dummy(temp), dict(style='hype', grade=dict(contrast=1.2, saturation=1.3)))
            look = editing.effective_look(candidate)
        self.assertEqual(look['curve'], 'beat')
        self.assertEqual(look['grade']['contrast'], 1.2)

    def test_signature_changes_with_the_project(self):
        with tempfile.TemporaryDirectory() as temp:
            file = self.dummy(temp)
            a = self.candidate(file)
            b = self.candidate(file, dict(cuts=[dict(start=1, end=2)]))
        self.assertNotEqual(media.signature(a), media.signature(b))


if __name__ == '__main__':
    unittest.main()
