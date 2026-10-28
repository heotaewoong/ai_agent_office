# Runway 생성 장면과 YouTube 비공개 업로드 설계

작성일: 2026-10-28. 상태: 구현 완료(가짜 응답 검증), 실제 키 검증은 EC2에서 진행.

## 목적

1. 승인 원고에서 지정한 핵심 장면만 Runway image-to-video로 5초 생성 클립을 받아 숏폼에 끼운다. 나머지 장면은 지금처럼 정지 화면 줌이다.
2. 출고 승인②를 받은 영상을 운영자가 명시적으로 요청할 때만 소유 채널에 비공개로 올린다. 수동 인계 ZIP은 그대로 남는다.

## 바꾸지 않는 것

- ⓪①②③ 승인 의미. 생성 영상은 ① 이후, 업로드는 ② 이후에만 호출한다. ③ 회차·발송은 이번 범위가 아니다.
- 유료 호출 자동 대체·자동 재시도 없음. 결과 불명은 대사 전까지 추가 전송을 막는다.
- 키는 환경변수로만 전달한다. `RUNWAYML_API_SECRET`, `YOUTUBE_CLIENT_ID`·`YOUTUBE_CLIENT_SECRET`·`YOUTUBE_REFRESH_TOKEN`.

## 생성 장면

| 항목 | 결정 |
|---|---|
| 지정 방식 | 승인 원고 `video.scenes[i].clip == "generated"`, 선택 `motion` 문장 |
| 입력 프레임 | 그 장면의 생성 배경 PNG. 배경 프로필이 꺼져 있으면 유료 호출 전에 거부 |
| 모델·규격 | `gen4_turbo` 25크레딧 또는 `gen4.5` 60크레딧, 5초, `720:1280`, 프롬프트 ≤1000자, 글자·로고 금지 문구 포함 |
| 과금 | 크레딧 × $0.01 × 2,000원. 예약 500원/1,200원, 작업 `cost.credits`로 정산. 업무당 3,000원, 최대 3장면 |
| 상태 | `submitted` → `complete` / `failed`(제공자 사유 기록) / `unknown`(task_id 보존, 예약 유지) / `asset_needs_review` |
| 폴링 | 5초 간격 최대 90회. 미완료면 결과 불명 |
| 조립 | 글자만 있는 투명 PNG를 클립 위에 overlay. `-stream_loop -1`로 음성 길이만큼 반복 후 `-t`로 자름 |
| 보관 | 산출물 URL 24~48시간 만료 → `<state>/clip-assets/<key>.mp4` + 영수증 |

## YouTube 비공개 업로드

| 항목 | 결정 |
|---|---|
| 전제 | 영상이 포함된 현재 출고 승인②, 제작물 해시 일치, 파일 SHA-256 일치 |
| 메타데이터 | 제목·태그는 승인 영상 계획, 설명은 `description.txt` + 합성 음성·생성 화면 고지. `privacyStatus: private`, `selfDeclaredMadeForKids: false` |
| 인증 | refresh token으로 접근 토큰 발급. 토큰은 호출 동안만 메모리 |
| 프로토콜 | resumable 세션 시작(POST, Location) → 바이트 PUT. 200/201 완료, 500/502/503/504·연결 끊김은 `unknown`, 그 외 4xx는 `failed` |
| 장부 | 설정 `deliveries`에 키 = (채널, 업무, 자산 해시, 제작물 판본). 상태 `created → accepted → private / failed / unknown / needs_review` |
| 멱등 | 같은 키가 `private`면 재업로드 없이 기존 기록 반환. `accepted`/`unknown`이면 대사 전 거부 |
| 대사 | `Content-Range: bytes */N` 상태 조회 → 200/201 완료, 308이면 받은 범위 다음 바이트부터 이어 올림, 404면 세션 만료 `failed`. 외부 ID가 있으면 `videos.list`로 uploadStatus·processingStatus·privacyStatus 확인 |
| 공개 범위 불일치 | private가 아니면 `needs_review`와 이벤트 `delivery_visibility_mismatch` |
| 할당량 | 업로드 전용 일일 버킷 100회, 기타 10,000단위(2026-10-28 공식 문서). 1,600단위 환산은 참고값으로만 기록 |

## 범위 밖

- 썸네일 `thumbnails.set`(채널 인증 필요), 예약 공개, 재생목록, 댓글.
- 뉴스레터 회차③ 발송, 상품·쿠폰. 동의 장부와 상품 API 계약이 먼저 필요하다.
- 화면(UI) 버튼. API와 CLI만 제공하며 화면 연결은 후속 작업이다.
