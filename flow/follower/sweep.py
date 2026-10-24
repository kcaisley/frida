"""The followers' design space (``flow.sweep``): the characterization's four followers at eight
sizings (a source follower has no shunt device to size: seven), in every PDK.

Each instance at its nominal input (where the characterization's follower follows in most PDKs:
an NMOS source follower 3/4 up the supply, a PMOS one 1/4, the flipped ones 1/2 and 1/4): the
output level, small-signal gain, bandwidth, PSRR, supply current and output impedance, the input
range where the gain stays within 10 % of it, and from a step of a quarter of the supply up and
back down the slew rates, settling and overshoot. The bias current scales with the current
source's width (20 uA at each follower's own). Over the input level (the supply in twelfths)
the output, gain, bandwidth, output impedance and PSRR; at the nominal input the response and
the impedance over frequency; over the supply (90 to 120 % of its own) the gain, bandwidth and
PSRR. Thirty Spectre runs, one to two minutes in all.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import NOMINAL_VIN, STEP, FollowerTbParams, _run_follower_sim, follower_signal_names
from .subckt import CASES, Follower, FollowerParams, Topology, is_valid_follower_params, write_netlist

GENERATOR = Follower
# the characterization's followers (flow.follower.subckt.CASES) at their own input and source widths
STRUCTURE = ("topology", "input_xtors", "sink")
CASE_SIZES = ("in_w", "bias_w")
# factors of each follower's own sizes: its widths scaled together (x0.5 to x4), the input or
# the shunt device alone doubled, the input device or the current source at twice its length
WIDTHS = ("in_w", "bias_w", "fb_w")
FACTORS = [
    dict.fromkeys(WIDTHS, 0.5),
    {},
    dict.fromkeys(WIDTHS, 2),
    dict.fromkeys(WIDTHS, 4),
    {"in_w": 2},
    {"fb_w": 2},
    {"in_l": 2},
    {"bias_l": 2},
]
NOMINAL_BIAS_A = FollowerTbParams().bias_current_a
VIN_SWEEP = tuple(range(13))  # twelfths of the supply
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)


def scaled(case: FollowerParams, factors: dict[str, float]) -> FollowerParams | None:
    """The case's follower with its sizes scaled by ``factors`` (a source follower has no shunt
    device to size); None where nothing it has is scaled (its base sizes again)."""
    if case.topology == Topology.SOURCE:
        kept = {name: factor for name, factor in factors.items() if name != "fb_w"}
        if factors and not kept:
            return None
        factors = kept
    sizes = {name: max(1, round(getattr(case, name) * factor)) for name, factor in factors.items()}
    return FollowerParams(**{**{name: getattr(case, name) for name in (*STRUCTURE, *CASE_SIZES)}, **sizes})


def instances(pdk: str) -> list[FollowerParams]:
    """Every follower at every scaling, in every PDK."""
    followers = (scaled(case, factors) for case in CASES.values() for factors in FACTORS)
    return [follower for follower in followers if follower is not None and is_valid_follower_params(follower)]


def _case(follower: FollowerParams) -> str:
    """The characterization's follower of the same topology."""
    key = (follower.topology, follower.input_xtors, follower.sink)
    return next(name for name, case in CASES.items() if (case.topology, case.input_xtors, case.sink) == key)


def _info(raw: Path, readbacks: dict):
    from flow.analysis.types import MeasInfo

    return MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={**readbacks, "supply_current_convention": "positive_current_draw"},
    )


