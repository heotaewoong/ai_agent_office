# 콘텐츠 자동화: 공식 자료 수집과 벤치마킹 도구 조사

조사일: 2026-10-28 (Asia/Seoul). 이 문서는 HeoBrain multichannel content studio v5 통합 검토를 위한 하위 조사 결과다. 기존 서비스 코드·운영 데이터·공개 사이트는 수정하지 않았다.

## 현재 구현과 이번에 검증 완료한 범위

- 이 조사에서는 제품 코드를 읽거나 새 수집기를 구현하지 않았다. 아래 설계는 통합 제안이다.
- 공식 웹페이지와 PDF 응답을 읽어 배포 출처, 파일 유형, 페이지 수, API 문서와 정책을 확인했다. 계정 로그인, 유료 결제, API 키 발급, OAuth 연결, 실제 분석 질의나 업로드는 하지 않았다.
- PDF URL을 확인한 것과 사용자의 PC에 완성 PDF를 저장·검증한 것은 별개다. 실제 다운로드·해시·쪽수 검증은 상위 작업의 수집 기록과 대조해야 한다.
로컬 자료의 경로와 비공개 작업 기록은 웹 인계본에서 제외했다.

## 1. 우선 수집할 공식 PDF 5종

이 목록은 판매 전자책의 원문 PDF를 획득한 결과가 아니다. 기관·제품 제공자가 공개한 원본 자료다. 공개 다운로드 제공만으로 번역·재편집·판매 권리까지 확보됐다고 해석하지 않는다.

