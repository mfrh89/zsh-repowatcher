"""Integration tests against temporary local Git remotes; no network required."""
import os
import pty
import select
import time
from pathlib import Path
import subprocess
import tempfile
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / 'zsh-repowatcher.plugin.zsh'

class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.base), GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL='/dev/null', XDG_CONFIG_HOME=str(self.base / '.config'), REPOWATCHER_CONFIG=str(self.base / '.config/repowatcher/config.zsh'), REPOWATCHER_CACHE_DIR=str(self.base / 'cache'),
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
        self.remote = self.base / 'remote.git'
        self.seed = self.base / 'seed'
        self.repo = self.base / 'working tree'
        self.git(self.base, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.git(self.base, 'clone', str(self.remote), str(self.seed))
        self.commit(self.seed, 'initial')
        self.git(self.seed, 'push', '-u', 'origin', 'main')
        self.git(self.base, 'clone', str(self.remote), str(self.repo))
        self.initial = self.git(self.repo, 'rev-parse', 'HEAD')

    def git(self, cwd, *args):
        return subprocess.check_output(['git', *args], cwd=cwd, env=self.env,
                                       stderr=subprocess.DEVNULL, text=True).strip()

    def commit(self, repo, name):
        (repo / name).write_text(name)
        self.git(repo, 'add', name)
        self.git(repo, 'commit', '-m', name)

    def incoming(self):
        self.commit(self.seed, 'incoming')
        self.git(self.seed, 'push')

    def shell(self, script, ok=True, cwd=None):
        result = subprocess.run(['zsh', '-f', '-c', 'source "$1"; ' + script,
                                 'test', str(PLUGIN)], cwd=cwd or self.repo,
                                env=self.env, capture_output=True, text=True, timeout=20)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_fetch_does_not_change_checkout(self):
        self.incoming()
        self.shell('repowatcher fetch; repowatcher status')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)
        self.assertNotEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)

    def test_pull_fast_forwards(self):
        self.incoming()
        self.shell('repowatcher pull')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.git(self.seed, 'rev-parse', 'HEAD'))

    def test_dirty_tracked_and_untracked_are_preserved(self):
        self.incoming()
        for filename in ['initial', 'untracked']:
            with self.subTest(filename=filename):
                (self.repo / filename).write_text('local')
                self.assertNotEqual(self.shell('repowatcher pull', ok=False).returncode, 0)
                self.assertEqual((self.repo / filename).read_text(), 'local')
                self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)
                if filename == 'initial':
                    self.git(self.repo, 'restore', filename)

    def test_divergence_preserves_local_commit(self):
        self.incoming()
        self.commit(self.repo, 'local')
        head = self.git(self.repo, 'rev-parse', 'HEAD')
        self.assertNotEqual(self.shell('repowatcher pull', ok=False).returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), head)

    def test_detached_head_is_skipped(self):
        self.incoming()
        self.git(self.repo, 'checkout', '--detach')
        self.assertNotEqual(self.shell('repowatcher pull', ok=False).returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_operation_in_progress_is_skipped(self):
        self.incoming()
        (self.repo / '.git' / 'CHERRY_PICK_HEAD').write_text(self.initial)
        self.assertNotEqual(self.shell('repowatcher pull', ok=False).returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_fetch_failure_prevents_pull(self):
        self.incoming()
        self.git(self.repo, 'fetch')
        self.git(self.repo, 'remote', 'set-url', 'origin', str(self.base / 'missing'))
        self.assertNotEqual(self.shell('repowatcher pull', ok=False).returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_local_settings_override_environment(self):
        self.git(self.repo, 'config', '--local', 'repowatcher.mode', 'notify')
        self.assertIn('mode=notify', self.shell('REPOWATCHER_MODE=auto; repowatcher status').stdout)

    def test_off_and_fetch_false_do_not_fetch(self):
        self.incoming()
        self.shell('REPOWATCHER_MODE=off; _repowatcher_prompt; wait')
        self.shell('REPOWATCHER_FETCH=false; _repowatcher_prompt; wait')
        self.assertEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)

    def test_notify_reports_without_mutating(self):
        self.incoming()
        result = self.shell('repowatcher fetch; REPOWATCHER_FETCH=false; REPOWATCHER_MODE=notify; _repowatcher_prompt; _repowatcher_prompt')
        self.assertEqual(result.stdout.count('incoming commit'), 1)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_auto_applies_fresh_fetch(self):
        self.incoming()
        self.shell('repowatcher fetch; REPOWATCHER_FETCH=false; REPOWATCHER_MODE=auto; _repowatcher_prompt')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.git(self.seed, 'rev-parse', 'HEAD'))

    def test_auto_does_not_apply_without_successful_fetch(self):
        self.incoming()
        self.git(self.repo, 'fetch')
        self.shell('REPOWATCHER_FETCH=false; REPOWATCHER_MODE=auto; _repowatcher_prompt')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_changed_branch_rejected(self):
        self.incoming()
        result = self.shell('repowatcher fetch; _repowatcher_counts; _repowatcher_pull wrong "$_rw_upstream"', ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_lock_prevents_fetch_and_update(self):
        self.incoming()
        result = self.shell('repowatcher fetch; (zsystem flock -t 0 -f held "$_rw_cache/lock"; touch "$_rw_cache/ready"; sleep 2) & locker=$!; while [[ ! -e $_rw_cache/ready ]]; do sleep 0.01; done; repowatcher pull; result=$?; wait $locker; exit $result', ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_worktree_supported(self):
        other = self.base / 'linked worktree'
        self.git(self.repo, 'worktree', 'add', '-b', 'other', str(other))
        self.git(other, 'branch', '--set-upstream-to', 'origin/main')
        self.incoming()
        self.shell('repowatcher pull', cwd=other)
        self.assertEqual(self.git(other, 'rev-parse', 'HEAD'), self.git(self.seed, 'rev-parse', 'HEAD'))
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_config_file_is_loaded(self):
        config = self.base / '.config/repowatcher/config.zsh'
        config.parent.mkdir(parents=True)
        config.write_text('REPOWATCHER_MODE=notify\nREPOWATCHER_INTERVAL=123\n')
        output = self.shell('repowatcher status').stdout
        self.assertIn('mode=notify interval=123s', output)

    def test_scan_fetches_without_pull_and_deduplicates(self):
        self.incoming()
        output = self.shell('REPOWATCHER_ROOTS=("$PWD" "$PWD"); repowatcher scan').stdout
        self.assertEqual(output.count('incoming,'), 1)
        self.assertNotEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_scan_exclusion_and_depth(self):
        self.incoming()
        self.shell('REPOWATCHER_ROOTS=("$PWD/.."); REPOWATCHER_DEPTH=0; repowatcher scan')
        self.assertEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)
        self.shell('REPOWATCHER_ROOTS=("$PWD/.."); REPOWATCHER_EXCLUDE=("working tree" seed); repowatcher scan')
        self.assertEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)

    def test_interval_throttles_background_attempts(self):
        self.shell('repowatcher fetch')
        self.incoming()
        self.shell('_repowatcher_context; _repowatcher_fetch false')
        self.assertEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)

    def test_invalid_settings_and_duplicate_source(self):
        self.assertNotEqual(self.shell('REPOWATCHER_MODE=invalid; repowatcher status', ok=False).returncode, 0)
        self.shell('source "$1"; repowatcher status')

    def test_auto_with_background_worker(self):
        self.incoming()
        self.shell('REPOWATCHER_MODE=auto; for n in {1..5}; do _repowatcher_prompt; sleep 0.1; done')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.git(self.seed, 'rev-parse', 'HEAD'))

    def test_interactive_confirmation_and_decline(self):
        self.incoming()
        for response in [b'\n', b'y']:
            with self.subTest(response=response):
                pid, master = pty.fork()
                if pid == 0:
                    os.chdir(self.repo)
                    os.execvpe('zsh', ['zsh', '-dfi', '-c',
                        'source "$1"; repowatcher fetch; REPOWATCHER_FETCH=false; _repowatcher_prompt',
                        'test', str(PLUGIN)], self.env)
                output = b''
                deadline = time.monotonic() + 10
                done = False
                try:
                    while b'Apply now?' not in output and time.monotonic() < deadline:
                        if select.select([master], [], [], 0.1)[0]:
                            try:
                                output += os.read(master, 4096)
                            except OSError:
                                break
                    self.assertIn(b'Apply now?', output)
                    time.sleep(0.2)
                    os.write(master, response)
                    while time.monotonic() < deadline:
                        waited, status = os.waitpid(pid, os.WNOHANG)
                        if waited:
                            done = True
                            self.assertEqual(status, 0)
                            break
                        if select.select([master], [], [], 0.05)[0]:
                            try:
                                output += os.read(master, 4096)
                            except OSError:
                                pass
                    self.assertTrue(done, repr(output))
                    if response == b'\n':
                        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)
                    else:
                        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.git(self.seed, 'rev-parse', 'HEAD'))
                finally:
                    if not done:
                        os.kill(pid, 9)
                        os.waitpid(pid, 0)
                    os.close(master)


if __name__ == '__main__':
    unittest.main()
