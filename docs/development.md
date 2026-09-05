# Development

Run the integration suite with `python3 -m unittest discover -s tests -v` and check syntax with `zsh -n zsh-repowatcher.plugin.zsh`.

The suite creates local bare remotes and independent clones in temporary directories. It requires no network access and isolates Git identity and configuration from the developer's home.

The `line-init` ZLE hook starts a detached fetch worker and draws the normal prompt before any notice; notifications and updates remain in the foreground. Cache keys derive from the canonical shared Git directory, so linked worktrees share a fetch interval and lock. Successful-fetch state is separate from attempt state: failures are throttled but do not qualify for automatic updates.

Repository overrides use local Git configuration, not tracked files, to keep update permissions under the machine owner's control. The plugin is deliberately independent of any plugin manager. Shell configuration and package installation belong in the consuming dotfiles repository.

## Load a local checkout with Sheldon

Use this instead of the GitHub entry while developing:

```toml
[plugins.zsh-repowatcher]
local = "~/dev/zsh-repowatcher"
use = ["zsh-repowatcher.plugin.zsh"]
```

Run `sheldon lock` after changing the entry. Open a new Zsh session after editing the plugin: its load guard deliberately prevents duplicate initialization in an existing shell.
