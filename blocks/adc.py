"""
SAR ADC specification with hierarchical CDAC integration.

The ADC is a hierarchical design composed of:
- Digital control logic (adc_digital.cdl)
- Capacitor drivers (capdriver.cdl)
- Capacitor arrays (caparray.cdl from CDAC module)
- Sampling switches (sampswitch.cdl)
- Comparator (comp.cdl)

Architecture variations:
- Resolution: 8, 10, 12, 14 bits (determined by digital block configuration)
- DAC stages: 7, 9, 11, 13, 15, 17, 19 capacitors per side
- The same ADC subcircuit name is used for all configs; only the included
  caparray netlist varies based on the number of caps

Naming conventions:
- Use +/- suffixes for differential signals (consistent with comp.py)
- Supply domains: vdd_a/vss_a (analog), vdd_d/vss_d (digital), vdd_dac/vss_dac (DAC drivers)
"""

from typing import Any


def subcircuit():
    """
    Generate ADC subcircuits for all DAC capacitor array configurations.

    The ADC architecture is fixed, but we generate 7 different netlists
    based on the number of capacitors in each CDAC array (7, 9, 11, 13, 15, 17, 19).
    Each configuration corresponds to different bit resolutions:
    - 7 caps: 8-bit ADC
    - 9 caps: 10-bit ADC
    - 11 caps: 12-bit ADC
    - 13 caps: 14-bit ADC
    - 15, 17, 19 caps: higher resolution variants with redundancy

    Returns:
        Tuple of (topology_list, sweeps)
    """
    m_caps_list = [7, 9, 11, 13, 15, 17, 19]
    topology_list = []

    # Technology sweep (same for all topologies)
    sweeps = {
        "tech": ["tsmc65"],
        "globals": {
            "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
            "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        },
    }

    for m_caps in m_caps_list:
        # Generate port list for this configuration
        # Digital control signals
        ports = {
            "seq_init": "I",
            "seq_samp": "I",
            "seq_comp": "I",
            "seq_update": "I",
            "comp_out": "O",
            "en_init": "I",
            "en_samp+": "I",
            "en_samp-": "I",
            "en_comp": "I",
            "en_update": "I",
            "dac_mode": "I",
            "dac_diffcaps": "I",
        }

        # DAC state bus inputs (2 buses per side: astate and bstate, m_caps bits each)
        # For diffcap DAC, drivers are internal, so only N inputs per side
        for side in ['+', '-']:
            for bus in ['astate', 'bstate']:
                for i in range(m_caps):
                    ports[f"dac_{bus}{side}[{i}]"] = "I"

        # Analog inputs and supplies
        ports.update({
            "vin+": "B",
            "vin-": "B",
            "vdd_a": "B",
            "vss_a": "B",
            "vdd_d": "B",
            "vss_d": "B",
            "vdd_dac": "B",
            "vss_dac": "B",
        })

        # Device instances
        devices = {}

        # Digital control block instance
        # Generates internal clock signals and DAC state/invert signals
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
            "dac_mode": "dac_mode",
            "dac_diffcaps": "dac_diffcaps",
            "comp_out": "comp_out",
            "comp_out+": "comp_out+",
            "comp_out-": "comp_out-",
            "clk_samp+": "clk_samp+",
            "clk_samp+b": "clk_samp+b",
            "clk_samp-": "clk_samp-",
            "clk_samp-b": "clk_samp-b",
            "clk_comp": "clk_comp",
            "dac_invert+_main": "dac_invert+_main",
            "dac_invert+_diff": "dac_invert+_diff",
            "dac_invert-_main": "dac_invert-_main",
            "dac_invert-_diff": "dac_invert-_diff",
            "vdd_d": "vdd_d",
            "vss_d": "vss_d",
        }

        # Add DAC state input/output buses to digital block
        for side in ['+', '-']:
            for bus in ['astate', 'bstate']:
                for i in range(m_caps):
                    # Input: external DAC state
                    digital_pins[f"dac_{bus}{side}[{i}]"] = f"dac_{bus}{side}[{i}]"

        for side in ['+', '-']:
            for array in ['main', 'diff']:
                for i in range(m_caps):
                    # Output: internal DAC state to drivers
                    digital_pins[f"dac_state{side}_{array}[{i}]"] = f"dac_state{side}_{array}[{i}]"

        devices['Xadc_digital'] = {'dev': 'subckt', 'subckt': 'adc_digital', 'pins': digital_pins}

        # Capacitor driver instances (4 total: +/- sides × main/diff arrays)
        for side in ['+', '-']:
            for array in ['main', 'diff']:
                driver_pins = {
                    "dac_invert": f"dac_invert{side}_{array}",
                    "vdd_dac": "vdd_dac",
                    "vss_dac": "vss_dac",
                }
                for i in range(m_caps):
                    driver_pins[f"dac_state[{i}]"] = f"dac_state{side}_{array}[{i}]"
                    driver_pins[f"dac_drive[{i}]"] = f"dac_drive{side}_{array}[{i}]"

                devices[f'Xcapdriver{side}_{array}'] = {
                    'dev': 'subckt',
                    'subckt': 'capdriver',
                    'pins': driver_pins
                }

        # Capacitor array instances (2 total: + and - sides)
        for side in ['+', '-']:
            caparray_pins = {
                "vdac": f"vdac{side}",
                "vshield": "vss_a",
            }
            for array in ['main', 'diff']:
                for i in range(m_caps):
                    caparray_pins[f"bot_{array}[{i}]"] = f"dac_drive{side}_{array}[{i}]"

            devices[f'Xcaparray{side}'] = {
                'dev': 'subckt',
                'subckt': 'caparray',
                'pins': caparray_pins
            }

        # Sampling switch instances (2 total: + and - sides)
        for side in ['+', '-']:
            devices[f'Xsampswitch{side}'] = {
                'dev': 'subckt',
                'subckt': 'sampswitch',
                'pins': {
                    "vin": f"vin{side}",
                    "vdac": f"vdac{side}",
                    "clk": f"clk_samp{side}",
                    "clkb": f"clk_samp{side}b",
                    "vdd": "vdd_a",
                    "vss": "vss_a",
                }
            }

        # Comparator instance
        devices['Xcomp'] = {
            'dev': 'subckt',
            'subckt': 'comp',
            'pins': {
                "in+": "vdac+",
                "in-": "vdac-",
                "out+": "comp_out+",
                "out-": "comp_out-",
                "clk": "clk_comp",
                "clkb": "clk_compb",
                "vdd": "vdd_a",
                "vss": "vss_a",
            }
        }

        # Build topology
        topology = {
            "subckt": "adc",
            "ports": ports,
            "devices": devices,
            "meta": {
                "m_caps": m_caps,
            }
        }

        topology_list.append(topology)

    return topology_list, sweeps


