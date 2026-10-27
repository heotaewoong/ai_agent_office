# HeoBrain 콘텐츠 스튜디오 · 편집 가능한 소스

v7.1 검토 보강판의 새 콘텐츠 경로만 포함한다. 기존 전체 플레이북은 HTTPS 링크로 연다.

필요 환경: Python 3.11 이상. JavaScript 검산은 Node.js 18 이상. 추가 패키지 설치는 없다.

전체 설계는 https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.html 의 정본을 먼저 읽는다. integrated-guide.md/json이 있으면 상위 설계의 읽기용 스냅샷이며 이 작업실 코드와 구분한다.

1. `content-studio/README.md`와 `content-studio/master-guide.md`부터 읽는다.
2. Python 표준 라이브러리로 `python scripts/build-content-studio.py`를 실행한다.
3. Node가 있으면 `node scripts/check-content-costs.cjs`, `node --check dist/content-studio/app.js`를 확인한다.
4. `python scripts/validate-content-studio.py`로 계약·링크·해시·내보내기를 확인한다.
5. `python -m http.server 8769 --bind 127.0.0.1 --directory dist` 후 http://127.0.0.1:8769/content-studio/ 를 연다.

설정·DB·API 키·로그인·회원 원문은 없다. 계산기는 가정을 계산하며 생성·게시·발송·결제를 하지 않는다.
사이트 정본은 site-target.json의 기존 Sites 연결 저장소다. 최신 버전·접근 범위를 보존해 병합한다. source.zip의 예전 사본으로 최신 원격 소스를 덮어쓰지 않는다.
