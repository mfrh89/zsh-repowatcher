# Load with any Zsh plugin manager or source this file directly.
[[ -n ${_REPOWATCHER_LOADED-} ]] && return 0
typeset -g _REPOWATCHER_LOADED=1
zmodload zsh/datetime
zmodload zsh/stat
zmodload zsh/system
zmodload zsh/zselect

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
  typeset -g _rw_branch _rw_head _rw_upstream='' _rw_upstream_ref='' _rw_ahead=0 _rw_behind=0
  _rw_branch=$(command git symbolic-ref -q --short HEAD) || return 1
  _rw_head=$(command git rev-parse --verify HEAD 2>/dev/null) || return 1
  if _rw_upstream=$(command git rev-parse --verify '@{upstream}' 2>/dev/null); then
    _rw_upstream_ref=$(command git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)
    local counts=$(command git rev-list --left-right --count "$_rw_head...$_rw_upstream" 2>/dev/null) || return 1
    local -a values=( ${(z)counts} )
    _rw_ahead=$values[1]; _rw_behind=$values[2]
  else
    _rw_upstream=''
  fi
  _repowatcher_base
  return 0
}

# Resolve the remote default branch without guessing that it is named main.
_repowatcher_base() {
  emulate -L zsh
  local base remote
  typeset -g _rw_base='' _rw_base_ref='' _rw_base_behind=0
  base=$(command git config --local --get repowatcher.base 2>/dev/null)
  [[ $base == off ]] && return 0
  if [[ -z $base ]]; then
    remote=$(command git config --get "branch.$_rw_branch.remote" 2>/dev/null)
    [[ -n $remote && $remote != . ]] || remote=origin
    base=$(command git symbolic-ref -q "refs/remotes/$remote/HEAD" 2>/dev/null) || return 0
  fi
  local commit=$(command git rev-parse --verify --end-of-options "${base}^{commit}" 2>/dev/null) || return 0
  [[ -n $commit && $commit != $_rw_upstream ]] || return 0
  typeset -g _rw_base=$commit _rw_base_ref=${base#refs/remotes/}
  _rw_base_behind=$(command git rev-list --count "$_rw_head..$_rw_base" 2>/dev/null) || _rw_base_behind=0
}

# Git subjects, branch names, and paths must never inject terminal controls.
_repowatcher_text() {
  emulate -L zsh
  local value=${1//[[:cntrl:]]/ } limit=$2
  (( ${#value} > limit )) && value="${value[1,$((limit - 1))]}…"
  typeset -g REPLY=$value
}

_repowatcher_commit_link() {
  emulate -L zsh
  local hash=$1 ref=$2 remote url host project prefix
  typeset -g REPLY=${hash[1,7]} _rw_linked=false
  local mode=${REPOWATCHER_LINKS:-auto}
  [[ $mode != off ]] || return 0
  if [[ $mode != on ]]; then
    [[ -t 1 && $TERM != dumb ]] || return 0
    [[ ${TERM_PROGRAM-} == (iTerm.app|WezTerm|vscode|ghostty) || ${TERM-} == (xterm-ghostty|xterm-kitty) ]] || return 0
  fi
  # Resolve the remote from the actual tracking ref, including remote names with slashes.
  local fullref=$(command git rev-parse --symbolic-full-name --verify --end-of-options "$ref" 2>/dev/null)
  [[ $fullref == refs/remotes/* ]] || return 0
  local candidate
  for candidate in ${(f)"$(command git remote)"}; do
    if [[ $fullref == refs/remotes/$candidate/* && ${#candidate} -gt ${#remote} ]]; then remote=$candidate; fi
  done
  [[ -n $remote ]] || return 0
  url=$(command git remote get-url "$remote" 2>/dev/null) || return 0
  case $url in
    https://*|http://*) url=${url#*://} ;;
    git@*:*) url=${url#git@}; url=${url/:/\/} ;;
    ssh://git@*) url=${url#ssh://git@} ;;
    *) return 0 ;;
  esac
  host=${url%%/*}
  project=${url#*/}
  project=${project%.git}
  [[ -n $project && $project != *[^a-zA-Z0-9._/-]* ]] || return 0
  case $host in
    github.com) prefix="https://$host/$project/commit/" ;;
    gitlab.com) prefix="https://$host/$project/-/commit/" ;;
    bitbucket.org) prefix="https://$host/$project/commits/" ;;
    *) return 0 ;;
  esac
  _rw_linked=true
  REPLY=$'\e]8;;'"$prefix$hash"$'\e\\'"${REPOWATCHER_LINK_ICON:-} ${hash[1,7]}"$'\e]8;;\e\\'
}

_repowatcher_cell() {
  emulate -L zsh
  local value=$1 width=$2
  # Zsh's m flag measures terminal columns, including wide Unicode characters.
  if (( ${(m)#value} > width )); then
    while (( ${(m)#value} > width - 1 )); do value=${value[1,-2]}; done
    value+='…'
  fi
  typeset -g REPLY="${(mr:$width:)value}"
}

_repowatcher_border() {
  emulate -L zsh
  local left=$1 middle=$2 right=$3 line=$1 empty='' width index
  for index in {1..6}; do
    width=$(( widths[index] + 2 ))
    line+="${(l:$width::─:)empty}"
    if (( index == 6 )); then line+=$right; else line+=$middle; fi
  done
  print -r -- "$line"
}

_repowatcher_render() {
  emulate -L zsh
  local -a headers=(REPO BRANCH KIND SOURCE COMMIT DESCRIPTION) widths=(4 6 4 6 7 11) minimum=(4 6 4 6 7 8)
  local index column row total widest value line padded hash ref
  for (( index=1; index<=${#cells}; index++ )); do
    column=$(( (index - 1) % 6 + 1 ))
    value=$cells[index]
    (( ${(m)#value} > widths[column] )) && widths[column]=${(m)#value}
  done
  minimum[5]=$widths[5]
  local available=${COLUMNS:-120}
  [[ $available == <-> ]] || available=120
  (( available > 0 )) || available=120
  # Six cells need 19 columns for padding and separators.
  while true; do
    total=19
    for column in {1..6}; do (( total += widths[column] )); done
    (( total <= available )) && break
    widest=0
    for column in {1..6}; do
      if (( widths[column] > minimum[column] && (widest == 0 || widths[column] > widths[widest]) )); then widest=$column; fi
    done
    (( widest > 0 )) || break
    (( widths[widest]-- ))
  done
  print
  _repowatcher_border '┌' '┬' '┐'
  line='│'
  for column in {1..6}; do
    _repowatcher_cell "$headers[column]" "$widths[column]"
    line+=" $REPLY │"
  done
  if [[ -t 1 && $TERM != dumb && ! -v NO_COLOR ]]; then
    print -r -- $'\e[1m'"$line"$'\e[22m'
  else
    print -r -- "$line"
  fi
  _repowatcher_border '├' '┼' '┤'
  for (( row=1; row<=${#hashes}; row++ )); do
    line='│'
    for column in {1..6}; do
      index=$(( (row - 1) * 6 + column ))
      _repowatcher_cell "$cells[index]" "$widths[column]"
      padded=$REPLY
      if (( column == 5 )) && [[ -n $hashes[row] ]]; then
        # Store links separately so control sequences never affect column sizing.
        local visible=$cells[index]
        padded="$rendered_links[row]${padded[$(( ${#visible} + 1 )),-1]}"
      fi
      line+=" $padded │"
    done
    print -r -- "$line"
  done
  _repowatcher_border '└' '┴' '┘'
}

_repowatcher_table() {
  emulate -L zsh
  (( _rw_behind > 0 || _rw_base_behind > 0 )) || return 0
  local repo branch source kind ref count line hash subject index
  local -a cells hashes row_refs rendered_links
  _repowatcher_text "${_rw_root:t}" 1000; repo=$REPLY
  _repowatcher_text "$_rw_branch" 1000; branch=$REPLY
  local -a kinds=(upstream base) refs=("$_rw_upstream_ref" "$_rw_base_ref") counts=("$_rw_behind" "$_rw_base_behind") commits=("$_rw_upstream" "$_rw_base")
  for index in 1 2; do
    kind=$kinds[$index]; ref=$refs[$index]; count=$counts[$index]
    (( count > 0 )) || continue
    _repowatcher_text "$ref" 1000; source=$REPLY
    for line in ${(f)"$(command git --no-pager log -5 --format='%H%x09%s' "$_rw_head..$commits[$index]" 2>/dev/null)"}; do
      hash=${line%%$'\t'*}; subject=${line#*$'\t'}
      _repowatcher_text "$subject" 50; subject=$REPLY
      _repowatcher_commit_link "$hash" "$ref"
      rendered_links+=("$REPLY")
      local label=${hash[1,7]}
      [[ $_rw_linked == true ]] && label="${REPOWATCHER_LINK_ICON:-} $label"
      cells+=("$repo" "$branch" "$kind" "$source" "$label" "$subject")
      hashes+=("$hash"); row_refs+=("$ref")
    done
    if (( count > 5 )); then
      cells+=("$repo" "$branch" "$kind" "$source" '' "… $((count - 5)) more commits")
      hashes+=(''); row_refs+=(''); rendered_links+=('')
    fi
  done
  _repowatcher_render
  (( _rw_base_behind > 0 )) && print -r -- 'Base commits are informational; Apply updates the upstream only.'
  return 0
}

_repowatcher_pull() {
  emulate -L zsh
  local expected_head=$1 expected_upstream=$2 expected_branch=${3:-$_rw_branch} fd gitdir marker dirty
  zsystem flock -t 0 -f fd "$_rw_cache/lock" 2>/dev/null || {
    print -r -- 'repowatcher: another check is running; try again.'; return 2
  }
  {
    _repowatcher_counts || return 1
    [[ $_rw_head == $expected_head && $_rw_upstream == $expected_upstream && $_rw_branch == $expected_branch ]] || {
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
  (( _rw_behind > 0 || _rw_base_behind > 0 )) || return 0
  local key="$_rw_root:$_rw_head:$_rw_upstream:$_rw_base:$_rw_mode"
  [[ -z ${_repowatcher_seen[$key]-} ]] || return 0
  local name=${_rw_root:t}
  if zle 2>/dev/null; then
    # Paint the real theme prompt before handing the terminal to the notice.
    zle -R
    zle -I
  fi
  _repowatcher_table
  if (( _rw_behind == 0 )); then
    _repowatcher_seen[$key]=1
    return 0
  fi
  if (( _rw_ahead > 0 )); then
    print -r -- "repowatcher: $name has diverged ($_rw_ahead ahead, $_rw_behind behind); update skipped."
    _repowatcher_seen[$key]=1
    return 0
  fi
  # Only mutate after a successful recent fetch, never based on stale refs.
  local -A info
  local fresh=false
  if zstat -H info "$_rw_cache/success" 2>/dev/null && (( EPOCHSECONDS - info[mtime] <= _rw_interval )); then
    fresh=true
  fi
  if [[ $_rw_mode == auto && $fresh == true ]]; then
    _repowatcher_pull "$_rw_head" "$_rw_upstream"
    (( $? == 2 )) && return 0
  elif [[ $_rw_mode == ask && -o interactive && -t 1 ]] && { [[ -t 0 ]] || zle 2>/dev/null; }; then
    # ZLE owns stdin while a widget runs; inspect its pending input instead.
    if zle 2>/dev/null; then
      (( PENDING > 0 || KEYS_QUEUED_COUNT > 0 )) && return 0
      [[ -n $BUFFER ]] && return 0
    else
      zselect -t 0 -r 0 2>/dev/null && return 0
    fi
    local answer confirmed=false
    if zle 2>/dev/null; then
      # line-init runs before ZLE enters raw input mode; read a full tty line.
      print -n -- 'Apply now? [y/N] '
      if IFS= read -r answer </dev/tty; then
        [[ $answer == (y|Y|yes|YES) ]] && confirmed=true
      fi
    elif read -q 'answer?Apply now? [y/N] '; then
      confirmed=true
    fi
    if [[ $confirmed == true ]]; then
      print
      local preview_head=$_rw_head preview_upstream=$_rw_upstream preview_branch=$_rw_branch
      if _repowatcher_fetch true; then
        _repowatcher_pull "$preview_head" "$preview_upstream" "$preview_branch"
        local applied=$?
        # A concurrent fetch/branch change needs a new preview, not a silent update.
        (( applied != 0 )) && return 0
      else
        print -r -- 'repowatcher: fetch failed or busy; update skipped.'
        return 0
      fi
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
    # Preserve the caller's cwd; report checked/failed/skipped/incoming as 0/1/2/3.
    (
      builtin cd -- "$directory" || exit 1
      _repowatcher_context || exit 1
      [[ $_rw_mode != off && $_rw_fetch == true ]] || exit 2
      [[ -e $_rw_cache/lock ]] || (umask 077; : >> "$_rw_cache/lock")
      _repowatcher_fetch false && [[ -e $_rw_cache/success ]] || {
        _repowatcher_text "$directory" 1000
        print -r -- "repowatcher: $REPLY: fetch failed or busy."
        exit 1
      }
      _repowatcher_counts || exit 2
      [[ -n $_rw_upstream || -n $_rw_base ]] || exit 2
      _repowatcher_table
      (( _rw_ahead > 0 && _rw_behind > 0 )) && print -r -- "repowatcher: branches have diverged ($_rw_ahead ahead, $_rw_behind behind); update skipped."
      (( _rw_behind > 0 || _rw_base_behind > 0 )) && exit 3
      exit 0
    )
    local scan_result=$?
    case $scan_result in
      0|3)
        (( scan_result == 3 )) && (( ++incoming ))
        (( ++checked ))
        discovered[$canonical]=checked
        ;;
      2) (( ++skipped )) ;;
      *) (( ++failed )) ;;
    esac
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
  local -i checked=0 incoming=0 skipped=0 failed=0
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
  if (( ${#discovered} == 0 )); then
    print -r -- 'repowatcher: scan complete: no repositories found.'
  else
    print -r -- "repowatcher: scan complete (last fetched state): $checked checked, $incoming with incoming commits, $skipped skipped, $failed failed."
  fi
  # The explicit scan already displayed this repository; do not repeat it when the prompt returns.
  if _repowatcher_context && [[ ${discovered[$_rw_root]-} == checked ]] && _repowatcher_counts; then
    local shown_key="$_rw_root:$_rw_head:$_rw_upstream:$_rw_base:$_rw_mode"
    _repowatcher_seen[$shown_key]=1
  fi
  return 0
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
      [[ -n $_rw_upstream ]] || print -r -- "No upstream configured; base information only."
      _repowatcher_table
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
      [[ -n $_rw_upstream ]] || { print -r -- "repowatcher: no upstream configured."; return 1; }
      if (( _rw_behind == 0 )); then print -r -- 'repowatcher: no incoming commits.'; return 0; fi
      if (( _rw_ahead > 0 )); then print -r -- 'repowatcher: branches have diverged; update skipped.'; return 1; fi
      _repowatcher_pull "$_rw_head" "$_rw_upstream"
      ;;
    *) print -u2 -- "repowatcher: unknown command: $action"; return 2 ;;
  esac
}

if [[ -o interactive ]]; then
  zmodload zsh/zle
  autoload -Uz add-zle-hook-widget
  add-zle-hook-widget line-init _repowatcher_prompt
fi
# Sourcing must succeed in noninteractive shells too.
true
