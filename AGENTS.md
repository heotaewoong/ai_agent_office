# AI 작업자 안내 (Codex · Claude · Gemini · Hermes 공통)

1. 작업을 시작하기 전에 `OFFICE_INDEX.md`를 읽는다. 최종 문서, 링크, 바꾸지 않는 결정, 공개 금지 자료가 정리돼 있다.
2. 최종 문서를 새로 만들거나 바꾸면 같은 작업 안에서 `OFFICE_INDEX.md`의 표와 "마지막 갱신" 날짜를 고친다.
3. 승인 단계는 ⓪ 기획 선택 · ① 원고 · ② 출고 · ③ 회차(뉴스레터·홍보 발송)다. 의미를 바꾸지 않고, 에이전트가 승인을 만들지 않는다.
4. `database/learning-private/`, `database/class101/`, 파일명에 `PRIVATE`가 있는 자료는 공개 산출물에 넣지 않는다.
5. 앱 작업은 `apps/content-office/README.md`를 따른다. 백엔드 테스트: `cd apps/content-office/backend && .venv/bin/python -m pytest -q`. 화면: `cd apps/content-office/frontend && npm run typecheck && npm test`.
6. 설계서·구현 계획은 Superpowers 형식으로 `docs/superpowers/specs/`, `docs/superpowers/plans/`에 둔다.
