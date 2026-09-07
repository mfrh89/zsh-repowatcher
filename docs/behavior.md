# Update behavior and limitations

## Fetching and notifications

Automatic fetching runs in a detached worker at the first prompt inside a repository and after entering a different repository. Leaving to a non-repository directory and re-entering also triggers a fetch, even within the same command. Fetching starts when the next prompt is ready, so transient directories visited by scripts do not each start a worker. Ordinary prompts and movement inside the same worktree do not fetch again or cancel a pending notification. Repository entries bypass the interval, including recent failed attempts. It fetches all remotes, without recursively fetching submodules. The worker never changes checked-out files.

The normal theme prompt is drawn before a commit table and confirmation. If the fetch finishes after the prompt appears, a completion callback shows its new commits at an idle prompt without requiring another command. Network latency still determines when new remote commits become visible. While a command is being typed or pasted, the notice waits until the next prompt. The callback only displays information: in ask or auto mode, press Enter to continue to the normal confirmation or automatic update. It never changes checked-out files or starts another fetch.

Notifications are normally shown once per current branch/upstream/base commit state and mode in each shell. Declining does not discard the update; `repowatcher pull` remains available. After an explicit scan displays the current repository, the next prompt does not repeat that table or ask to apply it.

`repowatcher status` displays the table once; the next prompt can still ask to apply it without repeating the table.

`repowatcher status` reads existing remote-tracking refs. It does not fetch. `scan` respects `REPOWATCHER_INTERVAL` (or local `repowatcher.interval`), whereas repository entry and explicit `fetch` and `pull` commands request an immediate fetch. The interval also defines how recent a successful fetch must be for automatic updates. It is not a periodic timer. `REPOWATCHER_FETCH=false` and mode `off` still disable automatic entry fetches.

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

Fetch output is stored in `fetch.log` under the repository's cache directory. An explicit pull prints the log location if fetching fails or is busy. Attempt timestamps are separate from success timestamps, so scan retries are throttled without qualifying failed fetches as successful fetches for automatic updates. Re-entering a repository retries immediately.

## Concurrency and Git history

Locks coordinate operations started by this plugin across shells and linked worktrees. An interactive background worker waits up to 30 seconds for an existing operation, then reads the resulting state. This lets another shell’s completed fetch notify the idle prompt too. Foreground fetch/pull commands retain their immediate busy response. They cannot prevent another application or unrelated Git command from editing the same repository. Use `ask` or `notify` when other processes actively work on the checkout.

Background fetches update remote-tracking refs. This can weaken the protection of `git push --force-with-lease` when it relies on those refs implicitly. Use an explicit expected commit when rewriting history; see the [Git push documentation](https://git-scm.com/docs/git-push).

Fast-forward eligibility checks Git history, not the correctness of incoming code or configuration.
