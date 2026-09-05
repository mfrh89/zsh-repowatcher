# Load with any Zsh plugin manager or source this file directly.
[[ -n ${_REPOWATCHER_LOADED-} ]] && return 0
typeset -g _REPOWATCHER_LOADED=1
zmodload zsh/datetime
zmodload zsh/stat
zmodload zsh/system
zmodload zsh/zselect
autoload -Uz add-zsh-hook

# This is trusted, user-owned shell configuration, never a project-local file.
if [[ -r ${REPOWATCHER_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/repowatcher/config.zsh} ]]; then
  source "${REPOWATCHER_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/repowatcher/config.zsh}"
fi

typeset -gA _repowatcher_seen

_repowatcher_context() {
  emulate -L zsh
  local root common value
  root=$(command git rev-parse --show-toplevel 2>/dev/null) || return 1
  common=$(command git rev-parse --git-common-dir 2>/dev/null) || return 1
  typeset -g _rw_root=${root:A} _rw_common=${common:A}
  value=$(command git config --local --get repowatcher.fetch 2>/dev/null)
  typeset -g _rw_fetch=${value:-${REPOWATCHER_FETCH:-true}}
  value=$(command git config --local --get repowatcher.mode 2>/dev/null)
  typeset -g _rw_mode=${value:-${REPOWATCHER_MODE:-ask}}
  value=$(command git config --local --get repowatcher.interval 2>/dev/null)
  typeset -g _rw_interval=${value:-${REPOWATCHER_INTERVAL:-900}}
  [[ $_rw_fetch == (true|false) && $_rw_mode == (off|notify|ask|auto) && $_rw_interval == <-> ]] || return 1
  local key=$(print -rn -- "$_rw_common" | command cksum)
  key=${key// /-}
  typeset -g _rw_cache=${REPOWATCHER_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/zsh-repowatcher}/$key
  (umask 077; command mkdir -p -- "$_rw_cache") || return 1
}

_repowatcher_fetch() {
  emulate -L zsh
  local force=${1:-false} fd last=0
  local -A info
  zsystem flock -t 0 -f fd "$_rw_cache/lock" 2>/dev/null || return 2
  {
    if zstat -H info "$_rw_cache/attempt" 2>/dev/null; then last=$info[mtime]; fi
    [[ $force == true ]] || (( EPOCHSECONDS - last >= _rw_interval )) || return 0
    : > "$_rw_cache/attempt"
    command rm -f -- "$_rw_cache/success"
    if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=10}" \
      command git -C "$_rw_root" fetch --all --quiet --no-recurse-submodules > "$_rw_cache/fetch.log" 2>&1; then
      : > "$_rw_cache/success"
    else
      return 1
    fi
  } always {
    zsystem flock -u $fd
  }
}

_repowatcher_counts() {
  emulate -L zsh
  command git symbolic-ref -q HEAD >/dev/null || return 1
  typeset -g _rw_head=$(command git rev-parse HEAD 2>/dev/null) || return 1
  typeset -g _rw_upstream=$(command git rev-parse --verify '@{upstream}' 2>/dev/null) || return 1
  local counts=$(command git rev-list --left-right --count "$_rw_head...$_rw_upstream" 2>/dev/null) || return 1
  local -a values=( ${(z)counts} )
  typeset -g _rw_ahead=$values[1] _rw_behind=$values[2]
}

_repowatcher_pull() {
  emulate -L zsh
  local expected_head=$1 expected_upstream=$2 fd gitdir marker dirty
  zsystem flock -t 0 -f fd "$_rw_cache/lock" 2>/dev/null || {
    print -r -- 'repowatcher: another check is running; try again.'; return 2
  }
  {
    _repowatcher_counts || return 1
    [[ $_rw_head == $expected_head && $_rw_upstream == $expected_upstream ]] || {
      print -r -- 'repowatcher: branch changed; check again.'; return 1
    }
    (( _rw_ahead == 0 && _rw_behind > 0 )) || return 1
    gitdir=$(command git rev-parse --absolute-git-dir) || return 1
    for marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply sequencer BISECT_START; do
      [[ ! -e $gitdir/$marker ]] || {
        print -r -- 'repowatcher: Git operation in progress; update skipped.'; return 1
      }
    done
    dirty=$(command git status --porcelain --untracked-files=normal) || return 1
    [[ -z $dirty ]] || {
      print -r -- 'repowatcher: local changes present; update skipped.'; return 1
    }
    # Integrate the exact commit just checked. Never stash or rebase automatically.
    command git -c merge.autoStash=false merge --ff-only --no-edit "$_rw_upstream"
  } always {
    zsystem flock -u $fd
  }
}

