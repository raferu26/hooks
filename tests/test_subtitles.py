import tempfile
import unittest
from pathlib import Path

from liveclips import subtitles


SRT = "1\r\n00:00:01,000 --> 00:00:03,500\r\n<i>Olá</i>, não é {\\an8}assim\r\nque se faz.\r\n\r\n2\r\n00:01:02,5 --> 00:01:04,000\r\nSegunda fala\r\n\r\n3\r\n00:00:10,000 --> 00:00:09,000\r\nInválida\r\n"
VTT = "WEBVTT\n\nNOTE comentário\n\n00:01.000 --> 00:02.000 align:start\nLinha única\n\n01:00:00.250 --> 01:00:01.000\nHora\n"
ASS = ("[Script Info]\nTitle: x\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
       "Dialogue: 0,0:00:05.00,0:00:07.50,Default,,0,0,0,,Texto com vírgula, ok\\Nsegunda linha\n"
       "Dialogue: 0,0:00:08.00,0:00:08.00,Default,,0,0,0,,vazio de tempo\n")


class Parse(unittest.TestCase):
    def test_srt_with_tags_accents_and_invalid_block(self):
        out = subtitles.parse(SRT.encode('utf-8'), 'a.srt')
        self.assertEqual([s['text'] for s in out], ['Olá, não é assim que se faz.', 'Segunda fala'])
        self.assertEqual(out[0]['start'], 1.0)
        self.assertEqual(out[0]['end'], 3.5)
        self.assertEqual(out[1]['start'], 62.5)
        self.assertEqual(out[0]['source'], 'importada')

    def test_vtt_short_and_long_timestamps(self):
        out = subtitles.parse(VTT, 'a.vtt')
        self.assertEqual([(s['start'], s['text']) for s in out], [(1.0, 'Linha única'), (3600.25, 'Hora')])

    def test_ass_keeps_commas_and_drops_empty_duration(self):
        out = subtitles.parse(ASS, 'a.ass')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['text'], 'Texto com vírgula, ok segunda linha')
        self.assertEqual((out[0]['start'], out[0]['end']), (5.0, 7.5))

    def test_encodings(self):
        text = "1\n00:00:01,000 --> 00:00:02,000\nação\n"
        for raw in (text.encode('utf-8'), b'\xef\xbb\xbf' + text.encode('utf-8'), text.encode('utf-16'), text.encode('cp1252')):
            self.assertEqual(subtitles.parse(raw, 'x.srt')[0]['text'], 'ação')

    def test_rejects_unknown_format_empty_and_huge(self):
        with self.assertRaises(subtitles.SubtitleError):
            subtitles.parse('x', 'a.txt')
        with self.assertRaises(subtitles.SubtitleError):
            subtitles.parse('sem nada', 'a.srt')
        with self.assertRaises(subtitles.SubtitleError):
            subtitles.parse(b'0' * (subtitles.MAX_BYTES + 1), 'a.srt')

    def test_shift_and_window(self):
        out = subtitles.parse(SRT, 'a.srt')
        moved = subtitles.shift(out, -2.0)
        self.assertEqual(moved[0]['start'], 0.0)       # 1,0 - 2 vira antes de zero e é cortado em 0
        self.assertEqual(moved[0]['end'], 1.5)
        self.assertEqual(subtitles.shift(out, -10)[0]['text'], 'Segunda fala')
        win = subtitles.window(out, 62, 70)
        self.assertEqual((win[0]['start'], win[0]['end']), (0.5, 2.0))

    def test_session_folder(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(subtitles.for_session(t), ([], []))
            folder = Path(t) / 'legendas'
            folder.mkdir()
            (folder / 'a.srt').write_text(SRT, encoding='utf-8')
            (folder / 'quebrada.srt').write_text('lixo', encoding='utf-8')
            (folder / 'nota.txt').write_text('ignora', encoding='utf-8')
            segments, warnings = subtitles.for_session(t)
            self.assertEqual(len(segments), 2)
            self.assertEqual(len(warnings), 1)
            self.assertIn('quebrada.srt', warnings[0])


if __name__ == '__main__':
    unittest.main()
