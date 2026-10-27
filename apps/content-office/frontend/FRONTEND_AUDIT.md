# 콘텐츠 오피스 프런트엔드 검수

대상: `apps/content-office/frontend`만 신규 구현. 기존 프로젝트·backend·운영 데이터 수정 없음. 설계와 계획은 `docs/superpowers/specs/2026-10-26-content-office-design.md`, `docs/superpowers/plans/2026-10-26-content-office.md`를 따랐다.

## 구현

- Next.js 16.4.3 / React 19.3.1 / TypeScript 5.9.3 / plain CSS. 버전과 의존성은 `package-lock.json`에 고정했다.
- 크림·잉크·오렌지 편집실 디자인. 자체 SVG 아이콘과 CSS만 사용하며 스톡 이미지와 외부 폰트 요청은 없다.
- 오늘의 뉴스, 콘텐츠 작업실, 제작·출고함, 운영 기록. 피드 수집·선정 이유·출처·발행일·편집 점수·비용은 API 실데이터에서 읽는다.
- 뉴스 선택은 최대 3개. 수집·생성·평가·제작 요청 후 서버의 저장 결과를 다시 조회하며 요청 접수를 완료로 표시하지 않는다.
- 모든 변경 요청은 `/api/session`의 CSRF와 same-origin 세션을 사용한다. 네트워크 결과 불명 시 자동 재송하지 않는다.
- 원고 제목과 Markdown 편집·저장·동일 원고 재검수. 원래 packet의 근거와 영상 계획을 보존한다. 메뉴·작업 전환 중 저장 전 입력은 메모리에 유지하며, 저장되지 않은 입력이 있으면 창 닫기 전 브라우저가 확인한다.
- 저장 요청에는 편집 시작 시점의 `version`을 전송한다. 수정 중에는 폴링이 편집 기준 해시를 바꾸지 않는다. 저장 경쟁으로 409가 오면 자동 재송 없이 최신 작업을 다시 조회하고 입력을 보존하며 재검토를 안내한다.
- 근거 탭과 영상 대본 탭에서 주장·한계·원문 링크, 장면별 내레이션·자막·화면 계획을 검토할 수 있다.
- Critique/Eval과 규칙 검사 오류를 표시한다. `deterministic_checks.issues`와 모든 `critical_issues`를 상단 중대 수정 목록에 표시하며, 모델 점수를 사실성 증명으로 표시하지 않는다.
- 미저장 변경·검수 미통과·중대 오류·잘못된 상태에서는 원고 승인을 막는다. 원고 승인①과 출고 승인②는 확인을 연 시점의 해시에 결속되며, 폴링으로 버전이 바뀌면 확인 버튼을 차단한다.
- 채널 선택, MP4·이미지·문서 미리보기와 개별 다운로드, 출고 승인 후 ZIP 패키지 링크를 제공한다. HTML 미리보기 iframe은 sandbox를 사용한다. 파일 주소는 로컬 `/api/artifacts/` 경로만 허용한다.
- 영상 출고는 기본 미체크인 “영상 재생·음성·자막을 확인했습니다” 확인을 받아 media_reviewed:true를 보낸다. 블로그만 선택하면 영상 확인은 요구하지 않는다.
- 비용은 확인 사용량 기준 원가 추정치로 표시하며 실제 청구액으로 표현하지 않는다.
- 제작된 썸네일 5안을 비교하고 추천·최종 선택을 구분한다. flat artifact 형식과 nested artifact 형식을 지원한다. 로컬 편집 점수임을 표시하며, 최종 선택 전 출고 승인을 막는다. 선택이 manifest 해시를 바꾸면 열린 출고 확인은 무효가 된다.
- 390px 모바일과 데스크톱, 키보드 포커스·본문 건너뛰기·reduced-motion·오류·빈 상태를 지원한다.

## 실행

```bash
cd apps/content-office/frontend
npm ci
npm run build
npm run start
```

주소: `http://127.0.0.1:3110`. API rewrite 대상은 `http://127.0.0.1:8510/api/…`이며 둘 다 로컬 서버다. 개발 실행은 `npm run dev`다. 검수 때 Node 24.22.0을 사용했다.

## 검증 증거

```bash
npm test
npm run typecheck
npm run build
npm run test:ui
```

