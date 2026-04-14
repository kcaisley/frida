"""FRIDA1 FPGA management: download SiTCP, compile, and flash bitstreams.

Usage (from ~/frida/):
    python design/fpga/manage.py --get_sitcp
    python design/fpga/manage.py --compile BDAQ53_KX1
    python design/fpga/manage.py --flash design/fpga/bit/frida_bdaq53_kx1.bit
    python design/fpga/manage.py --flash design/fpga/bit/frida_bdaq53_kx1.mcs
"""

import time
import logging
import argparse
import fileinput
from pathlib import Path

import pexpect
import git

log = logging.getLogger("frida.design.fpga.manage")

SITCP_REPO = "https://github.com/BeeBeansTechnologies/SiTCP_Netlist_for_Kintex7"

# Paths relative to this file's location (lives in design/fpga/)
_FPGA_DIR = Path(__file__).resolve().parent
_SITCP_DIR = _FPGA_DIR / "SiTCP"

# Build targets: platform -> (fpga_part, xdc_file, flash_size_mb)
TARGETS = {
    "BDAQ53_KX1": ("xc7k160tfbg676-1", "bdaq53_kx1.xdc", 64),
    "BDAQ53_KX2": ("xc7k160tffg676-2", "bdaq53_kx2.xdc", 64),
}


def _read_vivado_output(vivado, timeout=1):
    """Read all available output from a pexpect-driven Vivado process."""
    chunks = bytearray()
    try:
        while not vivado.expect(r".+", timeout=timeout):
            chunks += vivado.match.group(0)
    except (pexpect.exceptions.TIMEOUT, pexpect.exceptions.EOF):
        pass
    return chunks.decode("utf-8")


def _prepend_line(filepath, line):
    """Prepend a single line to a file."""
    path = Path(filepath)
    content = path.read_bytes()
    path.write_bytes(f"{line}\n".encode() + content)


def get_sitcp():
    """Download SiTCP netlist from GitHub and apply required patches."""
    sitcp_dir = _SITCP_DIR

    if (sitcp_dir / ".git").is_dir():
        log.info("SiTCP folder already exists, pulling updates")
        g = git.cmd.Git(str(sitcp_dir))
        result = g.pull()
        if "up to date" in result:
            log.info("SiTCP is up to date")
            return
        log.info("Updated SiTCP, re-applying patches")
    else:
        log.info("Downloading SiTCP from %s", SITCP_REPO)
        git.Repo.clone_from(url=SITCP_REPO, to_path=str(sitcp_dir), branch="master")

    # Patch 1: Add `default_nettype wire to files that lack it.
    # Without this, any module that sets `default_nettype none will break
    # SiTCP's implicit wire declarations.
    _prepend_line(sitcp_dir / "TIMER.v", r"`default_nettype wire")
    _prepend_line(sitcp_dir / "WRAP_SiTCP_GMII_XC7K_32K.V", r"`default_nettype wire")

    # Patch 2: Force SiTCP to always use EXT_IP_ADDR.
    # The original code selects DEFAULT_IP_ADDR when FORCE_DEFAULTn=0,
    # which ignores the IP address set in the Verilog instantiation.
    wrap_file = sitcp_dir / "WRAP_SiTCP_GMII_XC7K_32K.V"
    for line in fileinput.input([str(wrap_file)], inplace=True):
        print(
            line.replace(
                "assign\tMY_IP_ADDR[31:0]\t= (~FORCE_DEFAULTn | (EXT_IP_ADDR[31:0]==32'd0) "
                "\t? DEFAULT_IP_ADDR[31:0]\t\t: EXT_IP_ADDR[31:0]\t\t);",
                "assign\tMY_IP_ADDR[31:0]\t= EXT_IP_ADDR[31:0];",
            ),
            end="",
        )

    log.info("SiTCP downloaded and patched")


def _clean_build_artifacts():
    """Remove Vivado build artifacts from previous runs."""
    import glob

    patterns = [
        "*.backup.*",
        "vivado*.log",
        "vivado*.jou",
        "clockInfo.txt",
        "tight_setup_hold_pins.txt",
        "planAhead.ngc2edif.log",
    ]
    for pattern in patterns:
        for f in glob.glob(str(_FPGA_DIR / pattern)):
            Path(f).unlink(missing_ok=True)
    for d in [".Xil", ".ngc2edfcache", "build", "bit", "reports"]:
        path = _FPGA_DIR / d
        if path.is_dir():
            import shutil

            shutil.rmtree(path)


