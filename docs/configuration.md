# Configuration reference

The plugin loads `${XDG_CONFIG_HOME:-$HOME/.config}/repowatcher/config.zsh`. Set `REPOWATCHER_CONFIG` before loading the plugin to use another file. This is trusted user-owned Zsh code, not a project-local configuration file.

## Defaults

| Setting | Default | Purpose |
| --- | --- | --- |
| `REPOWATCHER_FETCH` | `true` | `true` or `false`: enable automatic fetching. |
| `REPOWATCHER_INTERVAL` | `900` | Minimum seconds between automatic fetch attempts per shared Git directory. Failed attempts are throttled too. |
| `REPOWATCHER_MODE` | `ask` | `off`, `notify`, `ask`, or `auto`. |
| `REPOWATCHER_ROOTS` | No roots | Zsh array of directories searched by `repowatcher scan`. |
| `REPOWATCHER_DEPTH` | `5` | Maximum directory depth for discovery. Zero checks only the listed roots. |
| `REPOWATCHER_EXCLUDE` | See below | Directory names excluded from recursive discovery. |
| `REPOWATCHER_LINKS` | `auto` | `auto`, `on`, or `off`: enable terminal hyperlinks. |
| `REPOWATCHER_LINK_ICON` | `` | Nerd Font external-link marker. Set to `↗` for a standard-font alternative. |
| `REPOWATCHER_CACHE_DIR` | `$XDG_CACHE_HOME/zsh-repowatcher`, or `~/.cache/zsh-repowatcher` | Fetch attempt state, success state, locks, and logs. |

## Repository overrides

These local Git keys override shared defaults:

```sh
git config --local repowatcher.fetch true
git config --local repowatcher.mode ask
git config --local repowatcher.interval 900
```

Only the local Git configuration is consulted for these keys. Invalid fetch, mode, or interval values disable checks for that repository. Linked worktrees share these settings.

Remove an override to return to the shared default:

```sh
git config --local --unset repowatcher.mode
```

## Search roots

```zsh
REPOWATCHER_ROOTS=(~/dev ~/projects)
REPOWATCHER_DEPTH=5
REPOWATCHER_EXCLUDE=(.git .cache .local .Trash Library node_modules .venv venv)
```

The exclusion list above is the default. Setting `REPOWATCHER_EXCLUDE` replaces it; an empty array disables name-based exclusions.

Discovery does not follow symlink directories and stops at each repository root. Overlapping roots are deduplicated. Exclusions apply to directory names during traversal, not explicitly listed roots. Submodules and nested repositories inside an already discovered repository are not scanned separately.

`REPOWATCHER_ROOTS=(~)` searches your home directory with the same depth limit and exclusions. No personal paths are built into the plugin.

Repositories with `repowatcher.mode=off` or `repowatcher.fetch=false` are skipped by `scan`.

## Base branch

The base is resolved through the tracking remote's local default-branch reference, such as `origin/HEAD`. Without a tracking remote, `origin` is used. When that reference is missing, the plugin does not guess a branch name.

Override the base with a local Git ref:

```sh
git config --local repowatcher.base origin/main
```

Disable base notices:

```sh
git config --local repowatcher.base off
```

A branch without an upstream can still show base information, but cannot pull. Identical base and upstream commit tips are displayed once. Base commits are informational even in `auto` mode.

## Tables and links

Each repository/source shows at most five commits. Descriptions are limited to 50 characters including the ellipsis. Columns fit their visible contents and shrink further on narrow terminals. The full layout needs at least 54 terminal columns, or more if link icons widen the commit column.

Table headers are bold on interactive terminals unless `NO_COLOR` is set. Terminal control characters in repository metadata are removed before rendering.

Commit links use OSC 8 for recognized github.com, gitlab.com, and bitbucket.org remotes. `auto` enables links in recognized compatible terminals: Ghostty, iTerm2, WezTerm, VS Code, and Kitty. For another compatible terminal, use:

```zsh
REPOWATCHER_LINKS=on
REPOWATCHER_LINK_ICON='↗'
```

Use `REPOWATCHER_LINKS=off` for plain hashes. Unknown hosts and remote formats fall back to plain text. Remote credentials are not printed. The key or mouse gesture used to open a link depends on the terminal.
