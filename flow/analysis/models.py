"""Backend-neutral data contracts for FRIDA post-processing.

These types deliberately model tables and metrics instead of individual
laboratory instruments, simulators, or circuit blocks.  The same structures
therefore carry physical measurements, behavioral-model output, and SPICE
results at either ADC or block level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, TypeAlias

import numpy as np

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class AdcConversion:
    """One raw FastRX conversion plus deterministic ideal-weight decoding."""

    conversion_index: int
    raw_word: int
    identifier: int
    frame: int
    spi: int
    bout: str
    dout_raw: int
    dout: int

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> AdcConversion:
        """Parse one raw ADC acquisition CSV row."""

        return cls(
            conversion_index=int(row["conversion_index"]),
            raw_word=int(row["raw_word"]),
            identifier=int(row["identifier"]),
            frame=int(row["frame"]),
            spi=int(row["spi"]),
            bout=row["bout"],
            dout_raw=int(row["dout_raw"]),
            dout=int(row["dout"]),
        )


class BackendKind(str, Enum):
    """Origin of one normalized result."""

    MEASUREMENT = "measurement"
    BEHAVIORAL = "behavioral"
    SPICE = "spice"


class BlockKind(str, Enum):
    """Circuit hierarchy represented by one result."""

    ADC = "adc"
    COMPARATOR = "comparator"
    CDAC = "cdac"
    SAMPLER = "sampler"
    GENERIC = "generic"


class SourceFormat(str, Enum):
    """Raw result representations supported by the normalization layer."""

    ADC_CSV = "adc_csv"
    SCOPE_CSV = "scope_csv"
    SCOPE_WAVEFORMS = "scope_waveforms"
    CSV = "csv"
    COLUMN_MAPPING = "column_mapping"
    SIM_RESULT = "sim_result"
    SPECTRE_NUTASCII = "spectre_nutascii"


class AnalysisKind(str, Enum):
    """Supported numerical post-processing operations."""

    CROSSINGS = "crossings"
    EDGE_SAMPLES = "edge_samples"
    SPECTRUM = "spectrum"
    DELAY = "delay"
    SETTLING = "settling"
    POWER = "power"
    OFFSET = "offset"
    CHARGE_INJECTION = "charge_injection"
    STATISTICS = "statistics"
    ADC_TRANSFER = "adc_transfer"
    ADC_ENDPOINT_LINEARITY = "adc_endpoint_linearity"
    ADC_DISTRIBUTION = "adc_distribution"
    ADC_CODE_DENSITY = "adc_code_density"
    ADC_DECISION_PATHS = "adc_decision_paths"
    ADC_DYNAMIC = "adc_dynamic"
    ADC_DYNAMIC_SWEEP = "adc_dynamic_sweep"
    COMPARATOR = "comparator"
    CDAC = "cdac"
    SAMPLER = "sampler"


class PlotKind(str, Enum):
    """Plot layouts produced from normalized runs or analysis results."""

    TIME_DOMAIN = "time_domain"
    FREQUENCY_DOMAIN = "frequency_domain"
    TRANSFER = "transfer"
    DISTRIBUTION = "distribution"
    LINEARITY = "linearity"
    DECISION_PATHS = "decision_paths"
    ADC_DYNAMIC = "adc_dynamic"
    ADC_DYNAMIC_SWEEP = "adc_dynamic_sweep"
    SWEEP = "sweep"
    MONTE_CARLO = "monte_carlo"


@dataclass(frozen=True, slots=True)
class DataColumn:
    """One named, one-dimensional column and its physical unit."""

    name: str
    values: np.ndarray
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("data-column name must not be empty")
        values = np.asarray(self.values)
        if values.ndim != 1:
            raise ValueError(f"data column {self.name!r} must be one-dimensional")
        if np.issubdtype(values.dtype, np.number) and not np.all(np.isfinite(values)):
            raise ValueError(f"numeric data column {self.name!r} contains non-finite values")
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class DataTable:
    """A named collection of aligned columns."""

    name: str
    columns: tuple[DataColumn, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("data-table name must not be empty")
        if not self.columns:
            raise ValueError(f"data table {self.name!r} must contain at least one column")
        names = tuple(column.name for column in self.columns)
        if len(set(names)) != len(names):
            raise ValueError(f"data table {self.name!r} contains duplicate columns")
        lengths = {len(column.values) for column in self.columns}
        if len(lengths) != 1:
            raise ValueError(f"data table {self.name!r} columns are not aligned: {sorted(lengths)}")

    def __len__(self) -> int:
        return len(self.columns[0].values)

    def column(self, name: str) -> np.ndarray:
        """Return one column by canonical name."""

        for column in self.columns:
            if column.name == name:
                return column.values
        raise KeyError(f"table {self.name!r} has no column {name!r}; available: {self.column_names}")

    def unit(self, name: str) -> str:
        """Return one column's unit."""

        for column in self.columns:
            if column.name == name:
                return column.unit
        raise KeyError(f"table {self.name!r} has no column {name!r}; available: {self.column_names}")

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


