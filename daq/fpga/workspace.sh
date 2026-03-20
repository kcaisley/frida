#!/bin/bash
# FRIDA DAQ workspace setup
# Usage: source workspace.sh

# --- Vivado / Vitis HLS environment ---
source /eda/local/scripts/vivado_2025.2.sh

echo "Vivado: $(vivado -version 2>/dev/null | head -1)"

# --- BDAQ / Enclustra network settings ---
BDAQ_IP="192.168.10.16"
BDAQ_IFACE="enp3s0"

echo ""
echo "=== BDAQ-core connectivity ==="

# Check that the local interface has an IP on the BDAQ subnet
LOCAL_IP=$(ip -4 addr show "$BDAQ_IFACE" 2>/dev/null | grep -oP 'inet 192\.168\.10\.\d+')
if [ -n "$LOCAL_IP" ]; then
    echo "$BDAQ_IFACE: configured ($LOCAL_IP)"
    # Check if the board itself is reachable
    if ping -c 1 -W 1 "$BDAQ_IP" &>/dev/null; then
        echo "BDAQ board ($BDAQ_IP): OK"
    else
        echo "BDAQ board ($BDAQ_IP): UNREACHABLE (check cable/power)"
    fi
else
    echo "$BDAQ_IFACE: no 192.168.10.x address configured"
    echo "  Run: sudo ip addr add 192.168.10.1/24 dev $BDAQ_IFACE"
fi

# Check JTAG (Xilinx hw_server)
echo ""
echo "=== JTAG scan ==="
echo "Starting hw_server probe (this may take a few seconds)..."
vivado -mode batch -nojournal -nolog -source /dev/stdin <<'TCL' 2>/dev/null
open_hw_manager
connect_hw_server -allow_non_jtag
foreach target [get_hw_targets] {
    puts "Found JTAG target: $target"
    open_hw_target $target
    foreach device [get_hw_devices] {
        puts "  Device: $device"
    }
    close_hw_target
}
close_hw_manager
TCL
