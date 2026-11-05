"""What a MOM capacitor is drawn as: a style (``MomStyle``) on one to three of the PDK's MOM metals
with its finger lengths (``MomcapGeometry``), the parameters ALIGN's ``MomUnit``
(``flow/layout/primitives/mom.py``) draws in ALIGN's own process.

Every style stacks the same plates on its metals at their minimum width and space, the plates of
one terminal joined through vias, over a shield on the metal below:

- ``DIFFERENCE``: a ring (the top plate) around two inner fingers in line, each from one end, a
  main and a difference finger (FRIDA's CDAC strip: its weight is the difference);
- ``RING``: a ring around one inner finger (a unit capacitor);
- ``STRIP``: two open-ended strips side by side.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class MomStyle(Enum):
    DIFFERENCE = auto()
    RING = auto()
    STRIP = auto()


class Neighbour(Enum):
    """What an array unit's side meets (``MomUnit``'s channels): a piece of its own stage, its
    bottom-plate bars joined across the shared wall (``JOINED``); another stage's piece, its bars
    apart (``APART``); the array's edge, the shield's frame closed through the channel (``EDGE``)."""

    JOINED = auto()
    APART = auto()
    EDGE = auto()


class ArrayKind(Enum):
    """How array units meet (``MomUnit``): side by side in a row, a channel across each unit's ends
    joining a stage's plates (``CHANNELS``, the difference strips); or in a grid, each column's
    inner plates joined down it and a stage's columns along the bottom (``COLUMNS``, unit
    capacitors)."""

    CHANNELS = auto()
    COLUMNS = auto()


# the terminals each style labels (and its SHIELD), in the order its plates are listed
TERMINALS = {
    MomStyle.DIFFERENCE: ("TOP", "MAIN", "DIFF"),
    MomStyle.RING: ("TOP", "INNER"),
    MomStyle.STRIP: ("A", "B"),
}

# a drawn unit's pins in order, its terminals and its shield: its view's ports, its netlist element's

PINS = {
    MomStyle.DIFFERENCE: ("MAIN", "DIFF", "TOP", "SHIELD"),
    MomStyle.RING: ("INNER", "TOP", "SHIELD"),
    MomStyle.STRIP: ("A", "B", "SHIELD"),
}
# each style's first-class device of the PDK's ALIGN package (flow/layout/primitives/models.py): a
# netlist calls it like a transistor, its generator's parameters on the call; MomUnit draws it
DEVICES = {MomStyle.DIFFERENCE: "fmomdiff", MomStyle.RING: "fmomcap", MomStyle.STRIP: "fmomstrip"}


@dataclass(frozen=True)
class MomcapGeometry:
    """A unit on ``layers`` of the PDK's MOM metals: a difference strip's main and difference
    fingers (``DIFFERENCE``), a ring unit's inner finger (``RING``, ``diff_length_nm`` 0), or the
    strips (``STRIP``), in nm."""

    style: MomStyle
    layers: int
    length_nm: int
    diff_length_nm: int = 0
    left: Neighbour = Neighbour.EDGE
    right: Neighbour = Neighbour.EDGE
    above: Neighbour = Neighbour.EDGE
    below: Neighbour = Neighbour.EDGE
    frame_nm: int = 0  # a column array's ring length inside (every row one height); 0: the finger's
    array: ArrayKind = ArrayKind.CHANNELS
    # a column unit's pins along its strip only this high from its bottom (the drivers' rows under
    # the array); 0: along the whole strip
    pin_band_nm: int = 0

    @property
    def sides(self) -> str:
        """Its neighbours as a name's suffix: ``je`` joined on the left, the edge on the right (a
        column unit: then above, below)."""
        out = f"{self.left.name[0]}{self.right.name[0]}"
        if self.array is ArrayKind.COLUMNS:
            out += f"{self.above.name[0]}{self.below.name[0]}"
        return out.lower()

    @property
    def align_generator(self) -> str:
        """The ALIGN generator that draws it (``flow/layout/primitives/mom.py``)."""
        return "MomUnit"

    @property
    def device(self) -> str:
        """The netlist's device for it (``DEVICES``)."""
        return DEVICES[self.style]

    def align_parameters(self) -> dict[str, str | int]:
        """What ``MomUnit.generate`` reads from its netlist element: placed by ALIGN, a unit abuts
        its neighbours (shared ring walls, ``abut``), its channels' bars joined or apart at each
        side (``left``, ``right``)."""
        return {
            "style": self.style.name.lower(),
            "layers": self.layers,
            "length": self.length_nm,
            "diff_length": self.diff_length_nm,
            "abut": 1,
            "left": self.left.name.lower(),
            "right": self.right.name.lower(),
            "above": self.above.name.lower(),
            "below": self.below.name.lower(),
            "frame": self.frame_nm,
            "array": self.array.name.lower(),
            "pin_band": self.pin_band_nm,
        }
