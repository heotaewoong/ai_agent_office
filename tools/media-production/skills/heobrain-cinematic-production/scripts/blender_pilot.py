# SPDX-License-Identifier: GPL-3.0-or-later
"""Original procedural camera/lighting proof. Run only through Blender on EC2."""
import bpy
import json
import hashlib
import math
import sys
from pathlib import Path
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
out = Path(args[0]).resolve()
assert str(out).startswith('/home/ubuntu/.local/state/heobrain-content-office/artifacts/')
assert not (out / 'pilot-scene.blend').exists(), 'Preserve the existing scene'
out.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 3
scene.render.threads_mode = 'FIXED'
scene.render.threads = 1
scene.render.resolution_x = 480
scene.render.resolution_y = 270
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 48
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(out / 'frames' / 'f')
scene.world.use_nodes = True
background = scene.world.node_tree.nodes.get('Background')
background.inputs['Color'].default_value = (.004, .008, .025, 1)
background.inputs['Strength'].default_value = .15


def material(name, color, metal=0, glow=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Roughness'].default_value = .28
    if glow:
        bsdf.inputs['Emission Color'].default_value = (*color, 1)
        bsdf.inputs['Emission Strength'].default_value = glow
    return m


steel = material('graphite titanium', (.055, .075, .11), .75)
floor = material('midnight floor', (.025, .045, .065), .45)
cyan = material('cyan light', (.05, .65, 1), .2, 4)
amber = material('amber light', (1, .38, .065), .2, 3)
glass = material('smoked canopy', (.025, .12, .19), .65)


def box(name, location, scale, mat, bevel=.08):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new('edge highlights', 'BEVEL')
        mod.width, mod.segments = bevel, 2
        o.modifiers.new('surface normals', 'WEIGHTED_NORMAL')
    return o


box('platform', (0, 0, -.22), (18, 16, .4), floor)
for x in (-6, -3, 0, 3, 6):
    box('guidance strip', (x, 0, .01), (.035, 13, .02), cyan, 0)
for x, y in [(-4, -2), (4, -2), (-4, 3), (4, 3)]:
    box('team station', (x, y, .7), (2.3, 1.2, 1.4), steel)
    box('holographic console', (x, y, 1.55), (2, .08, .85), cyan)
    for dx in (-.5, .5):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=.17,
                                            location=(x + dx, y - 1, 1.55))
        bpy.context.object.data.materials.append(steel)
        box('crew body', (x + dx, y - 1, 1.05), (.32, .25, .65), steel)

ship = box('Hermes prototype shuttle', (0, 1, 1.9), (2.6, 4.2, .55), steel, .18)
for x in (-1.6, 1.6):
    wing = box('swept wing', (x, 1.6, 1.8), (1.7, 2.6, .13), steel)
    wing.parent = ship
    wing.location = (x, .6, -.1)
cockpit = box('canopy', (0, .4, 2.35), (1.1, 1.8, .45), glass)
cockpit.parent = ship
cockpit.location = (0, -.6, .45)
mesh = bpy.data.meshes.new('tapered nose')
mesh.from_pydata([(-1.3, -2.1, -.1), (1.3, -2.1, -.1), (0, -3.4, .05),
                  (0, -2.1, .45)], [], [(0, 2, 3), (2, 1, 3), (0, 3, 1), (0, 1, 2)])
mesh.materials.append(steel)
nose = bpy.data.objects.new('shuttle nose', mesh)
scene.collection.objects.link(nose)
nose.parent = ship
for x in (-.85, .85):
    engine = box('engine', (x, 3.2, 1.9), (.5, .5, .35), amber)
    engine.parent = ship
    engine.location = (x, 2.2, 0)
ship.keyframe_insert(data_path='location', frame=1)
ship.location.z += .8
ship.keyframe_insert(data_path='location', frame=48)

for name, loc, color, power, size in [
    ('cool key', (1, -4, 8), (.35, .65, 1), 1800, 7),
    ('warm rim', (-5, 4, 6), (1, .42, .12), 2200, 5),
    ('soft fill', (6, 1, 5), (.15, .5, 1), 1000, 5),
]:
    data = bpy.data.lights.new(name, 'AREA')
    data.energy, data.color, data.shape, data.size = power, color, 'DISK', size
    light = bpy.data.objects.new(name, data)
    scene.collection.objects.link(light)
    light.location = loc
    light.rotation_euler = (Vector((0, 0, 1)) - light.location).to_track_quat('-Z', 'Y').to_euler()

bpy.ops.object.empty_add(location=(0, 1, 2))
focus = bpy.context.object
bpy.ops.object.camera_add(location=(8, -10, 6))
camera = bpy.context.object
scene.camera = camera
camera.data.lens = 36
track = camera.constraints.new('TRACK_TO')
track.target, track.track_axis, track.up_axis = focus, 'TRACK_NEGATIVE_Z', 'UP_Y'
camera.keyframe_insert(data_path='location', frame=1)
camera.location = (4, -7, 4.5)
camera.keyframe_insert(data_path='location', frame=48)
for f in range(1, 49):
    scene.frame_set(f)
    assert camera.location.y <= -7 and camera.location.z >= 4.49
    assert ship.location.z >= 1.89
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'pilot-scene.blend'))
(out / 'scene-receipt.json').write_text(json.dumps({
    'renderer': bpy.app.version_string, 'engine': 'CYCLES CPU', 'samples': 24,
    'frames': 48, 'width': 480, 'height': 270, 'fps': 24,
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'camera_keyframes': [[8, -10, 6], [4, -7, 4.5]],
    'path_clearance_check': True, 'actual_office_replica': False,
    'character_rigging_or_physics_simulation_verified': False,
    'external_assets': [],
}, indent=2))
if len(args) > 1 and args[1] == 'still':
    scene.render.filepath = str(out / 'benchmark.png')
    bpy.ops.render.render(write_still=True)
else:
    (out / 'frames').mkdir(exist_ok=False)
    bpy.ops.render.render(animation=True)
