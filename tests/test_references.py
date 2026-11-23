import tempfile
import unittest

from liveclips import references as refs
from liveclips.memory import Memory


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def ref(**kw):
    base = dict(url='https://example.com/v/1', platform='tiktok', niche='fps', region='BR', language='pt', observed_at=1_799_999_000.0, kind='hipotese',
                structure='gancho de 2 s, jogada, reação', inference_limits='3 vídeos vistos; sem dados de alcance', techniques=['zoom', 'rastro_neon'])
    base.update(kw)
    return base


class ValidationTests(unittest.TestCase):
    def test_required_and_url(self):
        self.assertEqual([], refs.validate(ref(), now=1_800_000_000))
        self.assertTrue(refs.validate(ref(url='ftp://x')))
        self.assertIn('falta inference_limits', refs.validate(ref(inference_limits='')))
        self.assertIn('tipo desconhecido', refs.validate(ref(kind='viral')))

    def test_observed_frequency_requires_seen(self):
        self.assertTrue(refs.validate(ref(kind='frequencia_observada')))
        self.assertEqual([], refs.validate(ref(kind='frequencia_observada', seen=True), now=1_800_000_000))

    def test_future_observation_rejected(self):
        self.assertTrue(refs.validate(ref(observed_at=9_999_999_999), now=1_800_000_000))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.mem = Memory(self.tmp.name, clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_sets_expiry_and_not_representative(self):
        record = refs.add(self.mem, ref())
        self.assertAlmostEqual(self.clock.now + 30 * 86400, record['valid_until'], delta=5)
        self.assertFalse(record['body']['representativa'])
        found = refs.add(self.mem, ref(url='https://example.com/v/2', foundation=True))
        self.assertAlmostEqual(self.clock.now + 180 * 86400, found['valid_until'], delta=5)

    def test_invalid_reference_not_stored(self):
        with self.assertRaises(refs.ReferenceError_):
            refs.add(self.mem, ref(url=''))
        self.assertEqual([], refs.query(self.mem))

    def test_query_filters_and_expiry(self):
        refs.add(self.mem, ref())
        refs.add(self.mem, ref(url='https://example.com/v/3', niche='irl', platform='reels'))
        self.assertEqual(1, len(refs.query(self.mem, niche='fps')))
        self.assertEqual(1, len(refs.query(self.mem, platform='reels')))
        self.assertEqual(2, len(refs.query(self.mem)))
        self.clock.now += 31 * 86400
        self.assertEqual([], refs.query(self.mem))

    def test_suggestions_respect_capabilities(self):
        refs.add(self.mem, ref())
        out = refs.usable_suggestions(refs.query(self.mem))
        self.assertEqual(['punch_in'], out[0]['aplicar'])
        self.assertEqual(['rastro_neon'], out[0]['nao_aplicavel_hoje'])
        self.assertIn('não copiar', out[0]['ativos_da_referencia'])

    def test_cycle_plan_bounds_and_totals(self):
        plan = refs.cycle_plan(['fps', 'irl'], ['tiktok', 'reels'], size=100)
        self.assertEqual(50, plan['total'])
        self.assertEqual(plan['total'] - plan['reservado_contraexemplos_e_saturacao'], sum(q['amostras'] for q in plan['cotas']))
        self.assertEqual(30, refs.cycle_plan(['fps'], ['tiktok'], size=5)['total'])
        with self.assertRaises(refs.ReferenceError_):
            refs.cycle_plan([], ['tiktok'])


if __name__ == '__main__':
    unittest.main()
