"""Software-only tests of the CDAC testbench: each stage up and back down in its turn."""

import io

import hdl21 as h
import pytest

from flow import cdac

from .test_subckt import PARAMS


def test_the_testbench_switches_each_stage_up_and_back_in_its_turn():
    tb = cdac.TbParams(params=PARAMS, window_s=2e-9, waveform_sample_interval_s=1e-12)
    bench = cdac.testbench(tb)
    assert tb.stop_s == pytest.approx(7 * 2e-9)
    for stage in range(3):
        up, down = tb.window_start_s(stage, True), tb.window_start_s(stage, False)
        assert down - up == pytest.approx(tb.window_s)
        p, n = bench.instances[f"vstate_p_{stage}"].of.params, bench.instances[f"vstate_n_{stage}"].of.params
        assert float(p.delay) == float(n.delay) == pytest.approx(up)
        assert (float(p.v1), float(p.v2), float(n.v1), float(n.v2)) == (0.0, 1.2, 1.2, 0.0)
        # high for one window, rise and width together
        assert float(p.width) + float(p.rise) == pytest.approx(tb.window_s)
    dest = io.StringIO()
    h.netlist(bench, dest, fmt="spice")
    netlist = dest.getvalue()
    # the nets a run saves, a bit a stage where they have one, are the testbench's
    for name in (
        "vdac_p",
        "vdac_n",
        *(f"{bus}_{stage}" for stage in range(3) for bus in ("dac_state_p", "dac_botplate_p")),
    ):
        assert name in netlist


def test_a_window_too_short_for_its_edges_is_refused():
    with pytest.raises(ValueError):
        cdac.TbParams(params=PARAMS, window_s=100e-12, waveform_sample_interval_s=1e-12)
    with pytest.raises(ValueError):
        cdac.TbParams(params=PARAMS, window_s=2e-9, waveform_sample_interval_s=0.0)
