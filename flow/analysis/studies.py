"""What the analysis studies of the blocks not on the pipeline share: explicit, manually invoked
measurement -> analysis -> plot pipelines, the ``*_study`` targets in each such block's
``targets.py`` (``python -m flow delay.characterization_study``). A block on the pipeline has no
studies: its figures of captures are ``python -m flow plot <block> <figure> --from <runs>``.

Each study pins its accepted input files or measurement directories under ``BASE_PATH``. Small
campaigns list every H5 file; large campaigns use a narrow glob within a named directory. There is
intentionally no automatic discovery of the newest run directory or of analysis pipelines.

Studies only load measurements, call analyses, pass results to later analyses, save results with
:func:`write_analysis` where another study needs them, and save figures. They never build reports.
Outputs go to a timestamped directory beneath ``build/analysis/<domain>``.
"""

from __future__ import annotations

from pathlib import Path

# the repository: every study's input directories are named under it
BASE_PATH = Path(__file__).resolve().parents[2]
