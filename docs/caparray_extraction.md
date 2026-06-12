# Caparray capacitance comparison

This table compares the intended behavioral capacitor values in `caparray.cdl` / `caparray.sp` against the current physical-layout extraction for `adc_1layer_radix17`.

Definitions:

- **Intended**: behavioral CDL model values from `caparray.cdl`.
- **Layout P-side**: current layout-derived PEX values from the `VDAC_P` branch of `adc_1layer_radix17.pex.netlist`.
- **Extracted avg**: average of the P-side and N-side PEX values.
- **Eff**: effective switched capacitance, `main - diff`.

The fresh PEX files used were generated in `/users/kcaisley/asiclab/tech/tsmc65/cds/PEX` on 2026-06-08 around 22:48.

| Bit | Weight | Intended main (fF) | Intended diff (fF) | Intended eff (fF) | Layout P main (fF) | Layout P diff (fF) | Layout P eff (fF) | Extracted avg main (fF) | Extracted avg diff (fF) | Extracted avg eff (fF) | Eff ratio ext/int |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 768 | 619.200 | 4.800 | 614.400 | 100.419 | 1.147 | 99.272 | 100.419 | 1.147 | 99.272 | 0.162 |
| 14 | 512 | 412.800 | 3.200 | 409.600 | 66.946 | 0.769 | 66.177 | 66.946 | 0.769 | 66.177 | 0.162 |
| 13 | 320 | 258.000 | 2.000 | 256.000 | 41.839 | 0.483 | 41.356 | 41.840 | 0.483 | 41.356 | 0.162 |
| 12 | 192 | 154.800 | 1.200 | 153.600 | 25.102 | 0.292 | 24.810 | 25.103 | 0.292 | 24.810 | 0.162 |
| 11 | 96 | 90.400 | 13.600 | 76.800 | 14.660 | 2.269 | 12.390 | 14.654 | 2.269 | 12.385 | 0.161 |
| 10 | 64 | 51.600 | 0.400 | 51.200 | 8.366 | 0.097 | 8.268 | 8.362 | 0.097 | 8.264 | 0.161 |
| 9 | 32 | 38.800 | 13.200 | 25.600 | 6.291 | 2.174 | 4.117 | 6.288 | 2.174 | 4.114 | 0.161 |
| 8 | 24 | 35.600 | 16.400 | 19.200 | 5.775 | 2.726 | 3.049 | 5.772 | 2.725 | 3.047 | 0.159 |
| 7 | 12 | 30.800 | 21.200 | 9.600 | 5.000 | 3.472 | 1.528 | 4.997 | 3.471 | 1.526 | 0.159 |
| 6 | 10 | 30.000 | 22.000 | 8.000 | 4.873 | 3.591 | 1.282 | 4.870 | 3.590 | 1.280 | 0.160 |
| 5 | 5 | 28.000 | 24.000 | 4.000 | 4.549 | 3.916 | 0.632 | 4.546 | 3.914 | 0.632 | 0.158 |
| 4 | 4 | 27.600 | 24.400 | 3.200 | 4.484 | 3.979 | 0.506 | 4.482 | 3.977 | 0.505 | 0.158 |
| 3 | 4 | 27.600 | 24.400 | 3.200 | 4.484 | 3.980 | 0.504 | 4.482 | 3.978 | 0.504 | 0.157 |
| 2 | 2 | 26.800 | 25.200 | 1.600 | 4.354 | 4.106 | 0.248 | 4.352 | 4.105 | 0.247 | 0.154 |
| 1 | 1 | 26.400 | 25.600 | 0.800 | 4.289 | 4.168 | 0.121 | 4.287 | 4.167 | 0.121 | 0.151 |
| 0 | 1 | 26.400 | 25.600 | 0.800 | 4.289 | 4.168 | 0.121 | 4.287 | 4.167 | 0.121 | 0.151 |
| **Sum** | **2047** | **1884.800** | **247.200** | **1637.600** | **305.720** | **41.340** | **264.380** | **305.686** | **41.324** | **264.361** | **0.161** |

## Notes

- The extracted `main - diff` relative weights match the intended `CAP_WEIGHTS` well after normalization.
- The absolute effective capacitance scale is about `16.1%` of the intended behavioral CDL value, or about `6.2x` smaller.
- The current physical result is consistent with the second layer in the 2-layer experiment being disconnected rather than contributing a parallel capacitance.

