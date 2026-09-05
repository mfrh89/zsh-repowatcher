# Repository rules

- Never update checked-out files from the background fetch worker.
- All updates must recheck the current branch, upstream, worktree cleanliness, and in-progress Git operations. Never add automatic stash, rebase, reset, push, or conflict resolution.
- Use local Git configuration for repository-specific permissions; never trust tracked files to enable automatic updates.
- Keep plugin-manager-specific setup in documentation. The entrypoint must work when sourced directly.
- Preserve the caller's shell options and avoid duplicate hooks when sourced twice.
- Tests must use isolated temporary repositories and local remotes; never use the developer's real repositories as mutation fixtures.
