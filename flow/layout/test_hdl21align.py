"""hdl21align: placement and ALIGN's every constraint stated on a generator's own instances and
nets, checked complete, named as the netlist names them (``module_plan``); ALIGN's own schema
accepts what it writes."""

import json
import re
import subprocess

import hdl21 as h
import pytest
from hdl21.primitives import MosType, MosVth, Nmos

from flow.layout.hdl21align import (
    column,
    halves,
    issues,
    module_plan,
    netlist_name,
    place,
    pnr_input,
    pnr_inputs,
    row,
    rows,
    sides,
)
from flow.layout.hdl21align import constraints as c
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


def _six() -> h.Module:
    """Six like NMOS devices on two nets, ``Ma`` to ``Mf``."""
    m = h.Module(name="six")
    m.x, m.y = h.Port(), h.Port()
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    for name in "abcdef":
        m.add(device(d=m.x, g=m.y, s=m.y, b=m.y), name=f"M{name}")
    return m


def test_a_column_in_a_row_is_a_sub_cell_stacking_its_entries() -> None:
    m = _six()
    plan = module_plan(place(m, rows(row(m.Ma, column(m.Mb, row(m.Mc, m.Md), m.Me), m.Mf))))
    assert plan["rows"] == [["Ma", "Xcolumn0", "Mf"]]
    assert plan["constraints"] == [
        {
            "constraint": "GroupBlocks",
            "instance_name": "Xcolumn0",
            "instances": ["Mb", "Mc", "Md", "Me"],
            "constraints": [
                {
                    "constraint": "Floorplan",
                    "regions": [["Mb"], ["Mc", "Md"], ["Me"]],
                    "order": True,
                    "symmetrize": True,
                },
                {"constraint": "DoNotIdentify", "instances": ["Mb", "Mc", "Md", "Me"]},
            ],
        }
    ]


def test_nesting_opens_like_containers_and_names_columns_inner_first() -> None:
    m = _six()
    nested = rows(row(row(m.Ma, column(column(m.Mb), m.Mc)), column(m.Md, row(m.Me, column(m.Mf)))))
    m2 = _six()
    flat = rows(row(m2.Ma, column(m2.Mb, m2.Mc), column(m2.Md, row(m2.Me, m2.Mf))))
    a = module_plan(place(m, nested, symmetric=False))
    b = module_plan(place(m2, flat, symmetric=False))
    assert a == b and a["rows"] == [["Ma", "Xcolumn0", "Xcolumn1"]]
    assert a["constraints"][1]["constraints"][0]["regions"] == [["Md"], ["Me", "Mf"]]
    # a column of one entry is that entry; a column at the top is the rows themselves
    m3 = _six()
    top = rows(column(row(m3.Ma, column(m3.Mb), m3.Mc), m3.Md, row(m3.Me, m3.Mf)))
    assert module_plan(place(m3, top))["rows"] == [["Ma", "Mb", "Mc"], ["Md"], ["Me", "Mf"]]


def test_a_column_within_a_column_within_a_row_is_a_group_within_a_group() -> None:
    m = _six()
    inner = column(m.Mc, m.Md, name="Xinner")
    plan = module_plan(
        place(m, rows(row(m.Ma, column(m.Mb, row(inner, m.Me)), m.Mf)), constraints=(c.Stackup((inner,), max_layer=3),))
    )
    groups = [(x["instance_name"], x["instances"]) for x in plan["constraints"] if x["constraint"] == "GroupBlocks"]
    assert groups == [("Xinner", ["Mc", "Md"]), ("Xcolumn0", ["Mb", "Xinner", "Me"])]
    assert plan["constraints"][-1] == {"constraint": "Stackup", "instances": ["Xinner"], "max_layer": "M3"}


def test_each_instance_is_placed_once_through_every_nesting() -> None:
    m = _six()
    pnr = place(m, rows(row(m.Ma, column(m.Mb, row(m.Mc, m.Ma)), m.Md), row(m.Me)))
    assert sorted(issues(pnr)) == ["Ma is placed 2 times", "Mf is in no row and not left to ALIGN"]
    top = h.Module(name="top")
    top.a, top.y, top.vdd, top.vss = h.Port(), h.Port(), h.Port(), h.Port()
    top.Xa = _inverters()(a=top.a, y=top.y, vdd=top.vdd, vss=top.vss)
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    top.Mb, top.Mc = device(d=top.y, g=top.a, s=top.vss, b=top.vss), device(d=top.y, g=top.a, s=top.vss, b=top.vss)
    named = rows(row(column(top.Mb, top.Mc, name="Xa"), top.Xa))
    assert issues(place(top, named)) == ["a sub-cell is named as an instance: XA"]
    m3 = _six()
    twice = rows(row(column(m3.Ma, m3.Mb, name="Xs"), column(m3.Mc, m3.Md, name="Xs")), row(m3.Me, m3.Mf))
    assert issues(place(m3, twice)) == ["two sub-cells are named XS"]


def _diff(*, taken: bool = False) -> h.Module:
    """A differential pair (an ``h.Pair``, ``diff``) on a tail."""
    m = h.Module(name="diff")
    m.inp, m.inn, m.vss, m.tail = h.Port(), h.Port(), h.Port(), h.Signal()
    m.out = h.Diff()
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    m.diff = h.Pair(device)(d=m.out, g=h.AnonymousBundle(p=m.inp, n=m.inn), s=m.tail, b=m.vss)
    m.Mtail = device(d=m.tail, g=m.inp, s=m.vss, b=m.vss)
    if taken:
        m.diff_p = device(d=m.tail, g=m.inp, s=m.vss, b=m.vss)
    return m


