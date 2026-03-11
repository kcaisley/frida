#!/usr/bin/env python3
"""
analyze_sweep.py -- Analyze allpix-squared fluence sweep results

Reads ROOT output files from the sweep simulations and produces:
1. Per-pixel hit count distributions
2. Collected charge per pixel distributions
3. Summary table of hits/pixel and charge/pixel for each energy point
4. Fluence interpretation: hits per cm^2 for various beam conditions

Requires: ROOT (PyROOT) -- source thisroot.sh before running.

Usage:
    source ~/libs/root/bin/thisroot.sh
    python3 analyze_sweep.py
"""

import os
import sys
import glob
import json
from dataclasses import dataclass, field
from typing import Optional

# Attempt to import ROOT; give a clear error if not available
try:
    import ROOT

    ROOT.gROOT.SetBatch(True)
except ImportError:
    print("ERROR: PyROOT not found. Source thisroot.sh first:")
    print("  source ~/libs/root/bin/thisroot.sh")
    sys.exit(1)

# Load allpix-squared object dictionary so PyROOT can deserialize
# the allpix::PixelHit, allpix::PixelCharge, etc. classes from ROOT files.
_ALLPIX_LIB = os.path.expanduser(
    "~/libs/allpix-squared/build/src/objects/libAllpixObjects.so"
)
if os.path.exists(_ALLPIX_LIB):
    ROOT.gSystem.Load(_ALLPIX_LIB)
else:
    print(f"WARNING: allpix dictionary not found at {_ALLPIX_LIB}")
    print("         Charge readout from ROOT files will fail.")
    print("         Build allpix-squared or adjust the path.")


# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SWEEP_DIR = os.path.join(SCRIPT_DIR, "sweep_results")
PLOTS_DIR = os.path.join(SCRIPT_DIR, "plots")

# Detector geometry
# Allpix simulation uses 16x16 pixels for tractability,
# but the actual focal plane is 25mm x 25mm (500x500 pixels),
# diced from a 300mm wafer.
N_PIXELS_X = 500
N_PIXELS_Y = 500
PIXEL_PITCH_UM = 50.0
SENSOR_THICKNESS_UM = 50.0
PIXEL_AREA_CM2 = (PIXEL_PITCH_UM * 1e-4) ** 2  # cm^2 per pixel
SENSOR_AREA_CM2 = N_PIXELS_X * N_PIXELS_Y * PIXEL_AREA_CM2  # total active area
FOCAL_PLANE_MM = 25.0  # mm, side length of the diced focal plane

# Silicon charge creation energy
SI_CHARGE_CREATION_EV = 3.64  # eV per e-h pair


# Typical electron beam fluences (e/cm^2/s) for reference
FLUENCE_REGIMES = {
    "SEM_low": {"fluence": 1e6, "energy_keV": 10, "desc": "SEM low-dose imaging"},
    "SEM_standard": {"fluence": 1e8, "energy_keV": 20, "desc": "SEM standard imaging"},
    "SEM_high": {"fluence": 1e10, "energy_keV": 30, "desc": "SEM high-current"},
    "TEM_low": {"fluence": 1e4, "energy_keV": 200, "desc": "TEM low-dose cryo"},
    "TEM_standard": {"fluence": 1e6, "energy_keV": 200, "desc": "TEM standard imaging"},
    "TEM_high": {"fluence": 1e8, "energy_keV": 300, "desc": "TEM high-dose"},
    "STEM_probe": {"fluence": 1e10, "energy_keV": 200, "desc": "STEM focused probe"},
    "MedLINAC": {"fluence": 1e10, "energy_keV": 6e3, "desc": "Medical LINAC 6 MeV"},
    "TestBeam": {"fluence": 1e6, "energy_keV": 5e6, "desc": "CERN test beam 5 GeV"},
    "TestBeam_high": {"fluence": 1e8, "energy_keV": 1e6, "desc": "High-rate test beam"},
}


@dataclass
class SimResult:
    """Results from one simulation run."""

    label: str
    dedx_ehpairs_per_um: float
    n_events: int
    n_hits_total: int = 0
    charge_per_pixel: list = field(default_factory=list)  # collected charge per hit [e]
    hits_per_pixel: dict = field(default_factory=dict)  # pixel_id -> hit count


