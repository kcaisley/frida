"""The capacitor array's targets (``python -m flow caparray.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import comp, new_run
from flow.analysis.cdac import analyze_cdac_cap_mismatch, analyze_cdac_decisions, analyze_cdac_transition
from flow.analysis.io import read_analysis, read_measurement
from flow.analysis.plots import (
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
)
from flow.analysis.studies import BASE_PATH
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    MeasCdac,
)
from flow.caparray.analysis import MeasCapArrayTran, analyze_caparray_transfer, analyze_caparray_weights
from flow.caparray.plots import plot_caparray_error, plot_caparray_transfer, plot_caparray_weights
from flow.sweep import runner as sweep_runner

from . import layout, sim


def _unmade(*parts: str) -> Path:
    """A fresh run directory's path, not made: an array's layout makes its own (and refuses an existing one)."""
    run_dir = new_run(*parts)
    run_dir.rmdir()
    return run_dir


def characterization() -> Path:
    """Every array's stage weights and code ramp, in every PDK."""
    return sim.caparray_characterization(new_run("sim", "caparray", "characterization"))


def frida1_transfer_curve() -> Path:
    """The fabricated-size CDAC's complete code ramp, in TSMC65."""
    return sim.frida1_transfer_curve(new_run("sim", "caparray", "frida1_transfer_curve"))


def layout_1layer_radix17() -> Path:
    """FRIDA's radix-17 array on one metal in TSMC65: drawn, signed off and extracted."""
    return layout.caparray_1layer_radix17(_unmade("layout", "caparray", "1layer_radix17"))


def layout_2layer_radix17() -> Path:
    """FRIDA's radix-17 array on two metals in TSMC65: drawn, signed off and extracted."""
    return layout.caparray_2layer_radix17(_unmade("layout", "caparray", "2layer_radix17"))


def layout_3layer_radix17() -> Path:
    """FRIDA's radix-17 array on three metals in TSMC65: drawn, signed off and extracted."""
    return layout.caparray_3layer_radix17(_unmade("layout", "caparray", "3layer_radix17"))


def layout_all() -> Path:
    """The three TSMC65 arrays above, each into its own directory of one run."""
    return layout.all_caparrays(new_run("layout", "caparray", "all"))


def layout_all_pdks() -> Path:
    """FRIDA's array at one to three stacked metals in every PDK, through DRC."""
    return layout.caparray_all_pdks(new_run("layout", "caparray", "all_pdks"))


def layout_extract_all_pdks() -> Path:
    """FRIDA's array at one to three metals extracted in every PDK, against the FMOM model."""
    return layout.caparray_extract_all_pdks(new_run("layout", "caparray", "extract_all_pdks"))


def layout_extract_adc_arrays(pdk: str = "tsmc65") -> Path:
    """Each ADC array (``layout.ADC_ARRAYS``: 10, 12 and 14 bits, binary and three schemes with 2, 4
    and 6 extra cycles, at one and two of its resolution's least capacitance, and FRIDA-1's array
    at 12 bits and two) at three metals in ``pdk``, its split and capacitance sized through its
    extraction (``flow.caparray.sizing``), 16 at a time."""
    from . import sizing

    return sizing.extract_adc_arrays(new_run("layout", "caparray", "extract_adc_arrays"), pdk=pdk)


def layout_window_check() -> Path:
    """Units 9-11 of the two- and three-metal arrays extracted alone, in TSMC28 and TPSC65."""
    return layout.caparray_window_check(new_run("layout", "caparray", "window_check"))