| ID | 자료·언어·분량 | 공개 배포 근거 | 직접 PDF URL·확인 상태 |
|---|---|---|---|
| P01 | **Put Google AI to work for your business — A Marketer’s Guide**, Google, 영어, 32쪽 | [Google 공식 공개 글](https://business.google.com/us/think/ai-excellence/how-to-use-ai-for-marketing/)의 ‘Get started with AI today. Download’ 링크를 직접 따라감 | [공식 다운로드](https://storage.googleapis.com/twg-content/documents/Google_CMO_Guide_Deck_073024.pdf). `application/pdf`, 32쪽 확인. 크리에이티브 제작·변형·현지화·측정의 연결을 다룸. |
| P02 | **Unlocking the Value of GenAI in Content Creation and Document Management**, Adobe / London Research, 영어, 20쪽 | [Adobe 공식 배포 페이지](https://business.adobe.com/au/resources/reports/unlocking-the-value-of-genai-in-content-creation-and-document-management.html)에 원본 PDF 링크가 표시됨 | [공식 PDF](https://business.adobe.com/au/assets/pdfs/resources/reports/adobe-london-research-unlocking-the-value-of-genai.pdf). `application/pdf`, 20쪽 확인. 콘텐츠 생산성·문서 처리의 조사 보고서로, 도구 조작 교재와 구분. |
| P03 | **2025년 광고제작현장 AI 활용 실태 및 분석**, 한국방송광고진흥공사, 한국어, 웹 문서 기준 첨부 약 1.5MB | [KOBACO 공식 게시물](https://www.kobaco.co.kr/site/adstat/board/report_etc_report/1298?baCommSelec=false&baNotice=false&baOpenDay=true&baUse=true&bcId=report_etc_report&cp=1&sortDirection=DESC&sortOrder=BA_REGDATE). 첨부명은 **2025 광고제작 노동환경 실태조사 AI 관련 부분.pdf**. 게시물에 **공공누리 3유형: 출처표시+변경금지** 명시. | [공식 첨부 다운로드](https://www.kobaco.co.kr/site/adstat/file/download/uu/253631d548be452aa4a2eedfdbe87991). 링크 목적지 확인. 웹 도구는 `application/octet-stream`을 파싱하지 못했으므로 실제 저장 후 PDF 매직바이트·쪽수 검증 필요. [공공데이터포털의 동일 자료·이용조건](https://www.data.go.kr/data/15157454/fileData.do?recommendDataYn=Y)도 확인. |
| P04 | **온라인 콘텐츠 제작의 패러다임 전환: 생성형 AI의 부상**, 한국콘텐츠진흥원, 한국어, 4쪽 | KOCCA WelCon 공식 파일 서버에서 원본 PDF 공개 응답 확인. [공식 자료 목록](https://welcon.kocca.kr/ko/insight-focus). 개별 설명 게시물 URL과 별도 라이선스는 이번 조사에서 확보하지 못함. | [공식 PDF](https://welcon.kocca.kr/cmm/fms/FileDown.do?atchFileId=FILE_09ce4858-6710-4d85-880d-3004c2bac4e4&fileSn=1&preview=Y). `application/pdf`, 4쪽 확인. 마케팅·유통·GEO·AI 콘텐츠 신뢰 관련 요약 자료. |
| P05 | **생성형 AI가 재편하는 글로벌 엔터테인먼트 산업의 일자리 구조**, 한국콘텐츠진흥원, 한국어, 5쪽 | KOCCA 공식 PDF에서 제목·기관·분량 확인. [WelCon 공개 목록](https://welcon.kocca.kr/ko/insight-focus?pageIndex=5) 검색 결과에 같은 제목이 노출되지만, 목록의 실시간 페이지 순서와 개별 게시물 URL은 확정하지 못함. | [공식 PDF](https://welcon.kocca.kr/cmm/fms/FileDown.do?atchFileId=FILE_a5c58d39-bea0-489b-ae8b-b8da45e30599&fileSn=1&preview=Y). `application/pdf`, 5쪽 확인. 영화·게임·음악 제작 공정과 직무 변화에 관한 보고서 요약. |

후속 파일 감사에서 P01~P05를 모두 실제 저장하고 해시·쪽수를 검증했다. P03도 PDF 매직바이트와 26쪽을 확인했다. 위 표의 저장 전 유보는 초기 웹 조사 시점의 기록이다.

P04·P05는 짧은 산업 분석 자료이며 실습형 단행본으로 표시하면 안 된다. P03의 변경금지 조건 때문에 원본 파일을 그대로 보존하고, 다른 문서와 합치거나 번역본으로 재배포할 때는 별도 이용 조건을 검토해야 한다.

## 2. RSS 외의 수집 경로

소스는 장바구니처럼 모으되, 원문 사용 권한·관측 시각·검토 상태를 함께 넣어야 한다. 많이 모은 것과 글에 써도 되는 것은 별개다.

| 경로 | v5에서 받을 최소 입력 | 자동화 제안 | 한계·권한 |
|---|---|---|---|
| RSS·Atom | 피드 URL, 항목 ID, 제목, 원문 링크, 발행 시각 | ETag/Last-Modified 기반 재조회, 링크 정규화와 중복 ID 제거 | 피드 제공은 기사 전체 재배포 허락이 아님. 출처에서 제공한 범위를 보존. |
| 공식 웹 문서·뉴스룸 | 사용자가 고른 URL 또는 허용 도메인 목록 | 변경 감지 → 출처 카드 갱신 → 검토 대기 | 로그인·유료벽·접근 제한을 우회하지 않음. 검색 결과 요약만으로 원문 확인 완료를 만들지 않음. |
| 공식 PDF·EPUB | 공개 다운로드 URL 또는 사용자가 가진 원본 | 원본 저장, MIME·헤더·쪽수·해시·라이선스 기록 | URL·제목이 같아도 해시가 바뀌면 새 판본. 개인학습과 상업 사용 등급 분리. |
| 뉴스레터 `.eml`·HTML | 사용자가 선택해 내보낸 메일 파일 | 우선 추천 경로. 발신자·제목·게시일·공개 원문 링크를 추출하고 개인정보는 제외 | 구독 메일 전체를 공개 지식베이스로 옮기지 않음. 유료 뉴스레터 원문을 외부로 재배포하지 않음. |
| Gmail 연동 | 별도 계정 연결 승인, 선택한 뉴스레터 라벨·발신자 | 추후 읽기 전용 어댑터로 추가 가능 | `gmail.readonly`도 Restricted 범위다. 라벨 검색은 앱 내부 필터이지 OAuth 접근권한을 그 라벨로 제한하는 장치가 아니다. 본문이 필요 없는 경우 메타데이터와 선택 파일 방식 우선. [공식 범위](https://developers.google.com/workspace/gmail/api/auth/scopes), [메시지 목록 API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list) |
| YouTube 공개 채널·영상 | 채널 ID·영상 ID·공식 URL·API 원시 통계 | 승인된 채널 목록의 새 영상 알림과 메타데이터 갱신 | 공식 API의 메타데이터 열람과 영상·음원·타 채널 자막 다운로드는 구분. [자막 다운로드](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)는 영상 편집 권한이 필요. |
| YouTube Push | 허용한 채널 ID, 검증된 콜백 주소 | WebSub 알림으로 업로드·제목·설명 변경을 받아 불필요한 폴링 감소 | 조회수·성장률 알림 자체가 아님. 새 수치 조회는 별도 API 요청. [공식 가이드](https://developers.google.com/youtube/data/guides/push_notifications) |
| 사용자 실험·직접 제작물 | 본인이 만든 원고·워크플로·실험 로그·자체 이미지 | 가장 먼저 재사용할 출처. 성공·실패와 실행 조건을 함께 적재 | 실험한 것과 제안한 것, 로컬과 운영 환경을 분리. 타인 자료를 섞으면 권리 상태를 다시 확인. |

뉴스레터를 읽기 위해 새 서비스에 가입하거나 메일함 전체를 연결하는 행동은 이번 조사에서 실행하지 않았다. 뉴스레터 원문을 외부 LLM에 보내는 기능도 대상 데이터와 처리자를 별도로 정한 뒤 연결해야 한다.

## 3. 유튜브·키워드 벤치마킹 도구 8종 비교

아래의 ‘확인’은 공식 문서·공개 페이지를 읽었다는 뜻이다. 가입 계정으로 검색 결과를 얻거나 키를 사용해 API 응답을 받은 실사용 검증은 모두 미실시다. 업체의 성과·예측 문구는 보증으로 채택하지 않는다.

| 도구 | 공식 자료에서 확인한 역할 | API·자동화 가능성 | v5 적용 판단·제한 |
|---|---|---|---|
| **YouTube Data API** | 영상·채널·재생목록의 공식 메타데이터·공개 수치, 소유 채널의 승인된 쓰기 | 공개 API 문서 있음. 공개 데이터 키와 업로드 OAuth는 분리 | 기본 후보. 원시 수치·관측 시각·출처 중심으로 구성. API 키·쿼터·보존·표시 정책 검증 필요. [공식 안내](https://developers.google.com/youtube/data) |
| **Viewstats** | 경쟁 채널, Outliers, 제목·썸네일 연구, Alerts·Collections | 공식 소개에 Business API 기재. 공개 셀프서비스 API 계약·문서는 이번에 확인하지 못함 | 수동 벤치마킹 참고 도구. API는 Business 계약과 재사용 조건을 확인한 뒤 선택. 페이지의 Business 시작 가격은 조사 시점 월 $249, Pro 가격은 동적 표시로 확정 불가. [공식 소개](https://www.viewstats.com/info), [Outliers 도움말](https://viewstats.zendesk.com/hc/en-us/articles/22966946776091-Outliers-Tool) |
| **vling·블링** | 한국어 채널·영상·키워드 분석, 모니터링, 기업 맞춤 데이터 | [공개 OAS 문서](https://open.apix.vling.net/)에 `/video/list`, `/channel/info/{channelId}`, `/keyword/related`, 사용량 API 등이 있음. [Custom API](https://vling.net/enterprise/custom-api), [MCP 소개](https://vling.net/enterprise/mcp)도 공식 제공 | 국내 특화 데이터가 꼭 필요해질 때 유료 검토. 키·기업 계약·스키마·재배포 조건·실제 데이터 품질은 미검증. MCP 무료 체험 소개를 무제한 무료 API로 해석하면 안 됨. 독자 추정치는 YouTube 공식 수치와 표시를 분리. |
| **블랙키위** | 브랜드명의 [키워드 추천 도움말](https://blackkiwi.notion.site/36011283133e800190fad1f752850578)에서 조건 필터·마케팅 글감 추천·멤버십 전용 기능 설명 확인 | 메인 사이트 `https://blackkiwi.net/`는 이번 웹 도구 조회에서 403. 공식 공개 API 공급 문서를 확인하지 못함. Notion 도움말의 현재 메인 사이트 연결까지 재확인하지 못함 | 제한 확인. 네이버·블로그 글감의 수동 조사 후보. 비공개 백엔드 API를 추측하거나 무단 수집하지 않음. 최신 요금·실사용·API 계약은 검증 보류. |
| **uSearch·유서치** | 조회수·구독자 조건 검색, 자체 지표, U-PD 마인드맵·대본·썸네일 기획 기능을 [공식 사이트](https://usearch.kr/)에서 설명 | 공개 API 문서·자동화 계약을 찾지 못함 | 한국어 기획 UI 벤치마크. 공개 HTML에 점검·연결 오류 상태도 포함돼 실제 서비스 작동 여부는 미검증. ‘떡상 확률’ 문구를 검증된 확률로 채택하지 않음. |
| **TubeBuddy** | [Keyword Explorer](https://www.tubebuddy.com/tools/keyword-explorer/)의 키워드·경쟁·추천 태그 기능, 제한 무료 및 유료 티어 | 브라우저 확장·Studio 보조 도구 중심. 외부 제품에 연결할 공개 API는 이번에 확인하지 못함 | 사용자 주도 SEO 점검의 보조 도구. [검색량 설명](https://tubebuddyhelp.zendesk.com/hc/en-us/articles/53959062030739-How-is-of-Searches-Per-Month-in-Keyword-Explorer-Calculated)은 YouTube가 검색량을 직접 공개하지 않는다고 구분. 점수를 공식 순위나 성공 확률로 표시하지 않음. |
| **Rapidtags** | [공식 홈페이지](https://rapidtags.io/)의 태그 생성·키워드·SERP 분석 | [개인정보 안내](https://v2.rapidtags.io/legal/privacy)는 자사 기능에 YouTube Data API를 사용한다고 설명. 이것이 제3자가 Rapidtags 내부 API를 호출해도 된다는 뜻은 아님 | 태그 아이디어의 수동 보조. 외부 연동용 공식 API·호출 한도·재사용 계약은 미확인. 홈페이지 예시는 실제 우리 키워드로 실행한 결과가 아님. |
| **KeywordTool.io** | 여러 검색 서비스의 키워드 제안·검색량. YouTube·Naver 등은 **추정 검색량**으로 명시 | [공식 API 문서](https://keywordtool.io/api)에 v2 REST·샌드박스·공개 OpenAPI 명세·키 인증·API 지원 플랜 안내 | 자동 키워드 확장이 꼭 필요해질 때 선택. UI·API·MCP가 일일 한도를 공유. 유료 플랜·키·지역·언어 조건을 확인해야 함. Google/Bing과 YouTube의 데이터 성격을 섞지 않음. |

현재 권장 조합은 **공식 URL·PDF·선택 EML + YouTube 공식 메타데이터 + 수동 벤치마킹 메모**다. 유료 분석 도구 여러 개를 한꺼번에 연결하기보다, 실제 주제 발굴의 공백이 확인됐을 때 한 공급자를 추가하는 편이 유지·비용 검증에 유리하다. 이는 설계 제안이며 구매·가입 추천을 실행한 상태가 아니다.

## 4. YouTube API의 최신 제약 — 과거 가정을 그대로 쓰지 않기

### 쿼터

조사한 [공식 쿼터 표](https://developers.google.com/youtube/data/determine_quota_cost)는 `search.list` 하루 100회 전용 버킷, `videos.insert` 하루 100회 전용 버킷, 나머지 메서드 합계 하루 10,000단위를 설명한다. 검색·업로드는 각 호출당 1이며 페이지 추가 조회도 새 호출이다. 실제 프로젝트 한도는 Cloud Console에서 확인해야 한다. [변경 이력](https://developers.google.com/youtube/data/revision_history)의 2026-06-01 항목이 분리 전환을 설명한다. 오래된 ‘검색 100단위·업로드 1,600단위’ 계산을 현재 기본값으로 사용하지 않는다.

### 공식 수치와 독자 점수

[개발 정책 가이드](https://developers.google.com/youtube/terms/developer-policies-guide)는 API 데이터만 사용한 단순 평균·차이·정렬의 허용 예시를 제시하지만, 채널에 자체 평가점수를 매기거나 시청자 구성·재무 성과·광고 적합성을 추정하는 기능은 금지 예시로 든다. ‘조회수는 공식 API 수치, 글감 적합성은 사용자가 쓴 편집 메모’처럼 분리한다. 임의의 떡상 확률·수익 예측을 API 기반 제품 기능으로 추가하려면 정책 검토가 먼저다.

### 저장과 표시

[개발 정책](https://developers.google.com/youtube/terms/developer-policies)의 비인증 데이터 저장·갱신 조건을 반영해 원시 메타데이터의 수집 시각, 갱신 시각, 만료 시각을 저장한다. 기본 캐시 TTL 제안은 29일이며 이 숫자는 제품 설계값이다. 오래된 경쟁 채널 통계를 무기한 보관하거나 자료를 다른 출처와 섞은 단일 지표로 제공하지 않는다.

### 업로드의 안전 기본값

[현재 업로드 문서](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert?hl=en)는 `privacyStatus` 생략 시 기본이 `public`이며 미검증 API 프로젝트가 자동으로 비공개 제한된다고 가정하지 말라고 설명한다. 따라서 v5는 승인 전 API 업로드를 호출하지 않고, 허용된 시험 업로드에도 `privacyStatus=private`를 명시해야 한다. 계정 설정에 따른 예외를 자동 안전장치로 의존하지 않는다.

## 5. 승인과 구독 보상의 분리

### 콘텐츠 승인 제안

1. 소스 URL·파일·사용 범위와 판본을 승인한다.
2. 공통 조사 원고의 사실·인용·개인 경험을 검토한다.
3. 원고 승인 후 원하는 채널의 파생물을 만든다.
4. 채널별 본문·영상·표지·메타데이터를 검증한다.
5. **최종 파일 해시, 계정, 채널, 공개 범위, 일정, 상품·쿠폰 조건**을 묶어 게시 승인을 받는다.
6. 그 승인과 같은 판본만 외부 전송한다. 파일·원문·계정·공개 범위·시간이 바뀌면 관련 승인부터 무효화한다.

이는 과거 하네스의 사용자 승인 구조를 재사용하자는 제안이다. 기존 v5 코드에서 실제 구현됐다고 확인한 결과가 아니다.

### YouTube 구독·참여 보상

[YouTube API 개발 정책](https://developers.google.com/youtube/terms/developer-policies)은 시청·좋아요·공유·구독·댓글과 교환하는 보상을 API 클라이언트에 허용하지 않는다. [구독 버튼 조건](https://developers.google.com/youtube/subscribe/conditions-of-use)은 버튼 클릭 보상과 클릭 추적도 금지한다. 따라서 ‘구독 인증 → HeoBrain 쿠폰 지급’을 기본 캠페인으로 구현하지 않는다. [허위 참여 정책](https://support.google.com/youtube/answer/3399767?hl=en-GB)도 함께 확인했다.

별도 제안은 YouTube 행동과 연동하지 않는 공개 캠페인 코드 또는 HeoBrain 자체 서비스에서 명시적으로 정한 구매·이벤트 조건이다. 이것이 곧 법률·플랫폼 승인 완료라는 뜻은 아니다. 뉴스레터 수신 동의·개인정보 이용·쿠폰 조건과 다른 플랫폼 규칙은 별도 확인 대상이다. YouTube의 규칙을 Instagram·TikTok 등 모든 플랫폼에 같은 문구로 확대하지 않는다.

## 6. 통합할 최소 소스 카드와 상태

기존 구조를 읽은 뒤 실제 필드에 맞추는 것이 우선이다. 다음은 개념 필드 제안이다.

- 소스: `source_id`, `source_type`, `canonical_url`, `title`, `publisher`, `published_at`, `retrieved_at`, `content_hash`, `language`, `license_evidence_url`, `usage_scope`, `rights_status`.
- 수집: `fetch_status`, `mime_type`, `bytes`, `pages`, `refresh_after`, `expires_at`, `error_code`, `attempts`, `auth_required`.
- 벤치마킹: `provider`, `observed_at`, `raw_metric_name`, `raw_metric_value`, `is_estimate`, `methodology_url`, `editor_note`. 제공자 추정치와 YouTube 원시 수치의 출처를 분리한다.
- 승인: `source_version`, `article_hash`, `artifact_hash`, `approved_by`, `approved_at`, `account_id`, `channel`, `visibility`, `schedule`, `campaign_conditions_hash`.

상태 흐름 제안:

`발견 → 원문 확인 → 권리·사용 범위 확인 → 수집/검증 → 검토 대기 → 원고 승인 → 파생물 검증 → 게시 조건 승인 → 전송 → 플랫폼 결과 확인`

검색 요약·로그인 화면·샘플 데이터는 ‘수집/검증’으로 승격하지 않는다. 접근 실패는 ‘자료 없음’과 다르다. `401/403`, 만료 토큰, 쿼터 초과, 잘못된 MIME, PDF 파싱 실패는 각각 다른 실패 사유를 보존한다.

## 7. 통합 후 필요한 검증 — 아직 실행하지 않음

- 같은 파일·URL의 중복 수집을 막되 출처와 새 판본 이력을 유지한다.
- 공개 PDF를 HTML 오류 페이지로 잘못 저장하지 않는다. 원본을 덮어쓰지 않고 매직바이트·쪽수·해시를 확인한다.
- API 키가 클라이언트 번들·로그·보고서에 노출되지 않는지 확인한다.
- 메일 라벨 필터가 있어도 과도한 OAuth 범위를 숨기지 않는다. 선택 파일 방식으로도 연구를 시작할 수 있게 한다.
- API 데이터가 만료되거나 소스가 바뀌면 관련 주장과 승인 상태를 갱신한다.
- 승인 없이 업로드·공개·쿠폰 발급이 호출되지 않는지 확인한다. 업로드 파라미터에서 공개 범위를 생략하는 경우 실패 처리한다.
- 공식 수치, 제공자 추정, 사용자 가설을 UI와 결과 문서에서 구별한다.
- 공급자 연결이 없어도 수동 URL·선택 PDF·EML로 계속 진행할 수 있게 한다.

## 미구현/차단과 산출물 기록

- 실제 API 연동·API 키 검증·OAuth·유료 도구 검색·외부 게시·쿠폰 발급·새 사이트 배포: 실행하지 않음.
- 블랙키위 메인 사이트는 403, uSearch는 공개 HTML에 오류 상태 포함, KOCCA의 개별 설명 게시물 일부와 찬스툴 직접 PDF는 확인 미완료.
- 다운로드 완료 PDF 수·해시는 상위 작업의 실제 저장 결과로 별도 판정해야 한다. 이 조사 파일만으로 ‘모든 책을 확보했다’고 보고하면 안 된다.
- 수정한 기존 파일: 없음.
로컬 자료의 경로와 비공개 작업 기록은 웹 인계본에서 제외했다.
- 외부 시스템에서 수정한 페이지: 없음.
