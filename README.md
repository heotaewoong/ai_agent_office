# HeoBrain AI 오피스

## 메인 콘텐츠 자동화 계획서

[2026-10-29 콘텐츠 파이프라인·리드마그넷 보완](reports/2026-10-29-content-pipeline.md) · [AI 자동화 무료 체험 작업표 초안](reports/2026-10-29-ai-automation-workbook.md). 학습/생산성 두 영역의 무료 자료 제작→제공→전달→선택적 후속 안내→관련 상품을 구분한 설계이며 실제 수집·발송 연결은 별도입니다.

HeoBrain의 상위 사업 영역은 **학습·시험 준비**와 **개인·업무·콘텐츠 생산성**입니다. 편입·자격증·개별 자동화는 그 안의 세부 분야와 실험입니다. 첫4주 마케팅 목표는 **브랜드 신뢰·검색 유입·자료 사용**과 **기존 학습 상품 구매 전환**이며, 도메인 조사→전략→페르소나→콘텐츠→성과 회고 순서로 기획합니다. 상위 전략·발표 근거와 미확인 범위는 로컬 문서 지도에서 관리합니다. 이것이 기존 안내 웹·앱에 새 기능이나 측정 연결을 구현했다는 뜻은 아닙니다.

**현재 정본: v7.5.0 · 2026-10-28 KST · Sites 판본21.** 기존 본인 전용 HTTPS에 source `20136eba96f99e867ba9bdb795cc7e0341a510b1`를 게시했고 실제 화면의 판본·TTJ 도구2개·51도구/46입력·독립 배치도 로드를 확인했습니다. [최신 Markdown](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/content-system-v7.md) · [현재 JSON](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.json) · [갱신 키트](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/content-maintenance-kit.zip). 키트 SHA256: `e276ac5178cded9f381e3eeda9b255a56002536789d9cf29a23bf0bc254695d9`.