def compile(platform):
    """Compile FPGA bitstream for the given platform using Vivado."""
    if platform not in TARGETS:
        raise ValueError(f"Unknown platform '{platform}'. Supported: {', '.join(TARGETS)}")

    _clean_build_artifacts()

    fpga_part, xdc_file, flash_size = TARGETS[platform]
    log.info("Compiling for %s (%s)", platform, fpga_part)

    command = f"vivado -mode batch -source run.tcl -tclargs {fpga_part} {xdc_file} {flash_size}"
    log.info("This takes several minutes...")

    try:
        vivado = pexpect.spawn(command, cwd=str(_FPGA_DIR), timeout=10)
        vivado.expect("Vivado", timeout=10)
    except pexpect.exceptions.ExceptionPexpect:
        raise RuntimeError(
            "Cannot start Vivado. Is it on your PATH?\n  Try: source /eda/local/scripts/vivado_2025.2.sh"
        )

    try:
        poll_timeout = 36  # iterations * 5s = 180s max silence
        silent_count = 0
        while silent_count < poll_timeout:
            output = _read_vivado_output(vivado)
            if output:
                if "write_cfgmem completed successfully" in output:
                    print(".", flush=True)
                    break
                print(".", end="", flush=True)
                silent_count = 0
            else:
                time.sleep(5)
                silent_count += 1
        else:
            raise RuntimeError("Timeout during compilation — check vivado.log")
    finally:
        if vivado.isalive():
            vivado.close()

    log.info("SUCCESS — bitstream in %s/bit/", _FPGA_DIR)


