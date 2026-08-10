# Netlist and simulation target refactor

## Status

Planned future work. This document does not change the current generator or
simulation interfaces.

## Goal

Replace the flag-driven ADC, CDAC, comparator, and sampler generator commands
with explicit, zero-argument named targets. Simulation targets should use the
native HDL21 flow: construct one or more `hdl21.sim.Sim` objects and pass them
directly to `hdl21.sim.run()`.

Each target owns its complete configuration, including its PDK, parameters,
simulator, output directory, Monte Carlo settings, and generated artifacts.
Module entry points may select one positional target name, but they do not
expose configuration flags.

The intended interface is:

```text
uv run python -m flow.comp.sim smoke
uv run python -m flow.comp.sim offset_sweep
```

This follows the explicit-target model used by the measurement and analysis
runners. A target represents a reviewed campaign rather than an arbitrary
combination of command-line options.

## Current problem

`flow.circuit.commands.testbench_main()` currently exposes generic `netlist`
and `simulate` subcommands with flags for the PDK, variant mode, format, scope,
Monte Carlo, simulator, and output path.

`flow.circuit.netlist.run_netlist_variants()` also serves two distinct roles:

1. Write persistent netlist artifacts for inspection or another tool.
2. Build `Sim` objects which are returned to the caller and then passed to
   `hdl21.sim.run()`.

The second path writes the simulation deck before HDL21/VLSIRTools generates
the simulator input again during execution. Its `return_sims` Boolean also
changes the function's return type from `float` to
`tuple[float, list[Sim]]`, obscuring the API and producing avoidable type
checking errors.

## Intended structure

Each generator module defines explicit public targets and a registry:

```python
def smoke() -> None:
    """Run the reviewed smoke-test simulation campaign."""

    set_pdk("ihp130")
    variants = build_smoke_variants()
    sims = [sim_input(params) for params in variants]
    h.sim.run(sims, SMOKE_SIM_OPTIONS)


TARGETS: dict[str, Callable[[], None]] = {
    "smoke": smoke,
}
```

The example is illustrative. Target names and campaign parameters should be
chosen from workflows which are currently used and validated.

## Netlist artifacts

Netlist generation remains available only where a persistent artifact has a
real consumer. Each such output becomes an explicit named target, for example:

```text
comp_dut_verilog
comp_ams_stimulus
```

Use the highest-level suitable API:

- Use `hdl21.netlist()` for DUT-level SPICE or structural Verilog output.
- Use the VLSIR simulation-input netlister only when a complete standalone
  simulator deck is required without executing it.
- Retain FRIDA-specific stimulus-wrapper generation only for an active AMS or
  co-simulation consumer.

Do not preserve generic `dut`, `stim`, and `full` scopes solely for backwards
compatibility. Add a named artifact target only after identifying its consumer
and expected output.

## Migration steps

1. Inventory the currently used ADC, CDAC, comparator, and sampler simulation
   campaigns and persistent netlist consumers.
2. Add zero-argument target functions and `TARGETS` registries to the four
   generator modules.
3. Move each campaign's configuration out of command-line flags and into its
   target function or immutable module-level configuration.
4. Make simulation targets construct `Sim` objects and call
   `hdl21.sim.run()` directly.
5. Convert required persistent netlists into explicitly named artifact
   targets using `hdl21.netlist()` or the narrow VLSIR API described above.
6. Remove `return_sims` and the simulation role from
   `run_netlist_variants()`.
7. Delete `testbench_main()` and any generic netlist helpers left without a
   caller.
8. Update `docs/usage.md` and tests to describe and validate the named targets.
9. Keep all four generator directories clean under the existing pre-commit
   `ty` hook as the temporary return-type casts are removed.

## Non-goals

- Changing circuit implementations, testbench stimulus, or numerical models.
- Changing the physical measurement or typed analysis pipelines.
- Removing a netlist artifact which has an identified synthesis, AMS,
  co-simulation, inspection, or archival consumer.
- Creating a second generic workflow framework around HDL21.

## Acceptance criteria

- ADC, CDAC, comparator, and sampler modules expose only reviewed named
  targets, with no configuration flags.
- Simulation targets do not explicitly netlist a `Sim` before calling HDL21.
- No function changes its return type in response to a Boolean argument.
- Every persistent netlist target names its consumer and expected artifact.
- Obsolete command parsing and helper layers are removed rather than wrapped.
- Ruff, `ty`, relevant software tests, and representative netlist/simulation
  smoke tests pass.
