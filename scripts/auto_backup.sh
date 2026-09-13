#!/usr/bin/env bash
# auto_backup.sh — hands-off git backup for peru-2027 (TravelGuide).
# Silent when there is nothing to back up. One line on action or error.
set -uo pipefail

REPO=/workspace/TravelGuide
cd "$REPO" || { echo "backup ERROR: cannot cd $REPO"; exit 1; }

export GIT_TERMINAL_PROMPT=0
git config --global --get-all safe.directory 2>/dev/null | grep -qx "$REPO" || git config --global --add safe.directory "$REPO" 2>/dev/null

DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
git fetch -q origin 2>/dev/null
AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)

if [ "$DIRTY" = "0" ] && [ "$AHEAD" = "0" ]; then
  exit 0
fi

CHANGED=""
if [ "$DIRTY" != "0" ]; then
  git add -A
  N=$(git diff --cached --name-only | wc -l | tr -d ' ')
  if [ "$N" != "0" ]; then
    STAMP=$(date -u +"%Y-%m-%d %H:%M UTC")
    git commit -q -m "Auto-backup ${STAMP} (${N} files)" || { echo "backup ERROR: commit failed"; exit 1; }
    CHANGED="committed ${N} files"
  fi
fi

BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
if [ "$BEHIND" != "0" ]; then
  git rebase -q origin/main || { echo "backup ERROR: rebase conflict — manual fix needed"; git rebase --abort 2>/dev/null; exit 1; }
fi

if ! git push -q origin main 2>/tmp/backup_push_err; then
  echo "backup ERROR: push failed — $(tail -1 /tmp/backup_push_err)"
  exit 1
fi

TOTAL=$(git rev-parse --short HEAD)
echo "backup OK: ${CHANGED:-pushed pending commits} -> ${TOTAL}"
