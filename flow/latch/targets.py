"""The latch's targets (``python -m flow latch.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.latch.analysis import (
    MeasLatch,
    analyze_latch_constraint,
    analyze_latch_sr,
    analyze_latch_timing,
    analyze_latch_upset,
)
from flow.latch.plots import plot_latch_frequency, plot_latch_setup_hold, plot_latch_supply, plot_latch_upset
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every latch over supply, data offset, clock period and upset, in every PDK."""
    return sim.latch_characterization(new_run("sim", "latch", "characterization"))


def layout_latch() -> Path:
    """The static C2MOS latch, in every PDK with every tool."""
    return layout.latch_latch_all_pdks(new_run("layout", "latch", "latch"))


def layout_latch_rst() -> Path:
    """The C2MOS latch with asynchronous reset, in every PDK with every tool."""
    return layout.latch_latch_rst_all_pdks(new_run("layout", "latch", "latch_rst"))


def layout_flop_rst() -> Path:
    """The master-slave flip-flop with reset, in every PDK with every tool."""
    return layout.latch_flop_rst_all_pdks(new_run("layout", "latch", "flop_rst"))


def layout_div2() -> Path:
    """The divide-by-two flip-flop with reset, in every PDK with every tool."""
    return layout.latch_div2_all_pdks(new_run("layout", "latch", "div2"))


def layout_sr_nand() -> Path:
    """The NAND SR latch, in every PDK with every tool."""
    return layout.latch_sr_nand_all_pdks(new_run("layout", "latch", "sr_nand"))


def layout_sr_nor() -> Path:
    """The NOR SR latch, in every PDK with every tool."""
    return layout.latch_sr_nor_all_pdks(new_run("layout", "latch", "sr_nor"))


def layout_flop_tspc() -> Path:
    """The TSPC flip-flop, in every PDK with every tool."""
    return layout.latch_flop_tspc_all_pdks(new_run("layout", "latch", "flop_tspc"))


def layout_div2_tspc() -> Path:
    """The TSPC divide-by-two, in every PDK with every tool."""
    return layout.latch_div2_tspc_all_pdks(new_run("layout", "latch", "div2_tspc"))


def layout_latch_dice() -> Path:
    """The DICE latch, in every PDK with every tool."""
    return layout.latch_latch_dice_all_pdks(new_run("layout", "latch", "latch_dice"))


def layout_all() -> Path:
    """Every latch layout above, each in every PDK."""
    return layout.all_latch_layouts(new_run("layout", "latch", "all"))


def sweep() -> None:
    """The latch's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["latch"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["latch"], 28)
    sweep_runner.table(["latch"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named latches' setup and hold, delay and energy over supply, toggle limit, and upset by a strike, in every PDK."""
    output_dir = new_run("analysis", "latch")

    meas_read_dir = BASE_PATH / "build/sim/latch/latch_characterization/20261019_234509"
    clocked = (
        ("latch", "latch: C2MOS"),
        ("latch_rst", "latch_rst: C2MOS with reset"),
        ("flop_rst", "flop_rst: master-slave"),
        ("div2", "div2: divide by two"),
        ("flop_tspc", "flop_tspc: TSPC"),
        ("div2_tspc", "div2_tspc: TSPC divide by two"),
        ("latch_dice", "latch_dice: DICE"),
    )
    srs = (("sr_nand", "sr_nand: NAND"), ("sr_nor", "sr_nor: NOR"))
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in (*clocked, *srs):
            for sweep, key in (
                ("supply", lambda item: float(item.param.vdd)),
                ("offset", lambda item: float(item.param.data_offset_s)),
                ("period", lambda item: -float(item.param.clock_period_s)),
                ("upset", lambda item: float(item.param.upset_charge_c)),
            ):
                sweeps[name, sweep] = read_measurements(
                    meas_read_dir, f"{pdk}/{name}/{sweep}/*/result.h5", MeasLatch, key=key
                )
        offset_cases = [(name, label) for name, label in clocked if sweeps[name, "offset"]]
        period_cases = [(name, label) for name, label in clocked if sweeps[name, "period"]]
        upset_cases = [(name, label) for name, label in clocked if sweeps[name, "upset"]]
        offset_timings = [analyze_latch_timing(sweeps[name, "offset"]) for name, _label in offset_cases]
        constraints = [
            analyze_latch_constraint(sweeps[name, "offset"], timing=timing)
            for (name, _label), timing in zip(offset_cases, offset_timings, strict=True)
        ]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_latch_setup_hold(
                offset_timings,
                constraints,
                labels=[label for _name, label in offset_cases],
                output_path=pdk_dir / "latch_setup_hold",
            ),
            *plot_latch_supply(
                [analyze_latch_timing(sweeps[name, "supply"]) for name, _label in clocked],
                [analyze_latch_sr(sweeps[name, "supply"]) for name, _label in srs],
                labels=[label for _name, label in (*clocked, *srs)],
                output_path=pdk_dir / "latch_supply",
            ),
            *plot_latch_frequency(
                [analyze_latch_timing(sweeps[name, "period"]) for name, _label in period_cases],
                labels=[label for _name, label in period_cases],
                output_path=pdk_dir / "latch_frequency",
            ),
            *plot_latch_upset(
                [analyze_latch_upset(sweeps[name, "upset"]) for name, _label in upset_cases],
                labels=[label for _name, label in upset_cases],
                output_path=pdk_dir / "latch_upset",
            ),
        ]
    return tuple(artifacts)
