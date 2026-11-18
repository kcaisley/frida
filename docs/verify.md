# Verifying a block end to end

A change to a block (its circuit, its benches, its analyses) is verified by running one of its runs through the flow before and after it and comparing every number the records hold. `tools/verify.py` does both with the flow's own steps, so what it checks is what `python -m flow` records.

## The run and its numbers

```bash
source workspace.sh
python tools/verify.py --block comp --run frida1 --pdks tsmc65 --workers 4 --save build/verify/comp_before.json
```

- `--block`, `--run`: one of the block's runs (its `runs.py`), run through the results step: netlist, presim, layout, DRC, LVS, extraction, postsim and the record (`python -m flow --block B --run R --to results`).
- `--pdks`: the kits to run in, comma-separated; the run's own by default.
- `--workers`: at most this many processes at once (else `PORT_WORKERS` where set, else the run's own).
- `--from STEP`: start at a later step in the run's latest folder; a step whose output is complete is kept, so `--from results` collects the records as they are, and with the instances' `results/` folders deleted analyses the kept simulations again.
- `--folder PATH`: collect a run's folder as it is (`build/<block>/<run>/<stamp>`, of any checkout), running nothing: a baseline from a run made before the change.
- `--save FILE`: every instance's numbers as one JSON: its `metrics` and, where the record is post-layout, its `prelayout` metrics, by dotted name (`metrics.delay_0p5mv_s`), a number not measured as `null`.

## Comparing with a baseline

```bash
python tools/verify.py --block comp --run frida1 --pdks tsmc65 --workers 4 --baseline build/verify/comp_before.json
```

`--baseline FILE` lists, after the run, every number that moved beyond `--rtol` (relative to the larger of the two, `1e-6` by default), every number added or removed, and every instance added or removed:

```text
against build/verify/comp_before.json:
tsmc65/frida1 metrics.delay_0p5mv_s: 1.2e-10 -> 1.3e-10 (+8.333%)
tsmc65/frida1 metrics.noise_v: removed (was 0.0002)
1 numbers changed beyond rtol 1e-06 (14 compared)
```

The exit status is 0 where nothing changed, 1 where something did and 2 where an instance failed (its record's error is among its numbers). A change that is meant goes in the commit that makes it, with the numbers before and after; one that is not is a bug.

## Steps

1. Before the change: save a baseline of the block's named runs in the kits it is checked in (`--save`; `--folder` for a run already made).
2. Make the change and its tests (`uv run --no-project --python 3.12 python tools/check.py all`).
3. Run again against the baseline (`--baseline`) and account for every number listed.
4. Check every bench's operating points with `flow.circuit.oppoint` (the bench saves each device's values after its compile, `oppoint.saves(devices, bench, includes)`, which names the device inside a kit's wrapper subckt and makes the run write PSF ASCII): `oppoint.saturation` gives the margin V_DS − V_D,sat of each device meant to be saturated (current sources, cascodes, amplifying devices; not switches) at the nominal supply and its corners and names those out of saturation; `oppoint.stress` names every device with a junction forward-biased past 0.3 V or a terminal pair past the run's largest supply (its nominal times 1.1), at the operating points and over the transient.
5. Check that every run that needs accuracy says so: `flow.circuit.spectre.run` refuses Spectre X for a noise analysis and for a run its bench marks with `spectre.Accuracy` (noise, distortion, an S-curve, a small difference, sub-picosecond timing), which passes `fast=False`; it warns of an unmarked run in Spectre X whose transient has noise or a `maxstep` (which Spectre X ignores), and the block's log shows the warning.
