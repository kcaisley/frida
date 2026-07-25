"""Run one shared ADC parameter configuration through the legacy model.

Run from /local/frida:
    uv run python -m flow.scans.scan_behavioral

The generated CSV uses the same typed :class:`AdcConversion` schema as the
physical scan. A small in-memory compatibility view is passed to the legacy
transfer plotter; no legacy-format CSV is written.
"""

from __future__ import annotations

from pathlib import Path

import hdl21 as h

from flow.cdac import get_cdac_weights
from flow.old.behavioral import SAR_ADC
from flow.scans.params import AdcTbParams
from flow.scans.plot import plot_adc_transfer
from flow.scans.results import AdcConversion, write_adc_conversions
from flow.scans.scan_adc import (
    convert_dac_caps_to_adc_weights,
    convert_dout_to_normalized_dout,
)
from flow.scans.scan_spice import bits_to_word

ADC_INDEX = 0
PARAMS = AdcTbParams(
    conversions=1,
    vin_cm=h.Vdc.Params(dc=0.600),
    vin_diff=h.Vdc.Params(dc=0.015),
)
CAP_WEIGHTS = get_cdac_weights(PARAMS.dut.cdac)
CODE_WEIGHTS = convert_dac_caps_to_adc_weights(CAP_WEIGHTS)
NUM_CAPTURE_BITS = len(CODE_WEIGHTS)
SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "behavioral_scan"
WRITE_PLOT = True

# FRIDA ADC physical/configuration settings.
ADC_CLOCK_HZ = float(PARAMS.symbol_rate) / len(PARAMS.seq_init_pattern)
UNIT_CAPACITANCE = 1e-15
PARASITIC_RATIO = 1.0  # Cpar/Cdac, passed into the legacy CDAC switching model.
# Keep this false by default: flow.old.behavioral already uses Cpar in the DAC
# switching denominator.  Applying an extra wrapper-level attenuation halves the
# transfer range a second time and yields only about half the output codes.
APPLY_INPUT_ATTENUATION = False

# Non-idealities.  Defaults are deterministic for comparison against PEX.
COMPARATOR_NOISE = 0.0
COMPARATOR_OFFSET = 0.0
REFERENCE_NOISE = 0.0
SETTLING_TIME = 0.0
SWITCHING_STRAT = "monotonic"


def build_frida_params() -> dict[str, dict[str, object]]:
    """Build parameters for the legacy behavioral model matching FRIDA's ADC."""
    cdac_capacitance = sum(CAP_WEIGHTS) * UNIT_CAPACITANCE
    parasitic_capacitance = PARASITIC_RATIO * cdac_capacitance

    return {
        "ADC": {
            "sampling_frequency": ADC_CLOCK_HZ,
            "use_calibration": False,
            "resolution": PARAMS.dut.adc_bits,
        },
        "COMP": {
            "offset_voltage": COMPARATOR_OFFSET,
            "common_mode_dependent_offset_gain": 0.0,
            "threshold_voltage_noise": COMPARATOR_NOISE,
            # Historical examples included this field, although COMPARATOR does not use it.
            "capacitor_mismatch_error": 0.0,
        },
        "CDAC": {
            "positive_reference_voltage": 1.2,
            "negative_reference_voltage": 0.0,
            "reference_voltage_noise": REFERENCE_NOISE,
            "unit_capacitance": UNIT_CAPACITANCE,
            "use_individual_weights": True,
            "individual_weights": CAP_WEIGHTS,
            "parasitic_capacitance": parasitic_capacitance,
            "capacitor_mismatch_error": 0.0,
            "settling_time": SETTLING_TIME,
            "switching_strat": SWITCHING_STRAT,
            "array_size": len(CAP_WEIGHTS),
        },
    }


def input_attenuation(params: dict[str, dict[str, object]]) -> float:
    """Return optional sampled input gain from top-plate parasitic loading.

    This is available for experiments, but is disabled by default because the
    legacy CDAC model already includes ``parasitic_capacitance`` in the DAC
    switching denominator.  Enabling both mechanisms double-counts Cpar for the
    transfer curve.
    """
    cdac = params["CDAC"]
    cdac_capacitance = sum(CAP_WEIGHTS) * float(cdac["unit_capacitance"])
    parasitic_capacitance = float(cdac["parasitic_capacitance"])
    return cdac_capacitance / (cdac_capacitance + parasitic_capacitance)


