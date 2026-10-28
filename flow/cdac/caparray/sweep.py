"""The capacitor array's design space (``flow.sweep``): the characterization's five arrays at six
unit capacitances, in every PDK.

Each instance as the characterization runs it (``flow.cdac.caparray.sim``): every stage's main bottom
plate driven by a code's bit and its difference plate by the complement, into 100 fF on the top
plate, at the PDK's own supply. Each stage toggled alone after an all-zero code (its weight on the
top plate) and the packed ramp over the DAC resolution's codes (the transfer and its error against
the design weights, in unit capacitors). The leaf is the MOM capacitor's ideal view, so a PDK
changes only the supply: the unit capacitance against the fixed load sets the top plate's swing.
Two Spectre runs, a few seconds.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.prefix import f

from flow.pipeline import Plot, Record

from .sim import CASES, CapArrayTbParams, _run_caparray_sim, caparray_measurement
from .subckt import CapArray, CapArrayParams, get_caparray_weights, is_valid_caparray_params

GENERATOR = CapArray
# the characterization's arrays (flow.cdac.caparray.sim.CASES): FRIDA-1's two fabricated flavours (MSB
# redistribution, radix 2 on repeated coarse units), 11-bit binary, the MSB and LSB splits with 5
ARRAYS = list(CASES.values())
# the unit capacitor from a quarter to eight times 1 fF, against the 100 fF load
UNIT_CAPS = [scale * f for scale in (0.25, 0.5, 1, 2, 4, 8)]


def instances(pdk: str) -> list[CapArrayParams]:
    """Every array at every unit capacitor, in every PDK."""
    arrays = (CapArrayParams(cdac=cdac, unit_cap=unit_cap) for cdac in ARRAYS for unit_cap in UNIT_CAPS)
    return [array for array in arrays if is_valid_caparray_params(array)]


def characterize(run_dir: Path, pdk: str, array: CapArrayParams) -> Record:
    from flow.analysis.io import write_measurement
    from flow.cdac.caparray.analysis import analyze_caparray_transfer, analyze_caparray_weights

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    cdac = array.cdac
    n_stages = len(get_caparray_weights(cdac))
    timing = {"pdk": pdk, "vdd": supply, "cdac": cdac, "unit_cap": array.unit_cap, "transition_time_s": 50e-12}
    benches = {
        # stage s is the packed code's bit n_stages - 1 - s; zero before each
        "stage": CapArrayTbParams(
            codes=tuple(code for stage in range(n_stages) for code in (0, 1 << (n_stages - 1 - stage))),
            code_dwell_s=2e-9,
            waveform_sample_interval_s=10e-12,
            **timing,
        ),
        "ramp": CapArrayTbParams(code_dwell_s=1e-9, waveform_sample_interval_s=50e-12, **timing),
    }
    measurements, waves = {}, {}
    for sweep, tb in benches.items():
        raw = _run_caparray_sim(run_dir / sweep, tb)
        measurements[sweep] = caparray_measurement(raw, tb, {"pdk": pdk, "case": run_dir.name, "sweep": sweep})
        raw.unlink()  # the measurement keeps the top plate
        path = run_dir / sweep / "result.h5"
        write_measurement(path, measurements[sweep])
        waves[{"stage": "each stage alone", "ramp": "code ramp"}[sweep]] = str(
            path.relative_to(Path(__file__).resolve().parents[3])
        )

    weights = analyze_caparray_weights(measurements["stage"])
    transfer = analyze_caparray_transfer(measurements["ramp"])
    # the array's own capacitance on its top plate: every finger of the ideal view
    capacitance = sum(float(unit.of.instances["cap"].of.params.c) for unit in CapArray(array).instances.values())
    stage = list(range(n_stages))
    return Record(
        metrics={
            "c_array_f": capacitance,
            "top_plate_swing_v": weights.total_fraction * supply,
            "attenuation_db": float(-20 * np.log10(weights.total_fraction)),
            "unit_step_v": transfer.volts_per_unit,
            "weight_error_max_pct": float(np.max(np.abs(weights.weight_error))) * 100,
            "ramp_error_max_lsb": float(np.max(np.abs(transfer.error_units))),
        },
        details=[
            Plot(
                name="stage_weights",
                title="Stage weights, each stage toggled alone",
                x_label="Stage (C0 first)",
                y_label="Weight (unit capacitors)",
                x=stage,
                series={
                    "design": list(weights.design_weight),
                    "measured": list(weights.fraction * np.sum(weights.design_weight) / weights.total_fraction),
                },
                y_log=True,
            ),
            Plot(
                name="weight_error",
                title="Stage weight error against the design",
                x_label="Stage (C0 first)",
                y_label="Weight error (%)",
                x=stage,
                series={"error": list(weights.weight_error * 100)},
            ),
            Plot(
                name="transfer",
                title="Top plate over the packed code ramp",
                x_label="Code",
                y_label="Top plate (V)",
                x=list(transfer.code),
                series={"top plate": list(transfer.voltage_v)},
            ),
            Plot(
                name="ramp_error",
                title="Ramp error against the design weights",
                x_label="Code",
                y_label="Error (unit capacitors)",
                x=list(transfer.code),
                series={"error": list(transfer.error_units)},
            ),
        ],
        waves=waves,
    )
