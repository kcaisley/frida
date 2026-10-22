"""The MOSFET's design space (``flow.sweep``): every core flavor at six sizes, in every PDK that
has it.

Each instance one device in Spectre as the characterization runs it (``flow.mosfet.sim``): Id-Vgs at
|Vds| of 50 mV and of the supply (threshold, subthreshold swing, on and off current, gm/Id over the
current density), Id-Vds at gate voltages from a third of the supply to all of it (at the bias,
|Vgs| and |Vds| half the supply: the drain current, gm, the output conductance, the intrinsic gain
and the Early voltage; the on-resistance at full drive), the gate-referred noise at the bias from
1 Hz to 10 GHz (white floor, flicker corner, 1 kHz spot), the drain current's transient noise over
10 us against its small-signal density, and a Monte Carlo of mismatch (200 runs: sigma(Vgs) and the
Pelgrom A_VT) where the kit has mismatch statistics (TSMC28, IHP130, Tower180, TPSC65; NaN
elsewhere). Two Spectre runs, under a minute.
"""

from __future__ import annotations

import importlib
import math
import shutil
from functools import cache
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType, MosVth

from flow.sweep import Detail, Record

from .sim import MosfetTbParams, _characterize, readbacks
from .subckt import WIDTH, Mosfet, MosfetParams, flavors

