"""Tests for PDK infrastructure: supply-rail metadata and walker scaling."""

from importlib import import_module
from pathlib import Path

import hdl21 as h
import pytest
from hdl21.pdk import Corner

# ==== Helpers ====


def _install_class(tech: str):
    """Import and return the Install class for a given PDK."""
    return import_module(f"pdk.{tech}.pdk_logic").Install


_LOCAL_INSTALL_BASES = {
    "tsmc65": Path("/eda/kits/TSMC/65LP/2024"),
    "tsmc28": Path("/eda/kits/TSMC/28HPC+/2023_v1.1"),
    "tower180": Path("/eda/kits/TOWER/ts18is_Rev_6.3.6"),
}


# ==== Supply-Rail Metadata ====


def test_supply_rails_have_vdd() -> None:
    """Each supported PDK exposes at least one VDD rail entry."""
    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        assert "VDD" in cls.SUPPLY_RAILS, f"{tech} missing VDD in SUPPLY_RAILS"
        assert cls.SUPPLY_RAILS["VDD"]["nominal"] > 0.0


def test_install_supply_voltage_corner_mapping() -> None:
    """Install.supply_voltage() maps corners to min/nominal/max."""
    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        vdd = cls.SUPPLY_RAILS["VDD"]
        assert cls.supply_voltage(Corner.SLOW, "VDD") == vdd["min"]
        assert cls.supply_voltage(Corner.TYP, "VDD") == vdd["nominal"]
        assert cls.supply_voltage(Corner.FAST, "VDD") == vdd["max"]


def test_supplyvals_resolves_via_install() -> None:
    """SupplyVals.corner() resolves VDD through Install.supply_voltage()."""
    from flow.circuit.params import SupplyVals

    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        expected = cls.supply_voltage(Corner.TYP, "VDD")
        vals = SupplyVals.corner(Corner.TYP, tech_name=tech)
        assert float(vals.VDD) == expected


# ==== Walker Scaling of Unitless MOS Dimensions ====


@pytest.mark.parametrize(
    "tech_name, expected_w_m, expected_l_m",
    [
        ("ihp130", 0.70e-6, 0.13e-6),
        ("tsmc65", 0.24e-6, 0.06e-6),
        ("tsmc28", 0.08e-6, 0.03e-6),
        ("tower180", 0.44e-6, 0.18e-6),
    ],
)
def test_unitless_mos_dimensions_scale_by_pdk_defaults(
    tech_name: str,
    expected_w_m: float,
    expected_l_m: float,
) -> None:
    """
    Unitless `w/l` multipliers are scaled by each PDK's unit-device defaults.

    Example under test:
    - `w=2*UNIT` -> `2 * pdk_default_w`
    - `l=1*UNIT` -> `1 * pdk_default_l`
    """
    pdk_module = import_module(f"pdk.{tech_name}")
    compile_fn = getattr(pdk_module, "compile")

    @h.module
    class Dut:
        d, g, s, b = h.Signals(4)
        m = h.Mos(tp=h.MosType.NMOS, w=2, l=1)(d=d, g=g, s=s, b=b)

    compile_fn(Dut)
    params = Dut.m.of.params
    assert float(params.w) == pytest.approx(expected_w_m)
    assert float(params.l) == pytest.approx(expected_l_m)


# ==== Local PDK Installation ====
# Relative paths are defined in each PDK's Install.LOCAL_SPICE_FILES (pdk_logic.py).
# Base installation paths are defined here in the test harness.
# Run pdk/<tech>/local.sh to populate the local /eda/kits/ cache from asiclab003.

_LOCAL_INSTALL_TECHS = ("tsmc65", "tsmc28", "tower180")


def _local_spice_params():
    """Collect (tech, install, resolved_path) tuples for local-install validation."""
    params = []
    for tech in _LOCAL_INSTALL_TECHS:
        cls = _install_class(tech)
        install = cls(pdk_path=_LOCAL_INSTALL_BASES[tech])
        for relpath in cls.LOCAL_SPICE_FILES:
            params.append(
                pytest.param(
                    tech,
                    install,
                    install.pdk_path / relpath,
                    id=f"{tech}/{relpath.name}",
                )
            )
    return params


@pytest.mark.parametrize("tech, install, path", _local_spice_params())
def test_local_pdk_spice_files_exist(tech: str, install, path: Path) -> None:
    """Verify that locally cached PDK SPICE files are present.

    The test harness supplies each PDK's site-specific base path and instantiates
    its Install object locally. If this test fails, run:
        bash pdk/<tech>/local.sh
    """
    assert install.pdk_path == _LOCAL_INSTALL_BASES[tech]
    assert path.exists(), f"Missing local PDK file: {path}\nRun bash pdk/{tech}/local.sh to sync from asiclab003."
