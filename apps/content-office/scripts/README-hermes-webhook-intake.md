# Hermes 외부 사건 검토 대기 접수 후보

외부 데이터는 Lumi가 실행할 인간 업무가 아니다. 이 후보는 기존 native webhook의 인증과
`--script`를 사용해 private 검토 대기 파일만 저장한다. 새 listener/daemon, HTTP route,
외부 서비스, 의존성을 추가하지 않는다. `hermes-board-relay.py`의 private JSON·원자 저장·파일
잠금·비밀 탐지 helper만 읽어 재사용한다. relay socket/create, agent, Slack, Gmail은 호출하지 않는다.

## 현재 구현과 한계

- 정확한 Lumi/tenant/board, 본문 전송 ID, 발생시각 ±300초, UTF-8 16KB/본문4000자 검사.
- 같은 ID·같은 내용은 한 번만 저장. 같은 ID·다른 내용은 충돌로 거절. 고정 namespace로 ID를 해시한다.
- 기존 파일 잠금과0600 원자 저장 재사용. 최대512개 pending 파일(최대 약8MB), 자동 삭제/재처리 없음.
- 외부 본문은 코드/명령/프롬프트로 실행하지 않는다. 권한·도구·승인·담당자 필드는 허용하지 않는다.
- script는 성공과 실패 모두 `[SILENT]`로 agent 실행 전에 끝난다. stderr는 상태/영수증 해시만 기록한다.
  **native HTTP 200 `ignored`는 저장 성공 영수증이 아니다.** private 파일을 직접 확인해야 한다.
  실패는 운영 담당 검토 대상으로 두며 자동 재시도하지 않는다.
- native의 raw UTF-8 body 한도16KB와 script의 ensure_ascii stdin 한도96KB를 구분한다.
- native HMAC은 그대로 사용한다. 권장 전송은 `X-Webhook-Signature-V2`(timestamp + body) 및
  `X-Webhook-Timestamp`. 전송 ID는 서명된 body의 `event_id`가 기준이며 바깥 헤더만 신뢰하지 않는다.
  native가 지원하는 token/body-only 서명을 강제 차단하는 새 인증 엔진은 만들지 않았다.
  loopback만 허용하며 공개 ingress는 별도 보안 검토가 끝나기 전 연결하지 않는다.

## 고정 입력

```json
{"version":1,"event_id":"provider-event-123","occurred_at":1793667600,"profile":"lumi","tenant":"heobrain-world","board":"heobrain-office","type":"inquiry","text":"검토할 외부 문의"}
```

예시 시각은 고정 시험용이다. 실제 송신 때 현재 Unix 초를 사용한다. Tally raw payload는 이
스키마와 다르므로 현재 직접 연결되지 않는다. 계정/폼/실서명/전송 매핑이 관측되기 전 완료로
표현하지 않는다. 토큰을 채팅·공개 Git·로그에 넣거나 기존 구독을 삭제/재생성하지 않는다.

## 설치 전 검토 자료 — 이 문서는 운영 실행 승인이 아니다

기존 운영 담당 한 곳에서 기존 시간표/안전 배포 절차로만 수행한다. 이 후보의 웹앱 main 병합은
native 설치나 receiver 활성화가 아니다. 다른 프로필 gateway나 별도 서비스로 우회하지 않는다.

1. 최신 정확 SHA CI·독립 검토, 실제 업무/agent drain, native gateway 소유자·PID·코드 판본을 확인한다.
   활성 세션이 있으면 보류한다. 강제 종료·lock 삭제·작업창 시각 변경은 하지 않는다.
2. native 소유자의 기존 config/구독/relay 코드와 파일 권한·SHA를 private0600 백업에 기록한다.
   구독이 없던 사실도 기록한다. 웹앱 운영자에게 native token을 넘기지 않는다.
3. 검토된 정확 후보 script만 native 소유
   `~/.hermes/profiles/lumi/scripts/hermes-webhook-intake.py`(0600)에 설치한다.
   기존 `~/.hermes/office-relay/code/hermes-board-relay.py`를 덮어쓰지 않고 판본/권한을 대조한다.
   `profiles/lumi/webhook-intake/pending-review`는 native 소유0700으로 사전 생성한다.
   새 조상 디렉터리는 native 소유이며 symlink나 group/other write가 없어야 한다.
4. default config의 다른 키를 보존하며 아래 후보 overlay를 검토한다.
   Lumi 자체 receiver는 disabled로 보존한다.

```yaml
gateway:
  multiplex_profiles: true
platforms:
  webhook:
    enabled: true
    extra:
      host: 127.0.0.1
      port: 8644
      max_body_bytes: 16384
      rate_limit: 5
      script_timeout_seconds: 5
```

5. 기존 전역 구독에 같은 이름이 없음을 확인한 뒤 **default** CLI에서
   `hermes webhook subscribe heobrain-review-intake --route-profile lumi --events inquiry --deliver log --script hermes-webhook-intake.py`
   를 사용한다. CLI 출력에는 secret이 있으므로 사전 생성한 private0600 파일로만 받아
   터미널/로그에 표시하지 않는다. 이미 존재하는 구독은 삭제/재생성하지 않고 일단 중단한다.
   native CLI의 잠금/CAS helper로 이 구독에만 `toolsets: [web]`를 설정한다. terminal/file/code 도구를
   켜지 않는다. 완성된 config/subscriptions를 `check_candidate(default, lumi, subscriptions)`로
   읽기 검증한다. 이 함수는 설정을 쓰거나 서비스를 켜지 않는다.
6. 동일 운영 담당이 drain/백업 재확인 뒤 default gateway만 정상 재시작한다. 재시작은 이 후보
   작업에서 수행하지 않았다. loopback bind·health·기존 플랫폼 정상 상태·소유자·새 PID를 확인한다.
7. private 합성 요청으로 정상 서명/잘못된 토큰/만료/중복/다른 profile/한도 초과를 확인한다.
   pending 파일의 단일성·0600·정확 tenant/board를 확인한다. 실제 보드·모델·Slack 전송은0이어야 한다.
8. 실패하면 같은 담당이 기록된 이전 판본과 현재 변경의 일치를 확인하고 이번 후보 키·구독만
   되돌린 뒤 정상 재시작한다. 다른 작업의 변경이 있으면 자동 복원하지 않는다. pending 증거는
   삭제하지 않는다. 공개 포트·Funnel·Caddy는 이 절차에서 변경하지 않는다.

## 기존 업무판 연결의 정확한 차단

현재 relay.create는 Lumi coordinator에 실행할 일을 만들며 "사용자가 요청한 업무"라는
본문 계약을 따른다. held/unassigned/review-only 생성 인터페이스가 없어 외부 사건을 직접
연결하지 않는다. 현재 pending 파일은 3D 업무판/UI에 보이지 않는다. 사람이 외부 출처와
개인정보를 검토해 실제 내부 업무로 요청하는 다음 단계는 별도 범위다. 이 후보는 인간 승인⓪①②③을
기록하거나 대행하지 않으며, native global receiver 활성·Tally 실연결·운영 E2E도 완료하지 않았다.

검사: backend에서 `python -X utf8 -m pytest -q tests/test_hermes_webhook_intake.py`.