앞으로 콘텐츠 자동화는 [이 통합 플레이북](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#content-system)을 메인 계획서로 삼아 계속 업그레이드합니다. 처음에는 [짧은 실행안](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-start.html) → [메인 실행계획 M0~M5](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#cs7-master-plan) → 필요한 도구·근거 순서로 읽습니다.

- 편집 정본은 **연결된 Sites 소스 저장소의 `content-system/source.json`**입니다. 이 앱 저장소의 보존 `sites/.../dist/`와 v7.1 인계본은 최신 원본이 아닙니다.
- 같은 JSON에서 웹·Markdown·다운로드·갱신 키트를 생성합니다. 새 대화나 다른 AI도 별도 메인 계획서를 만들지 않고 기존 공정·요구에 보완 내용을 합칩니다.
- 구현 순서: **실제 지원/배치 확인 → Hermes 요청·조회·검토 연결 → 원고1편+60초 영상 → 한 채널 전달/대사 → 뉴스레터③·관련 상품 → 한 공정씩 품질 비교**.
- 사람 승인 ⓪·①·②·③, 원고① 뒤 독립 제작, 하나의 장부/예약 소유자, 성공 자산과 불명 결과를 보존합니다. 에이전트는 사람 승인·작업 시간·예산을 늘리지 않습니다.
- 현재 코드는 수동 출고와 YouTube private 어댑터를 구분합니다. private 전달 코드 존재가 실제 계정 성공·공개/예약 지원을 뜻하지 않습니다. Hermes/Claude/Codex 사용자 운영 환경과 콘텐츠 앱의 연결 상태도 별도로 확인합니다.

[TTJ 영상 적용과 기존 Excalidraw 보강 위치](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#cs7-ttj_benchmark): 자동자막 전체·공개 도구 UI를 확인해 수동 발견2도구, 독자 효용 선별, 빈 작업 확인, 사람이 승인한 수정 규칙을 추가했습니다. [SVG](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/ttj-pipeline-placement-v7.svg) · [편집 가능한 Excalidraw](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/ttj-pipeline-placement-v7.excalidraw)는 독립 부품도입니다. 원본 방·계정/API·앱/EC2 설정은 이번 작업에서 변경하지 않았습니다.

정본 수정 → 근거/판본/변경 이유 기록 → 생성·검사 → 기존 HTTPS 갱신 → 게시 영수증·이 README·로컬 문서 지도 갱신 순서로 관리합니다. 사이트는 안내/계획이며 이 갱신이 앱·EC2 배포, 채널 게시·발송·쿠폰 실행 권한을 만들지 않습니다.

[로컬 작업실](http://localhost:3110) · [GitHub 저장소](https://github.com/heotaewoong/ai_agent_office)

개인용 콘텐츠 오피스의 소스 코드와 공개용으로 검토한 설계·벤치마킹 문서입니다. 실행과 검사는 [앱 안내](apps/content-office/README.md)를 따릅니다.

## 공개 문서

- [최신 통합 플레이북](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#content-system) · [보존한 로컬본](sites/heobrain-office-playbook-unified-20261027/dist/index.html)
- [오피스 월드 (3D 관제 공간)](sites/office-world/README.md) · [설계서](docs/superpowers/specs/2026-10-28-office-world-design.md) · [배경 조사와 결정](reports/3D%20오피스%20월드%20배경%20조사와%20결정.md)
- [AI 콘텐츠 에이전트 설계](docs/superpowers/specs/2026-10-27-ai-content-agent-design.md)
- [AI 콘텐츠 에이전트 구현 계획](docs/superpowers/plans/2026-10-27-ai-content-agent.md)
- [콘텐츠 오피스 작업 보고 2026-10-28](reports/2026-10-28%20콘텐츠%20오피스%20작업%20보고.md) · 유료 제공자 연결·EC2 준비 상태
- [콘텐츠 자동화 벤치마킹](reports/AI%20콘텐츠%20자동화%20에이전트%20벤치마킹.md)
- [저장소 공개 범위와 업로드 전 확인](docs/repository-sharing.md)

개인 지식 원본, 유료 강의·회원 자료, 계정·인증 정보, 실행 장부와 제작 검토본은 로컬에 보관하며 이 저장소에 포함하지 않습니다. 이 자료를 참조하는 문서의 링크·기능은 별도 로컬 자료가 있어야 동작할 수 있습니다.

로컬 작업의 최종 문서 지도는 공개에서 제외한 `OFFICE_INDEX.md`에 있습니다. AI 작업자 공통 안내는 [AGENTS.md](AGENTS.md)입니다.

## 콘텐츠 자동화 설계와 제작 작업실

### 이전 검증 기록 · 콘텐츠 자동화 v7.3.3

[처음 읽는 실행안](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-start.html) · [전체 도구·소스·자료 확보 상태](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.html) · [현재 정본 JSON](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.json) · [다른 AI용 갱신 키트](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/content-maintenance-kit.zip) · [키트 SHA256](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/downloads/content-maintenance-kit.sha256)

2026-10-28 KST 기준: 도구49개·입력46개·전달채널12개·설계요구79개를 비교한 안내·이관 정본입니다. v7.3.3은 Site18/source `0d186418f196cfb56fd7ce5d846abe21472c0de4`로 14:42 KST 게시했고, 실제 HTTPS Markdown·ZIP이 검증한 원본과 바이트까지 일치합니다. 키트 SHA256은 `4ce2df4047d6a1c47fda3944e4fd599b4348691e67b2c478e4d10b37cf2c55ad`입니다.

추가 검토 요청 창은 09:54:57~13:54:57 KST, 마감 상태 기록은 14:38:46 KST입니다. 13:55 경계 확인 이후 지연된 마감 처리·게시를 추가 조사나 연속 독해·모델 실험 시간으로 세지 않습니다. 이전 04~08시 기록은 별도로 보존합니다.

- 현재 구현: 같은 JSON에서 짧은·전체 안내와 이관 자료를 생성합니다. 기존 앱의 Gemini·Pillow·FFmpeg 기준선은 유지합니다.
- 이번 검증 완료: v7.3.2의 핵심 회귀35개와 영향2개 보완 검증, v7.3.3 마감 관련 회귀4개, 생성물13개·구조 검사·정확 재포장·HTTPS 문서/ZIP 일치입니다. 보조292검사는 변경 없는 Site16 작업실의 기록이며 앱 전체 실행시험이 아닙니다.
- 계획/제안: Claude·이미지/음성·모션/실사 후보 비교, 계정별 업로드, Resend 우선 뉴스레터 회차와 상품/쿠폰 연결입니다. 스티비·Buttondown은 요구에 따른 대안이며 실제 발송 어댑터는 미연결입니다.
- 미구현/미검증: 새 모델 생성 품질·실청구·새 계정 권한·운영 콘텐츠 게시·발송·쿠폰/주문·매출 효과입니다. 이 연구의 새 유료 생성·계정 연결·운영 게시/발송·쿠폰 쓰기는0건이며 Upside는 식별 보류입니다.

CLASS101 자료는 전부 확보 상태가 아닙니다. 현재 파일 대조와 과거 읽기 원장은 대상·시점이 달라 합산하지 않습니다. 회원 원문·개인 경로·계정·운영 DB·키는 이 저장소와 갱신 키트에 넣지 않으며 HTTPS의 기존 본인 전용 접근을 유지합니다.

다른 AI는 키트의 `KIT-README.md` → `README.md` → `dist/downloads/content-start.md` → `content-system/source.json` 순서로 읽고 원본 수정·생성·검사·동일 HTTPS 갱신 절차를 따릅니다. 사람 승인 ⓪기획·①원고·②출고·③회차와 실제 실행 권한은 문서나 ZIP으로 이전되지 않습니다. 이 갱신은 README 한 파일의 인계이며 앱·EC2 checkout을 동기화하거나 배포한 것이 아닙니다.

### 보존한 이전 인계 스냅샷

[통합 HTTPS 설계](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#content-system) · [자료·원가·실습](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-studio/) · [인계 README](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/README.md) · [정본·업데이트](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/SOURCE.md) · [편집 소스](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/editable-source/README.md) · [정오표](sites/heobrain-office-playbook-unified-20261027/handoffs/content-studio-v7.1-20261028/ERRATA.md)

상위 v7.2의49도구·38입력과 보조 작업실의35세부도구·21선별출처는 서로 다른 범위입니다. PDF56개·3205쪽 파일감사와10종96쪽 선택읽기, 원가 가정 계산·후반작업·이관 소스를 보강했습니다. 실제 모델 생성·유료 호출·개별 게시·회차③ 발송·상품/쿠폰/주문 쓰기는 실행하지 않았습니다. 기존 본인 전용 HTTPS 접근을 유지합니다.