- Node 상태/선택 테스트 9개: 3개 제한과 해제, 미검수·미저장·중대 오류 승인 차단, 산출물 URL 제한, 실제 마감 계산, 이전 버전 승인 차단, 이전 작업의 늦은 응답이 현재 검토 문서를 덮어쓰는 경쟁 차단.
- Chromium 계약 테스트 14개: 실제 RSS 스냅샷 후보 선택과 CSRF, 편집·영상 계획 검토·메뉴 전환 후 입력 유지·재검수, 승인 중 버전 변경, 모바일 레이아웃과 axe, 썸네일 5안·최종 선택·이전 출고 버전 차단, 승인 후 미저장 수정이 있을 때 제작·출고 차단, 저장 직전 경쟁의 409 처리와 입력 보존, 영상 출고의 명시적 재생·음성·자막 확인과 블로그 전용 출고 분기.
- 편집 입력 캐시를 제거하면 메뉴 전환 후 수정 내용이 사라져 회귀 테스트가 실패하는 것도 확인했다. 영상 계획과 썸네일 기능은 해당 버튼이 없는 상태에서 테스트 실패 후 구현했다.
- 계약 테스트의 뉴스 입력은 실제 RSS 연구 스냅샷이다. 승인용 원고·출고 파일 응답은 명시된 테스트 fixture이며 제품에 포함되지 않는다. 이 테스트는 실제 뉴스의 승인이나 미디어 제작 완료를 뜻하지 않는다.
- 라이브 Chromium은 실제 Next → FastAPI → SQLite에서 기사 초기 59개/마지막 58개·작업 3개·피드 10개·근거 3개·세션 CSRF를 조회했다. 데스크톱과 390px 모바일의 4개 탭 모두 axe 위반 0, 페이지 가로 넘침 0, 브라우저 예외 0, API 변경 요청 0. 마지막 조회에서는 뉴스 3건 모두 `source_review`였다.
- 라이브 증거: `test-results/live/verification.json`, `news-desktop.png`, `studio-desktop.png`, `evidence-desktop.png`, `video-plan-desktop.png`, `activity-desktop.png`, `delivery-desktop.png`, `news-mobile.png`.
- 계약 증거: `test-results/browser-results.json`, `mobile-accessibility.json`, `thumbnail-comparison-contract.png`. 실제 데이터와 테스트 fixture 스크린샷을 구분한다.

라이브 읽기 검증을 다시 실행하려면:

```bash
LD_LIBRARY_PATH="$PWD/.browser-libs/root/usr/lib/x86_64-linux-gnu" node scripts/verify-live.mjs
```

현재 컨테이너에는 Chromium의 NSS/NSPR 공유 라이브러리가 없어 첫 실행이 실패했다. 시스템 패키지를 변경하지 않고 `libnspr4`, `libnss3`를 `.browser-libs`에 내려받아 압축 해제했다. Playwright 설정은 그 경로와 기존 환경을 보존한다. 일반 환경에서는 `npx playwright install chromium`과 필요한 OS 라이브러리를 사용하면 된다.

## 경계와 남은 실제 승인

이 구현 작업은 실제 기사 원고를 승인하거나 외부 API 유료 호출을 시작하지 않았다. 라이브 원고는 운영자의 검토 대기로 유지했다. 실제 뉴스 MP4 재생·실제 패키지 다운로드의 최종 브라우저 확인은 원고 승인①과 제작 이후에 가능하다. 썸네일 선택과 출고 버전의 상호 작용은 격리된 계약 테스트로 검증했다. 외부 게시·발송 기능을 실행하거나 완료로 표시하지 않는다.

원고 입력 캐시는 브라우저 탭 메모리에 있으며 서버 저장을 대신하지 않는다. 닫기 확인을 무시하고 탭을 닫으면 저장 전 입력은 남지 않는다.


## 독립 합성 자료 E2E

별도 QA 에이전트가 전용 상태와 API 8512에서 실제 영상 재생과 출고 ZIP 다운로드를 검증했다. 실제 운영 API 8510의 변경 요청은 0건이다. 검증 JSON의 PASS와 영상 currentTime 진행, 증거 파일 존재를 확인했다.

