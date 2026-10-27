# HeoBrain 콘텐츠 스튜디오: 음성·글쓰기·배포 도구 선택과 이관 설계

조사일: **2026-10-28 KST**. 공식 모델 문서·개발 문서·저장소·모델 카드·라이선스를 기준으로 확인했다. 이 문서는 통합 계획의 부속 조사 원본이며, 다른 모델이 근거를 재검증하고 구현 상태를 이어받을 수 있도록 작성했다.

## 1. 먼저 선택할 조합

**운영 부담이 작은 기본안:** Claude Sonnet 5.5로 근거가 붙은 초안을 만들고, Claude Haiku 5.5로 제목·채널별 메타데이터를 구조화한다. TTS는 긴 설명 영상에 Eleven Multilingual v2, 짧은 대화·표현이 중요한 장면에 Eleven v4를 비교한다. 메일 제공자가 아직 없다면 Buttondown의 초안 API가 작은 시작점이다. 이미 검증된 메일 제공자가 있다면 새 서비스 도입보다 그 연결을 재사용한다.

**로컬 TTS 실험안:** Qwen3-TTS 0.6B CustomVoice의 한국어 화자 Sohee를 먼저 평가하고, 복제 음성이 필요할 때 Base 모델을 별도로 평가한다. VoxCPM2·Confucius4-TTS·Chatterbox Multilingual V3·OpenVoice V2는 비교 후보로 유지한다. 현재 PC의 메모리 압박을 고려하면 모든 모델을 한꺼번에 올리는 방식은 제안하지 않는다. 실제 실행 자원과 속도는 별도 측정해야 한다.

이는 HeoBrain의 초기 운영 조건을 고려한 **선택 제안**이다. 한국어 음질 순위를 직접 측정한 결론이 아니다. 공급사 벤치마크도 자체 평가와 독립 실험을 구분한다.

## 2. 현재 상태와 검증 경계

| 구분 | 이번 조사에서 확인한 범위 |
|---|---|
| 현재 구현 | 이 조사 문서와 단계별 선택·인계 계약을 작성했다. 기존 프로젝트의 어댑터 구현 여부를 이 문서만으로 판정하지 않는다. |
| 이번에 검증 완료 | 아래 공식 모델·API·가격·라이선스 문서를 직접 열어 확인했다. Eleven v4와 Confucius4-TTS는 실제 공식 제품/저장소가 있다. |
| 계획/제안 | 모델 라우팅, 음성 평가, 초안 저장, 승인 후 배포, UTM·서버 쿠폰·주문 귀속 흐름이다. |
| 미구현/차단 | 유료 API 호출, 음성 생성·청취 비교, 계정별 모델 사용 권한, OAuth 연결, 메일 발송, 영상 업로드, 실제 쿠폰 발급은 실행하지 않았다. Upside의 정확한 제품은 특정하지 못했다. |

**공식 문서 존재**와 **계정에서 호출 가능**과 **실제 콘텐츠 품질 통과**는 서로 다른 상태로 기록해야 한다.

## 3. 사용자 제시 TTS 이름의 정확한 해석

