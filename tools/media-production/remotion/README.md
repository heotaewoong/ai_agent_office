# AI Office Remotion production source snapshots

Source-only backup of the rendering components used for the AI Office film review.
These files preserve the production experiment; they are not a turnkey publishing
service or a new application deployment.

## Included

- `mobile/Scene.tsx`: 1080×1920, 24fps, 2727-frame compositions. Wide fleet and
  office shots retain the full source image; selected actor shots use a crop.
  English and Korean captions use the source timeline, with separate translation
  timing for English narration.
- `mobile/render-stage2.cjs`: eight still proofs, followed by an explicit technical
  layout gate before the Korean full render. That gate is **not human approval**.
- `portrait/Scene.tsx`: separate 1080×1350 layout for the LinkedIn review.
- `portrait/render-layout.cjs`: still proofs only.
- `portrait/render-full.cjs`: full Korean portrait render from the prepared bundle.

The snapshots retain the original Linux Chromium path, run markers, output names
and November 1, 2026 start deadline. They deliberately refuse duplicate starts.
Do not remove markers to restart an unknown render. A later production run needs
its own reviewed configuration and output directory.

## Private inputs are not in Git

Each composition expects these sibling files, supplied separately on the render
host:

- `captions.json`: `en`, `ko`, and `translation` arrays of
  `{ "start": 0.0, "end": 1.0, "text": "Example" }` cues, in seconds.
- `shots.json`: array of `{ "id": "example", "kind": "video", "file":
  "example.mp4", "start_frame": 0, "end_frame": 2727 }` entries.
- `public/frames/f00000.jpg` through `f02726.jpg`: the matching 24fps picture
  timeline. English narration requires the matching English source frames.

No footage, narration, music, original caption text, image assets, review receipt,
OAuth token, API key, state database, or private ledger is included. Generated
media remains on the existing render host. Do not commit the inputs or output
folders to make a missing-input error disappear.

## Runtime and verification boundary

The existing render host used Remotion, `@remotion/renderer`, and
`@remotion/bundler` **4.0.539**, React **19.1.0**, and its installed Chromium.
No dependencies are installed by this backup. Review the upstream Remotion license
for the actual user/team and use case; this is not a claim of unconditional MIT
licensing: <https://github.com/remotion-dev/remotion/blob/main/LICENSE.md>.

The 113.625-second English and Korean mobile review files were rendered and checked
for full decoding, 2727 frames, source AAC packet identity after muxing, and complete
native browser playback. The Korean 4:5 file passed decoding, dimensions, frame
count and AAC identity checks; its native playback check was blocked by office
authentication at backup time. The 4:5 English composition has not been rendered.
These checks do not prove subjective cinematic quality, speech lip sync throughout
the film, or successful upload to any social platform.

The snapshots render silent picture. Audio muxing, private office registration,
SRT export, and the film's separate 27-second excerpt are not included here.
Do not use this source backup as an instruction to call paid services, change
human approvals, publish media, or alter authentication.

Local syntax-only check (does not render or download media):

```sh
node --check mobile/render-stage2.cjs
node --check portrait/render-layout.cjs
node --check portrait/render-full.cjs
```

## Music and asset rights

The relevant 113.625-second film edition credits *Clash Defiant* and *Movement
Proposition* by Kevin MacLeod (incompetech.com), CC BY 4.0, edited excerpts and
mixing: <https://creativecommons.org/licenses/by/4.0/>. The tracks are not included.
Do not apply this credit or rights assessment to the separate 148-second reference
without checking that reference's actual soundtrack. Check rights and disclosure
requirements again before any later publication.

## Removal

This directory is isolated and is not imported by the operating app. Removing this
backup does not alter its database, approvals, authentication or existing media.
