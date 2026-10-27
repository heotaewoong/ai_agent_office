# 콘텐츠 파이프라인: 설계에서 현재 앱까지

이 앱은 RSS 기사 후보를 골라 근거가 붙은 한국어 원고를 만들고, 사람이 원고를 승인한 뒤 선택한 파일을 제작하는 로컬 작업실이다. 마지막 출고 승인 뒤 ZIP을 내려받아 직접 게시한다. 실제 뉴스3건의 사람 승인①은 대기 중이다. 합성 자료로 통과한 제작·출고 검증은 실제 뉴스 승인이나 사실성 검증을 대신하지 않는다.

기준일: 2026-10-26. 이 문서는 현재 소스와 저장된 검증 기록을 대조한 추적표다. 아래 테스트 경로는 기능 근거이며, 이 문서를 쓰면서 전체 앱 테스트를 새로 실행했다는 뜻이 아니다. 상세 재사용 배경은 [reference-reuse.md](reference-reuse.md)에 있다.

## 처음 사용하는 순서

1. ‘오늘의 뉴스’에서 날짜·공식 출처·선정 이유를 보고 최대3개를 고른다. RSS 수집 실패와 이전에 저장한 작업은 구분한다.
2. ‘작업실’에서 근거와 원고, Critique/Eval 결과를 확인한다. 새 원문의 자동 회수가 실패하면 사용할 권리가 있는 공개 본문을 입력할 수 있다. 입력 본문은 근거 추출·원고 생성 시 설정된 Gemini에 전달되므로 화면의 전송 안내를 확인한다. MD 지식 색인은 외부 모델에 전송하지 않는다.
3. 수정하면 새 판본으로 저장·재검수한다. 중대 오류가 남으면 승인할 수 없다. 완성 글·영상대본의 표현과 수치를 사람이 확인한다.
4. 승인①에서 블로그/영상/카드/PDF 선택을 확정한다. 영상은 블로그 게시 여부와 관계없이 선택할 수 있다.
5. 제작 뒤 완료된 파일과 실패한 항목을 구분한다. 완료된 출력만 고르는 화면과 API의 출고 선택 계약을 함께 구현했다. 영상을 출고할 때 실제 파일·음성·자막을 확인하고 썸네일5개 중 최종안을 고른다. 로컬 썸네일 점수는 가독성·대비·원고 표현 일치 제안이며 CTR 예측이 아니다.
6. 현재 제작물 중 선택한 완료 항목에 출고 승인②를 기록한 뒤 ZIP을 받는다. 티스토리·네이버·YouTube의 실제 계정/공개 범위/일정은 사용자가 각 플랫폼에서 확인한다. 앱은 외부 게시·메일·광고변경·판매를 실행하지 않는다.

작업 시간이 끝나면 새 유료 호출과 worker 작업을 보류한다. 대기·heartbeat·작업 완료는 서로 다른 상태다. 현재 세션은 이 PC의 로컬 운영자용이며 조직 계정 인증과 권한 분리를 제공하지 않는다.

## 실제 연결

