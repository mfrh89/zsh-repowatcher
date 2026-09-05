# zsh-repowatcher

Fetch Git updates in the background and choose whether to inspect, confirm, or automatically apply them when your Zsh prompt returns.

Works with Sheldon, Zinit, other Zsh plugin managers, or plain `source`. Requires Zsh 5.8+ with its standard modules and Git. Python 3 is needed only for tests.

## Install

With Sheldon, add to `plugins.toml`:

```toml
[plugins.zsh-repowatcher]
github = "mfrh89/zsh-repowatcher"
use = ["zsh-repowatcher.plugin.zsh"]
```

During local development, use this entry instead:

```toml
[plugins.zsh-repowatcher]
local = "~/dev/zsh-repowatcher"
use = ["zsh-repowatcher.plugin.zsh"]
```

With Zinit:

```zsh
zinit light mfrh89/zsh-repowatcher
```

Or source your checkout directly:

```zsh
source ~/dev/zsh-repowatcher/zsh-repowatcher.plugin.zsh
```

The remote installation examples require the plugin to have been published to GitHub.

## Configure

The plugin loads `${XDG_CONFIG_HOME:-~/.config}/repowatcher/config.zsh` when sourced. Create that file with your defaults:

```zsh
REPOWATCHER_FETCH=true
REPOWATCHER_INTERVAL=900
REPOWATCHER_MODE=ask
```

| Setting | Default | Values |
| --- | --- | --- |
| `REPOWATCHER_FETCH` | `true` | `true`, `false`: automatic fetch only |
| `REPOWATCHER_INTERVAL` | `900` | Minimum seconds between background attempts per shared Git directory |
| `REPOWATCHER_MODE` | `ask` | `off`, `notify`, `ask`, `auto` |
| `REPOWATCHER_LINKS` | `auto` | `auto`, `on`, `off`: clickable commit hashes |
| `REPOWATCHER_LINK_ICON` | `` | Nerd Font link marker; use `↗` with a standard font |
| `REPOWATCHER_CACHE_DIR` | `$XDG_CACHE_HOME/zsh-repowatcher` or `~/.cache/zsh-repowatcher` | Local state and fetch logs |

- `off`: disable automatic checks and updates for this repository.
- `notify`: show incoming commits, without applying them.
- `ask`: ask `Apply now? [y/N]` at the prompt. Enter declines.
- `auto`: apply incoming commits after a successful recent fetch, subject to the checks below.

Override defaults locally inside a repository:

```zsh
git config --local repowatcher.mode auto
git config --local repowatcher.fetch true
git config --local repowatcher.interval 900
```

These settings stay on this machine and are shared by linked worktrees. They are not taken from tracked project files. Invalid values disable checks for that repository. Global Git configuration is not consulted for these plugin settings.

You can symlink this file from your dotfiles repository, for example `~/config/repowatcher/config.zsh`. It is Zsh code owned by you, so keep it trusted. Set `REPOWATCHER_CONFIG` before loading to use another path. Changes take effect in a new shell. Local Git settings override file defaults.

## What happens

1. When the shell is ready for another command, the plugin checks the current repository. This includes returning to the prompt after `cd`.
2. If the interval has elapsed, it fetches all remotes in the background. It does not recursively fetch submodules.
3. The next prompt can show new commits and ask to apply them. The background process never changes checked-out files.
4. A confirmed or automatic update affects only the current branch.

This is not a daemon: closed shells and repositories you never enter are not monitored. A fetch completing while the shell is idle does not interrupt your typing. Press Enter to show a new prompt. Notices are normally shown once per branch/upstream state per shell; declined updates remain available through the command below.

## Commands

```zsh
repowatcher status  # Show settings and the last fetched ahead/behind counts
repowatcher fetch   # Fetch immediately, even when automatic fetching is disabled
repowatcher pull    # Fetch, recheck, and apply a fast-forward update
repowatcher scan    # Check repositories under configured roots; never pull
repowatcher help
```

## Update rules

Updates require a current branch with an upstream, no local commits diverging from it, and a clean working tree including untracked files. Merge, rebase, cherry-pick, revert, sequencer, and bisect operations block updates.

The plugin never automatically stashes, rebases, resolves conflicts, pushes, or updates other local branches. It integrates the exact upstream commit it checked using `git merge --ff-only` with autostash disabled. Git hooks retain their usual behavior.

Fetch failures prevent an explicit pull. Automatic updates additionally require a recent successful plugin fetch. Authentication is noninteractive: Git terminal prompts are disabled and the default SSH command uses batch mode and a connection timeout. An explicit `GIT_SSH_COMMAND` is respected; external credential helpers may have their own behavior.

