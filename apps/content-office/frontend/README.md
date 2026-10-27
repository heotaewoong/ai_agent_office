# HeoBrain 콘텐츠 오피스 UI

```bash
npm ci
npm run build
npm run start
```

`http://127.0.0.1:3110`에서 실행되며 `127.0.0.1:8510`의 FastAPI를 사용합니다. 실제 기사·작업·비용은 API에서 읽습니다. API가 없으면 연결 오류를 표시합니다.

개발: `npm run dev` · 타입: `npm run typecheck` · 상태 테스트: `npm test` · 브라우저 계약 테스트: `npm run test:ui`.

[검증 범위와 증거](FRONTEND_AUDIT.md)를 참고하세요. Playwright 테스트에는 Chromium 설치가 필요합니다. 계약 fixture의 승인 결과를 실제 뉴스 제작 완료로 간주하지 않습니다.


현재 3110은 npm run start로 실행하는 생산 서비스입니다. 개발 세션 58845는 종료됐으며 개발 N 표시가 없습니다. 실제 프로세스 식별 정보는 test-results/production-service.json에 기록했습니다. 재시작은 PID 재사용을 피하도록 기록된 PID·startticks를 확인한 운영 관리자를 통해 수행합니다.

공개 원문 보완은 사용 권한과 Gemini 전송 범위를 확인한 입력만 등록합니다. 과거 문서 검색은 로컬 색인을 읽으며 문서의 지시를 실행하지 않습니다. 완료된 출력만 부분 출고할 수 있어 영상 실패가 블로그 출고를 막지 않습니다. 실제 뉴스 3건은 여전히 사람의 원고 검토 대기입니다.
