"""
ADC generator module for FRIDA.

Exports:
- Params: ADC parameters (every combination they admit builds)
- TbParams: the parameters of one generated testbench
- Adc: Full ADC generator (composes digital + analog)
- the analysis results (``flow.adc.types``): ``adc.AnalysisRamp``, ``adc.AnalysisDynamic``, ...
"""

from .params import Params, TbParams
from .subckt import Adc
from .types import (
    AnalysisCalibration,
    AnalysisCalibration1,
    AnalysisCalibration2,
    AnalysisCalibration3,
    AnalysisCdacSettling,
    AnalysisCodeDensityNonlinearity,
    AnalysisCodeDistribution,
    AnalysisCodeSpectrum,
    AnalysisDecisionPaths,
    AnalysisDynamic,
    AnalysisEndpointNonlinearity,
    AnalysisInterferer,
    AnalysisMismatch,
    AnalysisNoise,
    AnalysisOperatingConditions,
    AnalysisPower,
    AnalysisPowerWaveform,
    AnalysisRamp,
    AnalysisSamplingNoise,
    AnalysisTimingClosure,
    AnalysisTimingSummary,
    AnalysisTransfer,
)

__all__ = [
    "Adc",
    "AnalysisCalibration",
    "AnalysisCalibration1",
    "AnalysisCalibration2",
    "AnalysisCalibration3",
    "AnalysisCdacSettling",
    "AnalysisCodeDensityNonlinearity",
    "AnalysisCodeDistribution",
    "AnalysisCodeSpectrum",
    "AnalysisDecisionPaths",
    "AnalysisDynamic",
    "AnalysisEndpointNonlinearity",
    "AnalysisInterferer",
    "AnalysisMismatch",
    "AnalysisNoise",
    "AnalysisOperatingConditions",
    "AnalysisPower",
    "AnalysisPowerWaveform",
    "AnalysisRamp",
    "AnalysisSamplingNoise",
    "AnalysisTimingClosure",
    "AnalysisTimingSummary",
    "AnalysisTransfer",
    "Params",
    "TbParams",
]
