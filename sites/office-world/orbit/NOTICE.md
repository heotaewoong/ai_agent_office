# HeoBrain Orbit

This interface replaces the default office-world presentation. The original world files remain at the parent directory for rollback. Existing Content Office authentication, approval gates, business records and native assistant bridge remain authoritative.

The scene and interface are HeoBrain-specific. Feature inventories reference DeskRPG (dandacompany/deskrpg) and Connect AI Lab (wonseokjung/aicb-colab); inventory entries are not a claim that every external capability has been implemented. Local training and model-merge demonstrations do not call training services or operate real models.

Bundled dependencies (no runtime CDN):

- Three.js 0.180.0 and OrbitControls/RoundedBoxGeometry: MIT, https://github.com/mrdoob/three, license in vendor/LICENSE-three.txt.
- Lucide React 1.45.0 icon paths rendered to icons.svg: ISC, https://github.com/lucide-icons/lucide, license in vendor/LICENSE-lucide.txt.

The concept image is the previously created HeoBrain design reference; it is not a screenshot proving live operations. data.json contains synthetic demo cards and profiles for the public preview. Actual Content Office data are separately retrieved from fixed same-origin read routes. No secret is required in this directory.

Rollback: restore the original WorldView iframe source `/world/index.html?api=/api/space&embed=1` through the normal reviewed deployment. Never restore or replace the business database to roll back this UI.
