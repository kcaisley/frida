"""hdl21align: placement and ALIGN's every constraint stated on a generator's own instances and
nets, checked complete, named as the netlist names them (``module_plan``); ALIGN's own schema
accepts what it writes."""

import json
import re
import subprocess

import hdl21 as h
import pytest
from hdl21.primitives import MosType, MosVth, Nmos

from flow.layout.hdl21align import constraints as c
from flow.layout.hdl21align import halves, issues, module_plan, place, pnr_input, pnr_inputs, row, rows
from flow.layout.run import ALIGN_HOME, align_env


def _pair(*, cascode: bool) -> h.Module:
    """A differential pair, a tail and, where asked, cascodes, placed as it is made."""
    m = h.Module(name=f"pair_{cascode}")
    m.d, m.g, m.s = h.Signal(), h.Signal(), h.Signal()
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    m.inp = device(d=m.d, g=m.g, s=m.s, b=m.s)
    m.inn = device(d=m.d, g=m.g, s=m.s, b=m.s)
    m.tail = device(d=m.s, g=m.g, s=m.s, b=m.s)
    cas_p = m.add(device(d=m.d, g=m.g, s=m.d, b=m.s), name="cas_p") if cascode else None
    cas_n = m.add(device(d=m.d, g=m.g, s=m.d, b=m.s), name="cas_n") if cascode else None
    place(m, rows(row(cas_p, cas_n), row(m.inp, m.tail, m.inn)))
    return m


@pytest.mark.parametrize("cascode", (False, True))
def test_a_device_a_generator_leaves_out_is_in_no_row(cascode: bool) -> None:
    m = _pair(cascode=cascode)
    pnr = pnr_input(m)
    assert pnr is not None
    plan = module_plan(pnr)
    expected = ([["Mcas_p", "Mcas_n"]] if cascode else []) + [["Minp", "Mtail", "Minn"]]
    assert plan["rows"] == expected and plan["symmetric"] is True


def test_an_unplaced_twice_placed_or_foreign_instance_is_an_issue() -> None:
    m = h.Module(name="loose")
    m.a, m.b = h.Signal(), h.Signal()
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    m.x = device(d=m.a, g=m.a, s=m.b, b=m.b)
    m.y = device(d=m.a, g=m.a, s=m.b, b=m.b)
    other = _pair(cascode=False)
    pnr = place(m, rows(row(m.x, m.x), row(other.tail)))
    found = issues(pnr)
    assert "x is placed 2 times" in found
    assert "y is in no row and not left to ALIGN" in found
    assert "a placed instance is not the module's" in found
    with pytest.raises(ValueError, match="incomplete"):
        module_plan(pnr)


def test_an_instance_left_to_align_is_complete_and_the_walk_finds_every_module() -> None:
    inner = _pair(cascode=True)
    top = h.Module(name="top")
    top.d, top.g, top.s = h.Signal(), h.Signal(), h.Signal()
    top.core = inner(d=top.d, g=top.g, s=top.s)
    place(top, rows(), auto=(top.core,))
    pnr = pnr_input(top)
    assert pnr is not None and issues(pnr) == []
    assert [pnr.module.name for pnr in pnr_inputs(top)] == ["top", inner.name]


def test_a_device_in_halves_is_placed_once_in_its_parts() -> None:
    m = h.Module(name="tall")
    m.a, m.b = h.Signal(), h.Signal()
    m.MN = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))(d=m.a, g=m.a, s=m.b, b=m.b)
    a, b = halves(m.MN)
    pnr = place(m, rows(row(a), row(b)), symmetric=False)
    assert module_plan(pnr) == {"rows": [["Mn_a"], ["Mn_b"]], "symmetric": False, "split": {"Mn": 2}, "constraints": []}
    m2 = h.Module(name="short")
    m2.a = h.Signal()
    m2.MN = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))(d=m2.a, g=m2.a, s=m2.a, b=m2.a)
    assert issues(place(m2, rows(row(halves(m2.MN)[0])))) == ["MN is placed 1 times"]


