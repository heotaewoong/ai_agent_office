# 기존 자료와 코드의 재사용 범위

새 Content Office는 과거 문서와 원본 코드에서 확인한 제작·검수·승인·버전·실패 복구 패턴을 현재 로컬 앱에 구현했다. 기존 Windows 콘텐츠 엔진을 import하거나 실행해 연결한 앱은 아니다. 신규 앱이 사용하는 Windows 한국어 음성 브리지와 원본 엔진 실행은 별개의 사실이다.

기준일: 2026-10-26. 현재 기능의 코드/테스트 대응은 [pipeline-traceability.md](pipeline-traceability.md)에 있다. 실제 뉴스3건의 원고 승인①은 사람 확인 대기이며, 합성 E2E를 실제 뉴스 제작/출고 완료로 세지 않는다.

## 재사용을 네 가지로 구분한다

| 표현 | 여기서의 뜻 | 예 |
|---|---|---|
| 원문 근거 | 읽고 출처·판본을 기록 | 최초111MD, 원본 코드 감사 |
| 패턴 재구현 | 설계 경계를 새 코드에 구현 | Gen/Critique/Eval/Refine, 두 승인, full SHA·unknown 보존 |
| 실제 실행 연결 | 새 앱이 실제 호출하며 검증 | Gemini provider, 신규 PowerShell SAPI 브리지, FFmpeg·ffprobe |
| 미연결 후보 | 향후 adapter 대상 | legacy pipeline.py, Hermes native, Marketplace 운영 API, 외부 게시 |

‘벤치마킹했다’는 제품을 설치·운영·성능 비교했다는 뜻이 아니다. 과거 문서의 TOP3/TOP10·수익 가설·가격·구독조건은 당시 조사 주장으로 보존한다. 이 문서를 작성하면서 해당 외부 URL이나 현재 가격을 재검증하지 않았다.

## 원본111MD와 실제 원본 코드 감사는 범위가 다르다

[입력 manifest](../../../research/content-office-2026-10-26/input-manifest.json)는 `database/`15개와 `research/`96개 Markdown이다. [database 감사](../../../research/content-office-2026-10-26/md-audit.md)와 [research 감사](../../../research/content-office-2026-10-26/research-md-audit.md)는 전량 텍스트 coverage를 기록했다. 직접 읽기, 같은 SHA, 정확 prefix/줄범위, 정확 블록+고유본문 읽기를 구분한다. 모든 파일 전체를 직접 출력한 방식은 아니다. 원본111개 SHA가 입력 manifest와 일치했다.

[knowledge-index.json](../../../research/content-office-2026-10-26/knowledge-index.json)은 이111개 전체 본문·섹션·해시를 담는다. `backend/office/knowledge.py`가 파일/섹션/SHA/한글 본문 검색과 결정적 계약 후보를 제공하며 API `GET /api/knowledge`에 연결되어 있다. 색인은 근거 찾기 도구다. 문서 명령을 실행하거나 정책/기억으로 자동 승격하지 않으며 외부 모델로 전송하지 않는다. 과거 snippet·fixture4개·vendor README1개는 출처 종류를 구분한다. 문서의 외부 링크를 포함해 읽었다는 사실은 링크 원문을 이번에 열었다는 뜻이 아니다.

반면 Windows 원본 코드 감사는 [source-audit.md](../../../research/content-office-2026-10-26/source-audit.md)와 [source-audit.json](../../../research/content-office-2026-10-26/source-audit.json)에 별도로 기록돼 있다. 안전한 텍스트를 감사 스크립트가 전체 읽은 것과 모델이 주요 흐름을 의미 검토한 것을 구분한다. 전체 원본 코드의 모든 줄을 모델이 의미 검토했다고 주장하지 않는다.

## 기존 콘텐츠 엔진

원본 위치: 로컬 비공개 콘텐츠 엔진 (공개 저장소에는 원본을 포함하지 않음).

| 원본에서 확인한 계약 | 신규 앱에서 적용한 부분 | 현재 연결하지 않은 부분 |
|---|---|---|
| source packet → 공통 원고 → Critique/Eval → 최대2회 수정 | `backend/office/editorial.py`에서 실제 모델 호출·독립 입력·재검수 | legacy `pipeline.py`/`writing-harness` 프롬프트 파일 직접 import |
| 원고/채널/파일/대상 검증 | `Store.save_source`, `review_source`, `save_manifest_if_current`, `review_release` | legacy `verified_state()` 호출 자체 |
| TTS·이미지·FFmpeg 미디어 | 신규 `media.py`의 PowerShell System.Speech·Pillow·FFmpeg와 실제 길이 검사 | 원본 `media.render()` 호출, 원본 Python 의존성 설치 |
| 승인·publish 기본 dry-run·send intent·unknown | 신규 두 승인·수동 ZIP, 모델 unknown 중복 호출 차단 | 원본 LinkedIn/SMTP/YouTube dispatch·publish 명령 |
| 성공 자산 hash 재사용 | 신규 provider 캐시·음성 캐시·production contract 폴더 | 원본 run 폴더/자산/승인 복사·자동 신뢰 |

