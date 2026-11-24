"""KI-10: dependência ausente tem que aparecer para o usuário, não falhar em silêncio."""
import tempfile
import unittest
from unittest import mock

from liveclips import deps, preflight
from liveclips.app import App


class Deps(unittest.TestCase):
    def test_all_present_reports_nothing_required(self):
        with mock.patch.object(deps, '_present', return_value=True):
            self.assertEqual(deps.missing(), [])

    def test_missing_opencv_has_clear_message_and_fix(self):
        with mock.patch.object(deps, '_present', side_effect=lambda m: m != 'cv2'):
            miss = deps.missing()
        self.assertEqual([d['id'] for d in miss], ['opencv'])
        self.assertTrue(miss[0]['required'])
        self.assertIn('opencv-contrib-python', miss[0]['message'])
        self.assertIn('capas', miss[0]['message'])
        self.assertIn('INSTALAR.bat', miss[0]['message'])

    def test_optional_missing_does_not_raise_a_warning_level(self):
        with mock.patch.object(deps, '_present', side_effect=lambda m: m != 'opentimelineio'):
            item = preflight.dependencies()
        self.assertEqual(item['level'], 'ok')
        self.assertIn('otio', item['detail'])

    def test_preflight_warns_when_required_missing(self):
        with mock.patch.object(deps, '_present', side_effect=lambda m: m != 'cv2'):
            item = preflight.dependencies()
        self.assertEqual(item['level'], 'aviso')
        self.assertEqual(item['id'], 'dependencias')

    def test_preflight_silent_when_everything_present(self):
        with mock.patch.object(deps, '_present', return_value=True):
            self.assertIsNone(preflight.dependencies())

    def test_state_exposes_missing_dependencies_for_the_banner(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(deps, '_present', side_effect=lambda m: m != 'yt_dlp'):
            state = App(root).state()
        self.assertEqual([d['id'] for d in state['dependencies']], ['yt_dlp'])


if __name__ == '__main__':
    unittest.main()
