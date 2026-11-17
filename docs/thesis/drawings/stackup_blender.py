"""The thesis's 3-D stack-up scenes, built and rendered inside Blender (run headless by
render_stackup.py, which writes the scene as JSON): layout pieces extruded by the BlenderGDS
add-on's importer, cut where their crop box ends, plus the parts no layout draws (silicon bulk,
bumps, bond wires, redistribution traces, through-silicon vias); an orthographic camera fitted to
the scene; a Cycles still on a transparent background and the same scene as GLB for the web page.

    blender -b --factory-startup --python stackup_blender.py -- SCENE.json

A scene's parts:

    {"kind": "layout", "gds", "cell", "crop": [x0, y0, x1, y1], "origin": [x, y], "z": z,
     "flip": bool, "unit": metres per scene unit (1e-6), "at": [x, y],
     "layers": [{"name", "gds": [layer, datatype], "z", "height", "material", "crop"}]}
    {"kind": "glb", "path", "scale", "styles": {"mask", "laminate", "copper", "pads", "silkscreen"}}
    {"kind": "box", "name", "min": [x, y, z], "max": [x, y, z], "material", "holes": [{"centre", "radius"}]}
    {"kind": "cylinder", "name", "centre": [x, y], "z": [z0, z1], "radius", "material", "cut"}
    {"kind": "bump", "name", "centre": [x, y, z], "radius", "height", "material", "cut"}
    {"kind": "frustum", "name", "centre": [x, y], "z": [z0, z1], "radius": [r0, r1], "shell", "material", "cut"}
    {"kind": "wedge", "name", "centre": [x, y, z], "angle", "size": [length, width, height], "material"}
    {"kind": "wire", "name", "points": [[x, y, z], ...], "radius", "material"}
    {"kind": "trace", "name", "points": [[x, y], ...], "z", "width", "height", "material"}

Lengths are the scene's unit: µm, or mm for the board (a layout part's ``unit`` then 1e-3, its
crop and origin in mm too, ``at`` where its origin lands). A layout piece's crop is in its own
coordinates; ``origin`` (also its own) lands on the scene's
x = y = 0, ``z`` is where its front-end surface sits, and ``flip`` turns it face down (a flip-chip
die, rotated about x). A material is {"color": "#rrggbb", "metallic", "roughness", "alpha"}.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time

with open(sys.argv[sys.argv.index("--") + 1]) as file:
    spec = json.load(file)
for path in spec["sys_path"]:
    sys.path.insert(0, path)

import bmesh
import bpy
import import_gdsii as gds
import klayout.db as kdb
from mathutils import Matrix, Vector

MATERIALS: dict[str, bpy.types.Material] = {}


def material(name: str, style: dict) -> bpy.types.Material:
    """One Principled material per style (sRGB colour; alpha below 1 is drawn translucent)."""

    key = json.dumps(style, sort_keys=True)
    if key in MATERIALS:
        return MATERIALS[key]
    rgb = tuple((int(style["color"][i : i + 2], 16) / 255) ** 2.2 for i in (1, 3, 5))
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.0 if spec.get("matte") else style.get("metallic", 0.0)
    bsdf.inputs["Roughness"].default_value = 0.92 if spec.get("matte") else style.get("roughness", 0.5)
    if spec.get("matte"):
        bsdf.inputs["Specular IOR Level"].default_value = 0.15
    alpha = style.get("alpha", 1.0)
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        mat.surface_render_method = "BLENDED"
    mat.diffuse_color = (*rgb, alpha)
    MATERIALS[key] = mat
    return mat


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def layout_part(part: dict) -> list[bpy.types.Object]:
    layout = kdb.Layout()
    layout.read(part["gds"])
    cell = layout.cell(part["cell"]) if part.get("cell") else layout.top_cells()[0]
    objects = []
    for layer in part["layers"]:
        style = layer["material"]
        colour = {
            "Base Color": (*((int(style["color"][i : i + 2], 16) / 255) ** 2.2 for i in (1, 3, 5)), 1.0),
            "Metallic": 0.0 if spec.get("matte") else style.get("metallic", 0.0),
            "Roughness": 0.92 if spec.get("matte") else style.get("roughness", 0.5),
            **({"Specular IOR Level": 0.15} if spec.get("matte") else {}),
            "Alpha": style.get("alpha", 1.0),
        }
        obj = gds.create_extruded_layer(
            lambda level, message: None,
            layout,
            [cell],
            layer["z"],
            layer["height"],
            tuple(layer["gds"]),
            f"{part.get('name', 'piece')}.{layer['name']}",
            colour,
            mat_name=f"{part.get('name', 'piece')}.{layer['name']}",
            crop_box=tuple(layer.get("crop", part["crop"])),
            offset=tuple(part["origin"]),
            unit=part.get("unit", 1e-6),
        )
        if obj is None:
            continue
        if style.get("alpha", 1.0) < 1:
            obj.active_material.surface_render_method = "BLENDED"
        if part.get("flip"):
            obj.matrix_world = Matrix.Rotation(math.pi, 4, "X") @ obj.matrix_world
        obj.location.z += part.get("z", 0.0)
        obj.location.x += part.get("at", (0.0, 0.0))[0]
        obj.location.y += part.get("at", (0.0, 0.0))[1]
        objects.append(obj)
    return objects


def restyle(mat: bpy.types.Material, styles: dict) -> None:
    """A material exported by KiCad, given a look: the board's own parts by their colours (solder
    mask, laminate, pads, silkscreen), the models' materials (all exported fully metallic and
    fully rough) as plastic or metal by their lightness."""

    if not mat.use_nodes or "Principled BSDF" not in mat.node_tree.nodes:
        return
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    r, g, b, _ = bsdf.inputs["Base Color"].default_value
    metallic = bsdf.inputs["Metallic"].default_value

    def apply(style: dict) -> None:
        if "color" in style:
            bsdf.inputs["Base Color"].default_value = (
                *((int(style["color"][i : i + 2], 16) / 255) ** 2.2 for i in (1, 3, 5)),
                1.0,
            )
        bsdf.inputs["Metallic"].default_value = style.get("metallic", 0.0)
        bsdf.inputs["Roughness"].default_value = style.get("roughness", 0.5)
        if "coat" in style:
            bsdf.inputs["Coat Weight"].default_value = style["coat"]
        if "alpha" in style:
            bsdf.inputs["Alpha"].default_value = style["alpha"]

    lightness = 0.2126 * r + 0.7152 * g + 0.0722 * b
    roughness = bsdf.inputs["Roughness"].default_value
    if metallic > 0.5 and roughness < 0.6:  # the board's copper (the models' are all fully rough)
        apply(styles["copper"] if r > 0.5 and b < 0.1 else styles["pads"])  # under the mask, or bare
    elif metallic < 0.5 and g > r and g > b and lightness < 0.3:
        apply(styles["mask"])
    elif metallic < 0.5 and lightness < 0.6 and r > b:
        apply(styles["laminate"])
    elif metallic < 0.5:
        apply(styles["silkscreen"])
    elif r > 0.5 and b < 0.1:
        apply(styles["pads"])
    elif lightness < 0.12:
        apply({"metallic": 0.0, "roughness": 0.45})
    elif max(r, g, b) - min(r, g, b) > 0.15:
        apply({"metallic": 1.0, "roughness": 0.25})
    elif lightness > 0.7:
        apply({"metallic": 0.0, "roughness": 0.4})
    else:
        apply({"metallic": 0.9, "roughness": 0.3})


def glb_part(part: dict) -> list[bpy.types.Object]:
    """A model exported as GLB (the board by kicad-cli), scaled into the scene's unit, its
    materials restyled."""

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=part["path"])
    objects = [o for o in bpy.data.objects if o not in before]
    for obj in objects:
        if obj.parent is None:
            obj.scale = [part.get("scale", 1.0)] * 3
    for mat in {slot.material for o in objects if o.type == "MESH" for slot in o.material_slots if slot.material}:
        restyle(mat, part["styles"])
    return objects


def box_part(part: dict) -> bpy.types.Object:
    lo, hi = Vector(part["min"]), Vector(part["max"])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2)
    obj = bpy.context.object
    obj.name = part["name"]
    obj.scale = hi - lo
    bpy.ops.object.transform_apply(scale=True)
    for n, hole in enumerate(part.get("holes", [])):  # openings through it (a passivation's), tapered
        depth = hi.z - lo.z
        top = hole.get("top_radius", hole["radius"])
        flare = (top - hole["radius"]) / depth  # the radius's growth per unit height, carried 1 beyond each face
        bpy.ops.mesh.primitive_cone_add(
            vertices=64,
            radius1=hole["radius"] - flare,
            radius2=top + flare,
            depth=depth + 2,
            location=(*hole["centre"], (lo.z + hi.z) / 2),
        )
        tool = bpy.context.object
        tool.name = f"{part['name']}.hole{n}"
        difference = obj.modifiers.new(f"hole{n}", "BOOLEAN")
        difference.operation, difference.object, difference.solver = "DIFFERENCE", tool, "EXACT"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=difference.name)
        bpy.data.objects.remove(tool)
    assign(obj, material(part["name"], part["material"]))
    return obj


def cylinder_part(part: dict) -> bpy.types.Object:
    z0, z1 = part["z"]
    x, y = part["centre"]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=part["radius"], depth=z1 - z0, location=(x, y, (z0 + z1) / 2)
    )
    obj = bpy.context.object
    obj.name = part["name"]
    bpy.ops.object.shade_smooth()
    cut(obj, part)
    assign(obj, material(part["name"], part["material"]))
    return obj


def cut(obj: bpy.types.Object, part: dict) -> None:
    """A solid cut by a plane (``part["cut"]``: {"axis", "at"}), the part beyond it removed and
    the opening closed, so a bump or a via shows its section on the scene's cut face."""

    if "cut" not in part:
        return
    axis = "xyz".index(part["cut"]["axis"])
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    point = [0.0, 0.0, 0.0]
    point[axis] = part["cut"]["at"]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    result = bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=point, plane_no=normal, clear_outer=True
    )
    edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    for face in bmesh.ops.holes_fill(bm, edges=edges, sides=0)["faces"]:
        face.smooth = False  # the section flat, the rest as smooth as before
    bm.transform(obj.matrix_world.inverted())
    bm.to_mesh(obj.data)
    bm.free()


