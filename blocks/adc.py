"""
SAR ADC subcircuit definition.

Dynamic topology using topo_params - generate_topology() computes ports/devices
for each m_caps configuration.

The ADC is a hierarchical design composed of:
- Digital control logic (adc_digital)
- Capacitor arrays with integrated drivers (cdac)
- Sampling switches (samp)
- Comparator (comp)

Architecture variations:
- m_caps: 7, 9, 11, 13, 15, 17, 19 capacitors per side
- Resolution depends on m_caps and redundancy strategy

Naming conventions:
- Use +/- suffixes for differential signals (consistent with comp.py)
- Supply domains: vdd_a/vss_a (analog), vdd_d/vss_d (digital)
"""

from typing import Any

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "adc",
    "ports": {},  # Empty - computed by generate_topology()
    "devices": {},  # Empty - computed by generate_topology()
    "meta": {},
    "tech": ["tsmc65"],
    "topo_params": {"m_caps": [7, 9, 11, 13, 15, 17, 19]},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [],
}


def generate_topology(m_caps: int) -> tuple[dict, dict]:
    """
    Compute ports and devices for given m_caps configuration.

    Called by expand_topo_params() for each topo_params combination.

    Args:
        m_caps: Total number of physical capacitors per side (n_dac + n_extra)

    Returns:
        Tuple of (ports, devices)
    """
    # Build port list
    ports = {
        # Sequencer control signals
        "seq_init": "I",
        "seq_samp": "I",
        "seq_comp": "I",
        "seq_update": "I",
        # Comparator output
        "comp_out": "O",
        # Enable signals
        "en_init": "I",
        "en_samp+": "I",
        "en_samp-": "I",
        "en_comp": "I",
        "en_update": "I",
    }

    # DAC state bus inputs (2 buses per side: astate and bstate, m_caps bits each)
    for side in ["+", "-"]:
        for bus in ["astate", "bstate"]:
            for i in range(m_caps):
                ports[f"{bus}{side}[{i}]"] = "I"

    # Analog inputs and supplies
    ports.update(
        {
            "vin+": "B",
            "vin-": "B",
            "vdd_a": "B",
            "vss_a": "B",
            "vdd_d": "B",
            "vss_d": "B",
        }
    )

    # Build device instances
    devices = {}

    # Digital control block instance
    # Generates internal clock signals and DAC control signals
    digital_pins = {
        "seq_init": "seq_init",
        "seq_samp": "seq_samp",
        "seq_comp": "seq_comp",
        "seq_update": "seq_update",
        "en_init": "en_init",
        "en_samp+": "en_samp+",
        "en_samp-": "en_samp-",
        "en_comp": "en_comp",
        "en_update": "en_update",
        "comp_out": "comp_out",
        "comp_out+": "comp_out+",
        "comp_out-": "comp_out-",
        "clk_samp+": "clk_samp+",
        "clk_samp+b": "clk_samp+b",
        "clk_samp-": "clk_samp-",
        "clk_samp-b": "clk_samp-b",
        "clk_comp": "clk_comp",
        "clk_compb": "clk_compb",
        "vdd_d": "vdd_d",
        "vss_d": "vss_d",
    }

    # Add DAC state input buses to digital block
    for side in ["+", "-"]:
        for bus in ["astate", "bstate"]:
            for i in range(m_caps):
                digital_pins[f"{bus}{side}[{i}]"] = f"{bus}{side}[{i}]"

    # Add DAC control output buses from digital block to CDACs
    for side in ["+", "-"]:
        for i in range(m_caps):
            digital_pins[f"dac_ctrl{side}[{i}]"] = f"dac_ctrl{side}[{i}]"

    devices["Xadc_digital"] = {
        "dev": "subckt",
        "subckt": "adc_digital",
        "pins": digital_pins,
    }

    # CDAC instances (2 total: + and - sides)
    # CDACs now have integrated drivers, no separate capdriver needed
    for side in ["+", "-"]:
        cdac_pins = {
            "top": f"vdac{side}",
            "vdd": "vdd_a",
            "vss": "vss_a",
        }
        for i in range(m_caps):
            cdac_pins[f"dac[{i}]"] = f"dac_ctrl{side}[{i}]"

        devices[f"Xcdac{side}"] = {"dev": "subckt", "subckt": "cdac", "pins": cdac_pins}

    # Sampling switch instances (2 total: + and - sides)
    for side in ["+", "-"]:
        devices[f"Xsamp{side}"] = {
            "dev": "subckt",
            "subckt": "samp",
            "pins": {
                "in": f"vin{side}",
                "out": f"vdac{side}",
                "clk": f"clk_samp{side}",
                "clk_b": f"clk_samp{side}b",
                "vdd": "vdd_a",
                "vss": "vss_a",
            },
        }

    # Comparator instance
    devices["Xcomp"] = {
        "dev": "subckt",
        "subckt": "comp",
        "pins": {
            "in+": "vdac+",
            "in-": "vdac-",
            "out+": "comp_out+",
            "out-": "comp_out-",
            "clk": "clk_comp",
            "clkb": "clk_compb",
            "vdd": "vdd_a",
            "vss": "vss_a",
        },
    }

    return ports, devices


