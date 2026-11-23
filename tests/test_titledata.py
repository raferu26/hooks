import unittest

from liveclips import titledata
from liveclips.store import DEFAULT_PROFILE, profile_checked


class TitleData(unittest.TestCase):
    def test_fills_fields(self):
        text = titledata.render('{streamer} · {rotulo}', dict(streamer='Coringa', rotulo='Clutch 1v3'))
        self.assertEqual(text, 'Coringa · Clutch 1v3')

    def test_missing_field_drops_its_separator(self):
        self.assertEqual(titledata.render('{rotulo} - {streamer}', dict(streamer='Coringa')), 'Coringa')
        self.assertEqual(titledata.render('{streamer} | {rotulo}', dict(streamer='Coringa')), 'Coringa')
        self.assertEqual(titledata.render('{rotulo}', {}), '')

    def test_unknown_field_and_loose_braces_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Campo desconhecido'):
            titledata.validate('{preco}')
        with self.assertRaises(ValueError):
            titledata.validate('abc {')
        with self.assertRaises(ValueError):
            titledata.validate('x' * 100)

    def test_long_title_is_cut(self):
        out = titledata.render('{rotulo}', dict(rotulo='palavra ' * 30))
        self.assertLessEqual(len(out), titledata.MAX_TITLE)
        self.assertTrue(out.endswith('…'))

    def test_values_use_marker_label_only(self):
        values = titledata.values_for(dict(data=dict(markers=[dict(time=5, label='Pedido do chat')])), 'Coringa', 'live', 3)
        self.assertEqual(values['rotulo'], 'Pedido do chat'); self.assertEqual(values['numero'], 'Parte 3')
        self.assertEqual(titledata.values_for(dict(data={}), 'x')['rotulo'], '')

    def test_profile_validates_template(self):
        self.assertEqual(profile_checked(dict(DEFAULT_PROFILE, title_template='{rotulo}'))['title_template'], '{rotulo}')
        with self.assertRaises(ValueError):
            profile_checked(dict(DEFAULT_PROFILE, title_template='{inventado}'))

    def test_title_entry_is_short_and_bounded(self):
        self.assertEqual(titledata.title_entry('x', 2.0)['end'], 2.0)
        self.assertEqual(titledata.title_entry('x', 60)['end'], 3.5)


if __name__ == '__main__':
    unittest.main()
