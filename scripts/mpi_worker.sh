#!/bin/bash
# MPI worker wrapper - sources Cadence environment and runs Python
# Used by: mpirun --hostfile hosts.openmpi scripts/mpi_worker.sh flow/simulate.py ...

# Source Cadence tools
source /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh 2>/dev/null || true

# Set license server and PyOPUS local storage
export CDS_LIC_FILE="${CDS_LIC_FILE:-27500@nexus.physik.uni-bonn.de}"
export PARALLEL_LOCAL_STORAGE="${PARALLEL_LOCAL_STORAGE:-/tmp}"

# Run Python with PYTHONPATH
PYTHONPATH=. .venv/bin/python "$@"
