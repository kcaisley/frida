#!/usr/bin/env python3
"""
Minimal gdsfactory + Graphviz netlist checker for VLSIR YAML.

- Loads VLSIR-style YAML netlists (single-module or recursive format)
- Validates endpoint syntax and references
- Imports with gdsfactory's schematic Netlist model
- Renders a Graphviz netlist image (`png`, `svg`, or `pdf`)
"""

from __future__ import annotations

import argparse
import html
import re
from collections import defaultdict
from collections import deque
from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = {"instances", "placements", "ports", "nets"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot YAML netlist using gdsfactory.")
    parser.add_argument("yaml_file", type=Path, help="Path to YAML netlist file")
    parser.add_argument(
        "--module",
        default=None,
        help="Module name for recursive netlists (default: first module)",
    )
    parser.add_argument(
        "--no-ports",
        action="store_false",
        dest="show_ports",
        help="Hide per-instance port labels and show only instance-level graph.",
    )
    parser.add_argument(
        "--fmt",
        choices=("png", "svg", "pdf"),
        default="png",
        help="Output format (default: png).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path. Extension is set from --fmt.",
    )
    parser.add_argument(
        "--engine",
        choices=("dot", "neato", "fdp", "sfdp"),
        default="dot",
        help="Graphviz layout engine (default: dot).",
    )
    parser.add_argument(
        "--rankdir",
        choices=("LR", "TB"),
        default="LR",
        help="Main layout direction for dot engine (default: LR).",
    )
    parser.add_argument(
        "--io-hints",
        action="store_true",
        help=(
            "Apply top-level IO placement hints (vdd top, vss bottom, in left, out right). "
            "Enabled by default."
        ),
    )
    parser.add_argument(
        "--no-power-stubs",
        action="store_false",
        dest="power_stubs",
        help=(
            "Draw full routing for power-connected nets instead of local stubs."
        ),
    )
    parser.set_defaults(show_ports=True)
    parser.set_defaults(power_stubs=True)
    parser.set_defaults(io_hints=True)
    return parser.parse_args()


def load_netlist(path: Path, module: str | None) -> tuple[dict[str, Any], str]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")

    if REQUIRED_KEYS.issubset(data.keys()):
        return data, module or "top"

    modules = [
        name
        for name, entry in data.items()
        if isinstance(entry, dict) and REQUIRED_KEYS.issubset(entry.keys())
    ]
    if not modules:
        raise ValueError(f"No module entries found in {path}")

    selected = module or modules[0]
    if selected not in data:
        raise ValueError(
            f"Module '{selected}' not found. Available modules: {', '.join(modules)}"
        )
    return data[selected], selected


def split_endpoint(endpoint: str) -> tuple[str, str]:
    if "," not in endpoint:
        raise ValueError(f"Expected endpoint 'instance,port', got: {endpoint!r}")
    inst, port = endpoint.split(",", 1)
    inst = inst.strip()
    port = port.strip()
    if not inst or not port:
        raise ValueError(f"Invalid endpoint {endpoint!r}")
    return inst, port


def collect_ports_by_instance(netlist: dict[str, Any]) -> dict[str, set[str]]:
    ports_by_instance: dict[str, set[str]] = defaultdict(set)

    for net in netlist.get("nets", []):
        if not isinstance(net, dict):
            continue
        for key in ("p1", "p2"):
            ep = net.get(key)
            if isinstance(ep, str):
                inst, port = split_endpoint(ep)
                ports_by_instance[inst].add(port)

    ports = netlist.get("ports", {})
    if isinstance(ports, dict):
        for ep in ports.values():
            if isinstance(ep, str):
                inst, port = split_endpoint(ep)
                ports_by_instance[inst].add(port)

    return ports_by_instance


def validate_netlist_shape(netlist: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    instances = netlist.get("instances")
    if not isinstance(instances, dict) or not instances:
        return ["Missing or empty 'instances' dictionary."]

    nets = netlist.get("nets")
    if not isinstance(nets, list):
        errors.append("Missing or invalid 'nets' list.")
        return errors

    ports = netlist.get("ports")
    if ports is not None and not isinstance(ports, dict):
        errors.append("Invalid 'ports' section: expected mapping.")
        return errors

    exported_endpoints: set[str] = set()
    if isinstance(ports, dict):
        for pname, ep in ports.items():
            if not isinstance(ep, str):
                errors.append(f"ports[{pname!r}] must be a string endpoint.")
                continue
            try:
                inst, port = split_endpoint(ep)
            except ValueError as e:
                errors.append(f"ports[{pname!r}] {e}")
                continue
            if inst not in instances:
                errors.append(
                    f"ports[{pname!r}] references unknown instance {inst!r}."
                )
            exported_endpoints.add(f"{inst},{port}")

    referenced_endpoints: set[str] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    for idx, net in enumerate(nets):
        if not isinstance(net, dict):
            errors.append(f"nets[{idx}] must be a mapping.")
            continue
        p1 = net.get("p1")
        p2 = net.get("p2")
        if not isinstance(p1, str) or not isinstance(p2, str):
            errors.append(f"nets[{idx}] must contain string 'p1' and 'p2'.")
            continue
        try:
            i1, po1 = split_endpoint(p1)
            i2, po2 = split_endpoint(p2)
        except ValueError as e:
            errors.append(f"nets[{idx}] {e}")
            continue
        if i1 not in instances:
            errors.append(f"nets[{idx}] p1 references unknown instance {i1!r}.")
        if i2 not in instances:
            errors.append(f"nets[{idx}] p2 references unknown instance {i2!r}.")

        ep1 = f"{i1},{po1}"
        ep2 = f"{i2},{po2}"
        referenced_endpoints.add(ep1)
        referenced_endpoints.add(ep2)
        if ep1 == ep2:
            errors.append(f"nets[{idx}] self-connection {ep1!r} is invalid.")
            continue
        adjacency[ep1].add(ep2)
        adjacency[ep2].add(ep1)

    # Flag isolated internal endpoints (no net edge and not exported top-level).
    for ep in sorted(referenced_endpoints):
        if not adjacency.get(ep) and ep not in exported_endpoints:
            errors.append(f"Endpoint {ep!r} is isolated.")

    return errors


def ensure_placements(netlist: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = netlist.get("placements", {})
    if isinstance(raw, dict):
        return raw
    return {}


def stub_factory(component_name: str, port_names: list[str]):
    def _factory(**kwargs):
        import gdsfactory as gf

        c = gf.Component()
        for i, pname in enumerate(port_names):
            c.add_port(
                name=pname,
                center=(0.0, float(-i * 10)),
                width=0.5,
                orientation=0.0,
                layer=(1, 0),
                port_type="electrical",
            )
        return c

    import gdsfactory as gf

    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", component_name)
    _factory.__name__ = f"stub_{sanitized}"
    return gf.cell(_factory, basename=f"stub_{sanitized}")


def register_stub_components(netlist: dict[str, Any]) -> None:
    import gdsfactory as gf

    ports_by_instance = collect_ports_by_instance(netlist)
    ports_by_component: dict[str, set[str]] = defaultdict(set)

    for inst_name, inst_data in netlist.get("instances", {}).items():
        if not isinstance(inst_data, dict):
            continue
        component_name = inst_data.get("component")
        if not isinstance(component_name, str):
            continue
        ports_by_component[component_name].update(ports_by_instance.get(inst_name, set()))

    pdk = gf.get_active_pdk()
    for component_name, port_names in ports_by_component.items():
        if component_name in pdk.cells:
            continue
        factory = stub_factory(component_name, sorted(port_names))
        pdk.cells[component_name] = factory
        pdk.cells[factory.__name__] = factory


def build_gf_netlist(
    netlist: dict[str, Any],
    module_name: str,
) -> dict[str, Any]:
    return {
        "name": module_name,
        "instances": netlist.get("instances", {}),
        "placements": ensure_placements(netlist),
        "ports": netlist.get("ports", {}),
        "nets": netlist.get("nets", []),
    }


def _sanitize_port_id(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _collect_ports_from_parsed(parsed: Any) -> dict[str, set[str]]:
    ports_by_instance: dict[str, set[str]] = defaultdict(set)
    for net in parsed.nets:
        i1, p1 = split_endpoint(net.p1)
        i2, p2 = split_endpoint(net.p2)
        ports_by_instance[i1].add(p1)
        ports_by_instance[i2].add(p2)
    for ep in parsed.ports.values():
        i, p = split_endpoint(ep)
        ports_by_instance[i].add(p)
    return ports_by_instance


def _html_cell(text: str, port_id: str | None = None, colspan: int = 1) -> str:
    port_attr = f' PORT="{port_id}"' if port_id is not None else ""
    col_attr = f' COLSPAN="{colspan}"' if colspan > 1 else ""
    return f"<TD{port_attr}{col_attr} BGCOLOR=\"white\">{html.escape(text)}</TD>"


def _is_pmos(component_name: str) -> bool:
    return "pmos" in component_name.lower()


def _build_port_node_label(
    inst_name: str,
    component_name: str,
    ports: list[str],
    port_id_map: dict[tuple[str, str], str],
    power_ports: set[str] | None = None,
) -> str:
    """
    Build a node label for one instance.

    Uses directional transistor layout when D/G/S/B ports are present:
    - NMOS: D top, S bottom, G left, B right
    - PMOS: S top, D bottom, G left, B right
    """
    for pname in ports:
        port_id_map[(inst_name, pname)] = _sanitize_port_id(pname)

    power_ports = power_ports or set()

    def port_text(pname: str) -> str:
        return f"{pname} -" if pname in power_ports else pname

    by_lower = {p.lower(): p for p in ports}
    if {"d", "g", "s", "b"}.issubset(by_lower):
        g = by_lower["g"]
        b = by_lower["b"]
        top = by_lower["s"] if _is_pmos(component_name) else by_lower["d"]
        bot = by_lower["d"] if _is_pmos(component_name) else by_lower["s"]

        center = f"{inst_name}<BR/>{component_name}"
        rows = [
            "<TR>"
            + _html_cell(port_text(top), port_id_map[(inst_name, top)], colspan=3)
            + "</TR>",
            "<TR>"
            + _html_cell(port_text(g), port_id_map[(inst_name, g)])
            + f"<TD>{center}</TD>"
            + _html_cell(port_text(b), port_id_map[(inst_name, b)])
            + "</TR>",
            "<TR>"
            + _html_cell(port_text(bot), port_id_map[(inst_name, bot)], colspan=3)
            + "</TR>",
        ]

        extras = [p for p in ports if p.lower() not in {"d", "g", "s", "b"}]
        if extras:
            extra_cells = "".join(
                _html_cell(port_text(p), port_id_map[(inst_name, p)]) for p in extras
            )
            rows.append(f"<TR>{extra_cells}</TR>")

        return (
            "<<TABLE BORDER=\"1\" CELLBORDER=\"1\" CELLSPACING=\"0\" CELLPADDING=\"5\" BGCOLOR=\"white\">"
            + "".join(rows)
            + "</TABLE>>"
        )

    # Fallback for non-transistor instances.
    title = f"{inst_name}<BR/>{component_name}"
    rows = [f"<TR><TD COLSPAN=\"2\">{title}</TD></TR>"]
    for pname in ports:
        rows.append(
            "<TR>"
            + _html_cell(port_text(pname), port_id_map[(inst_name, pname)])
            + "<TD></TD>"
            + "</TR>"
        )
    if not ports:
        rows.append("<TR><TD COLSPAN=\"2\">(no ports)</TD></TR>")
    return (
        "<<TABLE BORDER=\"1\" CELLBORDER=\"1\" CELLSPACING=\"0\" CELLPADDING=\"5\" BGCOLOR=\"white\">"
        + "".join(rows)
        + "</TABLE>>"
    )


def _classify_top_port(name: str) -> str:
    lname = name.lower()
    if "vdd" in lname:
        return "top"
    if "vss" in lname or "gnd" in lname:
        return "bottom"
    if "clk" in lname:
        return "left"
    if "out" in lname:
        return "right"
    if "in" in lname:
        return "left"
    return "other"


def _is_power_name(name: str) -> bool:
    lname = name.lower()
    return (
        "vdd" in lname
        or "vss" in lname
        or "gnd" in lname
        or lname in {"vcc", "vssq", "vdda", "vssa", "vddd", "vssd"}
    )


def _apply_io_layout_constraints(
    dot: Any,
    top_nodes: list[str],
    bottom_nodes: list[str],
    left_nodes: list[str],
    right_nodes: list[str],
    core_nodes: list[str],
) -> None:
    """Guide Graphviz DOT layout for top-level ports."""
    # Top/bottom placement.
    with dot.subgraph() as s:
        s.attr(rank="min")
        for n in top_nodes:
            s.node(n)
    with dot.subgraph() as s:
        s.attr(rank="max")
        for n in bottom_nodes:
            s.node(n)

    # Gentle left/right bias around one core anchor node.
    if core_nodes:
        anchor = core_nodes[0]
        for n in left_nodes:
            dot.edge(n, anchor, style="invis", weight="8")
        for n in right_nodes:
            dot.edge(anchor, n, style="invis", weight="8")


def _pin_io_nodes_neato(
    dot: Any,
    left_nodes: list[str],
    right_nodes: list[str],
    top_nodes: list[str],
    bottom_nodes: list[str],
    other_nodes: list[str],
) -> None:
    """Pin top-level IO nodes to sides for force-directed engines."""

    def _pin(nodes: list[str], x: float, y0: float, dy: float) -> None:
        for idx, n in enumerate(nodes):
            y = y0 - idx * dy
            dot.node(n, pos=f"{x},{y}!", pin="true")

    # Keep side IO clearly separated from internal network cloud.
    _pin(left_nodes, x=-300.0, y0=260.0, dy=105.0)
    _pin(right_nodes, x=300.0, y0=260.0, dy=105.0)
    _pin(top_nodes, x=0.0, y0=420.0, dy=95.0)
    _pin(bottom_nodes, x=0.0, y0=-420.0, dy=95.0)
    _pin(other_nodes, x=-300.0, y0=-90.0, dy=95.0)


def to_instance_graphviz(parsed: Any, engine: str):
    """Simplified instance-level graph for dense netlists."""
    from graphviz import Digraph

    dot = Digraph(comment="Instance Connectivity", engine=engine)
    dot.attr(dpi="160", overlap="false", splines="ortho", nodesep="0.5", ranksep="1.0")
    dot.graph_attr["concentrate"] = "false"
    dot.graph_attr["size"] = "14,8!"
    dot.graph_attr["ratio"] = "fill"

    for name, instance in parsed.instances.items():
        label = f"{name}\\n{instance.component}"
        dot.node(name, label=label, shape="box")

    edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    for net in parsed.nets:
        i1, _ = split_endpoint(net.p1)
        i2, _ = split_endpoint(net.p2)
        if i1 == i2:
            continue
        a, b = sorted((i1, i2))
        edge_counts[(a, b)] += 1

    for (a, b), count in edge_counts.items():
        kwargs = {"dir": "none"}
        if count > 1:
            kwargs["label"] = str(count)
        dot.edge(a, b, **kwargs)

    return dot


def to_port_graphviz(
    parsed: Any,
    engine: str,
    rankdir: str,
    io_hints: bool,
    power_stubs: bool,
):
    """Port-level floating graph (no fixed coordinates)."""
    from graphviz import Digraph

    dot = Digraph(comment="Port Connectivity", engine=engine)
    dot.attr(
        dpi="160",
        overlap="false",
        splines="ortho",
        nodesep="1.2",
        ranksep="1.6",
        rankdir=rankdir,
        outputorder="edgesfirst",
    )
    dot.graph_attr["concentrate"] = "false"
    dot.graph_attr["size"] = "14,8!"
    dot.graph_attr["ratio"] = "fill"

    ports_by_instance = _collect_ports_from_parsed(parsed)
    port_id_map: dict[tuple[str, str], str] = {}
    core_nodes = list(parsed.instances.keys())

    # Build endpoint connectivity to identify power-connected components.
    endpoint_adj: dict[str, set[str]] = defaultdict(set)
    for net in parsed.nets:
        endpoint_adj[net.p1].add(net.p2)
        endpoint_adj[net.p2].add(net.p1)

    power_seeds: set[str] = set()
    for top_name, endpoint in parsed.ports.items():
        if _is_power_name(top_name):
            power_seeds.add(endpoint)
    for endpoint in list(endpoint_adj.keys()):
        _, pname = split_endpoint(endpoint)
        if _is_power_name(pname):
            power_seeds.add(endpoint)

    power_endpoints: set[str] = set()
    if power_seeds:
        queue: deque[str] = deque(power_seeds)
        power_endpoints = set(power_seeds)
        while queue:
            ep = queue.popleft()
            for nbr in endpoint_adj.get(ep, set()):
                if nbr in power_endpoints:
                    continue
                power_endpoints.add(nbr)
                queue.append(nbr)

    power_ports_by_instance: dict[str, set[str]] = defaultdict(set)
    for endpoint in power_endpoints:
        inst, port = split_endpoint(endpoint)
        power_ports_by_instance[inst].add(port)

    for inst_name, inst in parsed.instances.items():
        ports = sorted(ports_by_instance.get(inst_name, set()))
        label = _build_port_node_label(
            inst_name,
            inst.component,
            ports,
            port_id_map,
            power_ports=power_ports_by_instance.get(inst_name, set()),
        )
        dot.node(inst_name, label=label, shape="plain")

    for net in parsed.nets:
        i1, p1 = split_endpoint(net.p1)
        i2, p2 = split_endpoint(net.p2)
        is_power_edge = net.p1 in power_endpoints and net.p2 in power_endpoints
        if power_stubs and is_power_edge:
            continue
        pid1 = port_id_map.get((i1, p1), _sanitize_port_id(p1))
        pid2 = port_id_map.get((i2, p2), _sanitize_port_id(p2))
        dot.edge(f"{i1}:{pid1}", f"{i2}:{pid2}", dir="none")

    top_nodes: list[str] = []
    bottom_nodes: list[str] = []
    left_nodes: list[str] = []
    right_nodes: list[str] = []
    other_nodes: list[str] = []

    for top_name, endpoint in sorted(parsed.ports.items()):
        if power_stubs and _is_power_name(top_name):
            # Power nets already represented by local stubs on internal instances.
            continue
        inst, port = split_endpoint(endpoint)
        top_node = f"top_{top_name}"
        dot.node(top_node, label=top_name, shape="oval")
        pid = port_id_map.get((inst, port), _sanitize_port_id(port))
        dot.edge(top_node, f"{inst}:{pid}", style="dashed", dir="none")
        category = _classify_top_port(top_name)
        if category == "top":
            top_nodes.append(top_node)
        elif category == "bottom":
            bottom_nodes.append(top_node)
        elif category == "left":
            left_nodes.append(top_node)
        elif category == "right":
            right_nodes.append(top_node)
        else:
            other_nodes.append(top_node)

    if engine == "dot" and io_hints:
        _apply_io_layout_constraints(
            dot,
            top_nodes=top_nodes,
            bottom_nodes=bottom_nodes,
            left_nodes=left_nodes,
            right_nodes=right_nodes + other_nodes,
            core_nodes=core_nodes,
        )
    elif engine in {"neato", "fdp", "sfdp"} and io_hints:
        _pin_io_nodes_neato(
            dot,
            left_nodes=left_nodes,
            right_nodes=right_nodes,
            top_nodes=top_nodes,
            bottom_nodes=bottom_nodes,
            other_nodes=other_nodes,
        )

    return dot


def main() -> int:
    args = parse_args()

    try:
        from gdsfactory.gpdk import PDK
        from gdsfactory.schematic import Netlist
    except ModuleNotFoundError as e:
        print("Missing dependency:", e)
        print("Install with: uv sync")
        return 1

    if not args.yaml_file.exists():
        print(f"YAML file not found: {args.yaml_file}")
        return 1

    PDK.activate()

    try:
        netlist, selected_module = load_netlist(args.yaml_file, args.module)
    except Exception as e:
        print(f"Failed to load netlist: {e}")
        return 1

    shape_errors = validate_netlist_shape(netlist)
    if shape_errors:
        print("Netlist validation failed:")
        for err in shape_errors:
            print(f"  - {err}")
        return 2

    register_stub_components(netlist)
    gf_yaml = build_gf_netlist(netlist, selected_module)

    # Parse with gdsfactory model validation.
    try:
        parsed = Netlist.model_validate(gf_yaml)
    except Exception as e:
        print(f"gdsfactory import failed: {e}")
        return 3

    print(
        f"Loaded module '{selected_module}' with "
        f"{len(parsed.instances)} instances and {len(parsed.nets)} nets"
    )

    dot = (
        to_port_graphviz(
            parsed,
            engine=args.engine,
            rankdir=args.rankdir,
            io_hints=args.io_hints,
            power_stubs=args.power_stubs,
        )
        if args.show_ports
        else to_instance_graphviz(parsed, engine=args.engine)
    )

    out_path = args.output
    if out_path is None:
        stem = args.yaml_file.stem
        module_tag = re.sub(r"[^a-zA-Z0-9_]+", "_", selected_module)
        out_path = args.yaml_file.with_name(
            f"{stem}.{module_tag}.graphviz.{args.fmt}"
        )
    else:
        out_path = out_path.with_suffix(f".{args.fmt}")

    dot.render(str(out_path.with_suffix("")), format=args.fmt, cleanup=True)
    print(f"Wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
