"""Software-only tests for reading a saved transient (``flow.circuit.results``); the ADC's decode of
it is ``flow.adc.sim``'s (``flow/adc/test_sim.py``)."""

import numpy as np
from vlsirtools.spice.sim_data import TranResult


def test_raw_step_validation_accepts_spectre_strobe_jitter_but_rejects_coarser_data():
    from flow.circuit.results import _is_valid_transient

    # Observed adjacent timestamps from a 10 ps Spectre strobe-only run.
    times = np.array([3.164999925451418e-8, 3.166000000000151e-8])
    names = {"time": "time", "raw": "vin_p"}
    result = TranResult("tran", {"time": times, "raw": np.zeros(2)}, {})
    assert _is_valid_transient(result, names, 10e-12)
    result = TranResult("tran", {"time": np.array([0.0, 10.1e-12]), "raw": np.zeros(2)}, {})
    assert not _is_valid_transient(result, names, 10e-12)


def test_current_polarity_only_changes_for_selected_supply_sources():
    from flow.circuit.results import conversion_inputs

    result = TranResult(
        "tran",
        {
            "time": np.array([0.0, 1e-12]),
            "supply:p": np.array([-2e-6, -3e-6]),
            "device:d": np.array([4e-6, -5e-6]),
        },
        {},
    )
    names = {"time": "time", "supply:p": "i(vdd)", "device:d": "i(device)"}
    _, _, currents = conversion_inputs(result, names, 1e-12, supply_rails=("vdd",))
    np.testing.assert_allclose(currents["vdd"], [2e-6, 3e-6])
    np.testing.assert_allclose(currents["device"], [4e-6, -5e-6])
