import unittest

from liveclips import layout_policy as lp


def ev(t, kind='acao', conf=.8, dur=3.0):
    return dict(time=t, kind=kind, confidence=conf, dur=dur)


class ProfileTests(unittest.TestCase):
    def test_normalize_and_bounds(self):
        self.assertEqual([.5, .25, .25, .5], lp.normalize_rect((960, 270, 480, 540), 1920, 1080))
        with self.assertRaises(ValueError):
            lp.normalize_rect((1800, 0, 400, 100), 1920, 1080)
        with self.assertRaises(ValueError):
            lp.normalize_rect((0, 0, 0, 10), 1920, 1080)

    def test_profile_scales_with_resolution(self):
        record = lp.profile_region([.5, .25, .25, .5], (1920, 1080), face_rect=[.2, .1, .5, .6])
        a, b = lp.to_pixels(record, 1280, 720), lp.to_pixels(record, 1920, 1080)
        self.assertAlmostEqual(a['aspect'], b['aspect'], places=2)
        self.assertEqual((640, 180), (a['camera']['x'], a['camera']['y']))
        self.assertEqual((960, 270), (b['camera']['x'], b['camera']['y']))
        self.assertIsNotNone(b['face'])

    def test_profile_rejects_pixel_coordinates(self):
        with self.assertRaises(ValueError):
            lp.profile_region([960, 270, 480, 540], (1920, 1080))

    def test_protected_hits(self):
        face = dict(name='rosto', x=100, y=100, w=100, h=100)
        self.assertEqual(['rosto'], lp.protected_hits(dict(x=150, y=150, w=100, h=100), [face]))
        self.assertEqual([], lp.protected_hits(dict(x=400, y=400, w=100, h=100), [face]))


class LayoutTests(unittest.TestCase):
    def covered(self, segments, duration):
        self.assertEqual(0.0, segments[0]['start'])
        self.assertEqual(duration, segments[-1]['end'])
        for a, b in zip(segments, segments[1:]):
            self.assertAlmostEqual(a['end'], b['start'], places=3)

    def test_no_events_stays_base(self):
        seg = lp.choose_layouts([], 30)
        self.assertEqual([lp.BASE], [s['layout'] for s in seg])

    def test_low_confidence_ignored(self):
        self.assertEqual([lp.BASE], [s['layout'] for s in lp.choose_layouts([ev(5, conf=.3)], 30)])

    def test_action_switches_and_returns(self):
        seg = lp.choose_layouts([ev(10)], 30)
        self.covered(seg, 30)
        self.assertEqual([lp.BASE, lp.ACTION_LAYOUT, lp.BASE], [s['layout'] for s in seg])

    def test_minimum_dwell(self):
        for s in lp.choose_layouts([ev(5), ev(15, 'reacao')], 40):
            if s['layout'] != lp.BASE:
                self.assertGreaterEqual(s['end'] - s['start'], lp.MIN_DWELL - .01)

    def test_switch_limit_per_window(self):
        events = [ev(t, kind='acao' if i % 2 else 'reacao', dur=2.0) for i, t in enumerate(range(2, 20, 3))]
        seg = lp.choose_layouts(events, 40)
        non_base = [s for s in seg if s['layout'] != lp.BASE]
        for s in non_base:
            self.assertLessEqual(len([x for x in non_base if 0 <= x['start'] - s['start'] < 10]), lp.MAX_SWITCHES_PER_10S)

    def test_unknown_kind_and_bad_events_ignored(self):
        seg = lp.choose_layouts([dict(time=3, kind='festa', confidence=.9), dict(kind='acao'), dict(time='x', confidence=.9)], 20)
        self.assertEqual([lp.BASE], [s['layout'] for s in seg])

    def test_to_plan_events(self):
        out = lp.to_plan_events(lp.choose_layouts([ev(10)], 30), lambda s: int(s * 90000))
        self.assertTrue(all(isinstance(e['start'], int) for e in out))


class TrackTests(unittest.TestCase):
    def points(self, xs, conf=1.0, dt=.1):
        return [dict(time=i * dt, x=x, y=.5, confidence=conf) for i, x in enumerate(xs)]

    def test_speed_and_accel_limited(self):
        track = lp.smooth_track(self.points([.1] * 3 + [.9] * 20), max_speed=.35, max_accel=1.2)
        steps = [abs(b['x'] - a['x']) / .1 for a, b in zip(track, track[1:])]
        self.assertLessEqual(max(steps), .35 + 1e-6)
        self.assertLess(track[4]['x'], .9)               # não pula direto
        self.assertAlmostEqual(.9, track[-1]['x'], delta=.15)

    def test_tolerance_ignores_jitter(self):
        track = lp.smooth_track(self.points([.5, .51, .49, .505, .495]))
        self.assertLess(lp.max_step(track), .02)

    def test_scene_cut_resets_position(self):
        pts = self.points([.1] * 5 + [.9] * 5)
        track = lp.smooth_track(pts, scene_cuts=[.5])
        self.assertAlmostEqual(.9, track[5]['x'], places=3)

    def test_low_confidence_freezes_then_falls_back(self):
        pts = self.points([.2] * 3, dt=.1) + [dict(time=.3 + i * .25, x=.9, y=.5, confidence=.1) for i in range(1, 8)]
        track = lp.smooth_track(pts, fallback=(.5, .5))
        states = [t['state'] for t in track]
        self.assertIn('congelado', states)
        self.assertEqual('fallback', states[-1])
        self.assertEqual((.5, .5), (track[-1]['x'], track[-1]['y']))


if __name__ == '__main__':
    unittest.main()