def flash(filepath):
    """Program FPGA or flash memory via JTAG.

    .bit/.bin files are written to FPGA SRAM (volatile).
    .mcs files are written to SPI flash (persistent).
    """
    filepath = str(Path(filepath).resolve())

    # Try vivado_lab first (free), fall back to full vivado
    # Run from fpga dir so Vivado writes logs/journals there, not cwd
    vivado = None
    for cmd in ("vivado_lab -mode tcl", "vivado -mode tcl"):
        try:
            vivado = pexpect.spawn(cmd, cwd=str(_FPGA_DIR), timeout=10)
            vivado.expect("Vivado", timeout=10)
            break
        except pexpect.exceptions.ExceptionPexpect:
            if vivado and vivado.isalive():
                vivado.close()
            vivado = None

    if vivado is None:
        raise RuntimeError("Cannot start vivado or vivado_lab")

    try:
        vivado.expect(["vivado_lab%", "Vivado%"], timeout=30)

        # --- Check USB programmer is visible to the OS ---
        try:
            import subprocess

            lsusb = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
            if "xilinx" not in lsusb.stdout.lower():
                raise RuntimeError(
                    "No Xilinx USB programmer found (lsusb shows no Xilinx device).\n"
                    "Check that the JTAG cable is plugged in."
                )
            log.info("JTAG programmer found on USB")
        except FileNotFoundError:
            pass  # lsusb not available, skip check

        # --- Connect to JTAG ---
        log.info("Connecting to JTAG interface")
        vivado.sendline("open_hw_manager")
        vivado.expect(["vivado_lab%", "Vivado%"])

        vivado.sendline("connect_hw_server")
        vivado.expect("localhost")
        _read_vivado_output(vivado)

        vivado.sendline("current_hw_target")
        ret = _read_vivado_output(vivado)
        log.info("Connected to: %s", ret.strip())
        if "WARNING" in ret:
            raise RuntimeError(
                "No JTAG target found. The USB programmer is connected but\n"
                "Vivado cannot find a JTAG target. Check the cable."
            )

        vivado.sendline("open_hw_target")
        vivado.expect(["vivado_lab%", "Vivado%"], timeout=15)
        open_output = vivado.before.decode("utf-8", errors="replace")
        if "No devices detected" in open_output or "failed" in open_output.lower():
            raise RuntimeError(
                "No FPGA detected on the JTAG chain.\n"
                "The JTAG programmer is connected but cannot see an FPGA device.\n"
                "Check that:\n"
                "  - The FPGA board is powered on\n"
                "  - The FPGA module is seated firmly in the base board\n"
                "  - The JTAG ribbon cable is on the correct header"
            )

        vivado.sendline("current_hw_device [lindex [get_hw_devices] 0]")
        vivado.expect(["vivado_lab%", "Vivado%"])
        dev_output = vivado.before.decode("utf-8", errors="replace")
        if "ERROR" in dev_output or "Invalid option value" in dev_output:
            raise RuntimeError(
                "No FPGA detected on the JTAG chain.\nCheck that the board is powered and the module is seated."
            )
        log.info("FPGA device found")

        if filepath.endswith((".bit", ".bin")):
            log.info("Writing to FPGA SRAM (volatile) — %s", filepath)

            vivado.sendline("set devPart [get_property PART [current_hw_device]]")
            vivado.expect(["vivado_lab%", "Vivado%"])

            vivado.sendline(f"set_property PROGRAM.FILE {{{filepath}}} [current_hw_device]")
            vivado.expect(["vivado_lab%", "Vivado%"])

            vivado.sendline("program_hw_devices [current_hw_device]")
            vivado.expect("End of startup status: HIGH")

        elif filepath.endswith(".mcs"):
            log.info("Writing to SPI flash (persistent) — %s", filepath)

            # Try KX2 flash chip first, fall back to older KX1 chip
            for flash_chip in ("s25fl512s-spi-x1_x2_x4", "mt25ql256-spi-x1_x2_x4"):
                try:
                    vivado.sendline(
                        f"create_hw_cfgmem -hw_device [current_hw_device] "
                        f"[lindex [get_cfgmem_parts {{{flash_chip}}}] 0]"
                    )
                    vivado.sendline(
                        "set_property PROGRAM.ADDRESS_RANGE {use_file} [get_property PROGRAM.HW_CFGMEM [current_hw_device]]"
                    )
                    vivado.sendline(
                        f"set_property PROGRAM.FILES {{{filepath}}} [get_property PROGRAM.HW_CFGMEM [current_hw_device]]"
                    )
                    vivado.sendline(
                        "set_property PROGRAM.BLANK_CHECK 0 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]"
                    )
                    vivado.sendline("set_property PROGRAM.ERASE 1 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]")
                    vivado.sendline(
                        "set_property PROGRAM.CFG_PROGRAM 1 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]"
                    )
                    vivado.sendline(
                        "set_property PROGRAM.VERIFY 1 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]"
                    )
                    vivado.sendline(
                        "create_hw_bitstream -hw_device [current_hw_device] [get_property PROGRAM.HW_CFGMEM_BITFILE [current_hw_device]]"
                    )
                    vivado.sendline("program_hw_devices [current_hw_device]")
                    vivado.expect("End of startup status: HIGH", timeout=10)
                    vivado.sendline("program_hw_cfgmem -hw_cfgmem [get_property PROGRAM.HW_CFGMEM [current_hw_device]]")
                    vivado.expect("Flash programming completed successfully", timeout=120)
                    break
                except pexpect.exceptions.TIMEOUT:
                    log.warning("Flash chip %s failed, trying next...", flash_chip)
                    continue
            else:
                raise RuntimeError("Flash programming failed with all known chip types")

            log.info(_read_vivado_output(vivado))
            vivado.sendline("boot_hw_device [current_hw_device]")
            vivado.expect("Done pin status: HIGH")

        else:
            raise ValueError(f"Unknown file type: {filepath} (expected .bit, .bin, or .mcs)")

        log.info("Programming successful!")

    finally:
        # Always clean up
        try:
            vivado.sendline("close_hw_target")
            vivado.expect("Closing", timeout=5)
            vivado.sendline("exit")
            vivado.expect("Exiting", timeout=5)
        except (pexpect.exceptions.TIMEOUT, pexpect.exceptions.EOF):
            pass
        if vivado.isalive():
            vivado.close()


