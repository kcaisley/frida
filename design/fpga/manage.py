"""BDAQ FPGA management: download SiTCP, compile, check JTAG, and flash bitstreams.

Usage (from the project root):
    python design/fpga/manage.py --get_sitcp
    python design/fpga/manage.py --help
    python design/fpga/manage.py --check
    python design/fpga/manage.py --flash /path/to/image.bit
"""

import argparse
import fileinput
import logging
import time
from pathlib import Path

import git
import pexpect

log = logging.getLogger("bdaq.fpga.manage")

SITCP_REPO = "https://github.com/BeeBeansTechnologies/SiTCP_Netlist_for_Kintex7"

# Paths relative to this file's location (lives in design/fpga/)
_FPGA_DIR = Path(__file__).resolve().parent
_SITCP_DIR = _FPGA_DIR / "SiTCP"
_BUILD_DIR = _FPGA_DIR / "build"

# Build targets: platform -> (fpga_part, flash_size_mb)
TARGETS = {
    "BDAQ53_KX1": ("xc7k160tfbg676-1", 64),
    "BDAQ53_KX2": ("xc7k160tffg676-2", 64),
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
    with fileinput.input([str(wrap_file)], inplace=True) as lines:
        for line in lines:
            print(
                line.replace(
                    "assign\tMY_IP_ADDR[31:0]\t= (~FORCE_DEFAULTn | (EXT_IP_ADDR[31:0]==32'd0) "
                    "\t? DEFAULT_IP_ADDR[31:0]\t\t: EXT_IP_ADDR[31:0]\t\t);",
                    "assign\tMY_IP_ADDR[31:0]\t= EXT_IP_ADDR[31:0];",
                ),
                end="",
            )

    log.info("SiTCP downloaded and patched")


def compile(platform, *, verilog, xdc, top, name, out_dir, edif=None, include_dir=None):
    """Compile FPGA bitstream for the given platform using Vivado."""
    for option, value in (("verilog", verilog), ("xdc", xdc), ("top", top), ("name", name), ("out-dir", out_dir)):
        if not value:
            raise ValueError(f"Compilation requires --{option}")
    _require_vivado()
    if platform not in TARGETS:
        raise ValueError(f"Unknown platform '{platform}'. Supported: {', '.join(TARGETS)}")

    output_dir = Path(out_dir).expanduser().resolve()
    build_dir = output_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    fpga_part, flash_size = TARGETS[platform]
    log.info("Compiling for %s (%s)", platform, fpga_part)

    arguments = [
        "-mode",
        "batch",
        "-source",
        str(_FPGA_DIR / "run.tcl"),
        "-log",
        str(build_dir / "vivado.log"),
        "-journal",
        str(build_dir / "vivado.jou"),
        "-tclargs",
        fpga_part,
        str(flash_size),
        "--out-dir",
        str(output_dir),
    ]
    for option, paths in (("--verilog", verilog), ("--xdc", xdc), ("--edif", edif), ("--include-dir", include_dir)):
        for path in paths or []:
            arguments.extend([option, str(Path(path).expanduser().resolve())])
    for option, value in (("--top", top), ("--name", name)):
        if value is not None:
            arguments.extend([option, value])
    log.info("This takes several minutes...")

    try:
        vivado = pexpect.spawn("vivado", arguments, cwd=str(output_dir), timeout=180)
        vivado.expect("Vivado", timeout=180)
    except pexpect.exceptions.ExceptionPexpect:
        raise RuntimeError(
            "Cannot start Vivado. Is it on your PATH?\n  Try: source /eda/local/scripts/vivado_2025.2.sh"
        )

    try:
        poll_timeout = 120  # iterations * 5s = 600s max silence
        silent_count = 0
        while silent_count < poll_timeout:
            output = _read_vivado_output(vivado)
            if output:
                if "write_cfgmem completed successfully" in output:
                    print(output, end="", flush=True)
                    break
                print(output, end="", flush=True)
                silent_count = 0
            else:
                if not vivado.isalive():
                    vivado.close()
                    status = vivado.exitstatus if vivado.exitstatus is not None else f"signal {vivado.signalstatus}"
                    raise RuntimeError(
                        f"Vivado exited before completing bitstream generation ({status}) — "
                        f"check {build_dir / 'vivado.log'}"
                    )
                time.sleep(5)
                silent_count += 1
        else:
            raise RuntimeError(f"Timeout during compilation — check {build_dir / 'vivado.log'}")
    finally:
        if vivado.isalive():
            vivado.close()

    log.info("SUCCESS — bitstream in %s/bit/", output_dir)


def flash(filepath):
    """Program FPGA or flash memory via JTAG.

    .bit/.bin files are written to FPGA SRAM (volatile).
    .mcs files are written to SPI flash (persistent).
    """
    path = Path(filepath).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"FPGA image not found: {path}")
    filepath = str(path)
    _require_vivado()
    _BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Try vivado_lab first (free), fall back to full vivado
    vivado = None
    for cmd in (
        "vivado_lab -mode tcl -log build/vivado_lab.log -journal build/vivado_lab.jou",
        "vivado -mode tcl -log build/vivado.log -journal build/vivado.jou",
    ):
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
        vivado.expect(["vivado_lab%", "Vivado%"], timeout=180)

        # --- Check USB programmer is visible to the OS ---
        try:
            import subprocess

            lsusb = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5, check=False)
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


