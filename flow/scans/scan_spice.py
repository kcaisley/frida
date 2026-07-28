"""Convert Spectre ADC PEX nutascii output into typed ADC conversion CSVs.

Before running this parser, first run the configured Spectre PEX decks:

    ./design/spice/adc_pex_monotonic.sh
    ./design/spice/adc_pex_bss.sh

Then parse the generated raw files into CSVs and transfer plots:

    uv run python -m flow.scans.scan_spice

The raw/CSV paths are listed in ``ADC_PEX_POSTPROCESS_RUNS`` below.

The output CSV uses the same :class:`AdcConversion` fields as the physical
scan. Spectre does not produce a Basil FastRX packet, so ``raw_word`` and
``spi`` contain the same synthetic 17-bit word packed from the sampled
comparator bits. Canonical in-memory columns feed the shared typed analysis
pipeline; no legacy-format CSV is written.
"""

from __future__ import annotations

import bisect
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from flow.cdac import get_cdac_weights
from flow.analysis.models import (
    AdcConversion,
    AdcSettings,
    AnalysisKind,
    AnalysisPlan,
    AnalysisSpec,
    BackendKind,
    BlockKind,
    PlotKind,
    PlotSpec,
    SourceFormat,
    SourceSpec,
)
from flow.analysis.runner import run_analysis_plan
from flow.scans.params import AdcTbParams
from flow.analysis.io import parse_spectre_nutascii
from flow.scans.results import write_adc_conversions
from flow.scans.scan_adc import (
    convert_dac_caps_to_adc_weights,
    convert_dout_to_normalized_dout,
)

ADC_INDEX = 0
PARAMS = AdcTbParams()
CODE_WEIGHTS = convert_dac_caps_to_adc_weights(get_cdac_weights(PARAMS.dut.cdac))
NUM_CAPTURE_BITS = len(CODE_WEIGHTS)
LOGIC_THRESHOLD_V = 0.6
COMP_SAMPLE_DELAY_S = 10e-9
COMP_SIGNAL = "comp_out"
CLOCK_SIGNAL = "seq_comp"
VINP_SIGNAL = "vin_p"
VINN_SIGNAL = "vin_n"

ADC_PEX_MONOTONIC_NAME = "monotonic"
ADC_PEX_MONOTONIC_RAW = Path("build/adc_pex_monotonic/tb_adc_pex_monotonic.raw")
ADC_PEX_MONOTONIC_CSV = Path("build/adc_pex_monotonic/adc_00.csv")
ADC_PEX_MONOTONIC_TITLE = "FRIDA ADC PEX monotonic voltage sweep"
ADC_PEX_MONOTONIC_LABEL = "PEX monotonic conversions"
ADC_PEX_MONOTONIC_COLOR = "green"

ADC_PEX_BSS_NAME = "bss"
ADC_PEX_BSS_RAW = Path("build/adc_pex_bss/tb_adc_pex_bss.raw")
ADC_PEX_BSS_CSV = Path("build/adc_pex_bss/adc_00.csv")
ADC_PEX_BSS_TITLE = "FRIDA ADC PEX BSS voltage sweep"
ADC_PEX_BSS_LABEL = "PEX BSS conversions"
ADC_PEX_BSS_COLOR = "orange"

ADC_PEX_NOISE_NAME = "noise"
ADC_PEX_NOISE_RAW = Path("build/adc_pex_noise/tb_adc_pex_noise.raw")
ADC_PEX_NOISE_CSV = Path("build/adc_pex_noise/adc00_dinit0101010101010101_noise_pex.csv")
ADC_PEX_NOISE_DAC_INIT = "0101010101010101"
ADC_PEX_NOISE_SETUP = "pex"

