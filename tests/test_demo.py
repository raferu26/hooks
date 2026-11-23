import tempfile
import unittest
from pathlib import Path

from liveclips import demo, media
from liveclips.engine import Engine
from liveclips.store import Store


class Demo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_creates_streamer_session_and_one_pending_clip_once(self):
        first = demo.create(self.store)
        self.assertTrue(first['created'])
        again = demo.create(self.store)
        self.assertFalse(again['created'])
        self.assertEqual(first['streamer'], again['streamer'])
        clips = self.store.rows('SELECT status,data FROM candidates WHERE streamer=?', (first['streamer'],))
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0]['status'], 'pending')
        self.assertEqual(len(self.store.rows('SELECT 1 FROM segments WHERE session=?', (first['session'],))), 1)

    def test_demo_clip_can_be_approved_and_exported_without_whisper(self):
        made = demo.create(self.store)
        item = self.store.rows('SELECT id,version,start,end,parts FROM candidates WHERE streamer=?', (made['streamer'],))[0]
        import json
        self.store.review(item['id'], item['version'], item['start'], item['end'], json.loads(item['parts']), 'approve')
        engine = Engine(self.store)
        engine.do_render(item['id'], False)
        done = self.store.candidate(item['id'])
        self.assertEqual(done['status'], 'done', done.get('error'))
        self.assertTrue(Path(done['export_path']).is_dir() or Path(done['export_path']).is_file())


if __name__ == '__main__':
    unittest.main()
