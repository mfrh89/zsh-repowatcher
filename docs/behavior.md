# Update behavior and limitations

## Fetching and notifications

Automatic fetching runs in a detached worker when the line editor initializes for another command. It fetches all remotes, without recursively fetching submodules. The worker never changes checked-out files.

The normal theme prompt is drawn before a commit table and confirmation. If the fetch has not finished, its new commits can appear at a subsequent prompt. Press Enter to check again. Finishing a fetch does not interrupt typing or immediately redraw an idle shell.

Notifications are normally shown once per current branch/upstream/base commit state and mode in each shell. Declining does not discard the update; `repowatcher pull` remains available. After an explicit scan displays the current repository, the next prompt does not repeat that table or ask to apply it.

`repowatcher status` reads existing remote-tracking refs. It does not fetch. `scan` respects the automatic fetch interval, whereas explicit `fetch` and `pull` commands request an immediate fetch.

Every scan prints a completion message. It reports checked repositories, those with
incoming upstream or base commits, skipped repositories, and failed checks.
Overlapping roots count each canonical repository once. Repositories with mode
`off`, fetching disabled, no current commit/branch, or no upstream/base comparison
are skipped. Invalid settings and failed or busy fetches are failures. A failed
fetch remains a failure during the retry interval; old remote-tracking refs do not
turn it into a successful check. A scan with no discovered repositories reports
that separately. Partial failures still allow other repositories to be checked;
the scan's existing exit-status behavior is unchanged.

## Applying updates

The current branch must track an upstream and be strictly behind it. Uncommitted tracked changes, untracked files, or diverged commits block an update. So do merge, rebase, cherry-pick, revert, sequencer, and bisect operations.

The plugin integrates the checked commit with `git merge --ff-only` and autostash disabled. Git hooks retain their usual behavior. Other branches are not updated.

A confirmation fetches again, then checks that the current branch and upstream commit still match the preview. If they changed, the plugin skips the update. Automatic updates require a recent successful plugin fetch. An explicit pull stops if its fetch fails or another plugin operation holds the lock.

## Authentication and logs

Git terminal prompts are disabled during fetch. The default SSH command uses batch mode and a connection timeout. An explicit `GIT_SSH_COMMAND` is respected, and external credential helpers may have their own behavior.

Fetch output is stored in `fetch.log` under the repository's cache directory. An explicit pull prints the log location if fetching fails or is busy. Attempt timestamps are separate from success timestamps, so repeated failures are throttled without qualifying as successful fetches for automatic updates.

## Concurrency and Git history

Locks coordinate operations started by this plugin across shells and linked worktrees. They cannot prevent another application or unrelated Git command from editing the same repository. Use `ask` or `notify` when other processes actively work on the checkout.

Background fetches update remote-tracking refs. This can weaken the protection of `git push --force-with-lease` when it relies on those refs implicitly. Use an explicit expected commit when rewriting history; see the [Git push documentation](https://git-scm.com/docs/git-push).

Fast-forward eligibility checks Git history, not the correctness of incoming code or configuration.