ADC_PEX_POSTPROCESS_RUNS = [
    {
        "name": ADC_PEX_MONOTONIC_NAME,
        "raw": ADC_PEX_MONOTONIC_RAW,
        "csv": ADC_PEX_MONOTONIC_CSV,
        "title": ADC_PEX_MONOTONIC_TITLE,
        "label": ADC_PEX_MONOTONIC_LABEL,
        "color": ADC_PEX_MONOTONIC_COLOR,
        "plot": "transfer",
    },
    {
        "name": ADC_PEX_BSS_NAME,
        "raw": ADC_PEX_BSS_RAW,
        "csv": ADC_PEX_BSS_CSV,
        "title": ADC_PEX_BSS_TITLE,
        "label": ADC_PEX_BSS_LABEL,
        "color": ADC_PEX_BSS_COLOR,
        "plot": "transfer",
    },
    {
        "name": ADC_PEX_NOISE_NAME,
        "raw": ADC_PEX_NOISE_RAW,
        "csv": ADC_PEX_NOISE_CSV,
        "plot": "noise",
        "dac_init_state": ADC_PEX_NOISE_DAC_INIT,
        "setup": ADC_PEX_NOISE_SETUP,
    },
]


def require_signal(data: Mapping[str, Sequence[float]], name: str) -> Sequence[float]:
    if name in data:
        return data[name]

    matches = [key for key in data if key.endswith(name)]
    if len(matches) == 1:
        return data[matches[0]]
    if matches:
        raise KeyError(f"signal {name!r} is ambiguous; matches: {matches}")
    raise KeyError(f"signal {name!r} not found. Available signals include: {list(data)[:20]}")


def rising_edges(
    times: Sequence[float],
    values: Sequence[float],
    threshold: float,
) -> list[float]:
    edges: list[float] = []
    last = values[0] > threshold
    for time, value in zip(times[1:], values[1:], strict=True):
        current = value > threshold
        if current and not last:
            edges.append(time)
        last = current
    return edges


def nearest_value(
    times: Sequence[float],
    values: Sequence[float],
    target: float,
) -> float:
    index = bisect.bisect_left(times, target)
    if index <= 0:
        return values[0]
    if index >= len(times):
        return values[-1]
    before = index - 1
    if abs(times[index] - target) < abs(target - times[before]):
        return values[index]
    return values[before]


def bits_to_word(bits: list[int]) -> int:
    word = 0
    for bit in bits:
        word = (word << 1) | int(bit)
    return word


def convert_raw_to_adc_conversions(
    data: Mapping[str, Sequence[float]],
    *,
    threshold: float,
    sample_delay: float,
    comp_signal: str,
    clock_signal: str,
    vinp_signal: str,
    vinn_signal: str,
) -> tuple[list[AdcConversion], dict[str, list[int | float | str]]]:
    """Sample comparator decisions and return typed rows plus analysis columns."""

    times = require_signal(data, "time")
    comp = require_signal(data, comp_signal)
    clock = require_signal(data, clock_signal)
    vinp = require_signal(data, vinp_signal)
    vinn = require_signal(data, vinn_signal)

    edge_times = rising_edges(times, clock, threshold)
    n_complete = len(edge_times) // NUM_CAPTURE_BITS
    n_extra = len(edge_times) % NUM_CAPTURE_BITS
    if n_extra:
        print(
            f"warning: ignoring {n_extra} extra {clock_signal} rising edges after {n_complete} complete conversions",
            file=sys.stderr,
        )

    conversions: list[AdcConversion] = []
    analysis_columns: dict[str, list[int | float | str]] = {
        "conversion_index": [],
        "bout": [],
        "dout": [],
        "vin_diff_v": [],
    }
    for sweep_index in range(n_complete):
        conversion_edges = edge_times[sweep_index * NUM_CAPTURE_BITS : (sweep_index + 1) * NUM_CAPTURE_BITS]
        sample_times = [edge + sample_delay for edge in conversion_edges]
        bits = [int(nearest_value(times, comp, sample_time) > threshold) for sample_time in sample_times]
        bout = "".join(str(bit) for bit in bits)
        dout_raw = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, bits, strict=True))
        dout = convert_dout_to_normalized_dout(
            dout_raw,
            CODE_WEIGHTS,
            PARAMS.dut.adc_bits,
        )
        spi = bits_to_word(bits)
        vin_set = nearest_value(times, vinp, conversion_edges[0])
        vin_n = nearest_value(times, vinn, conversion_edges[0])

        conversions.append(
            AdcConversion(
                conversion_index=sweep_index,
                raw_word=spi,
                identifier=0,
                frame=sweep_index,
                spi=spi,
                bout=bout,
                dout_raw=dout_raw,
                dout=dout,
            )
        )
        analysis_columns["conversion_index"].append(sweep_index)
        analysis_columns["bout"].append(bout)
        analysis_columns["dout"].append(dout)
        analysis_columns["vin_diff_v"].append(vin_set - vin_n)
        print(
            f"conversion {sweep_index:02d}: Vin_p={vin_set:.6g} V "
            f"Vin_n={vin_n:.6g} V Bout={bout} "
            f"Dout_raw={dout_raw} Dout={dout}"
        )

    return conversions, analysis_columns


