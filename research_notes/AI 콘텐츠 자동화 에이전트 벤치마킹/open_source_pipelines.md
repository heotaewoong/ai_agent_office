# Open-Source AI Content Automation Pipelines & Agent Projects (as of 2026-10-27)

> Method note: Repo metadata (stars, SPDX license, `pushed_at`, archived flag) was pulled from the GitHub REST API on **2026-10-27**. Latest-release tags/dates come from each repo's `/releases/latest` page on the same day. Pipeline descriptions come from each repo's README (raw.githubusercontent.com), fetched on the same day. Star counts are GitHub API values as of 2026-10-27; treat them as snapshots. "Stale" = no push for more than 12 months before 2026-10-27.

## Q1. Which open-source repos best implement end-to-end or multi-stage content pipelines?

### Takeaway
No single OSS project covers the whole lifecycle (research → article → long video → shorts → newsletter → social → feedback) end to end. The best fit is a composition of these:
- **GPT Researcher / STORM** for research → article.
- **MoneyPrinterTurbo** (topic → finished short) or **AutoClip / OpenShorts / AI-Youtube-Shorts-Generator** (long video → shorts).
- **Postiz** (multi-platform scheduling) and **listmonk / Ghost** (newsletter).
- **darkzOGx/youtube-automation-agent**, the only verified OSS project that closes a YouTube analytics → "lessons" loop.

Several once-popular reference projects are now archived: crewAI-examples, open_deep_research and agent-inbox.

### Cited Findings

