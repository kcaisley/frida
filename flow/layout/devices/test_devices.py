"""The precharacterized devices: every PDK's tables current, the lookups' arithmetic, and requests
that netlist as ideal devices and resolve to a PDK's own."""

import io
import json
from importlib import import_module
from itertools import pairwise

import hdl21 as h
import pytest
from hdl21.primitives import MosType, MosVth

from .device import ROOT, FloorError, geometry_of, request_of, resolve, table_path
from .momcap.geometry import MomcapGeometry, MomStyle
from .momcap.netlist import StripParams, UnitParams, strip, unit
from .momcap.table import MomcapTable
from .moscap.table import MosCapTable
from .mosfet.geometry import InverterGeometry
from .mosfet.netlist import DriverParams, DriverRequest, _input, driver, shared_fanin
from .mosfet.table import MosfetTable
from .polyres.table import PolyResTable

PDKS = ("tsmc65", "tsmc28", "tpsc65", "ihp130", "tower180", "lf150", "sky130", "gf180")
KINDS = ("mosfet", "moscap", "polyres", "momcap")


def _checked_out(pdk: str) -> bool:
    return (ROOT / "pdk" / pdk / "layout" / "tech.py").is_file()


@pytest.mark.parametrize("pdk", PDKS)
@pytest.mark.parametrize("kind", KINDS)
def test_every_pdk_has_every_table(kind: str, pdk: str) -> None:
    if not _checked_out(pdk):
        pytest.skip(f"{pdk} is not checked out")
    path = table_path(kind, pdk)
    assert path.is_file(), f"{path}: run python -m flow.layout.devices.{kind}.characterize {pdk}"
    provenance = json.loads(path.read_text())["provenance"]
    assert (provenance["pdk"], provenance["kind"], provenance["corner"]) == (pdk, kind, "TYPICAL")
    assert provenance["code_sha"]  # the code that made it, recorded; tables are not remade for code moves


def _mosfets() -> MosfetTable:
    return MosfetTable(pdk="synthetic", vdd_v=1.0, switching_ohm={"NMOS/LOW": 10e3, "PMOS/LOW": 25e3}, triode_ohm={})


def test_a_width_is_the_narrowest_whole_number_of_units_that_reaches_the_resistance() -> None:
    table = _mosfets()
    assert table.width(MosType.NMOS, MosVth.LOW, 1e3).units == 10
    assert table.width(MosType.NMOS, MosVth.LOW, 0.9e3).units == 12
    assert table.width(MosType.PMOS, MosVth.LOW, 1e3).units == 25
    assert table.width(MosType.NMOS, MosVth.LOW, 1e9).units == 1
    assert table.resistance(table.width(MosType.NMOS, MosVth.LOW, 0.9e3)) <= 0.9e3


def test_a_driver_chain_tapers_at_fo4_from_its_flip_flop_and_keeps_its_polarity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("flow.layout.devices.mosfet.netlist.mosfet_table", lambda pdk: _mosfets())
    least = _input(1, 1)  # the minimum inverter: a minimum-strength flip-flop's drive
    for invert in (False, True):
        for fanin in (4.0, 2.5, 1.0):
            stages = DriverRequest(100.0, invert, fanin=fanin).stages("synthetic")
            assert stages[-1] == (100, 250)  # each type from its own column
            assert len(stages) % 2 == (1 if invert else 0)
            loads = [_input(n, p) for n, p in stages]
            # the flip-flop drives it within its share of FO4, or the smallest inverter of its kind
            assert loads[0] <= max(fanin * least, _input(1, 2))
            assert all(after <= 4 * before for before, after in pairwise(loads))  # FO4 along the chain
    # a load within FO4 of the flip-flop is one inverter, and two where it must not invert
    small = DriverRequest(1e5, True).stages("synthetic")
    assert len(small) == 1 and len(DriverRequest(1e5, False).stages("synthetic")) == 2
    assert shared_fanin("synthetic", [DriverRequest(1e5, True)]) == 4.0 - _input(*small[0]) / least


