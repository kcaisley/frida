"""Software-only structural tests for the comparator subcircuit generator."""

import pytest
from hdl21.primitives import MosType

from .subckt import Bias, Comp, CompParams, Stages, State, _fingers


def test_comp():
    """Verify comparator generator produces a valid module."""
    m = Comp(CompParams())
    assert m is not None


def test_default_comp_is_single_tail_nmos_strongarm() -> None:
    """Pin the default topology and its power-of-two size multipliers."""

    Comp.Cache.reset()
    params = CompParams()
    assert params.comp_stages == Stages.SINGLE
    assert params.preamp_diff_xtors == MosType.NMOS
    assert params.preamp_bias == Bias.SWITCHED
    assert params.latch_inner_init_xtors == State.CLOCK
    assert params.latch_inner_on_xtors == State.OMIT
    assert params.latch_outer_init_xtors == State.OMIT
    assert params.latch_outer_on_xtors == State.OMIT
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

    module = Comp(params)
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


def test_comp_output_srlatch_handles_both_reset_polarities() -> None:
    """Build the NOR and NAND variants of the held comparator output."""

    nor = Comp(CompParams())
    assert nor.Msr_p_p_decision.conns["d"] is nor.sr_p_stack
    assert nor.Msr_p_n_decision.conns["s"] is nor.vss
    assert nor.Msr_p_n_decision.conns["g"] is nor.decision_n
    assert nor.Msr_n_n_decision.conns["g"] is nor.decision_p
    assert nor.Mbuf2_outp_p.conns["d"] is nor.outp
    assert nor.Mbuf2_outn_p.conns["d"] is nor.outn

    # latch_p rising pulls decision_n low, which must set sr_p (outp high for inp > inn)
    nand = Comp(CompParams(preamp_diff_xtors=MosType.PMOS))
    assert nand.Msr_p_p_decision.conns["d"] is nand.sr_p
    assert nand.Msr_p_n_decision.conns["s"] is nand.sr_p_stack
    assert nand.Msr_p_p_decision.conns["g"] is nand.decision_n
    assert nand.Msr_p_n_decision.conns["g"] is nand.decision_n
    assert nand.Msr_n_n_decision.conns["g"] is nand.decision_p


def test_signaled_latch_devices_take_the_opposite_input_drain() -> None:
    """All four signaled pairs are driven alike, so none of them works against another."""

    Comp.Cache.reset()
    m = Comp(
        CompParams(
            comp_stages=Stages.DOUBLE,
            latch_inner_on_xtors=State.SIGNAL,
            latch_outer_on_xtors=State.SIGNAL,
            latch_inner_init_xtors=State.SIGNAL,
            latch_outer_init_xtors=State.SIGNAL,
        )
    )
    for device in ("Minner_on", "Mouter_on", "Minner_init", "Mouter_init"):
        assert getattr(m, f"{device}_p").conns["g"] is m.input_p_drain
        assert getattr(m, f"{device}_n").conns["g"] is m.input_n_drain


def test_double_tail_shares_one_clocked_tail() -> None:
    """The double tail's second stage: one clocked tail under both cross-coupled halves."""

    Comp.Cache.reset()
    params = CompParams(
        comp_stages=Stages.DOUBLE,
        latch_inner_init_xtors=State.SIGNAL,
        latch_outer_on_xtors=State.CLOCK,
        latch_tail_shared=True,
    )
    m = Comp(params)
    assert m.Mcross_on_p.conns["s"] is m.outer and m.Mcross_on_n.conns["s"] is m.outer
    assert m.Mouter_on.conns["g"] is m.clkb and m.Mouter_on.conns["s"] is m.vdd
    assert float(m.Mouter_on.of.params.w) == _fingers(2 * params.latch_on_w, "analog")[0]
    assert not hasattr(m, "Mouter_on_p") and not hasattr(m, "outerp")
    with pytest.raises(ValueError):
        Comp(
            CompParams(
                comp_stages=Stages.DOUBLE,
                latch_inner_init_xtors=State.SIGNAL,
                latch_outer_on_xtors=State.SIGNAL,
                latch_tail_shared=True,
            )
        )


def test_triple_tail_stages() -> None:
    """Cascoded preamp, PMOS-latch second stage on midp/midn, clocked-tail third stage."""

    Comp.Cache.reset()
    m = Comp(CompParams(comp_stages=Stages.TRIPLE))
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
    params = CompParams()
    assert float(m.Minner_init_p.of.params.w) == _fingers(4 * params.rst_w, "analog")[0]
    assert float(m.Mtail3.of.params.w) == _fingers(params.latch_on_w, "analog")[0]
    # the third stage precharges high like a StrongARM: NOR output latch
    assert m.Msr_p_p_decision.conns["d"] is m.sr_p_stack
    with pytest.raises(ValueError):
        Comp(CompParams(comp_stages=Stages.TRIPLE, latch_inner_init_xtors=State.SIGNAL))


def test_devices_fit_the_pdk_rows_in_whole_units(tmp_path) -> None:
    """With TSMC65 active, analog devices take an even finger count within the row limit and
    the output stage's gates one count per NMOS/PMOS pair within the logic limits; every
    width written is a whole number of 120 nm units."""

    pdk = pytest.importorskip("pdk.tsmc65.hdl21.pdk_logic")
    from .subckt import FRIDA1, write_netlist

    limits = pdk.MOS_FINGER_UNITS
    netlist = write_netlist(FRIDA1, tmp_path / "comp.sp", pdk).read_text()
    devices = {}
    for line in netlist.splitlines():
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
    from .subckt import FRIDA1, OutputStage, write_netlist

    params = CompParams(**{**FRIDA1.__dict__, "output_stage": OutputStage.STDCELLS})
    lines = {
        line.split()[0]: line.split() for line in write_netlist(params, tmp_path / "c.sp", pdk).read_text().splitlines()
    }
    assert lines["Xdecision_p"][1:] == ["latch_n", "decision_p", "vdd", "vss", cells["inverter", 1].name]
    assert lines["Xsr_p"][1:] == ["decision_n", "sr_n", "sr_p", "vdd", "vss", cells["nor2", 2].name]
    assert lines["Xbuf2_outn"][-1] == cells["inverter", 8].name
    assert not any(name.startswith(("Mdecision", "Msr", "Mbuf")) for name in lines)
