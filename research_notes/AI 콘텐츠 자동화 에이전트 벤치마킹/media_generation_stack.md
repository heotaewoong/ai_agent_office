# AI Media Generation Stack for Korean-Language Content (blog visuals, YouTube long-form, Shorts, newsletter) — as of 2026-10-27

> Research date: 2026-10-27. All prices USD unless noted, list prices, pre-tax. Many vendor pages carry no "last updated" stamp; where a page was undated this is stated. The market moved a lot in 2026 (Sora shut down, Veo 3.1 Preview retired from the Gemini API, new "Gemini Omni Flash", ElevenLabs v4, Wan 3.0, Seedance 2.5, etc.), so treat anything not re-checked within ~30 days as stale.

## 1. Video generation (T2V / I2V): closed APIs vs open-weight models

### Takeaway
The 2025 names in the brief have largely been superseded: OpenAI Sora is gone (app shut down Apr 2026, API Sept 24 2026), and Veo 3.1 Preview was shut down on the Gemini API on Oct 22 2026 in favour of **Gemini Omni Flash** (~$0.10/s at 720p). Veo 3.1 itself is still sold via Runway's API ($0.10–0.40/s). The quality leaders on Artificial Analysis are now Wan 3.0, MiniMax H3, Seedance 2.5 and FLUX 3. For local, commercially usable models the realistic choices are **Wan 2.2 (Apache 2.0; the 5B variant fits a 24 GB card)** and **LTX-2.x (free under $10M annual revenue)**. **HunyuanVideo's license excludes South Korea**, so a Korean operator cannot use it.