GENERATOR = Mosfet
# the core flavors by type and threshold: each PDK has some of them (``flavors``)
FLAVORS = [
    {"tp": tp, "vth": vth}
    for tp in (MosType.NMOS, MosType.PMOS)
    for vth in (MosVth.ULTRA_LOW, MosVth.LOW, MosVth.STD, MosVth.HIGH)
]
# the characterization's lengths (1 to 8 times the minimum) at its width, and a narrow and a wide
# device at twice the minimum length (no width under 4 units: the finest PDK's minimum width)
SIZES = [
    *({"w": WIDTH, "l": length} for length in (1, 2, 4, 8)),
    {"w": WIDTH // 2, "l": 2},
    {"w": 4 * WIDTH, "l": 2},
]


@cache
def _devices(pdk: str) -> dict[tuple[MosType, MosVth], str]:
    """The PDK's core devices by type and threshold."""
    return {flavor: name for name, flavor in flavors(pdk).items()}


def instances(pdk: str) -> list[MosfetParams]:
    """Every flavor the PDK has at every size."""
    return [
        MosfetParams(**flavor, **sizes)
        for flavor in FLAVORS
        if (flavor["tp"], flavor["vth"]) in _devices(pdk)
        for sizes in SIZES
    ]


def _binned(frequency: np.ndarray, density: np.ndarray, grid: np.ndarray) -> list[float]:
    """A noise density averaged in power over each grid point's tenth of a decade (NaN outside
    its frequencies)."""

    half = 10**0.05
    out = []
    for center in grid:
        inside = (frequency >= center / half) & (frequency < center * half)
        out.append(float(np.sqrt(np.mean(np.square(density[inside])))) if inside.any() else math.nan)
    return out


def characterize(run_dir: Path, pdk: str, mosfet: MosfetParams) -> Record:
    from flow.analysis.io import read_measurement
    from flow.mosfet.analysis import (
        analyze_mosfet_mismatch,
        analyze_mosfet_noise,
        analyze_mosfet_output,
        analyze_mosfet_trannoise,
        analyze_mosfet_transfer,
    )

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    tb = MosfetTbParams(pdk=pdk, simulator="spectre", mosfet=mosfet, vdd=supply)
    device = _devices(pdk)[mosfet.tp, mosfet.vth]
    _characterize(run_dir, tb, readbacks(tb, f"{device}_l{mosfet.l}"))
    for raw in (run_dir / "netlist.raw", run_dir / "mismatch" / "netlist.raw"):  # the measurements keep them
        if raw.is_dir():
            shutil.rmtree(raw)
        else:
            raw.unlink(missing_ok=True)

    transfer = analyze_mosfet_transfer(read_measurement(run_dir / "transfer.h5"))
    output = analyze_mosfet_output(read_measurement(run_dir / "output.h5"))
    noise = analyze_mosfet_noise(read_measurement(run_dir / "noise.h5"))
    trannoise = analyze_mosfet_trannoise(read_measurement(run_dir / "trannoise.h5"))
    mismatch = (
        analyze_mosfet_mismatch(read_measurement(run_dir / "mismatch.h5"), transfer=transfer)
        if (run_dir / "mismatch.h5").is_file()
        else None
    )
    bias = tb.family.index(tb.bias)  # the family's curve at the bias's gate voltage
    return Record(
        metrics={
            "w_m": transfer.w_m,
            "l_m": transfer.l_m,
            "vth_v": transfer.vth_v,
            "subthreshold_swing_mv_dec": transfer.subthreshold_swing_mv_dec,
            "ion_a": transfer.ion_a,
            "ion_per_w_a_m": transfer.ion_a / transfer.w_m,
            "ioff_a": transfer.ioff_a,
            "gm_id_max_per_v": transfer.gm_over_id_max,
            "id_bias_a": float(output.id_a[bias]),
            "gm_s": float(output.gm_s[bias]),
            "gds_s": float(output.gds_s[bias]),
            "intrinsic_gain_db": float(20 * np.log10(output.intrinsic_gain[bias])),
            "early_v": float(output.early_voltage_v[bias]),
            "ron_ohm": float(output.on_resistance_ohm[-1]),
            "noise_white_v_rthz": noise.white_v_rthz,
            "flicker_corner_hz": noise.flicker_corner_hz,
            "noise_1khz_v_rthz": noise.gate_1khz_v_rthz,
            "trannoise_rms_a": trannoise.rms_a,
            "sigma_vgs_v": mismatch.sigma_vgs_v if mismatch else math.nan,
            "avt_mv_um": mismatch.avt_v_m * 1e9 if mismatch else math.nan,
        },
        details=[
            Detail(
                name="idvg",
                title="Drain current over the gate voltage",
                x_label="|Vgs| (V)",
                y_label="|Id| (A)",
                x=list(transfer.vgs_v),
                series={"|Vds| 50 mV": list(transfer.id_lin_a), "|Vds| supply": list(transfer.id_sat_a)},
                y_log=True,
            ),
            Detail(
                name="gm_id",
                title="gm/Id over the current density (|Vds| supply)",
                x_label="Id/W (A/m)",
                y_label="gm/Id (1/V)",
                x=list(transfer.current_density_a_m),
                series={"gm/Id": list(transfer.gm_over_id)},
                x_log=True,
            ),
            Detail(
                name="idvd",
                title="Drain current over the drain voltage",
                x_label="|Vds| (V)",
                y_label="|Id| (A)",
                x=list(output.vds_v),
                series={
                    f"|Vgs| {round(fraction * 100)} % of supply": list(output.id_family_a[:, index])
                    for index, fraction in enumerate(tb.family)
                },
            ),
            Detail(
                name="gate_noise",
                title="Gate-referred noise at the bias",
                x_label="Frequency (Hz)",
                y_label="Gate-referred noise (V/rtHz)",
                x=list(noise.frequency_hz),
                series={"small-signal": list(noise.gate_noise_v_rthz)},
                x_log=True,
                y_log=True,
            ),
            Detail(
                name="drain_noise",
                title="Drain current noise at the bias: small-signal and transient",
                x_label="Frequency (Hz)",
                y_label="Drain noise (A/rtHz)",
                x=list(noise.frequency_hz),
                series={
                    "small-signal": list(noise.drain_noise_a_rthz),
                    "transient": _binned(trannoise.frequency_hz, trannoise.drain_noise_a_rthz, noise.frequency_hz),
                },
                x_log=True,
                y_log=True,
            ),
        ],
    )
