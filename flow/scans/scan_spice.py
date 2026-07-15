"""Convert Spectre ADC PEX nutascii output into basic.py-style scan CSV.

Before running this parser, first run the configured Spectre PEX decks:

    ./design/spice/adc_pex_monotonic.sh
    ./design/spice/adc_pex_bss.sh

Then parse the generated raw files into CSVs and transfer plots:

    uv run python -m flow.scans.scan_spice

The raw/CSV paths are listed in ``ADC_PEX_POSTPROCESS_RUNS`` below.

The output CSV uses the same columns as ``flow/scans/basic.py``. Spectre does
not produce a Basil FastRX packet, so ``raw_word`` and ``spi`` contain the same
synthetic 17-bit word packed from the sampled comparator bits.
"""

from __future__ import annotations

import bisect
import sys
from pathlib import Path

from flow.scans.basic import ADC_CODE_WEIGHTS, NUM_CAPTURE_BITS
from flow.scans.plot import plot_adc_transfer, plot_code_histogram, plot_decision_paths, write_adc_csv

ADC_INDEX = 0
CODE_WEIGHTS = ADC_CODE_WEIGHTS[ADC_INDEX]
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


def parse_spectre_nutascii(path: Path, selected_signals: set[str] | None = None) -> dict[str, list[float]]:
    """Parse a Spectre nutascii raw file into ``signal_name -> values`` lists.

    ``selected_signals`` keeps large PEX transient-noise runs tractable by only
    storing the few top-level signals needed for ADC decoding.
    """
    header_lines = []
    with path.open(errors="replace") as f:
        for line in f:
            if line.strip() == "Values:":
                break
            header_lines.append(line)
        else:
            raise ValueError(f"{path} does not look like complete nutascii output: missing 'Values:' section")

        var_names: list[str] = []
        in_vars = False
        for line in header_lines:
            parts = line.strip().split()
            if not parts:
                continue

            if parts[0] == "Variables:":
                in_vars = True
                if len(parts) >= 4 and parts[1].isdigit():
                    var_names.append(parts[2])
                continue

            if in_vars:
                if parts[0].isdigit() and len(parts) >= 3:
                    var_names.append(parts[1])
                elif not parts[0].isdigit():
                    in_vars = False

        if not var_names:
            raise ValueError(f"could not parse variable list from {path}")

        n_vars = len(var_names)
        selected = selected_signals or set(var_names)
        selected_indices = {index: name for index, name in enumerate(var_names) if name in selected}
        parsed = {name: [] for name in selected_indices.values()}
        stride = n_vars + 1  # point index plus all variable values
        tokens: list[str] = []
        n_points = 0

        for line in f:
            tokens.extend(line.split())
            while len(tokens) >= stride:
                point_tokens = tokens[:stride]
                del tokens[:stride]
                base = 1
                for index, name in selected_indices.items():
                    parsed[name].append(float(point_tokens[base + index]))
                n_points += 1

        if n_points == 0:
            raise ValueError(f"no raw data points parsed from {path}")
        if tokens:
            print(
                f"warning: ignoring {len(tokens)} trailing numeric tokens in {path}; raw may be from an interrupted run",
                file=sys.stderr,
            )

    return parsed


def require_signal(data: dict[str, list[float]], name: str) -> list[float]:
    if name in data:
        return data[name]

    matches = [key for key in data if key.endswith(name)]
    if len(matches) == 1:
        return data[matches[0]]
    if matches:
        raise KeyError(f"signal {name!r} is ambiguous; matches: {matches}")
    raise KeyError(f"signal {name!r} not found. Available signals include: {list(data)[:20]}")


def rising_edges(times: list[float], values: list[float], threshold: float) -> list[float]:
    edges: list[float] = []
    last = values[0] > threshold
    for time, value in zip(times[1:], values[1:], strict=True):
        current = value > threshold
        if current and not last:
            edges.append(time)
        last = current
    return edges