def _strips() -> MomcapTable:
    # net = 0.5 Lm - 0.5 Ld, plus parasitic pairs; the shortest finger 1 um on a 5 nm grid
    pairs = {
        "MAIN-TOP": {"main_ff_per_um": 0.5, "diff_ff_per_um": 0.0, "ff": 0.1},
        "DIFF-TOP": {"main_ff_per_um": 0.0, "diff_ff_per_um": 0.5, "ff": 0.1},
        "SHIELD-TOP": {"main_ff_per_um": 0.2, "diff_ff_per_um": 0.2, "ff": 0.0},
    }
    entry = {"grid_nm": 5, "min_length_nm": 1000, "end_gap_nm": 200, "pairs": pairs}
    # ring units: 0.6 fF the smallest on three metals, 0.4 on two, 0.2 on one
    rings = {
        str(m): {
            "grid_nm": 5,
            "min_length_nm": 1000,
            "pairs": {"INNER-TOP": {"ff_per_um": 0.4 * m / 3, "ff": 0.2 * m / 3}},
        }
        for m in (1, 2, 3)
    }
    return MomcapTable(pdk="synthetic", styles={"DIFFERENCE": {"3": entry}, "RING": rings})


def test_every_strip_is_as_long_as_the_whole_one_and_nets_its_weight() -> None:
    table = _strips()
    whole, _ = table.strip(3, 32e-15, 32e-15)
    assert whole.diff_length_nm == 1000  # the whole strip's difference finger is the stub
    for net in (1e-15, 5e-15, 16e-15, 31e-15):
        geometry, floor = table.strip(3, net, 32e-15)
        assert floor is None
        assert geometry.length_nm + geometry.diff_length_nm == whole.length_nm + whole.diff_length_nm
        c = table.capacitances(geometry)
        assert c[("MAIN", "TOP")] - c[("DIFF", "TOP")] == pytest.approx(net, abs=0.5 * 5e-3 * 1e-15)


def test_a_unit_below_the_smallest_drops_metals_then_draws_the_smallest_with_an_error() -> None:
    table = _strips()
    assert [round(table.smallest_unit(m) * 1e15, 3) for m in (1, 2, 3)] == [0.2, 0.4, 0.6]
    assert [table.unit(3, c)[0].layers for c in (2.2e-15, 0.5e-15, 0.3e-15)] == [3, 2, 1]
    small, floor = table.unit(3, 0.1e-15)
    assert (small.layers, small.length_nm) == (1, 1000)
    assert isinstance(floor, FloorError) and "the smallest, 0.200 fF on 1 metal" in str(floor)


def test_a_request_netlists_as_ideal_devices_before_any_pdk() -> None:
    top = h.Module(name="top")
    top.a, top.y, top.vdd, top.vss = h.Signal(), h.Signal(), h.Signal(), h.Signal()
    top.drive = driver(DriverParams(r_ohm=1e3))(A=top.a, Y=top.y, VDD=top.vdd, VSS=top.vss)
    top.cap = strip(StripParams(net_f=1e-15, whole_f=32e-15))(MAIN=top.y, DIFF=top.a, TOP=top.vdd, SHIELD=top.vss)
    assert isinstance(request_of(top.drive.of), DriverRequest)
    text = io.StringIO()
    h.netlist(top, text, fmt="spice")
    assert "1000.0" in text.getvalue() or "1e+03" in text.getvalue() or "1000" in text.getvalue()


@pytest.mark.parametrize("pdk", PDKS)
def test_a_driver_request_resolves_to_the_pdks_own_inverters(pdk: str) -> None:
    if not table_path("mosfet", pdk).is_file():
        pytest.skip(f"{pdk} has no mosfet table")
    top = h.Module(name="top")
    top.a, top.y, top.vdd, top.vss = h.Signal(), h.Signal(), h.Signal(), h.Signal()
    top.drive = driver(DriverParams(r_ohm=500.0, invert=True))(A=top.a, Y=top.y, VDD=top.vdd, VSS=top.vss)
    assert resolve(top, pdk) == []
    assert request_of(top.drive.of) is None
    h.pdk.compile(top)  # the view is the PDK's devices
    cells = list(top.drive.of.instances.values())
    assert len(cells) % 2 == 1  # an odd number of inverters
    for cell in cells:  # each its NMOS and PMOS in one complementary row cell
        assert len(cell.of.instances) == 2
        assert isinstance(geometry_of(cell.of), InverterGeometry)
    assert geometry_of(top.drive.of) is None
    assert import_module(f"pdk.{pdk}.hdl21")


