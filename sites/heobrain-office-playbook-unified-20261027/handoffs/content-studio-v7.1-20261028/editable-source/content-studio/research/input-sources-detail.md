# 콘텐츠 자동화 입력 소스 등록부

검증일: 2026-10-28T05:17:37.909000+09:00

## 현재 구현·이번에 검증 완료

- 선별 등록부 **21개**: 공식 기관·개발사·공식 호스트 18개 항목과 보조 큐레이션 3개. 인터넷 전체를 조사했다는 의미가 아니다.
- 공개 페이지와 피드에 익명 GET을 보내 상태 코드·Content-Type·제한된 본문을 확인했다. RSS·Atom은 XML 루트와 항목 구조도 확인했다. 웹 도구가 XML MIME을 지원하지 않은 것은 원 서버 HTTP 오류와 구분했다.
- 검증된 피드 연결 항목 10개, 중복을 제외한 피드 URL 9개. HTML 정상 응답 18개. 모든 수집 설정은 비활성 상태다.
- 연결 확인은 콘텐츠 정확성·크롤링 허락·API 연동·스케줄 실행 검증을 대신하지 않는다. 인증정보·OAuth·메일함 접근·실제 구독·cron을 사용하거나 활성화하지 않았다.

## 신뢰 분류와 사용 원칙

1. 공급자 뉴스·기술 블로그는 원발표와 운영 경험의 근거다. 업체의 성능·매출·절감 주장을 독립 재현 실험으로 쓰지 않는다. 조건·버전·원 코드·평가 자료를 따로 확인한다.
2. 연구 블로그는 연결된 논문·코드·데이터로 돌아간다. arXiv는 ID와 v1/v2 등 판본, DOI·저널 참조와 심사 상태를 구분한다. 저장소에 올라왔다는 사실만으로 심사 통과나 오류 없음이 입증되지 않는다.
3. Hugging Face는 공식 플랫폼이어도 커뮤니티 저자·모델 제공자가 섞인다. 저자/조직·모델 카드·revision·가중치/데이터 라이선스를 개별 확인한다.
4. The Batch·TLDR AI·GeekNews는 소재 발견과 해설의 보조 경로다. 요약·추천 수·공유 수를 사실 검증 점수로 바꾸지 않고 원출처로 회귀한다.
5. frequency는 제품의 향후 수집 주기 제안이다. 발행사의 실제 발행 주기를 보증하거나 예약 작업을 활성화한 값이 아니다. confidence도 사실일 확률이 아니라 출처 성격의 분류다.

## 선별 소스 목록

