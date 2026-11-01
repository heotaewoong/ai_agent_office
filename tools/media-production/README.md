# Opt-in cinematic review production

This package adds an explicit review route without replacing the legacy worker.
Install `skills/heobrain-cinematic-production` into the owner's Codex skill directory
and the existing EC2 user's skill directory. Read its SKILL.md before invocation.
The bridge and scripts run media operations only on Linux/EC2. Private source files,
credentials, cue translations, plans and rendered assets do not belong in Git.

## Route

1. Read project instructions and identify the exact registered input asset.
2. Run `cinematic_review.py --state-root STATE --backend-root BACKEND prepare`
   with `--job-id`, `--expected-hash`, `--source-draft`, `--source-name`,
   `--skill-root` and a fresh `--output-id`.
   `--allow-previous-source-input` requires an explicitly selected older input;
   it records provenance and does not change the current job source.
3. Benchmark Blender with `blender --background --factory-startup --threads 1
   --python SKILL/scripts/blender_pilot.py -- OUTPUT still`.
   Inspect the still. The saved `.blend` can then render its 48-frame animation;
   do not rerun the scene builder into an existing output directory.
4. For Remotion, copy CaptionPilot.tsx into OUTPUT, supply private validated
   `cues.json`, and put the selected input at `public/baseline.mp4` on EC2.
   Reuse the installed Node modules and Chromium. Set CHROME_PATH and invoke
   `node SKILL/scripts/render_caption.cjs OUTPUT` once. This template samples
   seconds 8–16; adjust it for another input rather than assuming caption alignment.
   Its output is silent; add an exact common source-audio segment for comparison.
5. Run the bridge `verify --plan PLAN --file FILE --frames N --duration S
   --width W --height H`. Full decode and exact dimensions/count are required.
6. Inspect the actual result, then `register --plan PLAN --title TITLE`.
   Registration creates an unapproved review via existing `register_assets`.
   It does not approve source/release, start workers or publish.

Changed input/source/SKILL hashes stop verification or registration. Rendering
scripts are tracked separately by their execution receipts. Registration checks
output hashes and preserves approval fields; the normal worker remains default.
Do not mistake this opt-in integration for automatic invocation on every job.

## Runtime and limits

The pilot was tested on Blender 5.0.1 (official Ubuntu packages), Remotion 4.0.539,
React 19.1.0 and installed Chromium. Blender's generated procedural geometry is an
original camera/material test, not a faithful model of the live Babylon.js office,
a physics simulation, facial rig or feature-film quality claim. Blender script is
GPL-3.0-or-later. Remotion has its own licensing terms; check eligibility before
commercial scaling. No GPU, paid API or new subscription is required by this path.

Run one renderer at a time. Disable bundle caching and symlink public assets to
avoid duplicating large files on a small EC2 disk. Preserve failed logs and all
original media. Remove this opt-in package to disable it; never delete media or
approvals as part of removal.

Local checks: `python -m pytest tools/media-production/tests -q`.

## Full-length bilingual caption production

The 148-second vertical composition can render its lower caption panel separately
with `CaptionPanel.tsx` and `render_caption_full.cjs`. This preserves the selected
picture layout and avoids decoding the entire video inside every Chromium frame.
Private runtime `cues.json` must come from recorded character alignment and
independently matched source audio; do not shift another edit's SRT globally.
`caption_timing.py` rejects missing text, unreliable audio anchors, orphan
punctuation, large overlaps and out-of-range cues.

Copy the component, `caption_layout.cjs`, renderer and validated private cue data
into a fresh EC2 artifact directory. Reuse installed Node modules and CHROME_PATH.
The renderer checks every phrase's actual browser layout after fonts and the
1080px composition size are ready. Global client rectangles may refer to an
offscreen or zero-width staging layout, so the check waits and uses local offsets.
`--layout-only` repeats the still/layout proof without re-rendering the full panel.

The panel is 1080x660, 3552 frames at 24fps. Overlay it at y=1220 on the existing
1080x1920 picture with FFmpeg, and copy the original audio stream. These dimensions
are specific to the reviewed vertical layout, not a generic platform-safe preset.
Require full decode, exact frame count, AAC packet and timestamp identity,
phrase-to-panel frame checks and native full playback before delivery. The
standard review bridge pins input/source/SKILL hashes and registers only a new
unapproved draft.

Local checks additionally include:
`node --test tools/media-production/tests/caption_layout.test.cjs`.
