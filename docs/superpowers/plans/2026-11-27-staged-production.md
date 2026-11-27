# 나눠 만들기 구현 계획 (2026-11-27)

1. [x] 시험 먼저: `tests/test_production_stages.py`(그래프 멈춤과 재개, 영상만, 실패 인수인계, 실제 ffmpeg 두 단계, 유료 확인 위치)
2. [x] `media.produce(defer_video)`와 `deferred` 상태, 완성본 안내 문구
3. [x] `store.save_manifest_if_current`, 작업 결과의 `partial`에서 `deferred` 제외
4. [x] `office/production_graph.py`와 worker 연결(영상 단계에서만 유료 클립 확인과 썸네일 그림)
5. [x] API `stage=video`, 예상 비용 기본값, 승인① 자동 제작에서 영상 비용 확인 생략
6. [x] 화면: 승인① 안내, 제작·출고함 영상 만들기, `영상 만들기 대기` 표시, `lib/workflow.ts` 규칙과 시험
7. [x] 기본 선택에 카드뉴스, architecture.json 5판, README
8. [ ] EC2 전체 시험과 배포, 배포 뒤 실제 화면 확인