def sweep() -> None:
    """The capacitor array's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["caparray"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["caparray"], 28)
    sweep_runner.table(["caparray"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def system_cap_mismatch_study() -> tuple[Path, ...]:
    """Extract and plot ADC00–ADC03 capacitor mismatch from A-to-B transitions."""
    output_dir = new_run("analysis", "cdac")

    # Comparator characterizations: the reviewed 800-mV campaigns behind the
    # board inventory's accepted comparator calibration, with every coarse and
    # fine trial. Each one is the reference point of its ADC's CDAC steps.
    comparator_read_dirs = {
        0: BASE_PATH / "build/scan_comp/20260804_051653",
        1: BASE_PATH / "build/scan_comp/20260804_053759",
        2: BASE_PATH / "build/scan_comp/20260804_051653",
        3: BASE_PATH / "build/scan_comp/20260804_054953",
    }
    # CDAC A-to-B runs, in acquisition order. Each later run atomically replaces
    # every point of the same ADC, side, element, direction, and diffcaps curve;
    # physical points from distinct acquisition sessions are never combined.
    selected_curves: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
    for run_name in ("20260804_171234", "20260804_193030", "20260804_193631"):
        grouped_in_run: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
        for path in sorted((BASE_PATH / "build/scan_cdac" / run_name).glob("*.h5")):
            cdac_point = read_measurement(path)
            if not isinstance(cdac_point, MeasCdac):
                raise TypeError(f"{path} contains {type(cdac_point).__name__}, expected MeasCdac")
            params = cdac_point.param
            if params.campaign != "cdac_ab":
                raise ValueError("CDAC campaign contains a point outside campaign='cdac_ab'")
            readbacks = cdac_point.info.readbacks
            if int(readbacks.get("fastrx_lost_count", 0)) or int(readbacks.get("spi_mismatches", 0)):
                raise ValueError("CDAC campaign contains a corrupt physical capture")
            if (
                params.observed_adc is None
                or params.cdac_side is None
                or params.cdac_element is None
                or params.cdac_direction is None
            ):
                raise ValueError("CDAC measurement is missing its ADC, side, element, or direction")
            curve_key = (
                params.observed_adc,
                params.cdac_side,
                params.cdac_element,
                params.cdac_direction,
                params.tb.dac_diffcaps,
            )
            grouped_in_run.setdefault(curve_key, []).append(cdac_point)
        for curve_key, curve in grouped_in_run.items():
            physical = [point for point in curve if point.info.backend == "physical"]
            if physical:
                session_ids = {point.info.readbacks.get("acquisition_session_id") for point in physical}
                completed = [point for point in physical if point.info.readbacks.get("curve_complete") is True]
                latest_timestamp = max(point.info.timestamp_utc for point in physical)
                if (
                    len(physical) != len(curve)
                    or None in session_ids
                    or len(session_ids) != 1
                    or len(completed) != 1
                    or completed[0].info.timestamp_utc != latest_timestamp
                ):
                    raise ValueError(f"CDAC campaign contains an incomplete or mixed-session curve {curve_key}")
        selected_curves.update(grouped_in_run)
    cdac_measurements: dict[int, list[MeasCdac]] = {}
    cap_mismatch: dict[int, AnalysisCdacCapMismatch] = {}
    for adc_index in sorted({curve_key[0] for curve_key in selected_curves}):
        comparator_measurements = []
        for path in sorted(comparator_read_dirs[adc_index].glob(f"*adc{adc_index:02d}*.h5")):
            comparator_point = read_analysis(path)
            if not isinstance(comparator_point, comp.AnalysisDecisions):
                raise TypeError(f"{path} contains {type(comparator_point).__name__}, expected comp.AnalysisDecisions")
            comparator_measurements.append(comparator_point)
        transitions = []
        cdac_measurements[adc_index] = []
        for curve_key in sorted(key for key in selected_curves if key[0] == adc_index):
            curve = selected_curves[curve_key]
            cdac_measurements[adc_index].extend(curve)
            # Fit the fine sweep stage where the curve has one.
            fit_points = [point for point in curve if point.param.sweep_stage == "fine"] or curve
            transitions.append(
                analyze_cdac_transition(
                    fit_points, offset=comp.analyze_offset_noise([analyze_cdac_decisions(fit_points)])
                )
            )
        cap_mismatch[adc_index] = analyze_cdac_cap_mismatch(
            cdac_measurements[adc_index],
            transitions=transitions,
            comparator=comp.analyze_offset_noise(comparator_measurements),
        )
    artifacts = []
    for adc_index, analysis in cap_mismatch.items():
        artifacts.extend(
            plot_cdac_cap_mismatch(
                cdac_measurements[adc_index],
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_cdac_cap_mismatch",
            )
        )
    artifacts.extend(
        plot_cdac_cap_mismatch_comparison(
            list(cdac_measurements.values()),
            list(cap_mismatch.values()),
            output_path=output_dir / "adc00_adc03_cdac_cap_mismatch_comparison",
        )
    )
    return tuple(artifacts)


def characterization_study() -> tuple[Path, ...]:
    """Compare the named capacitor arrays' stage weights and their code ramp against the design weights, in every PDK."""
    output_dir = new_run("analysis", "caparray")

    meas_read_dir = BASE_PATH / "build/sim/caparray/characterization/20261024_002825"
    cases = (
        ("radix17", "radix17: FRIDA-1, MSB redistribution with 5"),
        ("radix20", "radix20: FRIDA-1, repeated coarse units"),
        ("binary", "binary: 11-bit radix 2"),
        ("msb_split5", "msb_split5: MSB split with 5"),
        ("lsb_split5", "lsb_split5: LSB split with 5"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in sweep_runner.PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep in ("stage", "ramp"):
                path = meas_read_dir / pdk / name / sweep / "result.h5"
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasCapArrayTran):
                    raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCapArrayTran")
                sweeps[name, sweep] = measurement
        transfers = [analyze_caparray_transfer(sweeps[name, "ramp"]) for name, _label in cases]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_caparray_weights(
                [analyze_caparray_weights(sweeps[name, "stage"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "caparray_weights",
            ),
            *plot_caparray_transfer(transfers, labels=labels, output_path=pdk_dir / "caparray_transfer"),
            *plot_caparray_error(transfers, labels=labels, output_path=pdk_dir / "caparray_error"),
        ]
    return tuple(artifacts)