| ID | 소스·유형 | 수집 후보 | 응답 확인 | 직접 유용한 이유 |
|---|---|---|---|---|
| openai-news | [OpenAI News](https://openai.com/news/) · official_news | [피드](https://openai.com/news/rss.xml); 비활성 | 페이지 403 / http_error; 피드 200 / xml_feed_confirmed | 모델·이미지·음성·콘텐츠 제작 기능 변경의 원발표. 공급자 발표를 독립 실험 결과로 취급하지 않음. |
| openai-engineering | [OpenAI Engineering](https://openai.com/news/engineering/) · official_engineering | [피드](https://openai.com/news/rss.xml); 비활성 | 페이지 403 / http_error; 피드 200 / xml_feed_confirmed | 운영·도구·평가·지연시간·비용 설계의 엔지니어링 근거. 공용 News 피드의 Engineering 범위를 선별. |
| anthropic-news | [Anthropic News](https://www.anthropic.com/news) · official_news | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | Claude·도구·제품 변경의 원발표. 뉴스룸 기사와 실제 사용 조건을 연결. |
| anthropic-engineering | [Anthropic Engineering](https://www.anthropic.com/engineering) · official_engineering | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 프롬프트·도구·하네스·에이전트 실패·평가 패턴의 구현 참고. |
| google-ai-blog | [Google AI Blog](https://blog.google/technology/ai/) · official_news | [피드](https://blog.google/rss/); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 이미지·영상·음성·Gemini 콘텐츠 기능의 원발표. 공식 페이지의 RSS 링크는 전체 Google 블로그 피드이므로 주제 선별 필요. |
| gemini-changelog | [Gemini API Release Notes](https://ai.google.dev/gemini-api/docs/changelog) · official_docs | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 생성 모델·API 지원·중단·버전 변경을 원문 날짜와 대조. 발표와 실제 API 호출 검증을 구분. |
| microsoft-research | [Microsoft Research Blog](https://www.microsoft.com/en-us/research/blog/) · official_research_blog | [피드](https://www.microsoft.com/en-us/research/feed/); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 멀티모달·에이전트·평가 연구를 원 논문과 연결. 블로그 요약은 독립 재현이 아님. |
| aws-ml | [AWS Machine Learning Blog](https://aws.amazon.com/blogs/machine-learning/) · official_technical_blog | [피드](https://aws.amazon.com/blogs/machine-learning/feed/); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 생성형 AI·에이전트·미디어 워크플로 구축 예시와 운영 제약. 클라우드 비용·버전은 별도 확인. |
| nvidia-developer | [NVIDIA Technical Blog](https://developer.nvidia.com/blog/) · official_technical_blog | [피드](https://developer.nvidia.com/blog/feed/); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 영상·음성·추론·로컬 GPU 제작 워크플로의 구현 자료. 업체 성능 수치는 조건·코드·측정 근거를 확인. |
| huggingface-blog | [Hugging Face Blog](https://huggingface.co/blog) · official_host_mixed_authors | [피드](https://huggingface.co/blog/feed.xml); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 콘텐츠 생성 모델·도구 사례의 탐색. 공식 호스트의 커뮤니티 글도 섞여 있으므로 저자·조직·원 저장소를 재확인. |
| huggingface-modelcards | [Hugging Face Model Cards](https://huggingface.co/docs/hub/model-cards) · official_modelcard_documentation | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 모델 카드의 용도·제약·평가·라이선스를 읽는 기준. 실제 감시 모델 저장소는 사용자가 별도로 선택. |
| github-n8n-releases | [n8n GitHub Releases](https://github.com/n8n-io/n8n/releases) · official_repository_releases | [피드](https://github.com/n8n-io/n8n/releases.atom); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 콘텐츠 자동화 노드·호환성·수정·중요 변경 추적. 릴리스 발표는 우리 설치 환경 검증을 대신하지 않음. |
| arxiv-ai | [arXiv cs.AI Recent / RSS](https://arxiv.org/list/cs.AI/recent) · preprint_repository | [피드](https://rss.arxiv.org/rss/cs.AI); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 에이전트·평가·생성 연구 후보를 탐색. arXiv ID와 v1/v2, DOI·저널 참조·심사 상태를 각각 확인. |
| nia-policy | [NIA Policy Research](https://www.nia.or.kr/site/nia_kor/ex/bbs/List.do?cbIdx=66361) · institutional_reports | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 한국어 AI 정책·활용·데이터·윤리 근거. 발간일·개별 보고서 원문·조사 조건을 확인. |
| aihub | [AI Hub](https://www.aihub.or.kr/) · official_dataset_portal | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 한국어 음성·영상·텍스트 등 제작·평가 데이터 후보와 이용 조건 확인. 수집은 공개 메타데이터·원문 링크부터. |
| etri-trends | [ETRI Electronics and Telecommunications Trends](https://ettrends.etri.re.kr/ettrends/) · institutional_technical_journal | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 미확인 / fetch_or_parse_error | 한국어 생성 콘텐츠·영상·음성·안전성 기술 동향. DOI·발간호·참고문헌과 실험 근거를 원문에서 확인. |
| kocca-welcon | [KOCCA WelCon Focus](https://welcon.kocca.kr/ko/insight-focus) · institutional_reports | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 콘텐츠 산업·마케팅·영상·창작 직무의 한국어 산업 자료. 연구 요약과 원 데이터 출처를 분리. |
| kobaco-reports | [KOBACO Advertising Research](https://www.kobaco.co.kr/site/adstat/board/report_etc_report/list?baCommSelec=false&baNotice=false&baOpenDay=true&baUse=true&bcId=report_etc_report&cp=1&sortDirection=DESC&sortOrder=BA_REGDATE) · institutional_reports | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 광고 제작 AI 활용·매체·노동환경·소비자 조사. 표본·조사시기·해석 범위를 보존. |
| the-batch | [The Batch / DeepLearning.AI](https://www.deeplearning.ai/the-batch/) · secondary_newsletter_archive | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 주간 AI 뉴스의 주제 발견과 해설. 주장·수치·모델 버전은 연결된 공식 발표·논문으로 회귀. |
| tldr-ai | [TLDR AI Archive](https://tldr.tech/ai/archives) · secondary_newsletter_archive | 공식 피드 미확인; 링크/변경 검토; 비활성 | 페이지 200 / html_response_confirmed | 짧은 동향 큐레이션에서 콘텐츠 소재 발견. 광고·소개 문구·요약과 원 출처를 구분. |
| geeknews | [GeekNews](https://news.hada.io/) · secondary_community_curation | [피드](https://news.hada.io/rss/news); 비활성 | 페이지 200 / html_response_confirmed; 피드 200 / xml_feed_confirmed | 한국어 개발·AI 큐레이션에서 주제 발견. 추천 수·요약은 사실 검증 점수가 아니며 링크된 원 출처를 읽음. |

## 피드와 변경 확인 시 주의

- OpenAI News와 Engineering은 하나의 News RSS를 공유한다. 실제 수집기에서는 피드 URL당 한 번만 가져오고 카테고리·원문을 나눠 중복 저장을 피한다.
- Google AI 페이지의 공식 RSS 링크는 전체 Google Blog 피드로 연결된다. AI 관련 항목을 선별해야 하며 AI 전용 피드라고 표시하지 않는다.
- NVIDIA·GeekNews는 경로 이름에 RSS/feed가 들어가더라도 응답은 Atom일 수 있다. MIME 하나나 확장자에만 의존하지 않는다.
- Anthropic·Gemini 문서·한국 기관·뉴스레터에 대해 공식 RSS를 확인하지 못한 경우 HTML 링크/변경 검토 후보로 남겼다. 부재를 영구 확정한 것은 아니다. RSSHub·개인이 만든 피드를 공식 피드로 둔갑시키지 않는다.
- 응답이 200이어도 자바스크립트 앱의 실제 검색·다운로드 기능이나 내용 최신성까지 검증한 것은 아니다. 차단·시간 초과는 자료가 없다는 뜻이 아니다.
- 익명 읽기 확인은 운영 수집 허락이 아니다. 도메인 약관·robots·요청량·자료별 라이선스를 운영 전에 확인하고, 유료벽·로그인·접근 제한은 우회하지 않는다.

## 권리·버전·출처 카드에 남길 값

각 수집물에 원문 URL, 발행/갱신 시각, 관측 시각, 저자/기관, 판본·commit·모델 revision, 권리 근거, 사용 범위, 원본 해시와 검토 상태를 붙인다. 모델 성능 비교는 조건과 재현 여부를 별도 기록한다. PDF·이미지·논문·데이터·코드의 라이선스를 같은 것으로 취급하지 않는다. 개인정보가 담긴 메일은 명시적으로 선택한 파일부터 받아 검토한다.

## 실제 HTTP·XML 검증 범위

페이지는 최대 128KiB, 피드는 최대 512KiB 샘플을 읽었다. 큰 응답은 XML 시작/항목 구조의 표본 검사이며 전체 XML 스키마 유효성 검사가 아니다. 샘플 SHA-256은 응답 전체가 아닌 읽은 샘플의 해시다. 원문의 내용·수치·링크를 전수 검증하지 않았다. HTTP 상태·리다이렉트·오류·응답 유형·관측 시각은 JSON의 verification에 보존했다.

## 계획/제안

처음에는 검증된 공식 피드 3~5개와 한국어 기관 1~2개만 사용자가 고른다. 주제 필터 → 원출처 확인 → 권리/버전 점검 → 조사 원고 검토로 이어간다. 수집량이 많아도 원고 승인·게시 조건 승인을 건너뛰지 않는다. 변경된 소스는 이전 승인과 파생물에 영향을 주는지 다시 확인한다.

## 미구현/차단

- 운영 수집기·동시 처리·HTML 파서·권한 연결·구독·메일 수집·cron: 이번 작업에서 실행하지 않음.
- 실제 정상 응답을 확인한 URL만 피드 확인 상태로 표시했다. 실패·보류 항목의 조회 경로를 다른 수단으로 우회하지 않았다.
- 품질 점수·임의 떡상 확률·보도자료 수치의 독립 재현을 검증했다고 주장하지 않는다.
- 이 등록부는 선택 목록이며 모든 뉴스·문서·학술자료·책을 모은 전체 목록이 아니다.
