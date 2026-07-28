"""Execution of explicit typed post-processing plans."""

from __future__ import annotations

from flow.analysis.blocks import analyze_block
from flow.analysis.measure import analyze_waveform
from flow.analysis.adc import analyze_adc
from flow.analysis.models import (
    AnalysisKind,
    AnalysisPlan,
    AnalysisReport,
    AnalysisRequest,
    AnalysisResult,
    PlotArtifacts,
    PlotRequest,
    RunData,
)
from flow.analysis.plot import render_plot
from flow.analysis.io import read_run

GENERIC_ANALYSES = {
    AnalysisKind.CROSSINGS,
    AnalysisKind.EDGE_SAMPLES,
    AnalysisKind.SPECTRUM,
    AnalysisKind.DELAY,
    AnalysisKind.SETTLING,
    AnalysisKind.POWER,
    AnalysisKind.OFFSET,
    AnalysisKind.CHARGE_INJECTION,
    AnalysisKind.STATISTICS,
}
ADC_ANALYSES = {
    AnalysisKind.ADC_TRANSFER,
    AnalysisKind.ADC_ENDPOINT_LINEARITY,
    AnalysisKind.ADC_DISTRIBUTION,
    AnalysisKind.ADC_CODE_DENSITY,
    AnalysisKind.ADC_DECISION_PATHS,
    AnalysisKind.ADC_DYNAMIC,
    AnalysisKind.ADC_DYNAMIC_SWEEP,
}
BLOCK_ANALYSES = {
    AnalysisKind.COMPARATOR,
    AnalysisKind.CDAC,
    AnalysisKind.SAMPLER,
}


def _validate_plan(plan: AnalysisPlan) -> tuple[str, ...]:
    """Validate all names and return the source IDs."""

    source_ids = tuple(source.run_id for source in plan.sources)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("analysis-plan source IDs must be unique")
    analysis_names = tuple(spec.name for spec in plan.analyses)
    if len(set(analysis_names)) != len(analysis_names):
        raise ValueError("analysis-plan job names must be unique")
    if set(source_ids).intersection(analysis_names):
        raise ValueError("source IDs and analysis names must be disjoint")
    plot_names = tuple(spec.name for spec in plan.plots)
    if len(set(plot_names)) != len(plot_names):
        raise ValueError("analysis-plan plot names must be unique")
    return source_ids


def _analyze(request: AnalysisRequest) -> AnalysisResult:
    """Dispatch one resolved analysis request."""

    if request.spec.kind in GENERIC_ANALYSES:
        return analyze_waveform(request)
    if request.spec.kind in ADC_ANALYSES:
        return analyze_adc(request)
    if request.spec.kind in BLOCK_ANALYSES:
        return analyze_block(request)
    raise ValueError(f"analysis plan contains unsupported kind {request.spec.kind.value!r}")


def _run_analysis_jobs(
    plan: AnalysisPlan,
    runs: tuple[RunData, ...],
    source_ids: tuple[str, ...],
) -> tuple[AnalysisResult, ...]:
    """Resolve result dependencies and return each in-memory analysis."""

    results: list[AnalysisResult] = []
    pending = list(plan.analyses)
    available_ids = set(source_ids)
    while pending:
        ready = [spec for spec in pending if set(spec.input_ids).issubset(available_ids)]
        if not ready:
            unresolved = {spec.name: sorted(set(spec.input_ids).difference(available_ids)) for spec in pending}
            raise ValueError(f"analysis plan contains missing or cyclic dependencies: {unresolved}")
        for spec in ready:
            request = AnalysisRequest(spec=spec, runs=runs, results=tuple(results))
            result = _analyze(request)
            results.append(result)
            available_ids.add(result.name)
            pending.remove(spec)
    return tuple(results)


def _render_plots(
    plan: AnalysisPlan,
    runs: tuple[RunData, ...],
    results: tuple[AnalysisResult, ...],
) -> tuple[PlotArtifacts, ...]:
    """Render all explicit plot jobs after numerical analysis."""

    return tuple(
        render_plot(
            PlotRequest(
                spec=spec,
                runs=runs,
                results=results,
            )
        )
        for spec in plan.plots
    )


def run_analysis_plan(plan: AnalysisPlan) -> AnalysisReport:
    """Load and analyze sources, rendering only explicitly requested plots."""

    source_ids = _validate_plan(plan)
    runs = tuple(read_run(source) for source in plan.sources)
    results = _run_analysis_jobs(
        plan,
        runs,
        source_ids,
    )
    plots = _render_plots(plan, runs, results)
    return AnalysisReport(runs, results, plots)
