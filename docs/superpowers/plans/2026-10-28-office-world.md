# 오피스 월드 1차 구현 계획

설계: `docs/superpowers/specs/2026-10-28-office-world-design.md` · 작성 2026-10-28

## 산출물

| 파일 | 역할 |
|---|---|
| `sites/office-world/index.html` | 페이지 뼈대, HUD 요소, 라이브러리 로드 |
| `sites/office-world/styles.css` | 색·글꼴 토큰, HUD·패널·미니맵 스타일, 휴대폰 대응 |
| `sites/office-world/app.js` | `data` · `world` · `hud` · `controls` 네 모듈 |
| `sites/office-world/data/space.json` | 공간 투영 v1 예시 |
| `sites/office-world/README.md` | 로컬 실행과 EC2 배포 |

## 작업 순서

1. **데이터 예시** — 다섯 섬, 동료 8명, 이벤트 10건, 흐름 3건. 상태 문구에 "게시됨"·"자동"을 쓰지 않는다.
2. **장면** — 우주 배경, 허브, 섬 배치(허브 둘레 등간격), 다리. 섬 수는 데이터에서 읽는다.
3. **가구와 캐릭터** — 벽·책상·모니터·의자·램프·식물·책장, 블록 캐릭터, 앉기·걷기 자세.
4. **두 시점** — 관제(궤도 카메라), 걷기(3인칭 추적, 섬·다리 위 이동 제한, 점프). M·R 키.
5. **HUD** — 투영 좌표로 섬 카드·뇌 카드 배치, 작업 패널, 자막 띠, 상단 바, 미니맵, 모델 태그.
6. **연출** — 실행 중 깜빡임, 흐름 점, 예시 모드의 기억 확인 걷기, 모션 줄이기.
7. **실시간 읽기** — `?api=` 또는 `window.OFFICE_WORLD_API`, 10초 폴링, 실패 시 예시 데이터 유지.
8. **검증** — 문법 검사, Playwright 화면 두 크기, 금지 문구 검사.
9. **문서** — README의 실행·배포 절차, 이 저장소 README의 공개 문서 목록에 링크 추가.

## 실행 방식

이 세션에서 직접 구현한다. 외부 패키지 설치 없음. 검증은 `apps/content-office/frontend`에 이미 설치된 Playwright를 재사용한다.
