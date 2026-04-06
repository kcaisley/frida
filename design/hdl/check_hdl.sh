#!/usr/bin/env bash
# Lint and syntax-check all cosim HDL and SPICE files.
#
# Usage (from repo root):
#   bash design/hdl/check_hdl.sh
#
# Requires: iverilog, verilator, ngspice on PATH.
# Optional: xrun, spectre (source /eda/local/scripts/cadence_2024-25.sh)

set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

# Source Cadence tools if available (xrun, spectre)
CADENCE_SETUP=/eda/local/scripts/cadence_2024-25.sh
if [ -f "$CADENCE_SETUP" ]; then
    source "$CADENCE_SETUP" > /dev/null 2>&1
fi

# =====================================================================
# Files under test
# =====================================================================

# Verilog files that run in the digital simulator during cosim.
# Modules inside the ADC (clkgate, salogic, sampdriver, capdriver) are
# replaced by SPICE and excluded here.
VERILOG_COSIM=(
    design/hdl/tb_integration.v
    design/hdl/frida_core_1chan.v
    design/hdl/sediff_stub.v
    design/hdl/spi_register.v
    design/hdl/adc_stub.v     # empty stub — body replaced by SPICE
)

SPICE_SUBCIRCUITS=(
    design/spice/sediff.sp
    design/spice/ths4541.sp
    design/spice/comp.cdl
    design/spice/caparray.cdl
    design/spice/capdriver.cdl
    design/spice/adc_digital.cdl
    design/spice/adc.cdl
)

SPICE_WRAPPER=design/spice/tb_adc.sp
AMS_CONTROL=design/spice/amscontrol.scs

# =====================================================================
# Counters
# =====================================================================
PASS=0
FAIL=0
SKIP=0

run_check() {
    local name="$1"
    shift
    printf "  %-45s " "$name"
    if output=$("$@" 2>&1); then
        echo "PASS"
        ((PASS++))
    else
        echo "FAIL"
        echo "$output" | head -15 | sed 's/^/    /'
        ((FAIL++))
    fi
}

skip_check() {
    local name="$1"
    local reason="$2"
    printf "  %-45s SKIP (%s)\n" "$name" "$reason"
    ((SKIP++))
}

# =====================================================================
# 1. Iverilog — cosim files (spicebind path)
# =====================================================================
echo ""
echo "=== Icarus Verilog ==="

if command -v iverilog &>/dev/null; then
    BASIL_INC=(-Ilibs/basil/basil/firmware/modules -Ilibs/basil/basil/firmware/modules/utils)
    BASIL_SIM=(libs/basil/basil/firmware/modules/utils/RAMB16_S1_S9_sim.v)

    run_check "cosim (spicebind, -DSPICEBIND)" \
        iverilog -DSPICEBIND -o /dev/null -Idesign/hdl -Idesign/fpga \
        "${BASIL_INC[@]}" \
        "${BASIL_SIM[@]}" \
        design/fpga/daq_core.v \
        "${VERILOG_COSIM[@]}"

    run_check "cosim (Xcelium path, no define)" \
        iverilog -o /dev/null -Idesign/hdl -Idesign/fpga \
        "${BASIL_INC[@]}" \
        "${BASIL_SIM[@]}" \
        design/fpga/daq_core.v \
        "${VERILOG_COSIM[@]}"
else
    skip_check "iverilog" "not on PATH"
fi

# =====================================================================
# 2. Verilator — lint only
# =====================================================================
echo ""
echo "=== Verilator ==="

if command -v verilator &>/dev/null; then
    # Cosim files only (not FPGA — Xilinx primitives won't resolve)
    run_check "cosim lint (-DSPICEBIND)" \
        verilator --lint-only -Wall -Wno-UNUSEDSIGNAL -Wno-MULTITOP -Wno-TIMESCALEMOD -Wno-DECLFILENAME -Wno-UNDRIVEN \
        -DSPICEBIND -Idesign/hdl \
        design/hdl/frida_core_1chan.v \
        design/hdl/sediff_stub.v \
        design/hdl/spi_register.v \
        design/hdl/adc_stub.v \
        design/hdl/comp.v \
        design/hdl/sampswitch.v \
        design/hdl/caparray.v
else
    skip_check "verilator" "not on PATH"
fi

# =====================================================================
# 3. ngspice — syntax check subcircuits
# =====================================================================
echo ""
echo "=== ngspice ==="

