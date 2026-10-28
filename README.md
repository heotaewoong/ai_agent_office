# HeoBrain AI 오피스

[로컬 작업실](http://localhost:3110) · [GitHub 저장소](https://github.com/heotaewoong/ai_agent_office)

개인용 콘텐츠 오피스의 소스 코드와 공개용으로 검토한 설계·벤치마킹 문서입니다. 실행과 검사는 [앱 안내](apps/content-office/README.md)를 따릅니다.

## 공개 문서

- [최신 통합 플레이북](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#content-system) · [보존한 로컬본](sites/heobrain-office-playbook-unified-20261027/dist/index.html)
- [오피스 월드 (3D 관제 공간)](sites/office-world/README.md) · [설계서](docs/superpowers/specs/2026-10-28-office-world-design.md) · [배경 조사와 결정](reports/3D%20오피스%20월드%20배경%20조사와%20결정.md)
- [AI 콘텐츠 에이전트 설계](docs/superpowers/specs/2026-10-27-ai-content-agent-design.md)
- [AI 콘텐츠 에이전트 구현 계획](docs/superpowers/plans/2026-10-27-ai-content-agent.md)
- [콘텐츠 자동화 벤치마킹](reports/AI%20콘텐츠%20자동화%20에이전트%20벤치마킹.md)
- [저장소 공개 범위와 업로드 전 확인](docs/repository-sharing.md)

개인 지식 원본, 유료 강의·회원 자료, 계정·인증 정보, 실행 장부와 제작 검토본은 로컬에 보관하며 이 저장소에 포함하지 않습니다. 이 자료를 참조하는 문서의 링크·기능은 별도 로컬 자료가 있어야 동작할 수 있습니다.

로컬 작업의 최종 문서 지도는 공개에서 제외한 `OFFICE_INDEX.md`에 있습니다. AI 작업자 공통 안내는 [AGENTS.md](AGENTS.md)입니다.

## 콘텐츠 자동화 설계와 제작 작업실

### 현재 정본 · 콘텐츠 자동화 v7.3.1

[처음 읽는 실행안](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-start.html) · [전체 도구·소스·자료 확보 상태](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.html) · [현재 정본 JSON](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.json) · [다른 AI용 갱신 키트](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/content-maintenance-kit.zip) · [키트 SHA256](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/content-maintenance-kit.sha256)

2026-10-28 KST 기준: 전체 설계는 도구49개·입력46개·전달채널12개·설계요구79개를 비교합니다. v7.3.1 안내 웹은 Site14/source `a4ff63f20edb3911849c79e139aa29ff884fc676`로 게시했고, 추가 핵심 회귀32개와 HTTPS 문서·ZIP 바이트 일치를 확인했습니다. 이는 정적 안내와 이관 검증이며 새 모델 생성·계정 연결·실제 콘텐츠 게시·발송·쿠폰/주문 실행의 검증이 아닙니다. 추가 요청의 09:54:57~13:54:57 검토 창은 진행 중입니다.

CLASS101 자료는 전부 확보 상태가 아닙니다. 최신 파일 대조와 과거 읽기 원장은 감사 대상·확인 시점이 달라 합산하지 않습니다. 회원 원문·개인 경로·계정·운영 DB·키는 이 저장소와 공개 갱신 키트에 넣지 않습니다. HTTPS의 기존 본인 전용 접근도 유지합니다.

다른 AI는 갱신 키트의 `KIT-README.md` → `README.md` → `dist/downloads/content-start.md` → `content-system/source.json` 순서로 읽습니다. 같은 정본을 고친 뒤 생성·검사·포장하고 현재 Sites 소스와 병합합니다. 같은 HTTPS를 게시할 접근 도구는 별도로 필요합니다. 실제 오피스가 있으면 먼저 그곳의 AGENTS·OFFICE_INDEX·앱 README를 대조합니다. 아래 인계 경로는 이전 스냅샷으로 보존하며 현재 Sites 정본을 덮어쓰지 않습니다.

### 보존한 이전 인계 스냅샷

[통합 HTTPS 설계](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#content-system) · [자료·원가·실습](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-studio/) · [인계 README](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/README.md) · [정본·업데이트](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/SOURCE.md) · [편집 소스](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/editable-source/README.md)

상위 v7.2의49도구·38입력과 보조 작업실의35세부도구·21선별출처는 서로 다른 범위입니다. PDF56개·3205쪽 파일감사와10종96쪽 선택읽기, 원가 가정 계산·후반작업·이관 소스를 보강했습니다. 실제 모델 생성·유료 호출·개별 게시·회차③ 발송·상품/쿠폰/주문 쓰기는 실행하지 않았습니다. 기존 본인 전용 HTTPS 접근을 유지합니다.
