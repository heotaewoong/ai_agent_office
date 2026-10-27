# HeoBrain AI 콘텐츠 자동화 에이전트 v6 설계

작성 2026-10-27 · 근거 보고서 `reports/AI 콘텐츠 자동화 에이전트 벤치마킹.md`(인용 104개) · 연구 노트 `research_notes/AI 콘텐츠 자동화 에이전트 벤치마킹/` 5개 · 기존 설계 `docs/superpowers/specs/2026-10-26-content-office-design.md`

## 1. 결정

HeoBrain의 콘텐츠 에이전트는 **생성 공장이 아니라 편집 통제실**로 만든다. 데이터로 아이디어를 고르고, 패키지(제목·썸네일·훅)를 원고보다 먼저 확정하고, 자동 게이트로 사람이 볼 곳을 좁히고, 성과에서 사람이 승인한 교훈만 다음 회차에 되돌린다.

외부 벤치마킹(2026-10 기준)에서 리서치부터 성과 환류까지 한 시스템에서 닫은 오픈소스·상용 제품은 없었다. 성과를 다음 기획으로 되돌리는 오픈소스는 darkzOGx/youtube-automation-agent 하나였다. HeoBrain의 중간 단계(버전에 묶인 승인, 원화 예산 예약, 독립 Critique/Eval, ZIP 핸드오프)는 이미 상위권이므로 투자는 **앞단(아이디어·패키지)과 뒷단(측정·교훈)**에 한다.

## 2. 범위

- 포함: 기획 은행과 점수, ⓪ 기획 선택, 패키지 카드 게이트, 브랜드 번들, 품질·정책 게이트, 포맷별 분기 계획, 성과 스냅샷과 교훈 카드, 관련 API.
- 제외(이번 계획): 생성 영상 B-roll, 쇼츠 클리핑, YouTube 자동 업로드, beehiiv·Postiz 연동, 다른 계열 평가 모델용 공급자 어댑터. 모두 P2 이후 별도 계획.
- 유지: 승인 ① 원고 · ② 출고 · ③ 회차(뉴스레터·홍보 발송)의 기존 의미. 보고서의 "③을 기획 승인으로 재정의" 제안은 채택하지 않고 **⓪ 기획 선택**을 새로 둔다.

## 3. 파이프라인 (0~13단계)

| 단계 | 하는 일 | 사람 결정 | 외부 기준 | 구현 위치 |
|---|---|---|---|---|
| 0 브랜드 번들 | 목소리 예시·표기 고정·금지 주장·발음 사전을 모든 생성이 물려받음 | 번들 수정 | Jasper IQ, WRITER Voice Profile | `office/brand.py`, `config/brand/` |
| 1 신호 수집 | 기존 RSS + 경쟁 채널 `videos.list` 통계 + Naver DataLab(앵커 키워드) + HN | - | TrendRadar, YouTube 쿼터(search 100회/일) | 기존 `feeds.py` + 후속 수집기 |
| 2 기획 은행 | 아웃라이어 배수·수요·1차 출처·적합도·신규성으로 점수, 차단 사유 표시 | - | vidIQ Outliers, Spotter, Welsh 매트릭스 | `office/ideas.py`, `ideas` 테이블 |
| 3 ⓪ 기획 선택 | 점수순 후보에서 하나를 고르면 작업 생성 | **⓪ 선택** | vidIQ 저장/기각 | `Store.select_idea` |
| 4 패키지 카드(G0) | 제목 3안·썸네일 3안·훅·로그라인·통할 이유 2~3개, 훅이 제목 약속을 이어받는지 검사 | 패키지 확정 | Abdaal, Galloway, YouTube A/B(3안·시청 시간) | `office/packaging.py` |
| 5 리서치 브리프 | 주장-출처 대응 | - | GPT Researcher, STORM | 기존 `evidence.py` |
| 6 원고 루프 | Gen → Critique/Eval → Refine ≤2, 브랜드 번들 주입 | - | G-Eval, MT-Bench | 기존 `editorial.py` + brand |
| 7 자동 게이트 | 메타데이터 숫자 근거, 템플릿 반복 유사도, YMYL 실존 인물 AI 페르소나, 금지 주장, AI 공개 판단 | 경고 확인 | SAFE, Google AI 콘텐츠 가이드, YouTube 2025-07-15·2026-07-16 | `office/gates.py` |
| 8 ① 원고 승인 | 게이트 결과를 함께 보고 승인 | **①** | StoryChief 스냅샷 승인 | 기존 |
| 9 포맷 분기 | 승인 해시에서만 블로그(티스토리·네이버 붙여넣기)·롱폼·쇼츠·뉴스레터 계획 | - | n8n #6899, MrBeast 리텐션 비트 | `office/formats.py` |
| 10 미디어 | 실제 화면 70~90%, 한글은 폰트 레이어, TTS 발음 사전 | - | 비용표(생성 영상이 변동비 80~95%) | 기존 `media.py` + `brand.tts_text` |
| 11 ② 출고 승인 | 시험용 썸네일 3안(1280×720 이상), AI 공개 체크 | **②** | YouTube A/B, 공개 정책 | 기존 |
| 12 배포·③ 회차 | YouTube·뉴스레터, 네이버는 수동 붙여넣기 | **③(뉴스레터·홍보)** | 네이버 자동 발행 API 없음 | 기존 수동 전달 |
| 13 측정·교훈 | 24h·7d·28d 스냅샷, 채널 중앙값 대비 규칙으로 교훈 후보, 승인된 교훈만 점수 가중치에 반영 | 교훈 승인 | darkzOGx Learn, Reporting API(노출·CTR) | `office/analytics.py`, `snapshots`·`lessons` 테이블 |

