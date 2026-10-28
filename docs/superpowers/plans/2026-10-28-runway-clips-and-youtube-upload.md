# Runway 생성 장면 · YouTube 비공개 업로드 구현 계획

설계서: `docs/superpowers/specs/2026-10-28-runway-clips-and-youtube-upload-design.md`. 각 Task는 테스트를 먼저 쓰고 실패를 확인한 뒤 구현했다.

### Task 1: Runway 클립 제공자 `office/video_provider.py`
- [x] 실패 테스트 `tests/test_video_provider.py`: 미승인·키 없음 거부, 지정 장면만·최대 3개, 성공(폴링·다운로드·크레딧 정산·재사용), gen4.5 예약과 업무 한도, FAILED 영수증, 미해결 → 불명·재제출 차단, 생성 HTTP·네트워크 오류, 비MP4 산출물 검토, 경로 검사.
- [x] 구현: `ClipProvider`, `make_runway_clip_renderer`, `generated_scene_indexes`.

### Task 2: 프로필 `office/video_selection.py`
- [x] 실패 테스트 `tests/test_video_selection.py`: 기본 `none`, 선택 무료, 승인·영상 선택·지정 장면 조건.
- [x] 구현: `PROFILES`, `profile_summary`, `select_profile`, `clip_renderer_for_job`, CLI.

### Task 3: 조립 `office/media.py`
- [x] 실패 테스트: 투명 오버레이 `draw_scene(overlay_only=True)`, `clip_command` 인자, `production_contract(clip_renderer=)`는 영상 선택에서만, `scene_clip`은 배경 없이는 유료 호출 전 거부.
- [x] 구현: `scene_clip`, `clip_command`, `render_short(clip_renderer=)`, `produce(clip_renderer=)`, manifest `clips`·경고. `worker.py`·`api.py` 계약 반영.

### Task 4: YouTube 어댑터 `office/youtube_delivery.py`
- [x] 실패 테스트 `tests/test_youtube_delivery.py`: ② 없이 거부, OAuth 없음 거부, 비공개 업로드·장부·멱등, 5xx 불명·재전송 차단, 시작 네트워크 불명·403 실패 후 재요청, 308 이어 올리기·상태 확인, 공개 범위 불일치, 변경된 파일 거부.
- [x] 구현: `deliver_youtube`, `reconcile_youtube`, `deliveries`, `video_metadata`, CLI.

### Task 5: API·문서·전체 검증
- [x] `api.py`: `GET /api/jobs/{id}/deliveries`, `POST /api/jobs/{id}/deliveries/youtube`, `POST .../{delivery_id}/reconcile`, 대시보드 `provider.clip`·`provider.youtube`. 테스트 `tests/test_api.py`.
- [x] README: 생성 영상 프로필, YouTube 비공개 업로드, 환경변수 표, 결과 파일 표.
- [x] 전체 검사: 백엔드 pytest, 프런트 typecheck·test.