| 단계 | 현재 코드 | 데이터·검사 | 남은 경계 |
|---|---|---|---|
| RSS/Atom → 최근 후보 | [feeds.py](../backend/office/feeds.py), [bootstrap.py](../backend/office/bootstrap.py) | 날짜·정규 URL·추적 URL·같은 이벤트 중복, batch 활성 기사ID, 원본 XML·실패 기록 | 공식 피드가 주는 후보 전체의 중요도/사실성을 보증하지 않음 |
| 기사 → 근거 묶음 | [evidence.py](../backend/office/evidence.py) | 공개 URL·본문 추출·원문 문단 위치/해시, 제공한 문단 인용 검사 | 단일 발행자 본문은 `independent_source_checked=false`, 독립 검증 미실시로 고정. 모델 추출/자기 점수는 사실 증명 아님 |
| 근거 → Gen | [editorial.py](../backend/office/editorial.py) `prepare_source` | 독자·rubric·근거·한계와 JSON schema를 실제 요청에 포함 | 현재 Gemini provider, 다른 공급사 자동 전환 없음 |
| Critique + Eval → Refine | `review_until_ready` | 두 호출은 같은 packet을 보되 서로 답을 받지 않음. 수정 최대2회, 매번 재검수 | 별도 호출이며 별도 회사/서로 다른 모델이라는 뜻은 아님 |
| 원고 승인① | [store.py](../backend/office/store.py) `review_source` | 현재 source_hash·검수 통과·선택 파일에 결속 | 사람이 허위로 검토했다고 누를 가능성까지 제거하지 않음 |
| 선택 제작 | [media.py](../backend/office/media.py), [exports.py](../backend/office/exports.py) | Windows 음성 브리지·FFmpeg·자체 도형/텍스트·MP4/SRT/PNG/블로그/PDF | legacy Windows pipeline은 호출하지 않음. 실제 뉴스 제작은 승인 대기 |
| 출고 승인② → ZIP | [api.py](../backend/office/api.py), Store `review_release` | manifest·파일 SHA 재검사, 완료 outputs만 출고·영상출고만 검토확인/썸네일 선택, `external_published:false` | 수동 전달 패키지. YouTube API/메일/예약 연결 없음 |
| 상태·재시작·시간 창 | [worker.py](../backend/office/worker.py), [runtime.py](../backend/office/runtime.py) | SQLite task/owner, OS flock, 옛 source 변경 방지, unknown 보존 | Hermes native runtime/cron/memory와 연결되지 않음 |
| 화면 | [page.tsx](../frontend/app/page.tsx), [workflow.ts](../frontend/lib/workflow.ts) | 현재 승인 판본·다른 작업의 늦은 응답·로컬 artifact URL 검사 | 다중 사용자 SaaS 인증은 별도 |

### 블로그와 영상의 독립성

원고 작성 때 블로그와 영상대본을 함께 만들 수 있지만, 블로그 공개가 영상 제작의 선행조건은 아니다. 영상 OFF이면 음성과 영상 렌더를 호출하지 않는다. 성공한 음성·파일은 다음 단계 실패에도 보존한다.

현재 `media.produce()`는 `output_status`와 `completed_outputs`, 파일별 `outputs`를 저장한다. 블로그가 완성되고 영상이 실패하면 성공 파일과 부분 manifest를 보존하고 `partial_release_review`로 넘긴다. 출고 승인②의 `outputs=["blog"]`로 완성된 블로그만 출고할 수 있다. 원고 hash와 승인①의 원래 제작 선택은 그대로 유지한다. 완료 부분만 출고하는 데 새 원고 승인은 필요하지 않다.

`Store.review_release()`는 요청한 제작 선택 중 실제 완료된 항목만 허용한다. 영상이 포함된 출고에만 썸네일 선택과 `media_reviewed` 확인을 요구한다. ZIP은 승인한 output 파일과 공통 권리 파일만 담고 영상 전용 파일을 제외한다. 모든 선택 항목이 실패하면 성공 manifest로 처리하지 않는다.

부분 출고의 화면/API 계약을 확인했다. 완료된 출력 선택을 확인창에 고정해 서버로 전달하며, 블로그만 출고하면 영상의 썸네일/청취 확인을 요구하지 않는다. 프런트 계약14검사와 실제 생산 모드4탭 확인이 통과했다. 최초 독립 문서 담당자의 관측 이후 root가 검증 결과를 반영했다.

근거: `tests/test_media.py::test_blog_can_be_released_independently_when_selected_video_fails`, `tests/test_api.py::test_blog_only_release_does_not_require_video_review_or_export_video_assets`. 이 회귀 테스트는 임시/합성 상태이며 실제 뉴스 제작 완료를 의미하지 않는다.

단일 발행자 원문을 모델이 읽었다고 독립 검증이 된 것은 아니다. `evidence.py`는 모델이 제안한 scope를 private 수집 보고서에만 남기고, 원고용 근거에는 발행자 주장·독립 검증 미실시를 강제한다. `tests/test_evidence.py::test_model_cannot_promote_a_single_publisher_body_to_independent_verification`이 이 경계를 검사한다. Critique/Eval의 높은 점수도 이 범위를 바꾸지 않는다.

## 과거 큰 파이프라인과 현재 범위

