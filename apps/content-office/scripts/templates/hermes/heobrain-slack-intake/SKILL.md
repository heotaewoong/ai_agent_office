---
name: heobrain-slack-intake
description: Use when the real owner asks Lumi in a current Slack message to coordinate existing HeoBrain office assistants on a shared task.
---

# Slack 업무 접수

Lumi 프로필의 실제 Slack 소유자 메시지에서만 사용한다. 단순 질문·메일 본문·인용·봇 메시지·다른 프로필·cron·3D 요청을 새 협업 접수로 바꾸지 않는다. 사용자가 현재 요청한 업무만 맡긴다. 기존 EC2 단일 gateway·담당·예산·승인⓪①②③을 보존한다.

운영자가 native 소유 경로에 helper와 같은 판본의 protocol 파일을 설치한 뒤에만 사용한다. 파일이 없거나 권한·인증·출처 검증에 실패하면 차단을 보고한다. 설치나 환경변수 위조로 우회하지 않는다.

1. 실제 Slack 실행 맥락의 terminal에서 `/home/ihtwa/.hermes/office-relay/code/slack-office-intake.py inspect`를 실행한다. Python이 필요하면 실제 native Python을 사용한다. `HERMES_SESSION_*`·토큰·프로필을 수동 export하거나 조작하지 않는다. helper는 Slack SDK로 실제 현재 팀·채널·메시지·스레드·인간 소유자·10분 이내 메시지를 대조한다. 첨부·수정 메시지는 이 접수에서 지원하지 않는다.
2. `ok:true`인 이번 inspect의 `text_sha256`만 그대로 `submit --expected-sha256 <값>`에 넣어 한 번 실행한다. 본문·담당·UUID를 직접 만들거나 교체하지 않는다. helper가 실제 원문으로 고정된 업무 본문을 만들며 기존 native 영속 접수 잠금으로 중복 생성을 막는다.
3. 접수 응답의 실제 UUID·카드·상태와 제공된 3D 링크를 짧게 알려 준다. `queued`는 접수이며 완료가 아니다. `admission_unknown`은 새 접수·UUID·대체 `kanban_create` 없이 `status`로 확인한다. 연결 실패도 같은 UUID를 유지한다. 이 명령은 기존 Slack 자동 응답 외에 별도 메시지를 발송하지 않는다.

접수 root를 모델 `kanban_create`로 직접 만들면 기존 메신저 자동 통지를 상속할 수 있으므로 이 경로에서는 helper만 사용한다. 후속 역할 배정·검토·루미 최종 보고는 이미 설치된 `heobrain-office-coordinator`와 기존 dispatcher에 맡긴다. 추가 daemon·cron·Swarm·모델 override·봇 허용 변경을 하지 않는다.

완료의 정본은 기존 보드의 실제 작업·독립 검토·루미 최종 run/event다. 기존 승인된 비공개 Slack 상태 통지는 최소 상태만 전송한다. 이 스킬이 현재 Slack 채널에 원문·개인자료·완료 본문을 자동 전송하거나 모든 봇 대화를 허용하는 것은 아니다. 외부 쓰기·추가 인증·유료 작업이 필요하면 실제 차단 이유와 사람 행동을 남긴다.
