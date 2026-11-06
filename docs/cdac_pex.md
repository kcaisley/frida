# FRIDA-1 capacitor-array extraction record

A record of extraction results for the fabricated FRIDA-1 capacitor arrays and of one held sampling-noise comparison. The legacy capacitor-array block that produced some of these numbers, and FRIDA-2's template-swapped extractions, were retired: the converter's DAC is `flow/capdac`, and FRIDA-2 is generated whole. FRIDA-1's four extracted flavors remain (`flow.adc.layout`'s `frida1_*` targets, with the cap array's LVS source frozen under `build/frida-1/`). The runs under `build/` cited here are history.

## Held sampling-noise comparison (2026-09-06)

The seven runs completed on September 5 were collected beneath `build/sim/adc/comparison/20260905_194921/results/`. Their executed transient statements all contained `isnoisy=yes`, `noisefmin=62500`, `noisefmax=25G`, and `noiseseed=1`. Each held 100 conversions at 50 mV differential input and 700 mV common mode, with 100 ns active conversion timing and 160 ns records. The three FRIDA-2 rows were extractions of the retired template-swapped layouts.

The held-level histogram used a clock-derived averaging window of approximately 20.52–22.02 ns: both sampling switches were off, and the first comparator edge was later. Each conversion contributed one averaged `VDAC_P - VDAC_N` value. The sample SD used `ddof=1`; histogram centering removed each design's own DC offset, which was retained separately in the CSV. Averaging suppresses fast ongoing noise, so this was not total comparator-input or output-code noise.

| Design | PEX total VDAC load per side (fF) | Held differential SD (µV) | First DAC correction (mV) |
|---|---:|---:|---:|
| FRIDA-1 1L R17 | 527.7 | 116.9 | 222.10 |
| FRIDA-1 1L R20 | 527.7 | 127.2 | 222.09 |
| FRIDA-1 disconnected 2L R17 | 499.7 | 109.9 | 234.65 |
| FRIDA-1 disconnected 2L R20 | 499.6 | 102.7 | 234.65 |
| FRIDA-2 1L R17 | 500.3 | 112.5 | 255.35 |
| FRIDA-2 2L R17 | 847.5 | 83.3 | 285.47 |
| FRIDA-2 3L R17 | 1209.8 | 81.5 | 297.02 |

Load is the P/N average of the full-ADC extraction's total node capacitance, including shunt loading, not `main - diff`. Totals used the coupling/total ratios in `coupling_capacitance.report`, consistent with the less precise `netsummary.report`. The roughly 0.8 pF effective switched term of the three-layer design is not a substitute for its roughly 1.21 pF total sampling-node load. Floating nodes and transistor capacitances also prevent treating this total as an exact scalar sampling-noise model.

The correction column is the mean differential change between 22.4 and 27.4 ns, spanning the first DAC update. It supported reduced attenuation in the three-layer design, but was not a measured full-scale transfer range. A wider input range makes each 12-bit LSB larger in volts: unchanged µV noise would then look smaller in LSB. Here held-voltage SD itself also decreased, by about 30% versus FRIDA-1 1L R17 and 26% versus FRIDA-1 2L R17. The roughly 2% difference between the two- and three-layer SD estimates was too small to claim a resolved advantage from these 100-sample runs. Final code spread also includes comparator/conversion noise, quantization and local code-width effects; converting it to input µV needs a separately calibrated transfer gain.

Outputs were written to `build/analysis/adc/20260906_112220/`: `adc_sampling_noise.pdf`, `adc_sampling_noise.csv`, and `adc_sampling_levels.csv`.

## Historical fabricated-array comparison

The following table compared the intended behavioral capacitor values in `caparray.cdl` / `caparray.sp` against the physical-layout extraction of `adc_1layer_radix17`.

Definitions:

- Intended: behavioral CDL model values from `caparray.cdl`.
- Layout P-side: layout-derived PEX values from the `VDAC_P` branch of `adc_1layer_radix17.pex.netlist`.
- Extracted avg: average of the P-side and N-side PEX values.
- Eff: effective switched capacitance, `main - diff`.

The PEX files used were extracted from the fabricated layout on 2026-06-08.

