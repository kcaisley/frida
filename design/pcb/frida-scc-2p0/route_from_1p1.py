"""Give frida-scc-2p0's board the routing frida-scc-1p1 has for the parts both boards have.

Run with KiCad's Python after the two placement scripts, on a board without tracks:

    $KICAD_APPDIR/bin/python3.11 route_from_1p1.py

- Each net of frida-scc-1p1 is matched to the net that is on the same pads here (the parts
  ``place_from_1p1.py`` put where they were); a net with no such pad has no counterpart, and its
  tracks are left behind.
- Every track and via of a matched net is copied, on its new net.
- A copy that would touch a pad or hole of another net is dropped (a new part stands there, or the
  pad changed its net), and then every track left with a loose end is removed back to the last
  junction: what led to a part that is gone.
- A via joins each COMP_OUT leg to its tap resistor on the back.
- The inner layers get frida-scc-1p1's ground plane; the outer layers' ground pour is added after
  the autorouter has run (``route_from_1p1.py pours``), so that it fills around the new tracks.

The copies are locked, which the autorouter respects.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path
from typing import Any

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_from_1p1 import NEW, OLD, net_map
from place_new import ON_LINE

CLEARANCE = pcbnew.FromMM(0.09)  # frida-scc-1p1 was routed to 0.1 mm
GROUND = "GND"


def ground_zone(old: Any, new: Any, layers: list[int], clearance_mm: float) -> None:
    """A ground zone over frida-scc-1p1's four-layer pour's outline, on the layers named."""

    source = next(zone for zone in old.Zones() if zone.GetLayerSet().Contains(pcbnew.In1_Cu))
    zone = pcbnew.Cast_to_ZONE(source.Duplicate(False))
    new.Add(zone)
    layer_set = pcbnew.LSET()
    for layer in layers:
        layer_set.AddLayer(layer)
    zone.SetLayerSet(layer_set)
    zone.SetNet(new.FindNet(GROUND))
    zone.SetLocalClearance(pcbnew.FromMM(clearance_mm))
    zone.SetAssignedPriority(0)


def pours() -> None:
    """The outer layers' ground pour, filled around whatever is routed."""

    old, new = pcbnew.LoadBoard(str(OLD)), pcbnew.LoadBoard(str(NEW))
    if any(zone.GetLayerSet().Contains(pcbnew.F_Cu) for zone in new.Zones()):
        print("the outer layers already have their pour")
    else:
        ground_zone(old, new, [pcbnew.F_Cu, pcbnew.B_Cu], 0.2)
    pcbnew.ZONE_FILLER(new).Fill(new.Zones())
    pcbnew.SaveBoard(str(NEW), new)
    print("outer ground pour filled")


def main() -> None:
    old, new = pcbnew.LoadBoard(str(OLD)), pcbnew.LoadBoard(str(NEW))
    if list(new.GetTracks()):
        raise SystemExit("the board already has tracks; this runs on a freshly placed board")
    mapping = net_map(old, new)

    # copy
    copies, left = [], collections.Counter()
    for track in old.GetTracks():
        name = mapping.get(track.GetNetname())
        if name is None:
            left[track.GetNetname() or "(no net)"] += 1
            continue
        copy = track.Duplicate()
        new.Add(copy)
        copy.SetNet(new.FindNet(name))
        copy.SetLocked(True)
        copies.append(copy)

    # a via where each COMP_OUT tap meets its leg (the tap resistors are on the back, under the points
    # where frida-scc-1p1's probe header was soldered through)
    like = next(track for track in old.GetTracks() if track.Type() == pcbnew.PCB_VIA_T)
    for reference, number in ON_LINE.values():
        pad = old.FindFootprintByReference(reference).FindPadByNumber(number)
        via = like.Duplicate()
        new.Add(via)
        via.SetPosition(pad.GetPosition())
        via.SetNet(new.FindNet(mapping[pad.GetNetname()]))
        via.SetLocked(True)
        copies.append(via)

    # drop what would touch another net's pad or a bare hole
    pads = [pad for fp in new.GetFootprints() for pad in fp.Pads()]
    boxes = [(pad, pad.GetBoundingBox()) for pad in pads]
    dropped = collections.Counter()
    blockers: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    kept = []
    for copy in copies:
        box = copy.GetBoundingBox()
        box.Inflate(CLEARANCE)
        layers = [pcbnew.F_Cu, pcbnew.B_Cu] if copy.Type() == pcbnew.PCB_VIA_T else [copy.GetLayer()]
        clash = False
        for pad, pad_box in boxes:
            if pad.GetNetname() == copy.GetNetname() or not box.Intersects(pad_box):
                continue
            for layer in layers:
                through = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
                if (pad.IsOnLayer(layer) or through) and copy.GetEffectiveShape(layer).Collide(
                    pad.GetEffectiveShape(layer if pad.IsOnLayer(layer) else pcbnew.F_Cu), CLEARANCE
                ):
                    clash = True
            if clash:
                blockers[copy.GetNetname()][pad.GetParentFootprint().GetFieldText("Path").rsplit(".", 1)[0]] += 1
                break
        if clash:
            dropped[copy.GetNetname()] += 1
            new.Remove(copy)
        else:
            kept.append(copy)

    # remove loose ends, back to the last junction
    pruned = 0
    for _ in range(200):
        new.BuildConnectivity()
        connectivity = new.GetConnectivity()
        loose = [t for t in kept if t.Type() != pcbnew.PCB_VIA_T and connectivity.TestTrackEndpointDangling(t, False)]
        ends = collections.Counter()
        for track in kept:
            if track.Type() != pcbnew.PCB_VIA_T and track not in loose:
                for point in (track.GetStart(), track.GetEnd()):
                    ends[(point.x, point.y)] += 1
        # a via no track ends on any more, other than ground's (those stitch the planes)
        loose += [
            t
            for t in kept
            if t.Type() == pcbnew.PCB_VIA_T
            and t.GetNetname() != GROUND
            and ends[(t.GetPosition().x, t.GetPosition().y)] < 2
        ]
        if not loose:
            break
        for track in loose:
            new.Remove(track)
            kept.remove(track)
        pruned += len(loose)

    ground_zone(old, new, [pcbnew.In1_Cu, pcbnew.In2_Cu], 0.2)
    pcbnew.ZONE_FILLER(new).Fill(new.Zones())
    new.BuildConnectivity()
    pcbnew.SaveBoard(str(NEW), new)

    vias = sum(1 for t in kept if t.Type() == pcbnew.PCB_VIA_T)
    print(f"nets matched: {len(mapping)} of {len({t.GetNetname() for t in old.GetTracks()})} routed on frida-scc-1p1")
    print(f"kept {len(kept) - vias} tracks and {vias} vias of {len(list(old.GetTracks()))}")
    print(f"left behind (no counterpart): {sum(left.values())} on {dict(left)}")
    print(f"dropped (another net's pad in the way): {sum(dropped.values())}")
    for name, count in dropped.most_common():
        print(
            f"    {count:3d} on {name}: under {', '.join(f'{part} ({n})' for part, n in blockers[name].most_common(4))}"
        )
    print(f"removed as loose ends: {pruned}")
    print(f"connections open: {new.GetConnectivity().GetUnconnectedCount(False)}")


if __name__ == "__main__":
    pours() if sys.argv[1:] == ["pours"] else main()
