# HeoBrain 콘텐츠 자동화: 이미지·영상·썸네일·모션 도구 비교

조사일: 2026-10-28 KST. 공식 제품 문서·공식 저장소·공식 약관을 열람한 조사다. 작성 담당 범위는 이미지, 영상 생성, 썸네일, 모션, 코드 기반 렌더링이다. 음성·글쓰기·발행·쿠폰은 상위 통합 문서에서 연결한다.

## 1. 현재 구현·검증 상태

| 구분 | 상태 |
|---|---|
| 현재 구현 | 이 조사 문서만 작성했다. HeoBrain 코드·계정·API 키·결제·배포 설정은 변경하지 않았다. |
| 이번에 검증 완료 | 아래의 공식 모델명·API 제공 문서·공개 요금·라이선스 조건을 확인했다. 공식 웹사이트가 주장하는 성능과 자체 실측을 구분했다. |
| 계획/제안 | 기존 템플릿을 재사용하고 이미지 API 1개, 영상 API 1개, 렌더러 1개를 기본으로 시작하는 구조를 제안한다. |
| 미구현/차단 | 유료 생성·실제 한국어 글자 정확도·대기시간·성공률·계정별 사용 가능 여부·인증 연결·실제 영상 렌더는 시험하지 않았다. Kling 1차 API 문서 접근은 robots 제한으로 확인하지 못했다. |

## 2. 선택 결론

1. **이미지 기본:** Google Nano Banana 2.1을 후보 기본값으로 둔다. 일반 일러스트·대표 이미지·편집을 한 API로 묶을 수 있다. 정확한 한글 제목·가격·수치·출처는 생성 이미지에 맡기지 않고 HTML/SVG 텍스트 레이어로 합성한다. 한국어 품질 우위는 실측 후 결정한다.
2. **영상 기본:** 설명형 콘텐츠의 대부분은 실제 제품 데모·차트·키네틱 타이포그래피·정지 이미지 모션으로 만든다. 유료 생성 영상은 핵심 장면에만 사용한다. Runway Gen-4.5와 Gen-4 Turbo를 같은 제공자 안의 품질/비용 후보로 둔다.
3. **특수 장면 후보:** Kling 4.0은 긴 동작·카메라 움직임 후보, Luma Ray 3.2는 키프레임·편집·리프레이밍 후보로 둔다. 자체 비교 실험 전에는 이 제품들이 HeoBrain 영상에서 더 좋다고 확정하지 않는다.
4. **Midjourney:** 수동 아트디렉션·스타일 탐색 단계로 분리한다. 공식 약관은 자동화 도구에 의한 접근·상호작용·생성을 금지한다. 브라우저 봇이나 비공식 Midjourney API를 무인 파이프라인에 넣지 않는다.
5. **렌더러:** 기존 Remotion 템플릿이 있으면 유지한다. 새 HTML 장면은 HyperFrames를 작은 실험으로 비교한다. 두 렌더러를 모든 영상에 강제로 직렬 연결하지 않는다. FFmpeg는 공통 후처리로 사용한다.
6. **썸네일:** AutoKliq는 공식 MCP/토큰 연결 후보다. 처음에는 콘셉트 검토 후 선택한 썸네일만 렌더하며, 게시와 크레딧 사용은 별도 승인·예산으로 관리한다.

이 목록은 문서에 근거한 설계 제안이다. 실제 연결된 서비스나 현재 운영 중인 HeoBrain 기능을 뜻하지 않는다.

## 3. 이미지·영상 생성 비교

