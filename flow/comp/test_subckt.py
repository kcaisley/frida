"""Software-only structural tests for the comparator's circuit (``netlist``), and its layout: the
placement it states (every latch and bias, as laid out, a row each device by its role)."""

import itertools

import pytest
from hdl21.primitives import MosType
from pydantic import ValidationError

from flow import pipeline
from flow.circuit.devices import fingers
from flow.layout.devices.moscap.netlist import CAP_L
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import subckt, sweep
from .params import Bias, Latch, Params, layout_view
from .subckt import netlist


def test_comp():
    """Verify comparator generator produces a valid module."""
    m = netlist(Params())
    assert m is not None


def test_default_comp_is_single_tail_nmos_strongarm() -> None:
    """Pin the default topology and its sizes, the characterization's short-channel ones."""

    netlist.Cache.reset()
    params = Params()
    assert params.latch == Latch.STRONGARM
    assert params.input_pair == MosType.NMOS
    assert params.bias == Bias.SWITCHED
    assert (
        params.diffpair_w,
        params.diffpair_l,
        params.tail_w,
        params.tail_l,
        params.rst_w,
        params.rst_l,
        params.latch_on_w,
        params.latch_on_l,
        params.latch_init_w,
        params.latch_init_l,
        params.srlatch_n_w,
        params.srlatch_p_w,
    ) == (32, 2, 16, 2, 8, 1, 8, 1, 8, 1, 4, 8)

    module = netlist(params)
    assert module.Mtail.conns["s"] is module.vss
    assert module.Mtail_reset.conns["d"] is module.tail
    assert module.Mtail_reset.conns["g"] is module.clk
    assert module.Mtail_reset.conns["s"] is module.vdd
    assert float(module.Mtail.of.params.w) == 16
    assert float(module.Mtail.of.params.l) == 2
    assert float(module.Minner_init_p.of.params.w) == 8
    assert float(module.Mcross_on_p.of.params.w) == 8
    assert float(module.Mcross_init_p.of.params.w) == 8
    assert not hasattr(module, "Mbias")
    assert not hasattr(module, "Cbias")


def test_every_combination_of_latch_input_pair_and_bias_builds() -> None:
    """The topology is three independent choices: each of their 24 combinations builds."""

    for latch, input_pair, bias in itertools.product(Latch, MosType, Bias):
        netlist.Cache.reset()
        assert netlist(Params(latch=latch, input_pair=input_pair, bias=bias)) is not None


def test_every_comparator_the_class_admits_builds() -> None:
    """Sizes and capacitors are positive by type: a design with one at zero is refused when it is
    made, never checked after; the defaults are the characterization's sizes."""

    for name in ("diffpair_w", "tail_l", "latch_init_w", "preamp_c_ff", "bias_c_ff"):
        with pytest.raises(ValidationError):
            Params(**{name: 0})
    assert (Params().diffpair_l, Params().tail_w, Params().latch_on_w) == (2, 16, 8)


def test_a_space_widens_the_parameters_by_name() -> None:
    """``widen``: a parameter set to a range or values widens, to a bare value is held; a name the
    class does not have, or a value it does not take, is refused as it is set; a grid gives every
    combination, a range that applies only to a dynamic bias only there."""

    space = pipeline.widen(Params())
    space.latch = pipeline.values(Latch.STRONGARM, Latch.DOUBLE_TAIL)
    space.bias = pipeline.every(Bias)
    space.diffpair_w = pipeline.steps(32, 512, n=3, log=True)
    space.preamp_c_ff = pipeline.steps(30, 120, n=2, log=True, when=Bias.DYNAMIC)
    space.rst_l = 2
    with pytest.raises(AttributeError, match="no parameter diffpiar_w"):
        space.diffpiar_w = 64
    with pytest.raises(ValidationError):
        space.tail_w = pipeline.steps(0, 8)
    assert isinstance(space, pipeline.Space)
    points = list(space.points())
    assert len(points) == 2 * 3 + 2 * 3 * 2  # switched: latch x width; dynamic: also C_P
    assert all(design.rst_l == 2 for _varied, design in points)
    assert {design.diffpair_w for _varied, design in points} == {32, 128, 512}
    assert {design.preamp_c_ff for _varied, design in points if design.bias is Bias.SWITCHED} == {60}


