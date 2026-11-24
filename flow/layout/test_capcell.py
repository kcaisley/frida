"""Tests for the MOM units' geometry beside the routing tracks (flow/layout/rows/capcell.py), in
IHP130, whose wide-metal space (Mn.e) the frame of capdac's FRIDA-1 array once missed."""

import pytest

from .pdkproc import ROOT, in_pdk

needs_ihp130 = pytest.mark.skipif(
    not (ROOT / "pdk/ihp130/layout/tech.py").is_file(), reason="needs the ihp130 PDK submodule"
)

PITCH, HALF = 420, 100  # IHP130's M2 tracks (layers.json) and half a route's wire


def frame_sides() -> tuple[int, int, list[int], int]:
    """Run bound to IHP130: an array's M2 frame a track wider than the ring's bar
    (``MomUnit._channels``): the space beside it, the space beside a channel's bar, its top side
    drawn back from the first track beyond it, at 95 nm (FRIDA-1's), 10 nm and 300 nm over a track,
    and its bottom side, on a track (the outline's)."""

    import capcell

    frame = capcell.space_beside(2, capcell.mom_geometry(3)["width"] + PITCH)
    bar = capcell.space_beside(2, capcell.mom_channel(3)["bar"])
    base = 100 * PITCH
    sides = [capcell.clear_of_track(base + over, 1, frame, PITCH, 0, HALF) - base for over in (95, 10, 300)]
    return frame, bar, sides, capcell.clear_of_track(-PITCH, -1, frame, PITCH, 0, HALF)


@needs_ihp130
def test_a_wide_frame_keeps_its_wide_space_from_the_track_beyond_it() -> None:
    frame, bar, (frida1, clear, near), bottom = in_pdk("ihp130", "flow.layout.test_capcell", "frame_sides")
    assert (frame, bar) == (240, 210)  # Mn.e beside the 690 nm frame, Mn.b beside a 290 nm bar
    assert frida1 == PITCH - HALF - frame  # 15 nm back: the next track's route 240 nm away, not 225 nm
    assert clear == 10  # the next track's wire 310 nm away already
    assert near == PITCH - HALF - frame  # 220 nm back: the next track's wire no closer than 240 nm
    assert bottom == -PITCH  # the track below 320 nm away