| 도구 | 확인한 모델·자동화 경로 | 규격·운영 범위 | HeoBrain 적용 판단 | 근거 |
|---|---|---|---|---|
| Midjourney | 공식 웹/Discord 제작. 공개 무인 API는 이번에 확인하지 못했으며 약관상 자동화 접근 금지 | 이미지→영상 기본 5초, 4초씩 연장해 최대 21초. 16:9 HD 예시는 1280×720. 구독 등급별 모드 차이 | 썸네일 미술 방향·수동 대표 장면 후보. 자동 큐 기본 엔진에서 제외 | [약관](https://docs.midjourney.com/hc/en-us/articles/32083055291277-Terms-of-Service), [영상](https://docs.midjourney.com/hc/en-us/articles/37460773864589-Video) |
| Google Nano Banana | Gemini API. 2.1=`gemini-nano-banana-2.1`; Lite=`gemini-3.1-flash-lite-image`; Pro=`gemini-3-pro-image` | 2.1은 1K/2K/4K, Lite는 1K. 텍스트→이미지·대화형 편집. 구형 2.5를 새 설계에 고정하지 않음 | 범용 이미지 기본 후보. 최종 한글 자막·표·수치·출처는 별도 텍스트 레이어 | [이미지 문서](https://ai.google.dev/gemini-api/docs/image-generation), [요금](https://ai.google.dev/gemini-api/docs/pricing) |
| Runway | 공식 API의 `gen4.5`, `gen4_turbo` | 텍스트/이미지→영상 모델 제공. 모델별 길이·해상도는 생성 요청 직전 API 스키마로 검증. 이번 호출 시험 없음 | 영상 API 기본 후보. Turbo는 이미지 모션 실험, 4.5는 주요 장면 후보. 성공률·한국어는 미실측 | [모델](https://docs.dev.runwayml.com/guides/models/), [요금](https://docs.dev.runwayml.com/guides/pricing/) |
| Kling | Kuaishou 공식 4.0 출시 확인. Runway API에 `kling_4` 등재 | Runway 경로 4.0은 3~30초, 720p/1080p 및 이미지/영상 참조. 원 공급자 직접 API 문서는 접근 제한으로 미검증 | 움직임이 중요한 장면의 비교 후보. 1차 API와 Runway 경유의 가격·약관·키를 혼동하지 않음 | [출시 발표](https://ir.kuaishou.com/news-releases/news-release-details/kling-ai-officially-launches-next-generation-kling-40-raising), [Runway 경로](https://docs.dev.runwayml.com/guides/models/) |
| Google Veo | Google Cloud `veo-3.1-generate-001` 경로는 공식 GA 표에 존재. Gemini API의 Veo 3.1 Preview는 종료 안내 | Cloud 표: 4/6/8초, 참조 이미지 경로 8초; 9:16/16:9; 720p/1080p/4K. 프롬프트 영어. 지원 종료일은 2026-11-17 또는 이후로 기재 | 공급 경로별 수명을 분리. 새 Gemini 개발은 Omni 후보를 검토. Cloud Veo는 실제 계정 가용성과 지원 수명 재확인 | [Cloud Veo](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate?hl=en), [Gemini 종료 안내](https://ai.google.dev/gemini-api/docs/video) |
| Luma | Luma Agents API `ray-3.2`; 생성·편집·리프레이밍 | 일반 생성 5/10초, 540p/720p/1080p; HDR/EXR는 별도 제약. 제공 모델 문서에서 생성물 URL 1시간 만료 안내 | 키프레임·화면비 변환이 필요할 때 비교. URL만 저장하지 않고 완성 자산을 제때 보관해야 함 | [모델](https://docs.agents.lumalabs.ai/guides/model/), [요금](https://docs.agents.lumalabs.ai/guides/pricing/) |

### Google 모델 수명과 이름을 따로 관리

Google 이미지 문서는 Nano Banana 2.1을 신규 작업의 주력으로 안내한다. Gemini 요금 페이지는 `gemini-2.5-flash-image` 종료일을 2026-10-02로 명시한다. 기존 블로그·강의의 2.5 예제를 그대로 운영 설정에 복사하지 않는다. 서비스 이름과 실제 공급자별 모델 ID를 분리해 기록한다. [이미지 문서](https://ai.google.dev/gemini-api/docs/image-generation), [수명·요금](https://ai.google.dev/gemini-api/docs/pricing)

Veo 종료 안내는 **Gemini API의 Preview 경로**를 가리킨다. Google Cloud나 파트너 API 전체의 종료로 확대 해석하지 않는다. 반대로 Cloud 페이지에 모델이 있다는 이유만으로 현재 계정에서 즉시 사용 가능하다고 표시하지 않는다. [Gemini 안내](https://ai.google.dev/gemini-api/docs/video), [Cloud 표](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate?hl=en)

## 4. 모션·렌더링은 역할을 나눠 선택

| 도구 | 확인한 자동화 방식 | 라이선스·비용 | 적합한 장면 | 통합 주의 |
|---|---|---|---|---|
| HyperFrames | HTML/CSS와 시킹 가능한 애니메이션을 헤드리스 Chrome·FFmpeg로 렌더. CLI 제공, 문서 요구 Node.js 22+ 및 FFmpeg | 공식 저장소 Apache-2.0. 자체 렌더 횟수 요금 없음. 자산·폰트와 컴퓨팅 비용은 별도 | 설명 영상, 차트, 자막, 키네틱 타이포그래피, 제품 출시, 에이전트가 작성한 HTML 장면 | 사용자 표현 Hyperframe의 현재 공식 프로젝트는 HeyGen `heygen-com/hyperframes`. 기존 임의 동명 패키지와 구분. [공식 저장소](https://github.com/heygen-com/hyperframes) |
| Remotion | React 컴포넌트와 파라미터로 영상을 구성·렌더. 서버·Lambda 렌더 경로 제공 | Source-available Remotion License. 개인·정의상 3인 이하 조직 등 무료 자격 조건. 자격 밖은 Company License | 기존 React 템플릿·데이터 기반 대량 변형·제품 개인화 영상 | HeoBrain의 실제 조직 자격은 이번에 판단하지 않음. 기존 템플릿이 있으면 새 렌더러로 일괄 전환할 이유가 없음. [라이선스](https://raw.githubusercontent.com/remotion-dev/remotion/main/LICENSE.md), [요금](https://www.remotion.dev/docs/license/pricing) |
| FFmpeg | CLI·필터로 인코딩, 이어 붙이기, 리사이즈, 음량·자막 등 후처리 | 기본 LGPL 2.1+; 선택한 GPL 구성요소를 사용하면 FFmpeg 전체에 GPL 적용. 배포 빌드·연결 방식별 준수 필요 | 16:9/9:16 파생본, 코덱 정규화, 최종 음량·패키징 | 바이너리 배포 시 `ffmpeg -buildconf`와 라이선스 고지/소스 대응 기록. `--enable-gpl`·`--enable-nonfree`를 무조건 추가하지 않음. [공식 법적 안내](https://ffmpeg.org/legal.html) |
| Blender | GUI 없이 백그라운드 렌더와 Python 자동화 가능 | 프로그램 GPL. 직접 만든 렌더 이미지·영상·blend 파일의 이용과 프로그램 배포 라이선스는 구분됨 | 독자 3D 도해, 카메라·공간 설명, 재사용 가능한 브랜드 장면 | 외부 모델·텍스처·음원 권리는 별도. 저메모리 PC의 기본 뉴스 영상마다 3D를 돌리지는 않음. [라이선스](https://www.blender.org/about/license/), [CLI](https://docs.blender.org/manual/en/3.6/advanced/command_line/arguments.html) |

### 제안하는 공통 교환 형식

`승인된 대본/주장 → 장면 JSON → renderer 선택 → scene MP4/PNG → FFmpeg 최종 조립 → 검수 → 발행 승인`

- 기존 Remotion 자산은 React 경로, 신규 HTML 장면은 HyperFrames 경로로 만든다. 최종 파이프라인은 영상/이미지 자산과 타임라인 데이터로 이어 붙인다.
- HyperFrames가 만든 HTML을 무조건 Remotion으로 다시 렌더하는 변환 계층은 초기 범위에서 제외한다. 이중 시계·폰트·브라우저 상태를 관리할 비용이 추가된다.
- Blender는 독립 장면을 만든 뒤 PNG/영상으로 넘긴다. 무거운 3D 장면과 전체 영상 조립을 한 프로세스에 섞지 않는다.
- 16:9, 9:16, 1:1은 단순 중앙 크롭만 하지 않고 제목·핵심 도형·CTA를 화면비별 레이아웃으로 재배치한다.
- 초안은 낮은 해상도, 최종은 승인된 1080p 레이아웃부터 시작한다. 4K는 필요한 채널·장면만 따로 요청한다.

이 교환 형식과 운영 규칙은 제안이며, 이번 조사에서 구현·렌더 시험한 것은 아니다.

## 5. AutoKliq를 썸네일 단계에 붙이는 방법

AutoKliq 공식 약관은 자체 MCP 서버·개인 API 토큰을 통한 자동화를 허용한다. 공식 주소는 `https://mcp.autokliq.com`으로 안내된다. 일반 웹봇 접근과 공식 연결을 구분해야 한다. 현재 연결·토큰 생성·유튜브 권한 부여는 실행하지 않았다. [약관](https://autokliq.com/terms), [공식 소개](https://autokliq.com/)

권고 흐름은 `제목 후보 → 콘셉트 계획 → 사용자 선택 → 비용 견적 → 선택안 렌더 → 사실·텍스트·시인성 검수 → 별도 게시 승인`이다. 약관은 크레딧 소비를 사용자 승인 또는 연결별 자동 승인 예산 안에서만 실행하도록 규정한다. 자동 승인 예산을 설정하지 않은 상태에서 생성 호출을 진행하지 않는다. 썸네일을 실제 YouTube에 바꾸는 권한도 별도로 취급한다. 약관은 CTR·조회수 보장을 하지 않으므로, 예측 점수를 실제 성과로 보고하지 않는다. [약관](https://autokliq.com/terms)

현재 공개 요금: 무료 월 300크레딧/기본 10회 렌더, Core 월 $25/3,000크레딧, Pro 월 $49/6,000크레딧. 한 썸네일 기본 렌더는 30크레딧이며 다른 기능 사용량과 공유된다. 콘셉트 우선 검토로 불필요한 6개 일괄 렌더를 피한다. [공식 요금](https://autokliq.com/pricing)

## 6. 추가 대안 세 가지

| 후보 | 추가하는 이유 | 확인한 범위·제약 | 근거 |
|---|---|---|---|
| Gemini Omni Flash 1.1 | 새 Gemini 영상 API를 검토할 때 Veo Preview 대체 후보 | 모델 ID `gemini-omni-1.1-flash`. 영상 생성·대화형 편집·오디오 출력. 기본 720p, 1080p/4K는 업스케일로 명시. 공식 문서는 영어만 평가 완료, 다른 언어는 미평가라고 안내. 한국어 내레이션은 별도 TTS 트랙으로 검토 | [기능](https://ai.google.dev/gemini-api/docs/omni), [요금](https://ai.google.dev/gemini-api/docs/pricing) |
| Adobe Firefly API | 브랜드 참조·제품 합성·확장 워크플로 후보 | 공식 API 제공. 일반적인 상업 이용 허용과 특정 beta 예외를 확인해야 함. Adobe Express beta API와 Firefly API를 같은 권리·출시 상태로 묶지 않음. 계약 요금은 미확인 | [API](https://developer.adobe.com/firefly-services/docs/firefly-api/), [생성 AI 이용 가이드](https://www.adobe.com/cis_en/legal/licenses-terms/adobe-gen-ai-user-guidelines.html) |
| Recraft V4.1 Vector | 편집 가능한 SVG·아이콘·독자 도해 자산을 API로 확보 | API 모델 `recraftv4_1_vector`. API 생성 자산의 상업 이용/소유 조건은 개발자 약관으로 확인; 웹 무료·커뮤니티·MCP 자산 권리와 동일 취급하지 않음. API 출력의 AI 모델 학습 이용 제한·표식 보존 의무가 있음 | [API](https://www.recraft.ai/docs), [개발자 약관](https://www.recraft.ai/legal/developer-terms), [요금](https://www.recraft.ai/docs/api-reference/pricing) |

정확한 한글·표·출처·가격 표시가 목적이면 이미지 생성 대안보다 직접 만든 SVG/HTML 템플릿을 우선한다. 이는 새 외부 모델이 아니라 기존 웹 기술의 재사용 제안이다.

## 7. 비용 비교: 같은 단위로 계산

모든 값은 조사일의 공개 USD 표이며 세금·환율·입력 토큰·재시도·오디오·저장·네트워크·별도 렌더 컴퓨팅은 포함하지 않는다. 구독 크레딧과 API 크레딧은 같은 잔액이라고 가정하지 않는다. 공개 요금 확인과 실제 청구 검증은 다르다.

| 경로 | 확인한 단위 비용 | 비교 예시 | 근거 |
|---|---:|---:|---|
| Nano Banana 2.1 Standard | 1K 출력 $0.0336/장 | 10장 출력 $0.336 + 입력 등 | [Google](https://ai.google.dev/gemini-api/docs/pricing) |
| Nano Banana 2.1 Batch | 1K 출력 $0.0168/장 | 비동기 10장 출력 $0.168 + 입력 등 | [Google](https://ai.google.dev/gemini-api/docs/pricing) |
| Runway Gen-4.5 | $0.12/출력초 | 성공 출력 10초 $1.20 | [Runway](https://docs.dev.runwayml.com/guides/pricing/) |
| Runway Gen-4 Turbo | $0.05/출력초 | 성공 출력 10초 $0.50 | [Runway](https://docs.dev.runwayml.com/guides/pricing/) |
| Runway 경유 Veo 3.1 | 무음 $0.20/초, 오디오 $0.40/초 | 8초 무음 $1.60, 오디오 $3.20 | [Runway](https://docs.dev.runwayml.com/guides/pricing/) |
| Gemini Omni Flash 1.1 | 720p 출력 약 $0.10/초 + 입력 | 10초 약 $1.00 + 입력 등 | [Google](https://ai.google.dev/gemini-api/docs/pricing) |
| Kling 4.0 / Runway 경로 | 720p 정가 $0.157/초, 1080p $0.235/초(입력 영상 없는 경우) | 2026-11-30 UTC까지 20% 할인 표시. 영상 입력이 있으면 별도 산식 | [Runway](https://docs.dev.runwayml.com/guides/pricing/) |
| Luma Ray 3.2 | 720p SDR 5초 100크레딧, 10초 300크레딧 | 10초가 5초의 두 배 가격이라고 가정하지 않음. USD 환산/계약은 요청 전 확인 | [Luma](https://docs.agents.lumalabs.ai/guides/pricing/) |
| Recraft V4.1 Vector | 일반 벡터 $0.08/장 | 10장 $0.80 | [Recraft](https://www.recraft.ai/docs/api-reference/pricing) |
| Remotion 무료 자격 밖의 자동화 | $0.01/렌더, 월 최소 $100 | 자격/규모별 비용 검토. Creator 좌석은 월 $25/인 별도 유형 | [Remotion](https://www.remotion.dev/docs/license/pricing) |

계산 예시: 60초 쇼츠의 전 구간을 Runway Gen-4.5 생성 영상으로 구성하면 성공 출력만 $7.20이다. 실제 비용에는 버린 테이크와 이미지·음성·렌더가 더해진다. 반면 생성 장면을 일부에만 쓰고 나머지는 제품 데모·HTML/SVG 설명으로 구성하면 비용 통제가 쉬워진다. 이는 요금 산식의 예시이며 60초 단일 요청을 허용한다는 뜻이 아니다.

실제 운영은 `산정 비용 → 승인된 예산 → 제출 → 공급자 작업 ID 보관 → 상태 조회 → 다운로드 → 사용 크레딧 대조` 순서로 만든다. 실패 응답을 보고 무조건 같은 생성 요청을 다시 보내지 않는다. 공급자별 실패 과금·재시도 규칙을 먼저 확인한다.

## 8. 상업 자산·라이선스 기록에 필요한 차이

- **Midjourney:** 연 매출 $1M 초과 회사/그 직원은 자산 소유 조건상 Pro 또는 Mega 구독이 필요하다고 명시한다. 타인 이미지를 확대한 출력은 타인의 권리와 별개가 아니다. 조직 매출을 이번에 확인한 것은 아니다. [약관](https://docs.midjourney.com/hc/en-us/articles/32083055291277-Terms-of-Service)
- **Google Gemini:** Google이 생성물 소유권을 주장하지 않는다고 규정하지만, 제3자 권리·법 준수까지 보증하는 뜻은 아니다. 무료 서비스와 유료 API의 입력 데이터 처리 조건이 다르다. [API 추가 약관](https://ai.google.dev/gemini-api/terms)
- **Runway:** 약정·이용 정책 준수를 전제로 출력의 상업 이용을 제한하지 않는다고 안내한다. 제공자 내부의 외부 모델은 모델별 추가 조건을 다시 확인한다. [공식 상업 이용 안내](https://dev.runwayml.com/learn/commercial-use)
- **Luma:** 과거 Dream Machine 무료/구독 조건과 현재 Agents API 계약은 구분한다. API 약관은 AI 생성 표시 및 독립 서비스 재판매 등의 제약을 둔다. 결제 상품/계약이 확정되기 전에 구독 권리나 데이터 보존·학습 정책을 API 전체로 일반화하지 않는다. [API 약관](https://lumalabs.ai/legal/api-terms-of-use), [구독 권리 안내](https://lumalabs.ai/learning-hub/licensing)
- **AutoKliq:** 생성한 썸네일 사용은 허용되지만 입력 콘텐츠 권리는 사용자가 확보해야 한다. 공개 채널 참조를 그대로 복제해도 된다는 의미는 아니다. [약관](https://autokliq.com/terms)
- **Blender/FFmpeg/HyperFrames:** 도구 라이선스와 그 안에 넣는 외부 자산·폰트·음원·3D 모델 권리를 분리한다. 영상을 만든다는 이유로 입력 자산의 권리 상태가 바뀌지 않는다.
- **Remotion:** 무료/회사 라이선스 자격과 버전을 기록한다. 상용 렌더링을 한다는 이유만으로 항상 무료 또는 항상 유료라고 단정하지 않는다.

자산 기록에는 `provider`, `provider_model_id`, `model_version`, `request_id`, `input_asset_ids`, `prompt_hash`, `generated_at`, `license_url`, `license_snapshot_date`, `commercial_review`, `sha256`, `expected_text`, `cost_quote`, `actual_cost`, `human_review`를 남기는 것을 제안한다. 이 필드들은 이번에 실제 구현한 데이터베이스 스키마가 아니다.

## 9. 한국어와 채널 검수 설계

| 검수 대상 | 통과 기준 제안 | 이번 검증 상태 |
|---|---|---|
| 한글 제목/가격/숫자 | 승인 텍스트와 최종 레이어가 정확히 일치; 자막 잘림 없음 | 미실행 |
| 인물·제품 일관성 | 승인된 참조와 장면별 비교; 다른 사람·제품으로 바뀌지 않음 | 미실행 |
| 유튜브 썸네일 | 작은 화면에서 핵심 정보 식별; 사실 없는 성과 수치 금지 | 미실행 |
| 이미지→영상 | 손·물체 변형, 급격한 컷, 의미 없는 동작·프레임 뒤틀림 검수 | 미실행 |
| 실제 제품 데모 | 실제 최신 기능의 원본 화면과 조작 증빙 유지; 가짜 UI를 성공 증거로 쓰지 않음 | 미실행 |
| 채널 변형 | 16:9/9:16/1:1의 안전 여백·읽기 순서·CTA 확인 | 미실행 |
| 최종 인코딩 | 길이·해상도·프레임레이트·오디오·검은 프레임·자막 범위 확인 | 미실행 |
| 성과 실험 | CTR/시청 유지/전환을 분리; 같은 조건과 표본 수 명시 | 미실행 |

영상 모델의 한국어 지원 설명, 자체 광고 사례, 다른 사용자의 A/B 성과를 HeoBrain에서 재현된 성과처럼 적지 않는다. 공식 API에 모델이 있다는 사실도 현재 계정의 사용 가능성·완성 영상 품질·실제 배포를 증명하지 않는다.

## 10. 다른 모델에 넘길 때 확인할 질문

1. 기존 v5에 실제로 있는 렌더러·템플릿·자산 스키마는 무엇인가? 이 문서의 신규 도구를 추가하기 전에 재사용할 수 있는가?
2. 기본 이미지 10장, 동일한 짧은 장면 몇 개, 한글 자막을 같은 기준으로 평가할 수 있는가? 유료 실행과 평가용 자산 권리는 승인됐는가?
3. 무료 구독과 API 크레딧, API 모델 ID와 앱 제품명을 혼동한 설정이 없는가?
4. 모델 종료·변경 시 이미지 템플릿/기존 장면으로 안전하게 돌아갈 수 있는가? 자동으로 더 비싼 모델을 호출하지 않는가?
5. 썸네일·영상 생성 승인과 실제 채널 발행 승인, 쿠폰 발급 승인이 분리돼 있는가?
6. 출력 이미지·자막·원본 영상·자산 원장·요금 기록을 다른 렌더러와 모델에서도 읽을 수 있는가?

권고 운영 기본값은 유료 생성 자동 실행 꺼짐, 실제 발행 꺼짐, 승인된 작업 단위 비용 상한, 동시 렌더 1개다. 이 값들은 상위 프로젝트의 사용자 승인·기존 운영 정책과 맞춘 다음 설정해야 한다.
