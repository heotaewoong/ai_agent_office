# OpenAI 이미지 배경 구현 계획

설계서: `docs/superpowers/specs/2026-10-28-openai-image-background-design.md`. 각 Task는 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.

### Task 1: 이미지 제공자 `office/image_provider.py`
- [x] 실패 테스트 `tests/test_image_provider.py`: 미승인 거부, 키 없음 거부, 성공 시 PNG·영수증·정산, 재호출 없는 재사용, HTTP 오류는 unknown 예약 유지, 사용량 누락은 unknown, 업무 하위한도 초과 거부, 승인 외 장면 거부.
- [x] 구현: `ImageProvider(store, job_id, allow_paid, transport)`, `background(scene_index, out_path)`, `make_openai_background_renderer`.
- [x] `cd apps/content-office/backend && .venv/Scripts/python -m pytest tests/test_image_provider.py -q`

### Task 2: 프로필 선택 `office/image_selection.py`
- [x] 실패 테스트 `tests/test_image_selection.py`: 기본 `none`, 선택이 예산을 바꾸지 않음, 미등록 프로필 거부, 승인 전 렌더러 거부.
- [x] 구현: `PROFILES`, `profile_summary`, `select_profile`, `background_renderer_for_job`, CLI.

### Task 3: 합성과 계약 `office/media.py`
- [x] 실패 테스트(`tests/test_media.py` 추가): 배경 있는 `draw_scene`이 1080×1920 PNG와 `background_sha256`을 남김, 배경 렌더러 유무로 `production_contract` 해시가 다름, `render_short`가 장면마다 배경 렌더러를 호출.
- [x] 구현: `draw_scene(..., background=None)`, `production_contract(..., image_renderer=None)`, `render_short(..., background_renderer=None)`, `produce`의 카드·영상 출력에 전달.

### Task 4: API와 문서
- [x] `api.py` 대시보드 `provider.image`, 제작 요청 계약에 이미지 렌더러 반영.
- [x] README에 이미지 프로필 선택 명령과 `OPENAI_API_KEY` 설명.
- [x] 전체 검사: 백엔드 pytest, 프런트 typecheck·test.
