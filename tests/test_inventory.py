import subprocess
import tempfile
import unittest
from pathlib import Path

from liveclips import inventory, media


def stream(**kw):
    base = dict(codec_type='video', codec_name='h264', width=1920, height=1080, avg_frame_rate='30/1', r_frame_rate='30/1', pix_fmt='yuv420p')
    base.update(kw)
    return base


AUDIO = dict(codec_type='audio', codec_name='aac', channels=2, sample_rate='48000')


class ParseTests(unittest.TestCase):
    def ids(self, data):
        return [r['id'] for r in inventory.parse(data)['risks']]

    def test_clean_file_has_no_risks(self):
        info = inventory.parse(dict(streams=[stream(), AUDIO], format=dict(duration='10')))
        self.assertEqual([], info['risks'])
        self.assertFalse(info['vfr'])

    def test_vfr_detected(self):
        self.assertIn('vfr', self.ids(dict(streams=[stream(avg_frame_rate='2400/101', r_frame_rate='60/1'), AUDIO], format={})))

    def test_ntsc_is_not_vfr(self):
        self.assertNotIn('vfr', self.ids(dict(streams=[stream(avg_frame_rate='30000/1001', r_frame_rate='30000/1001'), AUDIO], format={})))

    def test_rotation_swaps_display_size(self):
        info = inventory.parse(dict(streams=[stream(side_data_list=[dict(rotation=-90)]), AUDIO], format={}))
        self.assertEqual(270, info['rotation'])
        self.assertEqual([1080, 1920], info['display_size'])
        self.assertIn('rotacao', [r['id'] for r in info['risks']])

    def test_hdr_10bit_multiple_audio_and_no_audio(self):
        data = dict(streams=[stream(color_transfer='smpte2084', pix_fmt='yuv420p10le'), AUDIO, AUDIO], format={})
        ids = self.ids(data)
        self.assertTrue({'hdr', '10bits', 'varias_faixas'} <= set(ids))
        self.assertIn('sem_audio', self.ids(dict(streams=[stream()], format={})))

    def test_no_video_raises(self):
        with self.assertRaises(ValueError):
            inventory.parse(dict(streams=[AUDIO], format={}))


class RealFileTests(unittest.TestCase):
    def test_real_ffprobe_on_generated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'a.mp4'
            subprocess.run([media.tool('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=30',
                            '-f', 'lavfi', '-i', 'sine=f=300', '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
                            '-metadata:s:v:0', 'rotate=90', str(video)], check=True)
            info = inventory.describe(video)
            self.assertEqual([320, 240], info['stored_size'])
            self.assertEqual(1, len(info['audio']))
            self.assertAlmostEqual(2.0, info['duration'], delta=.2)


if __name__ == '__main__':
    unittest.main()
