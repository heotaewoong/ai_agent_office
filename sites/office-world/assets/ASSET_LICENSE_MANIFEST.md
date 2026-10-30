# HeoBrain 3D assets — provenance

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
