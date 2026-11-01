---
name: heobrain-cinematic-production
description: "Create and review HeoBrain cinematic 3D scenes, animated bilingual captions, and film edits using Blender and Remotion on the existing EC2 render host. Use for video production or motion improvement requests, not ordinary office UI changes."
---

# HeoBrain cinematic production

Turn a specific video brief into a short, inspectable production sample before
extending it. A director persona is not a quality check. This skill is an opt-in
review-production path, not authority to approve, publish, schedule or spend.

## Start from the selected version

Read applicable project instructions, current user request and production ledger.
Record the chosen input's draft ID, filename, SHA-256, duration and time range.
Preserve the original and all previous versions. A newly preferred source replaces
earlier aesthetic assumptions, not its underlying file. Never quietly switch the
user's selected 148-second vertical video to the different 113-second edit.

Use `scripts/cinematic_review.py prepare` on EC2 to bind a review plan to the
current job source hash, exact selected input asset and this SKILL.md hash. If an
older input is explicitly selected, retain that provenance in the plan. Do not
overwrite or reapprove the job source to make a render attach successfully.

## Choose the production operation

- **Blender 3D:** for new geometry, materials, lights, camera paths, character
  rigging, animation or simulated motion. Start with a bounded CPU still benchmark
  and a 2–5 second scene. `scripts/blender_pilot.py` is a procedural camera-and-
  lighting proof, not a replica of the live office or completed character rigging.
  Inspect silhouettes, grounding and camera/vehicle clearances. A smooth camera
  path must not intersect buildings or pass through a ship.
- **Existing office:** preserve the actual Babylon.js layout and identity. Use
  its native camera path for footage of the real app; don't call a newly modeled
  Blender set an exact screen capture. See `references/production.md`.
- **Remotion motion:** use `assets/CaptionPilot.tsx` and
  `scripts/render_caption.cjs` for timed titles, restrained entrances, semantic
  emphasis and English/Korean captions. Preserve picture framing and input audio
  during the first caption comparison. Avoid bounce, constant zoom or animation
  that competes with reading. Phrase emphasis is not word-level forced alignment.
- **Transition repair:** inspect the reported time range before changing it.
  Distinguish frozen frames from an intentional black/iris transition, compression
  and buffering. Match action direction, camera speed and color; use short visual
  bridges only where motivated. Keep the existing audio clock in the first test.
- **HyperFrames or other tools:** evaluate an actually available capability only
  when it solves a demonstrated gap. No claim of use from installation or a link.

## Production controls

Generated media, frames, audio and .blend files stay under the existing EC2 state
artifacts directory. No local video render/download. Install only an explicitly
requested tool from a verified source after checking license, compatibility,
storage and memory. Don't resize EC2, add a GPU, buy assets or call paid APIs from
this skill. Run one renderer at a time and bound threads, frames and duration.
Inspect existing completion markers before starting another process.

Keep actual product capabilities separate from fictional SF missions. Use owned,
original or rights-cleared assets. A reference film is creative research, not
permission to copy footage or train on it. Do not clone a recognizable actor's
voice or call a synthetic speaker the actual actor.

## Verify and hand off

Read `references/production.md` for the shot and caption checks. Use
`scripts/cinematic_review.py verify` to check the exact rendered files, full decode,
dimensions, actual frames and duration. Save measured loudness/peak and audio
offset separately from subjective voice/music preference. Compare a fixed range,
changing one factor at a time where practical.

The register command rechecks input, skill, output hashes and current source
version before calling the existing office `register_assets`. It adds only an
unapproved review draft; source/release approvals and production manifests remain
unchanged. Changed source or unknown results stop registration; preserve files and
report the hold. Never forge approval or weaken authentication for playback.

Report installed skill, invoked skill hash, actual tool execution, file checks,
native playback and platform upload as separate facts. Do not call the test a
finished film or a quality improvement until its actual result supports that claim.
