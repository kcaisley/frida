"""Software-only structural tests for the comparator's circuit (``netlist``)."""

import itertools

import pytest
from hdl21.primitives import MosType

from flow import pipeline
from flow.circuit.devices import CAP_L, fingers

from .params import LATCHES, Bias, Latch, Params, State, valid
from .subckt import netlist


def test_comp():
    """Verify comparator generator produces a valid module."""
    m = netlist(Params())
    assert m is not None


def test_default_comp_is_single_tail_nmos_strongarm() -> None:
    """Pin the default topology and its power-of-two size multipliers."""

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
    ) == (32, 4, 4, 16, 8, 1, 4, 1, 4, 1, 4, 8)

    module = netlist(params)
    assert module.Mtail.conns["s"] is module.vss
    assert module.Mtail_reset.conns["d"] is module.tail
    assert module.Mtail_reset.conns["g"] is module.clk
    assert module.Mtail_reset.conns["s"] is module.vdd
    assert float(module.Mtail.of.params.w) == 4
    assert float(module.Mtail.of.params.l) == 16
    assert float(module.Minner_init_p.of.params.w) == 8
    assert float(module.Mcross_on_p.of.params.w) == 4
    assert float(module.Mcross_init_p.of.params.w) == 4
    assert not hasattr(module, "Mbias")
    assert not hasattr(module, "Cbias")


def test_every_combination_of_latch_input_pair_and_bias_builds() -> None:
    """The topology is three independent choices: each of their 24 combinations is valid and
    builds."""

    for latch, input_pair, bias in itertools.product(Latch, MosType, Bias):
        params = Params(latch=latch, input_pair=input_pair, bias=bias)
        assert valid(params), params
        netlist.Cache.reset()
        assert netlist(params) is not None


def test_the_search_space_is_declared_on_the_parameters() -> None:
    """Every searched knob carries its domain; the dynamic bias's capacitors are searched only with a
    dynamic bias, and a design that does not use them is canonical at their defaults."""

    domains = pipeline.domains(Params)
    assert {"latch", "input_pair", "bias", "diffpair_w", "tail_l", "preamp_c_ff", "bias_c_ff"} <= set(domains)
    assert not {"output_stage", "rst_l", "srlatch_n_w", "srlatch_p_w", "vth"} & set(domains)
    assert pipeline.bounds(domains["latch_on_l"], "tpsc65") == (1, 1)
    assert pipeline.choices(domains["latch"], Latch, "tsmc65") == tuple(Latch)
    switched = Params(preamp_c_ff=240, bias_c_ff=900)
    assert pipeline.canonical(switched) == Params()
    dynamic = Params(bias=Bias.DYNAMIC, preamp_c_ff=240, bias_c_ff=900)
    assert pipeline.canonical(dynamic) == dynamic


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
    """In every latch, each signaled device pair is driven alike, so none works against another."""

    pairs = {"outer_on": "Mouter_on", "inner_on": "Minner_on", "outer_init": "Mouter_init", "inner_init": "Minner_init"}
    for latch, wiring in LATCHES.items():
        if latch == Latch.TRIPLE_TAIL:
            continue  # its later stages are fixed, its devices driven by the second stage
        netlist.Cache.reset()
        m = netlist(Params(latch=latch))
        for key, device in pairs.items():
            if wiring[key] == State.SIGNAL:
                assert getattr(m, f"{device}_p").conns["g"] is m.input_p_drain, (latch, key)
                assert getattr(m, f"{device}_n").conns["g"] is m.input_n_drain, (latch, key)


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


def test_devices_fit_the_pdk_rows_in_whole_units(tmp_path) -> None:
    """With TSMC65 active, analog devices take an even finger count within the row limit and
    the output stage's gates one count per NMOS/PMOS pair within the logic limits; every
    width written is a whole number of 120 nm units."""

    pdk = pytest.importorskip("pdk.tsmc65.hdl21.pdk_logic")
    from .layout import write_netlist
    from .params import FRIDA1

    limits = pdk.MOS_FINGER_UNITS
    text = write_netlist(FRIDA1, tmp_path / "comp.sp", pdk).read_text()
    devices = {}
    for line in text.splitlines():
        f = line.split()
        if f[0].startswith("M"):
            p = dict(kv.split("=") for kv in f[6:])
            w, nf = int(p["w"].removesuffix("n")), int(p["nf"])
            assert w % (120 * nf) == 0, line
            devices[f[0]] = (f[5][0], w // 120 // nf, nf, f[2])
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

    pdk = pytest.importorskip("pdk.tsmc65.hdl21.pdk_logic")
    cells = pytest.importorskip("pdk.tsmc65.hdl21.stdcells")._LOGIC  # (generic cell, drive) -> library cell
    from .layout import write_netlist
    from .params import FRIDA1, OutputStage

    params = Params(**{**FRIDA1.__dict__, "output_stage": OutputStage.STDCELLS})
    lines = {
        line.split()[0]: line.split() for line in write_netlist(params, tmp_path / "c.sp", pdk).read_text().splitlines()
    }
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
    # active PDK's gate capacitance per unit device makes 240 fF at CAP_L (fingered); without a
    # PDK, a unit device holds 0.1 fF
    import hdl21 as h

    density = getattr(h.pdk.default(), "MOS_CAP_FF", None) or {"n": 0.1, "p": 0.1}
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
