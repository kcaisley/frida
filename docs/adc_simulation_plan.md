# Unified HDL21 ADC simulation flow

## Summary

Replace the hand-written ADC simulation decks with two named HDL21 targets
using the shared `AdcTbParams`. Both the extracted FRIDA65A ADC and the
HDL21-generated ADC will produce compatible typed HDF5 measurements.

The public targets will be:

- `frida65a_noise_vs_rate`
- `hdl21gen_noise_vs_rate`

They will be invoked with:

```text
uv run python -m flow.adc.sim <target>
uv run python -m flow.adc.sim <target> --check
```

With no target, the command will list the available targets and exit. Separate
`_single_point` targets are unnecessary because `--check` provides that
coverage.

## Implementation status

- [x] Use the shared `AdcTbParams` for both generated and extracted views.
- [x] Match the synthesized digital and extracted ADC pin interfaces.
- [x] Generate the two named fixed-input campaign matrices and native Spectre stimuli.
- [x] Save 31 selected voltages and currents in NUTASCII.
- [x] Convert generated and PEX results to the shared `MeasAdcInt` HDF5 schema.
- [x] Run fixed-input `--check` cases for both ADC views.
- [x] Verify comparator activity, decision decoding, rail power, and HDF5 plots.
- [x] Add software coverage for campaigns, pin order, decoding, and analysis compatibility.
- [x] Remove the superseded hand-written decks and post-processing script.
- [x] Complete the two revised production noise campaigns.

## Testbench and simulation targets

Rewrite `flow/adc/sim.py` around the canonical
`flow.scans.params.AdcTbParams`.

Support two DUT views:

- `frida65a`: the full extracted FRIDA65A PEX.
- `hdl21gen`: generated comparator, sampler, and CDAC using the synthesized
  `adc_digital` SPICE block.

Add separate VDD_A, VDD_D, and VDD_DAC ports to the generated ADC, with the
CDAC powered from VDD_DAC. Generate the analog and digital stimuli from
`AdcTbParams`, including `Vbit` sequencer signals, phase offsets, a fixed DC
differential input and common mode, and alternating DAC initialization.

Save the external ADC signals, internal clocks and nodes, comparator nodes,
CDAC nodes, and signed current waveforms for all three supply sources. Use
Spectre transient noise from the lowest frequency represented by each finite
transient, `1 / tstop`, to 25 GHz with seed 1 for production campaigns. This
is the effective lower limit Spectre otherwise applies automatically. Use
seed 1 for deterministic campaign reproduction.

Each target creates its own timestamped directory beneath:

```text
build/adc/<target>/<YYYYMMDD_HHMM>/
```

### Fixed-input noise versus rate

The `*_noise_vs_rate` targets contain:

- Active ADC rates of 2, 6, and 10 MSPS.
- A fixed 600 mV common-mode voltage. Other common modes are excluded from
  these long-running PEX campaigns.
- A +50 mV DC differential input.
- 20 conversions per configuration. These simulations are sanity checks; the
  physical measurements provide the high-statistics noise characterization.
- Three independent raw and HDF5 results per DUT view.

No ADC Spectre case may request more than 100 conversions. Sine campaigns are
excluded: at practical PEX runtimes they do not provide enough observations
near any one input voltage for a useful fixed-input noise estimate.

All cases use alternating A-state `0101010101010101` and zero B-state
`0000000000000000` initialization.

## Check mode

The `--check` mode generates every production deck belonging to the selected
target, but runs Spectre on only one representative configuration:

- 10 MSPS and 600 mV common mode.
- The +50 mV DC differential stimulus.
- Noise disabled.
- One active conversion.
- A transient capped at 100 ns.
- Spectre X with `+preset=mx`.
- `-ahdllint=warn`, enabling static and dynamic Verilog-A lint whenever the
  generated deck includes Verilog-A.

Use a curated set of Spectre circuit checks:

- Static capacitor inventory.
- Static ERC, including floating gates, dangling nodes, and invalid
  gate-to-supply connections.
- Static high-impedance node and DC-path checks.
- Static worst-case RC-delay reporting.
- Static stacks of more than three devices.
- Static topology and pin-to-ground checks.
- Dynamic capacitance reporting for selected nodes.
- Dynamic setup/hold checks for comparator output relative to `seq_update`.
- Dynamic ADC and supply-port power reporting.