def analyze_one_run(label: str, run_dir: str) -> Optional[SimResult]:
    """Analyze a single simulation run from its ROOT output files."""

    data_file = os.path.join(run_dir, "data.root")
    if not os.path.exists(data_file):
        print(f"  WARNING: {data_file} not found, skipping {label}")
        return None

    # Extract dE/dx from label (encoded in sweep script)
    dedx_map = {
        "e_100keV": 40,
        "e_200keV": 30,
        "e_1MeV": 25,
        "e_5MeV": 27,
        "e_100MeV": 33,
        "e_1GeV": 35,
        "mip_mpv": 80,
        "mip_thin_mpv": 65,
    }
    dedx = dedx_map.get(label, 0)

    f = ROOT.TFile.Open(data_file, "READ")
    if not f or f.IsZombie():
        print(f"  WARNING: Cannot open {data_file}")
        return None

    result = SimResult(label=label, dedx_ehpairs_per_um=dedx, n_events=0)

    # Read PixelHit tree
    # The ROOTObjectWriter creates a tree named "PixelHit" with a branch
    # named after the detector ("dut") containing vector<allpix::PixelHit*>.
    # Ref: src/modules/ROOTObjectWriter/README.md
    tree = f.Get("PixelHit")
    if not tree:
        print(f"  WARNING: No PixelHit tree in {data_file}")
        f.Close()
        return result

    n_entries = tree.GetEntries()
    result.n_events = n_entries

    for i in range(n_entries):
        tree.GetEntry(i)

        # "dut" branch is a std::vector<allpix::PixelHit*>
        hits = tree.dut
        for j in range(hits.size()):
            pixel_hit = hits[j]
            signal = pixel_hit.getSignal()
            result.charge_per_pixel.append(signal)

            px = pixel_hit.getPixel().getIndex().X()
            py = pixel_hit.getPixel().getIndex().Y()
            pid = (px, py)
            result.hits_per_pixel[pid] = result.hits_per_pixel.get(pid, 0) + 1

    result.n_hits_total = len(result.charge_per_pixel)

    f.Close()
    return result


def print_summary_table(results: list):
    """Print a summary table of all simulation results."""

    print("\n" + "=" * 100)
    print("SIMULATION RESULTS SUMMARY")
    print("=" * 100)
    print(
        f"Detector: {N_PIXELS_X}x{N_PIXELS_Y} pixels, "
        f"{PIXEL_PITCH_UM:.0f}um pitch, {SENSOR_THICKNESS_UM:.0f}um thick Si"
    )
    print(f"Pixel area: {PIXEL_AREA_CM2:.2e} cm^2")
    print(f"Total active area: {SENSOR_AREA_CM2:.2e} cm^2")
    print("-" * 100)
    print(
        f"{'Label':<16} {'dE/dx':>8} {'Events':>8} {'Hits':>8} "
        f"{'Charge/hit':>12} {'Deposited':>12} {'Expected':>12}"
    )
    print(
        f"{'':<16} {'[e-h/um]':>8} {'':>8} {'total':>8} "
        f"{'[e] mean':>12} {'[keV]':>12} {'[e-h]':>12}"
    )
    print("-" * 100)

    for r in results:
        if r is None:
            continue

        expected_eh = r.dedx_ehpairs_per_um * SENSOR_THICKNESS_UM
        mean_charge = 0
        deposited_keV = 0
        if r.charge_per_pixel:
            mean_charge = sum(r.charge_per_pixel) / len(r.charge_per_pixel)
            deposited_keV = mean_charge * SI_CHARGE_CREATION_EV / 1000.0

        print(
            f"{r.label:<16} {r.dedx_ehpairs_per_um:>8.0f} {r.n_events:>8d} "
            f"{r.n_hits_total:>8d} {mean_charge:>12.1f} "
            f"{deposited_keV:>12.2f} {expected_eh:>12.0f}"
        )

    print("=" * 100)


