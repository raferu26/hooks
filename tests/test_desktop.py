"""Hook’s como aplicativo: lançador, janela, encerrar e atalho. A janela real (Edge/Chrome) e o Windows não rodam aqui:
o que se testa é a lógica, com servidor de verdade e processos de mentira."""
import json
import tempfile
import threading
import unittest
from pathlib import Path

from liveclips import buildinfo, desktop
from liveclips.app import App, server


class FakeProc:
    def __init__(self, polls=(None, None, 0)):
        self.polls = list(polls)
        self.terminated = False

    def poll(self):
        return self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]

    def terminate(self):
        self.terminated = True
        self.polls = [1]


class Running:
    """Hook’s de verdade (App + servidor HTTP) em porta livre, descrito em servidor.json como o programa faz."""
    def __init__(self, tc):
        self.tmp = tempfile.TemporaryDirectory()
        tc.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = App(self.root, worker=False)
        tc.addCleanup(self.app.close)
        self.http = server(self.app, 0)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        tc.addCleanup(self.http.server_close)
        tc.addCleanup(self.http.shutdown)
        self.quits = 0

        def quit_():
            self.quits += 1
        self.app.quit_callback = quit_
        (self.root / desktop.DISCOVERY).write_text(json.dumps(dict(pid=1, port=self.http.server_port, token=self.app.token, **buildinfo.identity())), encoding='utf-8')

    @property
    def info(self):
        return desktop.read_discovery(self.root)


class ServerSideTests(unittest.TestCase):
    def test_activity_is_in_state_and_idle_by_default(self):
        r = Running(self)
        act = desktop.activity(r.info)
        self.assertEqual(act, dict(capturas=0, analisando=False, exportando=0))
        self.assertTrue(desktop.is_idle(act))

    def test_activity_not_idle_when_anything_is_running(self):
        for act in (dict(capturas=1, analisando=False, exportando=0), dict(capturas=0, analisando=True, exportando=0),
                    dict(capturas=0, analisando=False, exportando=2)):
            self.assertFalse(desktop.is_idle(act))
        self.assertFalse(desktop.is_idle(None))

    def test_quit_calls_callback_and_requires_token(self):
        r = Running(self)
        self.assertTrue(desktop.request_quit(r.info))
        self.assertEqual(r.quits, 1)
        bad = dict(r.info, token='errado')
        self.assertFalse(desktop.request_quit(bad))
        self.assertEqual(r.quits, 1)

    def test_quit_without_callback_is_refused_with_explanation(self):
        r = Running(self)
        r.app.quit_callback = None
        with self.assertRaises(RuntimeError):
            r.app.action('/api/app/quit', {})

    def test_alive_false_for_stale_file(self):
        r = Running(self)
        self.assertTrue(desktop.alive(r.info))
        self.assertFalse(desktop.alive(dict(port=1, token='x')))
        self.assertFalse(desktop.alive(None))

    def test_read_discovery_ignores_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(desktop.read_discovery(root))
            (root / desktop.DISCOVERY).write_text('{quebrado', encoding='utf-8')
            self.assertIsNone(desktop.read_discovery(root))


