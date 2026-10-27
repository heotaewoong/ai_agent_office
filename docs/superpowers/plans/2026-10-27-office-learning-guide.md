# Office Learning Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** 자료를 사설 DB로 정리하고 실제 구현과 도입 계획을 구분하는 초보자용 HTTPS 파이프라인 가이드를 제공한다.

**Architecture:** 사설 자료함·출처 원장·로컬 SQLite FTS와 독립적인 정적 설명 사이트를 만든다. 기존 오피스 앱은 변경하지 않는다.

**Tech Stack:** Python SQLite/PyMuPDF/OCR, buildless HTML/CSS/JS, Sites owner-private hosting.

**Spec:** `research/office-learning-2026-10-27/design.md`

## Global Constraints

- 사설 원문·코드·책·강의 첨부는 사이트 패키지에서 제외한다.
- 원본은 덮어쓰지 않는다. 새 구매·구독·DRM 변환·모델 파인튜닝 없음.
- 자료 목록·본문 추출·의미 검토·실행 검증을 별도 상태로 표시한다.
- 실제 콘텐츠 앱 기능과 제안한 29분야 실행을 구분한다.

## Review Focus

- 이미지 PDF: 텍스트 0자를 학습 완료로 표시하지 않는다.
- Drive 문서 검색의 ZIP/code 누락: 파일 목록으로 보완한다.
- CLASS101 비로그인: 계정 전체 누락 대조 완료로 표시하지 않는다.
- 모바일·키보드·검색 결과 0건: 읽기와 이동이 가능해야 한다.
- private hosting: 사이트에 원본 자료나 임시 인증 URL이 섞이지 않아야 한다.

### Task 1: 자료 확보·출처·검색

- [ ] 지정한 Drive 폴더 목록과 실제 파일을 사설 원장에 기록한다.
- [ ] PDF/OCR와 가져온 텍스트를 원본 참조와 연결한다.
- [ ] 로컬 SQLite FTS에 문서·페이지·자료 상태를 저장하고 검색 결과를 확인한다.
- [ ] 저장 경로·추출 누락·실제 읽은 범위를 검증한다.

### Task 2: 내용과 화면

- [ ] 6개 상세 업무·29분야 매핑·도구·시작 순서를 `sites/office-pipeline-guide-20261027/dist/`에 작성한다.
- [ ] 검색·분야 선택·상세 단계·빈 결과·인쇄를 동작시킨다.
- [ ] 로컬 데스크톱·모바일 브라우저로 구조·클릭·가로 넘침·콘솔 오류를 확인한다.

### Task 3: 배포·인계

- [ ] `dist/`를 검토해 사설 자료·인증값 제외를 확인한다.
- [ ] Sites source helper로 정확한 소스를 push/package하고 private 배포한다.
- [ ] 배포 성공 응답의 실제 HTTPS URL과 로컬 DB/분석 범위를 보고한다.