def testbench():
    """
    ADC testbench for 2 complete conversions at 10 Msps.

    Timing: 10ns settling + 2x 100ns conversions = 210ns total
    Each conversion cycle:
      - 0-5ns: seq_init high
      - 5-15ns: seq_samp high
      - 15-100ns: seq_comp and seq_update alternate (2.5ns pulses)

    Generates testbenches for different m_caps values (matching subcircuit variants).
    """
    m_caps_list = [7, 9, 11, 13, 15, 17, 19]
    topology_list = []

    # Testbench sweep: corner, temp, and device globals
    sweeps = {
        "corner": ["tt"],
        "temp": [27],
        "globals": {
            "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
            "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        }
    }

    for m_caps in m_caps_list:
        # Generate DAC state bus signals (all tied high for normal operation)
        devices = {}

        for side in ['+', '-']:
            for bus in ['astate', 'bstate']:
                for i in range(m_caps):
                    name = f'Vdac_{bus}{side}{i}'
                    devices[name] = {
                        'dev': 'vsource',
                        'pins': {'p': f'dac_{bus}{side}[{i}]', 'n': 'gnd'},
                        'wave': 'dc',
                        'dc': 1.0
                    }

        # Power supplies
        devices.update({
            # Analog supply
            'Vvdd_a': {'dev': 'vsource', 'pins': {'p': 'vdd_a', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss_a': {'dev': 'vsource', 'pins': {'p': 'vss_a', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},

            # Digital supply
            'Vvdd_d': {'dev': 'vsource', 'pins': {'p': 'vdd_d', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss_d': {'dev': 'vsource', 'pins': {'p': 'vss_d', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},

            # DAC supply
            'Vvdd_dac': {'dev': 'vsource', 'pins': {'p': 'vdd_dac', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss_dac': {'dev': 'vsource', 'pins': {'p': 'vss_dac', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},

            # Differential input signals - ramping voltages
            'Vin+': {
                'dev': 'vsource',
                'pins': {'p': 'vin+', 'n': 'gnd'},
                'wave': 'pwl',
                'points': [0, 0.917, 210, 0.875]  # Ramps from 1.1V to 1.05V (normalized to 1.2V supply)
            },
            'Vin-': {
                'dev': 'vsource',
                'pins': {'p': 'vin-', 'n': 'gnd'},
                'wave': 'pwl',
                'points': [0, 0.667, 210, 0.708]  # Ramps from 0.8V to 0.85V (normalized to 1.2V supply)
            },

            # Sequencer timing signals
            'Vseq_init': {
                'dev': 'vsource',
                'pins': {'p': 'seq_init', 'n': 'gnd'},
                'wave': 'pulse',
                'v1': 0, 'v2': 1.0, 'td': 10, 'tr': 0.1, 'tf': 0.1, 'pw': 4.8, 'per': 100
            },
            'Vseq_samp': {
                'dev': 'vsource',
                'pins': {'p': 'seq_samp', 'n': 'gnd'},
                'wave': 'pulse',
                'v1': 0, 'v2': 1.0, 'td': 15, 'tr': 0.1, 'tf': 0.1, 'pw': 9.8, 'per': 100
            },
            'Vseq_comp': {
                'dev': 'vsource',
                'pins': {'p': 'seq_comp', 'n': 'gnd'},
                'wave': 'pulse',
                'v1': 0, 'v2': 1.0, 'td': 25, 'tr': 0.1, 'tf': 0.1, 'pw': 2.4, 'per': 5
            },
            'Vseq_update': {
                'dev': 'vsource',
                'pins': {'p': 'seq_update', 'n': 'gnd'},
                'wave': 'pulse',
                'v1': 0, 'v2': 1.0, 'td': 27.5, 'tr': 0.1, 'tf': 0.1, 'pw': 2.4, 'per': 5
            },

            # Enable signals - tied high for normal operation
            'Ven_init': {'dev': 'vsource', 'pins': {'p': 'en_init', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Ven_samp+': {'dev': 'vsource', 'pins': {'p': 'en_samp+', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Ven_samp-': {'dev': 'vsource', 'pins': {'p': 'en_samp-', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Ven_comp': {'dev': 'vsource', 'pins': {'p': 'en_comp', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Ven_update': {'dev': 'vsource', 'pins': {'p': 'en_update', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},

            # DAC mode control signals
            'Vdac_mode': {'dev': 'vsource', 'pins': {'p': 'dac_mode', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vdac_diffcaps': {'dev': 'vsource', 'pins': {'p': 'dac_diffcaps', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
        })

        # Build DUT pin mapping
        dut_pins = {
            'seq_init': 'seq_init',
            'seq_samp': 'seq_samp',
            'seq_comp': 'seq_comp',
            'seq_update': 'seq_update',
            'comp_out': 'comp_out',
            'en_init': 'en_init',
            'en_samp+': 'en_samp+',
            'en_samp-': 'en_samp-',
            'en_comp': 'en_comp',
            'en_update': 'en_update',
            'dac_mode': 'dac_mode',
            'dac_diffcaps': 'dac_diffcaps',
            'vin+': 'vin+',
            'vin-': 'vin-',
            'vdd_a': 'vdd_a',
            'vss_a': 'vss_a',
            'vdd_d': 'vdd_d',
            'vss_d': 'vss_d',
            'vdd_dac': 'vdd_dac',
            'vss_dac': 'vss_dac',
        }

        # Add DAC state buses to DUT pins
        for side in ['+', '-']:
            for bus in ['astate', 'bstate']:
                for i in range(m_caps):
                    dut_pins[f'dac_{bus}{side}[{i}]'] = f'dac_{bus}{side}[{i}]'

        devices['Xadc'] = {'dev': 'subckt', 'subckt': 'adc', 'pins': dut_pins}

        topology = {
            'testbench': 'tb_adc',
            'devices': devices,
            'analyses': {
                'tran1': {
                    'type': 'tran',
                    'stop': 210,
                    'step': 0.1
                }
            },
            'extra_includes': [
                # Standard cell libraries (TSMC65 specific)
                '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi',
                '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lp_200a/tcbn65lp_200a.spi',
                # ADC sub-module netlists
                'spice/sampswitch.cdl',
                'spice/comp.cdl',
                'spice/capdriver.cdl',
                'spice/caparray.cdl',
                'spice/adc_digital.cdl',
                'spice/adc.cdl'
            ],
            'save': [
                'v(vin+)', 'v(vin-)', 'v(comp_out)',
                'v(seq_init)', 'v(seq_samp)', 'v(seq_comp)', 'v(seq_update)',
                'v(en_init)', 'v(en_samp+)', 'v(en_samp-)', 'v(en_comp)', 'v(en_update)'
            ],
            'meta': {
                'm_caps': m_caps
            }
        }

        topology_list.append(topology)

    return topology_list, sweeps


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
        digitize, reconstruct_analog, calculate_inl, calculate_dnl,
        calculate_dnl_histogram, calculate_linearity_error,
        round_to_codes, write_analysis
    )
    import numpy as np

    # Load simulation data
    time = raw.get_axis()
    vin_p = raw.get_wave('v(vin+)')
    vin_n = raw.get_wave('v(vin-)')
    vin = vin_p - vin_n  # Differential input

    # Get digital output bits from ADC
    # TODO: Update these signal names based on actual ADC outputs
    # For now, assuming comp_out is the comparator output
    comp_out = raw.get_wave('v(comp_out)')

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
    linearity_error, error_rms = calculate_linearity_error(vin, dout_analog, return_stats=True)

    # Save all results (arrays + scalars) for plotting
    write_analysis(
        raw_file,
        time, vin, vin_p, vin_n, comp_digital,
        dout_analog, dout_rounded, inl, dnl, linearity_error,
        inl_rms, inl_max, dnl_rms, dnl_max,
        dnl_hist_rms, dnl_hist_max, error_rms
    )
