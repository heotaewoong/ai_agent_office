# HeoBrain 콘텐츠 자동화 · 정본과 보조 작업실 인계

2026-10-28 Site version10 / source `8c6bfca18b48f3a5868431104e4ec878069d8f7e`의 검토 스냅샷이다.

- [최신 통합 설계](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/#content-system): v7.2 ·49도구·38입력·79요구 대조.
- [자료·원가·실습 작업실](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-studio/): 35세부도구·21선별출처·28아이디어·PDF 감사·가정 계산.
- 기존 본인 전용 접근을 유지했다. URL·소스 ZIP은 새 로그인/게시 권한이 아니다.

> 이 스냅샷의 숫자·기본값 표기 오류와 감사 이후 앱 변경은 [정오표](ERRATA.md)에 정리했다. 원문보다 정오표를 먼저 읽는다.

## 읽는 순서와 정본

[README](README.md) → [상위 설계 스냅샷](integrated-guide.md) → [세부 제작 검토](master-guide.md) → [파이프라인 계약](pipeline-blueprint.json).
전체 설계의 정본은 같은 Sites 연결 저장소의 `content-system/source.json`이다. 이 폴더의 integrated-guide.json/md는 읽기용 사본이다.
보조 원본은 연결 저장소의 `content-studio/content.json`, `cost-scenarios.json`, Markdown·research 문서다. 가격·권리·API 조건을 바꾸면 정본과 세부 비교를 함께 대조한다. 두 목록의 항목 수는 범위가 달라 합산하지 않는다.

## 다른 모델에서 편집·미리보기

[편집 소스 README](editable-source/README.md)는 이번 보조 작업실의 실제 코드·데이터·생성기·검산을 포함한다. Python3.11+와 Node18+에서 별도 패키지 없이 실행한다.

```text
cd editable-source
python scripts/build-content-studio.py
node scripts/check-content-costs.cjs
python scripts/validate-content-studio.py
python -m http.server 8769 --bind 127.0.0.1 --directory dist
```

http://127.0.0.1:8769/content-studio/ 에서 확인한다. 기존 전체 플레이북은 HTTPS 링크로 열며 원문을 통째로 복제하지 않는다. SOURCE_MANIFEST.json은 배포 소스 ZIP55항목 중54개 파일의 원래 바이트 해시다. 파일/줄바꿈을 바꾼 뒤에는 생성물을 다시 만들고 새 manifest로 검증한다.

배포를 바꾸려면 실제 오피스 AGENTS·OFFICE_INDEX·README·현재 Git 변경부터 읽는다. Sites 스킬로 project_id `appgprj_6adf947030f48191b1332eff1c396042`의 최신 소스를 열고 변경을 병합한다. 과거 ZIP이나 이 저장소 사본으로 최신 원격을 덮어쓰지 않는다. 인증 정보는 파일·명령행·로그에 넣지 않는다. 상위 `handoff.study`가 세 보조 화면을 연결하므로 그 링크를 유지한다.

## 현재 구현·이번 검증·제안·남은 일

| 구분 | 상태 |
|---|---|
| 현재 구현 | 기존 기획⓪·원고①·출고② 코드 정적 확인. 이번 정적 안내·검색·경로 미리보기·가정 계산·문서/소스 내보내기 |
| 이번 검증 완료 | 상위 생성8파일 일치·범위 검사·회귀5개. 보조215검사·원가19검산. 소스ZIP 새 폴더 재빌드209검사·19검산. 실제 HTTPS의49도구·세 연결·계산·두ZIP 다운로드 해시 일치 |
| 자료 확인 | PDF56개·3205쪽 파일감사,10종229쪽 중96쪽 선택읽기. 새 공식PDF5개·87쪽. 구독도서 새PDF0. 원문은 이 폴더/소스 ZIP에서 제외 |
| 계획/제안 | 새 제공자 역할별 비교·자막/음향·공식 입력 운영·③회차·상품 오퍼·쿠폰·채널 연결 |
| 미구현/미검증 | 새 모델 생성·한국어 품질·실제 청구·계정 연결·개별 게시·발송·쿠폰/주문 쓰기. 품질 승자·매출 효과 없음 |

기본 추가 지출0, 실행/게시/발송/쿠폰 비활성, ⓪기획·①원고·②출고·③회차를 보존한다. 개인학습 PDF·회원자료·개인원고·계정·키·DB·개인 경로를 공개 인계에 넣지 않는다.

문서가 바뀌면 README·OFFICE_INDEX·공식 근거/확인일·manifest·검증 기록을 함께 갱신한다. 문서 다운로드는 계정 연결·유료 생성·운영 게시·발송·거래의 승인이 아니다.

Linux 추가 확인: Python 3.14.4에서 소스 사본 재빌드·209검사를 통과했다. Linux Node 검산은 PATH에 Node가 없어 실행하지 않았다. Windows Node19검산과 구분한다.