| 과거 방향 | 현재 연결 | 향후 또는 미연결 |
|---|---|---|
| 콘텐츠 공통원고 → 채널별 생성·평가 → 미디어 → 게시 | 근거/공통원고/독립 검수/선택 제작/수동 ZIP | legacy5채널별 독립 원고·평가 전체, LinkedIn/SMTP/YouTube 자동 전송 |
| all-in-one 총괄·연구·편집·QA·배포팀 | 업무 단계/이벤트와 UI 역할로 구분 | 18개 LLM을 상시 병렬 운영하거나 Paperclip/Hermes 실행 조직으로 연결한 상태 아님 |
| 마케팅/SEO/뉴스레터/리드 폐쇄루프 | 독자·hook·제목·영상 metadata·썸네일 후보를 편집 계약에 포함 | 광고 API·검색성과·캠페인·CRM·리드 수집·이메일 발송·ROI 측정 |
| 상품/PDF/쿠폰 → 주문·권한·정산 | 검토용 무료 PDF·권리 상태 파일 생성 | Marketplace 상품조회 adapter도 아직 없음. 가격/쿠폰/주문/권한/매출 변경 없음 |
| 지식/Obsidian → 업무 실행 | 111MD 로컬 검색·섹션·원문 SHA·계약 후보 | Obsidian 쓰기/메모리 자동 승격/유료 강의 수집/Hermes memory 연결 |

## 설계 계약 추적표

구현은 로컬 범위에서만 평가했다. ‘부분/향후/미연결’은 고장으로 단정하는 표지가 아니라 현재 경계다. 원문 증거는 아래 계약ID와 감사 JSON, 지식 색인의 정확 파일/섹션으로 연결한다.

