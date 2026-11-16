#!/usr/bin/env bash
set -euo pipefail
REPO="VectorLatch/mister-floppy-lab"
command -v git >/dev/null || { echo 'Install Git first.' >&2; exit 1; }
command -v gh >/dev/null || { echo 'Install GitHub CLI: brew install gh' >&2; exit 1; }
gh auth status || { echo 'Run: gh auth login' >&2; exit 1; }
if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repository $REPO already exists. Refusing to overwrite it." >&2
  exit 1
fi
cd "$(dirname "$0")/.."
if [ -e .git ]; then
  echo 'This folder already has a Git repository; refusing to change it.' >&2
  exit 1
fi
git init -b main
git add .
git commit -m 'Initialize clean pinned Minimig + Physical Floppy baseline'
gh repo create "$REPO" --public --source=. --remote=origin --push
echo "Created: https://github.com/$REPO"
echo "Actions: https://github.com/$REPO/actions"
