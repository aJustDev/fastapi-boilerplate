#!/usr/bin/env bash
# Installs the repo's git hooks: the pre-push hook from scripts/git-hooks/ and the
# pre-commit hook (ruff) from .pre-commit-config.yaml.
# Usage: bash scripts/install-hooks.sh

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
hooks_src="$(cd "$(dirname "$0")" && pwd)/git-hooks"

for hook_path in "$hooks_src"/*; do
  dest="$repo_root/.git/hooks/$(basename "$hook_path")"
  cp "$hook_path" "$dest"
  chmod +x "$dest"
  echo "installed: $dest"
done

# Without `pre-commit install`, .pre-commit-config.yaml does nothing. It also rewrites
# the hook if it points at a virtualenv that no longer exists.
if uv run pre-commit install >/dev/null 2>&1; then
  echo "installed: $repo_root/.git/hooks/pre-commit (pre-commit)"
else
  echo "WARNING: could not install the pre-commit hook; run 'uv sync' and retry." >&2
fi
