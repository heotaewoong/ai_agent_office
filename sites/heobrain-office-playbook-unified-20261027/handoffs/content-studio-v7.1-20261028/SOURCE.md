# 콘텐츠 스튜디오 v7.1 · 정본과 업데이트

이 폴더는 2026-10-28 검토한 문서 인계 스냅샷이다. 실행 앱이나 연결된 자동 발행기가 아니다.

- HTTPS: [콘텐츠 스튜디오](https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-studio/)
- Sites project_id: `appgprj_6adf947030f48191b1332eff1c396042`
- 배포 소스 commit: `d3924cb875c7632e7d7f0f42db0733fe1ae10d77`
- 배포 version_id: `appgprj_6adf947030f48191b1332eff1c396042~appgver_05ae7b47e9708191afff363ca8f5f699`
- 접근: 기존 본인 전용 설정 유지. 이 문서 링크가 접근 권한을 추가하지 않는다.

## 먼저 읽기

[README](README.md) → [통합안](master-guide.md) → [도구 비교](models-and-rights.md) → [파이프라인 계약](pipeline-blueprint.json).
실제 읽은 PDF 근거는 [읽기 범위](pdf-design-evidence.md), 원가 선택은 [제작 경로](production-economics.md), 상품·채널은 [HeoBrain 연결](brand-fit.md)을 읽는다.

## 고칠 정본

웹 소스의 정본은 같은 Sites project_id의 연결된 소스 저장소다. 이 폴더의 다운로드 사본만 고쳐 최신 사이트와 다른 결정을 남기지 않는다.

1. 실제 오피스 AGENTS·OFFICE_INDEX·README와 현재 Git 변경을 확인한다. 다른 작성자의 변경을 보존한다.
2. Sites 스킬을 읽고 `get_site`로 최신 버전·접근 범위를 확인한다.
3. 같은 Site의 `create_source_repository_write_credential`과 source helper로 최신 소스를 연다. 키는 세션 메모리와 stdin으로만 전달한다.
4. `content-studio/content.json`·`master-guide.md`·`README.md`·검토 문서가 정본이다. 화면은 `dist/content-studio/`, 생성기는 `scripts/build-content-studio.py`다.
5. 원본을 고친 뒤 생성기·JavaScript 구문·`scripts/validate-content-studio.py`·실제 화면을 확인한다.
6. 최신 원격 변경과 병합하고 같은 Site ID·접근 범위로 게시한다. 새 문서 snapshot을 만들면 manifest·이 폴더·상위 README·OFFICE_INDEX의 링크와 검증 상태를 함께 갱신한다.

실제 앱 개발은 현행 EC2 정본과 앱 README를 따른다. 이 문서 작업으로 WSL 서비스·새 예약·병렬 gateway를 켜지 않는다.

## 검증과 남은 일

- 현재 구현: 기존 오피스 기획⓪·원고①·출고②의 코드, 이번 정적 설명 사이트와 문서 인계.
- 이번 검증: 요청명29개 대응·35도구·12단계·28아이디어·21소스·PDF56개/3,205쪽 감사. PDF10종 중96쪽 선택 읽기. 문서 구조·개인정보 제외·링크·해시·ZIP 검사121개 통과. HTTPS 배포·실제 ZIP 다운로드 확인.
- 계획/제안: 새 제공자 비교, 소스 수집 운영, ③ 회차 발송, 상품 오퍼·쿠폰 계약, 채널 게시 연결.
- 미실행: 새 모델 생성·유료 호출·계정 연결·발행·발송·쿠폰/주문 변경. 품질 우승자·매출 효과 없음.

`manifest.json`은 원 다운로드18문서의 해시를 검증한다. 이 SOURCE.md는 저장소 인계 안내를 위해 추가한 파일이다.
