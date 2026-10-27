# HeoBrain 콘텐츠 자동화 — 다음 AI 작업자를 위한 README

이 패키지는 콘텐츠 오피스 v5/v6의 구조를 보존한 v7.1 도구 비교·운영 설계·개발 인계본이다. 실제 콘텐츠 생성·발행 시스템을 새로 연결한 배포물이 아니다.

전체 설계·도구 선정의 정본은 [통합 콘텐츠 v7.2](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.html)와 content-system/source.json이다. 이 작업실의 content.json·cost-scenarios.json은 원가 실습·자료 감사·세부 근거를 담당한다. 정본의49도구·38입력과 이 보강의35도구·21선별출처는 범위가 다르므로 합산하지 않는다. 상위 설계 스냅샷이 포함된 경우 integrated-guide.md·json으로 구분하고 최신 변경은 정본에서 시작한다.

## 읽는 순서

1. 실제 오피스 저장소의 AGENTS·OFFICE_INDEX·README를 먼저 읽는다.
2. master-guide.md에서 목적·상태·승인·전체 흐름을 읽는다.
3. hub-data.json에서 요청 도구 대응·제안 선택·소스·채널·자료 확보 상태를 확인한다.
4. pipeline-blueprint.json에서 게이트·작업 인계·실패 처리·기본 지출 0을 확인한다.
5. models-and-rights.md, voice-distribution.md, source-benchmarking.md, quality-evaluation.md와 아이디어 모음에서 필요한 근거를 읽는다.
6. 실제 앱 README·traceability와 대조해 구현 작업을 하나 고른다.

PDF 확보 수량과 실제 읽은 범위는 master-guide.md·pdf-design-evidence.md를 함께 본다. 실제 HeoBrain 상품·채널 관찰과 파일럿은 brand-fit.md에 있다. 이 문서들의 제안을 이미 생성·게시된 콘텐츠로 표시하지 않는다.

production-economics.md에는 제작경로별 후보·도입 조건과 가정 원가 계산이 있다. youtube-benchmark-sample.md는 제목·작성자 소개 수준의 4개 표본이며 실제 시청·자막 확인은 하지 않았다. 다음 작업자는 현재 기본 제공자·가격 확인일·가정/실측·결정 이유를 보존한다.

finishing-audio-rights.md에는 자막·정렬·청취·음원 권리·믹스의 후반작업을, public-signals.md와 latest-signal-decisions.md에는 1회 메타데이터 수집과 별도 본문 검토의 차이를 정리했다. 원문 확보 수준을 올릴 때는 실제 읽은 URL·부문만 갱신한다.

## 바꾸지 않는 결정

- 18부서·144 OF·37 EX·29 전문 분야와 기존 Next.js·FastAPI·Python·SQLite·FFmpeg 뼈대를 유지한다.
- ⓪ 기획 선택 · ① 원고 · ② 출력별 출고 · ③ 뉴스레터/홍보 회차의 의미를 유지한다.
- 에이전트가 승인을 만들지 않는다. 문서 업데이트는 생성비·개별 게시·메일·쿠폰·주문 변경의 승인이 아니다.
- 개인학습 원문·유료 강의·개인 원고·계정·키·로그인 상태를 웹·공개 저장소·인계 ZIP에 넣지 않는다.
- 구현·공식 문서 확인·실제 생성·실제 한국어 품질·실제 게시·실제 성과를 각각 표시한다.

## 사이트 소스를 가진 경우

원본은 content-studio/content.json과 master-guide.md, README.md 및 검토한 research 문서다. scripts/build-content-studio.py가 다운로드 문서·작업 계약·인계 ZIP을 만든다. dist/content-studio의 화면 세 파일은 표현 계층이다.

가정 원가의 가격·확인일·세 제작경로 입력은 content-studio/cost-scenarios.json이 정본이며 생성기가 hub.cost_model과 다운로드 cost-model.json으로 내보낸다. 계산기의 값은 견적·실측·승인 예산이 아니다. 새 단가나 수용 기준을 바꿀 때 공식 근거와 가정을 함께 갱신한다.

명령:

필요 환경: Python 3.11 이상. JavaScript 검산용 Node.js 18 이상. 별도 패키지 설치는 필요하지 않다.

    python scripts/build-content-studio.py
    node --check dist/content-studio/app.js
    python scripts/validate-content-studio.py
    python -m http.server 8769 --bind 127.0.0.1 --directory dist

로컬 화면: http://127.0.0.1:8769/content-studio/

배포는 기존 .openai/hosting.json의 project_id·접근 범위를 유지하고 해당 Sites의 현재 원격 소스에서 진행한다. 사이트 전체를 다른 프로젝트 ID로 바꾸거나 기존 complete/source-kits 경로를 지우지 않는다. 지금 접속하는 계정과 게시 대상의 권한을 다시 확인한다.

## 다운로드 ZIP만 가진 경우

상대 경로의 Markdown과 JSON부터 읽는다. 이 ZIP은 문서·계약·필요한 공개 근거를 전달하며, 기존 오피스의 DB·모델 키·계정·개인 자료는 포함하지 않는다. 서비스 연결을 원하면 실제 저장소·운영자·계정 권한을 별도로 확인한다.

content-studio-source.zip은 별도 편집용 소스다. 새 콘텐츠 경로의 HTML·CSS·JavaScript·가정 데이터·생성기·검사와 SOURCE_MANIFEST.json을 포함한다. 기존 전체 플레이북 경로는 실제 HTTPS 링크로 연결하며 그 원문을 통째로 복제하지 않는다. 압축 해제한 소스의 README 명령으로 HTTP 미리보기를 열 수 있다. 본인 전용 Sites 접근과 실제 앱 권한이 소스 ZIP으로 이전되는 것은 아니다.

## 업데이트 절차

1. 변경할 질문·근거·파일과 기존 결정을 먼저 기록한다.
2. 모델/서비스의 공식 페이지를 직접 읽고 확인일·모델 ID·제공 경로·버전·비용·권리를 갱신한다. 도구 비교의 비용 요약과 cost-scenarios.json의 단가·가정도 같은 근거·확인일에 맞춘다.
3. 실제로 시험하지 않았으면 generated/tested/account_connected 상태를 켜지 않는다.
4. content.json과 해당 원본문서만 바꾸고 생성물을 다시 만든다.
5. 29개 요청 이름의 대응, ID/링크, 승인 의미, 지출 0 기본값, 비공개 원문 제외, 모바일·키보드·검색·빈 결과·콘솔을 확인한다.
6. 문서판·사이트·JSON·ZIP의 버전과 해시를 대조한다. 기존 사이트 원격 버전이 바뀌었으면 병합하고 다시 확인한다.
7. 실제 오피스 README·OFFICE_INDEX·변경 기록에 최신 링크와 검증/미검증 범위를 기록한다.

## 다음 모델에게 전달할 작업 지시

최신 README와 AGENTS·OFFICE_INDEX를 읽고 현재 구현·변경 파일·기존 작업을 먼저 확인하세요. 이 패키지의 설계와 실제 앱 코드를 구분한 뒤 하나의 작업을 선택하세요. 새 근거·결정·최소 변경·검증·복귀 방법을 기록하고 관련 원본과 생성물을 함께 갱신하세요. 개인 자료·키·계정·권한을 임의로 가져오거나 유료 호출·게시·발송·쿠폰/결제를 실행하지 마세요. 승인이 필요한 단계는 현재 사용자 요청의 실제 범위로 판단하세요. 완료 보고에는 수정·생성 파일, 외부 변경, 이번 검증, 남은 항목을 구분하세요.