def check():
    """Check JTAG connectivity: USB programmer, cable, and FPGA device."""
    import subprocess

    # --- USB programmer ---
    log.info("Checking USB for Xilinx JTAG programmer...")
    try:
        lsusb = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
        xilinx_lines = [l for l in lsusb.stdout.splitlines() if "xilinx" in l.lower()]
        if not xilinx_lines:
            log.error("FAIL: No Xilinx USB device found. Check that the JTAG cable is plugged in.")
            return
        for line in xilinx_lines:
            log.info("  USB: %s", line.strip())
    except FileNotFoundError:
        log.warning("lsusb not available, skipping USB check")

    # --- Vivado JTAG scan ---
    log.info("Launching Vivado to scan JTAG chain...")
    vivado = None
    for cmd in ("vivado_lab -mode tcl", "vivado -mode tcl"):
        try:
            vivado = pexpect.spawn(cmd, cwd=str(_FPGA_DIR), timeout=10)
            vivado.expect("Vivado", timeout=10)
            break
        except pexpect.exceptions.ExceptionPexpect:
            if vivado and vivado.isalive():
                vivado.close()
            vivado = None

    if vivado is None:
        log.error("FAIL: Cannot start vivado or vivado_lab. Is Vivado sourced?")
        return

    try:
        vivado.expect(["vivado_lab%", "Vivado%"], timeout=30)
        vivado.sendline("open_hw_manager")
        vivado.expect(["vivado_lab%", "Vivado%"])
        vivado.sendline("connect_hw_server")
        vivado.expect("localhost")
        _read_vivado_output(vivado)

        # List targets
        vivado.sendline('puts "TARGETS:[get_hw_targets]"')
        vivado.expect(["vivado_lab%", "Vivado%"])
        target_output = vivado.before.decode("utf-8", errors="replace")
        if "TARGETS:" in target_output:
            targets = target_output.split("TARGETS:")[1].strip().split()
        else:
            targets = []

        if not targets:
            log.error("FAIL: No JTAG targets found. Check cable and drivers.")
            return
        log.info("  JTAG target: %s", targets[0])

        # Open target and scan for devices
        vivado.sendline(f"open_hw_target {{{targets[0]}}}")
        vivado.expect(["vivado_lab%", "Vivado%"], timeout=15)
        open_output = vivado.before.decode("utf-8", errors="replace")

        if "No devices detected" in open_output:
            log.error(
                "FAIL: JTAG target opened but no FPGA detected on the chain.\n"
                "  The programmer is connected but cannot see an FPGA device.\n"
                "  Check that:\n"
                "    - The FPGA board is powered on\n"
                "    - The FPGA module is seated firmly in the base board\n"
                "    - The JTAG ribbon cable is on the correct header"
            )
            return

        # List devices
        vivado.sendline('puts "DEVICES:[get_hw_devices]"')
        vivado.expect(["vivado_lab%", "Vivado%"])
        dev_output = vivado.before.decode("utf-8", errors="replace")
        if "DEVICES:" in dev_output:
            devices = dev_output.split("DEVICES:")[1].strip().split()
        else:
            devices = []

        if not devices:
            log.error("FAIL: No FPGA devices found on JTAG chain.")
            return

        for dev in devices:
            vivado.sendline(f"get_property PART [get_hw_devices {{{dev}}}]")
            vivado.expect(["vivado_lab%", "Vivado%"])
            part = vivado.before.decode("utf-8", errors="replace").strip().split("\n")[-1].strip()
            vivado.sendline(f"get_property STATUS [get_hw_devices {{{dev}}}]")
            vivado.expect(["vivado_lab%", "Vivado%"])
            status = vivado.before.decode("utf-8", errors="replace").strip().split("\n")[-1].strip()
            log.info("  Device: %s  Part: %s  Status: %s", dev, part, status)

        log.info("PASS: JTAG chain OK — %d device(s) found", len(devices))

    finally:
        try:
            vivado.sendline("close_hw_target")
            vivado.expect("Closing", timeout=5)
            vivado.sendline("exit")
            vivado.expect("Exiting", timeout=5)
        except (pexpect.exceptions.TIMEOUT, pexpect.exceptions.EOF):
            pass
        if vivado.isalive():
            vivado.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="FRIDA1 FPGA management: compile, flash, and download SiTCP.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--compile",
        metavar="PLATFORM",
        help=f"Compile bitstream for platform.\nSupported: {', '.join(TARGETS)}",
    )
    parser.add_argument(
        "--flash",
        metavar="FILE",
        help="Flash .bit (SRAM) or .mcs (SPI flash) to FPGA via JTAG.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check JTAG connectivity: USB programmer, cable, FPGA device.",
    )
    parser.add_argument(
        "--get_sitcp",
        action="store_true",
        help="Download and patch SiTCP netlist.",
    )

    args = parser.parse_args()

    if not any([args.compile, args.flash, args.check, args.get_sitcp]):
        parser.print_help()
        return

    if args.compile and args.flash:
        parser.error("Cannot compile and flash at the same time.")

    if args.get_sitcp or args.compile:
        get_sitcp()

    if args.check:
        check()
    elif args.compile:
        compile(args.compile)
    elif args.flash:
        flash(args.flash)


if __name__ == "__main__":
    main()