| 입력 이름 | 확인한 정확한 대상 | 한국어·언어 범위 | 자동화 방식·라이선스 | HeoBrain에서의 위치 |
|---|---|---|---|---|
| Chatterbox | Resemble AI의 Chatterbox 계열. 현재 공식 README에 Turbo 350M 및 Multilingual V3 500M 표기 | Turbo는 영어. Multilingual은 한국어를 포함한 다국어 지원 | 로컬 Python 경로, MIT. 관리형 Resemble API와 오픈 모델의 지원 범위·요금은 별개 | 한국어 기본으로 Turbo를 선택하지 않는다. 다국어 V3는 비교 실험 후보 |
| Qwen | 일반 Qwen 언어모델 전체를 TTS 한 모델로 세지 않는다 | 구체적 TTS 체크포인트를 지정해야 함 | Qwen3-TTS 행으로 정규화 | 이름만 Qwen인 설정은 배포하지 않음 |
| Qwen3-TTS | Qwen3-TTS-12Hz 0.6B·1.7B, CustomVoice / Base / VoiceDesign 구분 | 한국어 포함 10개 언어. CustomVoice의 Sohee는 한국어 화자 | Python SDK, 공식 DashScope API 연결 문서. 코드·확인한 0.6B 모델 카드는 Apache-2.0 | 저비용 로컬 실험의 첫 후보. 화자 복제가 불필요하면 CustomVoice부터 |
| Eleven v4 | 공식 `eleven_v4` | 한국어 포함 90+ 언어 | **Text to Dialogue API**. 유료 서비스 상업 조건 확인 필요 | 감정·대화·짧은 표현 장면의 유료 후보 |
| Multilingual v2 | `eleven_multilingual_v2` | 한국어 포함 29개 언어 | 기존 Text to Speech 경로. 유료 서비스 상업 조건 확인 필요 | 설명·교육·긴 내레이션의 안정성 기준선 |
| VoxCPM2 | OpenBMB/VoxCPM의 최신 2B 모델 | 한국어 포함 30개 언어, 48kHz 출력 | Python·서빙 경로, 코드·가중치 Apache-2.0. 공식 비교표의 VRAM은 약 8GB | 별도 GPU 작업자에서 음질·처리량 비교. 1.5/0.5B의 중·영어 지원을 v2와 혼동하지 않음 |
| Confucius4-TTS | NetEase Youdao 공식 저장소·가중치 | 한국어 포함 14개 언어 | Python/서버 예제. 코드 LICENSE와 공식 HF 카드 모두 Apache-2.0 | 다국어·교차언어 음색 전환 비교 후보 |
| OpenVoice | MyShell의 OpenVoice V2 | 한국어 포함 6개 언어의 네이티브 지원 | 로컬 음색 변환·복제 파이프라인, MIT·상업 사용 허용을 공식 명시 | 기존 화자 음색을 다국어로 옮길 때 검토. 완성형 관리 API와 동일시하지 않음 |