def _require_vivado():
    """Check that Vivado (or vivado_lab) is on PATH. Raise if not found."""
    import shutil

    if shutil.which("vivado_lab") or shutil.which("vivado"):
        return
    raise RuntimeError(
        "Neither 'vivado_lab' nor 'vivado' found on PATH.\n"
        "Source the environment first:\n"
        "  source /eda/local/scripts/vivado_2025.2.sh"
    )


def check():
    """Check JTAG connectivity: USB programmer, cable, and FPGA device.

    Runs a self-contained TCL script in batch mode to avoid pexpect
    buffer-parsing issues. The script writes structured output lines
    prefixed with BDAQ: for easy extraction.
    """
    import subprocess
    import tempfile

    _require_vivado()

    # --- USB programmer ---
    log.info("Checking USB for Xilinx JTAG programmer...")
    try:
        lsusb = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5, check=False)
        xilinx_lines = [l for l in lsusb.stdout.splitlines() if "xilinx" in l.lower()]
        if not xilinx_lines:
            log.error("FAIL: No Xilinx USB device found. Check that the JTAG cable is plugged in.")
            return
        for line in xilinx_lines:
            log.info("  USB: %s", line.strip())
    except FileNotFoundError:
        log.warning("lsusb not available, skipping USB check")

    # --- Vivado JTAG scan via batch TCL ---
    tcl_script = """\
open_hw_manager
connect_hw_server
set targets [get_hw_targets]
if {[llength $targets] == 0} {
    puts "BDAQ:NO_TARGETS"
    quit
}
foreach target $targets {
    puts "BDAQ:TARGET:$target"
    current_hw_target $target
    if {[catch {open_hw_target $target} err]} {
        puts "BDAQ:OPEN_FAILED:$target:$err"
        continue
    }
    set devices [get_hw_devices]
    if {[llength $devices] == 0} {
        puts "BDAQ:NO_DEVICES:$target"
    }
    foreach d $devices {
        set part [get_property PART $d]
        puts "BDAQ:DEVICE:$d:$part"
    }
    close_hw_target
}
quit
"""
    log.info("Launching Vivado to scan JTAG chain...")
    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    vivado_cmd = (
        "vivado_lab"
        if subprocess.run(["which", "vivado_lab"], capture_output=True, check=False).returncode == 0
        else "vivado"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
        f.write(tcl_script)
        tcl_path = f.name

    try:
        result = subprocess.run(
            [
                vivado_cmd,
                "-mode",
                "batch",
                "-source",
                tcl_path,
                "-log",
                "build/vivado_scan.log",
                "-journal",
                "build/vivado_scan.jou",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(_FPGA_DIR),
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        log.error("FAIL: Vivado timed out scanning JTAG chain.")
        return
    finally:
        Path(tcl_path).unlink(missing_ok=True)

    # A Tcl failure is not evidence of an empty chain. Preserve the actual error.
    if result.returncode != 0:
        log.error("FAIL: Vivado JTAG check failed (exit %d):\n%s", result.returncode, output.strip())
        return
    bdaq_lines = [line for line in output.splitlines() if line.startswith("BDAQ:")]
    for line in bdaq_lines:
        if line.startswith("BDAQ:TARGET:"):
            log.info("  JTAG target: %s", line.split(":", 2)[2])
        elif line.startswith("BDAQ:OPEN_FAILED:"):
            log.warning("  Could not open target: %s", line.split(":", 2)[2])
        elif line.startswith("BDAQ:NO_DEVICES:"):
            log.warning("  No devices on target: %s", line.split(":", 2)[2])

    devices = [line for line in bdaq_lines if line.startswith("BDAQ:DEVICE:")]
    for line in devices:
        _, _, name, part = line.split(":", 3)
        log.info("  Device: %s  Part: %s", name, part)
    if devices:
        log.info("PASS: JTAG chain OK — %d device(s) found", len(devices))
    elif "BDAQ:NO_TARGETS" in bdaq_lines:
        log.error("FAIL: No JTAG targets found. Check cable and drivers.")
    elif any(line.startswith(("BDAQ:NO_DEVICES:", "BDAQ:OPEN_FAILED:")) for line in bdaq_lines):
        log.error("FAIL: No FPGA detected on the enumerated JTAG targets; see target diagnostics above.")
    else:
        log.error("FAIL: Incomplete Vivado JTAG check output:\n%s", output.strip())


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="BDAQ FPGA management: compile, flash, and download SiTCP.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--compile",
        choices=TARGETS,
        metavar="PLATFORM",
        help=f"Compile bitstream for the specified platform.\nSupported: {', '.join(TARGETS)}",
    )
    parser.add_argument(
        "--flash",
        metavar="FILE",
        help="Flash the specified .bit/.bin (SRAM) or .mcs (SPI flash) image via JTAG.",
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

    parser.add_argument(
        "--verilog", action="append", metavar="FILE", help="Required for compilation; repeat for multiple HDL units."
    )
    parser.add_argument(
        "--xdc", action="append", metavar="FILE", help="Required for compilation; repeat for multiple constraint files."
    )
    parser.add_argument("--edif", action="append", metavar="FILE", help="EDIF netlist; repeat for multiple files.")
    parser.add_argument(
        "--include-dir",
        action="append",
        metavar="DIR",
        help="Verilog include directory; repeatable. No implicit include paths.",
    )
    parser.add_argument("--top", metavar="MODULE", help="Top module; required for compilation.")
    parser.add_argument("--name", metavar="NAME", help="Project and image basename; required for compilation.")
    parser.add_argument("--out-dir", metavar="DIR", help="Parent of build/, bit/, reports/; required for compilation.")

    args = parser.parse_args()

    if not any([args.compile, args.flash, args.check, args.get_sitcp]):
        parser.print_help()
        return

    if args.compile and args.flash:
        parser.error("Cannot compile and flash at the same time.")

    if args.compile:
        missing = [option for option in ("verilog", "xdc", "top", "name", "out_dir") if not getattr(args, option)]
        if missing:
            parser.error("Compilation requires " + ", ".join("--" + option.replace("_", "-") for option in missing))

    if args.get_sitcp:
        get_sitcp()

    if args.check:
        check()
    elif args.compile:
        compile(
            args.compile,
            verilog=args.verilog,
            xdc=args.xdc,
            edif=args.edif,
            include_dir=args.include_dir,
            top=args.top,
            name=args.name,
            out_dir=args.out_dir,
        )
    elif args.flash:
        flash(args.flash)


if __name__ == "__main__":
    main()