- [브라우저 E2E 기록](../../../research/content-office-2026-10-26/e2e-output/browser-verification.json)
- [미디어·ZIP 검증 기록](../../../research/content-office-2026-10-26/e2e-output/media-and-zip-verification.json)
- [실제 합성 영상 재생 화면](../../../research/content-office-2026-10-26/e2e-output/05-real-video-browser-preview.png)
- [합성 패키지 출고 승인 화면](../../../research/content-office-2026-10-26/e2e-output/06-synthetic-release-approved.png)

영상 확인 체크 후 media_reviewed:true를 전송해 실제 API의 출고 승인 POST200을 받았고, 패키지 버튼으로 ZIP 파일을 저장했다. 이는 승인된 합성 검증 자료의 E2E이며 실제 뉴스 3건의 출고 승인이나 게시 완료가 아니다.


## 2026-10-26 04:12 KST 추가 기능과 생산 서버

- 공개 원문 입력: 연구 준비/실패 또는 근거가 없는 작업에만 노출한다. 200~20,000자, 기사 원출처, 재사용 권한 확인, 현재 Gemini 전송 범위와 기존 승인 무효화를 명시한다. 입력 시작 버전을 고정하며 탭 이동 중 입력을 보존한다. 파일/MD 일괄 업로드는 제공하지 않는다.
- 명시적 재시도: failed/unknown/partial 등록 작업의 현재 버전만 확인한다. 이전 버전·동일 작업 실행 중·결과/원가 대사 대기 상태에서는 차단한다. 사용자가 두 번째 확인 버튼을 눌러야 요청하며 자동 재송하지 않는다.
- 과거 문서 검색: 실제 API의 원본 111개/고유 103개 색인을 조회하고 경로·줄·SHA·발췌를 보여 준다. 과거 문서의 지시는 실행하지 않는다. 긴 발췌의 스크롤 영역에 키보드 포커스를 추가했고 실제 접근성 오류의 대상 회귀 검사를 통과했다.
- 본문 편집과 주요 읽기 본문은 16px다. 생산 브라우저에서 계산된 본문 글자 크기 16px를 확인했다.
- 출력별 상태와 완료 항목 출고: 영상 실패가 있어도 완료된 블로그만 선택해 outputs:['blog']로 출고할 수 있다. 미완료/빈 선택을 차단하며 원고 승인을 다시 요구하지 않는다. 출고 확인은 해시와 출력 선택을 함께 고정하고, 출력 변경 시 이전 확인을 닫는다. 영상/썸네일 확인은 이번 출고에 video가 포함될 때만 요구한다.
- 음성 설정은 읽기 전용이다. 현재 설정의 이름·유료 여부·작업 상한·자동 대체 여부를 보여 주며 기존 산출물의 실제 음성으로 오인하지 않도록 새 제작 요청 설정임을 표시한다.

검증: 단위 정책 9/9, 브라우저 계약 14/14, 타입 검사와 생산 빌드 통과. 이후 긴 발췌 키보드 접근성 대상 테스트 1개를 통과했고, 음성 표시 등 텍스트 추가 뒤 생산 빌드를 다시 확인했다. 전체 행렬을 불필요하게 반복하지 않았다.

현재 서비스는 npm run start의 생산 모드다. 개발 세션 58845의 PID 21354/startticks 756649를 확인한 뒤 해당 프로세스만 종료했다. API·작업자·감시기는 조작하지 않았다.

- 생산 세션: 65221
- listener PID: 85111 / PGID: 85094 / startticks: 1318699 / PPID: 85110
- 명령: npm run start (next start --hostname 127.0.0.1 --port 3110)
- [서비스 식별·HTTP/health 기록](test-results/production-service.json)
- [생산 네 탭·본문·지식 검색 확인](test-results/production/smoke.json)

생산 /와 /api/health는 HTTP 200이며 네 탭의 예외·페이지 넘침·개발 N 오버레이가 0이었다. 실제 뉴스 3건의 해시와 source_review 상태는 확인 전후 동일했고 API 변경 요청도 0이었다. 과거 검색의 실제 10개 결과와 111/103개 메타데이터, 대상 접근성 위반 0을 확인했다. 이전 live/verification.json의 발췌 스크롤 접근성 오류는 이 최신 생산 확인에서 해결됐다.