def _measure_ac(run_dir: Path, tb: FollowerTbParams):
    """One operating point, AC response and supply transfer of the follower testbench, as a
    measurement (``flow.follower.sim.follower_characterization``'s)."""

    from vlsirtools.spice.spectre import parse_nutbin

    from .analysis import MeasFollower

    raw = _run_follower_sim(run_dir, tb)
    with raw.open("rb") as stream:
        analyses = parse_nutbin(stream)
    op, ac, xf = analyses["op"].data, analyses["ac"].data, analyses["xf"].data
    # the output per volt of input; or the output impedance, from the divider of the test
    # resistance and the impedance that the 1 V test stimulus drives
    response = np.asarray(ac["xtop.vout"])
    if tb.output_test:
        response = response * tb.test_resistance_ohm / (1 - response)
    info = _info(
        raw,
        {
            "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
            "op_vout_v": float(np.real(op["xtop.vout"][0])),
        },
    )
    raw.unlink()
    return MeasFollower(
        group=None,
        index=None,
        dut=tb.follower,
        info=info,
        param=tb,
        frequency_hz=np.real(np.asarray(ac["freq"])).astype(np.float64),
        magnitude=np.abs(response).astype(np.float64),
        phase_deg=np.degrees(np.unwrap(np.angle(response))).astype(np.float64),
        supply_gain_v_per_v=np.abs(np.asarray(xf["xtop.vvdd"])).astype(np.float64),
    )


def _measure_step(run_dir: Path, tb: FollowerTbParams):
    """One transient of the follower's step bench, as a measurement."""

    from flow.circuit.results import read_transient_wave

    from .analysis import MeasFollowerStep

    names = {"time": "time", **{raw: name for raw, name in follower_signal_names().items() if raw != "freq"}}
    raw = _run_follower_sim(run_dir, tb)
    wave, points = read_transient_wave(raw, names, tb.waveform_sample_interval_s, supply_rails=("vdd",))
    info = _info(raw, {"raw_points": points})
    raw.unlink()  # the measurement keeps the waveforms
    return MeasFollowerStep(
        group=None,
        index=None,
        dut=tb.follower,
        info=info,
        param=tb,
        trial_index=np.arange(1, dtype=np.int64),
        wave=wave,
    )