| ID | 상태 | 실제 연결·한계 | 검사/참조 |
|---|---|---|---|
| C01 | 구현 | editorial.prepare_source → Store.review_source → media.produce. 승인 전 제작 차단 | `tests/test_workflow.py::test_unapproved_source_cannot_start_production; tests/test_media.py::test_production_refuses_unapproved_before_any_artifact` |
| C02 | 구현 | editorial.review_until_ready: Critique/Eval 별도 입력, Refine 최대2, 수정 후 둘 다 재검수 | `tests/test_editorial.py::test_critique_and_eval_never_receive_each_others_answers; test_refine_is_limited_to_two_and_critical_errors_block` |
| C03 | 구현 | 중대 지적·deterministic_checks 실패는 점수와 무관하게 차단 | `tests/test_workflow.py::test_critical_quality_issue_blocks_approval` |
| C04 | 로컬 범위 구현 | source_hash/선택과 manifest hash를 각각 승인. 계정·원격 일정 결속은 미연결 | `tests/test_workflow.py::test_changing_production_choices_invalidates_derivatives_and_release; tests/test_api.py::test_video_release_requires_thumbnail_choice_and_media_review` |
| C05 | 구현 | providers.cache_key에 실제 messages/schema/model/options; 미디어 별도 production_contract | `tests/test_editorial.py::test_model_cache_covers_actual_system_schema_and_options; tests/test_media.py::test_font_bytes_and_explicit_voice_configuration_change_production_contract` |
| C06 | 구현 | render_short 성공 음성 즉시 캐시·파일 hash, 이후 장면 실패에도 보존 | `tests/test_media.py::test_failed_scene_retains_successful_voice_for_retry` |
| C07 | 구현 | Store.save_source 기대 hash 비교, 옛 승인/manifest 해제, 최종 manifest CAS | `tests/test_workflow.py::test_source_change_invalidates_approval_and_derivatives; test_manifest_cannot_attach_to_changed_source` |
| C08 | 구현 | Next.js → FastAPI → SQLite tasks → 별도 office.worker | `tests/test_e2e_workflow.py::test_synthetic_http_worker_download_and_source_invalidation` |
| C09 | 부분 | 모델 cache-key 비용 예약/unknown 재호출 차단 구현. 외부 게시 intent·remote ID는 미연결 | `tests/test_budget.py::test_same_uncertain_model_call_cannot_reserve_again; tests/test_providers.py::test_lost_response_preserves_reservation_and_never_marks_success` |
| C10 | 구현 | 영상 OFF=0 음성/렌더. 영상 실패에도 완료 블로그의 부분 manifest·출고 outputs·ZIP 보존. 승인①은 유지 | `tests/test_media.py::test_blog_can_be_released_independently_when_selected_video_fails; tests/test_api.py::test_blog_only_release_does_not_require_video_review_or_export_video_assets` |
| C11 | 패턴 재구현 | legacy verified_state/send를 import하지 않음. 신규 Store 검증·실제 음성길이·수동 출고로 경계 재구현 | `tests/test_media.py::test_real_mp4_subtitles_thumbnails_and_manifest_are_bound_to_source; tests/test_api.py` |
| C12 | 구현 | 신규 PowerShell System.Speech 브리지로 Windows ko-KR 음성 생성. 유료 fallback 없음 | `tests/test_media.py::test_unavailable_korean_voice_does_not_return_fake_success; tests/test_e2e_workflow.py` |
| C13 | 부분 | 근거 ID/URL·확인 범위, 원고/자산 hash·원가·오류·다음 행동 표시. 상업 권리 승인 완료는 아님 | `office/evidence.py; office/exports.py::write_rights_manifest; tests/test_evidence.py; tests/test_exports.py` |
| C14 | 단일 PC 범위 | 서버 세션/Origin/CSRF·버전 검사 구현. 실제 사람 계정/RBAC/제작자-승인자 조직 분리는 미구현 | `tests/test_api.py::test_mutation_requires_session_and_csrf; test_editor_cannot_forge_quality_passed` |
| C15 | 구현·청구 대사 별도 | BEGIN IMMEDIATE 예산 예약·unknown 보존·초과 기록. 사용량×단가 추정이며 청구서 확정 원가 아님 | `tests/test_budget.py; tests/test_providers.py::test_missing_output_usage_does_not_release_open_reservation` |
| C16 | 현재 미연결 | 로컬 worker 단일 flock·task owner 구현. Hermes native run/session/cron/memory 연결 없음 | `office/runtime.py::WorkerRuntime; tests/test_runtime.py::test_worker_process_death_is_recovered_only_after_os_lock_is_released` |
| C17 | 로컬 제작 구현 | MP4/SRT/음성/썸네일 별도 파일·검토 확인. YouTube 업로드·자막 API·Shorts 분류 미연결 | `tests/test_media.py; tests/test_api.py::test_video_release_requires_thumbnail_choice_and_media_review` |
| C18 | 구현·증거 범위 제한 | 뉴스/작업실/출고함/운영기록·미디어 미리보기·오류/빈 상태, 브라우저 검증 기록 존재 | `frontend/tests/browser/office.spec.ts; frontend/test-results/live/verification.json; research e2e-report.md` |
| C19 | 구현 | 고정 업무 핸들러, 등록 article/job/artifact ID, 공개 URL/경로 제한. 원문 명령은 실행하지 않음 | `tests/test_evidence.py::test_article_body_excludes_navigation_and_embedded_instructions; tests/test_knowledge.py; tests/test_api.py::test_artifact_id_is_not_a_file_path` |
| C20 | 원격 기능 보류 | 로컬 승인 무효화 구현. 실제 외부 예약이 없으므로 원격 취소/조회 완료는 주장하지 않음 | `Store.save_source; Store.select_thumbnail; 외부 계정 연결 후 별도 구현` |
| R21 | 구현·의미 구분 | 로컬111MD fulltext index, 실패/fixture/vendor 표시. 색인≠사람 판독≠정책 | `office/knowledge.py; tests/test_knowledge.py; research-md-audit.json` |
| R22 | 구현 | 폰트 바이트/렌더 버전/음성 설정을 production_contract에 결속, 새 산출물은 새 폴더 | `tests/test_media.py::test_new_renderer_preserves_old_artifacts_and_reuses_successful_voice; test_font_bytes_and_explicit_voice_configuration_change_production_contract` |
| R23 | 부분 | 모델 quality·파일 검증·사람 승인·외부 미게시를 구분. 원격 실행 verdict 없음 | `tests/test_e2e_workflow.py; office/exports.py; e2e-report.md` |
| R24 | 부분 | 실제 ffprobe/무음/길이 검사와 합성 미디어 E2E. 실제 기사 전체 사람 청취·품질 검토 대기 | `tests/test_media.py::test_silent_audio_is_rejected_instead_of_becoming_a_successful_video; e2e-report.md` |
| R25 | 향후 | worker 재시작/asset 보존은 구현. DB+자산+철회 tombstone 일관 backup/restore 연습은 별도 | `tests/test_runtime.py; 전체 백업/원격 대사 시험 미구현` |
| R26 | 부분 | 자체 도형/텍스트·권리 manifest·fixture/vendor 범위. 판매 PDF/미디어 상업 권리 승인 없음 | `office/exports.py::write_rights_manifest; tests/test_exports.py::test_reference_pdf_and_asset_rights_are_real_files` |
| R27 | 구현·운영 범위 제한 | model/fixture/합성 E2E 구분, 늦은 다른 job 응답 방지. heartbeat는 완료 증거가 아님 | `frontend/tests/workflow.test.ts; office/runtime.py; e2e-report.md` |
| R28 | 부분 | unknown+needs_reconciliation·사람 재시도·provider 재차단. 공급사별 수동 대사 화면/책임 배정은 확장 대상 | `tests/test_runtime.py::test_uncertain_external_result_is_unknown_and_not_failed_retryable; tests/test_budget.py` |
| R29 | 부분 | 현재 원고/제작물 영향 무효화 구현. 원격 공개물 정정/삭제와 예약 취소 미연결 | `tests/test_workflow.py::test_source_change_invalidates_approval_and_derivatives` |
| R30 | 구현·사업성과 별도 | 보고 token/추정KRW/열린예약 표시·미보고 보존. 청구 대사/ROI/CTR/매출 검증 없음 | `tests/test_providers.py; tests/test_budget.py; office/media.py::assess_thumbnail` |

