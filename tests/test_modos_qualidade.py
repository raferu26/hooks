"""0.19 · E2: os quatro modos de qualidade mudam de verdade o arquivo final (antes só valiam no plano B)."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from liveclips import hardware, media, telemetry


def value(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


class ModeArgumentTests(unittest.TestCase):
    def test_quatro_modos_distintos_na_cpu(self):
        seen = set()
        for name in ('rapido', 'equilibrado', 'qualidade', 'entrega'):
            kind, args = hardware.choose('cpu', mode=name)
            self.assertEqual(kind, 'cpu')
            self.assertEqual(value(args, '-c:v'), 'libx264')
            seen.add((value(args, '-preset'), value(args, '-crf'), value(args, '-x264-params')))
        self.assertEqual(len(seen), 4)

    def test_qualidade_cresce_com_o_modo(self):
        crf = [int(telemetry.MODES[m]['crf']) for m in ('rapido', 'equilibrado', 'qualidade', 'entrega')]
        self.assertEqual(crf, sorted(crf, reverse=True))
        order = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']
        presets = [order.index(telemetry.MODES[m]['preset']) for m in ('rapido', 'equilibrado', 'qualidade', 'entrega')]
        self.assertEqual(presets, sorted(presets))
        audio = [telemetry.MODES[m]['audio'] for m in ('rapido', 'equilibrado', 'qualidade', 'entrega')]
        self.assertEqual(audio, sorted(audio))

    def test_equilibrado_preserva_o_ajuste_anterior(self):
        self.assertEqual(hardware.choose('cpu', mode='equilibrado')[1], hardware.CPU_FINAL)
        self.assertEqual(hardware.arguments('nvenc'), ['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '20', '-b:v', '0', '-spatial-aq', '1'])

    def test_modo_desconhecido_cai_no_equilibrado(self):
        self.assertEqual(hardware.choose('cpu', mode='xyz')[1], hardware.CPU_FINAL)

    def test_placa_de_video_recebe_ajuste_proprio_por_modo(self):
        with patch.object(hardware, 'detect', return_value=['nvenc']):
            fast = hardware.choose('nvenc', mode='rapido')[1]
            best = hardware.choose('nvenc', mode='qualidade')[1]
        self.assertEqual(value(fast, '-c:v'), 'h264_nvenc')
        self.assertGreater(int(value(fast, '-cq')), int(value(best, '-cq')))
        self.assertNotEqual(value(fast, '-preset'), value(best, '-preset'))

    def test_entrega_sempre_usa_x264_mesmo_com_placa(self):
        with patch.object(hardware, 'detect', return_value=['nvenc', 'qsv']):
            kind, args = hardware.choose('nvenc', mode='entrega')
        self.assertEqual(kind, 'cpu')
        self.assertEqual(value(args, '-preset'), 'slower')

    def test_rascunho_nao_depende_do_modo(self):
        for name in telemetry.MODES:
            self.assertEqual(hardware.choose('auto', draft=True, mode=name), ('cpu', hardware.CPU_DRAFT))

    def test_codificador_grava_modo_no_manifesto(self):
        meta = {}
        args = media._video_codec(dict(video_encoder='cpu', quality_mode='qualidade'), False, meta)
        self.assertEqual(meta['quality_mode'], 'qualidade')
        self.assertIn('-x264-params', args)
        self.assertEqual(meta['video_args'], ' '.join(args))
        self.assertEqual(telemetry.audio_bitrate(dict(quality_mode='rapido')), '128k')


class RealEncodeTests(unittest.TestCase):
    """Codifica o mesmo trecho com os quatro argumentos de CPU e confere que o arquivo muda de fato."""

    def test_arquivos_diferem_por_modo(self):
        ffmpeg = media.tool('ffmpeg')
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'src.mp4'
            subprocess.run([ffmpeg, '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=540x960:rate=30:duration=2', '-pix_fmt', 'yuv420p', '-c:v', 'libx264',
                            '-crf', '0', '-preset', 'ultrafast', str(src)], check=True)
            sizes = {}
            for name in ('rapido', 'equilibrado', 'qualidade', 'entrega'):
                out = Path(temp) / (name + '.mp4')
                args = hardware.choose('cpu', mode=name)[1]
                subprocess.run([ffmpeg, '-nostdin', '-loglevel', 'error', '-y', '-i', str(src), *args,
                                '-pix_fmt', 'yuv420p', str(out)], check=True)
                sizes[name] = out.stat().st_size
            # CRF menor = mais bits gastos na mesma fonte
            self.assertLess(sizes['rapido'], sizes['qualidade'])
            self.assertLess(sizes['equilibrado'], sizes['entrega'])
            self.assertEqual(len(set(sizes.values())), 4)


if __name__ == '__main__':
    unittest.main()
