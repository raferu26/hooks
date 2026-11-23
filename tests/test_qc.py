import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import media, qc

ASS_HEAD = ('[Script Info]\nPlayResX: 720\nPlayResY: 1280\n[V4+ Styles]\n'
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, '
            'StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
            'Style: Principal,Arial,{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,70,90,{margin},1\n'
            'Style: Titulo0,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,50,50,{top},1\n'
            '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')


def ass(events, size=46, margin=260, top=170):
    body = ''.join(f'Dialogue: 0,{a},{b},{style},,0,0,0,,{text}\n' for a, b, style, text in events)
    return ASS_HEAD.format(size=size, margin=margin, top=top) + body


def by_id(items):
    return {i['id']: i for i in items}


class CaptionChecks(unittest.TestCase):
    def test_caption_running_past_the_end_is_an_error(self):
        text = ass([('0:00:00.50', '0:00:02.00', 'Principal', 'oi gente'), ('0:00:09.00', '0:00:11.50', 'Principal', 'ultima frase cortada')])
        got = by_id(qc.caption_checks(text, 10.0))
        self.assertEqual(got['legenda_cortada']['status'], 'erro')
        ok = by_id(qc.caption_checks(text, 12.0))
        self.assertEqual(ok['legenda_cortada']['status'], 'ok')

    def test_default_caption_margin_is_flagged_as_attention_with_a_fix(self):
        text = ass([('0:00:00.00', '0:00:02.00', 'Principal', 'texto simples')], margin=260)
        got = by_id(qc.caption_checks(text, 10.0))
        self.assertEqual(got['zona_inferior']['status'], 'atencao')
        self.assertIn('aproximado', got['zona_inferior']['detail'])
        safe = by_id(qc.caption_checks(ass([('0:00:00.00', '0:00:02.00', 'Principal', 'texto simples')], margin=340), 10.0))
        self.assertEqual(safe['zona_inferior']['status'], 'ok')

    def test_title_too_close_to_top_and_reading_speed(self):
        text = ass([('0:00:00.00', '0:00:02.00', 'Titulo0', 'Titulo'),
                    ('0:00:03.00', '0:00:03.50', 'Principal', 'uma frase muito longa para meio segundo apenas'),
                    ('0:00:04.00', '0:00:04.50', 'Principal', 'outra frase muito longa para meio segundo')], top=40, margin=340)
        got = by_id(qc.caption_checks(text, 10.0))
        self.assertEqual(got['zona_superior']['status'], 'atencao')
        self.assertEqual(got['leitura']['status'], 'atencao')

    def test_no_captions_is_not_a_problem(self):
        self.assertEqual(qc.caption_checks(ass([]), 10.0)[0]['status'], 'ok')


class AudioAndBlack(unittest.TestCase):
    def test_loudness_bands(self):
        self.assertEqual(by_id(qc.audio_checks(dict(input_i=-16.2, input_tp=-2.0)))['volume']['status'], 'ok')
        self.assertEqual(by_id(qc.audio_checks(dict(input_i=-18.0, input_tp=-2.0)))['volume']['status'], 'atencao')
        self.assertEqual(by_id(qc.audio_checks(dict(input_i=-24.0, input_tp=-2.0)))['volume']['status'], 'erro')
        self.assertEqual(by_id(qc.audio_checks(dict(input_i=-16.0, input_tp=-0.1)))['pico']['status'], 'erro')
        self.assertEqual(by_id(qc.audio_checks(None))['volume']['status'], 'erro')

    def test_black_intervals(self):
        self.assertEqual(qc.black_checks([(0, .2)], 30)['status'], 'ok')
        self.assertEqual(qc.black_checks([(5, 6)], 30)['status'], 'atencao')
        self.assertEqual(qc.black_checks([(0, 20)], 30)['status'], 'erro')
        self.assertEqual(qc.parse_blackdetect('x black_start:5.2 black_end:6.4 black_duration:1.2'), [(5.2, 6.4)])


class RealFile(unittest.TestCase):
    def make(self, folder, filter_v, filter_a, seconds=6):
        out = Path(folder) / 'v.mp4'
        subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', filter_v,
                        '-f', 'lavfi', '-i', filter_a, '-t', str(seconds), '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(out)], check=True)
        return out

    def test_good_and_bad_files_are_told_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = self.make(tmp, 'testsrc2=s=1080x1920:r=15', 'sine=f=300:sample_rate=48000,volume=2')
            report = qc.check_export(good)
            got = by_id(report['items'])
            self.assertEqual(got['preto']['status'], 'ok')
            self.assertEqual(got['formato']['status'], 'ok')
            self.assertEqual(got['volume']['status'], 'ok', got['volume'])
            self.assertEqual(report['level'], 'ok', report['summary'])
        with tempfile.TemporaryDirectory() as tmp:
            bad = self.make(tmp, 'color=c=black:s=540x960:r=15', 'sine=f=300:sample_rate=48000,volume=0.001', seconds=5)
            report = qc.check_export(bad)
            got = by_id(report['items'])
            self.assertEqual(got['preto']['status'], 'erro')
            self.assertEqual(got['formato']['status'], 'atencao')
            self.assertEqual(got['volume']['status'], 'erro')
            self.assertEqual(report['level'], 'erro')
            text = qc.as_text(report)
            self.assertIn('PROBLEMA', text)
            self.assertIn('aproximadas', text)

    def test_unreadable_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = Path(tmp) / 'x.mp4'
            junk.write_bytes(b'nada')
            report = qc.check_export(junk)
            self.assertEqual(report['level'], 'erro')


if __name__ == '__main__':
    unittest.main()


class EngineIntegration(unittest.TestCase):
    def test_run_qc_stores_report_and_text_and_never_raises(self):
        from liveclips import engine as engine_module
        from liveclips.store import Store
        from tests.test_second_pass import make_session
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'd')
            _, _, cid = make_session(store)
            eng = engine_module.Engine(store)
            video = Path(tmp) / 'saida.mp4'
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=15',
                            '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000,volume=2', '-t', '4', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True)
            (Path(tmp) / 'legendas.ass').write_text(ass([('0:00:00.00', '0:00:09.00', 'Principal', 'passa do fim')]), encoding='utf-8-sig')
            eng.run_qc(cid, video)
            data = store.candidate(cid)['data']
            self.assertEqual(data['qc']['level'], 'erro')
            self.assertTrue((Path(tmp) / 'qualidade.txt').is_file())
            eng.run_qc(cid, Path(tmp) / 'nao_existe.mp4')  # não levanta
            self.assertIn(store.candidate(cid)['data']['qc']['level'], ('erro', 'atencao'))
