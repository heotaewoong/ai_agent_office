# HeoBrain AI 오피스 통합 플레이북

2026-10-27 · 웹 버전: index.html · 원본 3개 사이트 + database + 외부 오픈소스 통합본

## 1. 한눈에 보는 결론

**18부서를 모두 등록하되, 한 번에 한 주문만 끝까지 완결하는 오피스를 만든다.** 세 사이트(전체 설계·소스 키트·벤치마크 1,921선), database 마크다운 33개, 이번 외부 오픈소스 조사 129개를 합쳐 내린 결론이다.

1. **뼈대는 바꾸지 않는다.** 한 화면 + Hermes 총괄 + 기존 Next.js·FastAPI·Python·SQLite·FFmpeg + 같은 업무 장부. 새 총괄·새 메모리·새 화면을 한꺼번에 들이지 않는다.
2. **외부 코드는 부품으로만 들인다.** TOP3(FastCampus MCP·A2A, 보유한 CLASS101 n8n 실습, Cole Medin oTTomator)에서 결과 계약과 검토 패턴만 떼어 기존 worker에 붙인다.
3. **확장은 21개 파이프라인 순서를 따른다.** 첫 기반(NX01·09·10·12) → 콘텐츠 첫 실험(NX03·07) → 영상 품질(NX04·06·15) → 운영 연결 → 전체 부서·매출.

| 구성 요소 | 규모 | 의미 |
| --- | --- | --- |
| 부서 | 18 (R01~R18) | 모두 등록, 업무에 필요한 역할만 호출 |
| 기본 업무 계약 | 144 (OF-001~144) + 보강 37 | 부서당 8개, 입력·납품·실패 검사 포함 |
| 전문 분야 | 29 (F01~F29) | 분야별 10개 이상 비교 후 TOP3 |
| 학습 확장 | 9소스 → 21확장 → 260기능 | 강의·영상·자료실 기능을 부서에 연결 |
| 코드 후보 | 30 → TOP3 | 공개 ZIP 4 · 선택 파일 5 · 보유 워크플로 4 확보 |
| 오픈소스 후보 | 1,921 + 이번 129 | 부품 후보이며 설치·실행 검증 0건 |
| 승인 단계 | ① 원고 · ② 출고 · ③ 회차 | 사람이 내리는 세 번의 결정 |

**현재 상태:** 조사·설계·소스 확보 단계다. 외부 키트 설치·실행 0건, 유료 API 호출 0건, 계정 연결 0건. 일정과 기능은 구현 계획이며 완료 표시가 아니다.

## 2. 추천 아키텍처와 공통 원칙

**모든 요청은 한 업무 장부를 거치고, 예약·승인·재시도의 최종 결정은 업무마다 한 곳에서 내린다.** 팀 관리가 병목이면 Paperclip, 장기 재개 공백이 확인되면 LangGraph를 해당 역할에만 비교한다.

1. 나: 요청·자료·목적·마감·예산
2. 한 화면 접수함: 오늘 할 일 · 18부서 · 콘텐츠 작업실 · 발행함 · 자료·지식 · 개인 업무 · 비용 (사람 승인 ①②③도 여기서)
3. Hermes 총괄: 담당 배정 · 필요한 기억 · 위임 · 예약 주체 한 곳 · 필요한 역할만 호출
4. 업무 장부(SQLite): 요청 · 원고 판본과 해시 · 승인 기록 · 예산 · 외부 ID · 결과 불명 상태 (3D·목록 관측 화면은 이 장부를 읽기만 함)
5. 작업자: 콘텐츠 엔진(Python·FFmpeg) · 연구·문서(Docling·검색) · 개발(Codex·Claude Code) · 금융 읽기(검산만, 매매 0) · 반복 전달(n8n)
6. 결과 확인: 실제 파일 · 검사 · 외부 상태 대사 → 다음 행동. 실패는 원래 담당에게 반환

| 원칙 | 뜻 | 지키는 방법 |
| --- | --- | --- |
| 승인 ① 원고 | 사실·구조가 맞는 원고인가 | 승인 전에는 미디어 제작 0건 |
| 승인 ② 출고 | 이 파일을 이 채널에 올려도 되는가 | 채널별로 따로 받고 외부 ID 보존 |
| 승인 ③ 회차 | 이 뉴스레터·홍보를 이 대상에게 보내도 되는가 | 발송 직전 최신 동의·수신 거부 검사 |
| 판본·해시 | 승인한 원고와 제작에 쓴 원고가 같은가 | 파일 지문(해시)과 manifest 대조 |
| unknown 상태 | 외부 응답이 사라진 작업 | 재전송 전에 외부 상태부터 조회 |
| 한 곳의 책임 | 같은 일을 두 플랫폼이 예약·재시도 | 예약 주체·재시도 책임을 업무마다 하나로 |

## 3. 10월 31일 마감: 먼저 가져올 코드 TOP3

강의를 더 사기 전에, 위치와 조건을 확인한 코드부터 붙인다. 30개 후보(FastCampus 6 · CLASS101 6 · Inflearn 8 · YouTube 10) 중 현재 앱과 마감에 맞춘 재사용 우선순위다.

