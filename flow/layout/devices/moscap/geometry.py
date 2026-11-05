"""What a MOS capacitor is drawn as: a core transistor of ``units`` unit widths at ``CAP_L`` minimum
lengths, its gate the capacitor's node and its channel and bulk on a rail (ALIGN's ``MOSGenerator``)."""

from __future__ import annotations

from dataclasses import dataclass

from hdl21.primitives import MosType, MosVth

# its length in minimum lengths: long enough that its gate area, not its overlap and fringe, holds
# the charge, short enough for every PDK's models
CAP_L = 8


@dataclass(frozen=True)
class MosCapGeometry:
    """A MOS capacitor: ``units`` unit widths of a ``tp`` transistor at ``CAP_L`` minimum lengths."""

    tp: MosType
    vth: MosVth
    units: int
