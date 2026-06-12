"""Run the legacy behavioral SAR ADC model as a basic.py-style scan.

Run from /local/frida:
    uv run python -m flow.scans.scan_behavioral

The generated CSV uses the same columns and ADC conversion constants as
``flow/scans/basic.py``.  Importing those constants is safe because the hardware
scan in ``basic.py`` only runs through its ``main()`` entry point.
"""

from __future__ import annotations

from pathlib import Path

from flow.old.behavioral import SAR_ADC
from flow.scans.basic import (
    CAP_WEIGHTS,
    CODE_WEIGHTS,
    N_SWEEP_POINTS,
    NUM_CAPTURE_BITS,
    V_START,
    V_STOP,
    VINP_SWEEP_V,
)
from flow.scans.plot import plot_adc_transfer, write_adc_csv
from flow.scans.scan_spice import synthetic_fast_rx_words

# Sweep settings matched to flow/scans/basic.py.
ADC_INDEX = 0
VIN_N = 0.600
CONVERSIONS_PER_VIN = 1
SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "behavioral_scan"
WRITE_PLOT = True

# FRIDA ADC physical/configuration settings.
ADC_CLOCK_HZ = 1.0 / 1.28e-6
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
            "resolution": 12,
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


def behavioral_bbits(adc: SAR_ADC, vin_p: float, vin_n: float) -> tuple[str, int]:
    """Run one conversion and return Bbits/Dout using basic.py's recombination."""
    adc.sample_and_convert(vin_p, vin_n, do_calculate_energy=False, do_plot=False, do_normalize_result=False)
    bits = [int(bit) for bit in adc.comp_result]
    if len(bits) != NUM_CAPTURE_BITS:
        raise RuntimeError(f"behavioral model produced {len(bits)} bits, expected {NUM_CAPTURE_BITS}")

    bbits = "".join(str(bit) for bit in bits)
    dout = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, bits, strict=True))
    return bbits, dout


def sweep_voltages() -> tuple[float, ...]:
    return VINP_SWEEP_V


def build_rows(adc: SAR_ADC, attenuation: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    vcm = VIN_N

    for sweep_index, vin_p in enumerate(sweep_voltages()):
        sampled_vin_p = vcm + attenuation * (vin_p - vcm)
        sampled_vin_n = vcm + attenuation * (VIN_N - vcm)
        print(f"sweep {sweep_index:02d}: Vin_p={vin_p:.6g} V, Vin_n={VIN_N:.6g} V, sampled Vin_p={sampled_vin_p:.6g} V")

        for conversion_index in range(CONVERSIONS_PER_VIN):
            bbits, dout = behavioral_bbits(adc, sampled_vin_p, sampled_vin_n)
            bits = [int(bit) for bit in bbits]
            spi0, spi1 = synthetic_fast_rx_words(bits)
            rows.append(
                {
                    "adc": ADC_INDEX,
                    "sweep_index": sweep_index,
                    "vin_set_v": vin_p,
                    "vin_read_v": vin_p,
                    "vdiff_v": vin_p - VIN_N,
                    "conversion_index": conversion_index,
                    "raw_word0": spi0,
                    "raw_word1": spi1,
                    "id0": 0,
                    "id1": 0,
                    "frame0": sweep_index,
                    "frame1": sweep_index,
                    "spi0": spi0,
                    "spi1": spi1,
                    "Bbits": bbits,
                    "Dout": dout,
                }
            )
            print(f"  conversion {conversion_index:02d}: Bbits={bbits} Dout={dout}")

    return rows


def main() -> None:
    params = build_frida_params()
    adc = SAR_ADC(params)
    attenuation = input_attenuation(params) if APPLY_INPUT_ATTENUATION else 1.0

    cdac_capacitance = sum(CAP_WEIGHTS) * UNIT_CAPACITANCE
    cpar = params["CDAC"]["parasitic_capacitance"]
    print("Behavioral FRIDA ADC configuration")
    print(f"Cap weights C16..C1: {CAP_WEIGHTS}")
    print(f"Bit weights W16..W0: {CODE_WEIGHTS}")
    print(f"Cdac={cdac_capacitance / 1e-15:.3f} fF, Cpar={float(cpar) / 1e-15:.3f} fF")
    print(f"Sampled input attenuation={attenuation:.6g}")
    print(f"Vin sweep: {N_SWEEP_POINTS} points from {V_START:.3f} V to {V_STOP:.3f} V")

    rows = build_rows(adc, attenuation)
    write_adc_csv(ADC_INDEX, rows, SCAN_OUTDIR)
    if WRITE_PLOT:
        plot_adc_transfer(
            ADC_INDEX,
            rows,
            SCAN_OUTDIR,
            title=f"FRIDA ADC {ADC_INDEX:02d} behavioral voltage sweep",
            label="behavioral conversions",
            color="red",
        )


if __name__ == "__main__":
    main()
