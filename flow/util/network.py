"""Check DAQ network connectivity.

Verifies that the host network interface is configured and that
all devices on the DAQ LAN (FPGA, oscilloscope) are reachable.

Usage (from repo root):
    uv run python flow/util/network.py

Network layout (192.168.10.0/24 on enp3s0):
    .1   — host (asiclab003)
    .16  — FPGA (SiTcp, hardcoded in daq_top.v)
    .18  — oscilloscope (Tektronix MSO54)
"""

from __future__ import annotations

import socket
import subprocess
import sys

# --- Configuration ---

INTERFACE = "enp3s0"
SUBNET = "192.168.10"
HOST_IP = f"{SUBNET}.1"

DEVICES = {
    "FPGA (SiTcp)": {
        "ip": f"{SUBNET}.16",
        "tcp_port": 24,
    },
    "Oscilloscope": {
        "ip": f"{SUBNET}.18",
    },
}


def _check_interface() -> bool:
    """Check that the host network interface has the right IP."""
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", INTERFACE],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        print("  SKIP: 'ip' command not found")
        return False

    if result.returncode != 0:
        print(f"  FAIL: Interface {INTERFACE} not found")
        return False

    if HOST_IP not in result.stdout:
        print(f"  FAIL: {INTERFACE} does not have {HOST_IP}")
        print("  Fix with:")
        print("    sudo nmcli connection add type ethernet con-name fpga-lan \\")
        print(f"        ifname {INTERFACE} ipv4.method manual ipv4.addresses {HOST_IP}/24")
        print("    sudo nmcli connection up fpga-lan")
        return False

    print(f"  OK:   {INTERFACE} has {HOST_IP}/24")
    return True


def _check_ping(name: str, ip: str) -> bool:
    """Ping a device."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError:
        print("  SKIP: 'ping' command not found")
        return False

    if result.returncode == 0:
        print(f"  OK:   {name} ({ip}) responds to ping")
        return True
    else:
        print(f"  FAIL: {name} ({ip}) not reachable")
        return False


def _check_tcp(name: str, ip: str, port: int) -> bool:
    """Check that a TCP port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((ip, port))
        sock.close()
        print(f"  OK:   {name} TCP port {port} open")
        return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        print(f"  FAIL: {name} TCP port {port} not reachable")
        return False


def check_network() -> bool:
    """Run all network checks. Returns True if all pass."""
    all_ok = True

    print("Host interface:")
    if not _check_interface():
        all_ok = False

    print("\nDevices:")
    for name, info in DEVICES.items():
        ip = info["ip"]
        if not _check_ping(name, ip):
            all_ok = False
            continue
        if "tcp_port" in info:
            if not _check_tcp(name, ip, info["tcp_port"]):
                all_ok = False

    print()
    if all_ok:
        print("PASS: All network checks passed")
    else:
        print("FAIL: Some checks failed (see above)")

    return all_ok


if __name__ == "__main__":
    ok = check_network()
    sys.exit(0 if ok else 1)