def test_a_strip_view_carries_its_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flow.layout.devices.momcap.netlist.momcap_table", lambda pdk: _strips())
    monkeypatch.setattr("flow.layout.devices.device.import_module", lambda name: type("m", (), {"pdk_logic": None}))
    monkeypatch.setattr("flow.layout.devices.device.h.pdk.set_default", lambda logic: None)
    top = h.Module(name="top")
    top.m, top.d, top.t, top.b = h.Signal(), h.Signal(), h.Signal(), h.Signal()
    top.cap = strip(StripParams(net_f=1e-15, whole_f=32e-15))(MAIN=top.m, DIFF=top.d, TOP=top.t, SHIELD=top.b)
    assert resolve(top, "synthetic") == []
    geometry = geometry_of(top.cap.of)
    assert isinstance(geometry, MomcapGeometry)
    assert geometry.style is MomStyle.DIFFERENCE and geometry.layers == 3
    assert {inst.of.name if hasattr(inst.of, "name") else "" for inst in top.cap.of.instances.values()}


def test_the_compile_returns_a_floor_error_for_each_undersized_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flow.layout.devices.momcap.netlist.momcap_table", lambda pdk: _strips())
    monkeypatch.setattr("flow.layout.devices.device.import_module", lambda name: type("m", (), {"pdk_logic": None}))
    monkeypatch.setattr("flow.layout.devices.device.h.pdk.set_default", lambda logic: None)
    top = h.Module(name="top")
    top.b, top.t, top.g = h.Signal(), h.Signal(), h.Signal()
    small = unit(UnitParams(c_f=0.1e-15))
    top.c0 = small(INNER=top.b, TOP=top.t, SHIELD=top.g)
    top.c1 = small(INNER=top.b, TOP=top.t, SHIELD=top.g)
    top.c2 = unit(UnitParams(c_f=2.2e-15))(INNER=top.b, TOP=top.t, SHIELD=top.g)
    floors = resolve(top, "synthetic")
    assert [str(f).split(":")[0] for f in floors] == ["top.c0", "top.c1"]


def test_a_resistor_length_reaches_its_resistance_on_the_grid() -> None:
    table = PolyResTable(pdk="synthetic", sheet_ohm=1000.0, end_ohm_um=50.0, dw_nm=20.0, width_nm=420, grid_nm=5)
    for r_ohm in (500.0, 5e3, 50e3):
        geometry = table.length(r_ohm)
        assert geometry.w_nm == 420 and geometry.l_nm % 5 == 0
        assert table.resistance(geometry) == pytest.approx(r_ohm, rel=0.01)


def test_a_moscap_takes_the_nearest_whole_number_of_units() -> None:
    table = MosCapTable(pdk="synthetic", ff_per_unit={"NMOS/STD": 0.8, "PMOS/STD": 0.7}, ff_per_um2={})
    assert table.units(MosType.NMOS, MosVth.STD, 8.1).units == 10
    assert table.units(MosType.PMOS, MosVth.STD, 0.1).units == 1


def test_a_resolved_strip_is_called_as_its_first_class_device() -> None:
    """A MOM unit is the PDK's ALIGN device of its style (``fmomdiff``, flow/layout/primitives/models.py),
    called like a transistor: its design values, then the parameters MomUnit reads; no subcircuit."""
    if not table_path("momcap", "tsmc65").is_file():
        pytest.skip("tsmc65 has no momcap table")
    from io import StringIO

    import vlsirtools

    from flow.circuit.netlists import Block, Context, package

    top = h.Module(name="top")
    top.m, top.d, top.t, top.s = h.Signal(), h.Signal(), h.Signal(), h.Signal()
    top.Xs = strip(StripParams(net_f=1e-15, whole_f=18e-15))(MAIN=top.m, DIFF=top.d, TOP=top.t, SHIELD=top.s)
    assert resolve(top, "tsmc65") == []
    geometry = geometry_of(top.Xs.of)
    out = StringIO()
    vlsirtools.netlist(package(Block(top, "tsmc65", "top", []), Context.ALIGN), out, fmt="cdl")
    (line,) = [line for line in out.getvalue().splitlines() if line.startswith("X")]
    assert isinstance(geometry, MomcapGeometry)
    assert line.startswith("Xs m d t s fmomdiff c=") and " c_diff=" in line
    assert f"length={geometry.length_nm} diff_length={geometry.diff_length_nm}" in line
    assert ".SUBCKT" not in out.getvalue().split(".SUBCKT top")[0]  # no unit subcircuit