class HelperTests(unittest.TestCase):
    def test_server_uses_python_exe_not_pythonw(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'python.exe').write_text('')
            (Path(tmp) / 'pythonw.exe').write_text('')
            self.assertEqual(desktop.server_python(Path(tmp) / 'pythonw.exe').name, 'python.exe')
            self.assertEqual(desktop.server_python(Path(tmp) / 'python.exe').name, 'python.exe')

    def test_start_server_command_logs_and_path(self):
        seen = {}

        def fake(cmd, **kw):
            seen['cmd'] = cmd
            seen['kw'] = kw
            return FakeProc()
        with tempfile.TemporaryDirectory() as tmp:
            desktop.start_server(Path(tmp), popen=fake, executable=Path(tmp) / 'python')
            self.assertIn('liveclips', seen['cmd'])
            self.assertIn('--no-browser', seen['cmd'])
            self.assertTrue(seen['kw']['env']['PATH'].startswith(str(Path(tmp))))
            self.assertTrue((Path(tmp) / 'logs' / desktop.LOG).exists())

    def test_find_browser_prefers_edge_then_chrome(self):
        env = {'ProgramFiles(x86)': r'C:\PF86', 'ProgramFiles': r'C:\PF'}
        import os

        def build(exists_set):
            return desktop.find_browser(env, exists=lambda p: p in exists_set, which=lambda n: None)
        # os.path.join usa o separador do sistema; montamos os caminhos do mesmo jeito
        e = os.path.join(r'C:\PF86', r'Microsoft\Edge\Application\msedge.exe')
        c = os.path.join(r'C:\PF', r'Google\Chrome\Application\chrome.exe')
        self.assertEqual(build({e, c}), e)
        self.assertEqual(build({c}), c)
        self.assertIsNone(build(set()))

    def test_window_command_is_app_mode_with_own_profile(self):
        cmd = desktop.window_command('edge.exe', 'http://127.0.0.1:8765', Path('/x/janela'))
        self.assertIn('--app=http://127.0.0.1:8765', cmd)
        self.assertTrue(any(a.startswith('--user-data-dir=') for a in cmd))

    def test_lock_is_exclusive_and_releasable(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = desktop.Lock(Path(tmp) / 'l'), desktop.Lock(Path(tmp) / 'l')
            self.assertTrue(a.acquire())
            self.assertFalse(b.acquire())
            a.release()
            self.assertTrue(b.acquire())
            b.release()

    def test_wait_ready_fails_when_process_dies_and_no_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(desktop.StartError):
                desktop.wait_ready(Path(tmp), FakeProc([3]), timeout=5, sleep=lambda s: None)

    def test_wait_ready_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = [0.0]

            def now():
                t[0] += 10
                return t[0]
            with self.assertRaises(desktop.StartError):
                desktop.wait_ready(Path(tmp), None, timeout=30, sleep=lambda s: None, now=now)

    def test_watch_closes_window_when_server_goes_away(self):
        w = FakeProc([None])
        t = [0.0]

        def now():
            t[0] += 5
            return t[0]
        res = desktop.watch(w, {}, sleep=lambda s: None, alive_fn=lambda i: False, now=now)
        self.assertEqual(res, 'servidor_encerrou')
        self.assertTrue(w.terminated)

    def test_watch_returns_when_window_closes(self):
        res = desktop.watch(FakeProc([None, 0]), {}, sleep=lambda s: None, alive_fn=lambda i: True)
        self.assertEqual(res, 'janela_fechou')


class LaunchTests(unittest.TestCase):
    def run_launch(self, r, popen_calls, shown, browser='edge.exe', **kw):
        def popen(cmd, **k):
            popen_calls.append(cmd)
            return FakeProc()
        kw.setdefault('min_window_s', 0)
        return desktop.launch(r.root, popen=popen, show=shown.append, sleep=lambda s: None,
                              browser_finder=lambda: browser, open_default=lambda u: shown.append('DEFAULT:' + u), **kw)

    def test_idle_after_window_closes_quits_the_server(self):
        r = Running(self)
        calls, shown = [], []
        self.assertEqual(self.run_launch(r, calls, shown), 0)
        self.assertEqual(len(calls), 1)                      # só abriu a janela; servidor já estava de pé
        self.assertTrue(calls[0][1].startswith('--app=http://127.0.0.1:'))
        self.assertEqual(r.quits, 1)
        self.assertEqual(shown, [])

    def test_busy_after_window_closes_keeps_server_and_warns(self):
        r = Running(self)
        r.app.activity = lambda: dict(capturas=1, analisando=True, exportando=0)
        calls, shown = [], []
        self.run_launch(r, calls, shown)
        self.assertEqual(r.quits, 0)
        self.assertEqual(len(shown), 1)
        self.assertIn('gravando 1 live', shown[0])
        self.assertIn('analisando', shown[0])

    def test_window_that_vanishes_instantly_never_quits_the_server(self):
        r = Running(self)
        calls, shown = [], []
        self.run_launch(r, calls, shown, min_window_s=8.0)
        self.assertEqual(r.quits, 0)
        self.assertIn('rápido demais', shown[0])

    def test_unknown_activity_never_kills_the_server(self):
        r = Running(self)

        def boom():
            raise RuntimeError('x')
        r.app.activity = boom
        calls, shown = [], []
        self.run_launch(r, calls, shown)
        self.assertEqual(r.quits, 0)

    def test_second_shortcut_only_opens_window(self):
        r = Running(self)
        other = desktop.Lock(r.root / desktop.WATCH_LOCK)
        self.assertTrue(other.acquire())
        self.addCleanup(other.release)
        calls, shown = [], []
        self.assertEqual(self.run_launch(r, calls, shown), 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r.quits, 0)

    def test_without_edge_or_chrome_opens_default_browser(self):
        r = Running(self)
        calls, shown = [], []
        self.run_launch(r, calls, shown, browser=None)
        self.assertEqual(calls, [])
        self.assertTrue(shown[0].startswith('DEFAULT:http://127.0.0.1:'))
        self.assertEqual(r.quits, 0)

    def test_starts_server_when_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            started = []
            real = Running(self)

            def popen(cmd, **kw):
                if '--no-browser' in cmd:
                    started.append(cmd)
                    (root / desktop.DISCOVERY).write_text(json.dumps(dict(port=real.http.server_port, token=real.app.token, **buildinfo.identity())), encoding='utf-8')
                    return FakeProc([None])
                return FakeProc()
            shown = []
            desktop.launch(root, popen=popen, show=shown.append, sleep=lambda s: None, browser_finder=lambda: 'edge.exe',
                           open_default=lambda u: None, min_window_s=0)
            self.assertEqual(len(started), 1)


class OtherInstallTests(unittest.TestCase):
    """Causa-raiz do relato "os layouts não aparecem": o atalho da versão NOVA abria o servidor da versão ANTERIOR, que continuava
    rodando sobre a mesma pasta de dados. O lançador agora confere versão, commit e pasta de instalação."""

    def old_server(self, **identity):
        r = Running(self)
        (r.root / desktop.DISCOVERY).write_text(json.dumps(dict(pid=1, port=r.http.server_port, token=r.app.token, **identity)), encoding='utf-8')
        return r

    def launch(self, r, ask, shown, calls):
        def popen(cmd, **k):
            calls.append(cmd)
            if '--no-browser' in cmd:   # "o novo servidor sobe": reaproveita o servidor de teste, agora com a identidade desta instalação
                (r.root / desktop.DISCOVERY).write_text(json.dumps(dict(pid=2, port=r.http.server_port, token=r.app.token, **buildinfo.identity())), encoding='utf-8')
                return FakeProc([None])
            return FakeProc()
        return desktop.launch(r.root, popen=popen, show=shown.append, sleep=lambda s: None, browser_finder=lambda: 'edge.exe',
                              open_default=lambda u: None, min_window_s=0, ask=ask)

    def test_same_build_is_reused(self):
        mine = buildinfo.identity()
        self.assertTrue(desktop.same_build(mine, mine))
        for key in ('versao', 'commit', 'install'):
            self.assertFalse(desktop.same_build(dict(mine, **{key: 'outra'}), mine), key)
        self.assertFalse(desktop.same_build(dict(versao=mine['versao']), mine))      # servidor.json de versão antiga, sem identidade
        self.assertFalse(desktop.same_build(None, mine))

    def test_install_path_comparison_ignores_case_and_slashes_on_windows_style_paths(self):
        a = dict(versao='1', commit='x', install='C:\\Hooks2\\app')
        self.assertTrue(desktop.same_build(a, dict(a)))

    def test_old_install_idle_and_user_agrees_is_replaced(self):
        r = self.old_server(versao='0.20.0-beta.1')
        shown, calls, questions = [], [], []
        stop = lambda: None
        r.app.quit_callback = lambda: setattr(r, 'old_stopped', True)
        orig_alive = desktop.alive
        desktop.alive = lambda info: False if getattr(r, 'old_stopped', False) and info.get('pid') == 1 else orig_alive(info)
        self.addCleanup(setattr, desktop, 'alive', orig_alive)
        rc = self.launch(r, lambda t: questions.append(t) or True, shown, calls)
        self.assertEqual(rc, 0)
        self.assertEqual(len(questions), 1)
        self.assertIn('0.20.0-beta.1', questions[0])
        self.assertIn('Nenhum projeto', questions[0])
        self.assertTrue(getattr(r, 'old_stopped', False))
        self.assertTrue(any('--no-browser' in c for c in calls))       # subiu o servidor DESTA instalação antes de abrir a janela

    def test_user_declines_nothing_changes_and_no_window_opens_on_the_wrong_version(self):
        r = self.old_server(versao='0.20.0-beta.1')
        shown, calls = [], []
        self.assertEqual(self.launch(r, lambda t: False, shown, calls), 1)
        self.assertEqual(calls, [])
        self.assertEqual(r.quits, 0)

    def test_busy_old_install_is_never_stopped(self):
        r = self.old_server(versao='0.20.0-beta.1')
        r.app.activity = lambda: dict(capturas=1, analisando=False, exportando=0)
        shown, calls, questions = [], [], []
        self.assertEqual(self.launch(r, lambda t: questions.append(t) or True, shown, calls), 1)
        self.assertEqual(questions, [])
        self.assertEqual((calls, r.quits), ([], 0))
        self.assertIn('ocupada', shown[0])


class FilesTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).resolve().parent.parent

    def test_ui_has_quit_button_wired(self):
        html = (self.base / 'liveclips' / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="quitApp"', html)
        self.assertIn('/api/app/quit', html)

    def test_shortcut_script_points_to_pythonw_module_and_icon(self):
        ps = (self.base / 'CRIAR_ATALHO.ps1').read_text(encoding='utf-8')
        self.assertIn('pythonw.exe', ps)
        self.assertIn('-m liveclips.desktop', ps)
        self.assertIn('hooks.ico', ps)
        self.assertIn('CRIAR_ATALHO.ps1', (self.base / 'CRIAR_ATALHO.bat').read_text(encoding='utf-8', errors='ignore'))
        self.assertTrue((self.base / 'assets' / 'hooks.ico').is_file())

    def test_installer_creates_the_shortcut(self):
        self.assertIn('CRIAR_ATALHO.bat', (self.base / 'INSTALAR.bat').read_text(encoding='utf-8', errors='ignore'))


if __name__ == '__main__':
    unittest.main()
