import errno
import unittest

from liveclips.app import friendly_error


class Friendly(unittest.TestCase):
    def test_keyerror_is_explained(self):
        text = friendly_error(KeyError('name'))
        self.assertIn('name', text)
        self.assertNotIn("'name'", text.replace('(name)', ''))
        self.assertIn('Atualize', text)

    def test_permission_and_missing_and_full_disk(self):
        self.assertIn('negou', friendly_error(PermissionError(13, 'x', 'C:\\a.mp4')))
        self.assertIn('C:\\a.mp4', friendly_error(PermissionError(13, 'x', 'C:\\a.mp4')))
        self.assertIn('não encontrado', friendly_error(FileNotFoundError(2, 'x', 'D:\\b')))
        self.assertIn('disco está cheio', friendly_error(OSError(errno.ENOSPC, 'No space')))

    def test_plain_messages_pass_through(self):
        self.assertEqual(friendly_error(ValueError('Mensagem clara.')), 'Mensagem clara.')


if __name__ == '__main__':
    unittest.main()
