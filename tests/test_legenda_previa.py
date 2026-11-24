"""A tabela de tamanhos da legenda ao vivo (ui/live.js) tem que ser a mesma do gerador da exportação (captions.CAPTION_STYLES)."""
import re
import unittest
from pathlib import Path

from liveclips import captions

LIVE = (Path(__file__).resolve().parent.parent / 'ui' / 'live.js').read_text(encoding='utf-8')


class LiveCaptionTable(unittest.TestCase):
    def test_size_offsets_and_caps_match_the_exporter(self):
        table = re.search(r'const CAP_SIZE=\{([^}]*)\}', LIVE).group(1)
        js = {m[0]: (int(m[1]), int(m[2])) for m in re.findall(r'(\w+):\[(-?\d+),(\d+)\]', table)}
        for name, spec in captions.CAPTION_STYLES.items():
            self.assertEqual(js.get(name), (spec['size'], spec.get('cap', 0)), name)
        self.assertEqual(set(js), set(captions.CAPTION_STYLES))

    def test_scale_constant_is_the_measured_libass_factor(self):
        self.assertRegex(LIVE, r'const CAP_SCALE=\.9;')


if __name__ == '__main__':
    unittest.main()
