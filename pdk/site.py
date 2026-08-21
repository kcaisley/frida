"""Site-local HDL21 PDK installations."""

from pathlib import Path

from pdk import tsmc65

tsmc65.install = tsmc65.Install(pdk_path=Path("/eda/kits/TSMC/65LP/2024"))