| Stage | Weight | Intended main (fF) | Intended diff (fF) | Intended eff (fF) | Layout P main (fF) | Layout P diff (fF) | Layout P eff (fF) | Extracted avg main (fF) | Extracted avg diff (fF) | Extracted avg eff (fF) | Eff ratio ext/int |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 768 | 619.200 | 4.800 | 614.400 | 100.419 | 1.147 | 99.272 | 100.419 | 1.147 | 99.272 | 0.162 |
| C1 | 512 | 412.800 | 3.200 | 409.600 | 66.946 | 0.769 | 66.177 | 66.946 | 0.769 | 66.177 | 0.162 |
| C2 | 320 | 258.000 | 2.000 | 256.000 | 41.839 | 0.483 | 41.356 | 41.840 | 0.483 | 41.356 | 0.162 |
| C3 | 192 | 154.800 | 1.200 | 153.600 | 25.102 | 0.292 | 24.810 | 25.103 | 0.292 | 24.810 | 0.162 |
| C4 | 96 | 90.400 | 13.600 | 76.800 | 14.660 | 2.269 | 12.390 | 14.654 | 2.269 | 12.385 | 0.161 |
| C5 | 64 | 51.600 | 0.400 | 51.200 | 8.366 | 0.097 | 8.268 | 8.362 | 0.097 | 8.264 | 0.161 |
| C6 | 32 | 38.800 | 13.200 | 25.600 | 6.291 | 2.174 | 4.117 | 6.288 | 2.174 | 4.114 | 0.161 |
| C7 | 24 | 35.600 | 16.400 | 19.200 | 5.775 | 2.726 | 3.049 | 5.772 | 2.725 | 3.047 | 0.159 |
| C8 | 12 | 30.800 | 21.200 | 9.600 | 5.000 | 3.472 | 1.528 | 4.997 | 3.471 | 1.526 | 0.159 |
| C9 | 10 | 30.000 | 22.000 | 8.000 | 4.873 | 3.591 | 1.282 | 4.870 | 3.590 | 1.280 | 0.160 |
| C10 | 5 | 28.000 | 24.000 | 4.000 | 4.549 | 3.916 | 0.632 | 4.546 | 3.914 | 0.632 | 0.158 |
| C11 | 4 | 27.600 | 24.400 | 3.200 | 4.484 | 3.979 | 0.506 | 4.482 | 3.977 | 0.505 | 0.158 |
| C12 | 4 | 27.600 | 24.400 | 3.200 | 4.484 | 3.980 | 0.504 | 4.482 | 3.978 | 0.504 | 0.157 |
| C13 | 2 | 26.800 | 25.200 | 1.600 | 4.354 | 4.106 | 0.248 | 4.352 | 4.105 | 0.247 | 0.154 |
| C14 | 1 | 26.400 | 25.600 | 0.800 | 4.289 | 4.168 | 0.121 | 4.287 | 4.167 | 0.121 | 0.151 |
| C15 | 1 | 26.400 | 25.600 | 0.800 | 4.289 | 4.168 | 0.121 | 4.287 | 4.167 | 0.121 | 0.151 |
| Sum | 2047 | 1884.800 | 247.200 | 1637.600 | 305.720 | 41.340 | 264.380 | 305.686 | 41.324 | 264.361 | 0.161 |

## Notes

- The extracted `main - diff` relative weights matched the intended `CAP_WEIGHTS` well after normalization.
- The absolute effective capacitance scale was about `16.1%` of the intended behavioral CDL value, or about `6.2x` smaller.
- The nominal two-layer flavors have disconnected upper plates: their raw LVS is `INCORRECT` with matching device and port counts, and only `vdac_p` and `vdac_n` have connectivity errors. A conductive-source LVS still allows their extraction. The extracted two-layer capacitance matched the one-layer one rather than adding a parallel layer.

## How the extracted values were read

The extracted values in this table came from the top-level xACT-style PEX netlist of the fabricated layout:

```text
adc_1layer_radix17.pex.netlist
```

Its side files were stale for this run and were not used:

```text
adc_1layer_radix17.pex.netlist.ADC_1LAYER_RADIX17.pxi
adc_1layer_radix17.pex.netlist.pex
```

The top-level netlist contains lumped capacitor lines like:

```spice
C12345 VDAC_P:17 DAC_DRIVE_BOTPLATE_MAIN_P<15>:42 0.123f
```

The topplate formal pin `cap_topplate` is flattened/promoted to the top-level nets:

```text
XXcaparray_p/cap_topplate -> VDAC_P
XXcaparray_n/cap_topplate -> VDAC_N
```

The historical botplate pins are the top-level drive nets:

```text
DAC_DRIVE_BOTPLATE_MAIN_P<physical-pin>
DAC_DRIVE_BOTPLATE_DIFF_P<physical-pin>
DAC_DRIVE_BOTPLATE_MAIN_N<physical-pin>
DAC_DRIVE_BOTPLATE_DIFF_N<physical-pin>
```

FRIDA-1 uses the legacy boundary mapping `stage = 15 - physical-pin`, so pin 15 is C0 and pin 0 is C15. The value of each table entry was the sum of all capacitors between the topplate and corresponding botplate, including colon-suffixed subnodes. For example:

```text
C0 main P = sum Cx where one terminal matches VDAC_P or VDAC_P:<subnode>
                     and the other matches DAC_DRIVE_BOTPLATE_MAIN_P<15>
                     or DAC_DRIVE_BOTPLATE_MAIN_P<15>:<subnode>
```

The same rule was used for `diff`, and for the `N` branch with `VDAC_N`.

Manual search in `coupling_capacitance.report` is useful for spot-checking large entries, for example:

```text
DAC_DRIVE_BOTPLATE_MAIN_P<15>  VDAC_P
```

but it is not sufficient for the complete table, because the report can omit smaller logical pair couplings: the full PEX netlist was parsed and summed.

The legacy array block's PEX reader automated the calculation, FRIDA-1's extraction in its legacy pin order and generated arrays in the direct stage order, both indexed C0 through C15; it was retired with the block.