@dataclass(frozen=True, slots=True)
class RunData:
    """One normalized physical, behavioral, or SPICE result."""

    run_id: str
    backend: BackendKind
    block: BlockKind
    tables: tuple[DataTable, ...]
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)
    source_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.tables:
            raise ValueError(f"run {self.run_id!r} must contain at least one table")
        table_names = tuple(table.name for table in self.tables)
        if len(set(table_names)) != len(table_names):
            raise ValueError(f"run {self.run_id!r} contains duplicate table names")
        object.__setattr__(self, "source_paths", tuple(Path(path) for path in self.source_paths))

    def table(self, name: str) -> DataTable:
        """Return one table by name."""

        for table in self.tables:
            if table.name == name:
                return table
        raise KeyError(f"run {self.run_id!r} has no table {name!r}; available: {self.table_names}")

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(table.name for table in self.tables)


@dataclass(frozen=True, slots=True)
class Metric:
    """One named scalar result and its physical unit."""

    name: str
    value: float
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("metric name must not be empty")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True, slots=True)
class WaveformSettings:
    """Shared settings for event- and waveform-based measurements."""

    axis_column: str = "time_s"
    signal_columns: tuple[str, ...] = ()
    thresholds: tuple[float, ...] = ()
    rising: bool = True
    target: float | None = None
    tolerance: float | None = None
    window: str = "none"
    sample_fraction: float = 0.5


@dataclass(frozen=True, slots=True)
class AdcSettings:
    """Shared settings for ADC transfer, linearity, and dynamic analyses."""

    code_column: str = "dout"
    bits_column: str = "bout"
    input_column: str = "vin_diff_v"
    adc_bits: int = 12
    sample_rate_hz: float | None = None
    input_frequency_hz: float | None = None
    frequency_search_fraction: float = 0.02
    maximum_harmonic_order: int = 5
    code_range: tuple[int, int] | None = None
    code_weights: tuple[float, ...] = ()
    initial_estimate: float | None = None
    selection: str = "all"
    row_index: int = 0
    selected_code: int | None = None
    sweep_axis: str = "input_frequency_hz"
    sweep_group: str | None = None


@dataclass(frozen=True, slots=True)
class StatisticsSettings:
    """Settings for scalar distributions and Monte Carlo summaries."""

    value_column: str
    histogram_bins: int | str = "auto"


AnalysisSettings: TypeAlias = WaveformSettings | AdcSettings | StatisticsSettings | None


