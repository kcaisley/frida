"""Software-only checks for the native HDL21 CDAC interface."""

import inspect

import hdl21 as h
import pytest

from . import sim


def test_cdac_testbench_uses_typed_timing() -> None:
    params = sim.CdacTbParams(code_dwell_s=250e-9, transition_time_s=50e-12)
    tb = sim.CdacTb(params)

    assert isinstance(tb, h.Module)
    assert tb.dac_bits.width == params.cdac.n_dac + params.cdac.n_extra
    assert float(tb.vdac_0.of.params.wave.points[1][0]) == pytest.approx(250e-9)
    assert not hasattr(params, "temperature_c")


def test_cdac_main_owns_check_and_transient_targets() -> None:
    source = inspect.getsource(sim.main)
    assert "frida65_baseline_check" in source
    assert "frida65_baseline_transient" in source
    assert "TARGETS" not in vars(sim)