#### A. Topic → finished short/long video ("faceless" generators)
- **MoneyPrinterTurbo** (harry0703). MIT, 135,559 stars, last push 2026-10-27, latest release v1.3.9 (2026-10-21). This is the most active project in the category. — [repo](https://github.com/harry0703/MoneyPrinterTurbo), [releases](https://github.com/harry0703/MoneyPrinterTurbo/releases)
  - Pipeline: "Provide a video topic or keyword → generate the script, match footage, create subtitles and background music, and produce an HD short video." Interfaces are AI Agent, WebUI, API or CLI. It can "generate multiple output variants in batches" and "retain control over every stage". — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
  - Footage: the user's own local images/videos, or stock footage from Pexels, Pixabay and Coverr. Optional AI-generated clips come from paid providers (MiniMax H3, Seedance, Shengsuan, WaveSpeed, OFox, MuAPI, OpenAI-compatible text-to-image). — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
  - TTS: Edge TTS ("free, no API key required"), Azure, SiliconFlow, Gemini, MiniMax, ElevenLabs, Chatterbox, Kokoro, Fish Audio and VoxCPM. It also does subtitle styling and background music. Output is 9:16 (1080×1920), 16:9 or 1:1. It can "publish completed videos directly to TikTok, Instagram, and YouTube Shorts". Requires Python 3.11+; faster-whisper is optional for local transcription. — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
  - The README ships an agent prompt: an "AI Agent [that] can read Skill documents and operate a local terminal" will install it, generate the video and return the file path. — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
  - The README carries many sponsor/affiliate blocks (VolcEngine Ark, APIMart, Metaso MiniMax H3, Kimi, Shengsuan Cloud, RunningHub, etc.). — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
- **MoneyPrinterV2** (FujiwaraChoki). **AGPL-3.0**, 32,209 stars, last push 2026-09-15, no GitHub releases.
  - Features: Twitter bot with CRON scheduler, YouTube Shorts automator with CRON, affiliate marketing (Amazon + Twitter), and "find local businesses & cold outreach". Requires Python 3.12. — [repo/README](https://github.com/FujiwaraChoki/MoneyPrinterV2)
- **ShortGPT** (RayVentura). MIT, 8,077 stars. **Stale**: last push and last release v0.3.0 were both 2025-02-10. — [repo](https://github.com/RayVentura/ShortGPT)
  - Engines:
    - `ContentShortEngine`: script → render, including YouTube metadata.
    - `ContentVideoEngine`: longer videos, with audio, background footage and caption timing.
    - `ContentTranslationEngine`: transcribe → translate → re-voice → caption.
    - `EditingEngine`: an "Editing Markup Language" in JSON designed to be legible to LLMs.
  - Tech: MoviePy, OpenAI, ElevenLabs, EdgeTTS, Pexels, Bing Image, TinyDB for persistence. Korean is listed among voiceover languages. Runs as a Gradio UI on port 31415 via Docker. — [README](https://github.com/RayVentura/ShortGPT/blob/stable/README.md)
- **short-video-maker** (gyoridavid). MIT, 1,438 stars. **Stale**: last push 2025-06-21.
  - Pipeline: Kokoro TTS → Whisper captions → Pexels background → composed with **Remotion**. Exposes MCP and REST servers, with example n8n workflows.
  - Limitation it states: "only capable generating videos with English voiceover (kokoro-js doesn't support other languages)". — [README](https://github.com/gyoridavid/short-video-maker)
- **RedditVideoMakerBot** (elebumm). GPL-3.0, 12,557 stars, release 3.4.0 (2025-10-28), last push 2026-10-26. Turns Reddit threads into videos "with one command". — [repo](https://github.com/elebumm/RedditVideoMakerBot)
- **MoneyPrinterPlus** (ddean2009). GPL-3.0, 7,261 stars. **Stale**: last release v4.7 (2024-09-23), last push 2025-03-07. Batch short-video generation and mixing, auto-publishing to Douyin, Kuaishou, Xiaohongshu and Channels; ChatTTS, faster-whisper, GPT-SoVITS. — [repo](https://github.com/ddean2009/MoneyPrinterPlus)
- **ViMax** (HKUDS). MIT, 12,771 stars, v1.2.0 (2026-07-20). "Agentic Video Generation (Director, Screenwriter, Producer, and Video Generator All-in-One)".
  - Modes: Idea2Video (concept → story, characters, script, storyboard, shots, video), Script2Video, Novel2Video (released 2026-06-07) and AutoCameo.
  - Agent Loop + TUI for "interactive planning, revision, rendering control" and to "review text artifacts". v1.2.0 adds a Web UI with storyboard previews and render checkpoints. — [README](https://github.com/HKUDS/ViMax)
- **NarratoAI** (linyqh). MIT, 11,561 stars, v0.8.7 (2026-07-17).
  - Film/drama commentary (影视解说): an LLM writes the commentary script, then auto-edit, dubbing and subtitles. Uses Qwen2-VL for video understanding and IndexTTS for voice cloning.
  - v0.7.7 (2026-03-27) "removed LiteLLM dependency for security reasons". — [README](https://github.com/linyqh/NarratoAI)

#### B. Long video → short clips (repurposing / clipping)
- **AutoClip** (zhouxiaoka). MIT, 9,762 stars, v1.5.7 (2026-10-24), last push 2026-10-27.
  - Pipeline: "one link → one-click output". Turns podcasts, interviews and courses into shorts and generates subtitles, covers and publishing copy. Targets Douyin, Xiaohongshu, TikTok, Reels, YouTube Shorts, Bilibili and YouTube.
  - Clipping, framing and rendering run locally. Transcription uses author subtitles, local Whisper / SenseVoice, or cloud ASR. The CLI/MCP shares the same pipeline as the desktop app.
  - YouTube long-form segments must be at least 180 s.
  - Built on FastAPI, React, Tauri, FFmpeg, yt-dlp, Whisper and FunASR. — [README](https://github.com/zhouxiaoka/autoclip)
- **OpenShorts** (mutonby). MIT, 7,138 stars, last push 2026-10-27, no releases. Three tools:
  - Clip Generator: Gemini 3.1 Flash-Lite detects 3–15 viral moments from the transcript plus scene boundaries. Cropping uses MediaPipe + YOLOv8 face tracking, with SPLIT/SCREENCAST layouts. Subtitles come from faster-whisper with word-level timestamps. Optional ElevenLabs dubbing.
  - AI Shorts: UGC-style videos with AI actors.
  - YouTube Studio: AI thumbnails, "10 viral title suggestions with refinement chat", auto descriptions with chapter timestamps.
  - Publishing to TikTok, Reels and Shorts goes through Upload-Post (a third-party API). — [README](https://github.com/mutonby/openshorts)
- **AI-Youtube-Shorts-Generator**. The repo moved from SamurAIGPT to **Anil-matcha**. MIT, 5,622 stars, last push 2026-10-24.
  - Pipeline: YouTube URL → transcript (Whisper) → LLM "virality-aware" highlight ranking, with a score, hook and reason per clip → dedupe → vertical crop → N 9:16 MP4s.
  - Videos over 30 minutes are auto-chunked. `--output-json` dumps transcript, candidates and paths. Importable as a Python library via `generate_shorts(...)`.
  - The default `--mode api` depends on **MuAPI** (a commercial service). `--mode local` uses yt-dlp, faster-whisper and ffmpeg/OpenCV face tracking, with OpenAI or Gemini for the LLM step. — [README](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
- **FunClip** (modelscope). MIT, 6,460 stars, v2.2.1 (2026-09-01).
  - FunASR Paraformer ASR (the model listed is zh-cn), SeACo hotword customization, CAM++ speaker-ID-based clipping, LLM-based clipping, and SRT export. Gradio UI.
  - v2.2.0 added MOSS-Transcribe-Diarize for long-form ASR. — [README](https://github.com/modelscope/FunClip)
- **ClipsAI** (ClipsAI/clipsai). MIT, 557 stars. **Abandoned/stale**: last push 2024-01-17. — [repo](https://github.com/ClipsAI/clipsai)

#### C. Research → report/article (blog/SEO input)
- **GPT Researcher** (assafelovic). Apache-2.0, 30,310 stars, v3.7.0 (2026-09-26).
  - "Planner" agents generate research questions, "execution" agents gather sources, and a "publisher" aggregates everything into a report.
  - Reports run over 2,000 words from more than 20 sources, can draw on web plus local documents, and export to PDF/Word.
  - It has an MCP client (`RETRIEVER=tavily,mcp`) and can be installed as a Claude Skill. — [README](https://github.com/assafelovic/gpt-researcher)
- **STORM / Co-STORM** (stanford-oval). MIT, 31,703 stars. Last release v1.1.0 (2025-01-23) and last push 2025-09-30, so it is **slowing**.
  - Two stages. Pre-writing does perspective-guided question asking plus a simulated writer↔expert conversation, then builds an outline. Writing produces a full article with citations.
  - Co-STORM adds a **human user** who can observe or "inject utterances to steer the discussion", a Moderator agent, and a dynamic mind map.
  - Built with dspy and LiteLLM. Retrievers include You.com, Bing and VectorRM (for user documents).
  - The README is candid: it "cannot produce publication-ready articles that often require a significant number of edits". — [README](https://github.com/stanford-oval/storm)
- **Open Deep Research** (langchain-ai). MIT, 12,678 stars. **Archived by the owner on Aug 21, 2026**, so it is read-only.
  - LangGraph agent with separate models for summarization, research, compression and the final report.
  - Ranked #6 on the Deep Research Bench leaderboard (score 0.4344) as of 2025-08-02. — [repo](https://github.com/langchain-ai/open_deep_research)
- **Agent Writer** (gregorym/agent-writer; formerly bloggy-ai-bot, which now redirects). **AGPL-3.0**.
  - Keyword analysis (from a site URL or seed keyword) → Gemini long-form article plus images → scheduled publishing to **Ghost** (Admin API) or to **GitHub as MDX via Pull Request**. — [repo/README](https://github.com/gregorym/agent-writer)

#### D. Agent-framework content teams
- **crewAI-examples** (crewAIInc). **Archived by the owner on Apr 20, 2026.** Pinned to CrewAI 0.152.0; the README points to the CrewAI Cookbook. — [repo](https://github.com/crewAIInc/crewAI-examples)
  - Content-relevant flows: Content Creator Flow ("multi-crew content generation system for blogs, LinkedIn posts, and research reports"), Self Evaluation Loop Flow ("iterative content improvement with self-review") and Lead Score Flow ("with human-in-the-loop review").
  - Content-relevant crews: Instagram Post, Marketing Strategy, Screenplay Writer.
- **langchain-ai/social-media-agent**. MIT, 2,954 stars, last push 2026-10-26, no releases. URL → Twitter & LinkedIn post, with HITL (details under Q2). — [README](https://github.com/langchain-ai/social-media-agent)
- **OpenCreator** (formerly **KrillinAI**; krillinai/KrillinAI now redirects to krillinai/OpenCreator). Apache-2.0, 13,953 stars, last push 2026-10-26.
  - Uses **Codex CLI as the execution engine** instead of its own agent loop.
  - Content workspace: video translation and download, image/video generation, voiceovers, "article and social post writing, short-video scripting".
  - Agent conversation with "approvals, attachments, files, Skills, MCP, schedules". Every revision is versioned, and it keeps global, project and thread memory. Korean docs are available. — [README](https://github.com/krillinai/OpenCreator)

#### E. Distribution: social scheduling & newsletter
- **Postiz** (gitroomhq/postiz-app). **AGPL-3.0**, 38,637 stars, v2.25.3 (2026-10-24).
  - Scheduling, calendar, cross-posting, analytics, team comments, RSS auto-post, public API & webhooks, an n8n custom node, and "agentic surfaces (MCP, CLI, Claude / ChatGPT / Codex / OpenClaw / Cursor connectors)". AI copilot, images and video clipping are bring-your-own-key when self-hosted.
  - Self-hosting means "you create your own developer apps on each platform and go through their approval (Meta, YouTube, TikTok can take weeks)". — [README](https://github.com/gitroomhq/postiz-app)
- **Mixpost** (inovector). MIT, 3,873 stars, v2.6.0 (2026-03-16). Per-platform analytics, "post versions and conditions… automate follow-up comments on high-performing posts", queue and calendar, templates, hashtag groups. Pro/Enterprise tiers are paid. — [README](https://github.com/inovector/mixpost)
- **social-auto-upload** (dreammis). MIT, 15,843 stars, v1.0.0-skills.2 (2026-10-22). Multi-platform uploader with a unified CLI plus **Skills for Codex, OpenClaw and Claude Code**. — [README](https://github.com/dreammis/social-auto-upload)
  - Platforms: Douyin, Kuaishou, Xiaohongshu, Bilibili, Channels, Baijiahao, Zhihu (articles too), Facebook Page and Instagram image posts.
  - YouTube: video upload works, but scheduling is "in development".
  - TikTok: a "Chrome version implementation".
- **listmonk** (knadh). **AGPL-3.0**, 24,001 stars, v7.0.0-beta.1 (2026-10-20). "Self-hosted newsletter and mailing list manager… single binary." — [repo](https://github.com/knadh/listmonk)
- **Ghost** (TryGhost). MIT, 55,614 stars, v6.72.0 (2026-10-20). Publishing, memberships, subscriptions, newsletters. — [repo](https://github.com/TryGhost/Ghost)
- **Keila** (pentacent). **AGPL-3.0**, 2,250 stars, v0.30.3 (2026-09-06). Open-source newsletter tool. — [repo](https://github.com/pentacent/keila)

#### F. Workflow glue (n8n)
- **n8n**. Licensed under the **Sustainable Use License** (fair-code, not OSI; the GitHub SPDX field shows NOASSERTION). 208,704 stars, n8n@2.44.7 (2026-10-26). — [repo](https://github.com/n8n-io/n8n), [LICENSE.md](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)
  - The license allows use "only for your own internal business purposes or for non-commercial" use, among other limits.
  - `.ee.` files require an Enterprise License.
- **n8n template #6899**, "Repurpose YouTube videos to multiple content types with OpenRouter AI and Airtable", by Alexandra Spalato. The page shows a last update about 8 months before retrieval. — [n8n.io](https://n8n.io/workflows/6899-repurpose-youtube-videos-to-multiple-content-types-with-openrouter-ai-and-airtable/)
  - Trigger: manual. It reads Airtable rows with Status="selected".
  - Steps: transcript via the Scrape Creators API → OpenRouter LLM chains generate only the selected output types → results are written back to Airtable.
  - Outputs: summary/key takeaways, tutorial, YouTube package (titles, hook, steps, CTA), blog post, LinkedIn post, newsletter, X post.
  - No output-review step is described.
- **Zie619/n8n-workflows**. MIT, 57,090 stars, last push 2026-06-24. A scraped collection of "all of the workflows of n8n I could find". Its latest release tag is literally `dmca-compliance-2025-08-14`. — [repo](https://github.com/Zie619/n8n-workflows), [release](https://github.com/Zie619/n8n-workflows/releases)
- Third-party paid n8n YouTube→blog templates exist on Gumroad and Payhip for $5–$34, e.g. Mistral rewriting a transcript into a blog draft, or a transcript → 6–8 tweet thread. These are not open source. — [Gumroad](https://zakwan8.gumroad.com/l/tyifx), [Payhip](https://payhip.com/b/3YL7W)

#### G. Rendering / editing / speech primitives
| Project | License | Stars (2026-10-27) | Latest release / last push | Role |
|---|---|---|---|---|
| [Remotion](https://github.com/remotion-dev/remotion) | Custom "Remotion License" (NOASSERTION) | 67,959 | v4.0.539 (2026-10-26) | React → video rendering |
| [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | MIT | 19,502 | v3.17.2 (2024-12-14); push 2026-07-02 | Code-driven animation (no release in ~22 months) |
| [Revideo](https://github.com/midrender/revideo) (moved from redotvideo) | MIT | 4,148 | push 2026-07-15 | TS video engine with headless `renderVideo()`; "engine behind Midrender" ([README](https://github.com/midrender/revideo)) |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) (moved to Comfy-Org) | GPL-3.0 | 143,357 | push 2026-10-27 | Node-graph diffusion / video workflows |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) | MIT | 96,408 | v0.3.0 (2026-04-15) | "Open-source CapCut alternative" |
| [auto-editor](https://github.com/WyattBlue/auto-editor) | Unlicense | 5,635 | 31.7.2 (2026-10-03) | Silence/dead-air cutting |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | BSD-3-Clause | 5,297 | v0.7.2 (2026-10-12) | Scene-cut detection (Python + OpenCV) |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | 26,195 | v1.2.1 (2025-10-31); push 2026-10-25 | CTranslate2 Whisper ASR |
| [whisperX](https://github.com/m-bain/whisperX) | BSD-2-Clause | 24,871 | v3.8.6 (2026-05-25) | Word timestamps + diarization |
| [openai/whisper](https://github.com/openai/whisper) | MIT | 111,359 | v20250625 (2025-06-26) | Reference ASR |
| [VideoLingo](https://github.com/Huanshere/VideoLingo) | Apache-2.0 | 18,949 | v3.1.1 (2026-09-27) | yt-dlp → Qwen3-ASR + ForcedAligner → terminology-aware translation with "reflection" → dubbing (GPT-SoVITS, OpenAI, Edge TTS) ([README](https://github.com/Huanshere/VideoLingo)) |
| [pyvideotrans](https://github.com/jianchang512/pyvideotrans) | GPL-3.0 | 19,560 | v4.17 (2026-10-23) | Video translation + dubbing + subtitles |
| [crawl4ai](https://github.com/unclecode/crawl4ai) | Apache-2.0 | 86,352 | v0.9.5 (2026-10-14) | Web → LLM-ready Markdown |
| [Firecrawl](https://github.com/firecrawl/firecrawl) | **AGPL-3.0** ([LICENSE](https://github.com/firecrawl/firecrawl/blob/main/LICENSE)) | not captured | n/a | Scraping API (social-media-agent depends on it) |
| [RSSHub](https://github.com/DIYgod/RSSHub) | **AGPL-3.0** | 46,677 | v2026.10.26 (2026-10-26) | "Everything is RSSible" (feed source) |

### Inferences
- The most active "topic → video" project is MoneyPrinterTurbo: the largest star count, a release 6 days before this snapshot, and a broad provider matrix. Its default visual layer is still keyword-matched stock footage, though, and its README economics are visibly driven by API sponsors.
- The clipping/repurposing tools (AutoClip, OpenShorts, AI-Youtube-Shorts-Generator) are higher-value for a creator who already films long-form. They transform original footage rather than synthesizing "faceless" filler, which also lowers YouTube inauthentic-content risk (see Q4).
- AutoClip is architecturally closest to the target stack: FastAPI, FFmpeg, local Whisper, CLI/MCP. AI-Youtube-Shorts-Generator in local mode is the cleanest importable Python library.
- For research → article, GPT Researcher is the safer dependency. It is actively released and Apache-2.0, with MCP and Skill support. STORM's outline-from-perspectives method and Co-STORM's human-steering protocol are worth copying as patterns, but the repo itself is slowing.
- The archived reference implementations (crewAI-examples, open_deep_research, agent-inbox) should be treated as design references, not dependencies.

### Gaps
- Could not capture star counts or licenses for CosyVoice, HunyuanVideo or Firecrawl from the API (rate limit hit). Firecrawl's license was verified from its LICENSE file instead.
- Release date for darkzOGx/youtube-automation-agent v2.11.0, and stars and last-push dates for Agent Writer, were not captured.
- No verified open-source project automates **Korean** platforms: Naver Blog, Tistory, Kakao Channel, Naver Clip. The social-auto-upload, MoneyPrinterPlus and AutoClip platform lists are China-centric plus global platforms.
- n8n.io's template library was not exhaustively surveyed; only template #6899 was opened and verified.

## Q2. Which projects implement content REPURPOSING (one source → many formats) and which implement HUMAN-IN-THE-LOOP approval?

### Takeaway
Repurposing is common: one transcript or URL turned into blog, social, newsletter and short clips. Real HITL gates are rare. The best verified examples are:
- **langchain-ai/social-media-agent**: LangGraph interrupts surfaced in Agent Inbox for accept/edit/reject.
- **darkzOGx/youtube-automation-agent**: mandatory fact review, media-rights confirmation and human approval before upload, plus approval of analytics "lessons".
- **Co-STORM**: a human steering the research discourse.
- **OpenCreator** (approvals and versioning) and **ViMax** (artifact review in its Agent Loop).

Most video generators publish without any gate.

### Cited Findings

#### Repurposing (one → many)
- n8n template #6899 turns one YouTube transcript into: summary, tutorial, YouTube titles/hook/CTA, blog post, LinkedIn post, newsletter and X post. Each piece is stored as a separate Airtable field. — [n8n.io](https://n8n.io/workflows/6899-repurpose-youtube-videos-to-multiple-content-types-with-openrouter-ai-and-airtable/)
- langchain-ai/social-media-agent: "take in a URL, and generate a Twitter & LinkedIn post based on the content of the URL". — [README](https://github.com/langchain-ai/social-media-agent)
  - Advanced mode parses GitHub, Twitter and YouTube URLs, using Google Vertex AI for YouTube content.
  - It can ingest links from a Slack channel through a daily cron. "We use this flow internally at LangChain."
- AutoClip: one long video → multiple shorts plus subtitles, covers and per-platform publishing copy, for Douyin, Xiaohongshu, TikTok, Reels, Shorts, Bilibili and YouTube. — [README](https://github.com/zhouxiaoka/autoclip)
- OpenShorts: long video → 3–15 shorts. Its YouTube Studio produces titles, thumbnails and chapter descriptions from the Whisper transcript. — [README](https://github.com/mutonby/openshorts)
- AI-Youtube-Shorts-Generator: one YouTube URL → N ranked 9:16 shorts with a score, hook and reason each. — [README](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
- ShortGPT ContentTranslationEngine: video/YouTube link → transcribe → translate → re-voice → captions → new video. — [README](https://github.com/RayVentura/ShortGPT/blob/stable/README.md)
- VideoLingo, pyvideotrans and OpenCreator handle cross-language repurposing: subtitles, translation and dubbing. — [VideoLingo](https://github.com/Huanshere/VideoLingo), [pyvideotrans](https://github.com/jianchang512/pyvideotrans), [OpenCreator](https://github.com/krillinai/OpenCreator)
- crewAI Content Creator Flow: one research input → blogs, LinkedIn posts and research reports (the repo is now archived). — [crewAI-examples](https://github.com/crewAIInc/crewAI-examples)
- Postiz: RSS auto-post and cross-posting across channels. — [README](https://github.com/gitroomhq/postiz-app)
- ViMax Novel2Video: long-form fiction → episodic video. — [README](https://github.com/HKUDS/ViMax)

#### Human-in-the-loop approval
- **langchain-ai/social-media-agent**: "uses a human-in-the-loop (HITL) flow to handle authentication with different social media platforms, and to allow the user to make changes, or accept/reject the generated post." — [README](https://github.com/langchain-ai/social-media-agent)
  - "The Agent Inbox is the easiest way to view interrupted events, and manage accepting, responding, or other allowed actions."
  - Dependencies: Anthropic API, LangSmith, FireCrawl and Arcade (social auth and scheduling); Supabase for images; optionally Slack.
- **langchain-ai/agent-inbox**: MIT. **Archived by the owner on Sep 20, 2026.** It defines the interrupt schema `HumanInterruptConfig` with flags such as `allow_ignore` and `allow_respond`, and connects to a LangGraph deployment "for fetching interrupts, and sending human responses". — [repo](https://github.com/langchain-ai/agent-inbox)
- **darkzOGx/youtube-automation-agent**: MIT, latest release v2.11.0. — [README](https://github.com/darkzOGx/youtube-automation-agent)
  - "You approve before anything is published. Finished videos wait for fact review, media-rights confirmation, and your approval. Turning on autonomy doesn't skip those checks."
  - "Simulated or placeholder media is clearly marked and can never be approved or uploaded."
  - The review screen has "approve, save, reject, and regenerate actions".
  - Comment reply drafts "post only after you approve them".
- **Co-STORM**: the human user can "observe the discourse" or "actively engage in the conversation by injecting utterances to steer the discussion focus". A shared mind map supports this. — [STORM README](https://github.com/stanford-oval/storm)
- **OpenCreator**: agent conversations "manage approvals, attachments, files, Skills, MCP, schedules". "Every revision creates a new version while preserving earlier settings and outputs for review and comparison." It also has "approvals and redacted diagnostics" under local security. — [README](https://github.com/krillinai/OpenCreator)
- **ViMax**: the Agent Loop/TUI supports discussing ideas, revising plans and reviewing text artifacts. The v1.2.0 Web UI adds storyboard previews and render checkpoints. — [README](https://github.com/HKUDS/ViMax)
- **MoneyPrinterTurbo**: "retaining control over every stage". It offers previews, such as voice samples and full narration previews, but no explicit approval gate before its direct-publish feature is documented. — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
- **crewAI-examples**: Lead Score Flow is "with human-in-the-loop review", but that is a sales flow, not content. Content Creator Flow is not described as having HITL. — [repo](https://github.com/crewAIInc/crewAI-examples)
- **Postiz**: "Invite your team members to collaborate, comment, and schedule posts". This is collaboration, but the README excerpt does not describe a formal approval state. — [README](https://github.com/gitroomhq/postiz-app)
- **n8n #6899**: no output approval step; the only human step is selecting inputs in Airtable. — [n8n.io](https://n8n.io/workflows/6899-repurpose-youtube-videos-to-multiple-content-types-with-openrouter-ai-and-airtable/)

### Inferences
- The strongest reusable HITL pattern is a three-part state machine:
  1. Generated artifacts land in a review queue (status `pending_review`).
  2. The reviewer can accept, edit, respond/regenerate or ignore, mirroring Agent Inbox's flags.
  3. Publishing reads only `approved` rows.
  This can be implemented in FastAPI + SQLite without LangGraph.
- darkzOGx's explicit gates are a good checklist to copy: fact review, media-rights confirmation, "placeholder media can never be approved", and approval-gated comment replies.
- Since Agent Inbox is archived, depending on its UI is risky. The interrupt schema is a reasonable design reference.

### Gaps
- Did not verify the full Agent Inbox schema (e.g., `allow_edit`, `allow_accept`). Only `allow_ignore` and `allow_respond` were seen in the fetched excerpt.
- Did not verify whether Postiz has a formal "approval required before publish" workflow state for team members.

## Q3. Which projects implement trend/idea discovery or performance feedback loops (YouTube Analytics ingestion, A/B titles)?

### Takeaway
- **Trend discovery** is well covered by TrendRadar (hot-list plus RSS aggregation with AI analysis and an MCP server), RSSHub/crawl4ai as feed and scrape sources, and GPT Researcher for deep dives.
- **Performance feedback loops** are rare in OSS. darkzOGx/youtube-automation-agent is the only verified project that ingests YouTube Analytics (retention, 24-hour and 7-day outcomes), proposes "lessons" and requires human approval before they change future videos.
- Title and thumbnail A/B testing is now best done natively in YouTube's "Test & Compare". OpenShorts and the YouTube agent only generate title candidates.

### Cited Findings
- **TrendRadar** (sansan0). GPL-3.0, 63,216 stars, last push 2026-10-20. "AI-driven public opinion & trend monitor with multi-platform aggregation, RSS, and smart alerts." — [repo](https://github.com/sansan0/TrendRadar), [README](https://github.com/sansan0/TrendRadar)
  - Changelog items:
    - mcp-v4.0.0 (2026-02-09) pushes AI-written content to 9 channels, including Feishu, DingTalk, Telegram and email.
    - RSS guid de-duplication.
    - The AI analysis window is decoupled from the push window.
    - Keyword and AI-interest files.
    - `timeline.yaml` sets one schedule for collect, push and AI analysis.
    - MCP resources for platforms, rss-feeds, dates and keywords.
- **RSSHub** (AGPL-3.0) and **crawl4ai** (Apache-2.0) are the commonly used feed and scrape layers. — [RSSHub](https://github.com/DIYgod/RSSHub), [crawl4ai](https://github.com/unclecode/crawl4ai)
- **darkzOGx/youtube-automation-agent**. Node.js 18.17+, FFmpeg via `ffmpeg-static`. — [README](https://github.com/darkzOGx/youtube-automation-agent)
  - Stage table: Research → Script → Production → Review → Publish → **Learn**. Learn "captures 24-hour and 7-day evidence, measures your chosen outcome, then proposes the next move". The user can "choose the KPI and approve or reject each lesson".
  - Requires "YouTube Data API v3, and YouTube Analytics API for retention and outcome data".
  - Features "scene-aware retention: see which scene lost viewers" and an "Audience Engagement Studio": comment sync, themes and questions, spam quarantine, and "video ideas mined from repeated requests".
  - Cron schedule: generation daily at 06:00, publish queue every 15 min, analytics daily at 09:00, optimization daily at 22:00, comment sync and growth experiments every 4 h, weekly strategy review on Sundays at 08:00.
  - Providers: Gemini, OpenAI, OpenRouter, Kimi, MiMo, GLM, DeepSeek or MiniMax for text. Narration in preference order ElevenLabs → OpenAI → Gemini. Video defaults to a free local slideshow, with optional Seedance, MiniMax H3, Gemini Omni, Kling or Wan clips capped by paid seconds.
  - A third-party write-up (2026-08-31) describes the same six-agent structure (strategy, script, thumbnail, SEO, publishing, analytics). — [addrom.com](https://addrom.com/youtube-automation-agent-install-and-automate-your-channel-with-ai/)
- **OpenShorts YouTube Studio**: "10 viral title suggestions with refinement chat", plus AI thumbnails. It generates candidates but does not measure them. — [README](https://github.com/mutonby/openshorts)
- **Mixpost**: per-platform analytics, and "automate follow-up comments on high-performing posts". This is a light performance-triggered action. — [README](https://github.com/inovector/mixpost)
- **Postiz**: "Measure your work with analytics". When self-hosted this "requires your own app credentials with analytics scopes". — [README](https://github.com/gitroomhq/postiz-app)
- **YouTube native "Test & Compare"**:
  - Up to 3 titles, 3 thumbnails or combinations per video, tested for up to two weeks.
  - Winners are chosen by watch time rather than CTR. If results are a tie, the first option becomes the default.
  - Title testing was expanded in July 2025. — [Tubefilter 2025-07-16](https://www.tubefilter.com/2025/07/16/youtube-feature-test-and-compare-titles-thumbnails/), [Search Engine Journal](https://www.searchenginejournal.com/youtube-title-a-b-testing-rolls-out-globally-to-creators/562571/), [RouteNote](https://routenote.com/blog/youtube-expand-test-compare-how-to-use-it/)
  - Sources conflict on eligibility. SEJ says it is available to creators with advanced features; RouteNote says all YPP creators.
- A search found **no other** open-source agent that closes a title/thumbnail A/B loop. Commercial tools (e.g., thumbnailtest.com) and hackathon projects (YouTube Growth Copilot on lablab.ai) exist, but their licenses and repos were not verified. — [lablab.ai](https://lablab.ai/submissions/irtakz3mvuzcs8rog6cvbksk), [thumbnailtest.com](https://thumbnailtest.com/features/analytics-for-youtube-tests)
- **Agent Writer** does keyword discovery from a site URL or seed keyword. This is SEO idea discovery without performance feedback. — [README](https://github.com/gregorym/agent-writer)

### Inferences
- A solo creator should not build A/B testing. Use YouTube Test & Compare for titles and thumbnails. Build only the ingestion and learning layer, copying darkzOGx's design:
  - a nightly YouTube Analytics API pull;
  - 24-hour and 7-day snapshots;
  - one KPI chosen per video (e.g., average view duration or subscribers gained);
  - an LLM-proposed "lesson" row that must be approved before it is injected into the next script or ideation prompt.
- TrendRadar's architecture is directly portable: a scheduled collector, keyword/interest filters, AI summary and multi-channel push, plus an MCP server for agents. Its source lists are Chinese-platform-oriented, so a Korean creator would swap in Korean feeds via RSSHub or crawl4ai.

### Gaps
- Did not verify whether TrendRadar has Korean platform sources (Naver, Daum, YouTube KR trending) built in.
- Did not verify YouTube Analytics API quota details or the current Test & Compare eligibility on YouTube's own Help Center.
- No OSS project was found that ingests **blog/SEO** performance (Google Search Console, Naver Search Advisor) back into topic selection.

## Q4. Known weaknesses: generic stock-footage slop, missing fact-checking, platform policy risk, license traps

### Takeaway
The biggest practical risks are:
1. **Monetization and policy risk** from mass-produced "faceless" output under YouTube's July 2025 "inauthentic content" clarification.
2. **License traps**, especially:
   - Tencent **HunyuanVideo's license explicitly excludes South Korea**;
   - F5-TTS weights are **non-commercial**;
   - XTTS-v2 uses a custom Coqui Public Model License;
   - Remotion needs a company license above 3 employees;
   - AGPL applies to Postiz, listmonk, Firecrawl, RSSHub, Keila, MoneyPrinterV2 and Agent Writer;
   - n8n's license allows only internal or non-commercial use.
3. **Missing fact-checking**: almost no generator verifies claims. STORM itself says its articles need significant edits.

### Cited Findings

#### Quality & fact-checking
- STORM "cannot produce publication-ready articles that often require a significant number of edits". — [README](https://github.com/stanford-oval/storm)
- VideoLingo: "Translation quality depends on the source audio, language…". — [README](https://github.com/Huanshere/VideoLingo)
- MoneyPrinterTurbo and ShortGPT source visuals from stock APIs (Pexels, Pixabay, Coverr, Bing Image) matched to script keywords. — [MPT README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md), [ShortGPT README](https://github.com/RayVentura/ShortGPT/blob/stable/README.md)
- The counter-example is darkzOGx/youtube-automation-agent, which gates publishing on "fact review, media-rights confirmation, and your approval". Its default local slideshow means "placeholder media… can never be approved or uploaded". — [README](https://github.com/darkzOGx/youtube-automation-agent)

#### Platform policy risk
- **YouTube YPP update (July 15, 2025)**: it targets "mass-produced and repetitive" content and renamed the "repetitious content" policy to "inauthentic content". — [TechCrunch 2025-07-09](https://techcrunch.com/2025/07/09/youtube-prepares-crackdown-on-mass-produced-and-repetitive-videos-as-concern-over-ai-slop-grows), [BetaNews 2025-07-10](https://betanews.com/2025/07/10/youtube-is-fighting-ai-slop-with-new-monetization-guidelines/), [AlternativeTo](https://alternativeto.net/news/2025/7/youtube-updates-its-policy-to-demonetize-inauthentic-mass-produced-ai-generated-content)
  - YouTube's Rene Ritchie called it a "minor update" to longstanding YPP policy.
  - Reaction and clip channels were said not to be targeted.
  - Exact enforcement language was not published at announcement time.
- **Postiz self-hosting** needs per-platform developer-app approval: "Meta, YouTube, TikTok can take weeks". Postiz states its hosted product "does not automate or scrape content from social media platforms" and uses official OAuth. — [README](https://github.com/gitroomhq/postiz-app)
- **social-auto-upload** works through per-platform login/account preparation, and its TikTok uploader is a "Chrome version implementation". It is browser-automation based rather than official-API based for many platforms. — [README](https://github.com/dreammis/social-auto-upload)
- **MoneyPrinterV2** includes "find local businesses & cold outreach" by email from scraped businesses. — [README](https://github.com/FujiwaraChoki/MoneyPrinterV2)
- **Zie619/n8n-workflows**' latest release is tagged `dmca-compliance-2025-08-14`. — [releases](https://github.com/Zie619/n8n-workflows/releases)

#### License traps
- **HunyuanVideo** (Tencent): "THIS LICENSE AGREEMENT DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA". "Territory" means "worldwide… excluding… the European Union, United Kingdom and South Korea". "You must not use, reproduce, modify, distribute, or display the Tencent Hunyuan Works, Output or results… outside the Territory." Services above 100M MAU need a separate license. **HunyuanVideo-1.5 has the same territory exclusion.** — [HunyuanVideo LICENSE.txt](https://github.com/Tencent-Hunyuan/HunyuanVideo/blob/main/LICENSE.txt), [HunyuanVideo-1.5 LICENSE](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/LICENSE)
- **F5-TTS**: "Our code is released under MIT License. The pre-trained models are licensed under the CC-BY-NC license due to the training data Emilia." — [README](https://github.com/SWivid/F5-TTS)
- **XTTS-v2** (Coqui): `license_name: coqui-public-model-license` ([coqui.ai/cpml](https://coqui.ai/cpml)). It supports 17 languages and added Korean. — [HF model card](https://huggingface.co/coqui/XTTS-v2)
- **Remotion**: free for individuals, for-profit organizations "with up to 3 employees", non-profits and evaluation. Otherwise a Company License is required. "It is not allowed to copy or modify Remotion code for the purpose of selling… your own derivate of Remotion." The license will "slightly change" in Remotion 5.0 (PR #3750). — [LICENSE.md](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)
  - short-video-maker composes with Remotion, so it inherits this license. — [short-video-maker README](https://github.com/gyoridavid/short-video-maker)
- **n8n Sustainable Use License**: "You may use or modify the software only for your own internal business purposes or for non-commercial or…" use. `.ee.` files need an Enterprise license. — [LICENSE.md](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)
- **AGPL-3.0** projects: Postiz, listmonk, Keila, RSSHub, Firecrawl, MoneyPrinterV2, Agent Writer. — [Postiz](https://github.com/gitroomhq/postiz-app), [listmonk](https://github.com/knadh/listmonk), [Keila](https://github.com/pentacent/keila), [RSSHub](https://github.com/DIYgod/RSSHub), [Firecrawl LICENSE](https://github.com/firecrawl/firecrawl/blob/main/LICENSE), [MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2), [Agent Writer](https://github.com/gregorym/agent-writer)
- **GPL-3.0** projects: ComfyUI, pyvideotrans, RedditVideoMakerBot, TrendRadar, MoneyPrinterPlus. — [ComfyUI](https://github.com/Comfy-Org/ComfyUI), [pyvideotrans](https://github.com/jianchang512/pyvideotrans), [RedditVideoMakerBot](https://github.com/elebumm/RedditVideoMakerBot), [TrendRadar](https://github.com/sansan0/TrendRadar), [MoneyPrinterPlus](https://github.com/ddean2009/MoneyPrinterPlus)
- **Permissive model options**:
  - **Kokoro-82M**: "Apache-licensed weights… can be deployed anywhere". — [HF card](https://huggingface.co/hexgrad/Kokoro-82M)
  - **MeloTTS**: MIT, "free for both commercial and non-commercial use", and has a Korean voice. It is **stale**: last push 2024-12-24, last release v0.1.2 (2024-03-01). — [README](https://github.com/myshell-ai/MeloTTS)
  - **Wan2.2**: Apache-2.0 repo, last push 2026-09-21. — [repo](https://github.com/Wan-Video/Wan2.2)
  - **LTX-Video**: Apache-2.0 repo, but its README says "LTX-2 is now the primary home for LTX development". — [README](https://github.com/Lightricks/LTX-Video)
  - **Fun-CosyVoice 3.0** covers 9 languages, including Korean. — [README](https://github.com/FunAudioLLM/CosyVoice)

#### Maintenance / dependency risk
- Archived: crewAI-examples (Apr 20, 2026), open_deep_research (Aug 21, 2026) and agent-inbox (Sep 20, 2026). — [crewAI-examples](https://github.com/crewAIInc/crewAI-examples), [open_deep_research](https://github.com/langchain-ai/open_deep_research), [agent-inbox](https://github.com/langchain-ai/agent-inbox)
- Stale (no push for more than 12 months): ShortGPT (2025-02-10), MoneyPrinterPlus (2025-03-07), MeloTTS (2024-12-24), ClipsAI (2024-01-17). short-video-maker is close behind (2025-06-21). — GitHub API, 2026-10-27 ([ShortGPT](https://github.com/RayVentura/ShortGPT), [MoneyPrinterPlus](https://github.com/ddean2009/MoneyPrinterPlus), [MeloTTS](https://github.com/myshell-ai/MeloTTS), [ClipsAI](https://github.com/ClipsAI/clipsai), [short-video-maker](https://github.com/gyoridavid/short-video-maker))
- Repo moves and renames:
  - SamurAIGPT → Anil-matcha (AI-Youtube-Shorts-Generator)
  - comfyanonymous → Comfy-Org (ComfyUI)
  - redotvideo → midrender (Revideo)
  - KrillinAI → OpenCreator
  - mendableai → firecrawl
  - bloggy-ai-bot → agent-writer

  — GitHub redirects observed 2026-10-27.
- Vendor lock-in through READMEs: AI-Youtube-Shorts-Generator's default mode needs MuAPI, and the README promotes MuAPI's paid clipping API. OpenShorts publishes through Upload-Post. MoneyPrinterTurbo's README is dominated by sponsored API providers. — [AYSG](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator), [OpenShorts](https://github.com/mutonby/openshorts), [MPT](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
- NarratoAI removed LiteLLM "for security reasons" in v0.7.7. This signals supply-chain concern in LLM-proxy dependencies. — [README](https://github.com/linyqh/NarratoAI)

### Inferences
- **For a creator based in South Korea, HunyuanVideo (including 1.5) should be excluded entirely.** The license grants nothing in South Korea and also forbids using its "Output" outside the Territory.
- Avoid F5-TTS pretrained weights for monetized content, and treat XTTS-v2/CPML as restricted until the CPML text is reviewed.
- Prefer Apache/MIT components: Kokoro (only if Korean voices exist), MeloTTS (Korean, but stale), Wan2.2, faster-whisper, whisperX, auto-editor, PySceneDetect.
- AGPL tools (Postiz, listmonk) are fine to self-host for one's own channel. Obligations arise mainly if you modify them and offer them to others over a network.
- n8n is fine for one's own internal automation but not for reselling as a hosted service.
- Remotion is free for a solo creator, but becomes paid once the business grows past 3 employees.
- Firecrawl, a social-media-agent dependency, is AGPL. crawl4ai (Apache-2.0) is the permissive substitute.
- Film/drama commentary (NarratoAI) and Reddit-to-video (RedditVideoMakerBot) carry copyright and "reused content" risk on top of the inauthentic-content policy. This is inferred from the source material types, not stated in their READMEs.
- MoneyPrinterV2-style scraped cold email would likely conflict with Korean anti-spam rules for unsolicited commercial messages. This was not verified in this research.

### Gaps
- Did not read the full CPML text, the HunyuanVideo acceptable-use policy, LTX-2 weight license, or CosyVoice weight license.
- Did not verify Kokoro's Korean voice support. short-video-maker reports kokoro-js as English-only, but the Python package may differ.
- Did not retrieve YouTube's official Help Center wording for the "inauthentic content" policy; secondary news coverage was used.
- Did not verify Microsoft Edge TTS terms for commercial use. MoneyPrinterTurbo and ShortGPT both default to it as "free".

## Q5. What could a solo Korean creator running Python/FastAPI/SQLite/FFmpeg + a Hermes agent reuse?

### Takeaway
Reuse **libraries and patterns**, not whole apps. Python-native, permissively licensed building blocks fit the stack directly:
- faster-whisper / whisperX for Korean ASR;
- auto-editor and PySceneDetect;
- AI-Youtube-Shorts-Generator's `generate_shorts()` in local mode;
- GPT Researcher and knowledge-storm for research;
- MeloTTS or CosyVoice for Korean TTS (licenses to verify).

Adopt three patterns:
- LangGraph/Agent-Inbox-style approval states;
- n8n #6899's "one transcript → many output fields" schema;
- darkzOGx's Learn loop (YouTube Analytics → approved lessons).

Postiz (via its API/MCP) and listmonk/Ghost can serve as external distribution services. Skills/MCP-style integrations (social-auto-upload, MoneyPrinterTurbo, AutoClip, GPT Researcher, TrendRadar) are the most portable to an agent like Hermes.

### Cited Findings
- AI-Youtube-Shorts-Generator can be imported as a Python library: "import `generate_shorts(...)` into your own pipeline". Local mode uses yt-dlp, faster-whisper and ffmpeg/OpenCV, with OpenAI or Gemini. `--output-json` gives the full transcript and candidates for downstream automation. — [README](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
- AutoClip's stack (FastAPI, React, Tauri, FFmpeg, yt-dlp, Whisper, FunASR) matches the target stack. Its CLI/MCP "shares the same one-click pipeline" and "local CLI does not need Redis". — [README](https://github.com/zhouxiaoka/autoclip)
- MoneyPrinterTurbo exposes WebUI, API and CLI, plus an agent prompt for "AI Agent[s] that can read Skill documents and operate a local terminal". — [README-en](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-en.md)
- social-auto-upload ships "Skill[s] for Codex, OpenClaw, Claude Code" and an "Agent Bootstrap Prompt". — [README](https://github.com/dreammis/social-auto-upload)
- GPT Researcher installs as a Claude Skill and supports MCP retrievers. — [README](https://github.com/assafelovic/gpt-researcher)
- STORM installs as `pip install knowledge-storm`, is built on dspy and LiteLLM, and supports VectorRM grounding on user documents. — [README](https://github.com/stanford-oval/storm)
- Postiz offers a public API, webhooks, an n8n node, and MCP/CLI connectors that "point… at your own instance". — [README](https://github.com/gitroomhq/postiz-app)
- Postiz's README sponsor table mentions a third-party product that lets you "bring your own OpenClaw, Hermes, or Claude agents". This is the only Hermes mention found. — [README](https://github.com/gitroomhq/postiz-app)
- TrendRadar has an MCP server with resources (platforms, rss-feeds, dates, keywords) and multi-channel push. — [README](https://github.com/sansan0/TrendRadar)
- Korean-capable speech components:
  - ShortGPT lists Korean voiceover (via EdgeTTS/ElevenLabs). — [ShortGPT](https://github.com/RayVentura/ShortGPT/blob/stable/README.md)
  - MeloTTS has a Korean voice (MIT). — [MeloTTS](https://github.com/myshell-ai/MeloTTS)
  - Fun-CosyVoice 3.0 covers Korean. — [CosyVoice](https://github.com/FunAudioLLM/CosyVoice)
  - XTTS-v2 added Korean (CPML). — [XTTS-v2](https://huggingface.co/coqui/XTTS-v2)
  - OpenCreator offers Korean docs and 124 target translation languages. — [OpenCreator](https://github.com/krillinai/OpenCreator)
- FunClip's bundled Paraformer model is zh-cn. — [README](https://github.com/modelscope/FunClip)
- darkzOGx's Learn stage: "24-hour and 7-day evidence… choose the KPI and approve or reject each lesson". Analytics run at 09:00 and optimization at 22:00 daily. — [README](https://github.com/darkzOGx/youtube-automation-agent)
- n8n #6899 stores each output type as its own field (blog_post, linkedin, newsletter, tweeter, youtube_titles, youtube_hook…), with Status="selected" as the trigger filter. — [n8n.io](https://n8n.io/workflows/6899-repurpose-youtube-videos-to-multiple-content-types-with-openrouter-ai-and-airtable/)

### Inferences
Suggested reuse map (재사용 제안):

1. **Idea / trends**: copy TrendRadar's `timeline.yaml` idea of one schedule for collect → AI analysis → push. Feed it Korean RSS (via RSSHub, self-hosted for one's own use) or crawl4ai (Apache). Add a "lesson-informed" prompt from the feedback table.
2. **Research → article**: call GPT Researcher (Apache-2.0, pip) for a sourced report. Optionally borrow STORM's perspective-guided outline step. Always keep a human fact-check gate, since STORM says outputs need significant edits.
3. **Script / long-form**: an LLM writes the script from the report. Self-filmed footage is recommended over stock footage for YPP safety. Use auto-editor (Unlicense) for silence cuts and PySceneDetect (BSD-3) for scene boundaries. All of these are FFmpeg-friendly CLIs.
4. **Subtitles (Korean)**: faster-whisper (MIT) or whisperX (BSD-2) for word timestamps. FunClip's Paraformer is Chinese-first and not a fit for Korean.
5. **Shorts**: AI-Youtube-Shorts-Generator local mode (MIT, importable), or AutoClip CLI/MCP (MIT). The pipeline is highlight ranking with score, hook and reason → face-tracked 9:16 crop → burned-in subtitles.
6. **TTS (if needed)**: MeloTTS-KR (MIT, stale) or CosyVoice 3 (license to verify). Avoid F5-TTS weights (CC-BY-NC), and treat XTTS-v2 (CPML) as restricted.
7. **Repurposing**: replicate n8n #6899 as a SQLite `derivatives` table with one row per (source_id, format) and a status of `draft → pending_review → approved → scheduled → published`.
8. **HITL**: mirror Agent Inbox actions (accept / edit / respond / ignore) and darkzOGx gates (fact review, media rights, no placeholder media) as FastAPI endpoints. The Hermes agent should only ever move items to `pending_review`.
9. **Distribution**: self-host Postiz (AGPL; fine for own use) and push via its public API or MCP. Expect weeks for Meta, YouTube and TikTok app approvals. Use listmonk (AGPL single binary) or Ghost (MIT) for the newsletter. Korean platforms (Naver Blog, Tistory) need custom work; no verified OSS covers them.
10. **Feedback**: a nightly YouTube Analytics API pull into SQLite with 24-hour and 7-day snapshots. An LLM proposes lessons, the human approves, and approved lessons feed the next ideation prompt. Delegate title and thumbnail A/B tests to YouTube Test & Compare.
11. **Avoid**: HunyuanVideo (South Korea excluded), and Remotion if the business may grow past 3 employees (Revideo or Motion Canvas are MIT alternatives; Motion Canvas releases are stale). Treat the archived LangChain/CrewAI repos as reference only.

### Gaps
- No verified documentation of the "Hermes agent" consuming SKILL.md or MCP from these projects. Portability is inferred from their generic Skill/MCP/CLI surfaces.
- Korean-language quality benchmarks were not found for faster-whisper vs whisperX vs Qwen3-ASR, nor for MeloTTS vs CosyVoice. This needs hands-on testing.
- No verified OSS uploader for Naver Blog, Tistory or Naver Clip was found within this research budget.
