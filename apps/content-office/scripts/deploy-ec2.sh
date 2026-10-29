#!/usr/bin/env bash
# EC2 배포: 최신 main을 받아 테스트·빌드하고, 결과를 구조도 화면용 배포 기록(runtime/build-info.json)에 남긴 뒤 재시작한다.
# 사용: OFFICE_ENV_FILE=~/office.env apps/content-office/scripts/deploy-ec2.sh
# 추적 중인 파일이 서버에서 수정돼 있으면 멈춘다(덮어쓰지 않음). 테스트가 실패하면 재시작하지 않는다.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd -- "$script_dir/.." && pwd)"
repo_dir="$(git -C "$app_dir" rev-parse --show-toplevel)"
export PATH="$HOME/.local/node/bin:$PATH"

cd "$repo_dir"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "중단: 서버에서 추적 중인 파일이 수정돼 있습니다."
  git status --short --untracked-files=no
  exit 2
fi
git fetch -q origin
git reset -q --hard origin/main
git log --oneline -1

cd "$app_dir/backend"
backend_summary="$(.venv/bin/python -m pytest -q 2>&1 | tail -1)"
echo "백엔드: $backend_summary"
if [[ "$backend_summary" == *failed* || "$backend_summary" == *error* ]]; then
  echo "중단: 백엔드 테스트 실패. 재시작하지 않습니다."
  exit 3
fi

cd "$app_dir/frontend"
npm ci --no-audit --no-fund >/dev/null 2>&1
npm run typecheck >/dev/null
frontend_summary="$(npm test 2>&1 | grep -E '^ℹ (pass|fail)' || true)"
echo "화면: $(echo "$frontend_summary" | tr '\n' ' ')"
if ! grep -q "ℹ fail 0" <<<"$frontend_summary"; then
  echo "중단: 화면 테스트 실패. 재시작하지 않습니다."
  exit 4
fi
NODE_OPTIONS=--max-old-space-size=1200 nice -n 15 npm run build 2>&1 | grep -E "Compiled|rror" | head -3

cd "$app_dir/backend"
if [[ -n "${OFFICE_ENV_FILE:-}" ]]; then set -a; source "$OFFICE_ENV_FILE"; set +a; fi
.venv/bin/python -m office.architecture record --backend "$backend_summary" --frontend "$frontend_summary" >/dev/null

cd "$app_dir"
scripts/stop-local.sh >/dev/null 2>&1 || true
OFFICE_ENV_FILE="${OFFICE_ENV_FILE:-}" scripts/start-local.sh >/dev/null 2>&1
sleep 8
curl -s -o /dev/null -w "backend %{http_code}\n" http://127.0.0.1:8510/api/session
curl -s -o /dev/null -w "frontend %{http_code}\n" http://127.0.0.1:3110/