테스트 표의 `tests/...`는 `apps/content-office/backend/tests/`, `office/...`는 같은 backend의 `office/` 아래다. `frontend/...`는 `apps/content-office/frontend/` 아래다.

## 근거를 직접 찾기

- 최초111MD 목록: [input-manifest.json](../../../research/content-office-2026-10-26/input-manifest.json).
- database15MD: [md-audit.md](../../../research/content-office-2026-10-26/md-audit.md).
- research96MD 및 C/R 근거: [research-md-audit.md](../../../research/content-office-2026-10-26/research-md-audit.md), [정확 offset/해시 JSON](../../../research/content-office-2026-10-26/research-md-audit.json).
- 로컬 fulltext111개 색인: [knowledge-index.json](../../../research/content-office-2026-10-26/knowledge-index.json). API `GET /api/knowledge?query=approve_article` 또는 파일/SHA/한글 검색을 지원한다. 검색은 근거 후보이며 정책 승인 기능이 아니다.

각 행은 감사자가 사람이 검토한 계약의 첫 근거다. 검색기가 출력하는 키워드 기반 candidate_contracts와 구분한다. SHA는 JSON에 전체64자로 저장되어 있으며 아래는 식별을 위한 앞12자다. section_id는 현재 지식 색인의 ID다.

