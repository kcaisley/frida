"""Shared fixtures for opt-in physical scan tests."""

import subprocess
from pathlib import Path
from time import sleep

import pytest


@pytest.fixture(scope="session")
def linux_gpib_interface() -> None:
    """Ensure the bound NI GPIB-USB-B has a usable Linux-GPIB board."""

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    import gpib

    def board_is_ready() -> bool:
        try:
            descriptor = gpib.dev(0, 1)
        except gpib.GpibError:
            return False
        gpib.close(descriptor)
        return True

    if board_is_ready():
        return

    driver_path = Path("/sys/bus/usb/drivers/ni_usb_gpib")
    interfaces = sorted(path for path in driver_path.glob("*-*:*.*") if path.is_symlink())
    if len(interfaces) != 1:
        pytest.fail(f"expected exactly one bound NI GPIB-USB-B interface under {driver_path}, found {len(interfaces)}")

    command = (
        "sudo",
        "-n",
        "udevadm",
        "trigger",
        "--action=change",
        "--settle",
        str(interfaces[0]),
    )
    for _attempt in range(3):
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", None) or str(error)
            pytest.fail(f"could not initialize the NI GPIB-USB-B through udev: {detail.strip()}")

        # udev --settle waits for gpib_config, but the kernel may still be
        # completing the final USB transactions before GPIB0 can be opened.
        sleep(1.0)
        if board_is_ready():
            return

    pytest.fail("NI GPIB-USB-B remained unavailable after three targeted udev retries; reconnect the adapter")