def convert_behavioral_to_bout_and_dout(
    adc: SAR_ADC,
    vin_p: float,
    vin_n: float,
) -> tuple[str, int, int]:
    """Run one conversion and return Bout plus raw and normalized Dout."""

    adc.sample_and_convert(vin_p, vin_n, do_calculate_energy=False, do_plot=False, do_normalize_result=False)
    bits = [int(bit) for bit in adc.comp_result]
    if len(bits) != NUM_CAPTURE_BITS:
        raise RuntimeError(f"behavioral model produced {len(bits)} bits, expected {NUM_CAPTURE_BITS}")

    bout = "".join(str(bit) for bit in bits)
    dout_raw = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, bits, strict=True))
    dout = convert_dout_to_normalized_dout(
        dout_raw,
        CODE_WEIGHTS,
        PARAMS.dut.adc_bits,
    )
    return bout, dout_raw, dout


def main() -> None:
    params = build_frida_params()
    adc = SAR_ADC(params)
    attenuation = input_attenuation(params) if APPLY_INPUT_ATTENUATION else 1.0
    if not isinstance(PARAMS.vin_diff, h.Vdc.Params):
        raise TypeError("the legacy behavioral adapter currently requires a DC vin_diff")
    vin_diff_v = float(PARAMS.vin_diff.dc)
    vin_cm_v = float(PARAMS.vin_cm.dc)
    vin_p = vin_cm_v + vin_diff_v / 2.0
    vin_n = vin_cm_v - vin_diff_v / 2.0
    sampled_vin_p = vin_cm_v + attenuation * (vin_p - vin_cm_v)
    sampled_vin_n = vin_cm_v + attenuation * (vin_n - vin_cm_v)

    cdac_capacitance = sum(CAP_WEIGHTS) * UNIT_CAPACITANCE
    cpar = params["CDAC"]["parasitic_capacitance"]
    print("Behavioral FRIDA ADC configuration")
    print(f"Cap weights C16..C1: {CAP_WEIGHTS}")
    print(f"Bit weights W16..W0: {CODE_WEIGHTS}")
    print(f"Cdac={cdac_capacitance / 1e-15:.3f} fF, Cpar={float(cpar) / 1e-15:.3f} fF")
    print(f"Sampled input attenuation={attenuation:.6g}")
    print(f"Vin_p={vin_p:.6g} V, Vin_n={vin_n:.6g} V, sampled Vin_p={sampled_vin_p:.6g} V")

    conversions = []
    plot_rows = []
    for conversion_index in range(PARAMS.conversions):
        bout, dout_raw, dout = convert_behavioral_to_bout_and_dout(
            adc,
            sampled_vin_p,
            sampled_vin_n,
        )
        spi = bits_to_word([int(bit) for bit in bout])
        conversions.append(
            AdcConversion(
                conversion_index=conversion_index,
                raw_word=spi,
                identifier=0,
                frame=conversion_index,
                spi=spi,
                bout=bout,
                dout_raw=dout_raw,
                dout=dout,
            )
        )
        plot_rows.append(
            {
                "vin_set_v": vin_p,
                "vdiff_v": vin_diff_v,
                "conversion_index": conversion_index,
                "Bbits": bout,
                "Dout": dout,
            }
        )
        print(f"conversion {conversion_index:02d}: Bout={bout} Dout_raw={dout_raw} Dout={dout}")

    csv_path = SCAN_OUTDIR / f"adc_{ADC_INDEX:02d}.csv"
    write_adc_conversions(csv_path, conversions)
    print(f"ADC {ADC_INDEX:02d}: saved typed data to {csv_path}")
    if WRITE_PLOT:
        adc_cfg = {
            "adc_index": ADC_INDEX,
            "artifact_stem": f"adc{ADC_INDEX:02d}_behavioral",
            "dac_init_state": "behavioral",
        }
        plot_adc_transfer(adc_cfg, plot_rows, SCAN_OUTDIR)


if __name__ == "__main__":
    main()
