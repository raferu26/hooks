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


import json
import random
import shutil
import subprocess
import tempfile

NODE = shutil.which('node')
CAPJS = Path(__file__).resolve().parent.parent / 'ui' / 'capgroups.js'
VOCAB = ('o', 'a', 'de', 'que', 'não', 'isso', 'aqui', 'agora', 'porque', 'ninguém', 'acredita', 'nisso', 'mas', 'Coringa', 'fez', 'novo', 'e',
         'foi', 'incrível', 'mesmo', 'eu', 'nunca', 'tinha', 'visto', 'nada', 'parecido', 'para', 'com', 'um', 'uma', 'também', 'então', 'tipo')


def fixture(seed, n=60):
    rnd = random.Random(seed); t = 0.3; words = []
    for _ in range(n):
        w = rnd.choice(VOCAB)
        if rnd.random() < .12: w += rnd.choice([',', '.', '?', '!', ';', ':', '…', '."', ')'])
        d = rnd.uniform(.15, .55); words.append(dict(start=round(t, 3), end=round(t + d, 3), text=w))
        t += d + (rnd.choice([0, 0, 0, .05, .2, .4, .8]))
    return words


def js_groups(cases):
    script = ("const C=require(%r);const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));"
              "console.log(JSON.stringify(cases.map(c=>{const [mw,mc]=C.capChunkFor(c.style);return C.capSmartGroups(c.words,mw,mc).map(g=>g.map(w=>w.start))})))" % str(CAPJS))
    out = subprocess.run([NODE, '-e', script], input=json.dumps(cases), capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@unittest.skipUnless(NODE, 'node ausente')
class ChunkParity(unittest.TestCase):
    """A legenda ao vivo tem que quebrar em blocos exatamente como a exportação (captions.smart_groups com os limites do estilo)."""

    def test_js_groups_equal_python_groups_for_every_style(self):
        cases = [dict(style=st, words=fixture(seed)) for st in captions.CAPTION_STYLES for seed in range(25)]
        got = js_groups(cases)
        for case, groups in zip(cases, got):
            spec = captions.CAPTION_STYLES[case['style']]
            want = [[w['start'] for w in g] for g in captions.smart_groups(case['words'], spec.get('max_words', 4), spec.get('max_chars', 26))]
            self.assertEqual(groups, want, case['style'])

    def test_chunk_limits_match_caption_styles(self):
        src = (CAPJS.parent / 'capgroups.js').read_text(encoding='utf-8')
        table = dict((m[0], (int(m[1]), int(m[2]))) for m in re.findall(r'(\w+):\[(\d+),(\d+)\]', re.search(r'const CAP_CHUNK=\{([^}]*)\}', src).group(1)))
        for name, spec in captions.CAPTION_STYLES.items():
            want = (spec.get('max_words', 4), spec.get('max_chars', 26))
            self.assertEqual(table.get(name, (4, 26)), want, name)

    def test_text_visible_at_each_instant_equals_the_exported_ass(self):
        """Compara, em muitos instantes, o texto do bloco visível (JS) com o evento ativo do ASS gerado pelo exportador."""
        for style in ('dynamic', 'impact', 'box', 'clean'):
            words = fixture(7, 80)
            segs = [dict(start=words[0]['start'], end=words[-1]['end'], text=' '.join(w['text'] for w in words),
                         words=[dict(start=w['start'], end=w['end'], word=w['text']) for w in words])]
            ass = captions.make_ass(segs, 0, words[-1]['end'] + 1, style=style, smart=True, keep_lines=False)
            events = []
            for line in ass.splitlines():
                if line.startswith('Dialogue:'):
                    f = line.split(',', 9); h, m, s = f[1].split(':'); a = int(h) * 3600 + int(m) * 60 + float(s)
                    h, m, s = f[2].split(':'); b = int(h) * 3600 + int(m) * 60 + float(s)
                    events.append((a, b, re.sub(r'\{[^}]*\}', '', f[9]).replace('\\N', ' ').strip()))
            mw, mc = captions.CAPTION_STYLES[style].get('max_words', 4), captions.CAPTION_STYLES[style].get('max_chars', 26)
            script = ("const C=require(%r);const d=JSON.parse(require('fs').readFileSync(0,'utf8'));const [mw,mc]=C.capChunkFor(d.style);const g=C.capSmartGroups(d.words,mw,mc);"
                      "console.log(JSON.stringify(d.times.map(t=>{const x=C.capGroupAt(g,t);return x?x.map(w=>w.text).join(' '):null})))" % str(CAPJS))
            times = [round(i * .137, 3) for i in range(int(words[-1]['end'] / .137))]
            seen = json.loads(subprocess.run([NODE, '-e', script], input=json.dumps(dict(style=style, words=words, times=times)), capture_output=True, text=True, check=True).stdout)
            bad = 0
            for t, js in zip(times, seen):
                act = [e for e in events if e[0] + .03 <= t < e[1] - .03]
                if act and js is not None and act[0][2].lower() != js.lower():
                    bad += 1
            self.assertEqual(bad, 0, f'{style}: {bad} instantes com texto diferente')


@unittest.skipUnless(NODE, 'node ausente')
class TitleParity(unittest.TestCase):
    def test_title_wrap_equals_textwrap(self):
        import textwrap
        rnd = random.Random(11); cases = []
        for _ in range(300):
            n = rnd.randint(1, 14); text = ' '.join(rnd.choice(VOCAB + ('supercalifragilisticoespialidoso', 'x')) for _ in range(n))
            cases.append(dict(text=text, width=rnd.choice((16, 22, 30))))
        script = ("const C=require(%r);const cs=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(JSON.stringify(cs.map(c=>C.capWrap(c.text,c.width,3))))" % str(CAPJS))
        got = json.loads(subprocess.run([NODE, '-e', script], input=json.dumps(cases), capture_output=True, text=True, check=True).stdout)
        for c, g in zip(cases, got):
            # o textwrap do Python 3.11 (o do Windows) deixa um espaço no fim da linha quando quebra uma palavra longa; o 3.13 não: o espaço final não muda o layout
            self.assertEqual(g, [x.rstrip() for x in textwrap.wrap(c['text'], width=c['width'])[:3]], c)

    def test_title_spec_matches_exporter(self):
        ass = captions.make_ass([], 0, 2, titles=[dict(start=0, end=2, text='x', style=k, position=p) for k, p in (('big', 'top'), ('top', 'center'), ('bar', 'bottom'))], captions=False)
        sizes = [int(l.split(',')[2]) for l in ass.splitlines() if l.startswith('Style: Titulo')]
        margins = [int(l.split(',')[-2]) for l in ass.splitlines() if l.startswith('Style: Titulo')]
        self.assertEqual(sizes, [66, 36, 50])
        self.assertEqual(margins, [170, 0, 430])
        src = CAPJS.read_text(encoding='utf-8')
        self.assertIn('big:{size:66,wrap:16,upper:true}', src); self.assertIn('top:{size:36,wrap:30,upper:false}', src); self.assertIn('bar:{size:50,wrap:22,upper:false}', src)
        self.assertIn('top:170,center:0,bottom:430', src)