@dataclass(frozen=True, slots=True)
class AnalysisSpec:
    """Declarative definition of one analysis job."""

    name: str
    kind: AnalysisKind
    input_ids: tuple[str, ...]
    settings: AnalysisSettings = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("analysis name must not be empty")
        if not self.input_ids:
            raise ValueError(f"analysis {self.name!r} requires at least one input")


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """Resolved input to one public analysis entry point."""

    spec: AnalysisSpec
    runs: tuple[RunData, ...] = ()
    results: tuple["AnalysisResult", ...] = ()

    def __post_init__(self) -> None:
        available_ids = {run.run_id for run in self.runs} | {result.name for result in self.results}
        missing = tuple(input_id for input_id in self.spec.input_ids if input_id not in available_ids)
        if missing:
            raise ValueError(f"analysis {self.spec.name!r} is missing inputs {missing}")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Backend-neutral output of one numerical analysis."""

    name: str
    kind: AnalysisKind
    source_ids: tuple[str, ...]
    metrics: tuple[Metric, ...] = ()
    tables: tuple[DataTable, ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("analysis-result name must not be empty")
        metric_names = tuple(metric.name for metric in self.metrics)
        if len(set(metric_names)) != len(metric_names):
            raise ValueError(f"analysis result {self.name!r} contains duplicate metrics")
        table_names = tuple(table.name for table in self.tables)
        if len(set(table_names)) != len(table_names):
            raise ValueError(f"analysis result {self.name!r} contains duplicate tables")

    def metric(self, name: str) -> float:
        """Return one scalar metric by name."""

        for metric in self.metrics:
            if metric.name == name:
                return metric.value
        raise KeyError(f"result {self.name!r} has no metric {name!r}; available: {self.metric_names}")

    def metric_unit(self, name: str) -> str:
        """Return one scalar metric's unit."""

        for metric in self.metrics:
            if metric.name == name:
                return metric.unit
        raise KeyError(f"result {self.name!r} has no metric {name!r}; available: {self.metric_names}")

    def table(self, name: str) -> DataTable:
        """Return one result table by name."""

        for table in self.tables:
            if table.name == name:
                return table
        raise KeyError(f"result {self.name!r} has no table {name!r}; available: {self.table_names}")

    @property
    def metric_names(self) -> tuple[str, ...]:
        return tuple(metric.name for metric in self.metrics)

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(table.name for table in self.tables)


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """One raw source and the metadata required to normalize it."""

    run_id: str
    backend: BackendKind
    block: BlockKind
    format: SourceFormat
    source: Any
    table_name: str = "data"
    analysis_index: int = 0
    column_map: Mapping[str, str] = field(default_factory=dict)
    units: Mapping[str, str] = field(default_factory=dict)
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlotSpec:
    """Declarative definition of one plot job."""

    name: str
    kind: PlotKind
    input_ids: tuple[str, ...]
    output_path: Path
    title: str | None = None
    table: str | None = None
    x_column: str | None = None
    y_columns: tuple[str, ...] = ()
    group_column: str | None = None
    labels: Mapping[str, str] = field(default_factory=dict)
    info_lines: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    legend_title: str | None = None
    formats: tuple[str, ...] = ("png", "pdf", "svg")
    x_limit: tuple[float, float] | None = None
    y_limit: tuple[float, float] | None = None
    x_ticks: tuple[float, ...] = ()
    secondary_x_reciprocal: float | None = None
    secondary_x_label: str | None = None


@dataclass(frozen=True, slots=True)
class PlotRequest:
    """Resolved input to the shared plotting entry point."""

    spec: PlotSpec
    runs: tuple[RunData, ...] = ()
    results: tuple[AnalysisResult, ...] = ()


@dataclass(frozen=True, slots=True)
class PlotArtifacts:
    """Files generated by one plot request."""

    name: str
    paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class AnalysisPlan:
    """Explicit sources, numerical jobs, and plots for one post-processing run."""

    sources: tuple[SourceSpec, ...]
    analyses: tuple[AnalysisSpec, ...]
    plots: tuple[PlotSpec, ...]


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    """Complete in-memory result plus explicitly requested plot artifacts."""

    runs: tuple[RunData, ...]
    results: tuple[AnalysisResult, ...]
    plots: tuple[PlotArtifacts, ...]
