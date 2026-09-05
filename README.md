# zsh-repowatcher

See incoming Git commits when you enter a repository, and choose when to apply them.

`zsh-repowatcher` fetches remote changes in the background and shows a commit table below your normal Zsh prompt. It can notify you, ask before updating, or automatically apply fast-forward updates to a clean working tree.

It works with Sheldon, Zinit, or a direct `source`. Runtime requirements are Zsh 5.8+ with its standard modules and Git, on macOS or Linux.

## A preview before you update

```text
~/dev/app on feat/login
❯

┌──────┬────────────┬──────────┬───────────────────┬─────────┬─────────────────────┐
│ REPO │ BRANCH     │ KIND     │ SOURCE            │ COMMIT  │ DESCRIPTION         │
├──────┼────────────┼──────────┼───────────────────┼─────────┼─────────────────────┤
│ app  │ feat/login │ upstream │ origin/feat/login │ a1b2c3d │ Fix session refresh │
│ app  │ feat/login │ base     │ origin/main       │ e4f5a6b │ Workspace settings  │
└──────┴────────────┴──────────┴───────────────────┴─────────┴─────────────────────┘
Base commits are informational; Apply updates the upstream only.
Apply now? [y/N]
```

*Illustrative output. Your shell theme supplies the prompt.*

- **Upstream updates:** commits on your current branch's tracking branch that you do not have locally. These are eligible for a checked fast-forward update.
- **Base updates:** commits on the remote default branch that your current branch does not contain. These are shown for reference; the plugin never merges or rebases your feature branch onto the base.
- **Commit previews:** up to five commits per repository and source, with subjects limited to 50 characters and a count of the remaining commits.
- **Terminal formatting:** fitted table borders, bold headers, and linked commit hashes with a Nerd Font link marker in supported terminals.

Confirm with `y` and Enter, or press Enter to decline. The command prompt returns after your answer.

## Install

Choose one installation method, then open a new Zsh session.

### Sheldon

Add to your Sheldon `plugins.toml`:

```toml
[plugins.zsh-repowatcher]
github = "mfrh89/zsh-repowatcher"
use = ["zsh-repowatcher.plugin.zsh"]
```

Run `sheldon lock`. Your `.zshrc` should already load plugins with `eval "$(sheldon source)"`.

### Zinit

Add after your Zinit initialization in `.zshrc`:

```zsh
zinit light mfrh89/zsh-repowatcher
```

### Without a plugin manager

Clone the repository:

```sh
git clone https://github.com/mfrh89/zsh-repowatcher.git ~/.local/share/zsh-repowatcher
```

Add to `.zshrc`:

```zsh
source ~/.local/share/zsh-repowatcher/zsh-repowatcher.plugin.zsh
```

## Configure

The defaults enable background fetching at most once every 15 minutes per shared Git directory and ask before applying updates. No configuration file is required for that behavior.

To customize it, create `~/.config/repowatcher/config.zsh` (or `$XDG_CONFIG_HOME/repowatcher/config.zsh`):

```zsh
REPOWATCHER_FETCH=true
REPOWATCHER_INTERVAL=900
REPOWATCHER_MODE=ask

# Optional search roots for `repowatcher scan`.
REPOWATCHER_ROOTS=(~/dev ~/projects)
REPOWATCHER_DEPTH=5
```

| Mode | Behavior |
| --- | --- |
| `notify` | Show incoming commits without applying them. |
| `ask` | Show the table and ask before applying upstream updates. Default. |
| `auto` | Apply eligible upstream updates after a recent successful fetch. |
| `off` | Disable automatic checks and exclude the repository from scans. |

Set `REPOWATCHER_FETCH=false` to disable automatic fetching independently of the mode. Manual `repowatcher fetch` and `repowatcher pull` still fetch when requested.

You can symlink the configuration file from your dotfiles repository. It contains Zsh code and is loaded once when the plugin starts. Open a new shell after changing it.

Override settings for one repository with local Git configuration:

```sh
git config --local repowatcher.mode auto
```

Local overrides take priority over shared defaults. They stay on that machine and apply to linked worktrees too. Tracked project files cannot enable automatic updates.

See the [configuration reference](docs/configuration.md) for every setting, exclusions, links, and base-branch selection.

## Current repo or all repos?

| Command | Scope and behavior |
| --- | --- |
| `repowatcher status` | Current repo: settings, ahead/behind counts, and commit tables from the last fetched state. Also the default when called without arguments. |
| `repowatcher fetch` | Current repo: fetch immediately without changing checked-out files. |
| `repowatcher pull` | Current repo: fetch, check eligibility, and apply a fast-forward update. |
| `repowatcher scan` | Configured search roots: discover repos, fetch subject to settings and interval, and show a table for each repo with incoming commits. Never pull. |
| `repowatcher help` | Show available commands. |

The automatic prompt notice concerns only the repository you are in. `scan` is an explicit command for checking several repositories, not a scheduled service.

A background fetch may finish after the prompt appears. Press Enter to see the result at the next prompt. The plugin does not interrupt an input line when a fetch finishes, monitor closed shells, or check every repository on your machine automatically.

## What an update can change

An update requires a current branch with an upstream, a clean working tree including untracked files, and a fast-forward relationship. Diverged histories and in-progress Git operations are skipped.

Only the checked-out branch is updated. The plugin never automatically stashes, rebases, resolves conflicts, pushes, or updates other local branches. If the branch or upstream commit changes while a confirmation is open, the update is skipped so you can review the new state.

Locks coordinate plugin operations across terminals and linked worktrees. They cannot coordinate unrelated editors or Git commands. A conflict-free update can still contain broken code or configuration; use `ask` or `notify` where you want to inspect changes first.

Read the [update behavior and limitations](docs/behavior.md) for authentication, notifications, and Git details.

## Development

Python 3 is needed only for the test suite. Tests use temporary repositories and local bare remotes, including real terminal sessions for prompt ordering and confirmation.

```sh
zsh -n zsh-repowatcher.plugin.zsh
python3 -m unittest discover -s tests -v
```

See [development notes](docs/development.md) for the local Sheldon setup and implementation boundaries.
