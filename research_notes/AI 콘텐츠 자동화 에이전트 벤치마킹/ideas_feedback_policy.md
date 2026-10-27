# AI 콘텐츠 자동화 에이전트의 "앞단과 뒷단": 아이디어/트렌드 발굴, 성과 피드백 루프, 품질 게이트, 플랫폼 정책 (기준일 2026-10-27)

> 조사 범위: (a) 아이디어 발굴·점수화 데이터 소스와 API, (b) 발행 후 성과 측정과 다음 기획으로의 환류, (c) 사람 승인 전 자동 품질/사실성 검사, (d) AI 자동화 콘텐츠를 제약하는 플랫폼 규칙과 법.
> 표기 원칙: 모든 정책과 수치에 날짜를 붙였습니다. 공식 문서 페이지의 "Last updated"는 해당 페이지를 이번 세션(2026-10-27)에 직접 가져와 확인한 값입니다. 2차 출처(블로그·벤더 글)만 있는 항목은 그렇게 표시했습니다.

---

## Q1. 아이디어 발굴: 데이터 소스, API, 쿼터, 아이디어 점수화 방법

### Takeaway
아이디어 발굴에 쓸 수 있는 공식 API는 쿼터가 빡빡하고(YouTube 검색은 하루 100회), 상대지수만 주거나(Naver DataLab, Google Trends 웹), 아직 알파 단계입니다(Google Trends API). 그래서 파이프라인은 저비용 소스(HN, RSS, `videos.list`)로 후보를 넓게 모은 뒤, 비싼 호출은 상위 후보에만 써야 합니다. YouTube가 2026-08부터 Studio에서 "outlier multiplier"(채널 평균 대비 배수)를 시험 중이라는 점은 "아웃라이어 비율"이 사실상 표준 점수 축이 되었다는 신호입니다.

### Cited Findings