| ID | 원문 경로·줄 | 색인 section_id | SHA 앞12자 |
|---|---|---|---|
| C01 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:280` | `L274` | `a3ee52d7ee96` |
| C02 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:272` | `L255` | `a3ee52d7ee96` |
| C03 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:272` | `L255` | `a3ee52d7ee96` |
| C04 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:283` | `L274` | `a3ee52d7ee96` |
| C05 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:282` | `L274` | `a3ee52d7ee96` |
| C06 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:287` | `L274` | `a3ee52d7ee96` |
| C07 | `research/ai-office-complete-2026-10-20/local-docs/b0e36a79-2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서.md:1739` | `L1735` | `a450d7605b4d` |
| C08 | `research/ai-office-complete-2026-10-20/local-docs/0aaf9383-2026-10-12-heobrain-dashboard-tool-comparison.md:7` | `L5` | `00d24ef5fff3` |
| C09 | `research/ai-office-master-2026-10-20/platform-review.md:70` | `L67` | `81e0c0503738` |
| C10 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:142` | `L133` | `a3ee52d7ee96` |
| C11 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:260` | `L255` | `a3ee52d7ee96` |
| C12 | `research/ai-office-complete-2026-10-20/local-docs/b0e36a79-2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서.md:3427` | `L3424` | `a450d7605b4d` |
| C13 | `research/ai-office-complete-2026-10-20/local-docs/b0e36a79-2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서.md:3662` | `L3647` | `a450d7605b4d` |
| C14 | `research/ai-office-master-2026-10-20/platform-review.md:89` | `L85` | `81e0c0503738` |
| C15 | `research/ai-office-master-2026-10-20/platform-review.md:112` | `L109` | `81e0c0503738` |
| C16 | `research/ai-office-master-2026-10-20/platform-review.md:54` | `L51` | `81e0c0503738` |
| C17 | `research/ai-office-complete-2026-10-20/local-docs/b0e36a79-2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서.md:3243` | `L3226` | `a450d7605b4d` |
| C18 | `research/ai-office-complete-2026-10-20/local-docs/b0e36a79-2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서.md:3615` | `L3602` | `a450d7605b4d` |
| C19 | `research/ai-office-master-2026-10-20/platform-review.md:105` | `L101` | `81e0c0503738` |
| C20 | `research/ai-office-master-2026-10-20/platform-review.md:62` | `L59` | `81e0c0503738` |
| R21 | `research/ai-office-master-2026-10-20/platform-review.md:393` | `L382` | `81e0c0503738` |
| R22 | `research/ai-office-master-2026-10-20/metadata-candidate-validation.md:49` | `L40` | `c45dd9125627` |
| R23 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:267` | `L255` | `a3ee52d7ee96` |
| R24 | `research/ai-office-complete-2026-10-20/local-docs/b0e36a79-2026-10-13_Hermes_에이전트_오피스_전체자동화_계획서.md:3243` | `L3226` | `a450d7605b4d` |
| R25 | `research/ai-office-master-2026-10-20/platform-review.md:284` | `L281` | `81e0c0503738` |
| R26 | `research/office-sixhour-2026-10-21/cloud-final-page-snapshot.md:5925` | `L5917` | `d79a1f10fa1f` |
| R27 | `research/ai-office-complete-2026-10-20/local-docs/bee86bed-2026-10-11-heobrain-content-business-all-in-one.md:265` | `L255` | `a3ee52d7ee96` |
| R28 | `research/ai-office-master-2026-10-20/platform-review.md:73` | `L67` | `81e0c0503738` |
| R29 | `research/ai-office-master-2026-10-20/platform-review.md:188` | `L183` | `81e0c0503738` |
| R30 | `research/ai-office-master-2026-10-20/platform-review.md:120` | `L117` | `81e0c0503738` |

## 검증을 읽는 방법과 다음 작업

[독립 합성 E2E](../../../research/content-office-2026-10-26/e2e-report.md)는 격리 API/SQLite/실제 worker/한국어 SAPI/FFmpeg/브라우저 재생/썸네일 선택/ZIP hash/재시작을 검증했다. 초기 원고와 quality는 fixture로 넣었으므로 실제 뉴스 모델 생성·사실성·사람 청취 완료·외부 게시 성공으로 해석하지 않는다. 실제 뉴스3건의 승인과 제작은 별도다.

[최초 코어 검수](../../../research/content-office-2026-10-26/core-review.md)는 수정 전 결함 스냅샷이다. 현재 회귀 테스트가 추가된 부분과 최초 보고를 구분한다. [runtime 감사](../../../research/content-office-2026-10-26/runtime-audit.md)의 특정 시각 관측을 이후 전체 시간의 연속 성공으로 확대하지 않는다.

다음 순서는 현재 기사 원고와 근거의 사람 확인 → 승인① → 선택 제작 → 실제 음성/영상/자막/썸네일 확인 → 승인② → 수동 전달이다. 실패/결과불명이면 원가 예약과 성공 자산을 보존하고 운영 기록에서 확인한다. 이후 확장은 실제 필요에 따라 계정 인증·원격 업로드/대사·Marketplace 읽기 adapter를 한 경계씩 추가한다.

이 문서 인계 전 부분 출고 회귀2개를 직접 실행했다: `backend/.venv/bin/python -m pytest -q tests/test_media.py::test_blog_can_be_released_independently_when_selected_video_fails tests/test_api.py::test_blog_only_release_does_not_require_video_review_or_export_video_assets` → **2 passed (1.43s)**. 전체 앱 suite는 이번 문서 작업에서 재실행하지 않았다. 문서 링크·명시 테스트명·계약30개/색인근거30개와 기존 감사 해시 불변도 확인했다.


후속 통합 검증(2026-10-26 04:22 KST): `OFFICE_REAL_MEDIA_E2E=1 .venv/bin/python -m pytest -q` → **166 passed (86.59s)**. 실제 Windows 한국어 음성/FFmpeg 합성 fixture를 포함하며, 승인 대기 중인 실제 뉴스3편 제작과 구분한다. Gemini/Kore 선택형 유료 음성 및 같은 업무의 수정 버전을 포함한1,000원 하위한도·전역1만원을 추가했다. [음성 비교](../../../research/content-office-2026-10-26/korean-voice-experiment.md)와 최초 두 검수 보고서/수정 증거를 분리해 읽는다.
