#!/usr/bin/env python3
# SiliconCompiler smake targets for the behavioral SPI register.


from __future__ import annotations

from pathlib import Path

from siliconcompiler import ASIC, Design, Flowgraph, Sim
from siliconcompiler.targets import ihp130_demo as _ihp130_demo
from siliconcompiler.tools.icarus.cocotb_exec import CocotbExecTask as IcarusCocotbExecTask
from siliconcompiler.tools.icarus.compile import CompileTask as IcarusCompileTask
from siliconcompiler.tools.verilator.lint import LintTask as VerilatorLintTask

from flow.sc.tasks.verible import VeribleLintTask

__scdefault = "sim"

REPO_ROOT = Path(__file__).resolve().parents[2]
RTL = "design/hdl/spi.v"
SDC = "design/constraints/spi_register.sdc"
TB = "test/cocotb/tb_spi_register.v"
COCOTB_TEST = "test/cocotb/test_spi_register.py"
TOP = "spi_register"
TB_TOP = "tb_spi_register"


class SpiDesign(Design):
    """Behavioral SPI register filesets for unit simulation and IHP130 build."""

    def __init__(self):
        super().__init__("spi")
        self.set_dataroot("frida", str(REPO_ROOT))

        # ASIC/synthesis fileset: design RTL only, top is the DUT.
        with self.active_dataroot("frida"), self.active_fileset("rtl"):
            self.set_topmodule(TOP)
            self.add_file(RTL)

        # Simulation fileset: DUT plus Verilog testbench wrapper.
        with self.active_dataroot("frida"), self.active_fileset("rtl.sim"):
            self.set_topmodule(TB_TOP)
            self.add_file(RTL)
            self.add_file(TB)

        with self.active_dataroot("frida"), self.active_fileset("sdc"):
            self.add_file(SDC)

        with self.active_dataroot("frida"), self.active_fileset("testbench.cocotb"):
            self.set_topmodule(TB_TOP)
            self.add_file(COCOTB_TEST, filetype="python")


class SpiSimProject(Sim):
    """Lint and cocotb simulation project for the behavioral implementation."""

    def __init__(self):
        super().__init__(SpiDesign())
        self.add_fileset("rtl.sim")
        self.add_fileset("testbench.cocotb")
        self.option.set_builddir(str(REPO_ROOT / "build"))
        self.option.set_jobname("sim")
        self.option.set_nodashboard(True)

        flow = Flowgraph("spi_sim")
        flow.node("lint.verible", VeribleLintTask())
        flow.node("lint.verilator", VerilatorLintTask())
        flow.node("compile", IcarusCompileTask())
        flow.node("simulate", IcarusCocotbExecTask())
        flow.edge("compile", "simulate")
        self.set_flow(flow)

        verible = VeribleLintTask.find_task(self)
        verible.add_source(REPO_ROOT / RTL)
        verible.add_source(REPO_ROOT / TB)

        # Verilator exits nonzero on warnings unless -Wno-fatal is used.
        # Keep warnings visible as SC metrics but do not fail this staged migration yet.
        VerilatorLintTask.find_task(self).add_warningoff("fatal")


class SpiIhp130Project(ASIC):
    """IHP130 ASIC project for the behavioral implementation."""

    def __init__(self):
        super().__init__(SpiDesign())
        self.add_fileset("rtl")
        self.add_fileset("sdc")
        self.option.set_builddir(str(REPO_ROOT / "build"))
        self.option.set_jobname("ihp130")
        self.option.set_nodashboard(True)

        _ihp130_demo(self)


def _configure_common(project, jobname: str, remote: bool) -> None:
    project.option.set_jobname(jobname)
    project.option.set_remote(remote)


def _run(project) -> None:
    project.run()
    project.summary()


def sim(jobname: str = "sim", remote: bool = False) -> None:
    """Run behavioral SPI lint and cocotb unit simulation."""
    project = SpiSimProject()
    _configure_common(project, jobname, remote)
    _run(project)


def syn(jobname: str = "ihp130", remote: bool = False) -> None:
    """Run behavioral SPI IHP130 synthesis plus OpenSTA timing."""
    project = SpiIhp130Project()
    _configure_common(project, jobname, remote)
    project.option.set_flow("synflow")
    _run(project)


def asic(jobname: str = "ihp130", remote: bool = False, screenshot: bool = True) -> None:
    """Run behavioral SPI IHP130 OpenROAD build through detailed route."""
    project = SpiIhp130Project()
    _configure_common(project, jobname, remote)

    # The installed IHP130 target currently fails in optional metal fill/GDS tail.
    # Stop at detailed route, where DEF/ODB and OpenROAD report images are valid.
    project.option.add_to(["route.detailed", "0"])

    _run(project)

    if screenshot:
        image = project.show(screenshot=True, extension="def", tool="openroad")
        print(f"Layout screenshot: {image}")


if __name__ == "__main__":
    sim()
