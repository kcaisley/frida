"""Convert Spectre ADC PEX NUTASCII output into typed HDF5 measurements.

Run the configured Spectre decks first, then parse their raw files:

    ./design/spice/adc_pex_monotonic.sh
    ./design/spice/adc_pex_bss.sh
    uv run python -m flow.scans.scan_spice
"""

from __future__ import annotations

import bisect
import dataclasses
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import numpy as np

from flow.analysis.io import (
    interpolate_wave_records,
    parse_spectre_nutascii,
    write_measurement,
)
from flow.analysis.types import AdcDaq, AdcExtWave, MeasAdcExt, MeasInfo
from flow.cdac import get_cdac_weights
from flow.scans.params import AdcTbParams
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
LOGIC_SIGNAL = "seq_update"
VINP_SIGNAL = "vin_p"
VINN_SIGNAL = "vin_n"
WAVE_SAMPLES_PER_CONVERSION = 2_000

ADC_PEX_POSTPROCESS_RUNS = (
    {
        "name": "monotonic",
        "raw": Path("build/adc_pex_monotonic/tb_adc_pex_monotonic.raw"),
        "h5": Path("build/adc_pex_monotonic/adc_00.h5"),
    },
    {
        "name": "bss",
        "raw": Path("build/adc_pex_bss/tb_adc_pex_bss.raw"),
        "h5": Path("build/adc_pex_bss/adc_00.h5"),
    },
    {
        "name": "noise",
        "raw": Path("build/adc_pex_noise/tb_adc_pex_noise.raw"),
        "h5": Path("build/adc_pex_noise/adc00_dinit0101010101010101_noise_pex.h5"),
    },
)


def require_signal(
    data: Mapping[str, Sequence[float]],
    name: str,
) -> Sequence[float]:
    """Resolve one exact or uniquely suffixed simulator signal."""

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
    """Return sample coordinates where a signal crosses high."""

    if len(times) != len(values):
        raise ValueError("edge time and value arrays must be aligned")
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
    """Return the value at the nearest simulator sample."""

    index = bisect.bisect_left(times, target)
    if index <= 0:
        return values[0]
    if index >= len(times):
        return values[-1]
    before = index - 1
    return values[index] if abs(times[index] - target) < abs(target - times[before]) else values[before]


def bits_to_word(bits: Sequence[int]) -> int:
    """Pack an MSB-first bit vector into one integer."""

    word = 0
    for bit in bits:
        word = (word << 1) | int(bit)
    return word


