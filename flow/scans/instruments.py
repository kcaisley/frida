"""Basil DUT construction for FRIDA laboratory instruments."""

from pathlib import Path

from yaml import safe_load


def configure_linux_gpib() -> None:
    """Expose ``gpib-ctypes`` under the module names expected by PyVISA-py."""
    from gpib_ctypes import make_default_gpib

    make_default_gpib()


def instrument_dut(map_path: Path | str):
    """Create a Basil DUT, enabling the Linux GPIB bridge when required."""
    path = Path(map_path)
    config = safe_load(path.read_text())
    uses_gpib = any(
        str(layer.get("init", {}).get("resource_name", "")).upper().startswith("GPIB")
        for layer in config.get("transfer_layer", ())
    )
    if uses_gpib:
        configure_linux_gpib()

    # Import Basil after configuring gpib-ctypes so its VISA transfer layer
    # observes the compatibility modules installed in sys.modules.
    from basil.dut import Dut

    return Dut(config)