if command -v ngspice &>/dev/null; then
    for f in "${SPICE_SUBCIRCUITS[@]}"; do
        name="parse $(basename "$f")"
        # ngspice returns "incomplete netlist" for subcircuit-only files,
        # which is fine — we just check there are no parse errors
        printf "  %-45s " "$name"
        output=$(ngspice -b -o /dev/null "$f" 2>&1 || true)
        if echo "$output" | grep -qi "error on line\|syntax error\|unknown parameter"; then
            echo "FAIL"
            echo "$output" | grep -i "error" | head -5 | sed 's/^/    /'
            ((FAIL++))
        else
            echo "PASS"
            ((PASS++))
        fi
    done
else
    skip_check "ngspice" "not on PATH"
fi

# =====================================================================
# 4. Port name matching (Verilog stubs vs SPICE .subckt pins)
# =====================================================================
echo ""
echo "=== Port Matching ==="

# Extract port names from a Verilog stub (grep for input/output/inout lines)
verilog_ports() {
    grep -oE '\b(input|output|inout)\b.*' "$1" \
        | sed 's/.*\b\(input\|output\|inout\)\b//; s/wire\|real\|wreal\|reg//g' \
        | tr ',' '\n' | sed 's|//.*||; s/[[:space:]]//g; s/\[.*\]//g' \
        | grep -v '^$' | tr '[:upper:]' '[:lower:]' | sort -u
}

# Extract pin names from a SPICE .subckt line (first .subckt in file)
spice_ports() {
    grep -i "^\.subckt $2 " "$1" \
        | sed "s/^\.subckt $2 //I" \
        | tr ' ' '\n' | sed 's/\[.*\]//g' \
        | grep -v '^$' | tr '[:upper:]' '[:lower:]' | sort -u
}

check_ports() {
    local label="$1" vfile="$2" spfile="$3" subckt="$4"
    printf "  %-45s " "$label"
    local vports spports
    vports=$(verilog_ports "$vfile")
    spports=$(spice_ports "$spfile" "$subckt")
    local diff
    diff=$(diff <(echo "$vports") <(echo "$spports") || true)
    if [ -z "$diff" ]; then
        echo "PASS"
        ((PASS++))
    else
        echo "FAIL"
        echo "$diff" | head -10 | sed 's/^/    /'
        ((FAIL++))
    fi
}

check_ports "sediff: stub vs .subckt" design/hdl/sediff_stub.v design/spice/sediff.sp sediff
check_ports "adc: stub vs .subckt"    design/hdl/adc_stub.v design/spice/adc.cdl adc

# =====================================================================
# 5. Xcelium (xrun) — compile + elaborate with AMS
# =====================================================================
echo ""
echo "=== Xcelium ==="

if command -v xrun &>/dev/null; then
    run_check "compile (Verilog only, -ams)" \
        xrun -compile -ams \
        design/fpga/daq_core.v \
        "${VERILOG_COSIM[@]}" \
        -incdir design/hdl -incdir design/fpga \
        -incdir libs/basil/basil/firmware/modules \
        -incdir libs/basil/basil/firmware/modules/utils \
        -top tb_integration

    run_check "compile + elaborate (-ams, with SPICE)" \
        xrun -elaborate -ams \
        design/fpga/daq_core.v \
        libs/basil/basil/firmware/modules/utils/RAMB16_S1_S9_sim.v \
        "${VERILOG_COSIM[@]}" \
        "$AMS_CONTROL" \
        design/spice/sediff.sp \
        design/spice/ths4541.sp \
        -spice_ext .scs,.sp,.cdl \
        design/spice/comp.cdl \
        design/spice/caparray.cdl \
        design/spice/capdriver.cdl \
        design/spice/adc_digital.cdl \
        design/spice/adc.cdl \
        -incdir design/hdl -incdir design/fpga \
        -incdir libs/basil/basil/firmware/modules \
        -incdir libs/basil/basil/firmware/modules/utils \
        -top tb_integration
else
    skip_check "xrun" "not on PATH (source /eda/local/scripts/cadence_2024-25.sh)"
fi

# =====================================================================
# Summary
# =====================================================================
echo ""
echo "========================================"
printf "  PASS: %d  FAIL: %d  SKIP: %d\n" "$PASS" "$FAIL" "$SKIP"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
