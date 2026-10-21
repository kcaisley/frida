"""What the analysis studies share: explicit, manually invoked measurement -> analysis -> plot
pipelines, the ``*_study`` targets in each block's ``targets.py``
(``python -m flow adc.sample_rate_study``).

Each study pins its accepted input files or measurement directories under ``BASE_PATH``. Small
campaigns list every H5 file; large campaigns use a narrow glob within a named directory. There is
intentionally no automatic discovery of the newest run directory or of analysis pipelines.

Studies only load measurements, call analyses, pass results to later analyses, save results with
:func:`write_analysis` where another study needs them, and save figures. They never build reports.
Outputs go to a timestamped directory beneath ``build/analysis/<domain>``.
"""

from __future__ import annotations

from pathlib import Path

from flow.adc.sequences import SEQUENCES

# the repository: every study's input directories are named under it
BASE_PATH = Path(__file__).resolve().parents[2]

# the 256-symbol recipe's logic timings at comparator timing 11110000 (the sample-rate study's LOGIC n/8)
timing_sequences = tuple(
    sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)