def nearest_value(times: list[float], values: list[float], target: float) -> float:
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


def rows_from_raw(
    data: dict[str, list[float]],
    *,
    adc_index: int,
    threshold: float,
    sample_delay: float,
    comp_signal: str,
    clock_signal: str,
    vinp_signal: str,
    vinn_signal: str,
) -> list[dict[str, object]]:
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

    rows: list[dict[str, object]] = []
    for sweep_index in range(n_complete):
        conversion_edges = edge_times[sweep_index * NUM_CAPTURE_BITS : (sweep_index + 1) * NUM_CAPTURE_BITS]
        sample_times = [edge + sample_delay for edge in conversion_edges]
        bits = [int(nearest_value(times, comp, sample_time) > threshold) for sample_time in sample_times]
        bbits = "".join(str(bit) for bit in bits)
        dout = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, bits, strict=True))
        spi = bits_to_word(bits)
        vin_set = nearest_value(times, vinp, conversion_edges[0])
        vin_read = vin_set
        vin_n = nearest_value(times, vinn, conversion_edges[0])

        rows.append(
            {
                "adc": adc_index,
                "sweep_index": sweep_index,
                "vin_set_v": vin_set,
                "vin_read_v": vin_read,
                "vdiff_v": vin_set - vin_n,
                "conversion_index": 0,
                "raw_word": spi,
                "id": 0,
                "frame": sweep_index,
                "spi": spi,
                "Bbits": bbits,
                "Dout": dout,
                "Dout_raw": dout,
            }
        )
        print(f"conversion {sweep_index:02d}: Vin_p={vin_set:.6g} V Vin_n={vin_n:.6g} V Bbits={bbits} Dout={dout}")

    return rows


def process_run(run: dict[str, object]) -> None:
    raw = run["raw"]
    csv = run["csv"]
    if not isinstance(raw, Path) or not isinstance(csv, Path):
        raise TypeError(f"invalid ADC PEX run paths: {run}")

    if not raw.exists():
        print(f"warning: skipping {run['name']}; missing raw file {raw}", file=sys.stderr)
        return

    print(f"processing {run['name']}: {raw}")
    data = parse_spectre_nutascii(raw, {"time", COMP_SIGNAL, CLOCK_SIGNAL, VINP_SIGNAL, VINN_SIGNAL})
    rows = rows_from_raw(
        data,
        adc_index=ADC_INDEX,
        threshold=LOGIC_THRESHOLD_V,
        sample_delay=COMP_SAMPLE_DELAY_S,
        comp_signal=COMP_SIGNAL,
        clock_signal=CLOCK_SIGNAL,
        vinp_signal=VINP_SIGNAL,
        vinn_signal=VINN_SIGNAL,
    )
    write_adc_csv(ADC_INDEX, rows, csv.parent, csv_path=csv)

    adc_cfg = {
        "adc_index": ADC_INDEX,
        "artifact_stem": csv.stem.removesuffix("_noise_pex"),
        "setup": str(run.get("setup", "")),
        "dac_init_state": str(run.get("dac_init_state", "n/a")),
        "dac_diffcaps": True,
        "num_samples": len(rows),
        "seq_base_freq_hz": 50_000_000,
        "conversion_steps": 40,
        "input_ramp": "fixed 612 mV",
        "code_range": (1, 4094),
        "code_weights": CODE_WEIGHTS,
    }
    if run.get("plot") == "noise":
        plot_code_histogram(adc_cfg, csv, csv.parent)
        plot_decision_paths(
            adc_cfg,
            csv,
            csv.parent,
            filter_mode="all",
            show_reference_lines=False,
            show_mean_path=False,
        )
    else:
        plot_adc_transfer(adc_cfg, csv, csv.parent)


def main() -> None:
    for run in ADC_PEX_POSTPROCESS_RUNS:
        process_run(run)


if __name__ == "__main__":
    main()