def _demo() -> tuple[h.Module, tuple[c.Constraint, ...]]:
    """A latch-like cell and one of each of ALIGN's constraints on it."""
    m = h.Module(name="demo")
    m.vdd, m.vss, m.inp, m.inn, m.outp, m.outn, m.clk = (h.Port() for _ in range(7))
    m.tail = h.Signal()
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    m.MP = device(d=m.outn, g=m.inp, s=m.tail, b=m.vss)
    m.MN = device(d=m.outp, g=m.inn, s=m.tail, b=m.vss)
    m.MT = device(d=m.tail, g=m.clk, s=m.vss, b=m.vss)
    m.MLp = device(d=m.outn, g=m.outp, s=m.vdd, b=m.vss)
    m.MLn = device(d=m.outp, g=m.outn, s=m.vdd, b=m.vss)
    load = c.Group("Xload", (m.MLp, m.MLn), constraints=(c.Order((m.MLp, m.MLn), c.OrderDirection.LEFT_TO_RIGHT),))
    every = (
        c.Order((m.MP, m.MN), c.OrderDirection.LEFT_TO_RIGHT, abut=True),
        c.Align((m.MP, m.MN), c.Line.H_BOTTOM),
        c.AlignInOrder((m.MP, m.MT, m.MN), c.Edge.BOTTOM, c.Axis.HORIZONTAL),
        c.Spread((m.MP, m.MN), c.Axis.HORIZONTAL, 200),
        c.Floorplan(((load,), (m.MP, m.MT, m.MN)), order=True, symmetrize=True),
        c.SymmetricBlocks(((m.MP, m.MN), (m.MT,)), c.Axis.VERTICAL),
        load,
        c.SameTemplate((m.MP, m.MN)),
        c.PlaceCloser((m.MP, m.MN)),
        c.PlaceOnBoundary(south=(m.MT,), northwest=m.MP),
        c.Stackup((m.MLp, m.MLn), max_layer=3),
        c.PlaceOnGrid(c.Axis.HORIZONTAL, 80, (((0, 40), (1, -1)),)),
        c.CompactPlacement(c.Compaction.CENTER),
        c.BlockDistance(10),
        c.HorizontalDistance(10),
        c.VerticalDistance(10),
        c.AssignBboxVariables(m.MT, 0, 0, 100, 100),
        c.AspectRatio(0.5, 2.0),
        c.Boundary(50.0, 25.0),
        c.Generator("MomUnit", {"style": "STRIP"}),
        c.GroupCaps("Ccc", (m.MP, m.MN), 1.5, (1, 1)),
        c.GuardRing("guard_ring", m.vss, "demo"),
        c.DoNotIdentify((m.MT,)),
        c.DoNotUseLib(("INV",)),
        c.ConfigureCompiler(auto_constraint=False),
        c.PowerPorts((m.vdd,)),
        c.GroundPorts((m.vss,)),
        c.ClockPorts((m.clk,)),
        c.DoNotRoute((m.vdd, m.vss)),
        c.Route(1, 3, (c.CustomizeRoute((m.outp, m.outn), 2, 4, shield=True, match=True),)),
        c.NetConst((m.outp, m.outn), shield=m.vss, criticality=10),
        c.NetPriority((m.outp,), 5),
        c.MultiConnection((m.tail,), 2),
        c.SymmetricNets(m.outp, m.outn, c.Axis.VERTICAL, (m.MN.d, m.MLn.d), (m.MP.d, m.MLp.d)),
        c.PortLocation((m.outp,), c.Location.TC),
        c.ChargeFlow((0.0, 1e-9), ((m.MT.d, (1e-6, 2e-6)),)),
    )
    return m, every


def _align_types() -> list[str]:
    source = (ALIGN_HOME / "align" / "schema" / "constraint.py").read_text()
    union = re.search(r"ConstraintType\s*=\s*Union\[(.*?)\]", source, re.DOTALL)
    assert union, "ALIGN's ConstraintType union not found"
    body = re.sub(r"#.*", "", union.group(1))
    return [name.strip() for name in body.split(",") if name.strip()]


def test_every_align_constraint_type_has_a_class() -> None:
    if not (ALIGN_HOME / "align").is_dir():
        pytest.skip("ALIGN is not installed")
    assert sorted(c.ALIGN_NAMES) == sorted(_align_types())


def test_each_constraint_names_the_modules_own_objects_and_groups_come_first() -> None:
    m, every = _demo()
    assert sorted({type(x).__name__ for x in every}) == sorted(cls.__name__ for cls in c.ALIGN_NAMES.values())
    plan = module_plan(place(m, rows(row(m.MP, m.MT, m.MN)), auto=(m.MLp, m.MLn), constraints=every))
    written = plan["constraints"]
    assert written[0]["constraint"] == "GroupBlocks" and written[0]["instances"] == ["Mlp", "Mln"]
    by_type = {x["constraint"]: x for x in written}
    assert set(by_type) == set(c.ALIGN_NAMES)
    assert by_type["Floorplan"]["regions"] == [["Xload"], ["Mp", "Mt", "Mn"]]
    assert by_type["SymmetricNets"]["pins1"] == ["Mn/d", "Mln/d"]
    assert by_type["Route"]["customize"][0]["max_layer"] == "M4"
    assert by_type["ChargeFlow"]["pin_current"] == {"Mt/d": [1e-6, 2e-6]}
    assert by_type["SymmetricBlocks"]["direction"] == "V" and by_type["Spread"]["direction"] == "horizontal"
    assert by_type["PlaceOnBoundary"] == {"constraint": "PlaceOnBoundary", "south": ["Mt"], "northwest": "Mp"}
    assert by_type["Stackup"] == {"constraint": "Stackup", "instances": ["Mlp", "Mln"], "max_layer": "M3"}


def test_a_constraint_on_another_modules_instance_or_net_is_an_issue() -> None:
    m, _ = _demo()
    other, _ = _demo()
    pnr = place(
        m,
        rows(row(m.MP, m.MT, m.MN), row(m.MLp, m.MLn)),
        constraints=(c.Order((m.MP, other.MN)), c.DoNotRoute((other.vdd,))),
    )
    assert [x.split(" names ")[0] for x in issues(pnr)] == ["Order", "DoNotRoute"]