def frustum_part(part: dict) -> bpy.types.Object:
    """A cone's frustum (radii at its bottom and top), solid or a shell of the given thickness
    (``shell``): the solder in a tapered opening, the liner along its walls."""

    z0, z1 = part["z"]
    r0, r1 = part["radius"]
    x, y = part["centre"]
    bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=r0, radius2=r1, depth=z1 - z0, location=(x, y, (z0 + z1) / 2))
    obj = bpy.context.object
    obj.name = part["name"]
    if part.get("shell"):
        t = part["shell"]
        flare = (r1 - r0) / (z1 - z0)
        bpy.ops.mesh.primitive_cone_add(
            vertices=64,
            radius1=r0 - t - flare,
            radius2=r1 - t + flare,
            depth=z1 - z0 + 2,
            location=(x, y, (z0 + z1) / 2 + t),
        )
        tool = bpy.context.object
        difference = obj.modifiers.new("hollow", "BOOLEAN")
        difference.operation, difference.object, difference.solver = "DIFFERENCE", tool, "EXACT"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=difference.name)
        bpy.data.objects.remove(tool)
    bpy.ops.object.shade_smooth()
    cut(obj, part)
    assign(obj, material(part["name"], part["material"]))
    return obj


def bump_part(part: dict) -> bpy.types.Object:
    """A solder bump: a sphere squashed to its height, its centre half way up."""

    x, y, z = part["centre"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=part["radius"], location=(x, y, z))
    obj = bpy.context.object
    obj.name = part["name"]
    obj.scale.z = part["height"] / (2 * part["radius"])
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    cut(obj, part)
    assign(obj, material(part["name"], part["material"]))
    return obj


