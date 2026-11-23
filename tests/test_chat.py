import tempfile
import unittest

from liveclips.chat import reaction_points,twitch_channel
from liveclips.store import Store


class ChatTests(unittest.TestCase):
    def test_twitch_channel_is_strict(self):
        self.assertEqual(twitch_channel('https://www.twitch.tv/coringa'),'coringa')
        self.assertIsNone(twitch_channel('https://example.com/coringa'))

    def test_reaction_points_require_multiple_people_or_reactions(self):
        messages=[{'time':10,'user':f'u{i}','text':'kkkkkk','emotes':1} for i in range(8)]
        points=reaction_points(messages,30)
        self.assertTrue(points)
        self.assertGreaterEqual(points[0]['users'],8)
        self.assertGreater(points[0]['reaction_types']['risada'],0)

    def test_learning_waits_for_four_decisions(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            streamer=store.create_streamer('Teste')
            self.assertEqual(store.ranking_preferences(streamer),{})


if __name__=='__main__':unittest.main()
