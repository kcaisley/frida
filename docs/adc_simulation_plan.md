# Unified HDL21 ADC simulation flow

## Summary

Replace the hand-written ADC simulation decks with four named HDL21 targets
using the shared `AdcTbParams`. Both the extracted FRIDA65A ADC and the
HDL21-generated ADC will produce compatible typed HDF5 measurements.

The public targets will be:

- `frida65a_noise_vs_rate_cm`
- `hdl21gen_noise_vs_rate_cm`
- `frida65a_noise_large_signal`
- `hdl21gen_noise_large_signal`

They will be invoked with:

```text
uv run python -m flow.adc.testbench <target>
uv run python -m flow.adc.testbench <target> --check
```

With no target, the command will list the available targets and exit. Separate
`_single_point` targets are unnecessary because `--check` provides that
coverage.

## Testbench and simulation targets

Rewrite `flow/adc/testbench.py` around the canonical
`flow.scans.params.AdcTbParams`.

Support two DUT views:

- `frida65a`: the full extracted FRIDA65A PEX.
- `hdl21gen`: generated comparator, sampler, and CDAC using the synthesized
  `adc_digital` SPICE block.

Add separate VDD_A, VDD_D, and VDD_DAC ports to the generated ADC, with the
CDAC powered from VDD_DAC. Generate the analog and digital stimuli from
`AdcTbParams`, including `Vbit` sequencer signals, phase offsets, DC or sine
differential input, common mode, and alternating DAC initialization.

Save the external ADC signals, internal clocks and nodes, comparator nodes,
CDAC nodes, and signed current waveforms for all three supply sources. Use
Spectre transient noise from 1 Hz to 25 GHz with seed 1 for production
campaigns.

Each target creates its own timestamped directory beneath:

```text
build/adc/<target>/<YYYYMMDD_HHMM>/
```

### Noise versus rate and common mode

The `*_noise_vs_rate_cm` targets contain:

- Active ADC rates of 1, 5, and 10 MSPS.
- Common-mode voltages of 200, 600, and 1000 mV.
- A +50 mV DC differential input.
- 100 conversions per configuration.
- Nine independent raw and HDF5 results.

### Large-signal noise

The `*_noise_large_signal` targets contain:

- Active ADC rates of 1, 5, and 10 MSPS.
- A 600 mV common-mode voltage.
- A 1.0 Vpp differential sine input.
- A tone frequency of 9,998.770151 Hz.
- 1,000 conversions per configuration.
- Three independent raw and HDF5 results.

All cases use alternating A-state `0101010101010101` and zero B-state
`0000000000000000` initialization.

## Check mode

The `--check` mode generates every production deck belonging to the selected
target, but runs Spectre on only one representative configuration:

- 10 MSPS and 600 mV common mode.
- The target-appropriate DC or sine stimulus.
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

Compute average rail power using:

```text
Prail = mean(Vrail * Idraw)
```

Decode comparator decisions immediately before the LOGIC/update edge instead
of using a fixed 10 ns delay. Require a complete internal and current signal
mapping for new simulations; legacy raw files without these signals do not
need to remain compatible.

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

Run `--check` once for each DUT view and inspect the generated netlist, Spectre
report, raw data, HDF5 hierarchy, decoded ADC result, and three rail currents.
Do not launch the four full noise campaigns during implementation; they remain
explicitly user-invoked because complete PEX runs may require many hours or
days.
