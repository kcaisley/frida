"""One-off: re-plot the deck's scope noise spectra on the shared nV/√Hz range.

The captures were plotted by flow/scans/test_noise.py when taken; this redraws
the ones the interferer-hunt deck shows from their saved slow and fast
AnalysisScope records under build/test_noise, with the same plot_spectrum call,
into this directory. Run from the repository root (needs the captures):

    uv run python docs/images/interferer_hunt/plot_scope_spectra.py
"""

from pathlib import Path

from flow.analysis.io import read_analysis
from flow.analysis.plots import plot_spectrum
from flow.analysis.types import AnalysisScope

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
# (capture directory, trace kind, step title as captured, output name)
FIGURES = (
    (
        "20261008_174908/step1_floor_probes",
        "single",
        "Measurement floor, passive probes (1X)",
        "step1_floor_probes_spectrum",
    ),
    ("20261008_173102/step2_supply_div", "single", "Divider supply", "step2_supply_div_shared"),
    ("20261008_185827/step2_supply_div", "single", "Divider supply", "step2_supply_div_own"),
    ("20261008_182504/step3_divider_out", "common", "Divider outputs", "step3_shared_supply_common"),
    ("20261008_182504/step3_divider_out", "diffcm", "Divider outputs, FPGA on the shared 5 V", "step3_shared_supply"),
    ("20261008_185309/step3_divider_out", "diffcm", "Divider outputs, FPGA on its own E3634A", "step3_own_supply"),
    ("20261008_185309/step3_divider_out", "diff", "Divider outputs", "step3_own_supply_diff"),
    ("20261008_232308/hunt_vdd_a", "single", "VDD_A, chip side at J13", "hunt_vdd_a_spectrum"),
    (
        "20261009_000030/sniff_e3634a_fpga",
        "single",
        "Sniffer loops at the E3634A (BDAQ 5 V) and on the FPGA module",
        "sniff_e3634a_fpga_spectrum",
    ),
    ("20261008_232808/hunt_gnd_bdaq", "single", "BDAQ ground against chip-card ground", "hunt_gnd_bdaq_spectrum"),
    ("20261008_233053/hunt_vdd_bdaq", "single", "VDD_BDAQ at J14.8", "hunt_vdd_bdaq_spectrum"),
    ("20261008_233643/step3_divider_out", "diff", "ADC inputs at J11, ADC running", "hunt_vin_diff"),
    ("20261008_234845/hunt_clk_comp", "diff", "COMP clock pair, idle", "hunt_clk_comp_diff"),
    (
        "20261009_001111/sniff_asic_fpga",
        "single",
        "Sniffer loops above the ASIC and around the FPGA module",
        "sniff_asic_fpga_spectrum",
    ),
    ("20261009_105554/step6_amp_out", "single", "Amplifier outputs", "step6_amp_out_spectrum"),
)
KIND_TITLES = {
    "single": "Single-ended",
    "diff": "Differential",
    "common": "Common-mode",
    "diffcm": "Differential and common-mode",
}

for capture, kind, title, name in FIGURES:
    scopes = []
    for record in ("slow", "fast"):
        scope = read_analysis(ROOT / "build/test_noise" / capture / f"{record}.h5")
        assert isinstance(scope, AnalysisScope)
        scopes.append(scope)
    traces = [
        trace
        for trace in scopes[0].spectrum_v_per_sqrt_hz
        if {
            "single": "-" not in trace and not trace.startswith("cm("),
            "diff": "-" in trace,
            "common": trace.startswith("cm("),
            "diffcm": "-" in trace or trace.startswith("cm("),
        }[kind]
    ]
    plot_spectrum(
        scopes,
        title=f"{KIND_TITLES[kind]} noise spectral density – {title}",
        signals={trace: trace for trace in traces},
        output_path=OUT_DIR / name,
    )
    print(f"{name}: {', '.join(traces)}")