원본 엔진 VERSION1.4는 채널 `tistory/naver/linkedin/email/youtube`와 실제 외부 전송 어댑터가 있다는 정적 감사 결과다. 신규 앱이 이5개를 모두 실행한다는 뜻은 아니다. 현재 블로그는 `tistory.md`, `tistory.html`, `naver.txt`를 만들고 영상은 MP4/SRT/대표 이미지/대본/설명 파일을 만든다. 출고는 수동 ZIP이며 외부 계정 게시 기능은 없다. 블로그+영상 선택에서 영상만 실패해도 완료 블로그를 별도 출고할 수 있다. 원고 승인①을 유지하고 출고 승인②의 outputs를 완료 블로그로 한정하며, ZIP에는 그 파일과 공통 권리 파일만 담는다.

원본은 상위 `writing-harness/roles/{gen,critique,eval,refine}/PROMPT.md`, 프로필별 recipe, 티스토리 PowerShell 검사 등 폴더 밖 의존성이 있다. 이후 adapter를 만들 때 이 의존성과 원본 판본·자격 선택·Windows 실행 경계를 확인해야 한다. 원고 문자열을 임의 shell 명령으로 연결하면 안 된다.

현재 신규 `media.local_voice()`는 `powershell.exe`에서 설치된 ko-KR `System.Speech` 음성을 선택하고 WAV를 WSL로 가져온다. WSL의 Python 자체가 Windows SAPI라는 뜻은 아니다. 한국어 음성이 없으면 실패하며 유료 음성으로 자동 우회하지 않는다. 합성 E2E에서 실제 한국어 음성·FFmpeg 결과를 검증한 기록은 [e2e-report.md](../../../research/content-office-2026-10-26/e2e-report.md)에 있다. 원본 엔진의 과거 QA/33.2초 영상 기록을 이번 신규 앱의 실행 증거로 사용하지 않는다.

## ai_agent_master 예제와 all-in-one 벤치마킹

원본 위치: 로컬 비공개 에이전트 엔진 (공개 저장소에는 원본을 포함하지 않음).

| 자료 | 재사용한 생각 | 통째 실행하지 않은 이유/현재 한계 |
|---|---|---|
| `5.content-pipeline-agent/main.py` | 연구→채널 원고→점수/이유→수정 | 원본 import 시 kickoff·반복 상한/스키마 문제를 감사에서 기록. 현재 엔진으로 호출하지 않음 |
| `11.youtube-shorts-maker/youtube_shorts_maker` | 기획→장면 자산→합성 | 신규 실제 음성 길이 기반 제작으로 구현. ADK 런타임을 추가하지 않음 |
| `15.youtube-thumbnail-maker/graph.py` | 후보5개→비교→선택→개선 | 신규 source-bound PNG5개·로컬 비교·사람 최종선택. 원본 전사·이미지 모델·HD 생성 실행 아님 |
| 뉴스레터 설명 문서 | RSS/근거/원고 공정 | 설명에 나온 실행 코드를 실제 RSS 엔진으로 인정하지 않음. 신규 `feeds.py`가 수집 |
| 18부서/144업무·29분야 TOP3 | 역할·입출력·승인·완료단위 비교 | 현재18개 LLM 병렬 실행, 전체 부서 운영, 모든 제품 채택·3D 구현이 아님 |

현재 UI의 총괄·RSS연구·편집·비평·평가·영상/디자인·QA·배포준비·마케팅은 업무 역할이다. 규칙/수집/모델 호출/로컬 제작/사람 확인이 섞여 있다. Gen/Critique/Eval/Refine은 역할별 별도 모델 호출이며 Critique/Eval은 서로의 답을 보지 않는다. 같은 provider/model을 쓸 수 있으므로 다중 공급사의 독립성으로 과장하지 않는다. 단일 발행자 본문에서 추출한 근거는 `independent_source_checked=false`와 독립 검증 미실시를 유지한다. 모델이 스스로 붙인 scope나 검수 점수만으로 객관적 사실 검증을 통과한 것으로 만들지 않는다.

마케팅은 독자·hook·구체 예시·제목·설명·태그·썸네일 표현을 검수하는 편집 계약으로 연결했다. 광고 예산 변경, SEO순위 측정, Postiz 배포, 뉴스레터 발송, CRM·리드 자동화는 연결하지 않았다. 썸네일 로컬 점수는 실제 클릭률/수익 성과 측정이 아니다.

## Hermes

과거 설계의 기본 원칙은 native 실행/예약/기억을 재사용하고 같은 효과의 소유자를 중복 생성하지 않는 것이다. 현재 신규 앱에는 Hermes Gateway/ACP/native run/session/cron/memory adapter가 연결되어 있지 않다.