def wedge_part(part: dict) -> bpy.types.Object:
    """A wedge bond's flattened foot: an ellipsoid of the given length, width and height, turned
    to the wire's direction (``angle``, degrees from x)."""

    length, width, height = part["size"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.5, location=part["centre"])
    obj = bpy.context.object
    obj.name = part["name"]
    obj.scale = (length, width, height)
    obj.rotation_euler.z = math.radians(part["angle"])
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    bpy.ops.object.shade_smooth()
    assign(obj, material(part["name"], part["material"]))
    return obj


def wire_part(part: dict) -> bpy.types.Object:
    """A bond wire: a smooth curve through its points, swept by a circle of its radius."""

    curve = bpy.data.curves.new(part["name"], "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = part["radius"]
    curve.bevel_resolution = 6
    curve.resolution_u = 24
    spline = curve.splines.new("NURBS")
    spline.points.add(len(part["points"]) - 1)
    for point, (x, y, z) in zip(spline.points, part["points"]):
        point.co = (x, y, z, 1.0)
    spline.use_endpoint_u = True
    spline.order_u = min(4, len(part["points"]))
    obj = bpy.data.objects.new(part["name"], curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material(part["name"], part["material"]))
    return obj


def trace_part(part: dict) -> bpy.types.Object:
    """A flat trace (a redistribution line): its centre line widened and extruded."""

    mesh = bpy.data.meshes.new(part["name"])
    bm = bmesh.new()
    half = part["width"] / 2
    points = [Vector((x, y, 0)) for x, y in part["points"]]
    for a, b in itertools.pairwise(points):
        d = (b - a).normalized()
        n = Vector((-d.y, d.x, 0)) * half
        a0, b0 = a - d * half, b + d * half
        quad = [a0 - n, b0 - n, b0 + n, a0 + n]
        bottom = [bm.verts.new((v.x, v.y, part["z"])) for v in quad]
        top = [bm.verts.new((v.x, v.y, part["z"] + part["height"])) for v in quad]
        bm.faces.new(bottom[::-1])
        bm.faces.new(top)
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(part["name"], mesh)
    bpy.context.collection.objects.link(obj)
    assign(obj, material(part["name"], part["material"]))
    return obj


BUILD = {
    "frustum": frustum_part,
    "layout": layout_part,
    "glb": glb_part,
    "wedge": wedge_part,
    "box": box_part,
    "cylinder": cylinder_part,
    "bump": bump_part,
    "wire": wire_part,
    "trace": trace_part,
}


def fit_camera(camera: dict) -> None:
    """A camera at the given azimuth and elevation framing every object: a perspective one with a
    moderate field of view (``fov``, degrees: the eye's sense of depth, as KiCad's viewer), or an
    orthographic one (``"ortho": true``). With ``target`` and ``span`` it frames that point, the
    view ``span`` wide there, instead of the whole scene."""

    scene = bpy.context.scene
    az, el = math.radians(camera["azimuth"]), math.radians(camera["elevation"])
    direction = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(c) for o in scene.objects if o.type in {"MESH", "CURVE"} for c in o.bound_box]
    centre = sum(corners, Vector()) / len(corners)
    reach = max((c - centre).length for c in corners)
    if "target" in camera:
        centre = Vector(camera["target"])
    width, height = spec["size"]
    data = bpy.data.cameras.new("camera")
    obj = bpy.data.objects.new("camera", data)
    scene.collection.objects.link(obj)
    margin = camera.get("margin", 1.06)

    def place(distance: float) -> None:
        obj.location = centre + direction * distance
        obj.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()

    if camera.get("ortho"):
        data.type = "ORTHO"
        data.clip_start, data.clip_end = 0.01, reach * 20
        place(reach * 4)
        view = obj.matrix_world.inverted()
        xs, ys = [(view @ c).x for c in corners], [(view @ c).y for c in corners]
        if "span" in camera:
            data.ortho_scale = camera["span"]
        else:
            data.ortho_scale = max(max(xs) - min(xs), (max(ys) - min(ys)) * width / height) * margin
            data.shift_x = (max(xs) + min(xs)) / 2 / data.ortho_scale
            data.shift_y = (max(ys) + min(ys)) / 2 / data.ortho_scale
        scene.camera = obj
        return
    data.type = "PERSP"
    data.sensor_fit = "HORIZONTAL"
    data.angle = math.radians(camera.get("fov", 30.0))
    half = math.tan(data.angle / 2)  # the view's half width at unit distance
    if "span" in camera:
        place(camera["span"] / 2 / half)
    else:
        # the distance and the lens shift that frame every corner (refined: the projection of a
        # near corner grows as the camera comes closer)
        distance = reach / math.sin(data.angle / 2)
        for _ in range(6):
            place(distance)
            view = obj.matrix_world.inverted()
            us, vs = [], []
            for corner in corners:
                local = view @ corner
                us.append(local.x / -local.z)
                vs.append(local.y / -local.z)
            span = max(max(us) - min(us), (max(vs) - min(vs)) * width / height) * margin
            distance *= span / (2 * half)
        data.shift_x = (max(us) + min(us)) / 2 / (2 * half)
        data.shift_y = (max(vs) + min(vs)) / 2 / (2 * half)
    data.clip_start, data.clip_end = (obj.location - centre).length / 1000, (obj.location - centre).length + reach * 4
    scene.camera = obj