def process_run(run: Mapping[str, object]) -> None:
    raw = run["raw"]
    csv = run["csv"]
    if not isinstance(raw, Path) or not isinstance(csv, Path):
        raise TypeError(f"invalid ADC PEX run paths: {run}")

    if not raw.exists():
        print(f"warning: skipping {run['name']}; missing raw file {raw}", file=sys.stderr)
        return

    print(f"processing {run['name']}: {raw}")
    data = parse_spectre_nutascii(raw, {"time", COMP_SIGNAL, CLOCK_SIGNAL, VINP_SIGNAL, VINN_SIGNAL})
    conversions, analysis_columns = convert_raw_to_adc_conversions(
        data,
        threshold=LOGIC_THRESHOLD_V,
        sample_delay=COMP_SAMPLE_DELAY_S,
        comp_signal=COMP_SIGNAL,
        clock_signal=CLOCK_SIGNAL,
        vinp_signal=VINP_SIGNAL,
        vinn_signal=VINN_SIGNAL,
    )
    write_adc_conversions(csv, conversions)
    print(f"ADC {ADC_INDEX:02d}: saved typed data to {csv}")

    run_name = f"adc{ADC_INDEX:02d}_{run['name']}_pex"
    source = SourceSpec(
        run_id=run_name,
        backend=BackendKind.SPICE,
        block=BlockKind.ADC,
        format=SourceFormat.COLUMN_MAPPING,
        source=analysis_columns,
        table_name="conversions",
        parameters={
            "raw_path": str(raw),
            "conversion_csv": str(csv),
            "setup": str(run.get("setup", "")),
            "dac_init_state": str(run.get("dac_init_state", "n/a")),
        },
    )
    adc_settings = AdcSettings(
        adc_bits=PARAMS.dut.adc_bits,
        code_weights=tuple(CODE_WEIGHTS),
        selection="all",
    )
    analyses = []
    plots = []
    if run.get("plot") == "noise":
        distribution_name = f"{run_name}_distribution"
        decision_name = f"{run_name}_decision_paths"
        analyses.extend(
            (
                AnalysisSpec(
                    distribution_name,
                    AnalysisKind.ADC_DISTRIBUTION,
                    (run_name,),
                    adc_settings,
                ),
                AnalysisSpec(
                    decision_name,
                    AnalysisKind.ADC_DECISION_PATHS,
                    (run_name,),
                    adc_settings,
                ),
            )
        )
        plots.extend(
            (
                PlotSpec(
                    distribution_name,
                    PlotKind.DISTRIBUTION,
                    (distribution_name,),
                    csv.parent / f"{distribution_name}.png",
                    title="FRIDA ADC PEX fixed-input distribution",
                ),
                PlotSpec(
                    decision_name,
                    PlotKind.DECISION_PATHS,
                    (decision_name,),
                    csv.parent / f"{decision_name}.png",
                    title="FRIDA ADC PEX decision paths",
                ),
            )
        )
    else:
        transfer_name = f"{run_name}_transfer"
        analyses.append(
            AnalysisSpec(
                transfer_name,
                AnalysisKind.ADC_TRANSFER,
                (run_name,),
                adc_settings,
            )
        )
        plots.append(
            PlotSpec(
                transfer_name,
                PlotKind.TRANSFER,
                (transfer_name,),
                csv.parent / f"{transfer_name}.png",
                title=str(run.get("title", "FRIDA ADC PEX transfer")),
            )
        )
    run_analysis_plan(
        AnalysisPlan(
            sources=(source,),
            analyses=tuple(analyses),
            plots=tuple(plots),
        )
    )


def main() -> None:
    for run in ADC_PEX_POSTPROCESS_RUNS:
        process_run(run)


if __name__ == "__main__":
    main()