_PAIR_CELL = {
    "constraint": "GroupBlocks",
    "instance_name": "Xdiff",
    "instances": ["Mdiff_p", "Mdiff_n"],
    "constraints": [
        {"constraint": "Order", "instances": ["Mdiff_p", "Mdiff_n"], "abut": False, "direction": "left_to_right"},
        {"constraint": "SymmetricBlocks", "pairs": [["Mdiff_p", "Mdiff_n"]], "direction": "V"},
    ],
}


def test_a_pair_placed_whole_is_a_mirrored_sub_cell_before_and_after_elaboration() -> None:
    m = _diff()
    pnr = place(m, rows(row(m.diff), row(m.Mtail)))
    before = module_plan(pnr)
    assert before == {"rows": [["Xdiff"], ["Mtail"]], "symmetric": True, "split": {}, "constraints": [_PAIR_CELL]}
    h.elaborate(m)
    assert set(m.instances) == {"diff_p", "diff_n", "Mtail"} and not m.instbundles
    assert module_plan(pnr) == before


@pytest.mark.parametrize(
    ("arrange", "symmetric", "added"),
    (
        ("p tail n", True, False),  # the mirrored rows mirror them already
        ("p tail n", False, True),
        ("p n tail", True, True),  # in the rows' mirrored places: (p, tail) and n
        ("p tail/n", False, False),  # in two rows: mirrored about no vertical axis
    ),
)
def test_a_pairs_sides_in_one_row_are_mirrored_unless_stated(arrange: str, symmetric: bool, added: bool) -> None:
    m = _diff()
    p, n = sides(m.diff)
    by = {"p": p, "n": n, "tail": m.Mtail}
    placed = rows(*(row(*(by[x] for x in r.split())) for r in arrange.split("/")))
    plan = module_plan(place(m, placed, symmetric=symmetric))
    mirror = {"constraint": "SymmetricBlocks", "pairs": [["Mdiff_p", "Mdiff_n"]], "direction": "V"}
    assert plan["constraints"] == ([mirror] if added else [])
    h.elaborate(m)
    assert module_plan(pnr_input(m)) == plan


def test_a_pairs_symmetry_the_generator_states_is_not_repeated() -> None:
    m = _diff()
    p, n = sides(m.diff)
    stated = c.SymmetricBlocks(((p, n), (m.Mtail,)), c.Axis.VERTICAL)
    plan = module_plan(place(m, rows(row(p, n, m.Mtail)), symmetric=False, constraints=(stated,)))
    assert plan["constraints"] == [
        {"constraint": "SymmetricBlocks", "pairs": [["Mdiff_p", "Mdiff_n"], ["Mtail"]], "direction": "V"}
    ]


def test_a_pair_is_placed_once_in_its_sides_and_only_its_own_module_s() -> None:
    m = _diff()
    p, _ = sides(m.diff)
    assert issues(place(m, rows(row(p, m.Mtail)))) == ["diff is placed 1 times"]
    m2 = _diff()
    assert issues(place(m2, rows(row(m2.Mtail)))) == ["diff is in no row and not left to ALIGN"]
    m3 = _diff()
    pnr = place(m3, rows(row(m3.Mtail)), auto=(m3.diff,))
    assert issues(pnr) == []
    h.elaborate(m3)
    assert issues(pnr) == []
    m4 = _diff()
    assert "a placed Pair is not the module's" in issues(place(m4, rows(row(m4.diff, m4.Mtail, _diff().diff))))
    with pytest.raises(ValueError, match="its name taken: diff_p"):
        place(_diff(taken=True), rows())
    with pytest.raises(TypeError):
        sides(m4.Mtail)


def test_a_pair_within_a_column_is_a_sub_cell_within_it() -> None:
    m = _diff()
    plan = module_plan(place(m, rows(row(column(m.diff, m.Mtail))), symmetric=False))
    assert plan["rows"] == [["Xcolumn0"]]
    assert plan["constraints"][0] == _PAIR_CELL
    assert plan["constraints"][1]["instances"] == ["Xdiff", "Mtail"]
    assert plan["constraints"][1]["constraints"] == [
        {"constraint": "Floorplan", "regions": [["Xdiff"], ["Mtail"]], "order": True, "symmetrize": False},
        {"constraint": "DoNotIdentify", "instances": ["Mtail"]},
    ]


@pytest.mark.parametrize("whole", (False, True))
def test_align_accepts_nested_columns_and_pairs(tmp_path, whole: bool) -> None:
    python = ALIGN_HOME / "general" / "bin" / "python"
    if not python.is_file():
        pytest.skip("ALIGN is not installed")
    m = _diff()
    device = Nmos(h.primitives.MosParams(tp=MosType.NMOS, vth=MosVth.STD))
    m.Mx, m.My = (device(d=m.tail, g=m.inn, s=m.vss, b=m.vss) for _ in range(2))
    p, n = sides(m.diff)
    if whole:  # the pair's sub-cell within a column
        placed = rows(row(m.Mx, column(m.diff, row(m.Mtail, m.My), name="Xstack")))
    else:
        placed = rows(row(p, column(m.Mtail, row(m.Mx, m.My)), n))
    pnr = place(m, placed, symmetric=not whole)
    h.elaborate(m)
    written = module_plan(pnr)["constraints"]
    design = {
        "name": m.name,
        "ports": list(m.ports),
        # the instances as the netlist names them: the pair's ``diff_p`` is ``Mdiff_p``
        "instances": {netlist_name(k, x.of): {p: s.name for p, s in x.conns.items()} for k, x in m.instances.items()},
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
