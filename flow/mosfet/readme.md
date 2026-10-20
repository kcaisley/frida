# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | One MOSFET of a PDK's core flavors, the width in its unit widths (fingered to its row cells), the length in multiples of its minimum. `cases(pdk)`: every core device the PDK wraps (no native devices) at 1, 2, 4 and 8 times the minimum length, 8 unit widths wide. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Wiring, invalid sizes, every PDK's cases. |
| Testbench generator | ✓ | [sim.py](sim.py) | Source and body on ground, a source on the drain and on the gate (a PMOS's at negative voltages). Spectre: Id-Vgs at \|Vds\| 50 mV and the supply, Id-Vds at five gate voltages, noise at the bias (\|Vgs\| = \|Vds\| = half the supply) from 1 Hz to 10 GHz, transient noise over 10 µs up to 1 GHz, and a Monte Carlo of mismatch (200 runs) on the PDK's statistical sections. ngspice (HSPICE compatibility): the sweeps and the noise; it has no device transient noise. Both read the PDK's `simulation_includes`. |
| Simulation runners | ✓ | [sim.py](sim.py) | `mosfet_characterization`: 112 devices in Spectre and the 48 of TSMC65, IHP130 and TPSC65 in ngspice (TSMC28's, Tower180's and LF150's decks do not load in ngspice: `pdk/test_spice.py`), in 70 s on 24 workers per PDK. Monte Carlo where the kit has mismatch statistics for the package's devices: TSMC28, IHP130, Tower180, TPSC65 (TSMC65's vary only its macro models; LF150's decks hold none). |
| Analysis | ✓ | [analysis.py](analysis.py) | `analyze_mosfet_transfer` (threshold by linear extrapolation, subthreshold swing, on and off current, gm/Id over Id/W), `analyze_mosfet_output` (output conductance, Early voltage, gm across the family, intrinsic gain, on resistance), `analyze_mosfet_noise` (gate-referred white floor, flicker corner, spot noise at 1 kHz and 1 MHz), `analyze_mosfet_trannoise` (Welch density of the transient record), `analyze_mosfet_mismatch` (σ(Id)/Id, σ(Vgs) through gm, the Pelgrom A_VT). |
| Plots | ✓ | [plots.py](plots.py) | Per PDK: Id-Vgs and gm/Id per device over its lengths, Id-Vds at twice the minimum length, gate-referred noise, transient against small-signal noise, the Pelgrom plot, Spectre against ngspice. Run by `flow.analysis.runner mosfet_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A square-law device of known threshold, gm/Id and output conductance; 1/f-plus-white noise of known corner; white transient noise and Gaussian mismatch of known density and spread; every plot renders. |
| Layout | - | - | A single device: the row-cell generators' MOS cells. |

Run 20261020_132427, each PDK's devices at twice the minimum length:

- **Threshold:** 0.21 V (TPSC65 SLVT PMOS) to 0.72 V (LF150 low-leakage PMOS).
- **Subthreshold swing:** 70–80 mV/decade (Tower180's HVT devices 87–92).
- **Peak gm/Id:** 24–32 V⁻¹.
- **Flicker corners:** 0.5–60 MHz, the NMOS an order above the PMOS.
- **Spectre against ngspice:** the threshold within 0.1 mV and the on current within 0.2 % in TSMC65, IHP130 and TPSC65 (the same BSIM4 and PSP models).
- **A_VT:**
  - TSMC28: 0.9–1.3 mV·µm.
  - IHP130: 2.6–3.4 mV·µm.
  - TPSC65: 3.2–4.2 mV·µm.
  - Tower180: 2.7–4.4 mV·µm (18 for its HVT NMOS, worth a check against the kit's matching data).
- **Transient against small-signal noise:** the transient record's drain noise density lies within about 15 % of the small-signal analysis's above 1 MHz.

Inspiration: the gm/Id methodology (Jespers and Murmann), BAG's `mos_char` characterization.