def print_fluence_table():
    """Print a reference table of fluences for different applications."""

    print("\n" + "=" * 100)
    print("ELECTRON BEAM FLUENCE REFERENCE")
    print("=" * 100)
    print(
        f"{'Application':<20} {'Energy':>12} {'Fluence':>15} "
        f"{'Hits/pixel/s':>15} {'Hits/pixel/frame':>18}"
    )
    print(f"{'':<20} {'':>12} {'[e/cm^2/s]':>15} {'':>15} {'(1ms frame)':>18}")
    print("-" * 100)

    for name, params in FLUENCE_REGIMES.items():
        fluence = params["fluence"]
        energy = params["energy_keV"]
        desc = params["desc"]

        hits_per_pixel_per_s = fluence * PIXEL_AREA_CM2
        hits_per_frame_1ms = hits_per_pixel_per_s * 1e-3

        if energy >= 1e6:
            energy_str = f"{energy / 1e6:.0f} GeV"
        elif energy >= 1e3:
            energy_str = f"{energy / 1e3:.0f} MeV"
        else:
            energy_str = f"{energy:.0f} keV"

        print(
            f"{desc:<20} {energy_str:>12} {fluence:>15.1e} "
            f"{hits_per_pixel_per_s:>15.2e} {hits_per_frame_1ms:>18.4f}"
        )

    print("=" * 100)

    print("\nNOTE: Hits/pixel/s = fluence * pixel_area")
    print(f"      pixel_area = ({PIXEL_PITCH_UM:.0f}um)^2 = {PIXEL_AREA_CM2:.2e} cm^2")
    print("      For a 1 ms frame readout time, multiply hits/pixel/s by 1e-3")
    print("      For a 25 ns LHC bunch crossing, multiply hits/pixel/s by 25e-9")


