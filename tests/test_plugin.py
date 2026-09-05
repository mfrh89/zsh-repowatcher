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

    def assert_scan_summary(self, output, checked=0, incoming=0, skipped=0, failed=0):
        for count, label in ((checked, 'checked'), (incoming, 'with incoming commits'),
                             (skipped, 'skipped'), (failed, 'failed')):
            self.assertRegex(output, rf'\b{count} {label}\b')

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
        self.assertEqual(result.stdout.count('DESCRIPTION'), 1)
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
        self.assert_scan_summary(output, checked=1, incoming=1)
        self.assertEqual(output.count('DESCRIPTION'), 1)
        self.assertNotEqual(self.git(self.repo, 'rev-parse', '@{u}'), self.initial)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_scan_reports_no_incoming_commits_without_changing_caller_directory(self):
        output = self.shell('REPOWATCHER_ROOTS=("$PWD" "$PWD"); cd "$HOME"; '
                            'repowatcher scan; print -r -- "caller=$PWD"').stdout
        self.assert_scan_summary(output, checked=1)
        self.assertIn(f'caller={self.base}', output)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_scan_reports_when_no_repositories_are_found(self):
        empty = self.base / 'empty'
        empty.mkdir()
        output = self.shell('REPOWATCHER_ROOTS=("$HOME/empty"); repowatcher scan').stdout
        self.assertRegex(output.lower(), r'no repositories found')

    def test_scan_counts_skipped_repositories_separately(self):
        self.git(self.repo, 'config', 'repowatcher.mode', 'off')
        output = self.shell('REPOWATCHER_ROOTS=("$PWD" "$HOME/seed"); repowatcher scan').stdout
        self.assert_scan_summary(output, checked=1, skipped=1)

    def test_scan_does_not_count_detached_or_untracked_branches_as_checked(self):
        self.git(self.repo, 'checkout', '--detach')
        output = self.shell('REPOWATCHER_ROOTS=("$PWD"); repowatcher scan').stdout
        self.assert_scan_summary(output, skipped=1)
        self.git(self.repo, 'checkout', 'main')
        self.git(self.repo, 'branch', '--unset-upstream')
        self.git(self.repo, 'config', 'repowatcher.base', 'off')
        output = self.shell('REPOWATCHER_ROOTS=("$PWD"); repowatcher scan').stdout
        self.assert_scan_summary(output, skipped=1)

    def test_scan_keeps_failed_fetches_failed_while_throttled(self):
        self.shell('repowatcher fetch')
        self.git(self.repo, 'remote', 'set-url', 'origin', str(self.base / 'missing'))
        self.shell('repowatcher fetch', ok=False)
        output = self.shell('REPOWATCHER_ROOTS=("$PWD" "$HOME/seed"); repowatcher scan').stdout
        self.assert_scan_summary(output, checked=1, failed=1)

    def test_scan_reports_invalid_repository_settings_as_failed(self):
        self.git(self.repo, 'config', 'repowatcher.mode', 'invalid')
        output = self.shell('REPOWATCHER_ROOTS=("$PWD"); repowatcher scan').stdout
        self.assert_scan_summary(output, failed=1)

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

    def feature(self):
        self.git(self.repo, 'checkout', '-b', 'feature')
        self.commit(self.repo, 'feature-local')
        self.git(self.repo, 'push', '-u', 'origin', 'feature')

    def test_base_only_is_shown_and_never_applied(self):
        self.feature()
        head = self.git(self.repo, 'rev-parse', 'HEAD')
        self.incoming()
        output = self.shell('repowatcher fetch; REPOWATCHER_FETCH=false; REPOWATCHER_MODE=auto; _repowatcher_prompt').stdout
        self.assertIn('origin/main', output)
        self.assertIn('base', output)
        self.assertIn('incoming', output)
        self.assertNotIn('Apply now?', output)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), head)

    def test_upstream_and_base_are_separate(self):
        self.feature()
        self.incoming()
        self.git(self.seed, 'fetch')
        self.git(self.seed, 'checkout', '-b', 'feature', 'origin/feature')
        self.commit(self.seed, 'feature-incoming')
        self.git(self.seed, 'push')
        feature_head = self.git(self.seed, 'rev-parse', 'HEAD')
        output = self.shell('repowatcher fetch; repowatcher status').stdout
        self.assertIn('origin/main', output)
        self.assertIn('origin/feature', output)
        self.shell('repowatcher pull')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), feature_head)
        self.assertFalse((self.repo / 'incoming').exists())

    def test_missing_upstream_still_shows_base(self):
        self.git(self.repo, 'checkout', '-b', 'unpublished')
        self.incoming()
        output = self.shell('repowatcher fetch; repowatcher status').stdout
        self.assertIn('base information only', output)
        self.assertIn('origin/main', output)
        self.assertNotEqual(self.shell('repowatcher pull', ok=False).returncode, 0)

    def test_base_override_and_disable(self):
        self.feature()
        self.incoming()
        self.git(self.repo, 'config', '--local', 'repowatcher.base', 'off')
        output = self.shell('repowatcher fetch; repowatcher status').stdout
        self.assertNotIn('DESCRIPTION', output)
        self.git(self.repo, 'config', '--local', 'repowatcher.base', 'origin/main')
        self.assertIn('DESCRIPTION', self.shell('repowatcher status').stdout)

    def test_no_default_branch_is_not_guessed(self):
        self.feature()
        self.incoming()
        self.shell('repowatcher fetch')
        self.git(self.repo, 'symbolic-ref', '--delete', 'refs/remotes/origin/HEAD')
        self.assertNotIn('DESCRIPTION', self.shell('repowatcher status').stdout)

    def test_description_limit_and_five_rows(self):
        for n in range(7):
            self.git(self.seed, 'commit', '--allow-empty', '-m', str(n) + 'ü' * 60)
        self.git(self.seed, 'push')
        output = self.shell('COLUMNS=200; repowatcher fetch; repowatcher status').stdout
        rows = [line for line in output.splitlines() if line.startswith('│ working tree')]
        self.assertEqual(len(rows), 6)
        for line in rows[:5]:
            description = line.split('│')[-2].strip()
            self.assertEqual(len(description), 50)
            self.assertTrue(description.endswith('…'))
        self.assertIn('2 more commits', rows[-1])

    def test_links_are_optional_and_provider_specific(self):
        self.incoming()
        self.shell('repowatcher fetch')
        sha = self.git(self.seed, 'rev-parse', 'HEAD')
        for remote, path in [('git@github.com:owner/repo.git', 'https://github.com/owner/repo/commit/'),
                             ('https://gitlab.com/team/repo.git', 'https://gitlab.com/team/repo/-/commit/'),
                             ('ssh://git@bitbucket.org/team/repo.git', 'https://bitbucket.org/team/repo/commits/')]:
            self.git(self.repo, 'remote', 'set-url', 'origin', remote)
            output = self.shell('REPOWATCHER_LINKS=on; repowatcher status').stdout
            self.assertIn('\x1b]8;;' + path + sha, output)
            self.assertIn(' ' + sha[:7], output)
            self.assertNotIn('\x1b', self.shell('REPOWATCHER_LINKS=off; repowatcher status').stdout)
        self.git(self.repo, 'remote', 'set-url', 'origin', 'https://token@example.invalid/team/repo.git')
        output = self.shell('REPOWATCHER_LINKS=on; repowatcher status').stdout
        self.assertNotIn('token', output)
        self.assertNotIn('\x1b', output)

    def test_commit_subject_controls_are_sanitized(self):
        self.git(self.seed, 'commit', '--allow-empty', '-m', 'unsafe\x1b]8;;https://bad.example\x07subject')
        self.git(self.seed, 'push')
        output = self.shell('repowatcher fetch; REPOWATCHER_LINKS=off; repowatcher status').stdout
        self.assertNotIn('\x1b', output)
        self.assertNotIn('\x07', output)

    def test_frames_fit_terminal_and_links_do_not_affect_width(self):
        self.incoming()
        self.shell('repowatcher fetch')
        self.git(self.repo, 'remote', 'set-url', 'origin', 'git@github.com:owner/repo.git')
        import re
        for columns in [60, 80, 160]:
            output = self.shell(f'COLUMNS={columns}; REPOWATCHER_LINKS=on; repowatcher status').stdout
            plain = re.sub(r'\x1b\]8;;.*?\x1b\\', '', output)
            lines = [line for line in plain.splitlines() if line.startswith(('┌', '├', '└', '│'))]
            self.assertEqual(len({len(line) for line in lines}), 1, plain)
            self.assertLessEqual(len(lines[0]), columns)

    def test_wide_unicode_cells_align_with_borders(self):
        import unicodedata
        self.git(self.seed, 'commit', '--allow-empty', '-m', '界' * 50)
        self.git(self.seed, 'push')
        output = self.shell('COLUMNS=80; repowatcher fetch; REPOWATCHER_LINKS=off; repowatcher status').stdout
        lines = [line for line in output.splitlines() if line.startswith(('┌', '├', '└', '│'))]
        def width(line):
            return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in line)
        self.assertEqual(len({width(line) for line in lines}), 1, output)
        self.assertLessEqual(width(lines[0]), 80)

    def test_scan_suppresses_duplicate_current_repo_prompt(self):
        self.incoming()
        output = self.shell('REPOWATCHER_ROOTS=("$PWD"); repowatcher scan; REPOWATCHER_FETCH=false; _repowatcher_prompt').stdout
        self.assertEqual(output.count('DESCRIPTION'), 1)

    def test_new_branch_identity_is_rechecked_before_update(self):
        self.incoming()
        result = self.shell('repowatcher fetch; _repowatcher_counts; previous=$_rw_branch; git checkout -b other; git branch --set-upstream-to origin/main; _repowatcher_pull "$_rw_head" "$_rw_upstream" "$previous"', ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.initial)

    def test_real_prompt_precedes_table_and_decline_preserves_input(self):
        self.real_prompt_flow(b'n\n')

    def test_real_prompt_precedes_table_and_accept_applies_upstream(self):
        self.real_prompt_flow(b'y\n')

    def real_prompt_flow(self, response):
        self.incoming()
        self.shell('repowatcher fetch')
        (self.base / '.zshrc').write_text(
            f'source "{PLUGIN}"\nREPOWATCHER_FETCH=false\nPS1="LOCATION:%~ > "\n')
        pid, master = pty.fork()
        if pid == 0:
            os.chdir(self.repo)
            os.execvpe('zsh', ['zsh', '-di'], dict(self.env, ZDOTDIR=str(self.base), TERM='xterm-256color'))
        output = b''
        def until(marker):
            nonlocal output
            deadline = time.monotonic() + 10
            while marker not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 4096)
                    except OSError:
                        break
            self.assertIn(marker, output)
        try:
            until(b'Apply now?')
            self.assertIn(b'LOCATION:', output)
            self.assertIn(b'\x1b[1m', output)
            self.assertLess(output.index(b'LOCATION:'), output.index(b'DESCRIPTION'))
            time.sleep(0.2)
            os.write(master, response)
            output = b''
            until(b'LOCATION:')
            os.write(master, b"print -- INPUT''_RESTORED\n")
            until(b'INPUT_RESTORED')
            expected = self.git(self.seed, 'rev-parse', 'HEAD') if response.startswith(b'y') else self.initial
            self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), expected)
        finally:
            os.close(master)
            os.kill(pid, 9)
            os.waitpid(pid, 0)

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
                    self.assertIn(b'DESCRIPTION', output)
                    self.assertLess(output.index(b'DESCRIPTION'), output.index(b'Apply now?'))
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