def test_a_group_in_a_row_places_its_instances() -> None:
    m, _ = _demo()
    load = c.Group("Xload", (m.MLp, m.MLn))
    plan = module_plan(place(m, rows(row(load), row(m.MP, m.MT, m.MN))))
    assert plan["rows"] == [["Xload"], ["Mp", "Mt", "Mn"]]
    assert plan["constraints"] == [{"constraint": "GroupBlocks", "instance_name": "Xload", "instances": ["Mlp", "Mln"]}]
    assert issues(place(_demo()[0], rows())) != []


_CHECK = """
import json, sys
from align.schema import constraint, Model, Instance, SubCircuit, Library
from align.schema.types import set_context

design = json.load(open(sys.argv[1]))
refused = {}
for entry in design["constraints"]:
    library = Library()
    with set_context(library):
        library.append(Model(name="NMOS", pins=["D", "G", "S", "B"]))
        subckt = SubCircuit(name=design["name"].upper(), pins=[p.upper() for p in design["ports"]])
        library.append(subckt)
    with set_context(subckt.elements):
        for name, pins in design["instances"].items():
            subckt.elements.append(Instance(name=name.upper(), model="NMOS", pins={k.upper(): v.upper() for k, v in pins.items()}))
    with set_context(subckt.constraints):
        try:
            for group in design["groups"]:
                if entry is not group:
                    subckt.constraints.append(group)
            subckt.constraints.append(entry)
        except Exception as error:
            refused[entry["constraint"]] = str(error)[:400]
print(json.dumps(refused))
"""


def test_align_accepts_every_constraint_written(tmp_path) -> None:
    python = ALIGN_HOME / "general" / "bin" / "python"
    if not python.is_file():
        pytest.skip("ALIGN is not installed")
    m, every = _demo()
    written = module_plan(place(m, rows(row(m.MP, m.MT, m.MN)), auto=(m.MLp, m.MLn), constraints=every))["constraints"]
    design = {
        "name": m.name,
        "ports": list(m.ports),
        "instances": {name: {p: s.name for p, s in inst.conns.items()} for name, inst in m.instances.items()},
        "constraints": written,
        "groups": [x for x in written if x["constraint"] == "GroupBlocks"],
    }
    path = tmp_path / "design.json"
    path.write_text(json.dumps(design))
    done = subprocess.run(
        [str(python), "-c", _CHECK, str(path)],
        env=align_env(),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert json.loads(done.stdout.strip().splitlines()[-1]) == {}


def _inverters() -> h.Module:
    """Two inverters in a cell that states its own rows, PMOS over NMOS."""
    cell = h.Module(name="inv2")
    cell.a, cell.y, cell.vdd, cell.vss = h.Port(), h.Port(), h.Port(), h.Port()
    cell.n0 = h.Signal()
    nmos = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.LOW))
    pmos = h.primitives.Pmos(h.primitives.MosParams(tp=MosType.PMOS, vth=MosVth.LOW))
    cell.mn0 = nmos(d=cell.n0, g=cell.a, s=cell.vss, b=cell.vss)
    cell.mp0 = pmos(d=cell.n0, g=cell.a, s=cell.vdd, b=cell.vdd)
    cell.mn1 = nmos(d=cell.y, g=cell.n0, s=cell.vss, b=cell.vss)
    cell.mp1 = pmos(d=cell.y, g=cell.n0, s=cell.vdd, b=cell.vdd)
    place(cell, rows(row(cell.mp0, cell.mp1), row(cell.mn0, cell.mn1)), symmetric=False)
    return cell


def test_a_child_module_in_a_row_is_one_instance_laid_out_by_its_own_plan() -> None:
    cell = _inverters()
    top = h.Module(name="top")
    top.a, top.y, top.z, top.vdd, top.vss = h.Port(), h.Port(), h.Port(), h.Port(), h.Port()
    top.Xa = cell(a=top.a, y=top.y, vdd=top.vdd, vss=top.vss)
    top.b = cell(a=top.y, y=top.z, vdd=top.vdd, vss=top.vss)
    top.Mz = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.LOW))(d=top.z, g=top.z, s=top.vss, b=top.vss)
    plan = module_plan(place(top, rows(row(top.Xa, top.b), row(top.Mz)), symmetric=False))
    assert plan["rows"] == [["Xa", "Xb"], ["Mz"]] and plan["constraints"] == []
    assert [pnr.module.name for pnr in pnr_inputs(top)] == ["top", "inv2"]
    assert module_plan(pnr_input(cell))["rows"] == [["Mp0", "Mp1"], ["Mn0", "Mn1"]]


def test_a_group_takes_only_the_constraints_align_takes_within_one() -> None:
    m, _ = _demo()
    with pytest.raises(ValueError, match="no PowerPorts within a group"):
        c.Group("Xload", (m.MLp, m.MLn), constraints=(c.PowerPorts((m.vdd,)),))
