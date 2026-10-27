# HeoBrain AI 오피스 통합 플레이북 (정적 사이트)

세 사이트(complete/#learning-expansion · source-kits/#top3 · ai-office-benchmarks-20261020), `database/` 마크다운 33개, 외부 오픈소스 129개를 합친 플레이북입니다. 빌드 과정 없이 `dist/` 폴더를 그대로 게시하면 됩니다.

## 파일 구조

| 파일 | 내용 | 고칠 때 |
| --- | --- | --- |
| `dist/index.html` | 웹 버전 본문(섹션 제목·설명 문장) | 문장·섹션 순서 |
| `dist/styles.css` | 밝은 고대비 테마, 색은 맨 위 `:root` 변수 | 색·글꼴·간격 |
| `dist/data.js` | 표·목록 데이터 `window.PLAYBOOK` (오픈소스 129, 기능 260, 코드 후보 30 등) | 항목 추가·수정 |
| `dist/app.js` | 데이터를 화면에 그리는 코드, 검색·필터, 인쇄 | 동작 |
| `dist/document.html` | 문서 버전(한 단, 인쇄·PDF용) | 문서 문장 |
| `dist/downloads/heobrain-office-playbook.md` | 문서 버전 Markdown | 문서 문장 |
| `dist/downloads/ai-content-agent-*.md` | AI 콘텐츠 에이전트 v6 근거 보고서·설계서·구현 계획 사본(원본은 `reports/`, `docs/superpowers/`) | 원본을 고친 뒤 다시 복사 |

전체 최종 문서 목록은 저장소 루트의 `OFFICE_INDEX.md`에 있습니다.

## 게시

- ChatGPT Sites: 다른 사이트와 같이 `dist/`를 정적 디렉터리로 게시합니다(`.openai/hosting.json`은 게시할 때 생성됨).
- 다른 정적 호스팅(Vercel, Netlify, GitHub Pages)도 `dist/`만 올리면 됩니다.
- 로컬 확인: `python3 -m http.server -d dist 8080` 후 http://localhost:8080

## 범위

조사·설계 문서입니다. 외부 키트 설치·실행, 유료 API 호출, 계정 연결은 하지 않았습니다. 개인 학습 PDF·강의 원본·개인 드라이브 링크는 넣지 않았습니다.