def characterize(run_dir: Path, pdk: str, follower: FollowerParams) -> Record:
    from flow.analysis import calc
    from flow.analysis.io import write_measurement

    from .analysis import analyze_follower_impedance, analyze_follower_slew, analyze_follower_transfer

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    case = _case(follower)
    nominal_vin = NOMINAL_VIN[case]
    bias = NOMINAL_BIAS_A * follower.bias_w / CASES[case].bias_w

    def bench(vdd: float, vin: float, **stimulus) -> FollowerTbParams:
        return FollowerTbParams(
            pdk=pdk, follower=follower, vdd=round(vdd, 4), vin=round(vin, 4), bias_current_a=bias, **stimulus
        )

    inputs = {k: _measure_ac(run_dir / f"input_vin{k}of12", bench(supply, k / 12 * supply)) for k in VIN_SWEEP}
    outputs = {
        k: _measure_ac(run_dir / f"output_vin{k}of12", bench(supply, k / 12 * supply, output_test=True))
        for k in VIN_SWEEP
    }
    k = round(nominal_vin * 12)
    supplies = {
        factor: inputs[k]
        if factor == 1.0
        else _measure_ac(
            run_dir / f"supply_{round(factor * 100)}", bench(factor * supply, nominal_vin * factor * supply)
        )
        for factor in SUPPLY_SWEEP
    }
    step = _measure_step(run_dir / "step", bench(supply, nominal_vin * supply, step_v=round(STEP * supply, 4)))
    path = write_measurement(run_dir / "step" / "result.h5", step)
    waves = {"step": str(path.relative_to(Path(__file__).resolve().parents[2]))}
    transfer = analyze_follower_transfer(list(inputs.values()))
    impedance = analyze_follower_impedance(list(outputs.values()))
    over_supply = analyze_follower_transfer(list(supplies.values()))
    slew = analyze_follower_slew([step])
    low, high = calc.compliance_range(transfer.gain_v_per_v, transfer.vin_v, transfer.vin_v[k], 0.1)
    vin_v = list(transfer.vin_v)
    frequency = list(transfer.frequency_hz)

    return Record(
        metrics={
            "vout_v": float(transfer.vout_v[k]),
            "level_shift_v": float(transfer.level_shift_v[k]),
            "gain_v_per_v": float(transfer.gain_v_per_v[k]),
            "bandwidth_hz": float(transfer.bandwidth_hz[k]),
            "psrr_db": float(transfer.psrr_db[k]),
            "supply_current_a": float(transfer.supply_current_a[k]),
            "output_impedance_ohm": float(impedance.impedance_ohm[k]),
            "input_range_v": high - low,
            "rise_slew_v_per_s": float(slew.rise_slew_v_per_s[0]),
            "fall_slew_v_per_s": float(slew.fall_slew_v_per_s[0]),
            "rise_settling_s": float(slew.rise_settling_s[0]),
            "fall_settling_s": float(slew.fall_settling_s[0]),
            "rise_overshoot": float(slew.rise_overshoot[0]),
            "fall_overshoot": float(slew.fall_overshoot[0]),
            "bandwidth_min_supply_hz": float(np.min(over_supply.bandwidth_hz)),
        },
        details=[
            Plot(
                name="vout_vin",
                title="Output level over the input",
                x_label="Input (V)",
                y_label="Output (V)",
                x=vin_v,
                series={"output": list(transfer.vout_v)},
            ),
            Plot(
                name="gain_vin",
                title="Small-signal gain over the input",
                x_label="Input (V)",
                y_label="Gain (V/V)",
                x=vin_v,
                series={"gain": list(transfer.gain_v_per_v)},
            ),
            Plot(
                name="bandwidth_vin",
                title="-3 dB bandwidth over the input",
                x_label="Input (V)",
                y_label="Bandwidth (Hz)",
                x=vin_v,
                series={"bandwidth": list(transfer.bandwidth_hz)},
                y_log=True,
            ),
            Plot(
                name="impedance_vin",
                title="Output impedance over the input",
                x_label="Input (V)",
                y_label="Output impedance (ohm)",
                x=vin_v,
                series={"impedance": list(impedance.impedance_ohm)},
                y_log=True,
            ),
            Plot(
                name="psrr_vin",
                title="PSRR over the input",
                x_label="Input (V)",
                y_label="PSRR (dB)",
                x=vin_v,
                series={"PSRR": list(transfer.psrr_db)},
            ),
            Plot(
                name="response",
                title="Response over frequency at the nominal input",
                x_label="Frequency (Hz)",
                y_label="Gain (dB)",
                x=frequency,
                series={"gain": list(transfer.response_db[k])},
                x_log=True,
            ),
            Plot(
                name="impedance_frequency",
                title="Output impedance over frequency at the nominal input",
                x_label="Frequency (Hz)",
                y_label="Output impedance (dB ohm)",
                x=frequency,
                series={"impedance": list(impedance.impedance_db_ohm[k])},
                x_log=True,
            ),
            Plot(
                name="gain_supply",
                title="Gain over the supply (the input at its share of it)",
                x_label="Supply over nominal",
                y_label="Gain (V/V)",
                x=list(SUPPLY_SWEEP),
                series={"gain": list(over_supply.gain_v_per_v)},
            ),
            Plot(
                name="bandwidth_supply",
                title="-3 dB bandwidth over the supply",
                x_label="Supply over nominal",
                y_label="Bandwidth (Hz)",
                x=list(SUPPLY_SWEEP),
                series={"bandwidth": list(over_supply.bandwidth_hz)},
                y_log=True,
            ),
            Plot(
                name="psrr_supply",
                title="PSRR over the supply",
                x_label="Supply over nominal",
                y_label="PSRR (dB)",
                x=list(SUPPLY_SWEEP),
                series={"PSRR": list(over_supply.psrr_db)},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, follower: FollowerParams) -> Path:
    """The transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(follower, out_dir / "follower_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "follower.sp")
