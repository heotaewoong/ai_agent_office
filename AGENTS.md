# AI 작업자 안내 (Codex · Claude · Gemini · Hermes 공통)

1. 작업을 시작하기 전에 `OFFICE_INDEX.md`를 읽는다. 최종 문서, 링크, 바꾸지 않는 결정, 공개 금지 자료가 정리돼 있다.
2. 최종 문서를 새로 만들거나 바꾸면 같은 작업 안에서 `OFFICE_INDEX.md`의 표와 "마지막 갱신" 날짜를 고친다.
3. 승인 단계는 ⓪ 기획 선택 · ① 원고 · ② 출고 · ③ 회차(뉴스레터·홍보 발송)다. 의미를 바꾸지 않고, 에이전트가 승인을 만들지 않는다.
4. `database/learning-private/`, `database/class101/`, 파일명에 `PRIVATE`가 있는 자료는 공개 산출물에 넣지 않는다.
5. 앱 작업은 `apps/content-office/README.md`를 따른다. 백엔드 테스트: `cd apps/content-office/backend && .venv/bin/python -m pytest -q`. 화면: `cd apps/content-office/frontend && npm run typecheck && npm test`.
6. 설계서·구현 계획은 Superpowers 형식으로 `docs/superpowers/specs/`, `docs/superpowers/plans/`에 둔다.


## 3D 오피스 지속 개선 — 2026-10-29 사용자 지시

- 국내외 공식 근거를 계속 조사하고 이 프로젝트에 붙일 기능 Top5와 다음 작은 구현을 갱신한다. 전체 인터넷 전수 확인·실행하지 않은 기능의 성공을 주장하지 않는다.
- 넓은 지상 미래도시·공중 팀 도시, 무료 차량 접근과 기존 포획/보유/크레딧 기록, 사람 승인⓪①②③을 보존한다.
- 편의 기능·캐릭터/건물 품질과 함께 리팩토링·최적화를 수행하되 실사용 근거 없는 코드 증설은 하지 않는다. 기존 코드/표준 기능/설치된 의존성을 먼저 재사용한다.
- 코드·모델·음원·폰트 이용조건을 각각 확인하고 필요한 도구/MCP를 선택한다. 설치·최고 화질·FPS·Mac/모바일 검증 여부를 구분한다.
- 연구·구현·단위검사·브라우저·GitHub·서버·실제 AI 실행을 분리해 기록한다. 새로운 조사/제안/결과 문서는 상위 사용자 지시의 작업공간 output/을 사용한다(기존6번의 신규 문서 경로보다 우선). 기존 파일은 일괄 이동하지 않는다.