| 순위 | 후보 | 고른 이유 | 가져올 부분 | 남은 확인 |
| --- | --- | --- | --- | --- |
| 1 | [FastCampus MCP·A2A 업무 Assistant](https://github.com/HyunjunJeon/FastCampus_mcp_a2a_workflow_project) | 실제 역할별 Python 구현·실행 구성과 MIT가 함께 확인된 통합 업무 Assistant 예제. 강의 구매 없이 공개 코드를 먼저 볼 수 있다. | Supervisor/Planner 결과 계약과 Basic의 사람 검토 예제. 현재 앱·Hermes는 유지. | 미실행. Python3.12·Ubuntu 호스트 연결·메모리 지속성을 별도 검증. |
| 2 | [이미 보유한 CLASS101 n8n 실습](https://class101.net/ko/products/687ca1006a9a3692f2f22a96) | 새 강의를 사기 전에 사용할 수 있는 개인 자료. 유튜브/블로그→노트·회의록·뉴스레터·주간보고 JSON 4개를 이번에 실제 확보했다. | n8n이 이미 준비돼 있으면 비활성 사본의 작은 연결 1개. 없으면 현재 Python 작업자에 필요한 처리만 독립 설계. | 원본 일부 active=true. 뉴스레터 고정 수신자·외부 STT/자막 API·승인 누락을 수정해야 한다. 학생자료 재배포권 미확인. |
| 3 | [Cole Medin / oTTomator 공개 부품](https://github.com/coleam00/ottomator-agents) | MIT 연구·콘텐츠 워크플로 원본을 가입 없이 받을 수 있다. 이번에 필요한 파일 5개를 확보했다. | 원문 URL 보존 연구와 채널 문안 생성. 승인한 공통 원고에서 독립 분기로 재설계. | 전체 오피스나 자동 게시 구현이 아니다. 메시지 저장·자격·active 플래그를 현재 SQLite/승인 계약에 맞춰 변경. |

인프런에서 하나를 고른다면 [LangGraph를 활용한 AI Agent 개발](https://github.com/jasonkang14/inflearn-langgraph-agent)(MIT)의 HITL·멀티 에이전트·MCP 예제 일부다.

### 받은 코드를 부품으로 바꾸는 5단계

1. **정확히 받기:** 강의·영상과 실제 파일을 대조하고 버전·해시·이용 조건을 기록한다.
2. **작은 부분 선택:** 처리 하나만 고르고 예제 계정·수신자·경로를 교체한다.
3. **기존 앱에 연결:** Python 작업자와 업무 장부에 붙이고 원고①·출고②·회차③을 유지한다.
4. **정상·실패 확인:** 파일·근거·재시작·중복·권한·비용·unknown을 검사한다.
5. **실제 사용:** 내 블로그·영상·학습 결과로 검토 시간과 원가를 잰다.

### 화~토 일정 (구현 계획)

| 날짜 | 목표 | 통과 기준 |
| --- | --- | --- |
| 10/27 화 | 소스와 현재 앱 기준 고정 | 버전·허가·개인자료 정리, n8n 또는 Python에서 작은 처리 1개 검증 |
| 10/28 수 | 읽히는 블로그 + 재생되는 영상 | RSS → 근거 원고 → 승인① → 독립 제작. 화면·음성·자막·썸네일·PDF·비용 확인 |
| 10/29 목 | 선택한 자료로 배우고 Wiki에 인계 | 고른 채널·영상의 허용 자료로 출처 있는 답·실습·검토한 노트 |
| 10/30 금 | Hermes와 18부서 상태·출고 연결 | 등록 업무만 호출, 미구현 도구는 지원·대기로 표시 |
| 10/31 토 | 실제 사용으로 통과 검사 | 블로그 열람·영상 재생·학습→Wiki, 원고 변경·중복·응답 유실 검사, 검토 시간·원가 기록 |

## 4. 학습 확장: 9개 소스에서 21개 파이프라인으로

지정 9개 소스에서 확인한 기능 260행을 21개 확장(NX01~NX21)에 연결했다. 기준은 역할 수가 아니라 정확한 결과, 사람이 덜 고치는 제작, 중단 후 이어지는 업무다.

- **주장마다 실제 화면·차트를 배치 (NX07):** 범용 이미지 슬라이드를 넘어 실제 조작·검증 숫자·선택 실사 컷을 장면의 목적에 맞춰 편집합니다. 원고① 뒤 만들고 전 구간 검사 뒤 출고②로 넘깁니다.
- **위키를 오늘의 다음 행동으로 (NX09):** 지식·메일·일정의 출처와 기한을 이어 브리핑→실행→결과→검토한 기억을 순환합니다. 개인자료와 공개 콘텐츠의 경계를 지킵니다.
- **18부서가 납품을 인수 (NX01):** 마케팅→문서·상품→주문·지원·회계, 개발→QA→출시를 같은 업무로 연결합니다. 입력·산출물·실현 조건·검사를 모든 기능에서 확인합니다.

### 지정 9개 소스와 읽은 범위

| ID | 소스 | 읽은 범위 |
| --- | --- | --- |
| S01 | [Claude Code 100명 규모 AI 조직 강의](https://fastcampus.co.kr/dgn_online_24fullclaude) | 공개 소개·69클립 목차 전체 |
| S02 | [Hermes × Codex AI 가상 오피스 강의](https://fastcampus.co.kr/biz_online_makefamily) | 공개 소개·78클립 목차 전체 |
| S03 | [단테랩스 Hermes × Codex 가상 오피스](https://www.inflearn.com/course/hermes-agent-advance) | 공개 소개·70강의+4미션 목차 |
| S04 | [FastCampus 자동화 검색 전체 목록](https://fastcampus.co.kr/search?keyword=%EC%9E%90%EB%8F%99%ED%99%94) | 검색9페이지·243카드 |
| S05 | [AI 크리에이티브 이상현상 연구소 행사](https://fastcampus.co.kr/event_online_aifan2610) | 행사 본문·40강의 카드 |
| S06 | [TTJ · 블로그/SNS 자동화 4단계 영상](https://www.youtube.com/watch?v=3-LWSeYx5bo) | 자막428구간 전체·설명·챕터 |
| S07 | [Career Hacker Alex 자료실](https://www.careerhackeralex.com/resources) | 17항목 목록·공개 본문·선택 코드 |
| S08 | [후츠릿 · Hermes AI 콘텐츠팀 영상](https://www.youtube.com/watch?v=96BAQ3v3NhI) | 자막678구간 전체·설명·챕터 |
| S09 | [CONNECT AI LAB 공개 채널](https://www.youtube.com/@CONNECT-AI-LAB) | Videos탭165목록·선택12편 설명/연결자료 |

### 21개 확장 파이프라인

| ID | 확장 | 단계 | 담당 | 받는 결과 |
| --- | --- | --- | --- | --- |
| NX01 | 18부서가 실제로 인수하는 업무 조직 | 첫 기반 | R01·R02·R03·R04 | 부서 헌장·업무 의존도·인계 영수증·현재 담당과 다음 행동 |
| NX02 | 아침 브리핑부터 답변 대기까지 이어지는 비서 | 첫 사용자 가치 | R01·R14·R16·R17 | 날짜별 브리핑·약속 근거·기다리는 상대·다음 확인 |
| NX03 | 매일 게시량보다 독자 질문을 먼저 고르는 콘텐츠 회의 | 콘텐츠 첫 실험 | R05·R06·R08·R09 | 주제 회의표·선정3편·출처·독자 질문·반증/미확인 목록 |
| NX04 | 스크린샷과 실제 화면이 설명하는 영상 | 영상 품질 우선 | R06·R07·R03 | 근거 화면 원본·초점 계획·확대 컷·말/화면 대응표·영상 |
| NX05 | 검증한 숫자로 움직이는 차트 | 영상·보고서 공통 | R05·R07·R11·R13·R03·R12 | ChartSpec·검산표·PNG/SVG·PPT 도형·모션 컷·근거 버전 |
| NX06 | 한국어 설명용 모션 템플릿 라이브러리 | 영상 품질 우선 | R07·R06·R03 | TemplateManifest·저해상도 스토리보드·검수된 모션 컷·렌더 영수증 |
| NX07 | 실사·모션·음성의 역할을 나누는 영상 감독 | 콘텐츠 첫 실험 | R06·R07·R03 | DirectorPlan·장면별 선택 이유·오디오/자막/시각 타임라인·검수 리포트 |
| NX08 | YouTube 성과를 다음 기획·편집으로 되돌리기 | 운영 데이터가 생긴 뒤 | R08·R09·R07·R05 | 채널 검토팩·대본/장면 관측·개선 가설·다음 실험 티켓 |
| NX09 | 다층 기억·LLM Wiki를 업무 근거로 연결 | 첫 기반 | R05·R15·R01·R16 | 기억 출처 카드·Wiki 근거·사용 기억 참조·정정/만료 영향표 |
| NX10 | 기억·판정 모델의 교체를 먼저 시험하는 실험실 | 첫 기반 | R03·R04·R05·R13 | 평가 세트·원가표·업무별 채택 결정·롤백 기준 |
| NX11 | 직무별 마케팅·영업·재무 결과를 같은 주문으로 잇기 | 전체 부서 확장 | R09·R10·R13·R15·R05 | 조사팩·캠페인/제안 초안·실제 조건·주문/정산·개선 티켓 |
| NX12 | Claude·Hermes·Codex의 실제 지원을 확인하는 실행 연결 | 첫 기반 | R01·R02·R04·R03 | RuntimeCapabilityManifest·업무별 지원표·계약 검사 결과·교체/복귀 계획 |
| NX13 | 24시간을 약속하기 전에 중단·재개·비용을 확인 | 운영 연결 전 | R01·R04·R13·R08 | 가용성/예약 정책·실행 시도·비용 예약·복구 보고·다음 확인 |
| NX14 | 좋은 작업법을 검수한 스킬로 만드는 개선 루프 | 반복 업무가 검증된 뒤 | R01·R02·R03·R05·R16 | SkillCandidate·변경 diff·평가 사례·검수/복귀 기록 |
| NX15 | 말로 요청하고 컷 단위로 되돌리는 편집 작업실 | 영상 품질 우선 | R07·R03·R06 | 편집 계획 EDL·전후 콘택트 시트·편집본·자막·오디오 검사·원본 보존 기록 |
| NX16 | 영수증부터 검토용 계약·PPT까지 이어지는 문서 공장 | 문서·매출 연결 | R13·R15·R07·R03·R10 | 검산표·누락 질문·편집 가능한 DOCX/PPTX·전체 페이지 미리보기·원문 대응표 |
| NX17 | 질문·검색·논문 비교·리뷰 답변이 이어지는 연구실 | 지식 재사용 | R05·R03·R15·R16 | 검색/제외 장부·근거 비교행렬·반증·남은 질문·발표/리뷰 답변 초안 |
| NX18 | 상품 한 개에서 검수한 광고·상세페이지 변형 만들기 | 매출 실험 | R07·R09·R10·R03 | 상품별 시안·변형 금지 검사·편집 원본·실험 계획·실제 전환/원가 대조 |
| NX19 | 승인 큐와 플랫폼별 실제 결과가 연결된 발행실 | 반복 작업 절감 | R08·R06·R09·R03 | 계정별 승인 큐·슬롯표·렌더 미리보기·게시 ID·실제 상태/정정 이력 |
| NX20 | 학습·생활·건강 기록을 개인 범위에서 챙기는 비서 | 개인 시간 절감 | R14·R16·R17·R18·R05 | 개인 브리핑·복습/준비 과제·기록 요약·질문·알림 초안 |
| NX21 | 요구사항에서 검수한 개발 변경까지 연결하는 제작팀 | 개발 시간 절감 | R02·R03·R04·R01·R10 | PRD·작업 명세·분리 diff·관련 검증·리뷰·출시/복구 인계 |

### 내가 고른 유튜버로 공부하는 학습 비서 (R16)

1. **내 채널 선택:** 채널·재생목록·영상 단위로 등록. 구독 전체가 자동 학습되지 않는다
2. **새 영상함:** 새 영상·제목 변경·중복·자료 부족을 구분
3. **근거 있는 노트:** 허용 자막·본문·내 메모에서 개념·절차·시간 위치 연결. 설명만 읽었으면 표시
4. **질문과 실습:** 선택 모음 안에서만 답하고 과제·오답 피드백·복습 제공
5. **Wiki·오피스 반영:** 검토한 지식만 필요한 부서에 인계

등록 후보 채널: CONNECT AI LAB · 투더제이 TTJ · 후츠릿 · 커맨드스페이스(구요한) · Career Hacker Alex. 실제 구독 연동·자동 학습은 꺼져 있다.

## 5. 먼저 완결할 다섯 흐름

외부 코드·공식 문서 20개를 추가 대조해 구현 공백 18건을 다섯 흐름으로 묶었다. 토요일에는 FLOW2·FLOW3 안에 근거·판본·인계·완료 검사를 넣는 것이 우선이다.

| 흐름 | 단계 | 받을 결과 | 계약 |
| --- | --- | --- | --- |
| FLOW1 새 자료가 실제 업무로 이어지는 아침 브리핑 | 선택 피드와 채널 → 새 판본·보류 후보 보존 → 근거 검토와 오늘 할 일 → 담당과 결과 조건에 연결 | 신규·변경·본문 대기를 구분한 브리핑 + 선택한 콘텐츠/조사 작업 | WF-01, NEXT-I01 |
| FLOW2 내 유튜버로 배우고 바로 써 보는 학습함 | 내가 고른 영상·허용 자료 → 확보 구간·부족한 본문 표시 → 모음 안의 근거 질문·실습 → 검토한 노트만 Wiki 인계 | 시간 위치가 있는 설명·작은 실습·검토한 Wiki 노트 | LEARN-I1, LEARN-I3, ROOT-I1 |
| FLOW3 한 원고에서 만드는 콘텐츠·마케팅 제작팩 | 주제·독자·근거 원고 → 비평·평가·수정과 원고① → 제작물 독립 선택·품질 검수 → 출고②·회차③·실제 결과 확인 | 블로그·말하기 대본·영상·PDF와 채널 문안, 출고 결과 | WF-03, WF-05 |
| FLOW4 바뀐 근거가 오래된 결과에 남지 않도록 | 원문·추출 규칙 판본 기록 → 내용/설정 변화 비교 → 해당 근거를 쓴 결과 찾기 → 영향 범위만 재검토·승인 갱신 | 바뀐 구간과 영향받은 원고·노트만 모은 재검토함 | LEARN-I2, WF-02, NEXT-I02 |
| FLOW5 부서가 바뀌고 중단돼도 끝까지 이어지는 주문 | 하나의 요청·완료 조건 → 담당·선행·판본 인계 → 결과 관측과 필요한 단계 재개 → 실제 파일·검사·다음 행동으로 인수 | 인수/반환·실패/불명·다음 행동과 확인 가능한 납품 기록 | NEXT-I01, WF-04, ROOT-I2, NEXT-I06 |

### 흐름을 받치는 보강안 18개

| ID | 보강안 | 적용 | 담당 |
| --- | --- | --- | --- |
| LEARN-I1 | 허용 자막을 근거 구간으로 바꾸는 입력 검사기 | 토요일 우선 | R16·R05·R15·R02·R03 |
| LEARN-I2 | 바뀐 원문에 연결된 카드·Wiki만 재검토 대기 | 토요일 우선 | R05·R15·R16·R02·R03 |
| LEARN-I3 | 모음별 로컬 검색으로 원문 위치부터 찾기 | 토요일 우선 | R16·R15·R05·R02·R03 |
| LEARN-I4 | 답을 떠올린 뒤 누르는 복습 평가와 다음 일정 | 주력 통과 후 | R16·R02·R03·R15 |
| LEARN-I5 | 검토한 질문만 Anki 파일로 가져가기 | 주력 통과 후 | R16·R15·R05·R02·R03 |
| WF-01 | 아침 브리핑을 새 증거만 담는 편집 후보함으로 | 조건부 | R05·R01·R06·R14 |
| WF-02 | 근거가 바뀐 콘텐츠·학습노트만 재검토함으로 돌리기 | 조건부 | R05·R06·R16·R15 |
| WF-03 | 승인 원고 한 편에서 근거가 연결된 소규모 캠페인 팩 | 조건부 | R09·R06·R07·R08·R03 |
| WF-04 | 정기 업무 템플릿에 단계별 재개·재시도 정책을 붙이기 | 조건부 | R04·R02·R01·R03 |
| WF-05 | 업로드 ID 뒤에 처리·공개·재생 증거를 따로 붙이기 | 조건부 | R08·R07·R03·R04 |
| NEXT-I01 | 인계 양방향 지도: 막힌 업무·같은 요청·검토 중인 결과를 구분 | 조건부 | R01·R02·R03·R04·R05·R06 |
| NEXT-I02 | 문서 계보함: 원본·개정본·추출본을 승인된 판본으로 묶기 | 조건부 | R05·R06·R07·R10·R11·R12 |
| NEXT-I03 | 갱신·예상지출 대사함: 예정 회차와 실제 결제 증거를 분리 | 조건부 | R01·R04·R07·R08·R10·R11 |
| NEXT-I04 | 일상 실행 일지: 알림·건너뜀·실제 수행·취소를 따로 기록 | 조건부 | R01·R04·R05·R14·R16·R17 |
| NEXT-I05 | 지원·약속 시계: 첫 답변과 해결을 구분하고 대기를 설명 | 조건부 | R01·R02·R03·R04·R06·R08 |
| NEXT-I06 | 개발·자동화 재현팩: 같은 판본에서 QA가 결과를 다시 확인 | 조건부 | R01·R02·R03·R04·R05·R07 |
| ROOT-I1 | Wiki 인계 뒤 실제 노트를 열어 확인하는 영수증 | 조건부 | R15·R16·R05 |
| ROOT-I2 | 여러 자동화의 실패를 한곳에서 인계하는 예외함 | 조건부 | R01·R04·R03 |

## 6. 18부서 조직과 부서별 첫 납품

18부서는 18개 모델을 상시 켜 두는 구조가 아니다. 부서는 책임, 비서는 맡길 역할, 작업자는 실제로 파일을 만들거나 계산하는 프로그램이다.

| 부서 | 맡길 반복 업무 | 첫 납품 | OF 범위 |
| --- | --- | --- | --- |
| R01 총괄·프로젝트 관리 | 요청 분해, 우선순위, 인계·마감 | 요청→선행 업무→인수/반환→다음 행동 | OF-001~OF-008 |
| R02 개발 | 요구사항 → 변경안 → 구현 후보 | 같은 판본의 변경·재현팩→독립 QA | OF-009~OF-016 |
| R03 QA·접근성 | 실패·경계·모바일·사용 흐름 검수 | 정상/권한/판본/중복/실패 조건을 같은 입력으로 검수 | OF-017~OF-024 |
| R04 인프라·보안·운영 | 상태·비용·백업·의존성·사고 검토 | 중단·결과 불명→관측→필요한 단계만 재개 | OF-025~OF-032 |
| R05 연구·지식 관리 | 최신 자료·근거·정정·재사용 정리 | 새 근거·원문 범위·변경 위치→연구 카드 | OF-033~OF-040 |
| R06 블로그·편집 | 주제·독자별 원고와 채널 변환 | 승인 원고→근거 연결 채널 문안·정정 후보 | OF-041~OF-048 |
| R07 디자인·영상 | 카드뉴스·숏폼·음성·자막·썸네일 | 승인 원고·장면 근거·자산 판본→검수할 제작팩 | OF-049~OF-056 |
| R08 배포·뉴스레터·커뮤니티 | 게시·발송·질문·동의·빈도 관리 | 출고②·회차③→접수/처리/공개 관측 | OF-057~OF-064 |
| R09 마케팅·고객지원 | 실험·유입·문의 분류·답변 초안 | 문의/캠페인→답변 대기·해결·다음 확인 | OF-065~OF-072 |
| R10 상품·매출 운영 | 자료·상품·캠페인·주문/권한 검토 | 상품 약속·제작 원가·지원→조건 검토팩 | OF-073~OF-080 |
| R11 주식·ETF 금융 | 공시·보유 노출·투자 논리 변경 | 공개 근거 변경→검산 브리핑/보유 영향 질문 | OF-081~OF-088 |
| R12 BTC·크립토 금융 | 네트워크·거래소·상품·사건 검토 | 공식 관측·상품 문서 판본→변화/미확인 브리핑 | OF-089~OF-096 |
| R13 회계·지출·세무 준비 | 거래 분류·영수증·구독·마감 | 예상 반복 지출과 실제 증빙→회차별 대사 | OF-097~OF-104 |
| R14 이메일·일정·회의 | 분류·초안·회의 준비·행동 항목 | 약속·준비·응답 대기→관측 시각/다음 확인 | OF-105~OF-112 |
| R15 문서·파일·계약 준비 | 문서 비교·정리·권리·갱신 | 원본·개정판·추출판본→검토된 Wiki 인계 | OF-113~OF-120 |
| R16 커리어·학습 | 공고 검증·자료·복습·프로젝트 증거 | 선택 자료→시간 근거→실습→복습/Wiki | OF-121~OF-128 |
| R17 생활·여행·구매 | 일정·비용·조건·대안 정리 | 생활 준비·반복 업무→실행/건너뜀/취소 기록 | OF-129~OF-136 |
| R18 건강·의료자료 지원 | 생활 기록·검진 일정·문서 질문 준비 | 허용 건강 기록·진료 질문 준비→사용자 확인 | OF-137~OF-144 |

금융은 근거·계산까지만 맡기고 실제 매매는 0건이다. 건강은 기록·질문 준비까지이며 진단·치료 결정은 위임하지 않는다.

## 7. 에이전트 팀 아이디어

팀은 부서를 묶은 주문 단위다. 18부서는 그대로 두고 주문마다 필요한 부서만 모아 주관 한 곳이 끝까지 책임진다.

### 우리 오피스에 만들 팀 8개

| 팀 | 구성 (주관 → 협력) | 첫 주문 | 완료 증거 |
| --- | --- | --- | --- |
| 콘텐츠 편집국 | R06 → R05 · R07 · R03 · R08 | AI 뉴스 3선 → 블로그 + 숏폼 | 승인① 원고 해시, 재생 검수, 출고② 후 공개 ID |
| 아침 브리핑 데스크 | R05 → R14 · R16 · R01 | 선택 RSS·채널의 새 자료 → 오늘 할 일 3개 | 신규/변경/본문 대기 구분, 담당·결과 조건 |
| 학습 스튜디오 | R16 → R05 · R15 · R02 | 고른 영상 1편 → 시간 근거 노트 + 실습 | 확보 구간 표시, 검토한 Wiki 노트 열람 영수증 |
| 개발 제작팀 | R02 → R03 · R04 · R01 | 결함 1건 → 작은 변경 + 검사 | 분리 diff, 같은 판본의 독립 QA, 재현팩 |
| 수익 운영팀 | R10 → R09 · R13 · R15 | 무료 PDF·쿠폰 캠페인 초안 | 비활성 쿠폰, 0원 주문·권한 검사, 실제 원가 |
| 투자 판단 작업실 | R11 → R12 · R05 | 보유 ETF 중복 노출·공시 변화 | 동일 기준일 검산, 반증/미확인, 매매 0건 |
| 예외·복구 데스크 | R04 → R01 · R03 | 결과 불명 작업 1건 대사 | 외부 ID 조회 후 재개, 중복 재전송 0건 |
| 생활 비서 | R14 → R17 · R18 | 다음 주 일정·구매·검진 준비 | 실행/건너뜀/취소 기록, 사용자 확인 |

### 검증된 팀 운영 패턴

- **위계형 회사:** 총괄 → 부서장 → 전문가. 조직도·목표·하트비트·에이전트별 월 예산·승인. 쓸 때: 여러 에이전트를 사람이 관리하는 것이 병목일 때 (Paperclip)
- **칸반 보드형:** 작업 카드가 보드에 남고 프로필·팀원이 가져간다. 재시도·사람 입력·담당 교체. 쓸 때: 중간에 멈추고 이어 가는 일이 많을 때 (Hermes Kanban · Multica)
- **감독자 → 작업자 → 검증자:** 계획과 실행과 검증을 다른 역할로 분리해 자기 채점을 막는다. 쓸 때: 결과 품질 판정이 중요한 일 (FastCampus Supervisor/Planner)
- **제작 → 비평 → 평가 루프:** 같은 원고·같은 기준으로 독립 평가, 수정은 최대 2회. 쓸 때: 원고·대본·보고서 (콘텐츠 v5 Gen/Critique/Eval)
- **병렬 worktree 팀:** 에이전트마다 분리된 작업 공간, 사람이 병합. 쓸 때: 개발 작업을 동시에 여러 개 (Claude Squad · Claw Empire · OpenHands)
- **승인 분기 파이프라인:** 승인한 원고 하나에서 블로그·영상·뉴스레터가 독립 분기. 쓸 때: 한 자료로 여러 납품물 (콘텐츠 v5)

### 비교한 올인원 AI 비서팀 TOP5

| 순위 | 팀 | 확인한 규모 | 제공 형태 | 가져올 가치 |
| --- | --- | --- | --- | --- |
| 1 | [Paperclip + Agency Agents](https://github.com/paperclipai/companies/tree/main/agency-agents) | 공개 역할표 167행·10개 부서 | Paperclip 회사 import 패키지 | 폭넓은 전문 조직·부서 인계·검수 |
| 2 | [Relevance AI MRP Workforce](https://marketplace.relevanceai.com/listing/2cd9c3ca-3527-481c-841c-27a560cfd222) | 관리자 1 + 전문 13 | Relevance 공개 clone 팀 | 조사 → CRM → 덱 → 회의 문서 → 기록 → 메일 |
| 3 | [Sintra X](https://sintra.ai/ai-team) | 실명 12역할 | 상용 비서 SaaS | 회사 공통 맥락·역할 UX·채팅 협업 |
| 4 | [Paperclip + Product Compass](https://github.com/paperclipai/companies/tree/main/product-compass-consulting) | 공개 역할표 48행·8개 부서 | Paperclip 회사 import 패키지 | 시장조사 → 가격/전략 → PRD → 출시 자료 |
| 5 | [Global AI Workforce Premium](https://globalaiworkforce.com/team.html) | CEO 1 + 전문 11 | 공급자 관리형 구축 상품 | 총괄·전문팀·도구·인프라·운영 지원 분리 |

## 8. 파이프라인 라이브러리

가치가 가장 큰 파이프라인은 **자료 → 조사 → 공통 원고 → 여러 납품물**이다. 순위는 구축 우선순위이며 실측 절감 시간은 아직 없다.

| 순위 | 파이프라인 | 참고할 실물 | 남는 가치 |
| --- | --- | --- | --- |
| 1 | 자료/주제 → 조사 → 공통 원고 → 글·숏폼·뉴스레터 → 납품/게시 | GPT Researcher · DeerFlow · 기존 Python · n8n | 한 번 조사를 여러 납품물로 전환 |
| 2 | 상담 → 요구 정리 → 견적·제안서 → 수락 → 제작 → 입금 | n8n 제안서/CRM 공정 + 1번 제작 공정 | 영업에서 실제 매출까지 연결 |
| 3 | 고객 메일 → 주문·배송 조회 → 답변/이관 → 처리 이력 | n8n 지원 공정 · Chatwoot | 문의마다 콘솔을 오가는 노동 감소 |
| 4 | 결함 → 코드 조사 → 수정·검사 → PR → 리뷰·CI → 출시 | OpenHands Issue-to-PR · Codex | 개발 외주·내부 개선 시간 절감 |
| 5 | 질문 → 조사 계획 → 병렬 조사 → 검토 → 출처 보고서/PDF/DOCX | GPT Researcher multi_agents · Open Deep Research | 편집 가능한 조사 납품물 |
| 6 | 메일·회의 → 맥락 정리 → 회신 초안 → 일정/할 일 → 후속 | Rowboat · n8n | 메일·달력·회의록 전사 노동 감소 |
| 7 | 청구 PDF → 추출 → 중복 확인 → 지급 보관 / 입금 → 미수금 보고 | Docling · Paperless-ngx · Actual | 전표 입력·파일 정리 절감 |
| 8 | 문서·계약 수신 → OCR·분류 → 보관 → 갱신 대상 → 알림 | Paperless-ngx · Onyx | 계약 기한 누락 감소 |
| 9 | 자료 연결 → 색인·검색 → 근거 인용 답변 → 업무 재사용 | Onyx · CMDS LLM Wiki | 같은 문서 재탐색 감소 |
| 10 | 자료/강의 → 요약·실습·문항 → 과제 → 채점 → 다음 학습 | n8n 학습 공정 · FSRS | 교육 준비·채점 절감, 교육 상품 확장 |

### 콘텐츠 v5: 승인한 원고 하나에서 독립 분기

1. 접수: 주제·독자·원본 자료·제작 여부·예산·상품 선택
2. 근거: 입력 검사 → 자료 수집 → 주장별 근거·권리 확인
3. Gen·Critique·Eval: 같은 원고·같은 기준으로 독립 평가, 수정 최대 2회
4. **승인 ①** 원고와 제작 범위 승인, 원고 버전 고정
5. 독립 분기: 글(티스토리·네이버·LinkedIn·Threads) · 카드뉴스 · 영상(대본 → 음성·화면 → 합성·자막 → 커버 5안) · PDF·뉴스레터 회차 후보
6. 결과물별 검사·미리보기·원가 표시
7. **승인 ②** 게시·업로드, **승인 ③** 뉴스레터·홍보 발송, 외부 ID와 실제 공개 상태 확인

### Obsidian·LLM Wiki 8단계

| 단계 | 하는 일 | 완료 결과 |
| --- | --- | --- |
| Capture | 목적을 정해 허용 URL·파일을 수신함에 등록 | 원본 참조·출처 카드, 중복·누락 목록 |
| Ingest | 복사본에서 추출, 쪽·구조 보존, OCR 구분 | 페이지별 본문·표 위치, 로컬 검색 색인 |
| Compile | 지식 조각·관계 제안 후 차이 검토 | 원문 허브·주장·방법 노트, 상충 목록 |
| Query | 질문 범위 고정 후 두 층 검색·원문 대조 | 출처 있는 답변, 다음 확인 질문 |
| Lint | 형식·근거 연결·변경 영향 검사 | 결함·의심 목록, 영향 노트 |
| Brief | 실제 상태 조회 후 우선순위 | 오늘 할 일·검토 대기 3개, 주간 회고 |
| Produce | 근거 묶음을 고정해 결과물 제작 | 블로그·영상 입력, 보고서·PPT 개요 |
| Archive | 보관·검색 제외·복원 | 보관 기록, 버전별 원본 참조 |

## 9. AI 콘텐츠 에이전트 v6: 편집 통제실

**생성 공장이 아니라 편집 통제실을 짓는다.** 데이터로 기획을 고르고, 제목·썸네일·훅을 원고보다 먼저 정하고, 자동 게이트로 사람이 볼 곳을 좁히고, 사람이 승인한 교훈만 다음 회차에 반영한다. 2026년 10월 외부 벤치마킹(오픈소스 약 55개, 상용 도구 공식 문서, 크리에이터 방법론, 플랫폼 정책, 미디어 생성 스택, 인용 104개)의 결론이다.

- 리서치부터 성과 환류까지 한 시스템에서 닫은 오픈소스·상용 제품은 없었다. 성과를 다음 기획으로 되돌리는 오픈소스는 darkzOGx/youtube-automation-agent 하나였다.
- HeoBrain의 중간 단계(버전 승인·예산 예약·독립 Critique/Eval·ZIP 인계)는 이미 상위권이므로 앞단(기획·패키지)과 뒷단(측정·교훈)에 투자한다.
- 승인 ① 원고 · ② 출고 · ③ 회차의 의미는 그대로 두고, 그 앞에 ⓪ 기획 선택과 교훈 승인을 새로 둔다.

### 0~13단계 파이프라인

| # | 단계 | 하는 일 | 사람 결정 | 외부 기준 |
| --- | --- | --- | --- | --- |
| 0 | 브랜드 번들 | 목소리 예시·표기 고정·금지 주장·발음 사전을 모든 생성이 물려받음 | 번들 수정 | Jasper IQ, WRITER Voice Profile |
| 1 | 신호 수집 | 기존 RSS + 경쟁 채널 videos.list 통계 + 네이버 데이터랩(기준 키워드) + Hacker News | - | YouTube 쿼터: search 하루 100회, videos.list 1 unit |
| 2 | 기획 은행 | 아웃라이어 배수·수요·1차 출처·적합도·신규성 점수, 차단 사유 표시 | - | vidIQ Outliers, Spotter, Justin Welsh 매트릭스 |
| 3 | ⓪ 기획 선택 | 점수순 후보에서 하나를 고르면 작업 생성 | ⓪ 선택 | vidIQ 저장/기각 |
| 4 | 패키지 카드 G0 | 제목 3안·썸네일 3안·훅·로그라인·통할 이유, 훅이 제목 약속을 잇는지 검사 | 패키지 확정 | Ali Abdaal, Paddy Galloway, YouTube A/B |
| 5 | 리서치 브리프 | 주장-출처 대응표 | - | GPT Researcher, STORM |
| 6 | 원고 루프 | Gen → Critique/Eval → Refine 최대 2회, 브랜드 번들 주입 | - | G-Eval, MT-Bench(평가자 편향) |
| 7 | 자동 게이트 | 메타데이터 숫자 근거·템플릿 반복·YMYL 실존 인물 AI 페르소나·금지 주장·AI 공개 판단 | 경고 확인 | SAFE, Google AI 콘텐츠 가이드, YouTube 정책 |
| 8 | ① 원고 승인 | 게이트 사유를 함께 보고 승인 | ① | StoryChief 스냅샷 승인 |
| 9 | 포맷 분기 | 승인 해시에서만 블로그·롱폼·쇼츠·뉴스레터 계획 | - | n8n #6899, MrBeast 리텐션 비트 |
| 10 | 미디어 | 실제 화면 70~90%, 한글은 폰트 레이어, TTS 발음 사전 | - | 생성 영상이 변동비 80~95% |
| 11 | ② 출고 승인 | 시험용 썸네일 3안(1280×720 이상), AI 공개 체크 | ② | YouTube A/B·공개 정책 |
| 12 | 배포·③ 회차 | YouTube·뉴스레터, 네이버는 수동 붙여넣기 | ③ | 네이버 자동 발행 API 없음 |
| 13 | 측정·교훈 | 24h·7d·28d 스냅샷 → 교훈 후보 → 승인한 교훈만 점수에 반영 | 교훈 승인 | darkzOGx Learn, Reporting API(노출·CTR) |

### 품질·정책 게이트 G0~G8 (차단 기준은 첫 값)

| 게이트 | 시점 | 검사 | 차단 기준 |
| --- | --- | --- | --- |
| G0 패키지 | 원고 전 | 제목·썸네일·훅·로그라인 | 훅이 제목 약속을 잇지 않거나 3안이 없음 |
| G1 근거 대응 | 원고 생성 전 | 핵심 주장마다 출처 구절 | 출처 없는 핵심 수치·날짜 |
| G2 주장 검증 | 원고 생성 후 | 지지/반박/확인 불가 분류 | 반박 1건 이상 |
| G3 교차 심사 | 원고 생성 후 | 다른 계열 모델 루브릭, 순서 뒤집기 | 80점 미만 또는 중대 오류 |
| G4 독창성·반복 | ① 전 | 이전 대본과 3-gram 유사도 | 0.5 이상 |
| G5 정책 린트 | ① 전 | 지어낸 경험, YMYL 실존 인물 AI 페르소나 | 해당하면 차단 |
| G6 미디어 | ② 전 | TTS 역전사 오독, 자막 싱크, 자리표시 미디어 | 고유명사 오독·자리표시 포함 |
| G7 메타데이터·공개 | ② 전 | 제목·설명·태그 숫자, 썸네일 해상도, AI 공개 | 근거 없는 숫자, 공개 누락 |
| G8 라이선스 | 도구 채택·② 전 | 모델·소재 허용 목록 | 허용 목록 밖 산출물 |

### 편당 비용 추정 (원화는 예약 환율 1달러=2,000원)

| 항목 | 프리미엄 API | 저가 API | 로컬(RTX 4090급) |
| --- | --- | --- | --- |
| 60초 쇼츠 | $19~37 (₩3.8만~7.4만) | $5~10 (₩1만~2만) | 약 $0 + GPU 시간 |
| 8분 해설(생성 B-roll 60~90초) | $30~45 (₩6만~9만) | $7~20 (₩1.4만~4만) | 약 $0 + GPU 시간 |
| 음성·음악·자막·썸네일 합계 | 편당 $2 미만 | 편당 $1 미만 | $0 |

### 도구 판단

- **채택:** faster-whisper·WhisperX(자막) · auto-editor·PySceneDetect(무음·장면) · FFmpeg · GPT Researcher 방식 리서치 · YouTube Test & Compare(A/B는 직접 만들지 않음) · Gemini TTS(2027-01-01부터 오디오 단가 2배)
- **먼저 비교:** Wan 2.2 5B·LTX-2(로컬 영상) · Runway API의 Veo 3.1, Gemini Omni Flash(생성 B-roll) · Revideo(MIT)·Remotion(3인 이하 무료) · AutoClip(롱폼→쇼츠) · Typecast(단어 타이밍) · beehiiv MCP·listmonk·Postiz
- **쓰지 않음:** HunyuanVideo(라이선스가 대한민국 제외) · F5-TTS 사전학습 가중치(CC-BY-NC) · FLUX dev(비상업) · Midjourney(공식 API 없음·자동화 금지) · Sora(2026-09-24 API 제거 보도) · Wav2Lip(상업 금지) · 네이버 자동 발행 봇 · 전편 AI 아바타 · Studio Inspiration 탭 자동화(2026-08부터 종료)

### 구현 우선순위

| 순위 | 기간 | 항목 | 완료 기준 |
| --- | --- | --- | --- |
| P0 | 1~2주 | 패키지 카드 게이트, ⓪ 기획 선택, 시험용 썸네일 3안 | 기획에서 시작한 모든 회차가 확정 패키지를 가짐 |
| P1 | 2~4주 | 브랜드 번들, 기획 은행 점수, 품질·정책 게이트 | 승인 화면에 게이트 사유, 주간 후보 20개 이상 |
| P2 | 4~8주 | 성과 스냅샷(Studio CSV → Analytics·Reporting API·GSC), 교훈 카드 | 발행물마다 스냅샷 3개, 승인·기각 교훈 |
| P3 | 8~12주 | 파생물(롱폼 대본·뉴스레터·네이버 패키지), YouTube 비공개 업로드, 다른 계열 평가 모델 | 원본 하나에서 승인된 파생물 4종 |
| P4 | 필요 시 | 생성 B-roll, 쇼츠 클리핑, 배포 연동 | 생성 클립이 런타임 30% 이하 |

### 지켜야 할 정책

- YouTube: 2025-07-15 "inauthentic content"로 개명, 2026-07-16 명확화로 템플릿·반복형, 자극·조작형, 실존 인물 AI 페르소나의 금융·법률·의료가 수익화 제외. 사실적 합성은 공개 의무, C2PA 자동 라벨은 되돌릴 수 없음.
- Google 검색: 제목·메타 설명·구조화 데이터·alt text까지 사람이 사실 확인. 가치 없는 대량 생성은 scaled content abuse.
- 네이버: 블로그의 "AI 활용" 표기는 권장(2026-05, 미표기 제재 없음). 공식 정책 원문은 미확보, 대량 게시·지어낸 경험이 저품질 위험.
- AI 기본법(2026-01-22 시행): 1인 크리에이터는 이용자. 에이전트를 남에게 서비스로 제공하면 표시 의무 가능성이 있어 법률 확인 필요.
- 저작권: 프롬프트만으로는 저작자가 아님(미국 저작권청, 한국저작권위원회). 승인 때 사람이 바꾼 부분을 보존해 기여 증거로 둔다.

설계서 `docs/superpowers/specs/2026-10-27-ai-content-agent-design.md`, 구현 계획 `docs/superpowers/plans/2026-10-27-ai-content-agent.md`(11개 작업, 코드는 임시 사본에서 테스트 통과 확인), 근거 보고서 `reports/AI 콘텐츠 자동화 에이전트 벤치마킹.md`. MrBeast 메모는 진위 미확인, 네이버 정책은 2차 자료 기준이다.

## 10. 외부 오픈소스 지도

**외부 오픈소스 129개를 17개 범주로 정리했고, 그중 40개를 우선 연결 또는 먼저 비교 대상으로 골랐다.** 기준은 기존 앱에 작은 부품으로 붙일 수 있는가, 라이선스·운영 부담을 감당할 수 있는가다. 49개는 1,921 카탈로그와 겹치고 나머지는 이번에 추가했다.

| 범주 | 프로젝트 | 우리에게 쓸 부분 | 판단 | 주의 |
| --- | --- | --- | --- | --- |
| 오피스·팀 운영 | [Paperclip](https://github.com/paperclipai/paperclip) | 여러 에이전트 관리가 병목일 때 R01 총괄의 예산·승인 화면 비교 | 먼저 비교 | MIT, Node.js 20+·pnpm, 에이전트 1개면 불필요 |
| 오피스·팀 운영 | [Multica](https://github.com/multica-ai/multica) | Hermes를 칸반 팀원으로 쓰는 화면·위임 비교 | 먼저 비교 | Go+Next.js+PostgreSQL |
| 오피스·팀 운영 | [AionUi](https://github.com/iOfficeAI/AionUi) | 개인 PC 작업실 UX 비교 | 먼저 비교 | Apache-2.0, Electron |
| 오피스·팀 운영 | [DeerFlow 2](https://github.com/bytedance/deer-flow) | 조사→파일 납품 첫 시범, 기존 Python 제작기를 도구로 연결 | 먼저 비교 | - |
| 오피스·팀 운영 | [Eigent](https://github.com/eigent-ai/eigent) | 개인 PC 중심 오피스 대안 | 먼저 비교 | - |
| 오피스·팀 운영 | [Rowboat](https://github.com/rowboatlabs/rowboat) | 메일·회의가 병목일 때 R14 | 먼저 비교 | - |
| 개인 비서·총괄 런타임 | [Hermes Agent](https://github.com/NousResearch/hermes-agent) | 현재 총괄 후보 유지: 위임·예약·프로필 | 우선 연결 | MIT, 기능은 버전별로 공식 문서 확인 |
| 개인 비서·총괄 런타임 | [OpenClaw](https://github.com/openclaw/openclaw) | 채널 연결·스킬 형식 비교 | 먼저 비교 | 서드파티 스킬은 신뢰하지 않고 읽은 뒤 사용 |
| 에이전트 프레임워크 | [LangGraph](https://github.com/langchain-ai/langgraph) | 장기 재개 공백이 확인되면 해당 업무에만 | 먼저 비교 | MIT |
| 에이전트 프레임워크 | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) | R02 개발 작업자 연결 | 먼저 비교 | - |
| 에이전트 프레임워크 | [PydanticAI](https://github.com/pydantic/pydantic-ai) | FastAPI 결과 스키마와 정합 | 먼저 비교 | - |
| 코딩 에이전트·병렬 실행 | [OpenHands](https://github.com/OpenHands/OpenHands) | R02 개발 제작팀 기준작 | 먼저 비교 | MIT |
| 코딩 에이전트·병렬 실행 | [Codex CLI](https://github.com/openai/codex) | R02 비교 대상 | 먼저 비교 | - |
| 코딩 에이전트·병렬 실행 | [Spec Kit](https://github.com/github/spec-kit) | NX21 요구사항→변경 연결 | 먼저 비교 | - |
| 워크플로·내구 실행 | [n8n](https://github.com/n8n-io/n8n) | 반복 전달·외부 앱 연결(설치 기록 있음) | 우선 연결 | Sustainable Use License(fair-code) |
| 워크플로·내구 실행 | [Windmill](https://github.com/windmill-labs/windmill) | Python 작업자 예약·재시도 비교 | 먼저 비교 | - |
| 리서치·지식·RAG | [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | R05 조사팩 기준작 | 먼저 비교 | - |
| 리서치·지식·RAG | [PaperQA2](https://github.com/Future-House/paper-qa) | NX17 연구실 | 먼저 비교 | - |
| 기억 | [Mem0](https://github.com/mem0ai/mem0) | 기억 후보 저장 비교 | 먼저 비교 | Apache-2.0 |
| 기억 | [Graphiti](https://github.com/getzep/graphiti) | 정정·만료가 있는 기억 | 먼저 비교 | - |
| 브라우저·컴퓨터 사용 | [Playwright MCP](https://github.com/microsoft/playwright-mcp) | R03 실제 사용 흐름 검수 | 우선 연결 | - |
| 브라우저·컴퓨터 사용 | [browser-use](https://github.com/browser-use/browser-use) | 읽기 전용 조사부터 | 먼저 비교 | - |
| 문서·PDF·PPT | [Docling](https://github.com/docling-project/docling) | Ingest·영수증 추출 기준 | 우선 연결 | MIT |
| 문서·PDF·PPT | [Presenton](https://github.com/presenton/presenton) | R15 PPT 초안 | 먼저 비교 | - |
| 콘텐츠·영상·음성 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 자막·회의 전사 | 우선 연결 | MIT |
| 콘텐츠·영상·음성 | [subtitle.js](https://github.com/gsantiago/subtitle.js) | LEARN-I1 시간 근거 | 우선 연결 | MIT |
| 콘텐츠·영상·음성 | [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | 실사·모션 컷 품질 실험 | 먼저 비교 | GPU 필요 |
| 콘텐츠·영상·음성 | [Remotion](https://github.com/remotion-dev/remotion) | 설명형 모션 템플릿(NX06) | 먼저 비교 | 회사 규모별 라이선스, OSI 오픈소스 아님 |
| 배포·뉴스레터 | [Postiz](https://github.com/gitroomhq/postiz-app) | NX19 발행실 비교 | 먼저 비교 | AGPL-3.0 |
| 배포·뉴스레터 | [listmonk](https://github.com/knadh/listmonk) | 회차③·동의 관리 | 먼저 비교 | AGPL-3.0 |
| 지원·CRM·회계·업무 | [Chatwoot](https://github.com/chatwoot/chatwoot) | R09 문의 접수 | 먼저 비교 | - |
| 지원·CRM·회계·업무 | [Actual](https://github.com/actualbudget/actual) | R13 월마감 대사 | 먼저 비교 | MIT |
| 금융 | [OpenBB](https://github.com/OpenBB-finance/OpenBB) | R11 자료 읽기 | 먼저 비교 | 데이터 공급자 약관 별도 |
| 관측·평가·승인 | [promptfoo](https://github.com/promptfoo/promptfoo) | NX10 모델 교체 실험실 | 우선 연결 | MIT |
| 관측·평가·승인 | [Langfuse](https://github.com/langfuse/langfuse) | 호출별 원가·실패 기록 | 먼저 비교 | MIT(코어) |
| 관측·평가·승인 | [DeepEval](https://github.com/confident-ai/deepeval) | pytest와 결합 | 먼저 비교 | - |
| 프로토콜·표준 | [MCP](https://github.com/modelcontextprotocol/modelcontextprotocol) | 도구 연결 표준 | 우선 연결 | - |
| 프로토콜·표준 | [MCP 공식 서버](https://github.com/modelcontextprotocol/servers) | 필요한 서버만 읽기 권한으로 | 우선 연결 | - |
| 3D·2D 오피스 화면 | [Roving Office](https://github.com/atlassian-labs/roving-office) | 관측 화면 1순위, Hermes 연결은 개발 필요 | 먼저 비교 | Apache-2.0 코드, 로고 별도 |
| 큐레이션 목록 | [ottomator-agents](https://github.com/coleam00/ottomator-agents) | TOP3 3순위 | 우선 연결 | 파일 5개 확보 |

### 참고·보류 프로젝트

| 범주 | 프로젝트 | 무엇인가 | 판단 |
| --- | --- | --- | --- |
| 오피스·팀 운영 | [Paperclip Companies](https://github.com/paperclipai/companies) | Agency Agents(역할 167)·Product Compass(48) 등 회사 import 패키지 | 참고 |
| 오피스·팀 운영 | [ChatDev 2.0 (DevAll)](https://github.com/OpenBMB/ChatDev) | 제로코드 멀티에이전트 플랫폼. YAML/GUI DAG, 40개 이상 템플릿, 사람 개입 단계 | 참고 |
| 오피스·팀 운영 | [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | SOP 기반 소프트웨어 회사: PM·아키텍트·엔지니어 역할별 산출물 | 참고 |
| 오피스·팀 운영 | [Claw Empire](https://github.com/GreenSheep01201/claw-empire) | CLI·API 에이전트를 직원으로 두는 로컬 가상 회사. git worktree로 병렬 개발 격리 | 참고 |
| 오피스·팀 운영 | [Kortix Suna](https://github.com/kortix-ai/suna) | 요청·실행·산출·협업을 한 회사 프로젝트로 묶는 작업실 원형 | 참고 |
| 오피스·팀 운영 | [OpenAgents](https://github.com/openagents-org/openagents) | 이슈·대화·파일·공유 브라우저가 있는 에이전트 협업 공간 | 참고 |
| 오피스·팀 운영 | [Sim](https://github.com/simstudioai/sim) | 에이전트 워크플로와 테이블·파일·지식을 한 화면에 | 참고 |
| 개인 비서·총괄 런타임 | [Agent Zero](https://github.com/agent0ai/agent-zero) | 도구를 스스로 만들어 쓰는 범용 개인 에이전트 | 참고 |
| 개인 비서·총괄 런타임 | [Khoj](https://github.com/khoj-ai/khoj) | 개인 문서·웹을 검색하는 두 번째 두뇌 | 참고 |
| 개인 비서·총괄 런타임 | [Open WebUI](https://github.com/open-webui/open-webui) | 로컬 모델 채팅 UI와 RAG | 참고 |
| 에이전트 프레임워크 | [CrewAI](https://github.com/crewAIInc/crewAI) | 역할·작업 기반 팀 프레임워크 | 참고 |
| 에이전트 프레임워크 | [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | AutoGen·Semantic Kernel 후속 SDK(Python·.NET) | 참고 |
| 에이전트 프레임워크 | [AG2](https://github.com/ag2ai/ag2) | AutoGen 커뮤니티 계열 멀티에이전트 | 참고 |
| 에이전트 프레임워크 | [Google ADK](https://github.com/google/adk-python) | A2A 네이티브 에이전트 개발 키트 | 참고 |
| 에이전트 프레임워크 | [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | handoff·guardrail·tracing | 참고 |
| 에이전트 프레임워크 | [smolagents](https://github.com/huggingface/smolagents) | 코드로 행동하는 경량 에이전트 | 참고 |
| 에이전트 프레임워크 | [Agno](https://github.com/agno-agi/agno) | 팀·메모리·AgentOS 런타임 | 참고 |
| 에이전트 프레임워크 | [OWL / CAMEL](https://github.com/camel-ai/owl) | 역할극 멀티에이전트, GUI | 참고 |
| 에이전트 프레임워크 | [Mastra](https://github.com/mastra-ai/mastra) | TypeScript 에이전트·워크플로·평가 | 참고 |
| 에이전트 프레임워크 | [Letta](https://github.com/letta-ai/letta) | 상태 보존 에이전트·메모리 블록 | 참고 |
| 코딩 에이전트·병렬 실행 | [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) | 코딩 에이전트 작업 칸반·리뷰 | 보류 |
| 코딩 에이전트·병렬 실행 | [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | 100줄대 최소 개발 에이전트 | 참고 |
| 코딩 에이전트·병렬 실행 | [Aider](https://github.com/Aider-AI/aider) | 터미널 페어 프로그래밍, git 커밋 단위 | 참고 |
| 코딩 에이전트·병렬 실행 | [Cline](https://github.com/cline/cline) | IDE 코딩 에이전트, 단계별 승인 | 참고 |
| 코딩 에이전트·병렬 실행 | [Goose](https://github.com/block/goose) | 로컬 확장형 에이전트, MCP | 참고 |
| 코딩 에이전트·병렬 실행 | [OpenCode](https://github.com/sst/opencode) | 터미널 코딩 에이전트, 여러 모델 | 참고 |
| 코딩 에이전트·병렬 실행 | [Gemini CLI](https://github.com/google-gemini/gemini-cli) | Google 터미널 에이전트 | 참고 |
| 코딩 에이전트·병렬 실행 | [Claude Squad](https://github.com/smtg-ai/claude-squad) | worktree별 병렬 에이전트 세션 | 참고 |
| 코딩 에이전트·병렬 실행 | [Task Master](https://github.com/eyaltoledano/claude-task-master) | PRD를 의존성 있는 작업으로 분해 | 참고 |
| 코딩 에이전트·병렬 실행 | [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | 분석가·PM·아키텍트 역할 에이전트 방법론 | 참고 |
| 코딩 에이전트·병렬 실행 | [wshobson/agents](https://github.com/wshobson/agents) | Claude Code 서브에이전트·플러그인 대형 모음 | 참고 |
| 코딩 에이전트·병렬 실행 | [Archon](https://github.com/coleam00/Archon) | 지식·작업 관리 MCP 서버(Cole Medin) | 참고 |
| 워크플로·내구 실행 | [n8n AI Starter Kit](https://github.com/n8n-io/self-hosted-ai-starter-kit) | n8n+Ollama+Qdrant Docker 묶음 | 보류 |
| 워크플로·내구 실행 | [Activepieces](https://github.com/activepieces/activepieces) | TypeScript 확장형 자동화, MCP | 참고 |
| 워크플로·내구 실행 | [Dify](https://github.com/langgenius/dify) | LLM 앱·워크플로·RAG 플랫폼 | 참고 |
| 워크플로·내구 실행 | [Flowise](https://github.com/FlowiseAI/Flowise) | 드래그형 에이전트·RAG 빌더 | 참고 |
| 워크플로·내구 실행 | [Langflow](https://github.com/langflow-ai/langflow) | 시각 에이전트 플로·API 배포 | 참고 |
| 워크플로·내구 실행 | [Temporal](https://github.com/temporalio/temporal) | 내구 실행: 재시도·재개·중복 방지 | 참고 |
| 리서치·지식·RAG | [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | LangGraph 딥리서치 에이전트 | 참고 |
| 리서치·지식·RAG | [STORM](https://github.com/stanford-oval/storm) | 관점별 질문으로 위키형 문서 작성 | 참고 |
| 리서치·지식·RAG | [Onyx](https://github.com/onyx-dot-app/onyx) | 사내 문서 연결·검색·인용 답변 | 참고 |
| 리서치·지식·RAG | [RAGFlow](https://github.com/infiniflow/ragflow) | 문서 깊이 파싱 기반 RAG 엔진 | 참고 |
| 리서치·지식·RAG | [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | 로컬 RAG 데스크톱 | 참고 |
| 기억 | [Cognee](https://github.com/topoteretes/cognee) | 그래프 기반 기억 파이프라인 | 참고 |
| 브라우저·컴퓨터 사용 | [Stagehand](https://github.com/browserbase/stagehand) | Playwright 위 자연어 브라우저 동작 | 참고 |
| 브라우저·컴퓨터 사용 | [Skyvern](https://github.com/Skyvern-AI/skyvern) | 시각 기반 웹 업무 자동화 | 참고 |
| 브라우저·컴퓨터 사용 | [UI-TARS Desktop](https://github.com/bytedance/UI-TARS-desktop) | 화면을 보고 조작하는 데스크톱 에이전트 | 참고 |
| 브라우저·컴퓨터 사용 | [Agent S](https://github.com/simular-ai/Agent-S) | 컴퓨터 사용 에이전트 프레임워크 | 참고 |
| 문서·PDF·PPT | [Marker](https://github.com/datalab-to/marker) | PDF→Markdown 고품질 변환 | 참고 |
| 문서·PDF·PPT | [MinerU](https://github.com/opendatalab/MinerU) | 수식·표 포함 PDF 추출 | 참고 |
| 문서·PDF·PPT | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 다국어 OCR·문서 구조 | 참고 |
| 문서·PDF·PPT | [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx) | 문서 보관·OCR·태그·버전 | 참고 |
| 문서·PDF·PPT | [PPTAgent](https://github.com/icip-cas/PPTAgent) | 참조 덱 기반 PPT 생성·평가 | 참고 |
| 문서·PDF·PPT | [Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF) | PDF 병합·분할·변환 도구 서버 | 참고 |
| 콘텐츠·영상·음성 | [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 주제→대본→소재→음성→자막→숏폼 | 참고 |
| 콘텐츠·영상·음성 | [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | 코드 기반 설명 애니메이션 | 참고 |
| 콘텐츠·영상·음성 | [WhisperX](https://github.com/m-bain/whisperX) | 단어 단위 타임스탬프·화자 분리 | 참고 |
| 콘텐츠·영상·음성 | [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | 다국어 TTS·음성 복제 | 참고 |
| 콘텐츠·영상·음성 | [F5-TTS](https://github.com/SWivid/F5-TTS) | 제로샷 TTS | 참고 |
| 배포·뉴스레터 | [Ghost](https://github.com/TryGhost/Ghost) | 블로그+뉴스레터 | 참고 |
| 배포·뉴스레터 | [Mixpost](https://github.com/inovector/mixpost) | SNS 일정·발행 | 참고 |
| 지원·CRM·회계·업무 | [Twenty](https://github.com/twentyhq/twenty) | 오픈소스 CRM | 참고 |
| 지원·CRM·회계·업무 | [Plane](https://github.com/makeplane/plane) | 이슈·관계·사이클 관리 | 참고 |
| 지원·CRM·회계·업무 | [Invoice Ninja](https://github.com/invoiceninja/invoiceninja) | 견적·청구·결제 | 참고 |
| 금융 | [Freqtrade](https://github.com/freqtrade/freqtrade) | 크립토 전략 백테스트·봇 | 보류 |
| 금융 | [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 에쿼티 리서치 에이전트 | 참고 |
| 금융 | [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 분석가·리서처·트레이더·리스크 역할 토론 | 참고 |
| 금융 | [Qlib](https://github.com/microsoft/qlib) | 정량 투자 연구 플랫폼 | 참고 |
| 관측·평가·승인 | [Arize Phoenix](https://github.com/Arize-ai/phoenix) | 추적·평가·데이터셋 | 참고 |
| 관측·평가·승인 | [Opik](https://github.com/comet-ml/opik) | 추적·평가 | 참고 |
| 관측·평가·승인 | [HumanLayer](https://github.com/humanlayer/humanlayer) | 에이전트 행동 전 사람 승인 요청 | 참고 |
| 관측·평가·승인 | [E2B](https://github.com/e2b-dev/E2B) | 에이전트용 격리 샌드박스 | 참고 |
| 프로토콜·표준 | [A2A](https://github.com/a2aproject/A2A) | 에이전트↔에이전트 통신. 2026-08 AAIF 합류 | 참고 |
| 프로토콜·표준 | [AG-UI](https://github.com/ag-ui-protocol/ag-ui) | 에이전트↔사용자 화면 이벤트 | 참고 |
| 프로토콜·표준 | [Agent Client Protocol](https://github.com/zed-industries/agent-client-protocol) | 편집기↔코딩 에이전트 표준(ACP) | 참고 |
| 3D·2D 오피스 화면 | [Agentshire](https://github.com/Agentshire/Agentshire) | OpenClaw 3D 마을·캐릭터 편집 | 보류 |
| 3D·2D 오피스 화면 | [Hermes Virtual Office](https://github.com/JuniorXcoder/hermes-virtual-office) | Hermes CLI/A2A 경로가 있는 가상 오피스 | 참고 |
| 3D·2D 오피스 화면 | [Hermes3D](https://github.com/iamlukethedev/Hermes3D) | Hermes bridge가 있는 3D 오피스 | 참고 |
| 3D·2D 오피스 화면 | [Pixel Agents](https://github.com/pixel-agents-hq/pixel-agents) | 터미널 코딩 에이전트를 픽셀 캐릭터로 보여 주는 뷰어 | 참고 |
| 3D·2D 오피스 화면 | [Star Office UI](https://github.com/ringhyacinth/Star-Office-UI) | OpenClaw 연동 픽셀 오피스 상태판(Flask+Phaser) | 참고 |
| 3D·2D 오피스 화면 | [AgentOffice](https://github.com/harishkotra/agent-office) | 보드에서 작업을 가져가는 픽셀 오피스, Ollama | 참고 |
| 3D·2D 오피스 화면 | [AI Town](https://github.com/a16z-infra/ai-town) | 생성형 에이전트 마을 시뮬레이션 | 참고 |
| 3D·2D 오피스 화면 | [Generative Agents](https://github.com/joonspk-research/generative_agents) | Stanford Smallville 연구 코드 | 참고 |
| 큐레이션 목록 | [awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) | AI 에이전트 큐레이션 | 참고 |
| 큐레이션 목록 | [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) | 실행 가능한 LLM 앱 예제 모음 | 참고 |
| 큐레이션 목록 | [500 AI Agents Projects](https://github.com/ashishpatel26/500-AI-Agents-Projects) | 산업별 에이전트 사례 목록 | 참고 |
| 큐레이션 목록 | [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | MCP 서버 목록 | 참고 |
| 큐레이션 목록 | [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | Claude Code 명령·훅·워크플로 | 참고 |
| 큐레이션 목록 | [ai-cookbook](https://github.com/daveebbelaar/ai-cookbook) | 에이전트 복잡도 5단계 예제(MIT) | 참고 |

### 2026년에 바뀐 판단

- **표준이 한곳에 모였다.** MCP(2025-12)에 이어 A2A도 2026-08 Agentic AI Foundation에 합류했다. 도구 연결은 MCP, 에이전트 사이 인계는 A2A.
- **AutoGen은 유지보수 모드다.** 새로 볼 대상은 Microsoft Agent Framework 또는 AG2.
- **에이전트 회사 레이어가 생겼다.** Paperclip·Multica·ChatDev 2.0·Claw Empire. 에이전트가 하나면 필요 없고, 여럿을 관리하는 것이 병목일 때 비교한다.

별 수와 순위 기사는 대부분 제작사·홍보성 출처라 채택 근거로 쓰지 않았다. 설치·실행 검증은 하지 않았다.

## 11. 벤치마크 1,921선과 3D 오피스 후보

**3D 오피스는 업무 위치를 보여 주는 지도이며 업무 완료의 증거가 아니다.** [벤치마크 탐색기](https://heobrain-ai-office-benchmarks-20261020.ihtwandy0528.chatgpt.site/)는 GitHub 공식 검색 응답 25개에서 찾은 2,116개 중 1,921개를 남긴 부품 후보 목록이다(2026-10-19 수집, 허용적 라이선스 표시 1,358개).

| 범주 | 후보 수 |
| --- | --- |
| 워크플로연결 | 457 |
| 에이전트프레임워크 | 446 |
| 연구지식 | 321 |
| 개발 | 228 |
| 콘텐츠 | 122 |
| 금융 | 111 |
| 개인비서 | 105 |
| 자료모음 | 75 |
| 기타기반 | 56 |

### 먼저 비교할 3D 후보 8개

| 후보 | 확인한 범위 | 채택 판단 |
| --- | --- | --- |
| [Roving Office](https://github.com/atlassian-labs/roving-office) | Apache-2.0 코드, Three.js, 관측 이벤트, 기본 모의 에이전트. 브랜드 자산 별도 | 관측 화면 우선 비교. Hermes 연결은 별도 개발 |
| [Hermes Virtual Office](https://github.com/JuniorXcoder/hermes-virtual-office) | MIT, 실제 Hermes CLI/A2A 경로. Origin 방어는 사용자 인증이 아님 | 로컬 연결 참고. 공개 서비스는 인증 보강 |
| [Hermes3D](https://github.com/iamlukethedev/Hermes3D) | MIT, 실제 bridge와 모의 gateway. 일부 승인 응답은 정책을 저장하지 않는 shim | 관측부터 검증. 승인 UI만 믿고 실행 권한을 주지 않음 |
| [AI Office](https://github.com/Gaurav2693/ai-office) | MIT, React/Three.js 시각 모형, 실제 AI API 호출 없음 | 조명·카메라·공간 표현 실습 참고 |
| [Agentshire](https://github.com/Agentshire/Agentshire) | MIT, OpenClaw 마을·편집기. 지원 버전 제약 | 게임형 UX 참고. Hermes 호환성 미검증 |
| [Offivo](https://github.com/OneByJorah/offivo) | MIT, 개명한 협업 앱과 이전 Hermes 코드 공존 | 문서·현행 실행 경로 대조 전 보류 |
| [Agents Office](https://github.com/ajsahni/agents-office) | Noncommercial + 다른 에이전트 시스템 결합 제한 | 코드 재사용 후보에서 제외 |
| [SimOffice](https://github.com/johnkf5-ops/simoffice) | 현행 독점 라이선스, 구독 제품 | 무료 오픈소스 후보에서 제외 |

### 관련 영상 18개 (제목·채널·설명 확인, 전편 시청 아님)

1. [One Command, Three AI Agents: My Claude Code Team](https://www.youtube.com/watch?v=-14NKNpWr1M) · Bekhruz AI · 제작팀 자동화 · 사용자 링크
2. [I Built an AI Office With 31 Agents (Full Build)](https://www.youtube.com/watch?v=t0hGE-aaAds) · Bekhruz AI · 3D 오피스 · 이전 편
3. [Hermes Agent Virtual Office - Command Control AI Hermes](https://www.youtube.com/watch?v=ezEthYDU_bw) · Kang Njun · 3D 오피스 · Hermes 직접 후보
4. [Agentshire — Your AI Agents Live in a 3D Town You Built Yourself | OpenClaw Plugin](https://www.youtube.com/watch?v=R6YXvkkwo9I) · Chn.Xiaoxin · 3D 마을 · OpenClaw
5. [Claude Office v0.5.0](https://www.youtube.com/watch?v=AM2UjKYB8Ew) · Paul Robello · 2D 픽셀 오피스
6. [Hermes3D Is INSANE: AI Agents Now Have a 3D Office](https://www.youtube.com/watch?v=_8kq_V-XG-w) · Julian Goldie SEO · 3D 오피스 소개
7. [Getting Started with CrewAI Open Source](https://www.youtube.com/watch?v=-kSOTtYzgEw) · CrewAI · 자동화 프레임워크 공식 입문
8. [CrewAI Tutorial - Next Generation AI Agent Teams (Fully Local)](https://www.youtube.com/watch?v=tnejrr-0a94) · Matthew Berman · 자동화 프레임워크 커뮤니티 강의
9. [Agents Create a Job Description for crewAI!](https://www.youtube.com/watch?v=u98wEMz-9to) · Build New Things · 자동화 응용: 채용 공고
10. [AI Agents on the cloud plan my next trip! 🤖☁️✈️](https://www.youtube.com/watch?v=xis7rWp-hjs) · Build New Things · 자동화 응용: 여행 계획
11. [Stock Analysis with AI Agents, using CrewAI 🚣](https://www.youtube.com/watch?v=e0Uj4yWdaAg) · Build New Things · 자동화 응용: 투자 리서치
12. [How To Install MetaGPT - Build A Startup With One Prompt!!](https://www.youtube.com/watch?v=uT75J_KG_aY) · Matthew Berman · 자동화 응용: 소프트웨어 팀
13. [GPT Researcher UX/UI - New](https://www.youtube.com/watch?v=f60rlc_QCxE) · Assaf Elovic · 자동화 응용: 연구 보고서
14. [OWL with GUI - General Multi-Agent Collaboration](https://www.youtube.com/watch?v=8XlqVyAZOr8) · Fahd Mirza · 자동화 프레임워크 GUI 소개
15. [Transformer Lab Application Demo in Five Minutes  - July 2024](https://www.youtube.com/watch?v=tY5TAvKviLo) · Ali Asaria · 주변 도구: 로컬 모델 관리
16. [Let's Get Fired: Using AI Coding Assistant AIDER to do my Engineering Job](https://www.youtube.com/watch?v=MPYFPvxfGZs) · IndyDevDan · 자동화 응용: 개발 보조
17. [Holy Grail: FREE Coding Assistant That Can Build From EXISTING CODE BASE](https://www.youtube.com/watch?v=df8afeb1FY8) · Matthew Berman · 자동화 응용: 기존 코드 개발 보조
18. [ALL ROADS LEAD to AI CODING: Cursor, Aider in the browser, Multi file Prompting](https://www.youtube.com/watch?v=YALpX8oOn78) · IndyDevDan · 자동화 응용: 개발 도구 비교

## 12. 29분야 TOP3

**전체 구축 우선 TOP3는 WRITER Agent의 자료→콘텐츠 납품 묶음, OpenHands Issue-to-PR, CMDS LLM Wiki다.** 29개 분야에서 총 317개 AI 후보를 비교했다.

| 분야 | 비교 수 | 1순위 | 2순위 | 3순위 |
| --- | --- | --- | --- | --- |
| F01 총괄·프로젝트·비서팀 | 10 | [Kortix](https://kortix.com/docs/cli#the-everyday-loop) | [DeerFlow 2.0](https://raw.githubusercontent.com/bytedance/deer-flow/main/skills/public/deep-research/SKILL.md) | [Paperclip](https://docs.paperclip.ing/guides/getting-started/five-minute-path/) |
| F02 주식·ETF | 10 | [FinRobot Equity](https://raw.githubusercontent.com/AI4Finance-Foundation/FinRobot/master/finrobot_equity/README.md) | [Fiscal.ai MCP Skills (comp-set/financial-model)](https://docs.fiscal.ai/docs/guides/mcp-skills) | [Quartr Pro Automations](https://quartr.com/automations) |
| F03 BTC·크립토 | 11 | [FreqAI/Freqtrade](https://www.freqtrade.io/en/stable/freqai-running/) | [CoinGecko MCP + Claude research workflow](https://www.coingecko.com/learn/ai-crypto-research-mcp) | [Heurist Mesh](https://github.com/heurist-network/heurist-agent-framework/blob/main/mesh/agents/ask_heurist_agent.py) |
| F04 딥리서치·시장·경쟁조사 | 11 | [GPT Researcher](https://raw.githubusercontent.com/assafelovic/gpt-researcher/master/multi_agents/README.md) | [LangChain Open Deep Research](https://raw.githubusercontent.com/langchain-ai/open_deep_research/main/src/open_deep_research/deep_researcher.py) | [DeerFlow 2.0](https://raw.githubusercontent.com/bytedance/deer-flow/main/skills/public/deep-research/SKILL.md) |
| F05 블로그·편집·번역 | 14 | [WRITER Agent](https://support.writer.com/articles/2664880799-how-to-use-writer-agent) | [StoryChief](https://storychief.io/blog/how-to-automate-your-content-publishing-workflow-with-mcp) | [MoneyPrinterTurbo](https://raw.githubusercontent.com/harry0703/MoneyPrinterTurbo/main/docs/skill/SKILL.md) |
| F06 마케팅·SEO·광고 운영 | 14 | [Gumloop — 광고 운영 agent](https://www.gumloop.com/templates/google-ads-analyst) | [HubSpot — Breeze 기반 CRM 워크플로](https://knowledge.hubspot.com/workflows/create-workflows) | [Clay — inbound 수요 포착·보강·segmentation](https://www.clay.com/blog/manage-enrich-inbound-automatically) |
| F07 SNS·뉴스레터·배포 | 11 | [Postiz](https://docs.postiz.com/mcp/introduction) | [ContentStudio](https://contentstudio.io/mcp-server) | [beehiiv](https://www.beehiiv.com/support/article/41262491804439-what-you-can-do-with-the-beehiiv-mcp) |
| F08 영업·리드·CRM·제안 | 11 | [Clay](https://www.clay.com/blog/manage-enrich-inbound-automatically) | [PandaDoc](https://support.pandadoc.com/en/articles/12108203-template-workflow-builder-and-guided-document-creation-full-guide) | [HubSpot Breeze Prospecting Agent](https://knowledge.hubspot.com/prospecting/use-the-prospecting-agent) |
| F09 고객지원 | 10 | [Intercom Fin Procedures](https://www.intercom.com/help/en/articles/12495167-fin-procedures-explained) | [Gorgias AI Agent Actions](https://docs.gorgias.com/en-US/create-an-action-for-ai-agent-567325) | [eesel AI Helpdesk agent](https://docs.eesel.ai/use-cases/helpdesk) |
| F10 상품·전자상거래·매출 | 10 | [Shopify Sidekick — 상품·draft order·매출 export](https://help.shopify.com/en/manual/ai-powered-tools/sidekick/help-and-guidance) | [Constructor AI Shopping Agent + agentic checkout](https://docs.constructor.com/docs/integrating-with-constructor-partner-integrations-agentic-checkout-integrations-stripe) | [Churnkey Adaptive Offers — AI retention 할인](https://docs.churnkey.co/cancel-flows/adaptive-offers/) |
| F11 PDF 수집·OCR·구조화 | 11 | [Docling — 로컬 PDF→구조 문서](https://raw.githubusercontent.com/docling-project/docling/main/README.md) | [LlamaParse — 비동기 agentic parse](https://developers.llamaindex.ai/llamaparse/parse/getting_started/) | [PaddleOCR-VL — 다페이지 구조 재구성](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md) |
| F12 PDF 보고서·전자책 제작 | 10 | [Gamma — AI ebook→세로 PDF](https://help.gamma.app/en/articles/16767225-how-do-i-create-an-ebook-in-gamma) | [Genspark AI Docs — 지시→서식 문서/PDF](https://www.genspark.ai/helpcenter/ai-docs) | [GPT Researcher — deep research→CSS PDF](https://raw.githubusercontent.com/assafelovic/gpt-researcher/main/backend/report_type/deep_research/main.py) |
| F13 PPT 기획·생성·편집·검수 | 11 | [Presenton](https://docs.presenton.ai/api-guides/presentation-generation-flows) | [PPTAgent](https://raw.githubusercontent.com/icip-cas/PPTAgent/main/skills/pptagent/SKILL.md) | [Beautiful.ai](https://support.beautiful.ai/hc/en-us/articles/12885226948109-Creating-a-presentation-with-AI) |
| F14 Excel·데이터 분석·차트 | 11 | [Microsoft Copilot in Excel](https://support.microsoft.com/en-us/excel/get-direct-answers-to-your-data-analysis-questions) | [Quadratic](https://www.quadratichq.com/ai/charts) | [Better Analyst (formerly Formula Bot)](https://betteranalyst.com/docs/get-started/quickstart) |
| F15 디자인·이미지·카드뉴스 | 11 | [Canva Magic Design](https://www.canva.com/help/use-magic-design/) | [Kittl Creative Agent](https://help.kittl.com/ai-tools/use-creative-agent/) | [Photoroom Batch](https://help.photoroom.com/en/articles/14178972-download-batch-images-web-app) |
| F16 영상·숏폼 | 10 | [Pictory](https://kb.pictory.ai/en/articles/8468908-how-to-generate-a-video-and-download-it) | [HeyGen](https://help.heygen.com/en/articles/9834825-how-to-download-or-export-a-video) | [Descript](https://help.descript.com/export-and-share/export-and-publishing-overview) |
| F17 오디오·음성·자막 | 10 | [ElevenLabs Dubbing](https://elevenlabs.io/docs/eleven-api/guides/cookbooks/dubbing) | [Adobe Podcast](https://helpx.adobe.com/podcast/adobe-podcast-faq.html) | [AssemblyAI End-to-End Examples](https://www.assemblyai.com/docs/getting-started/end-to-end-examples/meeting-notetaker) |
| F18 개발·코딩 | 15 | [OpenHands (Agent Canvas)](https://docs.openhands.dev/openhands/usage/agent-canvas/prebuilt/issue-to-pr) | [OpenAI Codex](https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex) | [GitHub Copilot cloud agent](https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/overview) |
| F19 QA·릴리스 | 10 | [Playwright Test Agents](https://playwright.dev/docs/test-agents) | [CodeRabbit](https://docs.coderabbit.ai/finishing-touches/fix-ci) | [BrowserStack (Test Companion)](https://www.browserstack.com/docs/test-companion/web-testing/test-lifecycle/fix-failed-tests) |
| F20 보안·운영·인프라 | 12 | [HolmesGPT](https://holmesgpt.dev/0.23.0/walkthrough/investigating-prometheus-alerts/) | [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/production-operations-autonomous-incident-response.html) | [Sentry Seer](https://docs.sentry.io/api/seer/start-seer-issue-fix/) |
| F21 사내지식·문서검색 | 10 | [Glean Enterprise Search](https://www.glean.com/enterprise-search) | [Microsoft Copilot Search](https://learn.microsoft.com/en-us/microsoft-365/copilot/copilot-search-overview) | [Notion Enterprise Search](https://www.notion.com/help/enterprise-search) |
| F22 계약·전자서명 | 10 | [fynk AI Playbooks](https://help.fynk.com/en/articles/302472-playbooks) | [Ironclad AI Assist / AI Playbooks](https://support.ironcladapp.com/hc/en-us/articles/13740722454935-AI-Assist-Overview) | [Spellbook Playbooks](https://help.spellbook.legal/en/articles/9926250-playbooks-overview) |
| F23 회계·지출·정산 | 10 | [Dext AI Assist / bookkeeping workflow](https://help.dext.com/en/articles/416727-getting-started-with-dext-for-accountants-and-bookkeepers) | [Expensify SmartScan + Concierge / agents](https://help.expensify.com/articles/new-expensify/ai-agents/Learn-About-AI-in-Expensify) | [Ramp Accounting Agent](https://support.ramp.com/ramp-accounting-agent-enablement-daily-use-admin-guide/) |
| F24 메일·일정·회의 | 10 | [Google Workspace Gemini (Meet notes)](https://support.google.com/meet/answer/14754931?co=GENIE.Platform%3DDesktop&hl=en-CA) | [Reclaim.ai 2.0](https://help.reclaim.ai/en/articles/15280604-reclaim-2-0-faq) | [Fireflies.ai Notepad / AI Skills](https://guide.fireflies.ai/articles/6653885315-learn-about-the-fireflies-notepad) |
| F25 채용·커리어 | 10 | [Huntr AI Tailored Resume](https://help.huntr.co/en/articles/13005373-building-your-tailored-resume) | [Metaview Notes](https://support.metaview.ai/notes/overview) | [Paradox Conversational Scheduling](https://www.paradox.ai/products/conversational-scheduling) |
| F26 학습·교육 | 11 | [Brisk Teaching Connector](https://help.briskteaching.com/hc/en-us/articles/50241696224020-Set-up-the-Brisk-Connector-for-Claude-and-ChatGPT) | [Diffit Resource Creation](https://web.diffit.me/diffit-certified-educator-course/create) | [NotebookLM Source-Grounded Learning](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/) |
| F27 생활·구매·여행 | 10 | [Mindtrip](https://resources.mindtrip.ai/travelers/help/traveler-faqs) | [Amazon Alexa for Shopping (formerly Rufus)](https://www.aboutamazon.com/news/retail/alexa-for-shopping-ai-assistant) | [Instacart Clementine](https://company.instacart.com/pressreleases/meet-clementine-instacart-s-ai-shopping-assistant-that-takes-what-s-for-dinner-off-your-plate) |
| F28 건강·의료자료 지원 | 10 | [Guava Assistant / AI Visit Prep](https://guavahealth.com/news/enhancing-doctor-visits-guava-ai-powered-auto-prep) | [PicnicHealth Picnic AI](https://help.picnichealth.com/en/articles/4871744) | [Mindsera AI Journal + MCP](https://mindsera.com/help/account/connect-ai-assistants-mcp) |
| F29 Obsidian·PKM·LLM Wiki | 13 | [CMDS LLM Wiki — 구요한 공개 작업법](https://llm-wiki.cmdspace.work/) | [Smart Second Brain — 구 Smart2Brain](https://smartsecondbrain.dev/) | [Companion for Claude](https://github.com/cavi-ai/claude-obsidian) |

## 13. 코드 후보 30개

공개 코드라도 LICENSE가 없으면 같은 이용 허가로 보지 않는다. 개인 자료 폴더 링크는 넣지 않았다.

| ID | 플랫폼 | 강의·영상 | 받는 조건 | 재사용 판단 | 판단 이유 |
| --- | --- | --- | --- | --- | --- |
| FC-CODE-01 | FastCampus | [MCP와 A2A로 끝내는 상상도 못할 Multi-Agent 구축](https://fastcampus.co.kr/data_online_mcpa2a) | 공개 코드 | 우선 재사용 | Planner/Supervisor 인계 계약과 별도 Basic의 검토 패턴만 선별. 전체 A2A 실행 환경은 마감 필수 아님 |
| FC-CODE-02 | FastCampus | [바이브코딩으로 10시간 만에 완성하는 12가지 AI Agent & RAG](https://fastcampus.co.kr/biz_online_vibeagent) | 공개 코드 | 보류 | 공개 코드와 하위 Apache 허가는 확인했으나 전체 root 허가 범위를 확정하지 못함. 구체 재사용 파일의 권리 확인이 먼저 |
| FC-CODE-03 | FastCampus | [MCP x n8n으로 이제야 실현하는 AI 자동화](https://fastcampus.co.kr/biz_online_mcpn8n) | 공개 코드 | 보류 | 일반 공개 라이선스를 확인하지 못함. 수강생 권리 범위 확인 전 공개 제품에 코드 복제하지 않음 |
| FC-CODE-04 | FastCampus | [실전 AI Agent의 모든 것 : 34개 프로젝트로 MCP부터 GraphRAG Agent까지 (by. 공원나연)](https://fastcampus.co.kr/data_online_graphrag) | 공개 코드 | 보류 | 공개 실습은 있으나 일반 허가 미확인·오래된 환경. GraphRAG 전체 이전은 토요일 주력 흐름 뒤로 |
| FC-CODE-05 | FastCampus | [비즈니스 자동화 마스터 : AI로 구현하는 Agent급 13가지 실전 워크플로우 자동화](https://fastcampus.co.kr/biz_online_13agent) | 수강생 자료 | 조건부 검토 | 학생자료 제공 약속은 확인. 실제 파일·이용 조건 확인 전 납품 필수 코드로 잡지 않음 |
| FC-CODE-06 | FastCampus | [바이브코딩 + 자동화 풀 패키지: 21개 프로젝트로 내 인생 자동화 (w. n8n x Claude Code)](https://fastcampus.co.kr/biz_online_vibecodingn8n) | 수강생 자료 | 참고만 | 학생 템플릿의 비영리/배포 조건을 공개 상업 제품 허가로 확대하지 않고 방법 학습에 활용 |
| C101-CODE-01 | CLASS101 | [실무에 바로 쓰는 자동화! n8n, Google 100% 활용하기](https://class101.net/ko/products/687ca1006a9a3692f2f22a96) | 내 보유 자료 | 조건부 검토 | 이미 가진 JSON4개를 정적 검토. n8n 준비 시 비활성 사본의 작은 처리부터; 미준비면 기존 Python으로 독립 설계 |
| C101-CODE-02 | CLASS101 | [[입문] 클로드코드로 시작하는 왕초보 업무 자동화](https://class101.net/ko/products/6a2f814d13b24cc712ceb695) | 내 보유 자료 | 조건부 검토 | 보유 견적서/스킬의 필요한 입력·결과부터 확인. Ubuntu 실행·학생자료 이용 범위 확인이 필요 |
| C101-CODE-03 | CLASS101 | [n8n으로 완성하는 AI 에이전트 - 나를 대신할 업무 자동화 입문](https://class101.net/ko/products/68d4d1a4dbb9c4ede54315ae) | 내 보유 자료 | 조건부 검토 | 보유 원본/목차는 확인. 현재 버전 노드·자격·실행 범위를 검토한 한 워크플로만 사용 후보 |
| C101-CODE-04 | CLASS101 | [Gen AI RAG 실전 가이드, Langchain을 활용한 AI 챗봇 완전정복](https://class101.net/ko/products/682d349b3d5487dd2bc944c2) | 내 보유 자료 | 조건부 검토 | 개인 보유 RAG 실습 중 필요한 추출/검색 계약부터 대조. 전면 프레임워크 이전은 하지 않음 |
| C101-CODE-05 | CLASS101 | [AI로 하는 파이썬 코딩부터 랭체인으로 챗봇 만들기까지](https://class101.net/ko/products/6773d7a256769770590c3fe5) | 내 보유 자료 | 조건부 검토 | 기존 개인 코드의 입력·기간·권한을 확인해 한 업무로 축소. 파일명만으로 실행 완료를 추정하지 않음 |
| C101-CODE-06 | CLASS101 | [생성형 AI 개발자로 입문 ： 나만의 챗봇 서비스 하기 (RAG 구축부터 서비스 배포까지)](https://class101.net/ko/products/67c5a4394bb5a248e32b2936) | 내 보유 자료 | 조건부 검토 | 보유 챗봇 예제는 대체 앱이 아니라 검색/배포 학습 자료. 기존 인증·원장 경계에 맞춘 뒤 사용 |
| IF01 | Inflearn | [[단테랩스] Hermes × Codex 로 세우는 나만의 AI 가상 오피스 (8주 마스터 과정)](https://www.inflearn.com/course/hermes-agent-advance?cid=342122) | 수강생 자료 | 조건부 검토 | Hermes 방향은 가깝고 학생용 스킬·가이드 제공. 전체 오피스 앱 코드 미확인이라 새 구매·8주 완강을 마감 선행조건으로 두지 않음 |
| IF02 | Inflearn | [회사에서 바로 쓰는 업무자동화 AI 에이전트 (w. n8n, LangGraph)](https://www.inflearn.com/course/회사에서-바로쓰는-업무자동화-ai에이전트?cid=337281) | 공개 코드 | 보류 | 공개 실습 repo의 일반 라이선스 미확인. 학생용 n8n JSON과 공개 Python 예제 범위를 구분 |
| IF03 | Inflearn | [LangGraph를 활용한 AI Agent 개발 (feat. MCP)](https://www.inflearn.com/course/랭그래프-활용한-llm에이전트-개발?cid=335334) | 공개 코드 | 우선 재사용 | MIT의 HITL·멀티에이전트 결과 계약을 선별. Python 최소버전 불일치·의존성·예제 자격 정리 후 별도 환경에서 검증 |
| IF04 | Inflearn | [[인프런어워드 베스트셀러] 코딩 없이 AI 자동화 전문가가 되는 법, n8n 완벽 가이드](https://www.inflearn.com/course/ai-자동화-n8n?cid=337053) | 수강생 자료 | 조건부 검토 | 학생용 JSON 제공은 명시. 이미 접근 가능한 경우 필요한 회차만; 코드 제공만으로 OSI 오픈소스로 보지 않음 |
| IF05 | Inflearn | [수익형 AI Agent n8n 전문가 강의, 블로그·쇼츠 자동화](https://www.inflearn.com/course/수익형-ai-agent-n8n-전문가?cid=338159) | 수강생 자료 | 참고만 | 수강 목적 외 복제/배포 제한을 확인. 블로그·쇼츠 제작 원리만 참고하며 공개 제품 코드 반입과 분리 |
| IF06 | Inflearn | [Claude Code로 만드는 n8n 자동화 실전](https://www.inflearn.com/course/practical-n8n-automa?cid=341282) | 수강생 자료 | 조건부 검토 | 수강 자료와 실제 코드 범위를 확인한 뒤 기존 업무 하나에만 연결. 새 자동화 런타임 전체 도입은 보류 |
| IF07 | Inflearn | [노코드 자동화 입문부터 실전까지: n8n 완전정복 (한국 최초 n8n 앰버서더 직강)](https://www.inflearn.com/course/노코드-자동화입문-실전-n8n완전정복?cid=336825) | 수강생 자료 | 조건부 검토 | 학생용 workflow와 배포 조건 확인 후 내부 실습 범위에서 검토. 실제 JSON 확보·동작은 별도 |
| IF08 | Inflearn | [1시간 만에 완성하는 사내 문서 AI 챗봇 - RAG와 LangChain으로 (feat. 소스코드 제공)](https://www.inflearn.com/course/1시간-만에-rag와-langchai?cid=340332) | 수강생 자료 | 조건부 검토 | 사내 RAG 소스 제공 안내는 확인. 학생용 실제 파일·권리·기존 검색과 중복 여부를 먼저 확인 |
| YT-KIT-01 | YouTube | [CONNECT AI LAB / Jay · 월급 0원으로 24시간 일하는 AI 직원 5명, 모든 코드와 프로그램을 무료로 공유합니다](https://www.youtube.com/watch?v=jpd7gYchCbQ) | 공개 코드 | 우선 재사용 | MIT 공개 확장의 역할/승인 기록 계약만 참고. 비공개로 옮겨진 desktop 전체 소스는 재사용 대상으로 잡지 않음 |
| YT-KIT-02 | YouTube | [CONNECT AI LAB / Jay · JEV 같은 AI, 내 컴퓨터에서 0원으로 돌립니다](https://www.youtube.com/watch?v=u5EL3dNwJpw) | 공개 프롬프트 | 참고만 | 완성 앱이 아닌 프롬프트4파일. 요구사항을 독립 정리하되 앱/실행 성능을 받은 것으로 표시하지 않음 |
| YT-KIT-03 | YouTube | [Cole Medin · I FINALLY Built an AI Agent to Organize my Life - AI Agents Masterclass #4](https://www.youtube.com/watch?v=s3SY_2a3Woo) | 공개 코드 | 우선 재사용 | MIT 문서 source 메타데이터와 명시 도구 registry를 선별. 오래된 전체 환경·원격 모델 기본값은 그대로 가져오지 않음 |
| YT-KIT-04 | YouTube | [Cole Medin / oTTomator contributors · Build an ARMY of AI Agents on Autopilot with Archon, Here's How](https://www.youtube.com/watch?v=-Fpp4CBo14g) | 공개 코드 | 우선 재사용 | 확보한 MIT 연구·콘텐츠 JSON의 입력/출력 경계를 재사용. active·자격·Supabase 저장은 기존 승인/SQLite로 재설계 |
| YT-KIT-05 | YouTube | [Dave Ebbelaar / Datalumina · 5 Levels of AI Agents - From Simple LLM Calls to Multi-Agent Systems](https://www.youtube.com/watch?v=BaXTos7B1vY) | 공개 코드 | 우선 재사용 | MIT의 Pydantic 계획·검토 데이터 계약을 참고. 프롬프트 입력 누락이 있는 예제를 통째 실행하지 않음 |
| YT-KIT-06 | YouTube | [Brandon Hancock / aiwithbrandon · Fullstack NextJS & CrewAI Crash Course For Beginners [Source Code Included]](https://www.youtube.com/watch?v=d8juNbo3onk) | 공개 코드 | 보류 | LICENSE 미확인과 오류를 COMPLETE로 덮는 경로가 있어 코드 반입 제외. UI 모양만으로 완성도를 판단하지 않음 |
| YT-KIT-07 | YouTube | [Sam Witteveen · How to make Muilt-Agent Apps with smolagents](https://www.youtube.com/watch?v=XHijkFRd2TU) | 공개 코드 | 보류 | 공개 예제지만 LICENSE 미확인. 새로운 총괄로 도입하지 않고 역할 구조만 학습 |
| YT-KIT-08 | YouTube | [Alejandro AO on Hugging Face channel · Build Your Own Open-Source Dots with Pi and Telegram](https://www.youtube.com/watch?v=HU03WDFB_tQ) | 공개 코드 | 보류 | 공개 Telegram 비서 코드의 일반 허가 미확인. Hermes를 교체하지 않고 세션 운영 원리만 참고 |
| YT-KIT-09 | YouTube | [노코드캣 (introducer); n8n GmbH (upstream author) · AI로 YouTube 요약하는게 이렇게 쉽습니다](https://www.youtube.com/watch?v=ZUwWpNEu8-k) | 공개 코드 | 조건부 검토 | Apache starter pack과 n8n 런타임 조건은 별도. 서버가 아직 없고 실제 필요할 때만 PoC 환경 후보 |
| YT-NOTION-10 | YouTube | [후츠릿 · 삽질 풀패스 비밀 아카이브](https://charmed-summer-94a.notion.site/32cbc95bcb9481e1a963c092e969c780?p=382bc95bcb9481cda9fddebc9d904be6&pm=s) | 회원·초대 자료 | 조건부 검토 | 회원이면 정식 초대 경로로 실제 소스와 조건 확인. 비공개 코드 취득·초대를 토요일 납품의 필수 조건으로 두지 않음 |

## 14. 구축 로드맵·측정·위험

**단계는 일정 약속이 아니라 통과 조건으로 넘어간다.** 앞 단계가 실제 사용으로 통과해야 다음 단계의 새 도구를 들인다.

| 단계 | 범위 | 통과 조건 |
| --- | --- | --- |
| 0. 토요일 마감 (10/27~31) | FLOW3 콘텐츠 제작 + FLOW2 선택 자료 학습, 18부서 등록·상태 표시 | 블로그 열람 · 영상 재생 · 학습→Wiki · 원고 변경·중복·응답 유실 검사 |
| 1. 첫 기반 (통과 후) | NX01 인계 계약 · NX09 기억·Wiki 근거 · NX10 모델 교체 실험실 · NX12 런타임 지원표 | 잘못 보낸 업무 1건 반환 · 사용 기억 출처 표시 · 평가 세트로 모델 비교 |
| 2. 콘텐츠·영상 품질 (통과 후) | NX03 · NX07 · NX04 · NX06 · NX15 · NX05 | 말/화면 대응표 · 컷 단위 수정 · 검산 차트를 글·영상에 재사용 |
| 3. 운영 연결 (통과 후) | NX13 중단·재개 · NX19 발행실 · NX08 성과 환류 · NX14 스킬 개선 | 재시작·인증 만료 후 이어짐 · 중복 재게시 0건 · 나쁜 스킬 변경 복구 |
| 4. 전체 부서·매출 (수요 확인 후) | NX02 · NX11 · NX16 · NX17 · NX18 · NX20 · NX21 | 실제 문의·주문·결함이 있는 업무만 연결 · 원가·수용률 기록 |

### 사람의 일이 실제로 줄었는가

**순절감 시간 = 같은 품질의 수동 시간 − (준비 + 검토 + 수정 + 복구 + 추가 운영)**. 같은 입력·허용 행동·한도에서 수용된 결과 수, 중요한 오류 수, 실패·재시도를 포함한 총비용을 비교한다. 무료 주문은 매출 0원이며 투자 수익은 보장하지 않는다.

### 반드시 통과할 실패 시나리오

- [ ] 원고 v2에 v1의 승인·파생물이 쓰이지 않는다
- [ ] 게시 응답이 유실되면 재전송 전에 외부 상태부터 조회한다
- [ ] 같은 요청 2회가 하나의 업무로 합쳐진다
- [ ] 블로그 게시가 뉴스레터를 자동 발송하지 않는다
- [ ] 합성이 실패해도 성공한 음성·이미지 자산은 보존된다
- [ ] 자료 사용 권한을 철회하면 관련 노트가 검색에서 빠진다
- [ ] 학습 모음 A의 질문에 모음 B의 답이 섞이지 않는다
- [ ] 미실행 검사가 통과로 표시되지 않는다

### 위험과 대응

| 위험 | 예 | 대응 |
| --- | --- | --- |
| 라이선스 | AGPL(Postiz·listmonk·Claude Squad), 비상업(Agents Office·Star Office 아트), 학생자료 | 코드 복사 대신 계약만 독립 구현, 공개 제품과 내부 실습 분리 |
| 비용 | 모델·검색·TTS·영상 API, 상시 실행 | 업무별 예산 예약·원가 기록, 무료/로컬 우선 |
| 보안 | 서드파티 스킬, Origin 검사를 인증으로 오인, 비밀키 노출 | 스킬은 읽고 나서 사용, 최소 권한, 자료 속 지시를 실행하지 않음 |
| 과대 주장 | ‘100명 조직’, ‘24시간’, 별 수 순위 | 홍보 수치를 성능 증거로 쓰지 않고 우리 원가·수용률로 판단 |
| 범위 팽창 | 새 총괄·메모리·화면 동시 도입 | 한 단계에 새 도구 하나, 통과 후 다음 단계 |

## 15. 출처와 확인 범위

원본 세 사이트의 데이터 파일, database 마크다운 33개, 외부 공식 저장소·문서를 대조했다. 큰 문서(최대 588KB)는 구조·결론 절·표를 중심으로 읽었다. 개인 학습용 PDF·강의 원본·개인 폴더 링크·계정 정보는 넣지 않았다.

- [전체 설계 · 지정 9소스 학습 확장](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/complete/#learning-expansion)
- [소스 키트 · 토요일 TOP3](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/source-kits/#top3)
- [AI 오피스 벤치마크 1,921선](https://heobrain-ai-office-benchmarks-20261020.ihtwandy0528.chatgpt.site/)

### 읽은 database 문서

- 2026-10-10_글로벌_투자_AI_agent_앱_아이디어_및_외부리서치
- 2026-10-12-heobrain-content-studio-plan-v4
- 2026-10-12-heobrain-content-studio-plan-v5
- 2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서
- 2026-10-18-작업기록
- 2026-10-20_AI_Office_12시간추적_진행기록
- 2026-10-20_AI_Office_고도화_딥리서치_벤치마킹_및_구축기획
- 2026-10-20_AI_Office_딥리서치_벤치마킹
- 2026-10-20_AI_Office_벤치마킹_전체목록
- 2026-10-20_AI_Office_완성형_파이프라인_벤치마킹_및_구축안
- 2026-10-20_AI_Office_전수조사_가치창출_TOP10
- 2026-10-21_AI_Office_29분야_최종벤치마킹_TOP3
- 2026-10-21_AI_Office_분야별10개이상_TOP3_6시간추적
- 2026-10-21_AI_Office_전분야_28업무_파이프라인_벤치마킹
- 2026-10-21_올인원_AI비서팀_TOP5_상세파이프라인
- 2026-10-26_AI뉴스3선_블로그_숏폼_제작결과
- 2026-10-26_AI뉴스3선_원고승인대기
- 2026-10-26_ComfyUI_영상품질_개선_도입검토
- 2026-10-26_HeoBrain_AI콘텐츠오피스_구현및검증
- 2026-10-26_Runway_첫실사컷_제작메모
- 2026-10-26_실사_AI영상_무료서비스_추천
- 2026-10-26_콘텐츠품질_및_블로그노출_수정결과
- 2026-10-27_AI오피스_18부서_콘텐츠v5_통합재설계
- 2026-10-27_AI오피스_외부소스_채택결정_및_완성안
- 2026-10-27_AI오피스_지정9소스_기능확장_벤치마킹
- 2026-10-27_AI오피스_학습_업무연결_보강_구현계획
- 2026-10-27_AI오피스_학습자료_통합_최종파이프라인
- 2026-10-27_Flow_실사영상_샘플_제작결과
- 2026-10-27_Obsidian_LLM_Wiki_자동화_최종구축계획
- 2026-10-27_YouTube_선택채널_학습비서_설계
- 2026-10-27_토요일마감_AI오피스_구현계획
- 2026-10-27_토요일마감_코드제공강의_소스확보_추천
- AI 오피스 자동화 및 3D 제작

### 이번에 연 외부 출처

- [Paperclip 저장소](https://github.com/paperclipai/paperclip)
- [Multica 저장소](https://github.com/multica-ai/multica)
- [Hermes Agent 프로필 문서](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
- [ChatDev 2.0 논문](https://arxiv.org/pdf/2609.00714)
- [Open Source AI Agent Office Apps (2026-10, 제작사 글)](https://munderdiffl.in/blog/ai-agent-office-github/)
- [GitHub topic: agent-office](https://github.com/topics/agent-office)
- [A2A의 Agentic AI Foundation 합류 (Axios)](https://www.axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards)
- [2026 멀티에이전트 프레임워크 비교](https://futureagi.com/blog/best-multi-agent-frameworks-2026)
- [OpenClaw 소개](https://www.mindstudio.ai/blog/what-is-openclaw-ai-agent)
- [AionUi 소개](https://recca0120.github.io/en/2026/04/07/aionui-ai-cowork-app/)
- [에이전트 기억 프레임워크 비교 (제작사 글)](https://www.cognee.ai/blog/guides/open-source-memory-frameworks-llm-agents)

**확인하지 않은 것:** 외부 키트 설치·실행·성능, 유료 강의 본문, 전체 채널 시청, 실계정 연동. 라이선스는 API·README 표시 수준이며 법률 판정이 아니다.