## How the extracted values were read

The extracted values in this table come from the fresh xACT-style PEX netlist:

```text
/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_1layer_radix17.pex.netlist
```

Do **not** use the stale side files for this run unless their timestamps show they were regenerated:

```text
adc_1layer_radix17.pex.netlist.ADC_1LAYER_RADIX17.pxi
adc_1layer_radix17.pex.netlist.pex
```

For the 2026-06-08 xACT/report run, the updated file was the top-level `adc_1layer_radix17.pex.netlist`, which contains lumped capacitor lines like:

```spice
C12345 VDAC_P:17 DAC_DRIVE_BOTPLATE_MAIN_P<15>:42 0.123f
```

The topplate formal pin `cap_topplate` is flattened/promoted to the top-level nets:

```text
XXcaparray_p/cap_topplate -> VDAC_P
XXcaparray_n/cap_topplate -> VDAC_N
```

The botplate pins are the top-level drive nets:

```text
DAC_DRIVE_BOTPLATE_MAIN_P<bit>
DAC_DRIVE_BOTPLATE_DIFF_P<bit>
DAC_DRIVE_BOTPLATE_MAIN_N<bit>
DAC_DRIVE_BOTPLATE_DIFF_N<bit>
```

The value for each table entry is the sum of **all** capacitors between the topplate net and the corresponding botplate net, including all colon-suffixed subnodes. For example:

```text
main_P[15] = sum Cx where one terminal matches VDAC_P or VDAC_P:<subnode>
                    and the other matches DAC_DRIVE_BOTPLATE_MAIN_P<15>
                    or DAC_DRIVE_BOTPLATE_MAIN_P<15>:<subnode>
```

The same rule is used for `diff`, and for the `N` branch with `VDAC_N`.

Manual search in `coupling_capacitance.report` is useful for spot-checking large entries, for example:

```text
DAC_DRIVE_BOTPLATE_MAIN_P<15>  VDAC_P
```

but it is **not sufficient** for the complete table, because the report can omit smaller logical pair couplings. The full PEX netlist should be parsed and summed.

The parser used was a one-off Python script equivalent to:

```python
import re
from collections import defaultdict

path = "/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_1layer_radix17.pex.netlist"

val_re = re.compile(r"^([+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?)([a-zA-Z]*)$")
bot_re = re.compile(r"^DAC_DRIVE_BOTPLATE_(MAIN|DIFF)_([PN])<([0-9]+)>(?::.*)?$", re.I)

def val_ff(s: str) -> float:
    m = val_re.match(s)
    if not m:
        raise ValueError(s)
    x = float(m.group(1))
    suffix = m.group(2).lower()
    return x * {"": 1e15, "f": 1.0, "p": 1e3, "n": 1e6, "u": 1e9, "m": 1e12}.get(suffix, 1)

def classify(node: str):
    u = node.upper()
    m = bot_re.match(u)
    if m:
        return ("BOT", m.group(1).upper(), m.group(2).upper(), int(m.group(3)))
    if u == "VDAC_P" or u.startswith("VDAC_P:"):
        return ("TOP", "P")
    if u == "VDAC_N" or u.startswith("VDAC_N:"):
        return ("TOP", "N")
    return ("OTHER",)

caps = defaultdict(float)

with open(path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        fields = line.split()
        if len(fields) != 4 or not fields[0].upper().startswith("C"):
            continue

        try:
            c_ff = val_ff(fields[3])
        except ValueError:
            continue

        a = classify(fields[1])
        b = classify(fields[2])

        if a[0] == "TOP" and b[0] == "BOT" and a[1] == b[2]:
            caps[(a[1], b[1], b[3])] += c_ff
        elif b[0] == "TOP" and a[0] == "BOT" and b[1] == a[2]:
            caps[(b[1], a[1], a[3])] += c_ff

for side in ["P", "N"]:
    print(f"side {side}")
    for bit in range(15, -1, -1):
        main = caps[(side, "MAIN", bit)]
        diff = caps[(side, "DIFF", bit)]
        print(bit, main, diff, main - diff)
```
