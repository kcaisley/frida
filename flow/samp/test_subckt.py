"""Software-only tests for the sampler subcircuit generator."""

from .subckt import Samp, SampParams, SwitchType


def test_samp():
    """Use the FRIDA-like complementary switch and power-of-two sizing."""
    params = SampParams()
    m = Samp(params)
    assert m is not None
    assert hasattr(m, "din")
    assert hasattr(m, "dout")
    assert params.switch_type is SwitchType.TGATE
    assert params.mos_w == 32
    assert m.MN.of.params.w == 32
    assert m.MP.of.params.w == 32
    assert m.MN.conns == {"d": m.dout, "g": m.clk, "s": m.din, "b": m.vss}
    assert m.MP.conns == {"d": m.dout, "g": m.clk_b, "s": m.din, "b": m.vdd}
