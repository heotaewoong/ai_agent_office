# HeoBrain 오피스 월드

콘텐츠 오피스의 작업 상태를 우주에 떠 있는 마인크래프트식 블록 땅 위의 마을로 보여주는 정적 3D 공간입니다. 가운데 광장이 공유 기억, 돌 블록 길로 이어진 방 다섯 개가 오피스 단계입니다. 설계는 [설계서](../../docs/superpowers/specs/2026-10-28-office-world-design.md), 구현 순서는 [계획](../../docs/superpowers/plans/2026-10-28-office-world.md)에 있습니다.

승인(⓪ 기획 선택 · ① 원고 · ② 출고 · ③ 회차)은 콘텐츠 오피스 앱에서 사람이 합니다. 이 공간은 상태를 보여주기만 하며 승인을 만들거나 대신하지 않습니다.

## 로컬에서 보기

빌드 도구가 없습니다. 정적 서버로 폴더를 열면 됩니다. 파일을 더블클릭해 `file://`로 열면 `data/space.json`을 읽지 못합니다.

```sh
cd sites/office-world
python -m http.server 8080
# 브라우저: http://127.0.0.1:8080/
```

- **관제 시점**(기본): 드래그 회전, 휠 확대, 섬·뇌 클릭으로 작업 패널.
- **걷기 시점**: M 키 또는 상단 버튼. WASD 이동, Shift 달리기, Space 점프, 드래그 시선, 동료 가까이에서 E, R 카메라 복귀. 휴대폰에서는 관제 시점만 제공합니다.
- 외부 자원은 Babylon.js(cdnjs, 7.54.0 고정)와 Google Fonts뿐입니다.

## 데이터

`data/space.json`이 공간 투영 v1 예시입니다. 항목 모양은 설계서 6장을 따릅니다. 실시간으로 바꾸려면 같은 모양을 돌려주는 주소를 지정합니다.

### 실시간 모드

- **앱 안**: `/world/index.html?api=/api/space&embed=1` (메뉴 "오피스 월드"). 콘텐츠 오피스 백엔드의 `GET /api/space`(읽기 전용, 승인을 만들지 않음)가 투영을 돌려줍니다.
- **단독 실행**: `index.html?api=https://서버/api/space` — 다른 도메인의 단독 페이지는 지금 `/api/space`를 읽을 수 없습니다(백엔드가 앱 자신의 origin만 받습니다). 지원하는 경로는 앱 안의 `/world/` 경로이거나, 리버스 프록시로 정적 사이트와 `/api/space`를 같은 origin에서 서빙하는 것입니다.
- 또는 `index.html`의 `app.js` 앞에 `<script>window.OFFICE_WORLD_API = '/api/space';</script>`

실시간 모드는 10초마다 다시 읽고, 실패하면 마지막 상태를 유지한 채 상단에 표시합니다. 예시 모드에서만 동료가 기억을 확인하러 걷는 연출이 돕니다.

투영에는 제목·상태·담당 이름만 넣습니다. 원문, 비밀값, `database/learning-private/`·`database/class101/`·`PRIVATE` 자료의 경로는 넣지 않습니다.

## 다른 UI와 연결하기 (협업자용)

이 공간은 데이터 파일 하나만 읽는 정적 페이지라서, 어떤 백엔드든 같은 모양의 JSON을 내놓으면 연결됩니다.

1. **투영 API 만들기 (완료: `GET /api/space`, 구현은 `apps/content-office/backend/office/space.py`)** — 설계서 6장의 "공간 투영 v1" 모양으로 `GET /api/space`를 제공합니다. 예시는 `data/space.json`입니다. `stages[]`(방), `agents[]`(동료), `events[]`(자막), `flows[]`(길 위 흐름), `brain`(중앙 기억)만 채우면 됩니다. 방 수·이름·색은 데이터가 정하므로 코드 수정이 필요 없습니다.
2. **주소 지정** — 페이지를 `index.html?api=https://내-서버/api/space`로 열거나, `app.js` 앞에 `window.OFFICE_WORLD_API`를 넣습니다. 다른 도메인이면 그 API에 CORS 허용이 필요합니다.
3. **내 화면 안에 넣기** — `<iframe src=".../office-world/index.html?api=..." allow="fullscreen">`로 임베드할 수 있습니다. 방 패널의 "오피스에서 열기"는 각 `stages[].url`로 새 탭을 엽니다.
4. **상태 조회·제어** — 페이지 전역 `window.__officeWorld`에 `space`(현재 데이터·선택), `controls`(`focusStage`, `enterStage`, `exitSpace`, `setView`), `hud`(`openStage`, `closePanel`)가 있습니다. 같은 origin에서 iframe의 `contentWindow.__officeWorld`로 접근할 수 있습니다. 공개 계약은 투영 JSON이며, 이 핸들은 보조 수단입니다.

투영에 넣는 값만 화면에 나옵니다. 공간은 진행률·완료를 추정하지 않고, 승인 상태를 바꾸는 요청도 보내지 않습니다.

## EC2 배포

Nginx 정적 호스팅 예시입니다. Amazon Linux 2023 기준.

```sh
sudo dnf install -y nginx
sudo mkdir -p /var/www/office-world
sudo cp -r sites/office-world/* /var/www/office-world/
```

`/etc/nginx/conf.d/office-world.conf`:

```nginx
server {
    listen 80;
    server_name _;
    root /var/www/office-world;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # 실시간 모드: 콘텐츠 오피스 백엔드의 투영 API만 노출
    # location = /api/space {
    #     proxy_pass http://127.0.0.1:8510/api/space;
    # }
}
```

```sh
sudo nginx -t && sudo systemctl enable --now nginx
```

보안 그룹에서 80(HTTPS를 쓰면 443)만 엽니다. HTTPS는 ALB 인증서나 certbot을 사용합니다. 투영 데이터에 비공개 정보가 없을 때만 공개 주소에 올립니다. S3 정적 웹 호스팅이나 CloudFront에 올려도 같은 파일이 그대로 동작합니다.

## 검증

```sh
node --check sites/office-world/app.js
```

화면 검사는 `apps/content-office/frontend`에 설치된 Playwright Chromium으로 페이지를 열어 콘솔 오류, 섬 카드 5개와 뇌 카드, 시점 전환, 패널 열기, 1366×768·390×844 가로 넘침을 확인합니다. 카드·자막에 "게시됨"·"자동 게시" 문구가 없어야 합니다.
