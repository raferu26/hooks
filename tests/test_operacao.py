import json
import sqlite3
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from liveclips import calibration, clockmap, recovery, replay, retention


class ClockTests(unittest.TestCase):
    def test_unknown_clock_declares_default_uncertainty_and_no_shift(self):
        c = clockmap.clock_for([dict(time=1)])
        self.assertEqual(('desconhecida', 0.0, 5.0), (c['source'], c['offset_s'], c['uncertainty_s']))

    def test_provider_latency_sets_uncertainty(self):
        msgs = [dict(time=i, wall=1000 + i, sent_ts=int((1000 + i - 2.0) * 1000)) for i in range(10)]
        c = clockmap.clock_for(msgs)
        self.assertEqual('latencia_do_provedor', c['source'])
        self.assertGreaterEqual(c['uncertainty_s'], 2.0)

    def test_saved_offset_is_applied_only_from_file(self):
        c = clockmap.clock_for([], dict(offset_s=-12.0, uncertainty_s=2))
        self.assertEqual(('arquivo', 2.0), (c['source'], c['uncertainty_s']))
        self.assertEqual(8.0, clockmap.apply([dict(time=20)], c)[0]['time'])
        self.assertEqual(20, clockmap.apply([dict(time=20)], clockmap.clock_for([]))[0]['time'])   # sem arquivo, nada se desloca

    def test_load_signals_carries_the_uncertainty(self):
        from liveclips.chat import load_signals
        with tempfile.TemporaryDirectory() as d:
            lines = [json.dumps(dict(time=10 + i * .2, user=f'u{i}', text='KKKKK', emotes=1)) for i in range(20)]
            (Path(d) / 'chat.jsonl').write_text('\n'.join(lines), encoding='utf-8')
            pts = load_signals(d, 60)
            self.assertTrue(pts)
            self.assertEqual(5.0, pts[0]['time_uncertainty_s'])


class CalibrationTests(unittest.TestCase):
    def test_few_cases_are_never_called_calibrated(self):
        s = calibration.status([(.9, 1)] * 10)
        self.assertEqual('nao_calibrado', s['estado'])

    def test_enough_heldout_cases_are_measured(self):
        pairs = [(.8, 1)] * 24 + [(.8, 0)] * 6 + [(.2, 0)] * 24 + [(.2, 1)] * 6
        s = calibration.status(pairs)
        self.assertEqual('calibrado', s['estado'])
        self.assertLess(s['ece'], .1)
        bad = calibration.status([(.9, 0)] * 40)
        self.assertEqual('descalibrado', bad['estado'])

    def test_brier(self):
        self.assertEqual(0.0, calibration.brier([(1, 1), (0, 0)]))
        self.assertIsNone(calibration.brier([]))


class ReplayTests(unittest.TestCase):
    def good(self, transcript, signals):
        return [dict(start=p['time'] - 3, end=p['time'] + 3) for p in signals.get('behavior', [])]

    def peeking(self, transcript, signals):
        total = len(signals.get('behavior', []))     # usa a contagem global: olha o futuro
        return [dict(start=p['time'] - 3, end=p['time'] + 3 + (1 if total > 2 else 0)) for p in signals.get('behavior', [])]

    def test_causal_function_passes_and_peeking_function_is_caught(self):
        sig = dict(behavior=[dict(time=10), dict(time=20), dict(time=40)])
        self.assertTrue(replay.no_lookahead(self.good, [], sig, 25)['ok'])
        self.assertFalse(replay.no_lookahead(self.peeking, [], sig, 25)['ok'])

    def test_ablation_reports_each_family(self):
        sig = dict(behavior=[dict(time=10)], audio=[dict(time=5)])
        out = replay.ablate(self.good, [], sig, ['behavior', 'audio'])
        self.assertEqual(-1, out['sem']['behavior']['delta'])
        self.assertEqual(0, out['sem']['audio']['delta'])

    def test_evaluate_needs_cases_and_counts_misses(self):
        self.assertEqual('sem_casos', replay.evaluate([dict(start=0, end=10)], [])['estado'])
        cases = [dict(case_kind='missed', human_intervals=[[50, 60]]), dict(case_kind='approved', human_intervals=[[0, 10]]),
                 dict(case_kind='rejected', human_intervals=[[100, 110]])]
        r = replay.evaluate([dict(start=0, end=10), dict(start=100, end=110)], cases)
        self.assertEqual((.5, 1, 1), (r['cobertura'], r['perdidos'], r['sobre_rejeitados']))


class RetentionRecoveryTests(unittest.TestCase):
    def test_retention_is_a_dry_run_and_protects_active_cuts(self):
        from liveclips.store import Store
        from tests.helpers import setup_session, candidate
        import os
        with tempfile.TemporaryDirectory() as d:
            store = Store(d)
            streamer, sid, _ = setup_session(store)
            item, _ = candidate(store, sid)
            old = time.time() - 90 * 86400
            for seg in store.rows('SELECT path FROM segments WHERE session=?', (sid,)):
                os.utime(seg['path'], (old, old))
            before = [Path(r['path']).is_file() for r in store.rows('SELECT path FROM segments')]
            out = retention.plan(store, keep_days=30)
            self.assertTrue(out['simulacao'] and not out['apagou_algo'])
            self.assertEqual(before, [Path(r['path']).is_file() for r in store.rows('SELECT path FROM segments')])
            listed = {i['path'] for i in out['itens']}
            used = {str(Path(p['path'])) for p in item['parts']}
            self.assertFalse(listed & used)

    def test_verify_restore_reports_missing_media_without_touching_the_root(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'liveclips_v8.sqlite3'
            con = sqlite3.connect(db)
            con.executescript("CREATE TABLE segments(path TEXT); CREATE TABLE sessions(id TEXT); CREATE TABLE streamers(id TEXT); CREATE TABLE candidates(id TEXT);")
            con.execute("INSERT INTO segments VALUES('/nao/existe.ts')")
            con.commit(); con.close()
            arc = Path(d) / 'b.zip'
            with zipfile.ZipFile(arc, 'w') as z:
                z.write(db, 'liveclips_v8.sqlite3')
                z.writestr('manifesto.json', json.dumps(dict(schema=recovery.SCHEMA)))
            r = recovery.verify_restore(arc)
            self.assertEqual((1, 0), (r['midias_referenciadas'], r['midias_presentes']))
            self.assertEqual(['/nao/existe.ts'], r['midias_ausentes'])


if __name__ == '__main__':
    unittest.main()