Do not enable `dyn_activity`, which requires XPS, or invasive statistical
floating-node pinging by default. The installed Spectre check is named
`static_rcdelay`; `static_coupling` is not an available circuit-check name.

Store the Spectre log and circuit-check reports alongside the generated deck.
Spectre errors fail the check. Diagnostic findings remain visible in the
reports without introducing a warning allowlist initially.

The existing PEX runtime scales to roughly one minute for a 100 ns transient
before circuit-check overhead. The representative check is therefore expected
to complete within several minutes, but runtime is not enforced as a test
assertion.

## Measurement conversion and analysis compatibility

Keep `flow/spice/io.py` generic. Each named target defines its signal mapping
locally and passes it to the raw-to-HDF5 converter instead of relying on a
module-level PEX signal map.

Convert every new ADC simulation to `MeasAdcInt`. Make `MeasAdcInt` a flat
structural superset of `MeasAdcExt`, containing all external fields plus the
internal and supply-current waveforms. Define:

```python
MeasAdc = MeasAdcExt | MeasAdcInt
```

Existing ADC transfer, noise, dynamic, and nonlinearity analyses will accept
either measurement type. Future analyses which require internal nodes will
accept only `MeasAdcInt`.

Convert Spectre supply-source current to current drawn by the ADC using:

```text
Idraw = -Isource
```

Compute average rail power over the possibly nonuniform transient time grid
using:

```text
Prail = integral(Vrail * Idraw, time) / (time[-1] - time[0])
```

Decode comparator decisions immediately before the LOGIC/update edge instead
of using a fixed 10 ns delay. Require a complete internal and current signal
mapping for new simulations; legacy raw files without these signals do not
need to remain compatible.

Store every complete SPICE waveform record on one uniform 25 ps grid for every
ADC rate; do not discard records during the default raw-to-HDF5 conversion.
Record the native raw timestep and whether the dense waveform grid required
interpolation. A finer HDF5 grid does not recover bandwidth missing from a
coarser Spectre result; campaign files may interpolate a coarser native grid,
and expose that fact in their readback metadata. Dedicated high-fidelity
captures should instead request native simulator points at 25 ps or finer.
Continue computing full-run rail power from the native Spectre time grid before
waveform resampling. The converter retains an explicit optional record limit
for specialized callers, but campaign output does not set it.

Publish each HDF5 result atomically from a same-directory temporary file after
the writer closes successfully, so collectors and analysis readers can never
observe a partially written measurement.

The 25 ps interval is based on 5 ps diagnostic transients, not only the ADC
symbol rate. FFTs over one steady 10 MSPS pattern showed less than 0.75% energy
above its 20 GHz Nyquist limit for inspected generated control, clock, CDAC,
and comparator voltages, and less than 0.1% for extracted control, clock, and
CDAC voltages. Saturated extracted comparator nodes were noise dominated and
placed 2.4--3.4% of their roughly millivolt-level residual energy above 20 GHz;
this accepted loss does not hide control edges. At 50 ps, extracted `comp_out`
retention fell to 90.63%. Supply-current impulses are also broadband, but
full-run power is integrated on the native Spectre grid before HDF5
interpolation.

## Cleanup

After the generated flow is verified:

- Remove the obsolete hand-written ADC decks.
- Remove the PEX shell launchers and PWL generator.
- Remove the duplicate testbench parameter class.
- Remove the obsolete post-processing-only `flow/scans/scan_spice.py`.
- Preserve its useful DAC configuration and raw-to-HDF5 behavior in the new
  targets and generic SPICE I/O code before deleting it.

## Verification

Add software tests for:

- Target names and campaign expansion.
- Stimulus and shared sequencer generation.
- Extracted subcircuit port order.
- Alternating DAC initialization.
- Decision sampling relative to `seq_update`.
- Supply-current polarity and rail-power calculation.
- `MeasAdcInt` HDF5 round trips.
- Shared `MeasAdc` analysis compatibility.

Run `--check` for both stimulus classes and DUT views and inspect the generated
netlist, Spectre report, raw data, HDF5 hierarchy, decoded ADC result, and three
rail currents. Start production campaigns only after these checks pass.
Generated campaigns require hours; complete PEX campaigns can require days, so
their timestamped outputs may remain in progress after the implementation
itself is complete.
