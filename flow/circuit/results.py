"""Read circuit simulation results: a saved transient as VLSIR holds it, or as one ``Wave`` (a
block's own reader decodes it further: the ADC's, ``flow.adc.sim``)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
from vlsirtools.spice.sim_data import TranResult

from flow.analysis import calc
from flow.analysis.io import interpolate_wave_records
from flow.analysis.types import Wave

# Spectre strobe timestamps can jitter by sub-femtoseconds around a 10 ps grid.
_RAW_STEP_RTOL = 1e-3


def read_raw_transient(path: Path) -> TranResult:
    """Read a saved transient with VLSIR, preserving all raw variable names."""
    from vlsirtools.spice.spectre import parse_nutbin

    with path.open("rb") as stream:
        plots = parse_nutbin(stream)
    transient = [plot for plot in plots.values() if "time" in plot.data]
    if len(transient) != 1:
        raise ValueError("Raw file must contain exactly one transient analysis")
    plot = transient[0]
    return TranResult(plot.analysis_name, plot.data, {})


def _is_valid_transient(result: TranResult, names: Mapping[str, str], interval: float) -> bool:
    """Check transient shape, complete bindings, and a requested sampling interval."""
    if not isinstance(result, TranResult) or not np.isfinite(interval) or interval <= 0:
        return False
    if set(result.data) != set(names) or names.get("time") != "time":
        return False
    if len(set(names.values())) != len(names):
        return False
    time = np.asarray(result.data["time"])
    return bool(
        time.ndim == 1
        and len(time) >= 2
        and np.all(np.isfinite(time))
        and np.all(np.diff(time) > 0)
        and calc.ymax(np.diff(time)) <= interval * (1 + _RAW_STEP_RTOL)
        and all(np.asarray(value).shape == time.shape and np.all(np.isfinite(value)) for value in result.data.values())
    )


def conversion_inputs(result: TranResult, names: Mapping[str, str], interval: float, *, supply_rails: tuple[str, ...]):
    """A saved transient's time, voltages and currents by ``names``' aliases, the ``supply_rails``
    sources' currents as positive draw (other currents in the simulator's reference direction).
    Raises unless the raw holds exactly those traces, finite, on steps no longer than ``interval``
    (Spectre's sub-femtosecond jitter aside): a block's reader decodes them further."""
    if not _is_valid_transient(result, names, interval):
        raise ValueError(
            "Invalid transient: require complete unique bindings, aligned finite traces, and raw timestep no larger than waveform_sample_interval_s"
        )
    # VLSIR owns the numerical representation; only its variable names change.
    canonical = TranResult(
        result.analysis_name, {names[key]: np.asarray(value) for key, value in result.data.items()}, result.measurements
    )
    voltage = {key: value for key, value in canonical.data.items() if key != "time" and not key.startswith("i(")}
    current = {
        key[2:-1]: -value if key[2:-1] in supply_rails else value
        for key, value in canonical.data.items()
        if key.startswith("i(")
    }
    return canonical.data["time"], voltage, current


def read_transient_wave(
    path: Path, names: Mapping[str, str], interval: float, *, supply_rails: tuple[str, ...]
) -> tuple[Wave, int]:
    """One saved transient as a single-record ``Wave`` on the uniform ``interval`` grid over its
    whole time, and the raw point count: traces renamed by ``names`` (which binds every saved trace,
    ``time`` to itself), the ``supply_rails`` sources' currents as positive draw. Raises unless the
    raw holds exactly those traces, finite, on steps no longer than ``interval``."""

    times_s, voltages, currents = conversion_inputs(
        read_raw_transient(path), names, interval, supply_rails=supply_rails
    )
    window = [(float(times_s[0]), float(times_s[-1]))]
    time_s, v = interpolate_wave_records(times_s, voltages, window, interval)
    _, i = interpolate_wave_records(times_s, currents, window, interval)
    return Wave(record_index=np.arange(1, dtype=np.int64), time_s=time_s, v=v, i=i), len(times_s)
