# 도구·모델·자동화·권리 비교

2026-10-28 공식 자료 확인. 실제 생성 품질 비교·계정 접근·청구 검증은 미실행.

| 도구 | 역할/선택 | 연결 | 제약 | 비용 | 권리·공식 근거 |
| --- | --- | --- | --- | --- | --- |
| Midjourney | 이미지·영상 / 선택형 아트디렉션 | 수동 | 브랜드 분위기와 대표 장면을 사람이 탐색할 때 선택한다. 공식 약관은 자동화 도구에 의한 접근·생성을 금지한다. 비공식 API·브라우저 봇을 기본 엔진으로 넣지 않는다. | 구독·모드별 요금 확인 필요 | 입력 권리·구독 등급별 자산 조건 확인 [공식 근거](https://docs.midjourney.com/hc/en-us/articles/32083055291277-Terms-of-Service) |
| Nano Banana | 이미지 / 이미지 API 우선 후보 | 공식 API | 현재 문서상 Nano Banana 2.1을 범용 생성·편집 후보로 둔다. 정확한 한글·가격·수치는 별도 HTML/SVG로 합성한다. gemini-nano-banana-2.1과 Lite/Pro를 구분. 한국어 품질·계정 접근은 미실측. | 1K 표준 출력 $0.0336/장 + 입력 등 | API 약관·입력 권리·데이터 처리 조건 확인 [공식 근거](https://ai.google.dev/gemini-api/docs/image-generation) |
| Runway | 영상 / 생성 영상 기본 비교 후보 | 공식 API | Gen-4.5와 Gen-4 Turbo를 같은 제공자에서 품질·비용 후보로 비교한다. 설명 영상 전체를 생성 영상으로 채우지 않는다. 모델별 요청 규격·실패 과금·입력 권리는 제출 전 확인. 실제 생성 0회. | 4.5 $0.12/초, Turbo $0.05/초 | 모델별 추가 조건과 상업 이용 범위 확인 [공식 근거](https://docs.dev.runwayml.com/guides/models/) |
| Kling | 영상 / 동작 장면 비교 후보 | 공식 API·파트너 경로 | Kling 4.0의 동작·참조 장면을 통제된 샷 시험에서 비교한다. 원 공급자 직접 API와 Runway 경유의 계정·요금·권리를 분리한다. 한국어 품질 우위 미확인. | 경로·해상도·입력 영상·프로모션별 다름 | 원 공급자·경유 제공자 조건 확인 [공식 근거](https://ir.kuaishou.com/news-releases/news-release-details/kling-ai-officially-launches-next-generation-kling-40-raising) |
| Veo | 영상 / 기존 경로 수명 확인 후 선택 | 공급 경로별 확인 | Cloud의 Veo 3.1 GA 경로와 Gemini API의 Preview 종료를 구분한다. Cloud 문서의 지원 수명은 2026-11-17 또는 이후. 신규 Gemini 개발은 Omni 경로도 검토한다. | 공급 경로·오디오 포함 여부별 확인 | 공급자·모델별 상업 조건 확인 [공식 근거](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate?hl=en) |
| Luma | 영상 / 키프레임·리프레이밍 후보 | 공식 API | Ray 3.2의 생성·편집·화면비 변환이 필요한 장면에서 비교한다. 산출물 URL 만료와 원본 다운로드를 관리한다. 자체 실험 결과는 없다. | 크레딧·길이별 산식 확인 | API 계약과 입력 자산 조건 확인 [공식 근거](https://docs.agents.lumalabs.ai/guides/model/) |
| AutoKliq | 썸네일 / 콘셉트 검토 후 선택 제작 | 공식 MCP·API | 제목·약속·가독성이 다른 내부 5안에서 사람이 고른 후보만 제작한다. 크레딧 지출은 승인된 연결별 예산 안에서만. CTR·매출 보장 아님. 실제 연결 안 함. | 무료 월 300크레딧·기본 10렌더 표시; 유료 별도 | MCP/API 약관·입력 권리·지출 승인 [공식 근거](https://autokliq.com/terms) |
| Chatterbox | 음성 / 한국어 비교 실험 | 로컬 모델 | Multilingual V3를 비교하고 영어 전용 Turbo와 구분한다. 지원 언어와 실제 한국어 발음·연기 품질은 다르다. 현 PC 상주 모델로 기본 배치하지 않는다. | 오픈 모델 + 실행 자원·운영비 | MIT; 화자·입력 권리 별도 [공식 근거](https://github.com/resemble-ai/chatterbox) |
| Qwen | 음성 / Qwen3-TTS 계열로 정규화 | 정확한 모델 지정 필요 | 일반 Qwen LLM과 TTS 체크포인트를 분리한다. Qwen이라는 이름만으로 음성 모델 설정을 확정하지 않는다. | 선택 체크포인트·실행 환경별 다름 | 각 모델 카드 확인 [공식 근거](https://github.com/QwenLM/Qwen3-TTS) |
| Eleven v4 | 음성 / 감정·대화 후보 | 공식 API | eleven_v4의 Text to Dialogue 경로를 숏폼·표현 장면에서 비교한다. 장문 안정성·오독·화자 권리를 직접 검증한다. 무료 출력의 상업 권리를 가정하지 않는다. | 공개 API 표시 $0.08/1,000자; 계정 조건 별도 | 유료 상업 조건·복제 동의·서비스 조건 [공식 근거](https://elevenlabs.io/docs/overview/models) |
| Multilingual v2 | 음성 / 설명·교육 내레이션 기준선 | 공식 API | eleven_multilingual_v2를 긴 한국어 설명의 우선 비교 기준으로 둔다. 실제 청취·발음 사전·상품명·숫자 검수 전에는 출고 음질 합격으로 세지 않는다. | 공개 API 표시 $0.08/1,000자; 계정 조건 별도 | 유료 상업 조건·화자·입력 권리 [공식 근거](https://elevenlabs.io/docs/overview/models) |
| Qwen3-TTS | 음성 / 저비용 실험 우선 후보 | 로컬·공식 서비스 경로 | 0.6B CustomVoice/Sohee부터 중립 한국어 20문장으로 비교한다. Base·CustomVoice·VoiceDesign을 구분한다. 16GB PC에서 동시 AI 작업과 함께 상주시킬 수 있다고 보장하지 않는다. | 모델 실행 자원·API 경로별 비용 | 확인한 0.6B 모델 카드 Apache-2.0; 화자 권리 별도 [공식 근거](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice) |
| VoxCPM2 | 음성 / 별도 GPU 작업자 비교 후보 | 로컬·서빙 | 최신 2B·48kHz·다국어 모델을 통제된 환경에서 비교한다. 공식 비교표 VRAM 약 8GB. 이 PC의 공유 RAM을 전용 VRAM 8GB로 해석하지 않는다. | 오픈 모델 + GPU·운영비 | 코드·가중치 Apache-2.0 확인 [공식 근거](https://github.com/OpenBMB/VoxCPM) |
| Confucius4-TTS | 음성 / 다국어 비교 후보 | 로컬·서빙 | 공식 Youdao 저장소의 다국어·음색 변환 후보를 검토한다. 공식 모델 존재와 계정 실행·한국어 품질·처리량은 별도 상태다. | 오픈 모델 + 실행 자원 | 코드·공식 가중치 Apache-2.0 확인 [공식 근거](https://github.com/netease-youdao/Confucius4-TTS) |
| OpenVoice | 음성 / 권한 있는 화자 확장 | 로컬 모델 | OpenVoice V2의 음색 변환·교차 언어 파이프라인을 비교한다. 음성 복제는 원음·동의·매체·기간·철회 범위를 기록한 화자만. 관리형 TTS와 동일시하지 않는다. | 오픈 모델 + 실행 자원 | MIT·상업 사용 안내; 화자 권리 별도 [공식 근거](https://github.com/myshell-ai/OpenVoice) |
| Claude | 글쓰기 / Sonnet 초안·별도 검토 | 공식 API | Sonnet 5.5를 초안 우선 후보, Haiku를 구조화·태그, Opus를 어려운 검토의 선택 후보로 둔다. 현재 오피스 기본 제공자와 다르다. Claude 연결·한국어 품질·실제 원가·승자 검증은 아직 없다. | Sonnet5.5 입력/출력 $2/$10 per MTok; 고급 모델 별도 | Anthropic 약관·입력 범위·API 비용 확인 [공식 근거](https://platform.claude.com/docs/en/about-claude/models/overview) |
| Blender | 모션·렌더 / 필요한 3D 장면만 | 로컬 CLI | 카메라·공간·독자 3D 도해를 장면 자산으로 만든다. 뉴스 영상마다 무거운 3D 렌더를 돌리지 않는다. 외부 모델·텍스처·음원 권리는 따로 확인한다. | 소프트웨어 무료 + 렌더 자원 | 프로그램 GPL; 직접 만든 산출물과 별도 [공식 근거](https://www.blender.org/about/license/) |
| HyperFrames | 모션·렌더 / HTML 장면 선택 렌더 | 로컬 CLI | 시킹 가능한 HTML/CSS 장면을 헤드리스 Chrome·FFmpeg로 렌더한다. 사용자 입력 Hyperframe의 공식 프로젝트를 HyperFrames로 정규화. Remotion과 강제 직렬 연결하지 않는다. | 프레임워크 요금 없음 + 실행 자원 | Apache-2.0; 자산·폰트 권리 별도 [공식 근거](https://github.com/heygen-com/hyperframes) |
| FFmpeg | 모션·렌더 / 공통 조립·납품 | 로컬 CLI | 인코딩·화면비·자막·음량·썸네일·최종 파일 검사 경로를 재사용한다. QSV 목록 존재와 실제 가속·화질 검증은 다르다. 렌더러가 이미 만든 장면은 다시 생성하지 않는다. | 실행 자원·저장 비용 | LGPL 기본; GPL 옵션·nonfree 빌드의 재배포 조건 확인 [공식 근거](https://ffmpeg.org/legal.html) |
| Remotion | 모션·렌더 / React 템플릿 선택 렌더 | 로컬·서버 렌더 | React 기반 데이터 영상과 기존 템플릿이 있을 때 재사용한다. 현재 오피스에 연결됐다고 확인한 것은 아니다. 무료 자격과 조직별 상업 라이선스를 확인한다. | 무료 자격/회사 라이선스·렌더 자원별 다름 | Remotion License; 소규모 무료 자격·회사 조건 [공식 근거](https://www.remotion.dev/docs/license/pricing) |
| Upside | 발행 / 공식 URL 확인 후 결정 | 제품 식별 보류 | 사용자가 의도한 자동 업로드 제품의 정확한 주소를 받아 식별한다. 동명 서비스로 대신 연결하지 않는다. 현재 API·가격·상태를 확인하지 못했다. | 미확인 | 미확인  |
| vidIQ | 벤치마킹 / 비교 기준 | 사용자 주도 도구 | 기존 불편을 기능별로 분해하고 대체 도구를 필요한 부분에만 선택한다. 비공식 API나 자체 성과 점수를 우리 서비스의 검증된 확률로 복사하지 않는다. | 이번 요금 확정 안 함 | 기능·계정·재사용 조건 별도 [공식 근거](https://vidiq.com/) |
| TubeBuddy | 벤치마킹 / Studio SEO 보조 | 확장·수동 | 키워드·태그·제목을 사용자가 점검하는 확장 도구 후보다. 외부 제품에 연결할 공개 API는 이번 확인 범위에 없다. 일부 무료·유료 티어를 구분한다. | 제한 무료·유료 티어 | 확장·서비스 약관 확인 [공식 근거](https://www.tubebuddy.com/tools/keyword-explorer/) |
| ViewStats | 벤치마킹 / 형식·제목·썸네일 관찰 | 수동·Business API 확인 | Outliers·Alerts·Collections로 편집 가설을 만든다. Business API 소개와 공개 셀프서비스 계약 확인을 구분한다. 실제 계정·API 사용 안 함. | Business 소개 $249/월부터; 기타 동적 가격 미확정 | 재사용·계정·계약 확인 [공식 근거](https://www.viewstats.com/info) |
| vling | 벤치마킹 / 국내 특화 데이터 선택 | 공식 OAS·기업 경로 | 공개 OAS와 Custom API/MCP를 확인한 국내 분석 후보다. 키·기업 계약·재배포·품질은 미검증. 추정치는 YouTube 공식 수치와 분리한다. | 계약·사용량 확인 | API 계약·재배포 조건 확인 [공식 근거](https://open.apix.vling.net/) |
| BLACKKIWI | 벤치마킹 / 한국어 검색 글감 조사 | 수동·API 미확인 | 네이버 검색 의도·키워드 가설을 수동 조사하는 후보로 둔다. 메인 조회 403; 도움말 확인 범위와 실제 서비스·API 계약을 구분한다. | 현재 요금 미확정 | 서비스·데이터 재사용 조건 확인 [공식 근거](https://blackkiwi.net/) |
| uSearch | 벤치마킹 / 한국어 기획 UI 참고 | 공개 API 미확인 | 영상 조건 검색·대본·썸네일의 기획 흐름을 참고한다. 공개 HTML의 점검·연결 오류와 실제 작동은 별도. 자체 떡상 확률을 검증된 확률로 채택하지 않는다. | 미확정 | API·사용 범위 미확인 [공식 근거](https://usearch.kr/) |
| RapidTags | 벤치마킹 / 보조 태그 후보 | 수동·API 미확인 | 콘텐츠와 실제로 관련된 태그 후보만 사람이 검토한다. 태그 생성이 주제 수요·시청 지속·매출 검증을 대신하지 않는다. | 계정·플랜 확인 | 공개 도구·재사용 조건 확인 [공식 근거](https://rapidtags.io/) |
| KeywordTool.io | 벤치마킹 / 검색어 후보 확장 | 공식 API | 검색 플랫폼별 키워드 후보를 확장하고 독자의 질문으로 좁힌다. 검색량·경쟁 추정치는 출처·시각·제공자를 표시하고 다른 지표와 혼동하지 않는다. | API·플랜별 확인 | API·재사용·계정 조건 확인 [공식 근거](https://keywordtool.io/api) |
| YouTube Data API | 발행 / 우선 검증할 업로드 어댑터 | 공식 API | 명시적 private 업로드 후 처리 완료·메타데이터·출고 승인과 예약을 확인한다. privacyStatus 생략을 비공개 안전장치로 쓰지 않는다. OAuth·쿼터·소유 채널·재시도 대사가 필요하다. | 현행 기본 검색/업로드 각 100회 전용 버킷 + 기타 10,000단위/일 | API 정책·사용자 제어·데이터 보존 [공식 근거](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert) |
| Gemini Omni 1.1 Flash | 영상 / 새 Gemini 영상 경로 후보 | 공식 API | Veo Preview 종료 뒤 신규 경로를 검토할 때 선택한다. 공식 문서는 영어만 평가 완료. 한국어 음성은 별도 TTS로 비교하며 1080p/4K 업스케일을 구분한다. | 720p 출력 약 $0.10/초 + 입력 등 | 모델·입력·서비스 조건 확인 [공식 근거](https://ai.google.dev/gemini-api/docs/omni) |
| Adobe Firefly API | 이미지 / 브랜드·제품 합성 후보 | 공식 API | 상업 콘텐츠에 필요한 참조·제품 합성 흐름을 비교한다. 정식/베타별 조건·입력 권리를 검토한다. 계정·계약 가격 미확인. | 계약·기능별 확인 | API·베타 예외·입력 권리 확인 [공식 근거](https://developer.adobe.com/firefly-services/docs/firefly-api/) |
| Recraft Vector | 이미지 / 편집 가능한 벡터 후보 | 공식 API | SVG 도해·아이콘이 필요한 장면에서 비교한다. 웹 Free·MCP·API 자산 조건을 혼동하지 않는다. 정확한 텍스트는 직접 레이어로 작성한다. | V4.1 일반 벡터 $0.08/장 | 개발자 약관·표식·학습 이용 제한 확인 [공식 근거](https://www.recraft.ai/legal/developer-terms) |
| Resend | 뉴스레터 / 기존 설계의 전송 후보 | 공식 API | 회차·동의·수신거부·빈도·승인 장부는 오피스가 소유하고 전송 기반만 빌린다. 현행 한 수신자 SMTP 접수와 뉴스레터 운영은 다르다. 실제 연결 안 함. | 계정·발송량별 확인 | 전송·개인정보·동의 조건 [공식 근거](https://resend.com/docs) |
| Buffer | 발행 / 다중 채널 초안 대안 | 공식 API | 공식 GraphQL API의 saveToDraft 등을 연결 후보로 검토한다. 연결 채널별 기능·토큰·계정 권한을 확인한다. 중복 작업 장부는 만들지 않는다. | Free API키1개·3,000요청/30일 표시; 조건 재확인 | 공식 API·채널별 정책 [공식 근거](https://developers.buffer.com/) |

## 사용자 요청 이름의 누락 검사

| 입력 이름 | 대응 ID |
| --- | --- |
| Midjourney | midjourney |
| Nano Banana | nano-banana |
| Runway | runway |
| Kling | kling |
| Veo | veo |
| Luma | luma |
| AutoKliq | autokliq |
| Chatterbox | chatterbox |
| Qwen | qwen-family |
| Eleven v4 | eleven-v4 |
| Multilingual v2 | eleven-v2 |
| Qwen3-TTS | qwen3-tts |
| VoxCPM2 | voxcpm2 |
| Confucius4-TTS | confucius4 |
| OpenVoice | openvoice |
| Claude | claude |
| Blender | blender |
| Hyperframe | hyperframes |
| FFmpeg | ffmpeg |
| Remotion | remotion |
| Upside | upside |
| vidIQ | vidiq |
| TubeBuddy | tubebuddy |
| ViewStats | viewstats |
| vling | vling |
| BLACKKIWI | blackkiwi |
| usearch | usearch |
| RapidTags | rapidtags |
| KeywordTool.io | keywordtool |