def convert_raw_to_adc_measurement(
    data: Mapping[str, Sequence[float]],
    *,
    params: AdcTbParams,
    raw_path: Path,
    threshold: float = LOGIC_THRESHOLD_V,
    sample_delay: float = COMP_SAMPLE_DELAY_S,
) -> MeasAdcExt:
    """Sample comparator decisions and retain dense external waveforms."""

    times = np.asarray(require_signal(data, "time"), dtype=np.float64)
    comp = np.asarray(require_signal(data, COMP_SIGNAL), dtype=np.float64)
    clock = np.asarray(require_signal(data, CLOCK_SIGNAL), dtype=np.float64)
    logic = np.asarray(require_signal(data, LOGIC_SIGNAL), dtype=np.float64)
    vin_p = np.asarray(require_signal(data, VINP_SIGNAL), dtype=np.float64)
    vin_n = np.asarray(require_signal(data, VINN_SIGNAL), dtype=np.float64)

    edge_times = rising_edges(times, clock, threshold)
    n_complete = len(edge_times) // NUM_CAPTURE_BITS
    n_extra = len(edge_times) % NUM_CAPTURE_BITS
    if n_extra:
        print(
            f"warning: ignoring {n_extra} extra {CLOCK_SIGNAL} rising edges after {n_complete} complete conversions",
            file=sys.stderr,
        )
    if not n_complete:
        raise ValueError("raw result contains no complete ADC conversions")
    params = dataclasses.replace(params, conversions=n_complete)

    conversion_index = np.arange(n_complete, dtype=np.int64)
    bout = np.empty((n_complete, NUM_CAPTURE_BITS), dtype=np.uint8)
    dout_raw = np.empty(n_complete, dtype=np.int64)
    dout = np.empty(n_complete, dtype=np.int64)
    vin_diff_v = np.empty(n_complete, dtype=np.float64)
    conversion_starts = []
    for index in range(n_complete):
        conversion_edges = edge_times[index * NUM_CAPTURE_BITS : (index + 1) * NUM_CAPTURE_BITS]
        sample_times = [edge + sample_delay for edge in conversion_edges]
        bits = np.asarray(
            [int(nearest_value(times, comp, sample_time) > threshold) for sample_time in sample_times],
            dtype=np.uint8,
        )
        bout[index] = bits
        dout_raw[index] = sum(weight * int(bit) for weight, bit in zip(CODE_WEIGHTS, bits, strict=True))
        dout[index] = convert_dout_to_normalized_dout(
            int(dout_raw[index]),
            CODE_WEIGHTS,
            params.dut.adc_bits,
        )
        conversion_starts.append(conversion_edges[0])
        vin_diff_v[index] = nearest_value(
            times,
            vin_p - vin_n,
            conversion_edges[0],
        )
        print(
            f"conversion {index:02d}: Vin_diff={vin_diff_v[index]:.6g} V "
            f"Bout={''.join(str(bit) for bit in bits)} "
            f"Dout_raw={dout_raw[index]} Dout={dout[index]}"
        )

    if n_complete > 1:
        record_duration_s = float(np.median(np.diff(conversion_starts)))
    else:
        record_duration_s = min(
            float(times[-1] - conversion_starts[0]),
            len(params.seq_init_pattern) / float(params.symbol_rate),
        )
    waveform_indices = []
    windows = []
    for index, start_s in enumerate(conversion_starts):
        stop_s = start_s + record_duration_s
        if stop_s <= times[-1]:
            waveform_indices.append(index)
            windows.append((start_s, stop_s))
    relative_time_s, records = interpolate_wave_records(
        times,
        {
            "vin_diff_v": vin_p - vin_n,
            "seq_comp_v": clock,
            "seq_logic_v": logic,
            "comp_out_v": comp,
        },
        windows,
        WAVE_SAMPLES_PER_CONVERSION,
    )
    return MeasAdcExt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcExt",
            backend="spice",
            timestamp_utc=datetime.now().astimezone(),
            instruments={"simulator": "Spectre"},
            readbacks={"raw_file": str(raw_path)},
        ),
        param=params,
        daq=AdcDaq(
            conversion_index=conversion_index,
            bout=bout,
            dout_raw=dout_raw,
            dout=dout,
            vin_diff_v=vin_diff_v,
        ),
        wave=AdcExtWave(
            conversion_index=waveform_indices,
            time_s=relative_time_s,
            **records,
        ),
    )


def process_run(run: Mapping[str, object]) -> None:
    """Convert one configured raw file when it exists."""

    raw = run["raw"]
    h5_path = run["h5"]
    if not isinstance(raw, Path) or not isinstance(h5_path, Path):
        raise TypeError(f"invalid ADC PEX run paths: {run}")
    if not raw.exists():
        print(
            f"warning: skipping {run['name']}; missing raw file {raw}",
            file=sys.stderr,
        )
        return

    print(f"processing {run['name']}: {raw}")
    data = parse_spectre_nutascii(
        raw,
        {
            "time",
            COMP_SIGNAL,
            CLOCK_SIGNAL,
            LOGIC_SIGNAL,
            VINP_SIGNAL,
            VINN_SIGNAL,
        },
    )
    measurement = convert_raw_to_adc_measurement(
        data,
        params=PARAMS,
        raw_path=raw,
    )
    write_measurement(h5_path, measurement)
    print(f"ADC {ADC_INDEX:02d}: saved typed measurement to {h5_path}")


def main() -> None:
    for run in ADC_PEX_POSTPROCESS_RUNS:
        process_run(run)


if __name__ == "__main__":
    main()