A lock coordinates plugin operations across shells and linked worktrees. It cannot serialize unrelated editors, agents, or Git commands. Choose `ask` or `notify` for repositories actively edited by another process. Fast-forward eligibility does not guarantee that the incoming code or configuration is correct.

Background fetching also updates remote-tracking refs used by implicit `git push --force-with-lease`; use an explicit expected commit when rewriting history. See [Git's explanation](https://git-scm.com/docs/git-push#Documentation/git-push.txt---force-with-leaseltrefnamegtltexpectgt).

See [development notes](docs/development.md) for tests and architecture.

## Scan multiple repositories

Configure search roots in `~/.config/repowatcher/config.zsh`, not in the plugin:

```zsh
REPOWATCHER_ROOTS=(~/dev ~/config)
REPOWATCHER_DEPTH=5
# Optional override of excluded directory names:
REPOWATCHER_EXCLUDE=(.git .cache .local .Trash Library node_modules .venv venv)
```

Run `repowatcher scan` from any directory. It discovers repositories recursively, fetches subject to their settings and interval, and reports incoming commits. It never pulls or asks questions in other repositories. Overlapping roots are deduplicated. Symlink directories are not traversed; discovery stops at a repository root. Depth zero checks only the explicitly listed roots.

`REPOWATCHER_ROOTS=(~)` searches the home directory, with the same exclusions and depth limit. No personal paths are hardcoded. With no roots configured, only the current-repository prompt integration is active. Scanning is currently an explicit command, not a periodic background service. It prints a separate table for each repository with incoming commits. A repository shown by the scan is not immediately repeated by the current-shell prompt hook; use `repowatcher pull` when you want to apply its upstream updates.

## Commit tables and the base branch

The prompt, `repowatcher status`, and `repowatcher scan` show incoming commits in tables. Automatic notices render the normal theme prompt first, then the table and confirmation. Confirm with `y` followed by Enter; Enter alone declines. After the answer, the shell restores its normal command input:

```text
┌─────────┬────────────┬──────────┬───────────────────┬─────────┬─────────────────────┐
│ REPO    │ BRANCH     │ KIND     │ SOURCE            │ COMMIT  │ DESCRIPTION         │
├─────────┼────────────┼──────────┼───────────────────┼─────────┼─────────────────────┤
│ compose │ feat/login │ upstream │ origin/feat/login │ a1b2c3d │ Fix session refresh │
│ compose │ feat/login │ base     │ origin/main       │ e4f5a6b │ Workspace settings  │
└─────────┴────────────┴──────────┴───────────────────┴─────────┴─────────────────────┘
Base commits are informational; Apply updates the upstream only.
Apply now? [y/N]
```

Each repository/source shows up to five commits, followed by the number remaining. Subjects are truncated to 50 characters including the ellipsis. Framed columns size themselves to their visible contents. On narrow terminals, long cells are shortened further to fit; the complete six-column layout requires at least 54 terminal columns. Hyperlink escape sequences do not count toward column widths. Terminal control characters in Git metadata are removed before rendering.

`upstream` means commits missing from the checked-out branch's configured upstream. `base` means commits on the remote default branch that are not reachable from the checked-out branch. These are informational: they never cause an automatic merge, rebase, or branch switch. If only base commits are new, the table appears without an Apply question. Diverged upstreams also display their commits but cannot be automatically applied.

The base is resolved through the tracking remote's local `HEAD` reference, such as `origin/HEAD`. Without a tracking remote, `origin` is used. If the default reference is unavailable, no branch name is guessed. Configure an explicit base, or disable base notices, locally:

```zsh
git config --local repowatcher.base origin/main
git config --local repowatcher.base off
```

A branch without an upstream may still show base information, but cannot pull. Identical base/upstream commit tips are displayed only once. A confirmation refreshes remote data and checks that the branch and upstream commit still match the preview; if either changes, it skips the update and shows a new preview at a subsequent prompt.

Clickable hashes have a Nerd Font external-link marker. Table headers are bold on interactive terminals unless `NO_COLOR` is set. Clickable hashes use OSC 8 terminal links for github.com, gitlab.com, and bitbucket.org remotes. Automatic mode enables them in recognized compatible terminals (Ghostty, iTerm2, WezTerm, VS Code, Kitty). Set `REPOWATCHER_LINKS=on` to opt in on another compatible terminal, or `off` for plain hashes. Unknown hosts and remote formats use plain hashes; credentials in remote URLs are never printed. Whether a link opens on click or with a modifier key depends on your terminal.

Prompt notices are based on fetched data. A first background fetch may finish after the prompt appears; press Enter to see its result. Open a new Zsh session after updating the plugin because sourcing it twice is deliberately ignored.
