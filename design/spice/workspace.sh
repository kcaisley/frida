#!/usr/bin/env bash
# Source this file before running local Spectre/Xcelium SPICE/AMS simulations:
#   source ./workspace.sh
#
# This intentionally sets up only the simulator tools. It does not create or copy
# Cadence workspace files such as cds.lib, .cdsinit, .cdsenv, or display.drf.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "This script must be sourced, not executed: source ./workspace.sh" >&2
    exit 1
fi

export CDS_LIC_FILE="27500@nexus.physik.uni-bonn.de"
export CDS_AUTO_64BIT=ALL

source /eda/cadence/2024-25/scripts/XCELIUM_24.03.004_RHELx86.sh
source /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh
