# HeoBrain 3D assets — provenance

## guide-avatar-v1.json · 2026-10-31

- Creator / rights basis: HeoBrain original procedural guide robot; project-authored geometry for HeoBrain use. No external character, person likeness, model, font, logo or texture is included. This entry does not grant a third-party license.
- Authoring: Blender 4.5.15; 34 editable beveled suit/helmet parts, four original colors, existing five-pivot rig dimensions. The exact editable recipe is `output/2026-10-31-office-guide-avatar-authoring.py`; no model download or purchase.
- Source `.blend`: `output/2026-10-31-heobrain-guide-avatar-v1.blend`, SHA-256 `f12bcc2ec577bf97177c738ff98f1e856110e6eff45a0ebe8ab8abbe5b6bd63d`.
- Export `.glb`: same stem, SHA-256 `a81a53376c0f50ae30bc34afb9885a42988eb6070dac361dc75076ff05096b1e`.
- Runtime `guide-avatar-v1.json`: SHA-256 `4615dc17828e7786ece32d80528f27a8d12233b262718b387afdb9ddca5a9cbb`. Four materials, 14 meshes, 3,672 triangles, under 620 KB, no external assets.
- Conversion: evaluated Blender geometry grouped by original rig pivot/material, coordinates and normals converted to Babylon left-handed Y-up, six-decimal vertex serialization. Meshes explicitly enabled. Existing walk/sit/movement/root visibility remain authoritative; the default player remains available on fetch/parse failure. High-quality walking view loads the asset once; low quality does not request it.
- Download date / external attribution / releases: not applicable to independently authored geometry. Build date 2026-10-31 KST. Actual Cycles 24-sample CPU review and WebGL walking inspection recorded in root `output/`. Native import, normals, rig movement, fallback and disposal are tested in `tests/guide-avatar.test.mjs`.

## atrium-detail-v3.json · 2026-10-31

- Creator: HeoBrain project; original procedural architecture authored in this project. No downloaded model, photograph, logo, font, texture, or third-party building design is included.
- Source: existing original `world.architecturePlan('atrium')`, independently modeled as beveled editable parts with Blender 4.5.15, exported GLB, then serialized with Babylon.js 7.54.0 to its native JSON format. Original dimensions, passage and collision model remain in `app.js`.
- Rights basis: project-authored asset for HeoBrain use; this entry does not grant a new third-party license to the asset or redistribute Blender. Babylon.js engine software retains its existing Apache-2.0 notice in `vendor/LICENSE-babylon.txt`.
- Build date: 2026-10-31 KST. External download date / releases / attribution: not applicable to this independently authored geometry.
- Editable source: `G:/내 드라이브/0.project_money/output/2026-10-31-heobrain-atrium-v3.blend`, SHA-256 `27fa63df05c0e38d881d54a463177c634acfe112cfade49769d6624b3693990e`.
- Export: `2026-10-31-heobrain-atrium-v3.glb`, SHA-256 `8c095d52e92064dc6eb48b8e6fc87a5f4665b9fb9bcecaeb12d298442e0be5dd`.
- Runtime asset: `atrium-detail-v3.json`, SHA-256 `3e43e5522132295e3b478191659cd328465a97c5f8d3662beff883598b2bf267`.
- Conversion: six-decimal vertex serialization; removed the automatically serialized, unused XR DepthSensing plugin registration. Four meshes / four materials / 6,204 triangles / no external textures, cameras, lights or animation. Native asset is under 900 KB; low mode makes no request.
- Authoring and conversion recipes, original GLB, Cycles render and validation logs remain in the workspace root `output/`. Runtime checks cover load failure fallback, stage replacement races, disposal and source provenance. Human approval and content-production APIs are unchanged.

## arrival-detail-v2.json · preserved

Existing independently authored Blender arrival asset is retained without modification. Its source GLB hash `4eb3370839e30e33c637f01ef490f4d45136127ff6adff1d45b847fb9212ece6` is embedded in its metadata and tested by `tests/arrival-detail.test.mjs`. Earlier provenance and render records remain in `output/2026-10-30-office-blender-arrival-live-result.md`; this change does not reclassify private materials or overwrite original source assets.