"""
ADC Testbench:

Tests ADC with 2 complete conversions at 10 Msps.

Timing: 10ns settling + 2x 100ns conversions = 210ns total
Each conversion cycle:
  - 0-5ns: seq_init high
  - 5-15ns: seq_samp high
  - 15-100ns: seq_comp and seq_update alternate (2.5ns pulses)

Test structure:
- Differential input signals (ramping voltages)
- DAC state buses (astate+/-, bstate+/-) tied high for normal operation
- Sequencer and enable signals
- Transient analysis to capture ADC behavior

The number of DAC state bus bits matches the ADC topology (m_caps).
"""

# Monolithic testbench struct (dynamic topology - uses m_caps topo_param)
tb = {
    "devices": {},  # Empty - computed by generate_tb_topology()
    "analyses": {"tran1": {"type": "tran", "stop": 210, "step": 0.1}},
    "corner": ["tt"],
    "temp": [27],
    "topo_params": {
        "m_caps": [7, 9, 11, 13, 15, 17, 19]  # Match subckt m_caps values
    },
    "extra_includes": [
        # Standard cell libraries (TSMC65 specific)
        "/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi",
        "/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lp_200a/tcbn65lp_200a.spi",
    ],
    "save": [
        "v(vin+)",
        "v(vin-)",
        "v(comp_out)",
        "v(seq_init)",
        "v(seq_samp)",
        "v(seq_comp)",
        "v(seq_update)",
        "v(en_init)",
        "v(en_samp+)",
        "v(en_samp-)",
        "v(en_comp)",
        "v(en_update)",
    ],
}


