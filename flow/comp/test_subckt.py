"""Software-only structural tests for the comparator subcircuit generator."""

from hdl21.primitives import MosType

from .subckt import Bias, Comp, CompParams, Stages, State


def test_comp():
    """Verify comparator generator produces a valid module."""
    m = Comp(CompParams())
    assert m is not None


def test_default_comp_is_single_tail_nmos_strongarm() -> None:
    """Pin the default topology and its power-of-two size multipliers."""

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

    nand = Comp(CompParams(preamp_diff_xtors=MosType.PMOS))
    assert nand.Msr_p_p_decision.conns["d"] is nand.sr_p
    assert nand.Msr_p_n_decision.conns["s"] is nand.sr_p_stack
    assert nand.Msr_p_n_decision.conns["g"] is nand.decision_p
    assert nand.Msr_n_n_decision.conns["g"] is nand.decision_n
