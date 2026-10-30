#!/usr/bin/env bash
# Fetch separately, then explicitly deploy one reviewed full commit SHA.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd -- "$script_dir/.." && pwd)"
if [[ $# -lt 1 ]]; then
  echo 'Usage: OFFICE_ENV_FILE=~/office.env scripts/deploy-ec2.sh <exact-40-character-SHA> [--ci-verified-repo OWNER/REPO]' >&2
  exit 2
fi
if [[ -n "${OFFICE_ENV_FILE:-}" ]]; then
  set -a
  source "$OFFICE_ENV_FILE"
  set +a
fi
export PATH="$HOME/.local/node/bin:$PATH"
exec "$app_dir/backend/.venv/bin/python" "$script_dir/deploy_ec2.py" "$@"