def test_comp_output_srlatch_handles_both_reset_polarities() -> None:
    """Build the NOR and NAND variants of the held comparator output."""

    nor = netlist(Params())
    assert nor.Msr_p_p_decision.conns["d"] is nor.sr_p_stack
    assert nor.Msr_p_n_decision.conns["s"] is nor.vss
    assert nor.Msr_p_n_decision.conns["g"] is nor.decision_n
    assert nor.Msr_n_n_decision.conns["g"] is nor.decision_p
    assert nor.Mbuf2_outp_p.conns["d"] is nor.outp
    assert nor.Mbuf2_outn_p.conns["d"] is nor.outn

    # latch_p rising pulls decision_n low, which must set sr_p (outp high for inp > inn)
    nand = netlist(Params(input_pair=MosType.PMOS))
    assert nand.Msr_p_p_decision.conns["d"] is nand.sr_p
    assert nand.Msr_p_n_decision.conns["s"] is nand.sr_p_stack
    assert nand.Msr_p_p_decision.conns["g"] is nand.decision_n
    assert nand.Msr_p_n_decision.conns["g"] is nand.decision_n
    assert nand.Msr_n_n_decision.conns["g"] is nand.decision_p


def test_signaled_latch_devices_take_the_opposite_input_drain() -> None:
    """In every latch, each signaled device pair (gated by neither clock) is driven alike, the
    opposite input drain, so none works against another."""

    for latch in Latch:
        if latch == Latch.TRIPLE_TAIL:
            continue  # its later stages are fixed, its devices driven by the second stage
        netlist.Cache.reset()
        m = netlist(Params(latch=latch))
        signaled = [
            device
            for device in ("Mouter_on", "Minner_on", "Mouter_init", "Minner_init")
            if hasattr(m, f"{device}_p") and getattr(m, f"{device}_p").conns["g"] not in (m.clk, m.clkb)
        ]
        for device in signaled:
            assert getattr(m, f"{device}_p").conns["g"] is m.input_p_drain, (latch, device)
            assert getattr(m, f"{device}_n").conns["g"] is m.input_n_drain, (latch, device)
        assert signaled or latch is Latch.STRONGARM, latch  # every double tail signals a pair


def test_double_tail_shares_one_clocked_tail() -> None:
    """The double tail's second stage: one clocked tail under both cross-coupled halves, as wide as
    both halves' on devices together."""

    netlist.Cache.reset()
    params = Params(latch=Latch.DOUBLE_TAIL)
    m = netlist(params)
    assert m.Mcross_on_p.conns["s"] is m.outer and m.Mcross_on_n.conns["s"] is m.outer
    assert m.Mouter_on.conns["g"] is m.clkb and m.Mouter_on.conns["s"] is m.vdd
    assert float(m.Mouter_on.of.params.w) == fingers(2 * params.latch_on_w, "analog")[0]
    assert not hasattr(m, "Mouter_on_p") and not hasattr(m, "outerp")


