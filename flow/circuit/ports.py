"""Flat HDL21 interfaces shared by generators, testbenches and netlist adapters.

Each block defines its ports once as an HDL21 Bundle. Its ``signals`` dictionary
is the registry; we copy declarations into flat modules, without adding hierarchy.
All name overrides are checked against that registry before constructing a circuit.
"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace

import hdl21 as h
from hdl21.elab.helpers.width import Sliceable, width


def module_from_ports(name: str, ports: Mapping[str, h.Signal]) -> h.Module:
    """Copy port declarations, including usage metadata, into a fresh module."""
    module = h.Module(name=name)
    for key, port in ports.items():
        if key != port.name:
            raise ValueError(f"Port key {key!r} differs from its declaration {port.name!r}")
        module.add(replace(port, name=key, props=deepcopy(port.props)))
    return module


def port_connections(ports: Mapping[str, h.Signal], module: h.Module, **overrides: Sliceable) -> dict[str, Sliceable]:
    """Connect matching names; reject unknown overrides and mismatched widths now."""
    if unknown := overrides.keys() - ports.keys():
        raise ValueError(f"Unknown port overrides: {sorted(unknown)}")
    connections = {}
    for name, port in ports.items():
        net = overrides[name] if name in overrides else module.namespace[name]
        if width(net) != port.width:
            raise ValueError(f"Port {name} expects width {port.width}, got {width(net)}")
        connections[name] = net
    return connections


def testbench_from_ports(
    name: str, ports: Mapping[str, h.Signal], *, renames: Mapping[str, str] | None = None
) -> tuple[h.Module, dict[str, Sliceable]]:
    """Create flat DUT nets and connect all declared grounds to simulator ground."""
    renames = {} if renames is None else renames
    if unknown := renames.keys() - ports.keys():
        raise ValueError(f"Unknown testbench ports: {sorted(unknown)}")
    tb = h.Module(name=name)
    tb.vss = h.Port(usage=h.Usage.GROUND)
    connections = {}
    for key, port in ports.items():
        if key != port.name:
            raise ValueError(f"Port key {key!r} differs from its declaration {port.name!r}")
        if port.usage == h.Usage.GROUND:
            if key in renames:
                raise ValueError(f"Ground {key} is tied to simulator ground; cannot rename it")
            connections[key] = tb.vss
            continue
        net_name = renames.get(key, key)
        if net_name in tb.namespace:
            raise ValueError(f"Duplicate testbench net: {net_name}")
        net = replace(
            port, name=net_name, vis=h.Visibility.INTERNAL, direction=h.PortDir.NONE, props=deepcopy(port.props)
        )
        tb.add(net)
        connections[key] = net
    return tb, connections


def scalar_connections(
    connections: Mapping[str, Sliceable], *, reverse: bool = False, brackets: str = "_"
) -> dict[str, Sliceable]:
    """Expand buses in descending physical-pin order; optionally reverse logical bits.

    HDL21 exports a vector MSB first. ``reverse`` adapts a legacy C15-first
    interface to C0-first nets, without changing stimuli or analysis indexing.
    """
    result = {}
    for name, net in connections.items():
        size = width(net)
        if size == 1:
            entries = {name: net}
        else:
            entries = {
                f"{name}{brackets[0]}{bit}{brackets[1:]}": net[size - 1 - bit if reverse else bit]
                for bit in reversed(range(size))
            }
        if result.keys() & entries.keys():
            raise ValueError(f"Scalar port names collide: {name}")
        result.update(entries)
    return result


def waveform_net_names(bundle: h.Bundle) -> set[str]:
    """Canonical scalar observation names, expanding every bus bit in C0 order."""
    return {
        net.name if net.width == 1 else f"{net.name}[{bit}]"
        for net in bundle.signals.values()
        for bit in range(net.width)
    }