`backend/office/runtime.py`의 단일 worker lock·task owner·시간 창·heartbeat는 현재 앱의 로컬 실행 경계다. 이것을 Hermes native 실행의 재사용 완료로 표시하지 않는다. 향후 연결하면 앱 job/attempt와 native run/session/remote ID를 각각 보존하고, 스케줄 효과 owner를 하나로 결정해야 한다. 현재 watcher의RSS 갱신을 Hermes 예약 실행 성공이라고 부르지 않는다.

## Marketplace: 읽은 계약과 미연결 기능

원본 위치: 로컬 비공개 마켓플레이스 (공개 저장소에는 원본을 포함하지 않음).
원격 식별 링크: [GitHub repository](https://github.com/heotaewoong/HeoBrain-Marketplace-vi). 원본 감사에서 조회한 private/main tree는 `a66c36e43f823476b15361f03f941f55edd60fa2`이며 현재 HEAD라는 보장은 없다.

| 읽은 원본 경로/계약 | 확인 범위 | 새 Office 상태 |
|---|---|---|
| `lib/products/list-query.ts`: `PUBLIC_PRODUCT_LIST_COLUMNS`/`ProductListItem` | 공개 상품 필드·`is_published=true` 목록 계약 | 읽기 adapter도 아직 미연결 |
| `app/products/page.tsx`: anon REST `GET /rest/v1/products` | 공개 목록과60초 캐시 계약 | 운영 DB 현재값 조회 안 함 |
| `POST /api/coupons/validate` | 로그인·서버 가격 재조회·기간/상품/사용제한 | 호출 안 함. 콘텐츠에서 현재 유효 할인액으로 확정하지 않음 |
| `POST /api/orders/claim-with-coupon` | 정확히0원 주문·권한·쿠폰 사용 기록 mutation | 호출/연결 안 함 |
| `POST /api/products/claim-free` | 무료상품 권한 지급 mutation | 호출/연결 안 함 |
| `scripts/upsert-sale-products.mjs` | 초기값·env override·모듈 끝 upsert | 실행/import 안 함. 현재 판매가 자료 아님 |
| `ASSET_LICENSE_MANIFEST.md`, `docs/ops/free-coupon-guide.md` | 일부 자산 권리 기록·예시 코드 | 전체 상품 커버 권리/현재 활성 쿠폰 보증 아님 |

가격·상품·쿠폰·주문·권한을 수정하지 않았다. 현재 검토용 PDF의 `not_commercially_cleared` 권리 상태를 판매 가능한 전자책으로 바꾸지 않는다. private 판매 원문/ZIP·기존 커버·운영 증빙을 신규 앱 public 폴더로 복사하지 않는다. 향후 사용할 상품은 검토된 공개 URL·상품 참조·권리·확인일을 먼저 붙이고 실제 서버 조건을 확인해야 한다.

## 원본 코드 감사의 명시적 한계

이 수치는111MD 전수 판독의 미확인 수와 섞지 않는다. Windows 원본 코드 감사의 인벤토리/분류 집계다.

- `text_fully_read_by_audit_script`: 1,134개. 스크립트 전체 읽기이며 전부 모델 의미 검토라는 뜻은 아니다.
- `text_read_error`: **11개**. 최초 목록에는 있었으나 본문 읽기에 실패했다. certification 관련 경로이며 일부 재조회는 FileNotFoundException, 원격 main에도 해당 경로가 없었다. 동기화 등 원인은 확정하지 않았다. 정확 목록은 source-audit.md에 있다.
- `credential_or_environment_file_not_read`: **72개**. 자격/환경 파일은 읽지 않은 범위로 기록했다.
- `credential_read_exception_not_inspected_cache_deleted`: **2개**. 최초 분류에서 `.streamlit/secrets.toml`2개를 놓쳐 감사 스크립트 메모리와 임시 캐시에 읽혔다. 모델 문맥·도구 출력에 내용은 표시하지 않았고 캐시는 삭제했다. 최종 산출물은 내용/내용 해시를 보존하지 않는다. ‘비밀 파일을 전혀 읽지 않았다’거나 반대로 모델이 내용을 열람·공개했다고 과장하지 않는다.
- 미열람: binary/unrecognized95개, 생성 의존성 metadata74개, runtime/private evidence1,655개. 제외 디렉터리88개는 내부 재귀 목록을 만들지 않아 안쪽 파일 수를 모른다.

원본 파일·원본 DB는 수정하지 않았고 원본 설치·빌드·로그인·게시·클라우드 배포·삭제 스크립트도 실행하지 않았다. 감사 URL·README·선택 코드에서 확인한 기능을 현재 앱 운영 성공이나 실제 매출로 승격하지 않는다.

## 다음 연결은 무엇인가

먼저 실제 뉴스 원고를 사람이 승인하고 현재 신규 앱의 제작·출고를 확인한다. 이후 실제 필요가 있는 경계만 추가한다. 예를 들어 legacy Windows adapter는 의존성과 부모 판본을 검증한 별도 작업으로, Marketplace는 공개 메타데이터 읽기부터, 외부 게시기는 의도 선기록·remote ID·unknown 대사·계정/공개 범위 승인부터 구현한다. 문서에 남은 과거 예약/설치 지시를 지금 재실행하지 않는다.