def test_triple_tail_stages() -> None:
    """Cascoded preamp, PMOS-latch second stage on midp/midn, clocked-tail third stage."""

    netlist.Cache.reset()
    m = netlist(Params(latch=Latch.TRIPLE_TAIL))
    assert m.Mdiff_p.conns["d"] is m.cas_p and m.Mcas_p.conns["d"] is m.input_p_drain
    # the cascodes' gates reach VDD through a tie, never by metal alone
    assert m.Mcas_p.conns["g"] is m.cas_gate and m.Mcas_n.conns["g"] is m.cas_gate
    assert m.Mtie.conns["d"] is m.cas_gate and m.Mtie.conns["s"] is m.vdd and m.Mtie.conns["g"] is m.tie_bias
    assert m.Mtie_bias.conns["g"] is m.tie_bias and m.Mtie_bias.conns["s"] is m.vss
    gates = [inst.conns["g"] for inst in m.instances.values() if "g" in inst.conns]
    assert m.vdd not in gates and m.vss not in gates
    assert m.Mtail2.conns["g"] is m.clkb and m.Mmid_cross_p.conns["s"] is m.tail2
    assert m.Mmid_in_p.conns["d"] is m.midp and m.Mmid_in_p.conns["g"] is m.input_p_drain
    assert m.Mtail3.conns["g"] is m.clk and m.Mcross_on_p.conns["s"] is m.tail3
    assert m.Minner_init_p.conns["g"] is m.midn and m.Minner_init_n.conns["g"] is m.midp
    # stage three's precharge outdrives its tail until stage two releases it
    params = Params()
    assert float(m.Minner_init_p.of.params.w) == fingers(4 * params.rst_w, "analog")[0]
    assert float(m.Mtail3.of.params.w) == fingers(params.latch_on_w, "analog")[0]
    assert float(m.Mtail2.of.params.w) == fingers(2 * params.latch_on_w, "analog")[0]
    # the third stage precharges high like a StrongARM: NOR output latch
    assert m.Msr_p_p_decision.conns["d"] is m.sr_p_stack


def _align_netlist(params: Params, tmp_path) -> str:
    """The comparator's netlist in ALIGN's context in TSMC65 (``flow.circuit.netlists``)."""
    from flow.circuit.netlists import Context, compile_block, package, write

    from .subckt import Nets

    block = compile_block(netlist, params, "tsmc65", "comp", Nets)
    return write(package(block, Context.ALIGN), tmp_path / "comp.sp").read_text()


