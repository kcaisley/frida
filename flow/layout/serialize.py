"""Layout and technology serialization / deserialization helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import klayout.db as kdb
import vlsir.raw_pb2
import vlsir.tech_pb2 as vtech
import vlsir.utils_pb2 as vutils
from google.protobuf import text_format

from .tech import LayerInfoData


@dataclass(frozen=True)
class ExportArtifacts:
    pb: Path
    pbtxt: Path
    gds: Path | None = None


@dataclass(frozen=True)
class TechArtifacts:
    pb: Path
    pbtxt: Path


def write_technology_proto(
    *,
    tech_name: str,
    layer_infos: tuple[LayerInfoData, ...],
    out_dir: Path,
    stem: str | None = None,
) -> TechArtifacts:
    """Write vlsir.tech protobuf (`.pb` and `.pbtxt`) from layer-info data.

    Only populates ``Technology.layers`` with ``LayerInfo`` entries
    (name, index, sub_index, purpose).  Rule-deck serialization has been
    removed — rules are consumed directly from the Python ``RuleDeck``.
    """

    tech = vtech.Technology(name=tech_name)

    purpose_map = {
        "UNKNOWN": vtech.LayerPurposeType.UNKNOWN,
        "LABEL": vtech.LayerPurposeType.LABEL,
        "DRAWING": vtech.LayerPurposeType.DRAWING,
        "PIN": vtech.LayerPurposeType.PIN,
        "OBSTRUCTION": vtech.LayerPurposeType.OBSTRUCTION,
        "OUTLINE": vtech.LayerPurposeType.OUTLINE,
    }

    for info in layer_infos:
        tech.layers.append(
            vtech.LayerInfo(
                name=info.name,
                purpose=vtech.LayerPurpose(
                    description=info.purpose_description,
                    type=purpose_map.get(
                        info.purpose_type.upper(), vtech.LayerPurposeType.UNKNOWN
                    ),
                ),
                index=info.index,
                sub_index=info.sub_index,
            )
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_stem = stem or tech_name
    pb = out_dir / f"{out_stem}.tech.pb"
    pbtxt = out_dir / f"{out_stem}.tech.pbtxt"
    pb.write_bytes(tech.SerializeToString())
    pbtxt.write_text(text_format.MessageToString(tech), encoding="utf-8")
    return TechArtifacts(pb=pb, pbtxt=pbtxt)


def read_technology_proto(path: Path) -> vtech.Technology:
    """Read vlsir.tech protobuf from `.pb` or `.pbtxt`."""

    tech = vtech.Technology()
    if path.suffix == ".pb":
        tech.ParseFromString(path.read_bytes())
    else:
        text_format.Parse(path.read_text(encoding="utf-8"), tech)
    return tech


def layout_to_vlsir_raw(
    layout: kdb.Layout,
    domain: str = "frida.layout",
    instance_params: dict[object, object] | None = None,
) -> vlsir.raw_pb2.Library:
    """Convert KLayout database to vlsir.raw, with optional param-derived names."""

    params_map = instance_params or {}
    lib = vlsir.raw_pb2.Library(domain=domain, units=vlsir.raw_pb2.Units.MICRO)
    layer_indexes = list(layout.layer_indexes())

    for cell in layout.each_cell():
        raw_layout = vlsir.raw_pb2.Layout(name=cell.name)

        for layer_idx in layer_indexes:
            shapes = cell.shapes(layer_idx)
            if shapes.is_empty():
                continue

            info = layout.get_info(layer_idx)
            layer_shapes = vlsir.raw_pb2.LayerShapes(
                layer=vlsir.raw_pb2.Layer(
                    number=int(info.layer), purpose=int(info.datatype)
                )
            )

            for shape in shapes.each():
                if shape.is_box():
                    box = shape.box
                    layer_shapes.rectangles.append(
                        vlsir.raw_pb2.Rectangle(
                            lower_left=vlsir.raw_pb2.Point(
                                x=int(box.left),
                                y=int(box.bottom),
                            ),
                            width=int(box.right - box.left),
                            height=int(box.top - box.bottom),
                        )
                    )
                elif shape.is_polygon():
                    poly = shape.polygon
                    layer_shapes.polygons.append(
                        vlsir.raw_pb2.Polygon(
                            vertices=[
                                vlsir.raw_pb2.Point(x=int(p.x), y=int(p.y))
                                for p in poly.each_point_hull()
                            ]
                        )
                    )
                elif shape.is_path():
                    path = shape.path
                    layer_shapes.paths.append(
                        vlsir.raw_pb2.Path(
                            points=[
                                vlsir.raw_pb2.Point(x=int(p.x), y=int(p.y))
                                for p in path.each_point()
                            ],
                            width=int(path.width),
                        )
                    )
                elif shape.is_text():
                    text = shape.text
                    raw_layout.annotations.append(
                        vlsir.raw_pb2.TextElement(
                            string=text.string,
                            loc=vlsir.raw_pb2.Point(x=int(text.x), y=int(text.y)),
                        )
                    )

            if layer_shapes.rectangles or layer_shapes.polygons or layer_shapes.paths:
                raw_layout.shapes.append(layer_shapes)

        for inst_idx, inst in enumerate(cell.each_inst()):
            target_name = layout.cell(inst.cell_index).name
            trans = inst.trans
            points = [(0, 0, int(trans.disp.x), int(trans.disp.y))]
            if inst.is_regular_array() and (inst.na > 1 or inst.nb > 1):
                points = [
                    (
                        ia,
                        ib,
                        int(trans.disp.x + ia * inst.a.x + ib * inst.b.x),
                        int(trans.disp.y + ia * inst.a.y + ib * inst.b.y),
                    )
                    for ia in range(inst.na)
                    for ib in range(inst.nb)
                ]

            for ia, ib, x, y in points:
                params = params_map.get((cell.name, inst_idx, ia, ib))
                if params is None:
                    params = params_map.get((cell.name, inst_idx))
                if params is None:
                    params = params_map.get(target_name)

                slug = ""
                if params is not None:
                    fields: list[tuple[str, str]] = []
                    if hasattr(params, "__dict__"):
                        for k, v in vars(params).items():
                            if k.startswith("_"):
                                continue
                            vv = getattr(v, "name", v)
                            fields.append((k, str(vv).lower()))
                    fields.sort(key=lambda item: item[0])
                    slug = "__".join(f"{k}-{v}" for k, v in fields)
                    if len(slug) > 120:
                        slug = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:16]

                if slug:
                    inst_name = f"{target_name.lower()}__{slug}__i{inst_idx}_{ia}_{ib}"
                else:
                    inst_name = f"{target_name.lower()}__i{inst_idx}_{ia}_{ib}"

                raw_layout.instances.append(
                    vlsir.raw_pb2.Instance(
                        name=inst_name,
                        cell=vutils.Reference(local=target_name),
                        origin_location=vlsir.raw_pb2.Point(x=x, y=y),
                        reflect_vert=bool(trans.is_mirror()),
                        rotation_clockwise_degrees=int(trans.angle * 90),
                    )
                )

        lib.cells.append(vlsir.raw_pb2.Cell(name=cell.name, layout=raw_layout))

    return lib


def vlsir_raw_to_disk(
    library: vlsir.raw_pb2.Library,
    pb_path: Path,
    pbtxt_path: Path | None = None,
) -> None:
    pb_path.parent.mkdir(parents=True, exist_ok=True)
    pb_path.write_bytes(library.SerializeToString())
    if pbtxt_path is not None:
        pbtxt_path.parent.mkdir(parents=True, exist_ok=True)
        pbtxt_path.write_text(text_format.MessageToString(library), encoding="utf-8")


def export_layout(
    layout: kdb.Layout,
    out_dir: Path,
    stem: str,
    domain: str = "frida.layout",
    write_debug_gds: bool = False,
) -> ExportArtifacts:
    out_dir.mkdir(parents=True, exist_ok=True)
    pb = out_dir / f"{stem}.raw.pb"
    pbtxt = out_dir / f"{stem}.raw.pbtxt"
    lib = layout_to_vlsir_raw(layout, domain=domain)
    vlsir_raw_to_disk(lib, pb, pbtxt)
    gds: Path | None = None
    if write_debug_gds:
        gds = out_dir / f"{stem}.debug.gds"
        layout.write(str(gds))
    return ExportArtifacts(pb=pb, pbtxt=pbtxt, gds=gds)


def test_serialize(outdir: Path) -> None:
    """Inline serializer test: raw export + text + instance expansion."""

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    child = layout.create_cell("CHILD")
    l1 = layout.layer(31, 0)

    child.shapes(l1).insert(kdb.Box(0, 0, 10, 10))
    top.shapes(l1).insert(kdb.Box(0, 0, 100, 50))
    top.shapes(l1).insert(kdb.Text("T", kdb.Trans(kdb.Point(4, 4))))
    top.insert(
        kdb.CellInstArray(
            child.cell_index(),
            kdb.Trans(kdb.Point(200, 300)),
            kdb.Vector(20, 0),
            kdb.Vector(0, 30),
            2,
            2,
        )
    )

    artifacts = export_layout(
        layout=layout,
        out_dir=outdir,
        stem="serialize_inline",
        domain="frida.layout.tests",
        write_debug_gds=True,
    )
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
    assert artifacts.gds is not None and artifacts.gds.exists()

    lib = layout_to_vlsir_raw(layout, domain="frida.layout.tests")
    assert lib.domain == "frida.layout.tests"
    top_cell = next(cell for cell in lib.cells if cell.name == "TOP")
    assert len(top_cell.layout.instances) == 4