def light() -> None:
    """A sun and a white sky; for a matte scene a flat light, mostly the sky's, the sun weak and
    behind the camera, so each face keeps its colour as in a drawing."""

    scene = bpy.context.scene
    flat = spec.get("matte")
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 0.45 if flat else 3.2
    sun_data.angle = math.radians(30 if flat else 12)
    sun = bpy.data.objects.new("sun", sun_data)
    if flat and scene.camera:
        sun.rotation_euler = scene.camera.rotation_euler.copy()
        sun.rotation_euler.x -= math.radians(15)
    else:
        sun.rotation_euler = (math.radians(38), math.radians(12), math.radians(-35))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (1, 1, 1, 1)
    background.inputs[1].default_value = 0.8 if flat else 0.65
    scene.world = world


def outline() -> None:
    """Every structure's edges drawn as thin dark lines (Freestyle), as the web viewer edges its
    boxes, so neighbouring structures of a colour stay apart."""

    scene = bpy.context.scene
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = spec.get("outline", 1.0)
    layer = scene.view_layers[0]
    layer.use_freestyle = True
    settings = layer.freestyle_settings
    settings.crease_angle = math.radians(140)
    lineset = settings.linesets[0] if settings.linesets else settings.linesets.new("edges")
    lineset.select_by_visibility = True
    lineset.select_by_edge_types = True
    lineset.select_silhouette = lineset.select_border = lineset.select_crease = True
    style = lineset.linestyle or bpy.data.linestyles.new("edges")
    lineset.linestyle = style
    style.color = (0.18, 0.2, 0.25)
    style.alpha = 0.85
    style.thickness = spec.get("outline", 1.0)


def render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = spec.get("samples", 64)
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = spec["size"]
    scene.render.threads_mode = "FIXED"
    scene.render.threads = spec.get("threads", 16)
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = spec["out"]
    bpy.ops.render.render(write_still=True)


def main() -> None:
    start = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for part in spec["parts"]:
        BUILD[part["kind"]](part)
    print(f"scene built in {time.time() - start:.0f} s: {len(bpy.data.objects)} objects")
    fit_camera(spec["camera"])
    light()
    if spec.get("outline"):
        outline()
    start = time.time()
    render()
    print(f"rendered {spec['out']} in {time.time() - start:.0f} s")
    if spec.get("glb"):
        bpy.ops.export_scene.gltf(
            filepath=spec["glb"], export_format="GLB", export_apply=True, export_cameras=False, export_lights=False
        )
        print(f"exported {spec['glb']}")


main()