_repowatcher_prompt() {
  emulate -L zsh
  _repowatcher_context || return 0
  [[ $_rw_mode != off ]] || return 0
  # Create once without truncating an existing lock file.
  [[ -e $_rw_cache/lock ]] || (umask 077; : >> "$_rw_cache/lock")
  if [[ $_rw_fetch == true ]]; then
    (_repowatcher_fetch false) &!
  fi
  _repowatcher_counts || return 0
  (( _rw_behind > 0 )) || return 0
  local key="$_rw_root:$_rw_head:$_rw_upstream:$_rw_mode"
  [[ -z ${_repowatcher_seen[$key]-} ]] || return 0
  local name=${_rw_root:t}
  if (( _rw_ahead > 0 )); then
    print -r -- "repowatcher: $name has diverged ($_rw_ahead ahead, $_rw_behind behind); update skipped."
    _repowatcher_seen[$key]=1
    return 0
  fi
  print -r -- "repowatcher: $name has $_rw_behind incoming commit(s)."
  # Only mutate after a successful recent fetch, never based on stale refs.
  local -A info
  local fresh=false
  if zstat -H info "$_rw_cache/success" 2>/dev/null && (( EPOCHSECONDS - info[mtime] <= _rw_interval )); then
    fresh=true
  fi
  if [[ $_rw_mode == auto && $fresh == true ]]; then
    _repowatcher_pull "$_rw_head" "$_rw_upstream"
    (( $? == 2 )) && return 0
  elif [[ $_rw_mode == ask && -o interactive && -t 0 && -t 1 ]]; then
    # Do not consume pasted commands or input already waiting at the terminal.
    zselect -t 0 -r 0 2>/dev/null && return 0
    local answer
    if read -q 'answer?Apply now? [y/N] '; then
      print
      repowatcher pull
    else
      print
    fi
  else
    print -r -- 'Run `repowatcher pull` to fetch and apply, or `repowatcher status` to inspect.'
  fi
  [[ $_rw_mode == auto && $fresh == false ]] || _repowatcher_seen[$key]=1
  return 0
}


_repowatcher_discover() {
  emulate -L zsh
  local directory=$1 depth=$2 child name
  [[ -d $directory && ! -L $directory ]] || return 0
  if [[ -e $directory/.git ]]; then
    local canonical=${directory:A}
    [[ -n ${discovered[$canonical]-} ]] && return 0
    discovered[$canonical]=1
    (
      builtin cd -- "$directory" || exit 1
      _repowatcher_context || exit 0
      [[ $_rw_mode != off && $_rw_fetch == true ]] || exit 0
      [[ -e $_rw_cache/lock ]] || (umask 077; : >> "$_rw_cache/lock")
      _repowatcher_fetch false || { print -r -- "repowatcher: $directory: fetch failed or busy."; exit 0; }
      _repowatcher_counts || exit 0
      (( _rw_behind > 0 )) && print -r -- "repowatcher: $directory: $_rw_behind incoming, $_rw_ahead outgoing commit(s)."
      exit 0
    )
    return 0
  fi
  (( depth > 0 )) || return 0
  for child in "$directory"/*(ND/); do
    name=${child:t}
    (( ${exclusions[(Ie)$name]} )) && continue
    _repowatcher_discover "$child" $(( depth - 1 ))
  done
}

_repowatcher_scan() {
  emulate -L zsh
  local root depth=${REPOWATCHER_DEPTH:-5}
  [[ $depth == <-> ]] || { print -u2 -- 'repowatcher: invalid scan depth.'; return 1; }
  local -A discovered
  local -a exclusions
  if (( ${+REPOWATCHER_EXCLUDE} )); then
    exclusions=( "${REPOWATCHER_EXCLUDE[@]}" )
  else
    exclusions=( .git .cache .local .Trash Library node_modules .venv venv )
  fi
  (( ${#REPOWATCHER_ROOTS} )) || { print -r -- 'repowatcher: configure REPOWATCHER_ROOTS to scan multiple repositories.'; return 0; }
  for root in "${REPOWATCHER_ROOTS[@]}"; do
    _repowatcher_discover "$root" "$depth"
  done
}

repowatcher() {
  emulate -L zsh
  local action=${1:-status}
  if [[ $action == help ]]; then
    print -r -- 'Usage: repowatcher [status|fetch|pull|scan|help]'
    return 0
  fi
  if [[ $action == scan ]]; then _repowatcher_scan; return $?; fi
  _repowatcher_context || { print -u2 -- 'repowatcher: no repository or invalid settings.'; return 1; }
  [[ -e $_rw_cache/lock ]] || (umask 077; : >> "$_rw_cache/lock")
  case $action in
    status)
      print -r -- "fetch=$_rw_fetch mode=$_rw_mode interval=${_rw_interval}s"
      _repowatcher_counts || { print -r -- 'No current branch with a valid upstream.'; return 1; }
      print -r -- "$_rw_ahead ahead, $_rw_behind behind (last fetched state)."
      ;;
    fetch) _repowatcher_fetch true ;;
    pull)
      _repowatcher_fetch true
      local fetched=$?
      if (( fetched != 0 )); then
        print -u2 -- "repowatcher: fetch failed or busy; see $_rw_cache/fetch.log"
        return $fetched
      fi
      _repowatcher_counts || return 1
      if (( _rw_behind == 0 )); then print -r -- 'repowatcher: no incoming commits.'; return 0; fi
      if (( _rw_ahead > 0 )); then print -r -- 'repowatcher: branches have diverged; update skipped.'; return 1; fi
      _repowatcher_pull "$_rw_head" "$_rw_upstream"
      ;;
    *) print -u2 -- "repowatcher: unknown command: $action"; return 2 ;;
  esac
}

[[ -o interactive ]] && add-zsh-hook precmd _repowatcher_prompt
# Sourcing must succeed in noninteractive shells too.
true
