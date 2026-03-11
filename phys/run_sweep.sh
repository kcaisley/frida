#!/bin/bash
# ==============================================================================
# run_sweep.sh -- Fluence sweep for electron beam simulation
#
# Runs allpix-squared simulations across a range of electron beam conditions
# spanning electron microscopy (SEM/TEM) through accelerator beamlines.
#
# FLUENCE REGIMES (electrons / cm^2 / s):
# -----------------------------------------------------------------------
# Application            Energy        Typical Fluence (e/cm^2/s)
# -----------------------------------------------------------------------
# SEM imaging            1-30 keV      1e6 - 1e10
# TEM imaging            80-300 keV    1e4 - 1e8
# STEM probe             80-300 keV    1e8 - 1e12
# Electron diffraction   100-300 keV   1e2 - 1e6
# Medical LINAC          4-20 MeV      1e8 - 1e12
# Physics beamline       1-10 GeV      1e4 - 1e8 (typical test beam)
# -----------------------------------------------------------------------
#
# CHARGE DEPOSITION (e-h pairs / um in Si):
# -----------------------------------------------------------------------
# Energy        dE/dx approx      e-h pairs/um    Notes
# -----------------------------------------------------------------------
# 10 keV        ~full stop         N/A             Stops in <5um Si (*)
# 30 keV        ~full stop         N/A             Stops in ~10um Si (*)
# 100 keV       ~0.5 MeV cm2/g    ~40/um          Sub-MIP, high scatter
# 200 keV       ~0.35 MeV cm2/g   ~30/um          Approaching MIP
# 1 MeV         ~0.27 MeV cm2/g   ~25/um          Near MIP minimum
# 5 MeV         ~0.30 MeV cm2/g   ~27/um          MIP-like
# 100 MeV       ~0.38 MeV cm2/g   ~33/um          Relativistic rise
# 1 GeV         ~0.40 MeV cm2/g   ~35/um          Fermi plateau
# MIP (generic) ~0.39 MeV cm2/g   ~80/um (MPV)    Most-probable Landau
# -----------------------------------------------------------------------
# (*) Electrons below ~50 keV stop within 50um Si. DepositionPointCharge
#     MIP model is NOT valid here -- it assumes straight-through tracks.
#     Results for <100 keV are included for comparison but are NOT physical.
#
# NOTE: The "80/um" MIP value is the most-probable Landau value including
# delta rays. The restricted dE/dx (mean without delta rays) gives ~30/um.
# For a 50um thin sensor, the most-probable value is closer to 60-70/um.
# We use several values to bracket the physics.
# ==============================================================================

set -euo pipefail

# Path to allpix-squared executable
ALLPIX="${ALLPIX_BIN:-$HOME/libs/allpix-squared/build/src/exec/allpix}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_CONF="${SCRIPT_DIR}/simulation.conf"

# Source ROOT environment (needed for allpix libraries)
source "${HOME}/libs/root/bin/thisroot.sh"

# Output base directory
OUTPUT_BASE="${SCRIPT_DIR}/sweep_results"
mkdir -p "${OUTPUT_BASE}"

# ==============================================================================
# Define sweep points
# Each line: label  energy_keV  ehpairs_per_um  num_events
#
# num_events represents the number of electrons hitting the 20x20 pixel
# sensor (1mm x 1mm = 1e-2 cm^2). We simulate a fixed batch per condition.
# The fluence interpretation is done in the analysis script.
# ==============================================================================
SWEEP_POINTS=(
    # Label          dE/dx(e-h/um)  Events  Notes
    "e_100keV        40             5000    sub-MIP_electron"
    "e_200keV        30             5000    near-MIP_electron"
    "e_1MeV          25             5000    MIP-minimum_electron"
    "e_5MeV          27             5000    MIP-like_electron"
    "e_100MeV        33             5000    relativistic-rise_electron"
    "e_1GeV          35             5000    Fermi-plateau_electron"
    "mip_mpv         80             5000    MIP_most-probable-value"
    "mip_thin_mpv    65             5000    thin-sensor_MPV_50um"
)

echo "============================================================"
echo "Electron fluence sweep for 50um Si pixel detector"
echo "Detector: 20x20 pixels, 50um pitch, 50um thick"
echo "Active area: 1mm x 1mm = 1e-2 cm^2"
echo "============================================================"
echo ""

for POINT in "${SWEEP_POINTS[@]}"; do
    # Parse sweep point parameters
    read -r LABEL EHPAIRS NEVENTS NOTES <<< "${POINT}"

    OUTDIR="${OUTPUT_BASE}/${LABEL}"
    mkdir -p "${OUTDIR}"

    echo "--------------------------------------------------------------"
    echo "Running: ${LABEL}"
    echo "  dE/dx: ${EHPAIRS} e-h pairs/um"
    echo "  Events: ${NEVENTS}"
    echo "  Notes: ${NOTES}"
    echo "  Output: ${OUTDIR}"
    echo "--------------------------------------------------------------"

    # Run allpix-squared with overridden parameters
    # Ref: doc/usermanual/04_framework/03_configuration.md -- CLI overrides
    # The -o flag overrides any parameter in the config file
    "${ALLPIX}" \
        -c "${BASE_CONF}" \
        -o "number_of_events=${NEVENTS}" \
        -o "output_directory=${OUTDIR}" \
        -o "DepositionPointCharge.number_of_charges=${EHPAIRS}/um" \
        -o "random_seed=$(shuf -i 1-999999 -n 1)" \
        2>&1 | tee "${OUTDIR}/allpix.log"

    echo "  -> Done: ${LABEL}"
    echo ""
done

echo "============================================================"
echo "All simulations complete."
echo "Results in: ${OUTPUT_BASE}/"
echo ""
echo "Run the analysis script:"
echo "  python3 analyze_sweep.py"
echo "============================================================"