### Cited Findings
**Status changes (critical)**
- OpenAI told developers on Mar 24 2026 that Sora was being deprecated. The Sora app and sora.com shut down Apr 26 2026, and the Videos API and every Sora 2 model alias were removed on **Sept 24 2026**. No API successor was named. — [Zilliz FAQ](https://zilliz.com/ai-faq/what-is-the-sora-shutdown-timeline); [TechJack brief](https://techjacksolutions.com/ai-brief/openai-videos-api-sora-2-deprecated-september-2026/); [invideo (Aug 2026 update)](https://invideo.io/blog/sora-ai-video-generator/). These are secondary sources. Supporting evidence: OpenAI's current API pricing page lists no video models at all ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)).
- Gemini API video docs: the **Veo 3.1 Preview models (standard, Fast, Lite) "was shut down" on October 22, 2026**. Google recommends migrating to Gemini Omni Flash (`gemini-omni-1.1-flash`) or to GA Veo models on the "Gemini Enterprise Agent Platform" (the Vertex AI successor). Omni Flash takes text, image, audio and video inputs and supports multi-turn conversational editing. — [Gemini API video docs](https://ai.google.dev/gemini-api/docs/video)
- Gemini Omni Flash launched at Google I/O in May 2026 and rolled out to the Gemini app, Flow, YouTube Shorts and YouTube Create. Its avatar mode was held back at launch. — [TNW](https://thenextweb.com/news/google-gemini-omni-flash-video-model-io-2026)

**API prices (per second of output)**
- **Gemini Omni Flash** (Gemini API, paid tier only, no free tier): input $1.50/1M tokens, video output $17.50/1M tokens. 720p bills at 5,792 tokens per second, which Google says is "approximately $0.10 per second". The page lists no 1080p/4K or batch rates. Page last updated 2026-10-26. — [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- **Runway API** (1 credit = $0.01): gen4_turbo $0.05/s; **gen4.5 $0.12/s**; aleph2 (the video-to-video editing successor to Aleph) $0.28/s, minimum 56 credits; **veo3.1 $0.40/s with audio, $0.20/s without**; **veo3.1_fast $0.15/s with audio, $0.10/s without**; act_two (performance capture) $0.05/s. The Magnific video upscaler costs $0.007–0.012 per output frame. — [Runway API pricing](https://docs.dev.runwayml.com/guides/pricing/)
- **Kling 3.0**: secondary sources disagree. One gives an official baseline of about $0.084/s (720p, no audio), $0.112/s (1080p, no audio), $0.140/s (1080p with audio) and $0.42/s (4K). An older June 2026 guide says about $0.10/s at 720p and $0.16/s at 1080p, with O3 at $0.24–0.40/s. Third-party resellers (EvoLink, fal) start around $0.075/s. Official packages are prepaid ($9.80–$7,560) and expire after 180 days. — [aireiter Kling 3 guide](https://aireiter.com/blog/kling-3-api-pricing-guide-2026); [evolink](https://evolink.ai/blog/kling-3-o3-api-official-discount-pricing-developers); [cloudzero](https://www.cloudzero.com/blog/kling-ai-pricing/)

**Quality ranking: Artificial Analysis text-to-video leaderboard (with audio), v2.1, fetched 2026-10-27 (page undated; notes "9 models added in last 30 days")**. Prices are the creator's API cost for one minute at 1080p.
- #1 Wan 3.0 (Alibaba): Elo 1174, $12.00/min, released Aug 2026, closed
- #2 Utopai X: Elo 1168, no API
- #3 **MiniMax H3 (768p)**: Elo 1158, $4.80/min, marked with a Hugging Face (open-weights) link
- #4 HeyGen Video 1: Elo 1157, $2.40/min, released Oct 2026
- #5 Dreamina Seedance 2.5 (ByteDance): Elo 1156, $34.12/min
- #6 FLUX 3 Max (720p, BFL via fal): Elo 1155, $2.55/min
- #8 FLUX 3: Elo 1142, $17.40/min
- #9 Seedance 2.0: Elo 1136, $22.45/min
- #10 **Gemini Omni Flash 1.1**: Elo 1128, $9.12/min
- #12 Grok Imagine Video 1.5: Elo 1057, $15/min
- #13/#16 HappyHorse 1.1/1.0 (Alibaba-ATH)
- #15 Wan 2.7: Elo 1037, $9.00/min
- #17 Kling 3.0 Omni 1080p Pro: Elo 1020, $8.40/min
- #18 Kling 3.0 1080p Pro: Elo 1000, $10.08/min (the board's anchor)
- #20 PixVerse V6: Elo 983, $6.90/min
- LTX-2.5 Fast (949) and LTX-2.5 Pro (944) rank below the top 20. HunyuanVideo, Luma Ray, Pika and Sora do not appear in the top 20.
- Source: [Artificial Analysis T2V leaderboard](https://artificialanalysis.ai/video/leaderboard/text-to-video)
- Earlier 2026 snapshots differ: Seedance 2.0 led at 1,216 per fal (June 26 2026), and Gemini Omni Flash led at 1245 per invideo (Aug 2026). The board is volatile, and Elo scales shift between versions. — [fal.ai guide](https://fal.ai/learn/tools/best-text-to-video-apis-2026); [invideo](https://invideo.io/blog/best-ai-video-model/)

**Open-weight video**
- **Wan 2.2** was released July 28 2025 under **Apache 2.0**. It comes as a 27B MoE (14B active) and a 5B model; the 5B model targets an RTX 4090. Wan 2.5 (Sept 2025), 2.6 (Dec 2025), 2.7 and 3.0 are **API-only, with no published weights**, so Wan 2.2 is still the newest downloadable Wan. Tongyi released Wan-Animate-2 weights (character animation) in Aug 2026, but one Wan-derived release uses a custom revenue-gated license, so check each card. — [howaiworks: open weights stopped at 2.2](https://howaiworks.ai/blog/alibaba-wan-open-weights-stopped-at-2-2); [flowjam review](https://www.flowjam.com/blog/wan-ai-review-2026)
- VRAM: Wan 2.2 5B stays around 22.9 GB on a 4090. A14B needs 41–60 GB on a single GPU unless you use community GGUF quantisations. — [magichour LTX-2.3 vs Wan 2.2](https://magichour.ai/blog/ltx-2-3-vs-wan-2-2)
- **LTX-2 Open Weights License** (dated Jan 5 2026; covers LTX-2 versions released since Oct 23 2025): free for commercial use; entities with **annual revenue ≥ $10,000,000** (affiliates counted together) must buy a paid license. A secondary source says products that compete with Lightricks also need a separate license. It is a revenue-conditional grant, not OSI open source. — [scancode license copy](https://scancode-licensedb.aboutcode.org/ltx-2-cla-2026.html); [Lightricks PDF](https://static.lightricks.com/legal/ltx-2-open-weights-license-0.X.pdf); [innfactory](https://innfactory.ai/en/ai-models/lightricks-ltx/)
- **HunyuanVideo (Tencent Hunyuan Community License)**: "Territory" means the worldwide territory **excluding the EU, UK and South Korea**. A survey says HunyuanVideo 1.5 carries the same exclusion and forbids using outputs to improve other AI models. Products with more than 100M MAU must request a license. — [DeepWiki HunyuanVideo license](https://deepwiki.com/Tencent/HunyuanVideo/5-license-and-legal); [creativeainews survey](https://www.creativeainews.com/articles/best-open-source-ai-video-models-2026/); [Hunyuan3D-2 LICENSE (same clause)](https://huggingface.co/tencent/Hunyuan3D-2/blob/main/LICENSE)

### Inferences
- For a Korean operator, HunyuanVideo is **not licensable** in South Korea. Drop it from the local stack completely, which leaves Wan 2.2 and LTX-2.x.
- Pipelines built on Sora 2 or Veo 3.1 Preview via the Gemini API are now broken. The cheapest replacements for the same role are Gemini Omni Flash (~$0.10/s at 720p) and Veo 3.1 Fast via Runway ($0.10–0.15/s). Runway is also a convenient single API for Veo, Gen-4.5, Aleph-style editing and ElevenLabs TTS.
- Cost tiers per second of finished generated footage, roughly: premium $0.20–0.57 (Veo 3.1 with audio via Runway; Seedance 2.5 at $34/min ≈ $0.57/s); mid $0.10–0.20 (Omni Flash, Kling 3.0, Wan 3.0 at $0.20/s, Gen-4.5); budget $0.04–0.08 (HeyGen Video 1, FLUX 3 Max 720p, MiniMax H3 at $0.08/s, Gen-4 Turbo at $0.05/s).
- MiniMax H3 is the only top-5 model that AA marks as open weights. If its license allows commercial use, it would be the strongest local option. It was not verified (see Gaps).

### Gaps
- No primary OpenAI deprecation page was fetched for the Sora shutdown; the dates come from consistent secondary sources.
- Official GA Veo prices on Google Cloud's "Agent Platform" (Vertex) were not retrievable; the page returned truncated content. Veo 3.1 prices above come from Runway's resale list.
- Luma Ray (Ray3), Pika, and MiniMax/Hailuo direct API prices were not individually verified. AA lists MiniMax H3 at $4.80/min; Luma and Pika are not in AA's top 20.
- The MiniMax H3 open-weights license, VRAM needs and Korean prompt handling are unknown.
- Mochi (Genmo) was not researched for 2026 status; it was not on the leaderboard.
- No source evaluates how natural **Korean spoken dialogue / lip-sync inside generated video** is (Veo, Omni, Kling, Seedance native audio). It has to be tested in-house.

## 2. Image generation and thumbnails (incl. Korean text rendering)

### Takeaway
For API thumbnails and blog images, Google's Nano Banana family is the default value pick ($0.034–0.134 per image). OpenAI's gpt-image-2 and gpt-image-1-mini are token-priced. FLUX API output is commercially licensed, but local FLUX weights are mixed: schnell and FLUX.2 klein 4B are Apache 2.0, while dev and klein 9B are non-commercial weights. Midjourney has **no official API** and its ToS forbids automation. Qwen-Image (Apache 2.0, 20B) is the main open model claiming Korean text rendering. **No benchmark of Hangul rendering exists**, so test it yourself.

### Cited Findings
- **Gemini API image prices** (standard, paid tier, page updated 2026-10-26):
  - Nano Banana 2.1 (`gemini-nano-banana-2.1`): $0.0336 (1K), $0.0504 (2K), $0.113 (4K)
  - Gemini 3.1 Flash Image (Nano Banana 2): $0.045 (0.5K) to $0.151 (4K); $0.067 at 1K
  - Nano Banana 2 Lite: $0.0336 (1K)
  - **Gemini 3 Pro Image (Nano Banana Pro): $0.134 (1K/2K), $0.24 (4K)**
  - Gemini 2.5 Flash Image is deprecated and was shut down Oct 2 2026
  - Batch rates are lower
  - Source: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Imagen 4 no longer appears on the Gemini API pricing page. A July 2026 third-party comparison puts Imagen 4 at about $0.02/image on Vertex; this is unverified. — [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing); [aiweekly](https://aiweekly.co/learning-ai/ai-applications/best-ai-image-generators)
- **OpenAI image** (per 1M tokens, standard tier):
  - gpt-image-2: image input $8, image output $30, text input $5
  - gpt-image-1.5: image output $32
  - **gpt-image-1-mini: image output $8**, text input $2
  - Batch is half price. gpt-image-1 is no longer listed. Newer gpt-image-2.5 "sunburst/flare" variants are listed.
  - Source: [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- **Runway gen4_image**: $0.05 (720p) / $0.08 (1080p) per image. — [Runway API pricing](https://docs.dev.runwayml.com/guides/pricing/)
- **FLUX licensing**:
  - BFL says images from the BFL API include full commercial rights.
  - **FLUX.1 [schnell] and FLUX.2 [klein] 4B are Apache 2.0** (commercial use OK).
  - FLUX.1 [dev], FLUX.1 Kontext [dev], FLUX.2 [dev] and FLUX.2 [klein] 9B are under the FLUX Non-Commercial License; commercial use of the weights needs a license from bfl.ai/licensing.
  - Sources: [BFL help center](https://help.bfl.ai/articles/3670520907-can-i-use-the-api-for-a-commercial-application); [FLUX.1-dev NC license text](https://open.windriver.com/info/uni-license-list/licenses/flux-1-nc.html)
  - Conflict: the NC license text says outputs are not "Derivatives" and a quoted clause says outputs may be used "for any purpose (including for commercial purposes)". Other clauses tie "non-commercial" to receiving payment arising from the model or its output, and BFL has given no official clarification. — [HF discussion on FLUX.2-klein-9B](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B/discussions/24)
- **Midjourney**:
  - V8.x is current. Sources disagree on whether V7 or V8 is the default.
  - **No official public API**, and the ToS says "You may not use automated tools to access, interact with, or generate Assets".
  - All paid tiers include commercial use. Plans run from $10/mo (Basic) to $120/mo (Mega).
  - Sources: [unifically (Aug 2026)](https://unifically.com/ru/blogs/midjourney-api); [llmreference V8.1](https://www.llmreference.com/model/midjourney-v8-1); [aiweekly](https://aiweekly.co/learning-ai/ai-applications/best-ai-image-generators)
- **Qwen-Image**: a 20B MMDiT under **Apache 2.0** that allows commercial use with attribution. ComfyUI's docs list Korean among its high-precision text-rendering languages; most other sources mention only English and Chinese. — [ComfyUI docs](https://docs.comfy.org/tutorials/image/qwen/qwen-image); [opensourceforu](https://www.opensourceforu.com/?p=88851); [NVIDIA build](https://build.nvidia.com/qwen/qwen-image)
- **Korean text rendering**: no head-to-head Hangul benchmark was found. A Google developer-forum thread asks how Nano Banana Pro achieves "such high accuracy" in Korean rendering, but that is anecdotal. Hangul has 11,172 possible syllable blocks, which is why diffusion models struggle with it. — [Google AI dev forum](https://discuss.ai.google.dev/t/how-does-nano-banana-pro-achieve-such-high-accuracy-in-cjk-text-rendering-especially-korean-hangul-text-rendering/114043); [arXiv 2504.21325](https://arxiv.org/pdf/2504.21325)

### Inferences
- Thumbnail workflow: generate the **background or character art** with Nano Banana 2/2.1 ($0.03–0.07) or Pro ($0.134). Add the **Korean headline text as a real font layer** in code (Remotion, Satori, PIL) or in Canva/Figma, rather than relying on model-rendered Hangul. This guarantees correct spelling and lets you A/B test text variants for free.
- With open weights, Qwen-Image (Apache 2.0) and FLUX.1 schnell / FLUX.2 klein 4B are the clean commercial choices. Avoid FLUX dev and klein 9B for monetised content unless you hold a BFL license.
- Midjourney can only be part of a manual step in an automated agent pipeline, because its ToS bans automation.

### Gaps
- **Ideogram** (v3 or later) pricing and Korean text quality were not researched in this session.
- Official per-image dollar conversions for gpt-image-2 by size and quality were not extracted; OpenAI points to its calculator.
- Qwen-Image's VRAM requirement and any newer Qwen-Image versions (2.x) were not verified.
- No measured Hangul legibility or spelling-error rates exist for any model.

## 3. Korean TTS / voice, music and SFX

### Takeaway
ElevenLabs v4 is now #1 overall on Artificial Analysis's TTS arena ($0.08/1K chars, or $0.04 for v4 Turbo). However, **that arena has no Korean filter**, so its rankings do not show Korean quality. The cheapest high-quality API is Gemini 3.8 Flash TTS: about $0.00225 per 10 s until Dec 31 2026, with the price doubling in 2027. For local and open TTS, GPT-SoVITS (MIT, Korean, 5-second cloning), CosyVoice 2 (Korean) and MeloTTS-Korean (MIT, CPU) are the practical choices. Kokoro's Korean support is disputed. For Korean-native vendors (Supertone, Typecast, CLOVA Voice), current prices could not be retrieved.

### Cited Findings
- **ElevenLabs API** (per 1K chars, same rate on all tiers):
  - **v4 $0.08**, v4 Turbo $0.04, v3 $0.08, v3 Conversational $0.04, Multilingual v2 $0.08, Flash/Turbo $0.04
  - Plans: Starter $6, Creator $22 (275K v4 chars/mo), Pro $99, Scale $299, Business $990
  - Music $0.15/min (commercial use licensing on Starter+); Sound Effects $0.12/min
  - Dubbing v1 $0.33/min with watermark, $0.50/min without; Dubbing v2 $2.20/min
  - Scribe v2 STT $0.22/hour
  - Source: [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- Through **Runway's API**, ElevenLabs eleven_v4 cost $0.022/1K chars until Oct 12 2026 and $0.05/1K chars after that. eleven_v3 and multilingual_v2 cost $0.02 per 50 chars (= $0.40/1K). Text-to-sound costs $0.01/s. — [Runway API pricing](https://docs.dev.runwayml.com/guides/pricing/)
- **Artificial Analysis TTS leaderboard** (fetched 2026-10-27, page undated; **no language filter, so Korean is not ranked**):
  - #1 Eleven v4 Turbo (1333, $40/1M chars) and Eleven v4 (1333, $80/1M)
  - #3 Qwen-Audio-3.1-TTS-Plus (1306, $19.30)
  - #4 Cartesia Sonic 3.6 (1292, $49)
  - **#5 Gemini 3.8 Flash TTS (1280, $16.50)**
  - #8 Gemini 3.8 Flash-Lite TTS (1256, $11)
  - #10 Fish Audio Drama 3 Preview (1245, open weights)
  - #12 Mistral Voxtral 3 TTS (1221, $13)
  - #19 Ant Ming-3.0-tts (open weights)
  - Kokoro 82M v1.0 is #58 (1063, ~$0.65–0.70/1M); Chatterbox #78 (open); VibeVoice 1.5B #84
  - CosyVoice and F5-TTS are not listed
  - 18 of 98 models are open weights
  - Source: [AA TTS leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard)
- **Gemini TTS** (per 1M audio output tokens):
  - Gemini 3.8 Flash TTS $9.00 until Dec 31 2026, then $18.00 from Jan 1 2027; equivalent to $0.00225 per 10 s now
  - 3.8 Flash-Lite TTS $6, then $12; $0.0015 per 10 s
  - 3.1 Flash TTS Preview $20; 2.5 Flash Preview TTS $10
  - Source: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- **Google Cloud TTS Chirp 3: HD**: $30 per 1M chars after a 1M-char monthly free tier. Instant custom voice costs $60 per 1M chars. SSML tags count toward the billed characters. No language-specific rate is shown. — [Google Cloud TTS pricing](https://cloud.google.com/text-to-speech/pricing?hl=nl)
- **OpenAI TTS**: tts-1 $15/1M chars; tts-1-hd $30/1M chars; gpt-4o-mini-tts $0.60/1M text input tokens plus $12/1M audio output tokens. — [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- **Lyria (Google music)**: Lyria 3.5 full song $0.08 per song; Lyria 3 Clip Preview (30 s) $0.04; Lyria 3 Pro Preview $0.08. Paid tier only. — [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- **Typecast**: the ssfm-v30 model supports 37 languages including Korean. A pricing revision was announced Jul 24 2026, but the figures could not be retrieved. — [Typecast docs](https://typecast.ai/docs/ko/overview); [Typecast blog/news](https://typecast.ai/kr/learn/category/newsletter/)
- **Supertone**: released **Supertonic**, an open-source on-device TTS engine under MIT; one source dates it to January 2025, which is unverified. No hosted Supertone API price was found. — [hyper.ai notebook](https://hyper.ai/ko/notebooks/47088)
- **Naver CLOVA Voice Premium**: a monthly base fee per application includes 1,000,000 characters pooled across applications. Overage is billed per 1,000 characters. The actual amounts did not render in the fetched page. — [NCloud CLOVA Voice](https://www.gov-ncloud.com/v2/product/aiService/clovaVoice); [NCloud guide](https://guide.ncloud-docs.com/docs/clovavoice-overview)
- **Open-source Korean-capable TTS** (from the tts.ai aggregator, marketing-grade):
  - **GPT-SoVITS**: MIT; few-shot cloning from about 5 s of audio; supports Korean; cross-lingual
  - **CosyVoice 2** (Alibaba): Korean among 8 languages; voice cloning; streaming
  - **MeloTTS Korean**: MIT; fixed voices, no cloning; about 25M params; CPU-friendly
  - Sources: [tts.ai GPT-SoVITS](https://tts.ai/voices/gpt-sovits/); [tts.ai MeloTTS-Korean](https://tts.ai/voices/melotts-korean/?lang=ko)
- **Kokoro**: weights are Apache 2.0 with MIT inference code; it depends on GPLv3 espeak-ng. Korean support **conflicts**: PyKokoro docs list Korean, while the tts.ai listing (en, ja, zh, fr, it, pt, es, hi) omits it. — [HF Kokoro-82M card mirror](https://huggingface.co/muratbuker/Kokoro-82M); [PyKokoro docs](https://pykokoro.readthedocs.io/); [tts.ai Kokoro](https://tts.ai/voices/kokoro/?lang=ko)
- A **Korean TTS Arena** ("한국어 TTS 아레나") is run by channelcorp on Hugging Face. Its leaderboard could not be read from the static page. — [HF Space](https://huggingface.co/spaces/channelcorp/Ko-TTS-Arena)

### Inferences
- Korean narration costs are trivial at any API tier. An 8-minute script is only a few thousand characters (assumption below), so even ElevenLabs v4 costs well under $1. Choose on Korean prosody quality and voice consistency, not on price.
- Pick the TTS by blind listening tests in Korean, for example on the channelcorp Korean TTS Arena or your own A/B tests. The global AA Elo is English-weighted.
- Lock in Gemini 3.8 Flash TTS before Jan 1 2027 if it is used, or budget for the 2× price increase.
- If you voice-clone a real person (e.g. the creator's own voice), store consent records. That ties into the deepfake disclosure rules in section 7.

### Gaps
- **No measured Korean TTS quality ranking** (MOS/Elo) was retrieved for ElevenLabs v3/v4, Supertone, Typecast, CLOVA Voice, Chirp 3 HD or OpenAI. The channelcorp arena leaderboard was not accessible.
- Supertone hosted API, Typecast API and CLOVA Voice per-character prices as of Oct 2026 were **not found**.
- F5-TTS's Korean support and weight license were not verified. It is commonly reported as CC-BY-NC, which would make it non-commercial; this is unconfirmed.
- Licenses for Fish Audio Drama 3 and Ming-3.0-tts open weights were not checked.
- ElevenLabs free-tier attribution/commercial terms for TTS (as opposed to Music) were not stated on the page fetched.

## 4. Transcription and subtitles (Korean)

### Takeaway
On the only multi-vendor Korean CER benchmark found (rtzr, AI-Hub data), stock OpenAI Whisper averages **11.39% CER**. **Naver CLOVA Speech scores 7.52%** and ReturnZero (RTZR) 5.91%. A Korean fine-tune of Whisper reaches 6.59%. Whisper large-v3 zero-shot is much better on clean read speech (5.3% on FLEURS). API transcription is nearly free ($0.003–0.006/min OpenAI; $0.22/hour ElevenLabs Scribe v2).

### Cited Findings
- **rtzr Awesome-Korean-Speech-Recognition** benchmark (CER %, 3,000 sentences per AI-Hub set; evaluation date not stated):

  | Service | Avg CER (%) |
  |---|---|
  | OpenAI Whisper (variant unspecified) | 11.39 |
  | Google STT v2 | 11.50 |
  | Azure batch | 10.88 |
  | AWS Transcribe | 11.11 |
  | Gemini 2.0 Flash | 16.58 |
  | Deepgram nova-2 | 21.02 |
  | ETRI | 10.19 |
  | **Naver ClovaSpeech** | **7.52** (best on Korean lecture: 7.08) |
  | **RTZR** | **5.91** |
  | RTZR fine-tuned Whisper | 6.59 |

  - Source: [rtzr GitHub](https://github.com/rtzr/Awesome-Korean-Speech-Recognition). RTZR is a Korean STT vendor, so the benchmark has a possible conflict of interest.
- Whisper-large-v3 zero-shot CER is 5.31% on FLEURS Korean and 6.01% on Common Voice 25. A Korean fine-tune cuts that by about 1.2×. — [BuzzASR/korean model card](https://huggingface.co/BuzzASR/korean)
- **OpenAI transcription prices** (per minute): Whisper $0.006; gpt-4o-transcribe $0.006; **gpt-4o-mini-transcribe $0.003**; gpt-transcribe $0.0045; gpt-4o-transcribe-diarize $0.006. — [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- ElevenLabs **Scribe v2** costs $0.22/hour (keyterm prompting +$0.05/hour); Scribe v2 Realtime $0.39/hour. — [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- A Korean production team has written up its experience optimising faster-whisper for Korean. — [SceneMaker blog](https://doc.scenemaker.solbox.com/en/blog/4)
- There is a whisper-large-v3-turbo Korean GGML conversion for whisper.cpp (CPU/edge use). — [HF model](https://huggingface.co/royshilkrot/whisper-large-v3-turbo-korean-ggml)

### Inferences
- When generating subtitles from your **own TTS output**, you already have the script. The fastest and most accurate path is forced alignment of the known script to the audio, or using the TTS vendor's timestamps where provided, not open-ended ASR. ASR quality matters mainly for screen recordings with live voice and for interview footage.
- Local default: faster-whisper large-v3 (or turbo), plus a custom vocabulary or post-correction pass with an LLM for AI terms (e.g. "에이전트", product names). If accuracy on spontaneous Korean speech matters, CLOVA Speech is the vendor-benchmarked accuracy leader among big-tech options.

### Gaps
- The specific Whisper version in the rtzr table, and the benchmark run date, are unknown.
- **WhisperX Korean alignment quality** and Korean wav2vec2 alignment-model availability were not verified this session.
- CLOVA Speech's current per-minute price was not retrieved.

## 5. Programmatic editing and rendering

### Takeaway
**Remotion** (React) is free for individuals and companies of **up to 3 people**. Larger companies need a paid license: $25/seat/month for Creators, or $0.01/render with a $100/month minimum for Automators. **Revideo** (MIT, a fork of Motion Canvas) is the permissive alternative for API-driven templated renders. FFmpeg stays the backbone for concatenation, loudness normalisation and subtitle burn-in.

### Cited Findings
- Remotion license:
  - Free for individuals, non-profits and for-profit organisations with ≤3 employees (commercial use included), and for evaluation.
  - Companies with 4+ people need a Company License.
  - You may not resell or relicense derivatives of Remotion itself.
  - The license "will change slightly in Remotion 5.0".
  - Source: [Remotion LICENSE.md](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)
- Remotion pricing (page undated, © 2026):
  - **Creators $25/month per seat** (manual/local creation)
  - **Automators $0.01 per render, $100/month minimum** (automator developers don't need seats)
  - Enterprise from $500/month
  - Source: [remotion.pro/license](https://www.remotion.pro/license)
- **Revideo** is MIT-licensed and forked from Motion Canvas. It renders TypeScript video templates with dynamic inputs via an API and includes an embeddable React player. Revideo was built by Haven (YC). — [Revideo docs](https://docs.re.video/); [Product Hunt](https://www.producthunt.com/products/revideo); [YC Haven](https://www.ycombinator.com/companies/haven-3)
- Motion Canvas is reported as MIT, from a third-party page. Remotion's own comparison describes Motion Canvas as an animation editor, not a library meant for broader use. — [Remotion compare](https://www.remotion.dev/docs/compare/motion-canvas); [Smithery](https://smithery.ai/skills/davila7/motion-canvas)

### Inferences
- For a ≤3-person Korean office, Remotion is free and is the most mature choice for data-driven Shorts and explainer templates (captions, charts, screenshot pans). Budget $100/month (Automators minimum) if the team grows past 3.
- A typical pipeline: script → TTS (with timestamps) → Remotion/Revideo composition (screenshots, screen recordings, generated B-roll, Korean caption track styled with Pretendard/Noto Sans KR) → FFmpeg loudnorm and encode → upload.

### Gaps
- Licenses for **FFmpeg** (generally LGPL/GPL depending on build flags), **auto-editor** and **PySceneDetect** were not verified this session; confirm them from the repos.
- Revideo's 2026 maintenance status (commit activity) was not checked; Haven may have pivoted.
- **CapCut and Vrew automation**: not researched. No source was found on public editing APIs for either; treat them as manual GUI tools until confirmed.

## 6. Avatars and lip-sync

### Takeaway
HeyGen's API costs about $1–4 per generated minute (Avatar IV Digital Twin ≈ $4 per 1080p minute, July 2026 rates; secondary sources). HeyGen also now ranks #4 on AA's text-to-video board with "HeyGen Video 1" at $2.40/min. For open source, **MuseTalk (MIT; weights allowed commercially)** is the real-time pick and **LatentSync (Apache 2.0 per a vendor blog)** the quality pick. Wav2Lip weights are non-commercial.

### Cited Findings
- HeyGen API pricing:
  - $1–4 per generated minute depending on engine; Digital Twin on Avatar IV ≈ $4 per 1080p minute (cites HeyGen's July 2026 API rates).
  - The API uses a separate pay-as-you-go USD wallet, and free API credits ended Feb 2026.
  - Subscription credit math per minute differs by source (e.g. 4 credits on Avatar III, 31 on Avatar IV Video Look, 48 on Avatar V).
  - Sources: [forasoft](https://www.forasoft.com/blog/article/heygen-alternatives); [anam.ai](https://anam.ai/blog/heygen-pricing); [creatify](https://creatify.ai/blog/heygen-pricing-(2026)-plans-and-what-you-ll-actually-pay)
- HeyGen Video 1 (Oct 2026) has Elo 1157 on AA T2V at $2.40/min. — [Artificial Analysis](https://artificialanalysis.ai/video/leaderboard/text-to-video)
- **MuseTalk**: code under MIT; the README says the trained models may be used for any purpose, including commercially. Dependencies (whisper, dwpose) have their own licenses, and the test data is research-only. It does one-step latent inpainting on a 256 px face region, making it real-time capable. — [MuseTalk GitHub](https://github.com/TMElyralab/MuseTalk); [sync.so](https://sync.so/blog/what-is-musetalk)
- **LatentSync** (ByteDance): the vendor blog says full code and weights are Apache 2.0, which was not confirmed against the LICENSE file. It uses multi-step latent diffusion: sharper output, but much slower. — [sync.so LatentSync](https://sync.so/blog/what-is-latentsync)
- Wav2Lip's README says "any form of commercial use is strictly prohibited" because it was trained on LRS2. A permissive code license does not cover models trained on restricted data. — [creativeainews lip-sync licenses](https://www.creativeainews.com/articles/open-source-lip-sync-licenses-commercial-use-2026/)
- Runway act_two (performance-driven character animation) costs $0.05/s. — [Runway API pricing](https://docs.dev.runwayml.com/guides/pricing/)

### Inferences
- For Korean explainers, a full-length talking-head avatar is the costliest line item ($8–32 per 8-minute video on HeyGen API) and adds deepfake-labelling obligations if it depicts a real person. Use avatars for intro/outro segments only, or skip them.

### Gaps
- **Synthesia** and **Hedra** 2026 API prices and Korean lip-sync quality were not researched.
- HeyGen's official API price page was not fetched directly; the figures come from secondary sources and they conflict.
- No source measured Korean phoneme lip-sync accuracy for any avatar tool.

## 7. Content credentials, watermarking, and disclosure rules (YouTube and Korea)

### Takeaway
Google's generators (Gemini Omni, Veo via YouTube tools) embed **SynthID plus C2PA**, and YouTube now **reads C2PA/SynthID and auto-labels** photorealistic AI content. Since May 2026 that label shows as an **overlay on Shorts** and below the player on long-form. AI-written scripts and generic TTS voices do not require a label. Korea's **AI Basic Act (in force since Jan 22 2026)** puts the labelling duty on AI service *providers*, not on general users who post outputs. Deepfakes must always be clearly labelled.

### Cited Findings
- Google DeepMind says content generated or edited with Gemini Omni carries **SynthID watermarks and C2PA content credentials**, verifiable in the Gemini app, with Chrome and Search support planned. The Adobe Firefly integration enables both by default. — [designcompass](https://designcompass.org/en/2026/05-1tp-3tea/20/gemini-omni-google-ai-video-model/); [CryptoBriefing](https://cryptobriefing.com/google-gemini-omni-flash-adobe-firefly-video/). These are secondary sources; no Google primary post was fetched.
- **YouTube**:
  - Disclosure has been required since May 21 2025 for meaningfully altered or synthetic content that looks realistic. AI scripts and generic TTS voices don't need a label.
  - Since May 2026, labels sit below the player on long-form and as an **on-video overlay on Shorts**. Lightly altered or unrealistic content is labelled only in the description.
  - YouTube reads C2PA metadata and SynthID, and its classifiers auto-label undisclosed photorealistic AI.
  - Labels on content made with YouTube's own AI tools (e.g. Veo, Dream Screen), or carrying C2PA marking it as fully AI-generated, **cannot be removed**.
  - Repeated non-disclosure can lead to removal or suspension from the Partner Programme. YouTube says a label alone does not change recommendations or monetisation eligibility.
  - Sources: [ppc.land](https://ppc.land/youtube-shifts-generative-ai-labels-to-spots-viewers-will-actually-see/); [medianama (May 2026)](https://www.medianama.com/2026/05/223-youtube-ai-content-labels-visible-adds-auto-detection-undisclosed-ai-videos/); [techwyse](https://www.techwyse.com/news/platform-updates/youtube-automatic-ai-labels-disclosure-may-2026). These are secondary sources, and they differ slightly on placement.
- **Korea AI Basic Act (인공지능 기본법)**, in force from 2026-01-22:
  - Generative AI outputs distributed externally must be marked as AI-generated, using a visible mark (logo or text) or an invisible one (watermark or metadata).
  - Deepfakes must be disclosed in a way users clearly recognise.
  - The duty falls on **businesses that provide AI products or services**. General users who consume or post AI outputs are not covered; platform services that keep generating outputs for users are.
  - Sanctions: a correction order, then a fine of up to ₩30M. A grace period of at least one year is reported.
  - Sources: [Newsis 2026-01-21](https://www.newsis.com/view/NISX20260121_0003484769); [wikidocs (Aug 2026)](https://wikidocs.net/blog/@openwiki/28121/); [SBS Biz (webtoon artists exempt, deepfake mandatory)](https://biz.sbs.co.kr/amp/article/20000286450); [KB Think](https://kbthink.com/life/daily/ai-basic-act.html)
- A ZDNet Korea piece (Oct 20 2026) argues the Act's watermark and responsibility provisions need revising because "watermarks can just be erased", which signals that amendments are under discussion. — [ZDNet Korea](https://zdnet.co.kr/view?no=20261020095628)
- ElevenLabs Dubbing is priced lower with a watermark ($0.33/min) than without ($0.50/min). — [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)

### Inferences
- Realistic generated B-roll in a Shorts video is likely to get a **visible on-video "altered or synthetic" overlay**, especially from Google models with SynthID/C2PA. That can hurt credibility for news-style or explainer content. Screenshots, screen recordings and clearly stylised or illustrative graphics avoid it.
- If the office sells AI-generated content production *as a service* to clients, it may count as a "provider" under the Korea AI Basic Act. Get a legal check before commercialising, and keep C2PA metadata rather than stripping it.

### Gaps
- Whether OpenAI gpt-image, Runway, Kling, MiniMax, Seedance and ElevenLabs embed C2PA or invisible watermarks in 2026 was not verified this session.
- No primary YouTube Help Center or MSIT (과기정통부) enforcement-decree text was fetched; the findings come from news and secondary summaries.

## 8. Practical cost model (60-second Short and 8-minute explainer) and B-roll strategy

### Takeaway
Voice, music, subtitles and thumbnails together cost **under $2 per video at any API tier**. **Generated video footage is 80–95% of the variable cost.** A 60 s Short costs about **$19–37 premium (about $51 with Seedance 2.5), $5–10 budget, and about $0 marginal locally**. An 8-minute explainer with mostly real screenshots and screen recordings plus 60–90 s of generated B-roll costs about **$30–45 premium, or up to about $110 with a full-length avatar or Veo with audio; $7–20 budget; and about $0 marginal locally**. The best way to save money and protect credibility is the same: keep generated clips to a minority of screen time.

### Cited Findings (unit prices used, all cited above)
- Video:
  - Veo 3.1 via Runway: $0.40/s with audio, $0.20/s without; Veo 3.1 Fast $0.15/$0.10
  - Gen-4.5 $0.12/s; Gen-4 Turbo $0.05/s
  - Source: [Runway](https://docs.dev.runwayml.com/guides/pricing/)
  - Gemini Omni Flash ~$0.10/s at 720p — [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
  - Seedance 2.5 $34.12/min; Wan 3.0 $12/min; MiniMax H3 $4.80/min; HeyGen Video 1 $2.40/min; FLUX 3 Max 720p $2.55/min — [AA](https://artificialanalysis.ai/video/leaderboard/text-to-video)
  - Kling 3.0 from ~$0.075/s through resellers — [aireiter](https://aireiter.com/blog/kling-3-api-pricing-guide-2026)
- TTS:
  - ElevenLabs v4 $0.08/1K chars — [ElevenLabs](https://elevenlabs.io/pricing/api)
  - Gemini 3.8 Flash TTS $0.00225/10 s — [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
  - Chirp 3 HD $30/1M chars with 1M free monthly — [Google Cloud](https://cloud.google.com/text-to-speech/pricing?hl=nl)
- Music: ElevenLabs Music $0.15/min ([ElevenLabs](https://elevenlabs.io/pricing/api)); Lyria 3.5 $0.08/song ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing))
- Images: Nano Banana Pro $0.134; Nano Banana 2.1 $0.0336 — [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Subtitles: gpt-4o-mini-transcribe $0.003/min — [OpenAI](https://developers.openai.com/api/docs/pricing)
- Rendering: Remotion is free for ≤3 people; otherwise $0.01/render with a $100/month minimum — [remotion.pro](https://www.remotion.pro/license)
- Avatar: HeyGen API $1–4/min — [forasoft](https://www.forasoft.com/blog/article/heygen-alternatives)
- Local: Wan 2.2 5B runs on a 24 GB RTX 4090 at ~22.9 GB — [magichour](https://magichour.ai/blog/ltx-2-3-vs-wan-2-2). LTX-2 is free under $10M revenue — [scancode](https://scancode-licensedb.aboutcode.org/ltx-2-cla-2026.html)

### Inferences (worked estimates; ASSUMPTIONS flagged)
Assumptions, all mine and not from sources:
- Korean narration ≈ 300–400 characters per minute.
- A Short is about 60 s of narration with about 40–48 s of generated footage, made from 6–8 clips of 6 s each. The rest is screenshots or text cards.
- Each kept clip takes **about 2× regeneration**, so you pay for about 2× the seconds you keep.
- The 8-minute explainer is 70–85% screenshots and screen recordings, with 60–90 s of generated B-roll.
- Electricity and GPU depreciation are excluded from the local tier.

**60-second Short**

| Line item | Premium API | Budget API | Local (RTX 4090-class) |
|---|---|---|---|
| Generated video (~45 s kept, ~90 s billed) | Veo 3.1 no audio via Runway $0.20/s → **$18**; with audio $0.40/s → $36; Seedance 2.5 ≈ $51 | Gemini Omni Flash 720p $0.10/s → **$9**; Gen-4 Turbo $0.05/s → $4.50; MiniMax H3 $0.08/s → $7.20 | Wan 2.2 5B or LTX-2: $0 marginal (minutes to hours of GPU time per clip; 720p-class) |
| Korean TTS (~400 chars) | ElevenLabs v4 → $0.03 | Gemini 3.8 Flash TTS → $0.014 | GPT-SoVITS / CosyVoice 2 / MeloTTS → $0 |
| Music/SFX | ElevenLabs Music 1 min → $0.15 | Lyria 3.5 → $0.08 | Royalty-free library → $0 |
| Subtitles | from script/timestamps → ~$0 | gpt-4o-mini-transcribe → $0.003 | faster-whisper → $0 |
| Thumbnail / cover (4 variants) | Nano Banana Pro → $0.54 | Nano Banana 2.1 → $0.13 | Qwen-Image / FLUX schnell → $0 |
| Render | Remotion (free ≤3 ppl) → $0–0.01 | same | FFmpeg / Revideo → $0 |
| **Total** | **≈ $19–37** (Veo 3.1 no-audio to with-audio) | **≈ $5–10** | **≈ $0 + GPU time** |

**8-minute explainer (480 s)**

| Line item | Premium API | Budget API | Local |
|---|---|---|---|
| Generated B-roll (60–90 s kept, 120–180 s billed) | Veo 3.1 no-audio $0.20/s → $24–36; Gen-4.5 $0.12/s → $14–22 | Omni Flash $0.10/s → $12–18; Gen-4 Turbo $0.05/s → $6–9 | Wan 2.2 / LTX-2 → $0 |
| Optional avatar intro/outro (1 min) | HeyGen ~$4 | HeyGen low engine ~$1 | MuseTalk / LatentSync → $0 |
| (Full-length avatar instead, 8 min) | +$32 | +$8 | $0 |
| Korean TTS (~2,400–3,200 chars) | ElevenLabs v4 → ~$0.26 | Gemini Flash TTS 480 s → ~$0.11; Chirp 3 HD → within free 1M tier | GPT-SoVITS etc. → $0 |
| Music bed (8 min) | ElevenLabs Music → $1.20 | Lyria 3.5 (a few songs) → ~$0.25 | library → $0 |
| Subtitles (8 min) | ~$0.05 | ~$0.02 | $0 |
| Thumbnails (4–6) | ~$0.80 | ~$0.20 | $0 |
| **Total** | **≈ $30–45** (no avatar); **≈ $60–110** with full avatar or Veo with audio | **≈ $7–20** | **≈ $0 + GPU time** |

- The remaining fixed monthly costs are small: Remotion is $0 for ≤3 people, otherwise $100+/month; ElevenLabs Creator is $22/month and covers 275K chars, enough for about 80+ eight-minute scripts. Labour (human review of every generated clip) dominates the real cost.
- **Recommended B-roll strategy for credibility (inference):**
  1. For explainers about AI news and tools, make **real screenshots, screen recordings of the actual product, official demo clips (with permission/fair use), and code-rendered charts or diagrams the default (70–90% of runtime)**. They prove the claim and avoid YouTube's "altered/synthetic" overlay.
  2. Use generated clips only for **abstract or metaphorical visuals** (e.g. "data flowing into an agent") and transitions, kept **clearly stylised** (illustration or 3D look rather than photoreal people or places). Never generate fake UI, fake people "using" a real product, or fake news footage.
  3. Use **image-to-video** from your own designed keyframes (Nano Banana / Qwen-Image → Omni Flash / Kling / Wan 2.2) for visual consistency with the channel's brand, rather than pure text-to-video.
  4. Keep C2PA metadata, and self-disclose in YouTube Studio whenever generated footage looks realistic. Auto-labelling on Shorts is visible anyway.
  5. Put Korean on-screen text as real font layers in Remotion, never baked into generated video or images.

### Gaps
- No published source gives a per-video cost benchmark for Korean Shorts or explainers; all totals above are my estimates from list prices.
- Real-world regeneration ratios (takes per kept clip) for each model are unknown; 2× is an assumption.
- Local generation throughput (seconds of video per GPU-hour for Wan 2.2 5B / LTX-2 on a 4090) was not measured or sourced.
- No audience or credibility study comparing generated vs. real B-roll in explainer content was found; the B-roll recommendation is reasoning from YouTube's labelling policy, not from data.
