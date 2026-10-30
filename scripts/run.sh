#!/usr/bin/env bash
# -*- coding: utf-8 -*-

# Clones the specified repo (or resyncs a persistent local clone),
# runs its update tool and might git-push.
#
# Usage: run.sh <repo-url> [local-dir]
#   Without local-dir: fresh clone into a temp dir, removed on exit.
#   With local-dir:    reuse that clone, hard-resynced to origin/master;
#                      recloned if missing or broken.

set -euo pipefail

REPO_URL="${1:?Usage: $0 <repo-url> [local-dir]}"
LOCAL_DIR="${2:-}"
UPDATE_TXT="data/update.txt"
TIMESTAMP=$(date -u "+%Y-%m-%d %H:%M")

fresh_clone() {
  echo "Cloning $REPO_URL into $1..."
  git clone --recursive "$REPO_URL" "$1"
}

# Resync an existing clone to origin/master, discarding everything local.
resync() {
  local dir=$1
  [[ -d "$dir/.git" ]] &&
    [[ "$(git -C "$dir" remote get-url origin 2>/dev/null)" == "$REPO_URL" ]] &&
    git -C "$dir" fetch origin &&
    git -C "$dir" checkout -f -B master origin/master &&
    git -C "$dir" clean -ffdx &&
    git -C "$dir" submodule sync --recursive &&
    git -C "$dir" submodule update --init --recursive --force &&
    git -C "$dir" submodule foreach --recursive 'git clean -ffdx'
}

if [[ -z "$LOCAL_DIR" ]]; then
  WORKDIR=$(mktemp -d)
  trap 'echo "Cleaning up $WORKDIR..."; rm -rf "$WORKDIR"' EXIT
  fresh_clone "$WORKDIR"
else
  WORKDIR="$LOCAL_DIR"
  echo "Resyncing $WORKDIR..."
  if ! resync "$WORKDIR"; then
    if [[ -e "$WORKDIR" ]]; then
      # Only ever delete something that is a git repo; never a random dir.
      if [[ -d "$WORKDIR/.git" ]]; then
        echo "Local repo broken or mismatched, removing $WORKDIR..."
        rm -rf "$WORKDIR"
      elif [[ -n "$(ls -A "$WORKDIR")" ]]; then
        echo "Refusing to use $WORKDIR: non-empty and not a git repo" >&2
        exit 1
      fi
    fi
    fresh_clone "$WORKDIR"
  fi
fi

cd "$WORKDIR"

echo "Running update..."
./update.py

# Any new (untracked) zip files in data/?
NEW_FILES=$(git status --porcelain data/ | awk '/^\?\?/ {print $2}')

if [[ -n "$NEW_FILES" ]]; then
  echo "New files produced:"
  echo "$NEW_FILES"
  echo "$TIMESTAMP" > "$UPDATE_TXT"
  git add data/
  git commit -m "data: update $TIMESTAMP"
  git push origin master

else
  echo "No new files."

  # Check if update.txt is missing or older than 1 day
  NEEDS_BUMP=0
  if [[ ! -f "$UPDATE_TXT" ]]; then
    NEEDS_BUMP=1
  else
    LAST=$(cat "$UPDATE_TXT")
    LAST_EPOCH=$(date -ud "$LAST" "+%s" 2>/dev/null || date -ujf "%Y-%m-%d %H:%M" "$LAST" "+%s")
    NOW_EPOCH=$(date -u "+%s")
    if (( NOW_EPOCH - LAST_EPOCH > 86400 )); then
      NEEDS_BUMP=1
    fi
  fi

  if [[ "$NEEDS_BUMP" -eq 1 ]]; then
    echo "Bumping $UPDATE_TXT to $TIMESTAMP"
    echo "$TIMESTAMP" > "$UPDATE_TXT"
    git add "$UPDATE_TXT"
    git commit -m "data: heartbeat $TIMESTAMP"
    git push origin master
  else
    echo "update.txt is fresh, nothing to do."
  fi
fi
