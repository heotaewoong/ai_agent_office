# Content quality and blog visibility repair

> For agentic workers: implement the independent fixes in the current session; preserve approved source versions and external-action gates.

**Goal:** Make the three existing blogs immediately readable, repair misleading video presentation, and provide concrete editorial revision drafts.

**Architecture:** Keep FastAPI, Next.js, immutable artifacts and existing source approvals. A read-only blog viewer wraps verified exports without changing their bytes. Renderer fixes preserve approved narration; new editorial text stays a separate unapproved draft.

**Tech Stack:** Existing Python/FastAPI, Next.js/React, Pillow and FFmpeg. No new paid provider or dependency.

**Spec:** Existing user content brief and this turn's report of poor quality and invisible blogs; `database/2026-10-12-heobrain-content-studio-plan-v4.md`.

## Constraints and review focus

- Do not publish, upload, grant release approval, or overwrite the three approved source packets.
- Keep the existing cumulative 10,000 KRW cap and open reservations; this repair uses no paid generation.
- Viewer GETs must leave source, approvals, manifests, queue and budget unchanged.
- Reject modified files, stale source bindings, unfinished blog output, and invalid formats.
- Test actual desktop/mobile blog discoverability; technical tests do not establish editorial quality or human listening.

## Task 1: Existing delivery screen

Files: frontend `app/page.tsx`, `app/globals.css`, relevant tests. Owner: blog visibility agent.

- [x] Reproduce video default and the blog selector below the thumbnail gallery.
- [x] Add failing browser coverage for visible blog controls, blog default, job switching and read-only operation.
- [x] Put blog/video and HTML/Markdown/Naver controls before the preview; default to blog when present.
- [x] Use `GET /api/jobs/{id}/blog-preview?format=html|markdown|naver`; keep original artifact links and release requirements.
- [x] Verify narrow viewport, original downloads, no mutation, and existing frontend checks.

## Task 2: Verified blog reader

Files: backend `office/exports.py`, `office/api.py`, new `tests/test_blog_reader.py`. Owner: root.

- [x] Write failing tests: real produced blog visible without release approval, escaped title/text, no state/budget changes, tampered/stale artifacts rejected, invalid format rejected.
- [x] Add `blog_reader_html(title, content, format)` as a complete styled HTML document, preserving stored export content.
- [x] Register a read-only viewer route using current source approval, completed blog output, path and SHA verification; return sandbox-compatible script-free HTML.
- [x] Run targeted tests, then the combined backend suite after renderer integration.

## Task 3: Video meaning and editorial usefulness

Files: backend `office/media.py`, `tests/test_media.py`; new editorial drafts under `output/2026-10-26_AI뉴스_품질개선_초안/`. Owners: media and editorial agents.

- [x] Reproduce lost slash-separated comparison labels and phonetic narration leaking into visual cards.
- [x] Fix those rendering branches and remove production jargon from viewer-facing labels, without changing narration or numeric claims.
- [x] Draft three articles and five-scene scripts with complete, explicitly hypothetical examples; do not render new unapproved scripts.
- [x] Render existing approved sources using cached local voice after tests; preserve prior production versions.
- [x] Inspect actual frames and show clear before/after examples; keep voice-quality and editorial limitations explicit.

## Integration

- [x] Build/restart only owned local services, verify browser → API → actual files, and preserve all approval/budget records.
- [x] Provide direct links to all three blogs, improved videos, and separately labelled new drafts.
- [x] Record exact changes and remaining quality work; do not present regression counts as a creative-quality score.

The workspace is not a Git checkout; no commit or branch operations are planned.
