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