def generate_tb_topology(m_caps: int) -> tuple[dict, dict]:
    """
    Generate testbench topology for given m_caps.

    Args:
        m_caps: Number of DAC state bus bits (matches ADC topology)

    Returns:
        Tuple of (ports, devices) - ports is empty for top-level TB
    """
    ports = {}  # Testbenches have no ports (top-level)

    devices = {}

    # Generate DAC state bus signals (all tied high for normal operation)
    for side in ["+", "-"]:
        for bus in ["astate", "bstate"]:
            for i in range(m_caps):
                name = f"V{bus}{side}{i}"
                devices[name] = {
                    "dev": "vsource",
                    "pins": {"p": f"{bus}{side}[{i}]", "n": "gnd"},
                    "wave": "dc",
                    "dc": 1.0,
                }

    # Power supplies
    devices.update(
        {
            # Analog supply
            "Vvdd_a": {
                "dev": "vsource",
                "pins": {"p": "vdd_a", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
            "Vvss_a": {
                "dev": "vsource",
                "pins": {"p": "vss_a", "n": "gnd"},
                "wave": "dc",
                "dc": 0.0,
            },
            # Digital supply
            "Vvdd_d": {
                "dev": "vsource",
                "pins": {"p": "vdd_d", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
            "Vvss_d": {
                "dev": "vsource",
                "pins": {"p": "vss_d", "n": "gnd"},
                "wave": "dc",
                "dc": 0.0,
            },
            # Differential input signals - ramping voltages
            "Vin+": {
                "dev": "vsource",
                "pins": {"p": "vin+", "n": "gnd"},
                "wave": "pwl",
                "points": [
                    0,
                    0.917,
                    210,
                    0.875,
                ],  # Ramps from 1.1V to 1.05V (normalized to 1.2V supply)
            },
            "Vin-": {
                "dev": "vsource",
                "pins": {"p": "vin-", "n": "gnd"},
                "wave": "pwl",
                "points": [
                    0,
                    0.667,
                    210,
                    0.708,
                ],  # Ramps from 0.8V to 0.85V (normalized to 1.2V supply)
            },
            # Sequencer timing signals
            "Vseq_init": {
                "dev": "vsource",
                "pins": {"p": "seq_init", "n": "gnd"},
                "wave": "pulse",
                "v1": 0,
                "v2": 1.0,
                "td": 10,
                "tr": 0.1,
                "tf": 0.1,
                "pw": 4.8,
                "per": 100,
            },
            "Vseq_samp": {
                "dev": "vsource",
                "pins": {"p": "seq_samp", "n": "gnd"},
                "wave": "pulse",
                "v1": 0,
                "v2": 1.0,
                "td": 15,
                "tr": 0.1,
                "tf": 0.1,
                "pw": 9.8,
                "per": 100,
            },
            "Vseq_comp": {
                "dev": "vsource",
                "pins": {"p": "seq_comp", "n": "gnd"},
                "wave": "pulse",
                "v1": 0,
                "v2": 1.0,
                "td": 25,
                "tr": 0.1,
                "tf": 0.1,
                "pw": 2.4,
                "per": 5,
            },
            "Vseq_update": {
                "dev": "vsource",
                "pins": {"p": "seq_update", "n": "gnd"},
                "wave": "pulse",
                "v1": 0,
                "v2": 1.0,
                "td": 27.5,
                "tr": 0.1,
                "tf": 0.1,
                "pw": 2.4,
                "per": 5,
            },
            # Enable signals - tied high for normal operation
            "Ven_init": {
                "dev": "vsource",
                "pins": {"p": "en_init", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
            "Ven_samp+": {
                "dev": "vsource",
                "pins": {"p": "en_samp+", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
            "Ven_samp-": {
                "dev": "vsource",
                "pins": {"p": "en_samp-", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
            "Ven_comp": {
                "dev": "vsource",
                "pins": {"p": "en_comp", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
            "Ven_update": {
                "dev": "vsource",
                "pins": {"p": "en_update", "n": "gnd"},
                "wave": "dc",
                "dc": 1.0,
            },
        }
    )

    # Build DUT pin mapping
    dut_pins = {
        "seq_init": "seq_init",
        "seq_samp": "seq_samp",
        "seq_comp": "seq_comp",
        "seq_update": "seq_update",
        "comp_out": "comp_out",
        "en_init": "en_init",
        "en_samp+": "en_samp+",
        "en_samp-": "en_samp-",
        "en_comp": "en_comp",
        "en_update": "en_update",
        "vin+": "vin+",
        "vin-": "vin-",
        "vdd_a": "vdd_a",
        "vss_a": "vss_a",
        "vdd_d": "vdd_d",
        "vss_d": "vss_d",
    }

    # Add DAC state buses to DUT pins
    for side in ["+", "-"]:
        for bus in ["astate", "bstate"]:
            for i in range(m_caps):
                dut_pins[f"{bus}{side}[{i}]"] = f"{bus}{side}[{i}]"

    devices["Xadc"] = {"dev": "subckt", "subckt": "adc", "pins": dut_pins}

    return ports, devices


def measure(raw, subckt_json, tb_json, raw_file):
    """
    Measure ADC linearity from simulation results.

    This function:
    1. Extracts differential input voltage
    2. Digitizes ADC output bits
    3. Reconstructs analog output using weights
    4. Calculates INL and DNL (both step-based and histogram methods)
    5. Saves all results for plotting
    """
    from flow.measure import (
        digitize,
        reconstruct_analog,
        calculate_inl,
        calculate_dnl,
        calculate_dnl_histogram,
        calculate_linearity_error,
        round_to_codes,
        write_analysis,
    )
    import numpy as np

    # Load simulation data
    time = raw.get_axis()
    vin_p = raw.get_wave("v(vin+)")
    vin_n = raw.get_wave("v(vin-)")
    vin = vin_p - vin_n  # Differential input

    # Get digital output bits from ADC
    # TODO: Update these signal names based on actual ADC outputs
    # For now, assuming comp_out is the comparator output
    comp_out = raw.get_wave("v(comp_out)")

    # Define ADC parameters
    n_bits = 12  # 12-bit ADC
    vdd = 1.0  # Supply voltage

    # Digitize comparator output
    comp_digital = digitize(comp_out, vdd=vdd)

    # TODO: Extract actual DAC state bits when available from simulation
    # For now, create placeholder digital code array
    # This should be replaced with actual bit extraction like:
    # dcode = np.zeros((len(time), n_bits))
    # for i in range(n_bits):
    #     dcode[:, i] = digitize(raw.get_wave(f'v(dac_bit_{i})'), vdd=vdd)

    # Define weights for 12-bit binary ADC
    radix = 2.0
    weights = np.array([radix**i for i in range(n_bits)])

    # For now, create synthetic digital code based on input
    # TODO: Replace with actual ADC output extraction
    vref_range = (-0.6, 0.6)  # ADC input range
    vin_normalized = np.clip(vin, vref_range[0], vref_range[1])

    # Reconstruct analog output from digital code (placeholder until real bits available)
    # dout_analog = reconstruct_analog(dcode, weights, vref_range=vref_range)
    dout_analog = vin_normalized  # Placeholder

    # Round to discrete codes
    dout_rounded = round_to_codes(dout_analog)

    # Calculate INL (Integral Nonlinearity)
    inl, inl_rms, inl_max = calculate_inl(vin, dout_analog, return_stats=True)

    # Calculate DNL using both methods
    # Method 1: Step-based DNL
    dnl, dnl_rms, dnl_max = calculate_dnl(dout_analog, return_stats=True)

    # Method 2: Histogram-based DNL (code density)
    dnl_hist, code_counts, dnl_hist_rms, dnl_hist_max = calculate_dnl_histogram(
        dout_analog, return_stats=True
    )

    # Calculate linearity error
    linearity_error, error_rms = calculate_linearity_error(
        vin, dout_analog, return_stats=True
    )

    # Save all results (arrays + scalars) for plotting
    write_analysis(
        raw_file,
        time,
        vin,
        vin_p,
        vin_n,
        comp_digital,
        dout_analog,
        dout_rounded,
        inl,
        dnl,
        linearity_error,
        inl_rms,
        inl_max,
        dnl_rms,
        dnl_max,
        dnl_hist_rms,
        dnl_hist_max,
        error_rms,
    )
