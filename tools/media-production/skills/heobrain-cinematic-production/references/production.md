# Production and review criteria

For a shot, record purpose, in/out times, camera position/target, principal action,
dialogue, bilingual caption interval, music/SFX and transition. Put long story
briefs in the private project ledger, not in the reusable skill.

Blender: benchmark one still before an animation; preserve the .blend and camera
keyframes. Prefer existing licensed geometry. Check contact with the floor,
bounding clearances and all rendered frames for abrupt motion. A procedural
camera test does not prove physics, facial animation, combat staging or feature-
film realism. Use Cycles CPU or an actually tested engine; don't claim GPU use.

Remotion: captions remain inside the chosen platform-safe layout. Show complete
phrases, English and Korean with clear hierarchy, no orphaned glyphs, short
fade/position movement at cue boundaries. Keep existing baked captions unless
the user approves a separate replacement; explain duplicate caption layers.
New SRT translations need provenance and timing checks. Reusing a subtitle from
another cut requires confirming the actual local scene and timing.

Reported 1:20–1:28 discontinuity: inspect native PTS/frame count, image changes,
black/freeze intervals and audio separately. A black iris may be an editorial
effect, not a decoder freeze. For the first repair, maintain the audio and total
duration while replacing only the problematic picture interval. Do not hide
unverified dialogue or lip-sync issues behind a transition.

Completion evidence: exact input/output SHA, renderer/version, dimensions,
duration, actual decoded frames, complete decode, caption bounds/overlap, original
preservation, changed-variable list, native playback status, rights/credits and
unresolved findings. RMS/SSIM/LUFS do not establish cinematic quality by themselves.

Blender official license: https://www.blender.org/about/license/
Command line: https://docs.blender.org/manual/en/latest/advanced/command_line/
Remotion license: https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
Remotion renderer: https://www.remotion.dev/docs/renderer/render-media

Remove or disable this opt-in path without deleting existing media, receipts,
approvals or state. It does not alter the default production worker automatically.
