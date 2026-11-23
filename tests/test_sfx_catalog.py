import unittest

from liveclips import sfx, sfx_catalog as cat


class CatalogTests(unittest.TestCase):
    def test_every_synthesized_effect_has_function_and_license(self):
        self.assertEqual(set(sfx.EFFECTS), set(cat.BUILTIN))
        for item in cat.catalog():
            self.assertIn(item['function'], cat.FUNCTIONS)
            self.assertIn(item['intensity'], cat.INTENSITIES)
            self.assertEqual('livre_proprio', item['permission'])
            self.assertFalse(item['validated_by_ear'])           # nada foi ouvido por humano ainda

    def test_no_function_means_no_effect(self):
        self.assertIsNone(cat.choose(None)['effect'])
        self.assertIsNone(cat.choose('gargalhada')['effect'])

    def test_choice_by_function(self):
        self.assertEqual('boom', cat.choose('impacto', 'forte')['effect'])
        self.assertEqual('whoosh', cat.choose('transicao')['effect'])

    def test_extra_asset_without_permission_is_never_used(self):
        extra = [dict(id='meu', function='impacto', intensity='forte', permission='sem_permissao')]
        self.assertEqual('boom', cat.choose('impacto', 'forte', extra)['effect'])
        self.assertFalse(cat.usable(cat.catalog(extra)[-1]))

    def test_declared_license_asset_is_preferred_when_ear_validated(self):
        extra = [dict(id='meu', function='impacto', intensity='forte', permission='licenca_declarada', validated_by_ear=True)]
        self.assertEqual('meu', cat.choose('impacto', 'forte', extra)['effect'])

    def test_invalid_asset_is_ignored(self):
        self.assertEqual(len(cat.BUILTIN), len(cat.catalog([dict(id='x', function='???', permission='livre_proprio')])))

    def test_budget_and_speech(self):
        self.assertIsNone(cat.decide('impacto', budget_left=0)['effect'])
        loud = cat.decide('impacto')
        quiet = cat.decide('impacto', near_speech=True)
        self.assertGreater(loud['volume'], quiet['volume'])
        self.assertLessEqual(quiet['volume'], cat.MIX['sfx_max_over_voice'])


if __name__ == '__main__':
    unittest.main()