## 4. 데이터 모델 추가

- `ideas(id, dedup_key UNIQUE, state, data, created_at, updated_at)` — state: candidate → selected. 제목 공백·대소문자 정규화 + 출처 URL로 중복 제거.
- `snapshots(id, channel, external_id, period, job_id, data, created_at, UNIQUE(channel, external_id, period))` — 같은 구간은 덮어씀.
- `lessons(id, state, data, created_at, updated_at)` — state: proposed → approved/rejected. `weight_change`가 있는 승인 교훈만 기획 점수에 반영.
- `job.packaging` — 확정한 패키지와 `packaging_hash`. 기획에서 시작한 작업(`article.origin == "idea"`)은 패키지 없이 원고를 만들 수 없음. 기존 RSS 작업은 영향 없음.
- `packet.quality.gates` — 게이트 결과(`pass|warn|block`, 항목, AI 공개 판단). `block`이면 원고 품질 상태를 blocked로.

## 5. 게이트 기준 (첫 값, 오탐률을 보고 조정)

| 규칙 | 차단 | 경고 |
|---|---|---|
| 메타데이터 숫자 | 블로그·영상 제목·설명·태그의 숫자가 근거·본문 어디에도 없음 | 본문에만 있음 |
| 템플릿 반복 | 이전 대본과 3-gram Jaccard 0.5 이상 | - |
| YMYL 페르소나 | 금융·법률·건강 주제 + 실존 인물 AI 페르소나 | - |
| 금지 주장 | 브랜드 번들의 금지 문구 포함 | - |
| AI 공개 | (판단만) 사실적 인물·사건·장소 합성, 타인 목소리 복제면 YouTube 변경·합성 표시 필요 | 자기 목소리 복제·양식화 B-roll은 표시 불필요 |

## 6. 도구 판단

- 채택: faster-whisper·WhisperX(자막), auto-editor·PySceneDetect(무음·장면), FFmpeg, GPT Researcher 방식(리서치), YouTube Test & Compare(A/B는 직접 만들지 않음), Gemini TTS(2027-01-01부터 오디오 단가 2배).
- 비교: Wan 2.2 5B·LTX-2(로컬 영상), Runway API의 Veo 3.1·Gemini Omni Flash(생성 B-roll), Revideo(MIT)와 Remotion(3인 이하 무료), AutoClip(롱폼→쇼츠), Typecast(단어 타이밍), beehiiv MCP·listmonk·Postiz.
- 제외: HunyuanVideo(대한민국 제외 라이선스), F5-TTS 사전학습 가중치(CC-BY-NC), FLUX dev(비상업), Midjourney(공식 API 없음·자동화 금지), Sora(2026-09-24 API 제거 보도), Wav2Lip(상업 금지), 네이버 자동 발행 봇, 전편 아바타, Inspiration 탭 자동화.

## 7. 정책 제약 요약

- YouTube: 2025-07-15 "inauthentic content", 2026-07-16 명확화(템플릿·반복형, 자극·조작형, 실존 인물 AI 페르소나의 금융·법률·의료). 사실적 합성은 공개 의무, C2PA 자동 라벨은 되돌릴 수 없음.
- Google 검색: 제목·메타 설명·구조화 데이터·alt text까지 사실 확인, 가치 없는 대량 생성은 scaled content abuse.
- 네이버: "AI 활용" 표기는 블로그에서 권장(2026-05), 공식 정책 원문은 미확보. 대량 게시·지어낸 경험이 저품질 위험.
- AI 기본법(2026-01-22 시행): 1인 크리에이터는 이용자. 에이전트를 남에게 서비스로 제공하면 표시 의무 가능성 → 법률 확인.
- 저작권: 승인 시 사람이 바꾼 부분(diff)을 보존해 인간 기여 증거로 둔다.

## 8. 우선순위

| 순위 | 기간(제안) | 항목 | 완료 기준 |
|---|---|---|---|
| P0 | 1~2주 | 패키지 카드 게이트, ⓪ 기획 선택, 시험용 썸네일 3안 | 기획에서 시작한 모든 회차가 확정 패키지를 가짐 |
| P1 | 2~4주 | 브랜드 번들, 기획 은행 점수, 품질·정책 게이트 | 승인 화면에 게이트 사유 표시, 주간 후보 20개 이상 |
| P2 | 4~8주 | 스냅샷(Studio CSV → Analytics·Reporting API·GSC), 교훈 카드 | 발행물마다 스냅샷 3개와 승인·기각 교훈 |
| P3 | 8~12주 | 파생물 테이블(롱폼 대본·뉴스레터·네이버 패키지), YouTube 비공개 업로드, 다른 계열 평가 모델 | 원본 하나에서 승인된 파생물 4종 |
| P4 | 필요 시 | 생성 B-roll, 쇼츠 클리핑, 배포 연동 | 생성 클립이 런타임의 30% 이하 |

## 9. 성공 기준

- 기능: 새 테스트와 기존 테스트 전체 통과, 기존 RSS 흐름 변화 없음.
- 운영(첫 10~20회차로 확인): 사람의 ①·② 검토 시간 감소, 게이트 오탐률, 패키지 3안 중 A/B 승자 비율, 승인된 교훈 적용 후 재확인 결과.

## 10. 미해결

- 네이버 공식 AI 정책 원문, 한국어 TTS·한글 렌더링의 측정 순위는 문헌에 없음 → 자체 블라인드 청취·회차 데이터로 확인.
- 다른 계열 평가 모델의 공급자·단가 확정 전까지 Eval은 기존 모델 유지.
- MrBeast 메모는 진위 미확인 자료로 표시.
