"""Power the FRIDA ASIC rails and check their quiescent current draw.

The three Keithley 2400 SourceMeters drive VDD_A, VDD_D, and VDD_DAC at
1.2 V with 500 uA compliance. Each loaded rail must remain near 1.2 V and
draw a current on the order of microamps. All outputs are disabled and reset
to 0 V when the check exits, including after a failed assertion or GPIB error.

Run from the repository root with:

    uv run python -m flow.scans.check_smu
"""

from pathlib import Path
from time import sleep


MAP_PATH = Path(__file__).resolve().parent / "map_smu.yaml"
SMU_RAILS = (
    ("smu1", "VDD_A"),
    ("smu2", "VDD_D"),
    ("smu3", "VDD_DAC"),
)

SUPPLY_V = 1.2
VOLTAGE_RANGE_V = 2.0
CURRENT_COMPLIANCE_A = 500.0e-6
SETTLE_TIME_S = 0.5

MINIMUM_LOADED_V = 1.15
MAXIMUM_LOADED_V = 1.205
MINIMUM_EXPECTED_CURRENT_A = 1.0e-6
MAXIMUM_EXPECTED_CURRENT_A = 100.0e-6


def main() -> None:
    if not 0.0 < SUPPLY_V <= 1.2:
        raise ValueError("SMU supply voltage must remain in 0..1.2 V")
    if not 0.0 < CURRENT_COMPLIANCE_A <= 500.0e-6:
        raise ValueError("SMU current compliance must remain in 0..500 uA")
    if not 0.0 < MINIMUM_EXPECTED_CURRENT_A < MAXIMUM_EXPECTED_CURRENT_A < CURRENT_COMPLIANCE_A:
        raise ValueError("expected current bounds must remain below SMU compliance")

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    dut = Dut(str(MAP_PATH))
    smus = []

    try:
        dut.init()
        smus = [(dut[name], rail) for name, rail in SMU_RAILS]

        # First make every output safe. Configure all three rails while they
        # remain disabled so no partially configured supply reaches the ASIC.
        for smu, _rail in smus:
            smu.off()
            smu.set_voltage(0.0)

        for smu, rail in smus:
            smu.source_volt()
            smu.four_wire_off()
            smu.set_voltage_range(VOLTAGE_RANGE_V)
            smu.set_current_limit(CURRENT_COMPLIANCE_A)
            smu.current_sense_autorange_on()
            smu.set_current_nplc(10.0)
            smu.autozero_on()
            smu.set_voltage(SUPPLY_V)

            programmed_voltage_v = float(smu.get_source_voltage())
            programmed_compliance_a = float(smu.get_current_limit())
            if not 0.0 < programmed_voltage_v <= SUPPLY_V:
                raise RuntimeError(f"{rail}: unsafe voltage setpoint readback {programmed_voltage_v:g} V")
            if not 0.0 < programmed_compliance_a <= CURRENT_COMPLIANCE_A:
                raise RuntimeError(f"{rail}: unsafe current-compliance readback {programmed_compliance_a:g} A")

        # Enable the domains back-to-back so the ASIC is not powered through
        # one domain for an extended interval.
        for smu, _rail in smus:
            smu.on()
        sleep(SETTLE_TIME_S)

        measurements = []
        for smu, rail in smus:
            measured_voltage_v = float(smu.get_voltage())
            measured_current_a = float(smu.get_current())
            measurements.append((rail, measured_voltage_v, measured_current_a))
            print(f"{rail}: {measured_voltage_v:.6f} V, {measured_current_a * 1e6:.3f} uA")

            if not MINIMUM_LOADED_V <= measured_voltage_v <= MAXIMUM_LOADED_V:
                raise RuntimeError(
                    f"{rail}: loaded voltage {measured_voltage_v:g} V is outside "
                    f"{MINIMUM_LOADED_V:g}..{MAXIMUM_LOADED_V:g} V"
                )
            if not MINIMUM_EXPECTED_CURRENT_A <= abs(measured_current_a) <= MAXIMUM_EXPECTED_CURRENT_A:
                raise RuntimeError(
                    f"{rail}: measured current {measured_current_a:g} A is outside "
                    f"the expected {MINIMUM_EXPECTED_CURRENT_A * 1e6:g}.."
                    f"{MAXIMUM_EXPECTED_CURRENT_A * 1e6:g} uA range"
                )

        print("PASS: all three FRIDA rails are near 1.2 V and draw microamp-scale current")
        for rail, voltage_v, current_a in measurements:
            print(f"  {rail}: {voltage_v:.6f} V, {current_a * 1e6:.3f} uA")
    finally:
        # Disable all domains before clearing their setpoints. Continue through
        # every rail even if one GPIB transaction fails.
        for smu, rail in smus:
            try:
                smu.off()
                smu.set_voltage(0.0)
            except Exception as error:
                print(f"WARNING: could not disable and zero {rail}: {error}")
        dut.close()


if __name__ == "__main__":
    main()
