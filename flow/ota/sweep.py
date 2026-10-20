"""The amplifier's design space (``flow.sweep``): the characterization's six cases at seven
sizings, in every PDK.

Each instance on the characterization's bench (``flow.ota.sim``: a 40 µA tail, the cascodes an
eighth of the supply off its middle, 50 fF on each output) at its own supply, the inputs at
mid-supply: the DC gain, unity-gain frequency, phase and gain margin, -3 dB bandwidth, PSRR and
CMRR at ``outp`` at 1 kHz, power, and input-referred noise at 1 MHz and integrated to the
unity-gain frequency, with the gain, phase, noise density and rejections over frequency. Over the
input common mode (1/6 to 5/6 of the supply, nine points) the DC gain, unity-gain frequency and
spot noise, and the span of common modes keeping the gain within 6 dB of its mid-supply value;
over the supply (90 to 120 % of its own) the DC gain, unity-gain frequency and power. The
single-ended cases also in unity gain: a quarter-supply step (slew rates, 1 % settling) and a
tenth-supply sine at 10 MHz (THD); NaN for the differential ones. Twelve to fourteen Spectre runs,
under a minute.
"""

from __future__ import annotations

import importlib
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.sweep import Detail, Record

from .sim import NOMINAL_VCM, SINE, STEP, OtaTbParams, _run_ota_sim, is_large_signal, ota_transient_names
from .subckt import CASES, Ota, OtaParams, Topology, is_valid_ota_params, write_netlist

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = Ota
# the characterization's cases: topology, input type, second stage
TOPOLOGIES = {
    case: {name: getattr(ota, name) for name in ("topology", "input_xtors", "two_stage", "miller")}
    for case, ota in CASES.items()
}
# every width scaled together (x0.5 to x4), the input pair twice as wide or long, and the current
# sources (tail and load) at twice their length
DEFAULT = OtaParams()
WIDTHS = ("in_w", "tail_w", "load_w", "cas_w", "stage2_w")
SIZINGS = {
    "x0.5": {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    "x1": {},
    "x2": {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    "x4": {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    "pair_x2": {"in_w": 2 * DEFAULT.in_w},
    "pair_long": {"in_l": 2 * DEFAULT.in_l},
    "sources_long": {"tail_l": 2 * DEFAULT.tail_l, "load_l": 2 * DEFAULT.load_l},
}
CM_SWEEP = tuple(step / 24 for step in range(4, 21, 2))
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
GAIN_DROP_DB = 6.0  # the common-mode range: the DC gain no further below its mid-supply value


def params(pdk: str, topology: str, sizing: str) -> OtaParams | None:
    ota = OtaParams(**TOPOLOGIES[topology], **SIZINGS[sizing])
    return ota if is_valid_ota_params(ota) else None


def _bench(pdk: str, ota: OtaParams, vdd: float, vcm: float, **large) -> OtaTbParams:
    """The characterization's bench at ``vdd`` and input common mode ``vcm``: the output common
    mode at mid-supply, the cascodes an eighth of the supply off its middle."""

    return OtaTbParams(
        pdk=pdk,
        ota=ota,
        vdd=round(vdd, 4),
        vcm=round(vcm, 4),
        vocm=round(vdd / 2, 4),
        vcasn=round(5 * vdd / 8, 4),
        vcasp=round(3 * vdd / 8, 4),
        **large,
    )


def _measure(run_dir: Path, tb: OtaTbParams):
    """One Spectre run of the bench as ``ota_characterization`` converts it: a ``MeasOta``, or for
    a step or a sine a ``MeasOtaTran``."""

    from vlsirtools.spice.spectre import parse_psfascii

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasOta, MeasOtaTran

    raw = _run_ota_sim(run_dir, tb)
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"pdk": tb.pdk, "raw_file": raw.name, "supply_current_convention": "positive_current_draw"},
    )
    common = {"group": None, "index": None, "dut": tb.ota, "info": info, "param": tb}
    if is_large_signal(tb):
        interval = tb.waveform_sample_interval_s
        wave, points = read_transient_wave(raw, ota_transient_names(tb), interval, supply_rails=("vdd",))
        raw.unlink()  # the measurement keeps the waveforms
        info.readbacks.update({"waveform_sample_interval_s": interval, "raw_points": points})
        return MeasOtaTran(**common, trial_index=np.arange(1, dtype=np.int64), wave=wave)
    analyses = parse_psfascii(raw)
    shutil.rmtree(raw)  # PSF ASCII: a directory of every analysis, read
    op, ac, noise, xf = (analyses[key].data for key in ("op", "ac", "noise", "xf"))
    single = tb.ota.topology in (Topology.FIVE_T, Topology.SELF_BIASED)
    # the differential response to the 1 V differential stimulus; at outp each source's transfer
    response = np.asarray(ac["xtop.outp"]) - (0.0 if single else np.asarray(ac["xtop.outn"]))
    to_inp, to_inn = np.asarray(xf["xtop.vinp"]), np.asarray(xf["xtop.vinn"])
    info.readbacks.update(
        {
            "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
            "op_outp_v": float(np.real(op["xtop.outp"][0])),
            **({} if single else {"op_outn_v": float(np.real(op["xtop.outn"][0]))}),
            "op_vbp_v": float(np.real(op["xtop.vbp"][0])),
        }
    )
    return MeasOta(
        **common,
        frequency_hz=np.real(np.asarray(ac["freq"])).astype(np.float64),
        gain_v_per_v=np.abs(response).astype(np.float64),
        phase_deg=np.degrees(np.unwrap(np.angle(response))).astype(np.float64),
        output_noise_v_rthz=np.asarray(noise["out"], dtype=np.float64),
        outp_gain_v_per_v=np.abs((to_inp - to_inn) / 2).astype(np.float64),
        common_mode_gain_v_per_v=np.abs(to_inp + to_inn).astype(np.float64),
        supply_gain_v_per_v=np.abs(np.asarray(xf["xtop.vvdd"])).astype(np.float64),
    )


def _span(within: np.ndarray, center: int) -> tuple[int, int]:
    """The run of true entries about ``center``: its first and last index."""

    low = high = center
    while low > 0 and within[low - 1]:
        low -= 1
    while high < len(within) - 1 and within[high + 1]:
        high += 1
    return low, high


def characterize(run_dir: Path, pdk: str, ota: OtaParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_ota_ac, analyze_ota_distortion, analyze_ota_noise, analyze_ota_slew

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    # the common-mode points, then the supply's but its 100 %, the mid-supply common-mode point
    measurements = {
        ("cm", fraction): _measure(run_dir / f"cm{round(fraction * 24)}", _bench(pdk, ota, supply, fraction * supply))
        for fraction in CM_SWEEP
    }
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            vdd = factor * supply
            measurements["supply", factor] = _measure(
                run_dir / f"supply_{round(factor * 100)}", _bench(pdk, ota, vdd, NOMINAL_VCM * vdd)
            )
    ac = analyze_ota_ac(list(measurements.values()))
    noise = analyze_ota_noise(list(measurements.values()), ac=ac)
    row = {key: index for index, key in enumerate(measurements)}
    nominal = row["cm", NOMINAL_VCM]
    cm_rows = [row["cm", fraction] for fraction in CM_SWEEP]
    supply_rows = [row.get(("supply", factor), nominal) for factor in SUPPLY_SWEEP]

    gains = ac.dc_gain_db[cm_rows]
    within = gains >= ac.dc_gain_db[nominal] - GAIN_DROP_DB  # NaN: outside
    low, high = _span(within, CM_SWEEP.index(NOMINAL_VCM))
    cm_range = (CM_SWEEP[high] - CM_SWEEP[low]) * supply if within[CM_SWEEP.index(NOMINAL_VCM)] else math.nan
    supply_gains = ac.dc_gain_db[supply_rows]

    # unity gain, single-ended only: a differential output would need a common-mode feedback circuit
    waves, slew, distortion = {}, None, None
    if ota.topology in (Topology.FIVE_T, Topology.SELF_BIASED):
        mid = NOMINAL_VCM * supply
        step = _measure(run_dir / "step", _bench(pdk, ota, supply, mid, step_v=round(STEP * supply, 4)))
        sine = _measure(
            run_dir / "sine",
            _bench(pdk, ota, supply, mid, sine_v=round(SINE * supply, 4), waveform_sample_interval_s=100e-12),
        )
        for name, folder, measurement in (("unity-gain step", "step", step), ("unity-gain sine", "sine", sine)):
            path = run_dir / folder / "result.h5"
            write_measurement(path, measurement)
            waves[name] = str(path.relative_to(ROOT))
        slew, distortion = analyze_ota_slew([step]), analyze_ota_distortion([sine])

    frequency = ac.frequency_hz.tolist()
    cm_v = [fraction * supply for fraction in CM_SWEEP]
    return Record(
        metrics={
            "dc_gain_db": float(ac.dc_gain_db[nominal]),
            "ugbw_hz": float(ac.ugbw_hz[nominal]),
            "phase_margin_deg": float(ac.phase_margin_deg[nominal]),
            "gain_margin_db": float(ac.gain_margin_db[nominal]),
            "bandwidth_hz": float(ac.bandwidth_hz[nominal]),
            "psrr_db": float(ac.low_psrr_db[nominal]),
            "cmrr_db": float(ac.low_cmrr_db[nominal]),
            "power_w": float(ac.power_w[nominal]),
            "output_cm_v": float(ac.output_cm_v[nominal]),
            "noise_1mhz_v_rthz": float(noise.spot_noise_v_rthz[nominal]),
            "noise_rms_v": float(noise.integrated_noise_v[nominal]),
            "cm_range_v": cm_range,
            "dc_gain_min_supply_db": float(np.min(supply_gains)),  # NaN where a point lost its output
            "slew_rise_v_per_s": float(slew.rise_slew_v_per_s[0]) if slew else math.nan,
            "slew_fall_v_per_s": float(-slew.fall_slew_v_per_s[0]) if slew else math.nan,
            "settling_s": float(np.max([slew.rise_settling_s[0], slew.fall_settling_s[0]])) if slew else math.nan,
            "thd_db": float(distortion.thd_db[0]) if distortion else math.nan,
        },
        details=[
            Detail(
                name="gain",
                title="Gain over frequency (mid-supply input)",
                x_label="Frequency (Hz)",
                y_label="Gain (dB)",
                x=frequency,
                series={"gain": ac.gain_db[nominal].tolist()},
                x_log=True,
            ),
            Detail(
                name="phase",
                title="Phase over frequency (mid-supply input)",
                x_label="Frequency (Hz)",
                y_label="Phase (deg)",
                x=frequency,
                series={"phase": ac.phase_deg[nominal].tolist()},
                x_log=True,
            ),
            Detail(
                name="noise_density",
                title="Input-referred noise density (mid-supply input)",
                x_label="Frequency (Hz)",
                y_label="Noise (V/√Hz)",
                x=frequency,
                series={"noise": noise.input_noise_v_rthz[nominal].tolist()},
                x_log=True,
                y_log=True,
            ),
            Detail(
                name="rejection",
                title="Supply and common-mode rejection at outp",
                x_label="Frequency (Hz)",
                y_label="Rejection (dB)",
                x=frequency,
                series={"PSRR": ac.psrr_db[nominal].tolist(), "CMRR": ac.cmrr_db[nominal].tolist()},
                x_log=True,
            ),
            Detail(
                name="gain_cm",
                title="DC gain over the input common mode",
                x_label="Input common mode (V)",
                y_label="DC gain (dB)",
                x=cm_v,
                series={"DC gain": gains.tolist()},
            ),
            Detail(
                name="ugbw_cm",
                title="Unity-gain frequency over the input common mode",
                x_label="Input common mode (V)",
                y_label="Unity-gain frequency (Hz)",
                x=cm_v,
                series={"unity-gain frequency": ac.ugbw_hz[cm_rows].tolist()},
                y_log=True,
            ),
            Detail(
                name="noise_cm",
                title="Input-referred noise at 1 MHz over the input common mode",
                x_label="Input common mode (V)",
                y_label="Noise (V/√Hz)",
                x=cm_v,
                series={"1 MHz": noise.spot_noise_v_rthz[cm_rows].tolist()},
                y_log=True,
            ),
            Detail(
                name="gain_supply",
                title="DC gain over the supply",
                x_label="Supply over nominal",
                y_label="DC gain (dB)",
                x=list(SUPPLY_SWEEP),
                series={"DC gain": supply_gains.tolist()},
            ),
            Detail(
                name="ugbw_supply",
                title="Unity-gain frequency over the supply",
                x_label="Supply over nominal",
                y_label="Unity-gain frequency (Hz)",
                x=list(SUPPLY_SWEEP),
                series={"unity-gain frequency": ac.ugbw_hz[supply_rows].tolist()},
                y_log=True,
            ),
            Detail(
                name="power_supply",
                title="Power over the supply",
                x_label="Supply over nominal",
                y_label="Power (W)",
                x=list(SUPPLY_SWEEP),
                series={"power": ac.power_w[supply_rows].tolist()},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, ota: OtaParams) -> Path:
    """The transistor netlist ``flow.ota.layout`` places, with the PDK's library cells it contains
    recognized (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(ota, out_dir / "ota_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "ota.sp")