**YouTube Data API v3 (쿼터)**
- 2026-10-15에 갱신된 공식 쿼터 페이지 기준으로 `search.list`와 `videos.insert`는 각자 별도 쿼터 버킷을 씁니다. 원문: "Projects that enable the YouTube Data API have a default quota allocation of 100 `search.list` calls, 100 `videos.insert` calls, and 10,000 units per day combined for all other endpoints." 두 메서드 모두 "Each call costs 1 quota"이고 기본 한도는 하루 100회입니다. 쿼터는 태평양 시간 자정에 초기화됩니다. — [YouTube Data API: Quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- 같은 페이지(2026-10-15) 기준 호출 비용: `videos.list`, `channels.list`, `commentThreads.list`, `playlistItems.list`는 1 unit, `thumbnails.set`과 `videos.update`는 50 unit, `captions.insert`는 400 unit입니다. — [YouTube Data API: Quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- 이 페이지에는 쿼터 체계를 언제 바꿨는지 알려주는 변경 이력이나 날짜 공지가 없습니다. — [YouTube Data API: Quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)

**YouTube Studio 내 아이디어 도구**
- Inspiration 탭은 단계적으로 종료되는 중입니다. 원문: "Starting August 2026, we are gradually deprecating the Inspiration tab." 아이디어 브레인스토밍은 "use Ask Studio in YouTube Studio"로 안내합니다. Inspiration 탭은 데스크톱에서만 쓸 수 있었고, 아이디어는 영어로만 제공했습니다. — [YouTube Help: Explore Inspiration tab](https://support.google.com/youtube/answer/15575509?hl=en)
- 2026-08-05 Tubefilter 보도에 따르면 YouTube는 Studio에서 새 "Research" 탭을 "a small number of users"에게 시험 중입니다. 이 탭은 "outlier multiplier"를 보여주는데, 기사의 정의는 "a number that rates how well a video performed compared to a creator's other content"이고 스크린샷 예시는 4x~132x입니다. "Watched by my viewers" 필터는 내 기존 시청자가 많이 본 다른 크리에이터의 영상만 보여줍니다. 더 넓은 출시에 대해서는 "currently no information available"이라고 했습니다. — [Tubefilter, 2026-08-05](https://www.tubefilter.com/2026/08/05/youtube-research-tab-outlier-multipliers-viewer-comparison-data/)
- Social Media Today는 이전에 Studio의 "Research" 탭 이름이 "Inspiration"으로 바뀌었다고 보도했습니다. 2026-08의 새 Research 탭과 시간 순서가 맞지 않으므로, 별개 실험으로 봐야 합니다. — [Social Media Today](https://www.socialmediatoday.com/news/youtube-previews-coming-ai-elements-in-its-inspiration-tab/734347/) (검색 요약 기준, 직접 가져오지 않음)

**Google Trends API**
- 공식 페이지 기준 상태는 여전히 **alpha**입니다. "now accepting applications for alpha testers", "As we can't open the API for everyone yet". 신청서를 내야 하며 셀프서비스 가입은 없습니다. 데이터는 최근 5년 롤링 윈도, 일/주/월/년 집계, 국가와 하위 지역 비교를 지원합니다. 웹 UI처럼 0~100으로 정규화하지 않고 "consistently scaled"이므로 최신 기간만 다시 가져와 이어 붙일 수 있습니다. UI는 8개 검색어까지 비교하지만 API는 "dozens"를 비교할 수 있습니다. 쿼터는 페이지에 없습니다. — [Google Search Central: Trends API](https://developers.google.com/search/apis/trends)
- 발표일은 2025-07-24이고, 2026-08-31에도 페이지는 여전히 알파 테스터 모집 상태였습니다. Trending Now 데이터는 포함되지 않고, 가격과 GA 일정은 발표되지 않았습니다. — [PPC Land](https://ppc.land/google-opens-alpha-testing-for-new-trends-api-targeting-developers-and-journalists/); [Search Engine Journal](https://www.searchenginejournal.com/google-trends-api-alpha-launching-breaking-news/551935/); [konabayev.com "Google Trends API Landscape 2026"](https://konabayev.com/blog/google-trends-api-landscape-2026/) (2차 출처)

**Naver DataLab / NAVER API HUB (한국)**
- 2026-07-31부터 신규 키는 NAVER API HUB에서만 발급합니다. 기존 NAVER Developers 키는 2027-06-30까지 쓸 수 있고, "HUB 키와 서로 바꿔 쓸 수 없습니다". — [디지털마케터 인사이트 (2026-09-14 게시, 2026-10-04 수정)](https://www.digitalmarketer.co.kr/insights/naver-datalab-api-data-for-non-developers)
- HUB 쿼터는 검색어 트렌드 **월 최대 50,000건**, 쇼핑인사이트 **월 최대 50,000건**(서로 별도)입니다. 이 값은 2026-10-04 공식 개요 기준이며 "지금은 한시적으로 무료"입니다. 같은 키를 쓰는 프로그램은 사용량이 합산됩니다. — [디지털마케터 인사이트](https://www.digitalmarketer.co.kr/insights/naver-datalab-api-data-for-non-developers)
- 기존 Developers 키의 검색어 트렌드 한도는 **하루 1,000회**입니다. — [디지털마케터 클래스: AI 검색 트렌드 조사](https://www.digitalmarketer.co.kr/class/ai-marketing-in-practice/search-trend-research-with-ai) (검색 요약 기준)
- DataLab 값은 "한 요청 안에서 가장 큰 값을 100으로 둔 상대 지수"입니다. 실제 검색 횟수는 알 수 없고, 기간·검색어 구성·필터가 다른 요청끼리는 지수를 이어 붙이거나 직접 비교하면 안 됩니다. — [디지털마케터 인사이트](https://www.digitalmarketer.co.kr/insights/naver-datalab-api-data-for-non-developers)
- NAVER API HUB 공식 개요 문서의 API 목록: 검색(뉴스, 백과, 블로그, 웹문서, 이미지, 지식iN, 지역, 카페, 성인 검색어 판별, 오타 변환), Search Trend(DataLab 통합검색 키워드 그룹 트렌드), Shopping Insight(분야별, 분야·키워드별, 기기·성별·연령별 트렌드). 429 에러는 "하루 허용량 초과"를 뜻합니다. — [NAVER Cloud: NAVER API HUB overview](https://api.ncloud-docs.com/docs/naver-api-hub-overview)

**Reddit Data API**
- 여러 2차 출처에 따르면 OAuth 클라이언트 ID 하나당 **100 QPM**이고 10분 윈도로 평균을 냅니다. 비OAuth 요청은 단순 제한이 아니라 거부됩니다. 2026-07-20 게시, 2026-08-25 수정된 출처입니다. — [SocialCrawl "Reddit API Key, Limits, and Pricing: The 2026 Guide"](https://www.socialcrawl.dev/blog/reddit-api-key-limits-alternatives-2026). **상충**: 2026-07-27에 약관 원문을 직접 읽었다고 밝힌 다른 2차 출처는 OAuth 클라이언트 한도를 **60 RPM**으로 적었습니다. — [SocialCrawl "Reddit Data API 2026"](https://www.socialcrawl.dev/blog/reddit-data-api-2026) (검색 요약 기준)
- 상업적 이용, 레이트 리밋을 넘는 연구, 명시적으로 허용되지 않은 모든 이용에는 Reddit과의 별도 계약이 필요하고 요금은 Reddit 재량입니다. AI 학습에 쓰려면 콘텐츠 권리자의 명시적 허락이 필요합니다. 약관 최종 개정일은 2026-07-20입니다(2차 출처). — [SocialCrawl "Reddit Data API 2026"](https://www.socialcrawl.dev/blog/reddit-data-api-2026) (검색 요약 기준)
- 흔히 인용되는 "$0.24 / 1,000 calls"는 2023-06 발표에서 나온 수치이고, 현재 공개된 요금 페이지에는 없습니다. — [SocialCrawl 2026 Guide](https://www.socialcrawl.dev/blog/reddit-api-key-limits-alternatives-2026)
- Reddit 공식 Data API Wiki(support.reddithelp.com)는 이번 세션에서 403 오류로 열리지 않았습니다.

**Hacker News API**
- 기본 URL은 `https://hacker-news.firebaseio.com/v0/`이고, 엔드포인트는 `item`, `user`, `topstories`(최대 500), `newstories`(최대 500), `beststories`, `askstories`/`showstories`/`jobstories`(각 최대 200), `maxitem`, `updates`입니다. 원문: "There is currently no rate limit." Firebase 기반이라 거의 실시간으로 변경 알림을 받을 수 있습니다. — [GitHub HackerNews/API](https://github.com/HackerNews/API)

### Inferences
- **YouTube 쿼터 변경 주의**: 기존 지식(이번 세션에서 검증하지 않음)으로는 `search.list`가 호출당 100 unit이었고 10,000 unit을 같이 썼습니다. 2026-10-15 페이지는 "별도 버킷, 하루 100회, 호출당 1"로 바뀌어 있습니다. 실무적으로 키워드 검색은 여전히 **하루 100회**가 상한입니다. 그 대신 `videos.list`(1 unit, 1회에 최대 50개 ID)와 `channels.list`로 통계를 보강하는 비용은 매우 쌉니다. 따라서 "검색은 적게, 통계는 많이" 구조가 맞습니다. 쿼터 증설 신청 절차와 감사 요건은 이번 조사 범위 밖입니다.
- **아이디어 점수화 공식(제안)**. YouTube Research 탭의 "outlier multiplier"(채널 자기 평균 대비 배수)를 핵심 축으로 둡니다.
  - `outlier = 영상 조회수 / 해당 채널 최근 N개 영상의 중앙값 조회수`. 구독자 수 대비 조회수(views/subs)는 보조 지표로만 씁니다. 구독자 수는 반올림 공개값이라 노이즈가 큽니다.
  - `demand = Trends API 절대 스케일 또는 Naver DataLab 상대지수의 기울기(최근 4주 대비 12주)`. DataLab은 요청마다 최댓값이 100이므로 **같은 요청 안에 기준 키워드(앵커)를 넣어** 정규화해야 합니다.
  - `competition = 같은 키워드 상위 결과의 최근 30일 업로드 수, 상위 채널 규모`
  - `fit = 브랜드/채널 주제 임베딩과의 코사인 유사도` 같은 LLM 판정
  - 최종 점수는 `w1·log(outlier) + w2·demand_slope − w3·competition + w4·fit`처럼 잡습니다. 가중치는 Q2의 피드백 루프 결과로 다시 맞춥니다.
- HN과 RSS는 쿼터 부담이 거의 없어 "얼리 시그널" 레이어로 적합합니다. Reddit은 상업용 자동화라면 별도 계약 리스크가 있으므로, 개인 연구 수준의 저빈도 사용이나 공식 계약을 전제로 설계해야 합니다.
- Naver 키 체계 이행 기간(2026-07-31 ~ 2027-06-30) 중에는 두 키 체계를 모두 지원하는 어댑터를 두는 것이 안전합니다.

### Gaps
- **Exploding Topics / Glimpse**: 이번 세션에서 API 요금, 엔드포인트, 데이터 정의를 확인하지 못했습니다.
- **Reddit 공식 문서**: 공식 Wiki가 403으로 막혀 레이트 리밋(100 vs 60 QPM)을 1차 출처로 확정하지 못했습니다. 2026-10-31에 신규 공개 요청이 중단된다는 소문도 검증하지 못했습니다(2차 출처조차 "unverified"로 표기).
- **Naver Developers 원문**: developers.naver.com이 이번 세션에서 열리지 않아 DataLab 파라미터 원문(시작일 하한, keywordGroups 최대 개수 등)을 확인하지 못했습니다. 기존 지식으로는 2016-01-01 이후, 그룹 최대 5개, 그룹당 키워드 최대 20개이지만 이번 세션에서 검증하지 않았습니다.
- **Google Trends API 쿼터·GA 일정**: 공식 페이지에 없습니다.
- **YouTube Research 탭의 outlier multiplier 정확한 공식**(평균인지 중앙값인지, 비교 기간이 얼마인지): 공개된 정의가 없습니다.

---

## Q2. 피드백 루프: 포맷별 핵심 지표, API로 얻을 수 있는 것, A/B 테스트, 원인 귀속과 다음 가설

### Takeaway
YouTube의 리텐션 지표(평균 시청 지속시간, 시청 비율, 구간별 리텐션 곡선, 동일 길이 대비 상대 리텐션)는 Analytics API로 받을 수 있습니다. 반면 **노출수와 노출 클릭률(CTR)은 Analytics API에 없고 Reporting API 대량 보고서(`channel_reach_basic_a1`, `channel_reach_combined_a1`)로만** 받습니다. YouTube Test & Compare는 CTR이 아니라 **watch time(시청 시간)**으로 승자를 정하고, Shorts에는 쓸 수 없습니다. 블로그는 Google Search Console API로 클릭, 노출, CTR, 순위를 시간 단위까지 받을 수 있지만, 네이버 서치어드바이저용 공식 API는 확인되지 않았습니다.

### Cited Findings

**YouTube Analytics API (targeted queries), 페이지 갱신 2026-09-14**
- `engagedViews`: "The number of times the channel's videos have been viewed past the first frame, or the user clicks/taps to play." — [YouTube Analytics API: Metrics](https://developers.google.com/youtube/analytics/metrics)
- `averageViewDuration`("The average length, in seconds, of video playbacks"; 2021-12-13부터 looping clips 트래픽 제외), `averageViewPercentage`, `estimatedMinutesWatched`, `subscribersGained` — [YouTube Analytics API: Metrics](https://developers.google.com/youtube/analytics/metrics)
- 리텐션 곡선: `audienceWatchRatio`("The absolute ratio of viewers watching the video at the given point in the video", `elapsedVideoTimeRatio` 차원과 함께 사용), `relativeRetentionPerformance`(0~1, "all YouTube videos of similar length"와 비교), `startedWatching`/`stoppedWatching`/`totalSegmentImpressions` — [YouTube Analytics API: Metrics](https://developers.google.com/youtube/analytics/metrics)
- 이 페이지에는 일반 영상 **노출수나 노출 CTR 지표가 없습니다**. 있는 것은 `adImpressions`, `cardImpressions`, `cardClickRate`, `annotationClickThroughRate` 같은 카드·광고·주석용 지표뿐입니다. Shorts 전용 설명도 없습니다. — [YouTube Analytics API: Metrics](https://developers.google.com/youtube/analytics/metrics)

**YouTube Reporting API (bulk), 페이지 갱신 2026-09-14**
- 썸네일 노출과 CTR은 보고서 `channel_reach_basic_a1`과 `channel_reach_combined_a1`의 지표 `video_thumbnail_impressions`, `video_thumbnail_impressions_ctr`로 제공됩니다. — [YouTube Reporting API: Channel reports](https://developers.google.com/youtube/reporting/v1/reports/channel_reports)

**Shorts 지표 변화**
- 2025-03-31부터 Shorts 조회수는 시청 시간 하한 없이 재생이나 반복 재생이 시작될 때마다 1회로 셉니다. 기존 방식의 지표는 "engaged views"로 남아 YouTube Analytics Advanced Mode에서 볼 수 있습니다. 이 변경은 수익화에 영향이 없고, YouTube는 2025-03-31 전후 비교에 engaged views를 쓰라고 권합니다. — [PPC Land](https://ppc.land/youtube-changes-how-shorts-views-are-counted-from-march-31/); [Sprout Social Help](https://support.sproutsocial.com/hc/en-us/articles/35874991211533-YouTube-Shorts-View-Count-Update-March-2025); [Digital Music News, 2025-03-27](https://www.digitalmusicnews.com/2025/03/27/how-does-youtube-shorts-count-views-2025/)
- Shorts 최대 길이는 2024-10에 60초에서 3분으로 늘었습니다. — [Routenote](https://routenote.com/blog/how-are-views-counted-shorts-tiktok-reels/) (2차 출처)

**YouTube A/B 테스트 (Test & Compare / "A/B test titles & thumbnails")**
- 테스트 유형은 "Title only, Thumbnail only, or Title and thumbnail"이고 최대 3개 변형까지 됩니다. YouTube Studio 데스크톱에서만 쓸 수 있고 Advanced features를 켜야 합니다. "Your test should be completed within two weeks." — [YouTube Help: A/B test titles & thumbnails](https://support.google.com/youtube/answer/13861714?hl=en)
- 승자 기준은 **watch time**입니다. YouTube는 "for overall watch time over other metrics, like click-through-rate"을 최적화한다고 밝힙니다. 결과는 "Winner", "Performed Same", "Inconclusive" 중 하나이고, Inconclusive면 처음 올린 제목과 썸네일이 기본값이 됩니다. 일부 시청자는 기본안만 보는 컨트롤 그룹으로 빠지고 결과에서 제외됩니다. — [YouTube Help: A/B test titles & thumbnails](https://support.google.com/youtube/answer/13861714?hl=en)
- 제외 대상: "You are not able to A/B test Shorts, Scheduled Lives, and Premiere videos at this time." 아동용, 성인 대상, 비공개 영상도 안 됩니다. 테스트 중 제목이나 썸네일을 바꾸면 테스트가 자동으로 멈춥니다. — [YouTube Help: A/B test titles & thumbnails](https://support.google.com/youtube/answer/13861714?hl=en)
- 제목 테스트는 2025-09에 "small percentage of creators" 대상 실험으로 시작했습니다. 2025-12에 전체 적격 크리에이터로 넓어졌다는 보도가 있지만 YouTube 1차 출처로는 확인하지 못했습니다. — [thumbnailtest.com](https://thumbnailtest.com/news/youtube-releases-title-test-compare/) (2차 출처)

**Google Search Console API (블로그와 웹)**
- Search Analytics `query`의 차원은 `country`, `device`, `page`, `query`, `searchAppearance`, `date`, `hour`입니다. `type`은 `web`, `image`, `video`, `news`, `discover`, `googleNews` 중 하나이고, `rowLimit`은 1~25,000(기본 1,000)이며 `startRow`로 페이지를 넘깁니다. `dataState`는 `final`, `all`, `hourly_all`입니다. 이 API는 "does not guarantee to return all data rows but rather top ones"이고, `first_incomplete_date` 이후 값은 "may still change noticeably". 페이지 갱신일은 2026-08-11입니다. — [Search Console API: searchanalytics.query](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
- 사용 한도(페이지 갱신 2025-08-28): Search Analytics는 사이트당 1,200 QPM, 사용자당 1,200 QPM, 프로젝트당 40,000 QPM과 30,000,000 QPD입니다. URL Inspection은 사이트당 2,000 QPD와 600 QPM입니다. 기간이 길수록, 그리고 page/query로 묶거나 필터링할수록 "load" 쿼터를 더 씁니다. — [Search Console API: Usage limits](https://developers.google.com/webmaster-tools/limits)

**Naver 서치어드바이저**
- 서치어드바이저는 색인 상태, 노출량, 클릭률, 순위 같은 지표를 웹 UI로 보여주는 무료 웹마스터 도구입니다. 이번 검색에서 **노출·클릭 데이터를 내보내는 공식 API는 찾지 못했습니다**. — [ampm 인사이트](https://inside.ampm.co.kr/insight/3721) (2차 출처)

### Inferences
- **포맷별 1차 KPI(제안)**
  - 롱폼: 노출 CTR(Reporting API), `averageViewPercentage`, `relativeRetentionPerformance`, 0~30초 구간 `audienceWatchRatio`(초반 이탈), 구독 전환(`subscribersGained/views`)
  - Shorts: `engagedViews / views` 비율. 2025-03-31 이후 views가 "모든 재생 시작"이 되었으므로, 이 비율이 Studio의 "viewed vs. swiped away"를 대신하는 근사치가 됩니다(추정). 여기에 `averageViewPercentage`(루프 포함 여부 주의)를 더합니다.
  - 블로그(Google): GSC의 query×page 노출, CTR, 평균 순위. Naver는 API가 없으므로 수동 또는 RPA 내보내기가 필요합니다.
  - 뉴스레터: 오픈율과 클릭률. 이번 세션에서 출처를 확보하지 못했습니다(Gaps).
- **원인 귀속(attribution)**
  - 제목과 썸네일은 Test & Compare(watch time 기준)로 인과 효과를 측정할 수 있습니다. 단, Shorts는 안 됩니다.
  - 주제, 훅, 길이 같은 나머지 변수는 실험을 할 수 없으므로 `relativeRetentionPerformance`(같은 길이 영상과 비교한 점수)와 채널 중앙값 대비 outlier 배수로 "채널 성장 효과"를 걷어낸 뒤, 변수별 태그(훅 유형, 길이 구간, 주제 클러스터)로 회귀하거나 집단별로 비교합니다.
  - 2025-03-31 Shorts 조회수 정의 변경처럼 지표 정의가 바뀐 시점은 시계열 단절로 다뤄야 합니다.
- **다음 기획으로 넘기는 방법(제안)**: 발행 후 48시간, 7일, 28일 스냅샷을 찍습니다. 지표별 임계값 규칙을 걸어 LLM이 "가설 카드"를 씁니다. 예: "초반 30초 리텐션이 채널 중앙값보다 15%p 낮다 → 훅에서 결론 먼저 제시". 이 카드를 Q1 점수식의 가중치와 다음 기획 브리프에 다시 넣습니다.
- Test & Compare가 CTR이 아니라 watch time으로 승자를 고르므로, 자동화 에이전트가 "CTR 최적화 제목"만 만들면 플랫폼의 판정 기준과 어긋날 수 있습니다.

### Gaps
- Shorts "swiped away" 지표를 API로 받을 수 있는지: Analytics metrics 페이지에 없어 API 미제공으로 보이지만 확정하지 못했습니다.
- Reporting API에서 audience retention 전용 bulk 보고서가 있는지: 이번에 본 channel reports 페이지에는 없었습니다.
- Naver 서치어드바이저와 Naver 블로그 통계의 공식 API 유무, 그리고 뉴스레터 플랫폼(Stibee, Beehiiv 등)의 오픈·클릭 API와 Apple MPP로 인한 오픈율 왜곡: 이번 세션에서 출처를 확보하지 못했습니다.
- GSC 데이터 보존 기간(16개월로 알려져 있음)과 property당 일일 행 상한: 이번에 본 공식 페이지에서는 확인하지 못했습니다.
- YouTube 제목 테스트가 전체 적격 크리에이터로 넓어진 날짜(2025-12설)를 1차 출처로 확인하지 못했습니다.

---

## Q3. 품질 게이트: LLM-as-judge, 사실 검증, 가독성·표절·브랜드 보이스·TTS·자막 검사

### Takeaway
사실성 검증은 "응답을 원자적 사실로 쪼갠 뒤 검색이나 지식원으로 하나씩 확인하는" 방식(FActScore, SAFE)이 정립되어 있습니다. SAFE는 사람 주석자와 72% 일치했고 의견이 갈린 사례에서 76% 이겼으며 비용은 20배 이상 저렴했습니다. LLM 심사(G-Eval, MT-Bench)는 사람과 상당히 일치하지만 위치 편향, 장황함 편향, 자기 선호 편향, LLM이 쓴 글을 선호하는 편향이 있어서 교차 모델 판정과 순서 무작위화가 필요합니다.

### Cited Findings
- **SAFE (Search-Augmented Factuality Evaluator)**: Wei, Yang 외(Google DeepMind), arXiv 2024-03-27, NeurIPS 2024. LLM이 긴 응답을 개별 사실로 나누고, 사실마다 Google Search 질의를 여러 단계 추론으로 보내 뒷받침 여부를 판정합니다. 약 16k개 사실에서 "SAFE agrees with crowdsourced human annotators 72% of the time"이었고, 불일치 100건 표본에서 "SAFE wins 76% of the time"이었으며, "more than 20 times cheaper than human annotators"입니다. 벤치마크 LongFact는 38개 주제의 질문 수천 개이고, 지표 F1@K는 정밀도(지지된 사실 비율)와 선호 길이 기준 재현율을 결합합니다. — [arXiv:2403.18802](https://arxiv.org/abs/2403.18802)
- **FActScore**: Min 외, EMNLP 2023. 생성문을 원자적 사실로 쪼개 신뢰할 수 있는 지식원이 뒷받침하는 비율을 계산합니다. 자동 추정기의 오차율은 "less than a 2%"이고, 전기(biography) 생성에서 ChatGPT는 "only achieves 58%"였습니다. 6,500개 생성물을 사람이 평가하면 약 $26K가 든다고 추산했습니다. — [arXiv:2305.14251](https://arxiv.org/abs/2305.14251)
- **G-Eval**: Liu 외(Microsoft), arXiv 2023-03-29. CoT와 form-filling 방식의 LLM 평가입니다. GPT-4 기반으로 요약 과제에서 사람과 "Spearman correlation of 0.514"를 기록해 기존 방법들을 앞섰습니다. 저자들은 "LLM-based evaluators having a bias towards the LLM-generated texts"를 경고합니다. — [arXiv:2303.16634](https://arxiv.org/abs/2303.16634)
- **MT-Bench / LLM-as-a-Judge**: Zheng 외(LMSYS), NeurIPS 2023 Datasets & Benchmarks. 강한 LLM 심사자(GPT-4)는 사람과 "over 80% agreement, the same level of agreement between humans"였습니다. 확인된 편향은 position bias, verbosity bias, self-enhancement bias, 그리고 limited reasoning입니다. — [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)
- **Google의 AI 콘텐츠 검수 권고**(페이지 갱신 2026-10-01): 생성 모델은 사실을 꺼내오는 게 아니라 다음 단어를 예측하므로 hallucination이 생길 수 있습니다. 그래서 발행 전에 본문뿐 아니라 **title, meta description, structured data, image alt text**까지 fact-check하고 검토하라고 권합니다. 구조화 데이터는 검증 도구로 확인해야 합니다. — [Google Search Central: Using generative AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)

### Inferences
- **추천 게이트 구성(순서대로, 실패하면 사람 승인 큐로 사유와 함께 넘김)**
  1. **주장 추출과 검증(SAFE/FActScore식)**: 대본이나 글에서 수치, 날짜, 고유명사가 들어간 원자적 주장을 뽑습니다. 각 주장에 대해 (a) 기획 단계에서 모은 출처 문서 안에서 근거 구절을 찾고(citation grounding), (b) 근거가 없으면 웹 검색으로 확인합니다. 지표는 "지지됨 / 반박됨 / 확인 불가" 비율로 둡니다. "반박됨"이 하나라도 있거나 "확인 불가"가 일정 비율을 넘으면 차단합니다.
  2. **인용 무결성**: 인용한 URL이 살아 있는지 확인하고, 인용문이 원문에 그대로 있는지 문자열이나 퍼지 매칭으로 봅니다. 날짜와 수치는 출처와 정확히 일치해야 합니다.
  3. **LLM 루브릭 심사(G-Eval식)**: 정확성, 독창적 관점(YouTube "inauthentic content" 대응), 훅, 구조, 브랜드 보이스를 1~5점으로 매기고 근거 문장을 함께 내게 합니다. 편향을 줄이려고 생성 모델과 다른 계열 모델을 심사자로 쓰고, A/B 비교는 순서를 바꿔 두 번 돌리며, 길이 정규화도 합니다(MT-Bench 편향 결과에 근거한 추론).
  4. **중복과 대량생산 탐지**: 내 채널 과거 산출물과 임베딩 유사도 및 n-gram 중복을 비교합니다. "템플릿 반복" 신호(같은 구조와 같은 결말)를 측정해 Q4의 YouTube inauthentic content 기준과 Google scaled content abuse 기준에 대비합니다. 외부 표절은 웹 검색 기반 근사 중복 검사로 봅니다.
  5. **가독성**: 한국어는 문장 길이와 어휘 난이도 같은 휴리스틱을 쓰고, 영어는 Flesch 계열 지표를 씁니다.
  6. **TTS 발음**: 생성한 음성을 ASR로 다시 받아쓰게 한 뒤 원고와 비교한 WER/CER, 그리고 고유명사·숫자·영문 약어 사전 대조로 봅니다.
  7. **자막 싱크**: 강제 정렬(forced alignment)로 단어 타임스탬프를 뽑아 자막 큐와의 오프셋 허용치(예: ±200ms)와 줄당 글자 수 및 표시 시간 규칙을 검사합니다.
  8. **메타데이터 검사**: 제목, 설명, 태그, alt text에도 1번 검증을 똑같이 적용합니다(Google 권고).
- SAFE의 72% 일치율을 보면 자동 사실 검증은 "사람 승인 대체"가 아니라 **"사람이 볼 곳을 좁혀주는 필터"**로 써야 합니다.

### Gaps
- 4~7번(표절, 가독성, TTS 발음, 자막 싱크)은 이번 세션에서 논문이나 벤더 문서 같은 출처를 확보하지 못했습니다. 위 내용은 설계 제안(추론)입니다. 특히 한국어 가독성 지표의 표준과 상용 표절 검사 API(Copyleaks, Turnitin 등)의 한국어 지원·요금은 따로 확인해야 합니다.
- 브랜드 보이스 자동 평가의 검증된 벤치마크나 방법론은 찾지 못했습니다.
- 2025~2026년의 최신 사실성 평가(SAFE 후속, 다국어·한국어 사실성 벤치마크)는 조사하지 못했습니다.

---

## Q4. 플랫폼 정책과 법: AI 자동화 콘텐츠를 제약하는 규칙 (날짜·원문 중심)

### Takeaway
YouTube는 2025-07-15에 "repetitious content"를 "**inauthentic content**"로 이름을 바꿨고, 2026-07-16에는 수익화 불가 유형을 세 가지(템플릿·반복형, 자극·조작형, 민감 주제의 AI 페르소나)로 명확히 했습니다. AI 사용 자체가 아니라 "대량생산 느낌"과 "변형 부족"이 판단 기준입니다. Google 검색은 "**scaled content abuse**"로 AI 대량 페이지를 겨냥하고, site reputation 수동 조치는 2026-08-30부터 EEA에서 적용하지 않습니다. 한국 AI 기본법(2026-01-22 시행)의 표시 의무는 **AI 서비스를 제공하는 '인공지능사업자'**에게 있고, AI 결과물로 자기 콘텐츠를 만드는 유튜버나 블로거는 원칙적으로 "이용자"입니다. 다만 자동화 에이전트를 **서비스로 외부에 제공하면** 이용사업자로서 의무를 질 수 있습니다. AI만으로 만든 결과물은 미국과 한국 모두 저작권 보호를 받지 못하고, 사람의 창작적 기여 부분만 보호됩니다.

### Cited Findings

**YouTube: 수익화 (YPP)**
- 2025-07-15 업데이트에서 반복적이거나 대량생산된 콘텐츠를 다룬다는 점을 명확히 했습니다. 원문: "We are also renaming this policy from 'repetitious content' to 'inauthentic content.'" 이런 콘텐츠는 이전에도 수익화 대상이 아니었고, "There is no change to our reused content policy." — [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en)
- 수익화할 수 없는 예시(원문):
  - "Similar or repetitive content with low educational value, commentary, narratives, or minimal variation across videos"
  - "Image slideshows, templated storylines, or scrolling text with minimal or no narrative, commentary, or educational value"
  - "**AI-generated content made with generic or unoriginal templates giving the impression of mass production**"
  - 같은 상황과 같은 결말을 반복하는 캐릭터 스토리 템플릿
  - 허용되는 예: 같은 인트로와 아웃트로를 쓰되 본문은 영상마다 다른 경우
  - — [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en)
- Reused content의 수익화 불가 예시: "Content that exclusively features readings of other materials you did not originally create", "Content that gets views from mostly non-verbal reactions ... without added voice commentary". 원저작자 허락이 있어도 최소한의 변경만 하면 위반입니다. 심사자는 채널 주제, 조회수 상위 영상과 최신 영상, 시청 시간 비중, 메타데이터, About 섹션을 봅니다. — [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en)
- **2026-07-16 명확화**: YouTube Trust & Safety 책임자 Matt Halprin이 Creator Insider에서 발표했고, 모든 YPP 회원에게 적용됩니다. 수익화 불가 유형은 세 가지입니다.
  - (1) generic/repetitive/template-based content: AI, CGI, 템플릿으로 쉽게 만들고 영상 간 변형이 적은 것. 플랫폼에 이미 흔한 튜토리얼을 재생산한 것도 포함
  - (2) off-putting/distressing content: 조회수를 노린 감정 조작형. 예: 고통받는 동물을 구조하는 연출
  - (3) **AI personas discussing sensitive topics**: 실존 인물의 AI 재현으로 금융, 법률, 건강·의료를 다루는 것
  - Halprin은 AI가 "enhances creativity"라고 말했고, 문제 삼는 것은 content farming이라고 했습니다. off-putting 콘텐츠 전용 채널은 YPP에서 제외되며, 세 유형이 "too much"인 채널은 수익화가 막힙니다("too much"의 기준은 밝히지 않음).
  - — [TechCrunch, 2026-07-20](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/); [Android Headlines, 2026-07](https://www.androidheadlines.com/2026/07/youtube-monetization-rules-ai-slop-inauthentic-content.html)
- 집행이 영상 단위가 아니라 채널 단위이고 최근 30개 업로드의 패턴을 본다는 주장은 단일 논평 기사에서만 나왔고 YouTube가 확인하지 않았습니다. — [HackerNoon](https://hackernoon.com/youtubes-ai-slop-crackdown-cant-tell-a-directed-ai-film-from-a-bot-farm) (검색 요약 기준)

**YouTube: 변경·합성 콘텐츠 공개 (altered or synthetic content)**
- 실존 인물, 사건, 장소, 장면을 바꾸거나 새로 만든 **사실적인** GenAI 콘텐츠, 그리고 음악이 주가 되는 AI 콘텐츠는 업로드할 때 "AI use" 설정으로 공개해야 합니다. 예: 실존 테니스 선수 두 명의 사실적인 AI 경기 영상, 실존 인물이 체포된 것처럼 보이게 만든 영상 — [YouTube Help: Disclosing altered or synthetic content](https://support.google.com/youtube/answer/14328491?hl=en)
- **공개하지 않아도 되는 것**: 비사실적 콘텐츠(판타지), 미적 보정(뷰티 필터, 색 보정, 배경 흐림, 자막, 업스케일링), **자기 목소리를 복제한 보이스오버**, 그리고 제작 보조(AI로 대본, 제목, 썸네일 초안 작성) — [YouTube Help](https://support.google.com/youtube/answer/14328491?hl=en)
- 라벨 위치: AI 음악이나 실사 같은 AI 콘텐츠는 **플레이어 위**, 음악이 아닌 AI 오디오나 비실사·애니메이션 AI 콘텐츠는 **확장 설명란**입니다. 공개만으로는 노출이나 수익화 자격에 영향이 없습니다. 반복해서 공개하지 않으면 수동 라벨, 콘텐츠 삭제, **YPP 정지**가 따를 수 있습니다. — [YouTube Help](https://support.google.com/youtube/answer/14328491?hl=en)
- YouTube는 자사 GenAI 도구로 만든 콘텐츠, **C2PA 메타데이터가 있는 콘텐츠**, 자체 시스템이 탐지한 콘텐츠에 **자동 라벨**을 붙일 수 있습니다. 자사 도구, C2PA, 수동 검토로 붙은 라벨은 크리에이터가 "No"로 되돌릴 수 없습니다. 페이지에 날짜 표기는 없습니다(©2026). — [YouTube Help](https://support.google.com/youtube/answer/14328491?hl=en)

**Google 검색 (페이지 갱신 2026-08-28)**
- **Scaled content abuse**: "Scaled content abuse is when many pages are generated for the primary purpose of manipulating search rankings and not helping users." 예시: "Using generative AI tools or other similar tools to generate many pages without adding value for users", "Creating many pages where the content makes little or no sense to a reader but contains search keywords". 스팸의 정의에 "generative AI responses in Google Search"를 조작하려는 시도도 들어갔습니다. — [Google Search Central: Spam policies](https://developers.google.com/search/docs/essentials/spam-policies)
- 이 섹션의 현재 명칭은 "Site reputation policy"입니다(예전 "site reputation abuse"). 원문: "applies where third-party content is published on a host site mainly because of that host's already-established ranking signals, which it has earned primarily from its first-party content." — [Google Search Central: Spam policies](https://developers.google.com/search/docs/essentials/spam-policies)
- **EEA 예외(2026-08-28 발표, 2026-08-30 시행)**: site reputation 정책에 따른 수동 조치는 EU 27개국, 아이슬란드, 노르웨이, 리히텐슈타인 사용자에게 순위 하락을 적용하지 않습니다. 해당 섹션은 시스템에서 분리되어 독립적으로 순위가 매겨질 수 있습니다. Search Console 알림과 재검토 요청은 그대로 유지됩니다. DMA 관련 EU 집행위원회 협의 이후 나온 조치입니다. — [Search Engine Land](https://searchengineland.com/google-wont-respect-manual-actions-for-site-reputation-abuse-in-european-economic-area-486055); [Search Engine Roundtable](https://www.seroundtable.com/google-site-reputation-abuse-eea-41968.html)
- **AI 콘텐츠 가이드**(페이지 갱신 2026-10-01): AI는 리서치와 구조화에 도움이 될 수 있지만 가치 없이 대량 생성하면 scaled content abuse가 될 수 있습니다. 콘텐츠를 어떻게 만들었는지(자동화 사용 여부 등) 독자에게 알리는 것을 고려하라고 권합니다. Merchant Center는 AI 생성 이미지에 IPTC `DigitalSourceType` = `TrainedAlgorithmicMedia`를 요구하고, AI 생성 상품 제목·설명은 따로 지정하고 라벨을 붙여야 합니다. 평가자 가이드라인 4.6.5와 4.6.6을 참조하라고 하지만 평가자 평가는 "don't directly influence ranking". — [Google Search Central: Using generative AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)

**Naver**
- 2026-07-24 MTN 보도에 따르면, 네이버는 5월에 블로그, 카페, 네이버 TV, 클립에 "AI 활용" 기능을 적용한다고 공지했습니다. 아이콘의 의미는 "AI 기술을 활용해 생성되거나 편집된 콘텐츠가 포함된 것"입니다. 블로그 등 일반 콘텐츠에서는 **권장일 뿐 의무가 아니며, 표기하지 않아도 게시물 제한 같은 제재는 없습니다**. 반면 **쇼핑 광고는 표기가 의무**이고, 위반하면 클린 프로그램에 따라 쇼핑 검색 제외 같은 제재가 가능합니다. 의료기기, 건강기능식품, 유아식품, 신선식품, 의약외품, 위험 화학물질, 반려동물 건강, 이미용 가전 분야는 AI 활용 자체가 제한됩니다. — [MTN, 2026-07-24](https://news.mtn.co.kr/news-detail/2026072417015682342)
- 네이버가 블로그의 AI 생성 글을 검색 노출에서 제한한다는 **공식 정책은 찾지 못했습니다**. 일부 마케팅 자료가 내세우는 "노출 70% 이상 감소" 같은 수치는 출처를 확인할 수 없습니다. — [검색 결과 종합: tilnote, inblog 등](https://inblog.ai/ko/glossary/naver-seo) (2차 출처, 신뢰도 낮음)

**한국 AI 기본법 (「인공지능 발전과 신뢰 기반 조성 등에 관한 기본법」)**
- 시행일은 **2026-01-22**입니다. 시행령 제정안은 2025-11-12에 입법예고되었고, 과태료 적용 전 **최소 1년의 계도기간**을 둡니다. 과기정통부는 유예기간을 더 늘릴 수 있다고 밝혔습니다. — [대륜 뉴스레터](https://www.daeryunlaw.com/newsletter/news/246); [다음/뉴스, 2025-11-12](https://v.daum.net/v/20251112120151444)
- 제31조는 세 가지 의무를 둡니다. (1항) 고영향 AI 또는 생성형 AI 기반 제품·서비스의 **사전 고지**, (2항) 생성형 AI 결과물의 **생성 사실 표시**, (3항) **딥페이크** 결과물을 이용자가 명확히 인식할 수 있게 고지하거나 표시. 의무를 지는 쪽은 "인공지능사업자"로, 개발사업자와 이용사업자로 나뉩니다(제2조 제7호). 국외 행위도 국내에 영향을 미치면 적용될 수 있습니다(제4조). — [법무법인 세종(Shin & Kim) 뉴스레터, 2026-02-26](https://shinkim.com/kor/media/newsletter/3142)
- 「인공지능 투명성 확보 가이드라인」의 표시 방법:
  - 결과물 표시는 사람이 인식할 수 있는 방식이나 기계가 판독할 수 있는 방식 중 하나로 합니다. 기계 판독 방식(메타데이터, 비가시 워터마크)을 쓰면 다운로드할 때 **최소 1회 문구나 음성으로 안내**해야 합니다.
  - 외부로 반출할 때(다운로드, 공유) 결과물 자체에 표시하는 방법: 텍스트는 머리말이나 파일 메타데이터, 이미지는 로고나 워터마크·메타데이터, 영상은 화면 로고나 시작 부분 안내 또는 워터마크·메타데이터, 음성은 시작 멘트나 음성 워터마크
  - **딥페이크에는 기계 판독 방식을 쓸 수 없고, AI로 생성한 재생 구간 전체에 로고 등을 표시**해야 합니다. 예술적·창의적 표현물은 감상을 방해하지 않는 방식(시간적으로 떨어뜨리거나 비가시적 방식)이 허용됩니다.
  - — [법무법인 세종 뉴스레터, 2026-02-26](https://shinkim.com/kor/media/newsletter/3142)
- **의무 주체 해석**: "단순히 인공지능 생성 결과물을 활용하여 자신의 콘텐츠를 제작·제공하는 경우에는 인공지능사업자에 해당하지 않고 이용자로 분류". 예: Sora로 영상을 만드는 유튜버 — [법무법인 세종 뉴스레터](https://shinkim.com/kor/media/newsletter/3142). 과기정통부의 2026-01-21 발표 내용을 전한 보도도 같은 해석입니다. 개인이 ChatGPT나 Gemini로 만든 웹툰을 연재할 때는 수익이 있어도 표시 의무가 없고, 편집 중 워터마크를 지워도 AI 기본법 위반이 아닙니다. 다만 합성물 악용은 성폭력처벌법이나 정보통신망법 같은 기존 법으로 따로 판단합니다. 그림이나 애니메이션처럼 실제와 쉽게 구별되는 결과물은 비가시 표시도 허용되고, 반출할 때 팝업 등으로 1회 알리면 의무를 이행한 것으로 봅니다. — [뉴스1 via 다음, 2026-01-21](https://v.daum.net/v/20260121120209717)
- 과태료: 제31조 제1항을 위반하면 제43조에 따라 **3천만 원 이하**라는 블로그 요약이 있습니다(조문 원문은 확인하지 못함). — [help-me.kr Korea AI Act 2026 compliance guide](https://www.help-me.kr/blog/article/korea-ai-act-2026-compliance-guide/) (2차 출처). 보도에 따르면 시행령 제정안에도 위반 시 최대 3천만 원 과태료가 들어 있습니다. — [다음/뉴스, 2025-11-12](https://v.daum.net/v/20251112120151444)
- 2026-10-20 현재 상태: 계도기간 중이며 제도 개선 논의가 진행 중입니다. 가시 워터마크는 쉽게 지울 수 있어 실효성이 낮다는 비판이 있고, 업계는 비가시 워터마크·메타데이터와 플랫폼 탐지·표시 방식으로 가야 한다는 데 대체로 동의합니다. C2PA와 비가시 워터마크를 결합하자는 제안도 나왔습니다. 유포자에게도 표시 의무를 지울지, 범위를 고위험 분야로 한정할지 전반으로 할지는 사회적 합의가 필요한 쟁점으로 남아 있습니다. 플랫폼의 워터마크 제거를 직접 제재할 근거가 없어 정보통신망법 개정안이 발의되어 있습니다. — [ZDNet Korea, 2026-10-20](https://zdnet.co.kr/view?no=20261020095628); [법무법인 세종 뉴스레터](https://shinkim.com/kor/media/newsletter/3142)

**저작권 (미국·한국)**
- 미국 저작권청 보고서 「Copyright and Artificial Intelligence」: Part 1 Digital Replicas(2024-07-31), **Part 2 Copyrightability(2025-01-29)**, Part 3 Generative AI Training(사전 공개판 2025-05-09, 최종판에서 실질적 변경은 없을 것으로 예상). 등록 가이던스는 88 Fed. Reg. 16,190(2023-03-16)입니다. 2026년 업데이트는 페이지에 없습니다. — [U.S. Copyright Office: Copyright and AI](https://www.copyright.gov/ai/)
- Part 2의 결론(2차 요약): 현재 일반적으로 쓸 수 있는 기술에서는 **프롬프트만으로 저작자가 될 만큼의 통제력을 주지 못합니다**. 프롬프트는 보호되지 않는 아이디어를 전하는 지시에 가깝습니다. 출력물 안에서 지각할 수 있는 사람의 표현, 창작적인 선택·조정·배열, 출력물을 창작적으로 수정한 부분은 보호될 수 있고 판단은 사안별로 합니다. 새 입법이나 sui generis 보호는 필요하지 않다고 봤고, 의견서는 10,000건 이상이었습니다. — [IPWatchdog, 2025-01-29](https://ipwatchdog.com/2025/01/29/part-two-copyright-office-ai-report-says-creative-prompting-doesnt-constitute-authorship/); [Baker Botts](https://ourtake.bakerbotts.com/post/102jxrk/copyright-office-releases-part-2-of-artificial-intelligence-report)
- 한국: 한국저작권위원회는 문체부와 함께 「생성형 AI 활용 저작물 등록 안내서」, 분쟁 예방 가이드, AI 학습 공정이용 판단 기준 안내서를 마련했습니다. 원문 표현은 "AI만으로 생성된 결과물은 저작물이 아니라 산출물로 보지만", 사람의 창작적 기여가 들어간 부분에는 저작권이 인정됩니다. AI로 만든 뒤 일부만 고쳐 등록하는 이른바 '딸깍 출판'이 늘었고, 저작권 등록은 30% 이상 늘었습니다(강석원 위원장). — [동아일보 via 다음, 2026-04-21](https://v.daum.net/v/20260421144511956)
- 등록을 신청할 때는 AI 산출물과 사람의 창작 부분을 명확히 나눠 적어야 하고, 허위로 적으면 처벌받을 수 있습니다. 예: 만화의 글은 사람이, 그림은 AI가 만들었다면 글 부분만 등록할 수 있습니다. 등록 심사는 형식 심사여서 명백히 저작물이 아닌 경우만 거절합니다. — [ditoday](https://ditoday.com/gai-copyright/); [isplus](https://isplus.com/article/view/isp202509010284) (검색 요약 기준이며 문장별 출처 매칭은 불확실)

### Inferences
- **자동화 파이프라인 설계에 주는 함의**
  - YouTube에서 위험한 것은 "AI 사용"이 아니라 "템플릿 반복"입니다. Q3의 중복·템플릿 탐지 게이트로 영상 사이의 구조적 변형(관점, 자체 해설, 고유 데이터)을 수치로 관리해야 합니다.
  - 2026-07-16 명확화에 따라 **금융, 법률, 의료 주제에서 실존 인물을 AI로 재현한 진행자(아바타)는 피해야** 합니다. 이 주제들은 사용자의 AI 뉴스나 해설 채널과도 겹칩니다.
  - AI 내레이션이 자기 목소리 복제라면 공개 대상이 아닙니다. 그러나 실존 인물의 사실적 합성이나 사실적인 가상 장면을 만들면 "AI use = Yes"로 표시해야 합니다. C2PA 메타데이터가 있는 생성 소재를 쓰면 자동 라벨이 붙고 되돌릴 수 없으므로, 업로드 전에 메타데이터를 점검하는 단계를 둡니다.
- **AI 기본법 측면**
  - 1인 크리에이터가 자기 채널에 올리는 용도라면 원칙적으로 "이용자"입니다.
  - 그러나 이 에이전트를 **다른 사람에게 서비스로 제공하면(SaaS, 대행)** "이용사업자"가 되어 제31조 표시 의무가 생길 가능성이 높습니다. 그렇다면 다운로드 산출물에 메타데이터나 워터마크를 넣고 1회 안내하는 기능을 설계 단계에서 넣어야 합니다.
  - 계도기간은 최소 1년이므로 2027-01 이후 과태료 집행 가능성을 염두에 둡니다. 이는 시행일과 최소 1년 계도기간에서 계산한 추정입니다.
- **저작권 측면**: 순수 AI 산출물(완전 자동 생성 대본, 이미지)은 미국과 한국 모두 보호받기 어렵습니다. 따라서 사람의 편집·선택·배열 기록(버전 기록, 승인 로그)을 남겨 두면 권리 주장과 등록 시 구분 기재에 유리합니다.
- **Google과 Naver 블로그 측면**: Google은 "가치 없는 대량 생성"을 문제 삼습니다. 발행 빈도에 상한을 두고, 페이지마다 고유 데이터나 관점이 있어야 한다는 게이트가 필요합니다. Naver는 AI 표기가 권장 사항이므로 브랜드 신뢰 차원에서 "AI 활용" 표기를 기본으로 켜는 것을 고려할 수 있습니다.

### Gaps
- **YouTube YPP 개편설**(2026-08-10 발표, 2027-02-01 시행, AIR Media-Tech 타임라인): 다른 출처로 확인되지 않았습니다. — [AIR Media-Tech](https://air.io/en/monetization/youtube-monetization-policy-changes-2026-a-complete-dated-timeline) (미검증)
- **YouTube Shorts 전용 정책**(Shorts YPP 기준 같은 수치, Shorts 재사용 콘텐츠 규칙): 이번 세션에서 1차 출처를 확인하지 못했습니다. 기존 지식(미검증)으로는 YPP 기준이 1,000 구독자 + 12개월 4,000 시청시간 또는 90일 Shorts 1,000만 조회입니다.
- 2026-07-16 명확화를 YouTube 1차 문서(Help Center 정책 문구)에서 직접 확인하지 못했습니다. YPP 정책 페이지는 2025-07-15 갱신 내용까지만 보여줬습니다.
- **Naver 블로그 운영정책의 '어뷰징' 조항 원문**(자동화 프로그램 이용, 반복 게시, 키워드 남용)과 서치어드바이저 웹문서 품질 기준(C-Rank, D.I.A.): 공식 원문을 확보하지 못했습니다.
- **AI 기본법 제31조·제43조 조문 원문과 시행령 최종 문구**(법제처): 직접 확인하지 못해 로펌 뉴스레터와 보도 기준으로 정리했습니다. 2026-01 시행 이후 계도기간 연장 결정이 있었는지도 확인하지 못했습니다.
- **한국 음악 분야**: 음저협이 인간 기여 기준의 신탁 등록 방침을 냈다가 철회했다는 2026-09 보도는 정확한 기사 출처를 확인하지 못했습니다.
- **US Copyright Office Part 2 원문 인용**: 이번에는 2차 요약만 확인했고, 보고서 PDF의 원문 문장은 확인하지 못했습니다.