def test_devices_fit_the_pdk_rows_in_whole_units(tmp_path) -> None:
    """With TSMC65 active, analog devices take an even finger count within the row limit and
    the output stage's gates one count per NMOS/PMOS pair within the logic limits; every
    width written is a whole number of 120 nm units."""

    pdk = pytest.importorskip("pdk.tsmc65.hdl21.pdk_logic")
    from .params import FRIDA1

    limits = pdk.MOS_FINGER_UNITS
    devices = {}
    for line in _align_netlist(FRIDA1, tmp_path).splitlines():
        f = line.split()
        if f and f[0].startswith("M"):
            p = dict(kv.split("=") for kv in f[6:])
            w, nf = int(p["w"].removesuffix("n")), int(p["nf"])  # ALIGN's: w a finger's
            assert w % 120 == 0, line
            devices[f[0]] = (f[5][0], w // 120, nf, f[2])
    for name, (pol, units, nf, _gate) in devices.items():
        if name.startswith(("Mdecision", "Msr", "Mbuf")):
            assert units <= limits["logic_n" if pol == "n" else "logic_p"], name
        else:
            assert nf % 2 == 0 and units <= limits["analog"], name
    for gate in {g for name, (_, _, _, g) in devices.items() if name.startswith("Mbuf")}:
        counts = {nf for name, (_, _, nf, g) in devices.items() if g == gate and name.startswith("Mbuf")}
        assert len(counts) == 1, gate


def test_standard_cell_output_stage(tmp_path) -> None:
    """The output stage as generic logic cells, written as the PDK's library cells by its compile."""

    cells = pytest.importorskip("pdk.tsmc65.hdl21.stdcells")._LOGIC  # (generic cell, drive) -> library cell
    from .params import FRIDA1, OutputStage

    params = Params(**{**FRIDA1.__dict__, "output_stage": OutputStage.STDCELLS})
    lines = {line.split()[0]: line.split() for line in _align_netlist(params, tmp_path).splitlines() if line.split()}
    assert lines["Xdecision_p"][1:] == ["latch_n", "decision_p", "vdd", "vss", cells["inverter", 1].name]
    assert lines["Xsr_p"][1:] == ["decision_n", "sr_n", "sr_p", "vdd", "vss", cells["nor2", 2].name]
    assert lines["Xbuf2_outn"][-1] == cells["inverter", 8].name
    assert not any(name.startswith(("Mdecision", "Msr", "Mbuf")) for name in lines)


def test_the_dynamic_bias_capacitors() -> None:
    """The dynamic bias's capacitors, C_P on the input pair's drains and C_TAIL under its tail switch:
    MOS capacitors whose gate is their node, in strong inversion over its swing; a switched tail has
    neither, whatever their values."""

    netlist.Cache.reset()
    assert not hasattr(netlist(Params(preamp_c_ff=240)), "Mcap_p")
    module = netlist(Params(bias=Bias.DYNAMIC, preamp_c_ff=240, bias_c_ff=320))
    # an NMOS against ground, its gate the input pair's drain (precharged high), as wide as the
    # active PDK's measured gate capacitance makes 240 fF at CAP_L (fingered); without a PDK, a
    # unit device holds 0.1 fF per minimum length

    from flow.layout.devices.device import active_pdk
    from flow.layout.devices.moscap.table import density as gate_density

    density = gate_density(active_pdk())
    cap = module.Mcap_p
    assert cap.conns["g"] is module.input_p_drain and cap.conns["d"] is cap.conns["s"] is cap.conns["b"] is module.vss
    assert cap.of.params.tp == MosType.NMOS and float(cap.of.params.l) == CAP_L
    assert float(cap.of.params.w) == pytest.approx(240 / (density["n"] * CAP_L), rel=0.05)

    # the tail capacitor: a PMOS against the supply, its gate the cap node (starting at ground)
    tail = module.Mcap_tail
    assert tail.conns["g"] is module.cap_node and tail.conns["s"] is tail.conns["b"] is module.vdd
    assert tail.of.params.tp == MosType.PMOS
    assert float(tail.of.params.w) == pytest.approx(320 / (density["p"] * CAP_L), rel=0.05)
    default = netlist(Params(bias=Bias.DYNAMIC)).Mcap_tail
    assert float(default.of.params.w) == pytest.approx(100 / (density["p"] * CAP_L), rel=0.05)


def test_the_named_instances() -> None:
    """``python -m flow comp --to layout --instance NAME`` lays out these, each by the shared
    layout step (``flow.layout.step.lay_out_align``) as its generator places it."""
    assert set(pipeline.names(sweep)) == {
        "frida1",
        "strongarm",
        "double_tail",
        "triple_tail",
        "double_tail_self_timed",
        "double_tail_modified",
        "double_tail_modified_self_timed",
    }


def test_every_comparator_states_its_rows() -> None:
    """Every latch and bias, as laid out (``layout_view``: the output stage the PDK's library cells),
    places each device in a row by its role (``issues`` finds nothing): an even count of rows (its
    top row meets the edge), the cross-coupled init pair split cross-quad over two; the dynamic
    bias's capacitors split, on rows of their own above the input pair. Drawn transistor by
    transistor, the output stage fits no row, and the comparator states nothing: ALIGN places it."""
    for latch in Latch:
        for bias in (Bias.SWITCHED, Bias.DYNAMIC):
            pnr = pnr_input(subckt.netlist(layout_view(Params(latch=latch, bias=bias))))
            assert pnr is not None and issues(pnr) == []
            fp = module_plan(pnr)
            assert len(fp["rows"]) % 2 == 0
            assert {"Mcross_init_p_a", "Mcross_init_p_b"} <= {cell for row in fp["rows"] for cell in row}
            if bias == Bias.DYNAMIC:
                assert {"Mcap_tail", "Mcap_p", "Mcap_n"} <= set(fp["split"])
                assert fp["rows"][:2] == [["Mcap_tail_a"], ["Mcap_tail_b"]]
    assert pnr_input(subckt.netlist(Params())) is None
