"""
SAR ADC subcircuit definition.

Dynamic topology using topo_params - generate_topology() computes ports/instances
for each num_caps configuration.

The ADC is a hierarchical design composed of:
- Digital control logic (adc_digital)
- Capacitor arrays with integrated drivers (cdac)
- Sampling switches (samp)
- Comparator (comp)

Architecture variations:
- num_caps: 7, 9, 11, 13, 15, 17, 19 capacitors per side
- Resolution depends on num_caps and redundancy strategy

Naming conventions:
- Use +/- suffixes for differential signals (consistent with comp.py)
- Supply domains: vdd_a/vss_a (analog), vdd_d/vss_d (digital)
"""


# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "adc",
    "ports": {},  # Empty - computed by generate_topology()
    "instances": {},  # Empty - computed by generate_topology()
    "tech": ["tsmc65"],
    "topo_params": {
        "n_cycles": [8, 12, 14, 16, 18, 20],
        "n_adc": [8, 12, 14],
    },
    "inst_params": [
        # Defaults for all nmos/pmos instances in the ADC itself
        {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        # Child cdac config - sweep redun_strat and split_strat
        {
            "instances": {"cdac": "all"},
            "topo_params": {
                "redun_strat": ["rdx2", "subrdx2rdst", "subrdx2lim", "subrdx2", "rdx2rpt"],
                "split_strat": ["nosplit", "vdivsplit", "diffcapsplit"],
            },
        },
        # Child samp config - use default sizing
        {
            "instances": {"samp": "all"},
            "inst_params": [
                {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
                {"instances": {"nmos": ["MN"], "pmos": ["MP"]}, "w": 5, "l": 1},
            ],
        },
        # Child inv config - use default sizing
        {
            "instances": {"inv": "all"},
            "inst_params": [
                {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
                {"instances": {"nmos": ["MN"], "pmos": ["MP"]}, "w": 1, "type": "lvt"},
            ],
        },
        # Child comp config - use default sizing
        {
            "instances": {"comp": "all"},
            "inst_params": [
                {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
                {"instances": {"cap": "all"}, "c": 1, "m": 1},
            ],
        },
    ],
}


def generate_topology(n_cycles: int, n_adc: int) -> tuple[dict, dict]:
    """
    Compute ports and instances for given n_cycles/n_adc configuration.

    Called by generate_topology() for each topo_params combination.

    Args:
        n_cycles: Number of SAR conversion cycles
        n_adc: ADC resolution in bits

    Returns:
        Tuple of (ports, instances)
    """
    # Compute child cdac topo_params from parent topo_params
    n_dac = n_adc - 1
    n_extra = n_cycles - n_adc

    # Number of physical capacitors per side (used for port/signal counts)
    num_caps = n_dac + n_extra
    # Build port list
    ports = {
        # Clock/control signals for salogic
        "clk_init": "I",
        "clk_update": "I",
        "clk_samp": "I",
        "clk_samp_b": "I",
        "dac_mode": "I",
        # Analog inputs
        "vin+": "B",
        "vin-": "B",
        # Supplies
        "vdd_a": "B",
        "vss_a": "B",
        "vdd_d": "B",
        "vss_d": "B",
    }

    # DAC state bus inputs (2 buses per side: astate and bstate, num_caps bits each)
    for side in ["+", "-"]:
        for bus in ["astate", "bstate"]:
            for i in range(num_caps):
                ports[f"dac_{bus}{side}[{i}]"] = "I"

    # Build instances
    instances = {}

    # SAR Logic block - manages DAC state based on comparator outputs
    salogic_pins = {
        "clk_init": "clk_init",
        "clk_update": "clk_update",
        "dac_mode": "dac_mode",
        "comp_p": "comp_p",
        "comp_n": "comp_n",
        "vdd_d": "vdd_d",
        "vss_d": "vss_d",
    }

    # Add DAC state input buses (from external SPI) and output buses (to CDACs)
    for side, suffix in [("p", "+"), ("n", "-")]:
        for bus in ["astate", "bstate"]:
            for i in range(num_caps):
                salogic_pins[f"dac_{bus}_{side}[{i}]"] = f"dac_{bus}{suffix}[{i}]"
        for i in range(num_caps):
            salogic_pins[f"dac_state_{side}[{i}]"] = f"dac_state{suffix}[{i}]"

    instances["Xsalogic"] = {
        "cell": "salogic",
        "pins": salogic_pins,
    }

    # CDAC instances (2 total: + and - sides)
    # CDACs now have integrated drivers, no separate capdriver needed
    for side in ["+", "-"]:
        cdac_pins = {
            "top": f"vdac{side}",
            "vdd": "vdd_a",
            "vss": "vss_a",
        }
        for i in range(num_caps):
            cdac_pins[f"dac[{i}]"] = f"dac_state{side}[{i}]"

        instances[f"Xcdac{side}"] = {
            "cell": "cdac",
            "pins": cdac_pins,
            "topo_params": {"n_dac": n_dac, "n_extra": n_extra},
        }

    # Sampling switch instances (2 total: + and - sides)
    for side in ["+", "-"]:
        instances[f"Xsamp{side}"] = {
            "cell": "samp",
            "pins": {
                "in": f"vin{side}",
                "out": f"vdac{side}",
                "clk": "clk_samp",
                "clk_b": "clk_samp_b",
                "vdd": "vdd_a",
                "vss": "vss_a",
            },
            "topo_params": {"switch_type": "nmos"},  # Use nmos switch
        }

    # Inverter to generate clkb from clk_update
    instances["Xinv_clk"] = {
        "cell": "inv",
        "pins": {
            "in": "clk_update",
            "out": "clk_update_b",
            "vdd": "vdd_d",
            "vss": "vss_d",
        },
    }

    # Comparator instance - outputs feed back to salogic
    instances["Xcomp"] = {
        "cell": "comp",
        "pins": {
            "in+": "vdac+",
            "in-": "vdac-",
            "out+": "comp_p",
            "out-": "comp_n",
            "clk": "clk_update",
            "clkb": "clk_update_b",
            "vdd": "vdd_a",
            "vss": "vss_a",
        },
        "topo_params": {
            "preamp_diffpair": "nmosinput",
            "preamp_bias": "dynbias",
            "comp_stages": "doublestage",
            "latch_pwrgate_ctl": "signalled",
            "latch_pwrgate_node": "internal",
            "latch_rst_extern_ctl": "noreset",
            "latch_rst_intern_ctl": "signalled",
        },
    }

    return ports, instances


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

The number of DAC state bus bits matches the ADC topology (num_caps = n_cycles - 1).
"""

# Monolithic testbench struct (dynamic topology - uses n_cycles/n_adc topo_params)
tb = {
    "instances": {},  # Empty - computed by generate_tb_topology()
    "analyses": {"tran1": {"type": "tran", "stop": 210, "step": 0.1}},
    "corner": ["tt"],
    "temp": [27],
    "topo_params": {
        "n_cycles": [8, 12, 14, 16, 18, 20],  # Match subckt n_cycles values
        "n_adc": [8, 12, 14],  # Match subckt n_adc values
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


def generate_tb_topology(n_cycles: int, n_adc: int) -> tuple[dict, dict]:
    """
    Generate testbench topology for given n_cycles/n_adc.

    Args:
        n_cycles: Number of SAR conversion cycles
        n_adc: ADC resolution in bits

    Returns:
        Tuple of (ports, instances) - ports is empty for top-level TB
    """
    # Compute num_caps from n_cycles (same as in generate_topology)
    num_caps = n_cycles - 1

    ports = {}  # Testbenches have no ports (top-level)

    instances = {}

    # Generate DAC state bus signals (all tied high for normal operation)
    for side in ["+", "-"]:
        for bus in ["astate", "bstate"]:
            for i in range(num_caps):
                name = f"V{bus}{side}{i}"
                instances[name] = {
                    "dev": "vsource",
                    "pins": {"p": f"{bus}{side}[{i}]", "n": "gnd"},
                    "wave": "dc",
                    "dc": 1.0,
                }

    # Power supplies
    instances.update(
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
            for i in range(num_caps):
                dut_pins[f"{bus}{side}[{i}]"] = f"{bus}{side}[{i}]"

    instances["Xadc"] = {"cell": "adc", "pins": dut_pins}

    return ports, instances


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
    vdd = 1.0  # Supply voltage

    # Digitize comparator output
    comp_digital = digitize(comp_out, vdd=vdd)

    # TODO: Extract actual DAC state bits when available from simulation
    # For now, create placeholder digital code array
    # This should be replaced with actual bit extraction like:
    # dcode = np.zeros((len(time), n_bits))
    # for i in range(n_bits):
    #     dcode[:, i] = digitize(raw.get_wave(f'v(dac_bit_{i})'), vdd=vdd)

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
    dnl_hist, code_counts, dnl_hist_rms, dnl_hist_max = calculate_dnl_histogram(  # pyright: ignore[reportAssignmentType]
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
