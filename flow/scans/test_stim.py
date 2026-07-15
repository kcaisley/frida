"""Smoke-test the FRIDA ADC stimulus instruments.

Run from the repository root with:

    uv run python -m flow.scans.test_stim

The Agilent 33250A exercises DC, sine, and ramp outputs over 0..1.2 V.
The TTi QL355TP exercises DC output on main channels 1 and 2 over the
same range. Outputs are disabled and reset to 0 V when the script exits.
"""

from pathlib import Path
from time import sleep

from yaml import safe_load

VOLTAGE_MIN_V = 0.0
VOLTAGE_MAX_V = 1.2
DC_LEVELS_V = (0.0, 0.3, 0.6, 0.9, 1.2)
WAVEFORM_FREQUENCY_HZ = 1.0
DC_DWELL_S = 1.0
WAVEFORM_DWELL_S = 5.0
PSU_CHANNELS = (1, 2)
PSU_CURRENT_LIMIT_A = 0.010


def exercise_awg(awg) -> None:
    """Exercise 0..1.2 V DC, sine, and ramp outputs on the 33250A."""
    amplitude_vpp = VOLTAGE_MAX_V - VOLTAGE_MIN_V
    offset_v = (VOLTAGE_MAX_V + VOLTAGE_MIN_V) / 2

    print("\nAgilent 33250A DC sweep")
    awg.set_output_load("INFinity")
    for voltage in DC_LEVELS_V:
        awg.set_DC(f"DEF,DEF,{voltage}")
        awg.set_enable(1)
        sleep(DC_DWELL_S)
        actual = float(str(awg.get_voltage_offset()).strip())
        print(f"  requested={voltage:.3f} V, offset readback={actual:.3f} V")
    awg.set_enable(0)

    print(
        f"\nAgilent 33250A sine: {WAVEFORM_FREQUENCY_HZ:g} Hz, "
        f"{amplitude_vpp:.3f} Vpp, {offset_v:.3f} V offset "
        f"({VOLTAGE_MIN_V:.3f}..{VOLTAGE_MAX_V:.3f} V)"
    )
    awg.set_sin(f"{WAVEFORM_FREQUENCY_HZ},{amplitude_vpp},{offset_v}")
    awg.set_enable(1)
    print(f"  configured as {str(awg.get_function()).strip()}")
    sleep(WAVEFORM_DWELL_S)
    awg.set_enable(0)

    print(
        f"\nAgilent 33250A ramp: {WAVEFORM_FREQUENCY_HZ:g} Hz, "
        f"{amplitude_vpp:.3f} Vpp, {offset_v:.3f} V offset "
        f"({VOLTAGE_MIN_V:.3f}..{VOLTAGE_MAX_V:.3f} V)"
    )
    awg.set_ramp(f"{WAVEFORM_FREQUENCY_HZ},{amplitude_vpp},{offset_v}")
    awg.set_function_ramp_symmetry(50)
    awg.set_enable(1)
    print(f"  configured as {str(awg.get_function()).strip()}")
    sleep(WAVEFORM_DWELL_S)
    awg.set_enable(0)


def exercise_psu(psu) -> None:
    """Exercise 0..1.2 V DC output on both QL355TP main channels."""
    print(f"\nTTi QL355TP DC sweep on channels {PSU_CHANNELS}")
    for channel in PSU_CHANNELS:
        psu.set_enable(False, channel=channel)
        psu.set_current_limit(PSU_CURRENT_LIMIT_A, channel=channel)
        psu.set_voltage(0.0, channel=channel)
        psu.set_enable(True, channel=channel)

    for voltage in DC_LEVELS_V:
        for channel in PSU_CHANNELS:
            psu.set_voltage(voltage, channel=channel)
        sleep(DC_DWELL_S)

        for channel in PSU_CHANNELS:
            requested = psu.get_set_voltage(channel)
            measured = psu.get_voltage(channel)
            print(f"  CH{channel}: requested={requested:.3f} V, measured={measured:.3f} V")

    for channel in PSU_CHANNELS:
        psu.set_enable(False, channel=channel)


def shut_down_awg(awg) -> None:
    """Best-effort safe shutdown of the waveform generator."""
    try:
        awg.set_enable(0)
        awg.set_DC("DEF,DEF,0")
    except Exception as error:
        print(f"Warning: could not reset AWG output: {error}")


def shut_down_psu(psu) -> None:
    """Best-effort safe shutdown of both power-supply channels."""
    for channel in PSU_CHANNELS:
        try:
            psu.set_enable(False, channel=channel)
            psu.set_voltage(0.0, channel=channel)
        except Exception as error:
            print(f"Warning: could not reset PSU channel {channel}: {error}")


def load_instrument(map_path: Path, driver_name: str):
    """Create a one-device Basil DUT from the shared instrument map."""
    from basil.dut import Dut

    config = safe_load(map_path.read_text())
    driver = next(item for item in config["hw_drivers"] if item["name"] == driver_name)
    interface_name = driver["interface"]
    config["transfer_layer"] = [item for item in config["transfer_layer"] if item["name"] == interface_name]
    config["hw_drivers"] = [driver]
    return Dut(config)


def main() -> None:
    map_path = Path(__file__).resolve().parent / "map_awg.yaml"
    failures = []

    awg_dut = load_instrument(map_path, "awg")
    awg_initialized = False
    try:
        awg_dut.init()
        awg_initialized = True
        awg = awg_dut["awg"]
        print(f"AWG: {str(awg.get_info()).strip()}")
        shut_down_awg(awg)
        exercise_awg(awg)
    except Exception as error:
        failures.append(f"AWG: {error}")
        print(f"\nAWG test failed: {error}")
    finally:
        if awg_initialized:
            shut_down_awg(awg_dut["awg"])
        awg_dut.close()

    psu_dut = load_instrument(map_path, "psu")
    psu_initialized = False
    try:
        psu_dut.init()
        psu_initialized = True
        psu = psu_dut["psu"]
        print(f"\nPSU: {psu.get_name()}")
        shut_down_psu(psu)
        exercise_psu(psu)
    except Exception as error:
        failures.append(f"PSU: {error}")
        print(f"\nPSU test failed: {error}")
    finally:
        if psu_initialized:
            shut_down_psu(psu_dut["psu"])
        psu_dut.close()

    if failures:
        print("\nStimulus smoke test failed: " + "; ".join(failures))
        raise SystemExit(1)

    print("\nStimulus smoke test completed; all outputs are disabled and reset to 0 V.")


if __name__ == "__main__":
    main()