def make_plots(results: list):
    """Generate summary plots if matplotlib is available."""

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\nINFO: matplotlib not available, skipping plots.")
        print("      Install with: pip install matplotlib numpy")
        return

    # LaTeX serif font style (matches flow/verify/plot.py)
    plt.rcParams.update(
        {
            "text.usetex": True,
            "font.family": "serif",
            "font.serif": ["Computer Modern Roman"],
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )

    os.makedirs(PLOTS_DIR, exist_ok=True)

    # --- Plot 1: Expected deposited charge vs electron energy ---
    energies_keV = [100, 200, 1e3, 5e3, 1e5, 1e6]
    dedx_values = [40, 30, 25, 27, 33, 35]
    total_charge = [d * SENSOR_THICKNESS_UM for d in dedx_values]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.semilogx(energies_keV, total_charge, "bo-", markersize=8, linewidth=2)
    ax1.axhline(
        y=80 * SENSOR_THICKNESS_UM,
        color="r",
        linestyle="--",
        label=f"MIP MPV = {80 * SENSOR_THICKNESS_UM:.0f} e-h",
    )
    ax1.axhline(
        y=65 * SENSOR_THICKNESS_UM,
        color="orange",
        linestyle="--",
        label=f"Thin sensor MPV = {65 * SENSOR_THICKNESS_UM:.0f} e-h",
    )
    ax1.set_xlabel("Electron Energy [keV]")
    ax1.set_ylabel(r"Total e-h pairs in 50\,\textmu{}m Si")
    ax1.set_title(
        r"Charge Deposition vs Electron Energy"
        "\n"
        r"(restricted $\mathrm{d}E/\mathrm{d}x$, no delta rays)",
    )
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(bottom=0)

    plt.tight_layout()
    outfile = os.path.join(PLOTS_DIR, "charge_vs_energy.pdf")
    plt.savefig(outfile)
    print(f"  Saved: {outfile}")
    plt.close()

    # --- Plot 2: Hit rate per pixel vs fluence ---
    # One line per pixel pitch; horizontal range indicators along bottom
    # for microscope regimes. Nord color palette throughout.
    #
    # Nord palette reference:
    #   nord0  #2E3440  (dark bg)     nord7  #8FBCBB  (teal)
    #   nord1  #3B4252              nord8  #88C0D0  (light blue)
    #   nord2  #434C5E              nord9  #81A1C1  (blue)
    #   nord3  #4C566A              nord10 #5E81AC  (dark blue)
    #   nord4  #D8DEE9  (light fg)  nord11 #BF616A  (red)
    #   nord5  #E5E9F0              nord12 #D08770  (orange)
    #   nord6  #ECEFF4              nord13 #EBCB8B  (yellow)
    #                               nord14 #A3BE8C  (green)
    #                               nord15 #B48EAD  (purple)
    nord = {
        "bg": "#2E3440",
        "fg": "#D8DEE9",
        "fg_dim": "#4C566A",
        "blue": "#5E81AC",
        "lblue": "#81A1C1",
        "teal": "#8FBCBB",
        "cyan": "#88C0D0",
        "red": "#BF616A",
        "orange": "#D08770",
        "yellow": "#EBCB8B",
        "green": "#A3BE8C",
        "purple": "#B48EAD",
    }

    fluences = np.logspace(2, 12, 200)
    pixel_pitches_um = [10, 20, 35, 50]
    pitch_colors = [nord["cyan"], nord["teal"], nord["lblue"], nord["blue"]]

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor("white")

    for pitch_um, lc in zip(pixel_pitches_um, pitch_colors):
        area_cm2 = (pitch_um * 1e-4) ** 2
        hits = fluences * area_cm2
        ax.loglog(
            fluences,
            hits,
            "-",
            color=lc,
            linewidth=2.2,
            label=rf"{pitch_um}\,\textmu{{}}m pixel",
        )

    # Fluence regimes as horizontal range indicators below the plot area,
    # staggered vertically like overlapping spans on a timeline.
    # Derived from beam current ranges and detection fractions,
    # assuming electrons spread uniformly over 1 cm^2 detector.
    #   fluence = (I / e) * detection_fraction
    #
    # TEM:  10 pA – 1 nA,  10–50% detected  => 6.2e6 – 3.1e9 e/cm^2/s
    # SEM:  1 pA – 10 nA,  0.1–2% detected  => 6.2e3 – 1.2e9 e/cm^2/s
    # STEM: 10 pA – 1 nA,  5–40% detected   => 3.1e6 – 2.5e9 e/cm^2/s
    e_charge = 1.602e-19

    regime_bands = [
        {
            "label": "SEM",
            "I_lo": 1e-12,
            "I_hi": 10e-9,
            "frac_lo": 0.001,
            "frac_hi": 0.02,
            "color": nord["green"],
        },
        {
            "label": "TEM",
            "I_lo": 10e-12,
            "I_hi": 1e-9,
            "frac_lo": 0.10,
            "frac_hi": 0.50,
            "color": nord["orange"],
        },
        {
            "label": "STEM",
            "I_lo": 10e-12,
            "I_hi": 1e-9,
            "frac_lo": 0.05,
            "frac_hi": 0.40,
            "color": nord["purple"],
        },
        {
            # ELSA (Bonn): 3.2 GeV electron beam, direct beam on detector.
            # Rate: few kHz (~1e3 e/s) up to 100 pA (~6.2e8 e/s).
            # Detection fraction ~100% (direct beam), 1 cm^2 detector.
            "label": "ELSA",
            "I_lo": None,
            "I_hi": None,
            "frac_lo": None,
            "frac_hi": None,
            "fl_lo_override": 1e3,
            "fl_hi_override": 100e-12 / e_charge,  # 100 pA
            "color": nord["red"],
        },
    ]

    # Reserve space below the plot for the range indicators.
    # We use a secondary axes below the main plot, sharing the same x-axis.
    y_lo, y_hi = 1e-4, 1e8

    # Restructure: create figure with two vertically stacked axes.
    # Top = main plot, bottom = regime range bars.
    plt.close(fig)  # close the fig we already created
    fig, (ax, ax_bars) = plt.subplots(
        2,
        1,
        figsize=(12, 7.5),
        gridspec_kw={"height_ratios": [6, 1], "hspace": 0.02},
        sharex=True,
    )
    fig.patch.set_facecolor("white")

    # Re-draw the pitch lines on the new axes
    for pitch_um, lc in zip(pixel_pitches_um, pitch_colors):
        area_cm2 = (pitch_um * 1e-4) ** 2
        hits = fluences * area_cm2
        ax.loglog(
            fluences,
            hits,
            "-",
            color=lc,
            linewidth=2.2,
            label=rf"{pitch_um}\,\textmu{{}}m pixel",
        )

    ax.set_xlim(1e3, 1e12)
    ax.set_ylim(y_lo, y_hi)
    ax.set_ylabel("Hits per pixel per second")
    ax.set_title("Hit Rate vs Fluence for Different Pixel Pitches")

    # --- Detector readout capability markers (horizontal y-axis lines/bands) ---
    # These show the max hit rate each detector can sustain, plotted as
    # horizontal lines/bands because they constrain hits/pixel/s (y-axis).

    # OBELIX-1: 120 MHz/cm^2 max readout rate.
    # Convert to hits/pixel/s for each pitch shown on the plot.
    # For the reference 50um pitch: 120e6 * (50e-4)^2 = 3000 hits/pixel/s
    obelix_rate_cm2 = 120e6  # hits/cm^2/s
    obelix_50um = obelix_rate_cm2 * (50e-4) ** 2  # 3000 hits/pixel/s at 50um
    ax.axhline(
        y=obelix_50um,
        color=nord["red"],
        linestyle="--",
        linewidth=1.5,
        alpha=0.7,
        zorder=2,
    )
    ax.text(
        1.02,
        obelix_50um,
        r"OBELIX-1" "\n" r"120\,MHz/cm$^2$",
        ha="left",
        va="center",
        fontsize=7,
        color=nord["red"],
        fontstyle="italic",
        transform=ax.get_yaxis_transform(),
        clip_on=False,
        zorder=5,
    )

    # EDET DH80k: 60um pixel, 80 kHz frame rate, 1-100 e-/pixel/frame.
    # Hit rate range: 80e3*1 = 8e4 to 80e3*100 = 8e6 hits/pixel/s.
    # Shown as a horizontal band spanning the full x-axis.
    edet_lo = 8e4  # hits/pixel/s (1 e-/pixel/frame * 80 kHz)
    edet_hi = 8e6  # hits/pixel/s (100 e-/pixel/frame * 80 kHz)
    ax.axhspan(
        edet_lo,
        edet_hi,
        color=nord["yellow"],
        alpha=0.10,
        zorder=1,
    )
    ax.axhline(y=edet_lo, color=nord["yellow"], linestyle=":", linewidth=1.0, alpha=0.4)
    ax.axhline(y=edet_hi, color=nord["yellow"], linestyle=":", linewidth=1.0, alpha=0.4)
    ax.text(
        1.02,
        np.sqrt(edet_lo * edet_hi),
        r"EDET DH80k" "\n" r"80\,kHz, 60\,\textmu{}m",
        ha="left",
        va="center",
        fontsize=7,
        color="#b8a434",  # darker gold for readability on white
        fontstyle="italic",
        transform=ax.get_yaxis_transform(),
        clip_on=False,
        zorder=5,
    )

    ax.legend(fontsize=10, loc="upper left")
    ax.grid(True, alpha=0.15, which="both")

    # Footnote on main axes
    ax.text(
        0.99,
        0.01,
        r"Beam spread across 25$\times$25\,mm focal plane ($\approx$ reticle scale)",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        fontstyle="italic",
        color="gray",
    )

    # --- Bottom strip: regime range bars ---
    ax_bars.set_xscale("log")
    ax_bars.set_xlim(1e3, 1e12)
    ax_bars.set_ylim(0, 1)
    ax_bars.set_xlabel(r"Fluence [electrons/cm$^2$/s]")

    # Remove y-axis ticks/labels and most spines on the bar strip
    ax_bars.set_yticks([])
    ax_bars.spines["left"].set_visible(False)
    ax_bars.spines["right"].set_visible(False)
    ax_bars.spines["top"].set_visible(False)

    n_bands = len(regime_bands)
    bar_height = 0.18
    bar_gap = 0.04
    # Stack from bottom up, centered vertically
    total_height = n_bands * bar_height + (n_bands - 1) * bar_gap
    y_start = (1.0 - total_height) / 2

    for i, band in enumerate(regime_bands):
        if "fl_lo_override" in band:
            fl_lo = band["fl_lo_override"]
            fl_hi = band["fl_hi_override"]
        else:
            fl_lo = band["I_lo"] * band["frac_lo"] / e_charge
            fl_hi = band["I_hi"] * band["frac_hi"] / e_charge

        bar_bottom = y_start + i * (bar_height + bar_gap)

        # Use axhspan-style fill between fl_lo and fl_hi
        ax_bars.fill_between(
            [fl_lo, fl_hi],
            bar_bottom,
            bar_bottom + bar_height,
            color=band["color"],
            alpha=0.45,
            edgecolor=band["color"],
            linewidth=1.5,
            zorder=3,
        )

        # Rounded end-caps via thin bars at edges (visual polish)
        # Label centered on the bar
        x_center = np.sqrt(fl_lo * fl_hi)
        ax_bars.text(
            x_center,
            bar_bottom + bar_height / 2,
            band["label"],
            ha="center",
            va="center",
            fontsize=9,
            color="black",
            fontweight="bold",
            zorder=4,
        )

    plt.tight_layout()
    fig.subplots_adjust(hspace=0.02, right=0.85)  # margin for y-axis labels
    outfile = os.path.join(PLOTS_DIR, "hitrate_vs_fluence.pdf")
    plt.savefig(outfile)
    print(f"  Saved: {outfile}")
    plt.close()

    # --- Plot 3: Charge distribution per simulation point ---
    valid_results = [r for r in results if r is not None and r.charge_per_pixel]
    if valid_results:
        fig, ax = plt.subplots(figsize=(10, 6))
        for r in valid_results:
            if r.charge_per_pixel:
                ax.hist(
                    r.charge_per_pixel,
                    bins=50,
                    alpha=0.5,
                    label=rf"{r.label} ({r.dedx_ehpairs_per_um}/\textmu{{}}m)",
                    histtype="step",
                    linewidth=1.5,
                )

        ax.set_xlabel("Collected Charge per Pixel [e]")
        ax.set_ylabel("Entries")
        ax.set_title("Charge Collection Distribution by Energy Point")
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        outfile = os.path.join(PLOTS_DIR, "charge_distributions.pdf")
        plt.savefig(outfile)
        print(f"  Saved: {outfile}")
        plt.close()


def main():
    print("=" * 60)
    print("Allpix Squared Fluence Sweep Analysis")
    print("=" * 60)

    # Always print the fluence reference table
    print_fluence_table()

    # Check if sweep results exist
    if not os.path.isdir(SWEEP_DIR):
        print(f"\nINFO: Sweep results directory not found: {SWEEP_DIR}")
        print("      Run the simulation first: bash run_sweep.sh")
        print("      Showing reference tables only.\n")
        return

    # Analyze each run
    run_dirs = sorted(glob.glob(os.path.join(SWEEP_DIR, "*")))
    if not run_dirs:
        print(f"\nINFO: No results found in {SWEEP_DIR}")
        return

    results = []
    for run_dir in run_dirs:
        if not os.path.isdir(run_dir):
            continue
        label = os.path.basename(run_dir)
        print(f"\nAnalyzing: {label} ...")
        result = analyze_one_run(label, run_dir)
        results.append(result)

    # Summary
    print_summary_table(results)

    # Make plots
    print("\nGenerating plots...")
    make_plots(results)

    # Save summary as JSON
    summary = []
    for r in results:
        if r is None:
            continue
        expected_eh = r.dedx_ehpairs_per_um * SENSOR_THICKNESS_UM
        mean_charge = (
            sum(r.charge_per_pixel) / len(r.charge_per_pixel)
            if r.charge_per_pixel
            else 0
        )
        summary.append(
            {
                "label": r.label,
                "dedx_ehpairs_per_um": r.dedx_ehpairs_per_um,
                "expected_total_eh": expected_eh,
                "n_events": r.n_events,
                "n_hits": r.n_hits_total,
                "mean_collected_charge_e": round(mean_charge, 1),
                "deposited_energy_keV": round(
                    mean_charge * SI_CHARGE_CREATION_EV / 1000, 2
                ),
                "charge_collection_efficiency": (
                    round(mean_charge / expected_eh, 3) if expected_eh > 0 else None
                ),
            }
        )

    summary_file = os.path.join(SWEEP_DIR, "summary.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary: {summary_file}")


if __name__ == "__main__":
    main()