근거: [Chatterbox 공식 README](https://github.com/resemble-ai/chatterbox), [Chatterbox MIT](https://raw.githubusercontent.com/resemble-ai/chatterbox/master/LICENSE), [Qwen3-TTS 공식 저장소](https://github.com/QwenLM/Qwen3-TTS), [Qwen 0.6B 공식 모델 카드](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice), [ElevenLabs 모델 문서](https://elevenlabs.io/docs/overview/models), [VoxCPM 공식 저장소](https://github.com/OpenBMB/VoxCPM), [Confucius4 공식 저장소](https://github.com/netease-youdao/Confucius4-TTS), [Confucius 코드 LICENSE](https://raw.githubusercontent.com/netease-youdao/Confucius4-TTS/main/LICENSE), [Confucius 공식 가중치 카드](https://huggingface.co/netease-youdao/Confucius4-TTS), [OpenVoice 공식 저장소](https://github.com/myshell-ai/OpenVoice).

### 선택할 때 놓치면 안 되는 차이

- **Eleven v4는 이름만 교체하는 작업이 아니다.** 공식 모델 문서의 제공 경로가 Text to Dialogue이므로, 기존 v2 TTS 어댑터에 모델 ID만 바꾸기 전에 요청·응답·멀티 화자 형식을 확인한다.
- Chatterbox의 한국어 지원은 확인했지만, 공급사 V3 평가 문서는 한국어·베트남어 개선 여지가 있다고 설명한다. 언어 목록에 있다는 이유로 한국어 최고 음질이라고 부르지 않는다. [Resemble의 V3 평가 설명](https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages)
- Qwen의 **CustomVoice**는 제공된 화자, **Base**는 참조 음성 복제, **VoiceDesign**은 설명에 따른 음성 설계라는 역할을 구분한다. 특정 체크포인트와 실제 화자 목록은 운영 전에 고정한다.
- Qwen README의 **96GB RAM 관련 문구는 FlashAttention 빌드 병렬 수를 줄이는 안내**다. 이를 모델 실행 최소 RAM 96GB라고 해석하면 안 된다. 최소 시스템 RAM을 확인하지 못한 모델에는 임의의 숫자를 쓰지 않는다.
- Confucius README는 Python 3.10·CUDA 12.6 환경과 CPU/GPU 선택 예제를 제공하지만, 최소 RAM/VRAM을 명확히 보증하지 않는다. CPU 예제 존재가 현재 PC에서의 실용 속도를 보장하지 않는다.
- VoxCPM2의 약 8GB는 **GPU VRAM** 수치다. 시스템 RAM 여유 8GB와 같은 조건이 아니다. 공식 RTX 4090 속도도 현재 PC 속도 예측값으로 사용하지 않는다.
- MIT·Apache-2.0는 소프트웨어/모델 배포 조건이다. 타인의 음성·상표·대본 권리까지 자동으로 해결해 주지 않는다.

## 4. TTS 추천 프로필과 비용 계산

| 프로필 | 1차 선택 | 대체·비교 | 적용 조건 |
|---|---|---|---|
| 한국어 설명 영상·뉴스레터 음성 | Eleven Multilingual v2 | Eleven v4 | 긴 문장·날짜·금액·고유명사의 일관성을 직접 평가 |
| 숏폼·대화·캐릭터 연기 | Eleven v4 | v2 또는 검증된 로컬 모델 | 과한 감정·속도 변화가 메시지를 왜곡하지 않는지 청취 검토 |
| 유료 API 비용 최소화 실험 | Qwen3-TTS 0.6B CustomVoice/Sohee | 1.7B CustomVoice | 운영과 분리된 환경에서 RAM·속도·한국어 정확도를 먼저 측정 |
| 자사 화자 다국어 확장 | Qwen Base / VoxCPM2 / Confucius4 / OpenVoice V2 | Eleven의 권한 있는 화자 | 원음·동의·허용 매체·기간·철회 범위를 확인한 화자만 |

2026-10-28 공식 ElevenAPI 가격 페이지 표시는 **v4와 v2 Multilingual 모두 1,000자당 USD 0.08**, Flash/Turbo는 USD 0.04다. 과거 크레딧 요금표와 섞지 않는다. 월 구독·지역·부가 조건과 해당 계정 청구 방식을 다시 확인해야 한다. [공식 API 가격](https://elevenlabs.io/pricing/api)

예산 예시: 대본 5,000자로 음성을 한 번 생성하면 `5 × 0.08 = USD 0.40`이다. 같은 대본을 세 번 전부 재생성하면 USD 1.20이다. 이는 **가정 계산**이며 실제 청구·한국어 재생 길이 측정이 아니다. 영상·이미지·글쓰기·저장·재시도 비용은 별도다.

오픈 모델에도 GPU/전력/운영/저장/재생성 비용이 있다. 현재 PC에서 모델을 상주시켜 다른 AI 작업과 경쟁시키기보다, 승인된 예산과 별도 작업자 사용 가능성을 먼저 결정한다.

### 상업 사용과 화자 동의

ElevenLabs는 Free 생성물에 상업 라이선스가 없고, 유료 플랜 생성물도 Beta Services·개별 서비스 약관·입력 권리 조건을 따른다고 명시한다. 무료 테스트 음성을 나중에 유료 결제로 소급해 상업용으로 간주하지 않는다. [공식 상업 사용 안내](https://help.elevenlabs.io/hc/en-us/articles/13313564601361-Can-I-publish-the-content-I-generate-on-the-platform)

Instant Voice Cloning은 필요한 권리·동의를 확인한다. Professional Voice Cloning은 공급사 정책상 **본인 음성만** 만들 수 있으며, 타인이 자신의 계정에서 확인한 음성을 공유하는 방식과 구분된다. Eleven의 음성 모델은 독립 파일로 내보낼 수 없으므로 원음·동의·발음 사전·대본을 별도로 보관한다. [음성 복제 공식 문서](https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning), [Professional Voice Cloning](https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/professional-voice-cloning)

## 5. 한국어 음성 품질 검증 계약

공급사 벤치마크의 순위를 그대로 구매 결정으로 바꾸지 않고, 다음은 **HeoBrain에 적용할 평가안**으로 둔다.

1. 30~60초 동일 대본을 후보 두 모델로 생성한다. 뉴스·개념 설명·상품 안내 대본을 나눈다.
2. 날짜·금액·단위·영문 약어·고유명사·문장 끝·긴 문단을 포함한 100문장 평가 묶음을 만든다.
3. 표기 사전 예: HeoBrain, SQLD, API, MCP, Claude, 쿠폰 15%, 8,000원. 화면 표기와 낭독 표기를 별도 필드로 보관한다.
4. ASR 재전사로 빠짐·반복·언어 전환 후보를 찾고 사람이 실제 원문과 음성을 듣는다. ASR 일치율은 자연스러움·감정·유사성을 대신하지 않는다.
5. 합격 기준을 문서에 고정한다. 예: 상품 가격·쿠폰 조건·날짜 오류 0건, 대본 누락 0건, 귀에 거슬리는 끊김/클리핑 없음. 이는 제안한 출시 기준이며 달성 결과가 아니다.
6. 문장별로 나누어 생성하되, 이어붙인 뒤 경계·음량·호흡을 다시 듣는다. 한 번의 실패 때문에 전체 음성을 재생성하지 않도록 장면 해시와 캐시를 둔다.

인계 데이터에 `text_hash`, 정규화 대본, 화면 대본, provider/model/voice ID, 요청 옵션, 생성 시점, 출력 SHA-256, 화자 권리 상태, 검수 결과, 실제 비용을 기록한다. 외부 웹사이트에 참조 음성·동의서·비밀 키를 공개하지 않는다.

## 6. 글쓰기: Claude를 역할별로 선택

공식 모델 목록은 조사일에 Claude Fable 5.1·Opus 5.5·Sonnet 5.5·Haiku 5.5를 제공한다. 아래는 소규모 콘텐츠 운영에 맞춘 역할 제안이며, 공급사 전체 용도의 성능 순위와 다르다. 모델 접근 가능 여부는 실제 계정의 Models API로 검증해야 한다. [공식 모델 목록](https://platform.claude.com/docs/en/models/overview)

| 역할 제안 | API ID | 표준 입력 / 출력, USD per 1M tokens |
|---|---|---:|
| 분류·요약 후보·태그·메타데이터 | `claude-haiku-5-5` | 100K 이하 입력 프롬프트: 0.10 / 0.50. 100K 초과: 0.50 / 2.50 |
| 근거 있는 대본·블로그·메일 초안 기본 | `claude-sonnet-5-5` | 2 / 10 |
| 복잡한 비교·정책·고위험 표현의 추가 검토 | `claude-opus-5-5` | 4 / 20 |
| Opus 평가가 계속 부족한 어려운 추론·장기 작업 | `claude-fable-5-1` | 10 / 50. 일상 초안에 기본 투입하지 않음 |

표는 조사일 공식 글로벌 표준 단가다. 캐시·Batch·Fast mode·지역·호스팅 경로의 요금 차이를 섞지 않는다. 공식 문서는 Batch의 입출력 50% 할인과 모델별 캐시 비용을 설명한다. [공식 가격](https://platform.claude.com/docs/en/about-claude/pricing)

예시: Sonnet에 입력 3,000·출력 2,000토큰인 요청 한 번은 표준 단가상 `0.006 + 0.020 = USD 0.026`이다. 같은 규모 요청 네 번은 USD 0.104다. 실제 콘텐츠 토큰 수나 도구 사용료를 측정한 결과는 아니다.

글쓰기 계약은 자료의 `source_id`와 문장별 근거를 보존하고, 한 번 승인한 사실 묶음에서 블로그·메일·영상 대본을 파생시키는 방식이다. 작성 모델과 검토 역할을 분리해도 모델 답변이 사실 확인 자체가 되는 것은 아니다. 원문 근거·수치 조건·개인 경험의 실제 기록을 별도 검사한다.

## 7. 배포 어댑터 비교

| 채널·도구 | 확인 상태 | 기본 저장 상태 | 권장 운영 방식·제약 |
|---|---|---|---|
| YouTube Data API | 공식 업로드 API | `status.privacyStatus=private`를 **명시** | 업로드 후 처리·차단·자막·썸네일 확인, 별도 공개 승인. 예약은 미래의 `publishAt`과 private 조건 확인 |
| WordPress | 공식 REST Posts API | `status=draft` | 소유 사이트의 권한 있는 계정으로 생성·재조회 후 승인. WordPress.com 인증과 자체 호스팅 인증은 구분 |
| Tistory | 기존 Open API 종료 공지 확인 | 로컬 Markdown/HTML 초안 | 자동 API 발행 가능하다고 표기하지 않음. 현재 에디터에 수동 인계 |
| NAVER Blog | 로그인 방식 글쓰기 Open API 종료 공지 확인 | 로컬 초안 | 검색 API와 글쓰기 API를 혼동하지 않음. 기계적 유사 글 대량 게재를 피하고 수동 인계 |
| Buttondown | 공식 API, Free 포함 접근 문서 | `status=draft` | 초안 생성→검토→별도 보내기/예약. 가입자 목록과 수신 동의는 별도 관리 |
| beehiiv | 공식 Create Post/Send API | `draft` 명시 | 조사일 공식 제공 플랜은 **Pro·Enterprise**. 기본 계정에서 사용 가능하다고 가정하지 않음 |
| Ghost | 공식 Admin API | `draft` 명시 | 게시물 게시와 이메일 발송은 별도 결과. HTML→Lexical 변환과 이메일 상태 재검증 |
| Resend Broadcasts | 공식 생성·발송 API | 생성 시 발송 옵션을 켜지 않은 draft | 기존 서버 메일 도메인·구독 관리가 준비된 경우 재사용 검토. `send=true`는 승인된 발송 경로에만 |
| Substack | 공식 Developer API 약관은 존재 | 수동 발행 인계 | 확인한 공식 API 약관은 공개 창작자/출판물 데이터 용도. 글쓰기·예약 엔드포인트는 이번에 검증하지 못함 |
| Buffer | 2026-05-27 공개 GraphQL API 공식 출시 | `saveToDraft=true` | 실제 지원 채널·자산 형식·연결 권한을 확인한 뒤 예약. 댓글 읽기/답변 API로 확장해 해석하지 않음 |
| Upside | **제품 식별 보류** | 미설정 | 정확한 공식 URL·제품명·API 문서가 필요. 동명 GTM·부동산·일반 upside 검색 결과를 자동업로드 서비스로 연결하지 않음 |

근거: [YouTube videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert?hl=en), [WordPress Posts](https://developer.wordpress.org/rest-api/reference/posts/), [Tistory 종료 공지](https://notice.tistory.com/2664), [NAVER 종료 공지](https://developers.naver.com/notice/article/7527), [Buttondown 초안 API](https://docs.buttondown.com/drafting-emails-via-the-api), [beehiiv Create Post](https://developers.beehiiv.com/api-reference/posts/create), [beehiiv 플랜 안내](https://www.beehiiv.com/support/article/36759164012439-using-the-send-api-and-create-post-endpoint), [Ghost 초안 생성](https://docs.ghost.org/admin-api/posts/creating-a-post), [Ghost 이메일 발송](https://docs.ghost.org/admin-api/posts/sending-a-post), [Resend Broadcast 생성](https://resend.com/docs/api-reference/broadcasts/create-broadcast), [Substack API 약관](https://substack.com/api-tos), [Buffer 공식 출시](https://buffer.com/resources/buffer-api-is-here/), [Buffer API 레퍼런스](https://developers.buffer.com/reference.html).

### YouTube의 낡은 전제를 제거한다

현재 공식 문서는 검색 100회/일·영상 업로드 100회/일의 별도 기본 할당과 기타 엔드포인트 합계 10,000단위/일을 설명한다. `videos.insert`는 Video Uploads 버킷에서 1단위/호출로 기재돼 있다. 계정·프로젝트별 콘솔 수치와 실제 오류를 추가 확인한다. 과거의 검색/업로드 단위 수를 계산식에 무조건 재사용하지 않는다. [공식 할당·감사 안내](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits?hl=en)

조사일 `videos.insert` 문서는 `privacyStatus` 생략 시 public이 기본이며, 미검증 API 프로젝트 업로드가 일률적으로 private 제한을 받는 것은 아니라고 명시한다. 따라서 **명시적으로 private을 지정하는 어댑터**를 만든다. 이는 HeoBrain 프로젝트에서 업로드를 실제 실행·공개 검증했다는 뜻이 아니다. [공식 업로드 명세](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert?hl=en)

`publishAt`은 private이고 아직 공개되지 않은 영상에서 조건을 확인해야 한다. 과거 시각을 넣으면 즉시 공개될 수 있으므로 미래 시각·KST/UTC 변환을 검증한다. [공식 Video resource](https://developers.google.com/youtube/data/reference/rest/v3/videos)

## 8. 뉴스레터 선택을 좁히는 기준

- **초기 독자 검증:** Buttondown. 공식 가격은 첫 100명 무료이며, API는 Free를 포함해 제공한다. 분석·태그·RSS 등 추가 기능에 별도 비용이 있으므로 모두 무료라고 설명하지 않는다. [공식 가격](https://buttondown.com/pricing), [공식 API 제공 범위](https://marketing.buttondown.email/features/api)
- **블로그·아카이브·멤버십을 한 CMS에서 운영해야 할 때:** Ghost. 기존 HeoBrain을 대체하는 새 CMS를 곧바로 설치하지 않고, 별도 운영비·이중 로그인·자료 이관 부담을 비교한다.
- **추천 프로그램·성장 기능·뉴스레터 비즈니스가 실제 요구일 때:** beehiiv. 일반 API 접근과 Send API의 플랜 조건을 분리한다.
- **기존 앱의 이메일 기반을 유지할 때:** Resend 등 이미 검증한 제공자 연결을 우선 검토한다. 연락처 동의·수신거부·반송·스팸 신고·인증 도메인 처리가 준비돼야 한다.
- **기존 Substack 독자가 중심일 때:** 초안 패키지를 사람이 발행한다. 공식 공개 데이터 API를 글쓰기 API로 확대 해석하지 않는다.

Buttondown의 현재 초안 API 예제는 `draft`, 발송 전환은 `about_to_send`, 예약은 `scheduled`와 `publish_date`를 설명한다. 공급사 기본값이 바뀔 수 있어 안전한 초안 상태를 명시한다. 메일이 `sent`인지, 일부만 전달됐는지와 반송 여부를 구분한다. 초안 저장 성공을 발송 성공으로 보고하지 않는다. [공식 상태 설명](https://docs.buttondown.com/api-emails-introduction)

Buffer는 Free 포함 API를 제공하며, 공식 도움말은 Free에 API 키 1개·30일간 3,000요청을 설명한다. 신규 계정 생성·키 발급·권한 연결·예약/발행은 실제 운영 승인 후 별도 단계로 둔다. [Buffer 공식 API 도움말](https://support.buffer.com/en-us/articles/what-is-buffers-api-GtIYIQilz5)

## 9. HeoBrain 멀티채널 → 상품 연결 아이디어

다음은 **계획/제안**이며 현재 운영 실적이 아니다.

| 콘텐츠 흐름 | 뉴스레터 | 블로그 | 영상 | HeoBrain 연결 |
|---|---|---|---|---|
| 주간 AI 자동화 실험실 | 실제 실행한 워크플로 1개와 실패 기록 | 재현 절차·환경·비용 | 3~6분 실행 데모 + 30초 핵심 장면 | 해당 실습 체크리스트·템플릿 페이지 |
| 모델 선택 비교 | 이번 주 의사결정 1개 | 같은 입력의 품질·비용 비교 | 블라인드 샘플·결과 설명 | 비교표 다운로드·업데이트 구독 |
| 자동화 전후 사례 | 수행 시간·조건·사람 검토 범위 | 설정 파일·되돌리기 절차 | 실제 화면 기반 시연 | 관련 상품의 구체적 학습 결과 안내 |
| 독자 질문 해결 | 익명화한 질문 3개 | 자세한 답변과 출처 | 질문 1개당 짧은 설명 | 주제별 자료 묶음·자발적 알림 신청 |
| 개념 → 실습 → 회고 | 한 개념과 한 행동 | 원문 링크·실습·한계 | 독립 제작 도해·내레이션 | 학습 모듈·선택형 퀴즈·관련 상품 |

하나의 승인된 사실 묶음에서 채널별 길이·예시·CTA를 다르게 만든다. 텍스트만 바꾼 동일 대량 콘텐츠를 성공 모델로 삼지 않는다.

### 쿠폰·매출 연결의 계약

1. `content_id`를 기사·메일·영상·상품 안내의 공통 키로 둔다.
2. 링크에는 표준화한 `utm_source`, `utm_medium`, `utm_campaign`, 필요 시 `utm_content`를 넣는다. 이메일 주소·실명·비밀 토큰을 UTM에 넣지 않는다. [Google의 캠페인 URL 안내](https://support.google.com/analytics/answer/10917952?hl=en)
3. 상품 클릭·쿠폰 발급·쿠폰 사용·결제 확인·환불을 별도 이벤트로 구분한다. UTM 유입이 있었다는 사실을 매출의 인과 효과로 단정하지 않는다.
4. 쿠폰의 할인액·대상 상품·기한·발급/사용 한도·중복 정책은 서버에서 결정한다. 콘텐츠 모델은 문구 초안을 만들고, 서버가 승인된 캠페인 값으로 검증한다.
5. 동일 캠페인/사용자/주문의 중복 처리를 서버의 고유 키와 상태 전이로 막는다. 결제 성공·주문 생성·상품 전달·환불은 각 단계의 실제 응답으로 확인한다.
6. **유튜브 구독·조회·좋아요·댓글의 보상으로 쿠폰을 자동 발급하는 조건은 넣지 않는다.** YouTube API 정책은 이런 참여에 대한 보상 제공을 금지한다. 상품 페이지의 공개 캠페인이나 별도의 자발적 구독 혜택과 구분해 정책 검토한다. [공식 Developer Policies](https://developers.google.com/youtube/terms/developer-policies), [Fake engagement 정책](https://support.google.com/youtube/answer/3399767?hl=en-GB)

## 10. 영상·음성의 공개 전 검사

- 출처 확인된 사실·실제 실행 화면·독립 제작 도해·권한 있는 음성·상업 조건이 확인된 자산만 사용한다.
- YouTube는 사실처럼 보이는 합성 인물/사건/장소와 특정 AI 음악 등에 공개 표시를 요구한다. 반대로 기획·대본·썸네일 보조, 자막, 자신의 음성 복제 등은 공식 예외 사례가 있다. 모든 AI 사용을 동일 규칙으로 분류하지 말고 장면별 이유와 `containsSyntheticMedia` 결정 근거를 남긴다. [공식 GenAI 표시 안내](https://support.google.com/youtube/answer/14328491?hl=en)
- 생성형 콘텐츠라고 자동으로 수익화가 불가능한 것은 아니지만, 일반적·반복적·대량생산된 템플릿 콘텐츠는 수익화 부적격이 될 수 있다. 실험, 설명, 사례, 자체 판단을 각 영상에 실질적으로 추가한다. [공식 수익화 정책](https://support.google.com/youtube/answer/1311392?hl=en)
- 의료·법률·재무·상품 효능처럼 영향이 큰 주제는 별도 전문가 검토 상태를 둔다. 검토가 필요한 문장을 음성으로 먼저 배포하지 않는다.

## 11. 다른 모델로 이관할 때 넘길 최소 계약

아래는 실제 연결 설정이 아닌 **제안한 인계 데이터 예시**다.

```yaml
research_checked_kst: 2026-10-28
implementation_state: proposed
execution_verdict: NOT_RUN
content_id: hb-example-001
source_approval: pending
script:
  model_id: claude-sonnet-5-5
  artifact: script.reviewed.md
  text_hash: pending
voice:
  default_model_id: eleven_multilingual_v2
  expressive_candidate_model_id: eleven_v4
  voice_id: unset
  speaker_rights: pending
  commercial_terms: pending
  normalized_script: narration.ko.txt
  audio_artifact: unset
publish:
  approval_required: true
  youtube_initial_privacy: private
  newsletter_initial_status: draft
  blog_delivery: manual_handoff
  coupon_issue_permission: false
  production_publish_permission: false
measurement:
  campaign_id: hb-example-campaign
  pii_in_utm: false
  order_result_verified: false
```

이관 묶음에는 다음을 포함한다.

- 근거 URL과 확인일, 사용한 모델 ID/체크포인트와 옵션, 가격의 단위·기준일.
- 소스 원본·승인된 사실 묶음·초안·검토 의견·최종본·장면별 미디어·권리 기록·파일 해시.
- 로컬 경로와 배포 URL의 역할 차이. 공개 사이트에는 비밀 키·음성 동의서·가입자 목록을 넣지 않는다.
- 발행 어댑터별 `official_api`, `manual_handoff`, `unverified` 상태.
- 실패 시 재개 지점과 외부 서비스가 반환한 ID. 타임아웃 후 같은 메일/영상/쿠폰을 무조건 재생성·재발행하지 않는다.
- 다른 모델이 실행할 다음 작업: 공식 모델/가격 재확인 → 계정 권한 확인 → 비공개 샘플 생성 → 한국어 검수 → 명시적 배포 승인 → 실제 결과 재조회.

## 12. 이번 조사에서 의도적으로 남긴 검증 보류

| 항목 | 보류 이유·필요한 다음 확인 |
|---|---|
| Upside | 자동업로드 제품의 정확한 공식 URL 미확보. 이름만으로 다른 서비스를 대신 연결하지 않음 |
| 한국어 최고 음질 순위 | 생성·청취 비교를 하지 않음. 공급사 지원 언어와 벤치마크만 확인 |
| 대부분 오픈 TTS의 최소 시스템 RAM | 공식 보장 수치를 찾지 못함. 모델 파라미터·VRAM·빌드 RAM을 서로 대신 쓰지 않음 |
| Substack 글쓰기 API | 공식 API 약관은 확인했지만 기술 도움말 링크는 404였고 발행 엔드포인트를 검증하지 못함 |
| 서비스별 실제 계정 접근 | 로그인·API 키·유료 실행·권한 연결을 하지 않음 |
| 실제 매출·쿠폰 효과 | 캠페인·판매·콘텐츠를 실행하지 않았으므로 성과 주장 없음 |
