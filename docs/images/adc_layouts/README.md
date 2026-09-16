# Historical ADC channel layouts

These transparent, 6000-pixel-long-edge PNGs show one representative ADC channel
from four preserved chip generations. The images are rendered directly from the
read-only archival GDS files; no historical layout is modified.

| Image | Archived cell |
|---|---|
| `dcd2_adc_channel.png` | DCD2 `PixelDCD2` |
| `dhpt02_adc_channel.png` | DHPT 0.2 `SAR_ADC_1ch_v2` |
| `cordia1_adc_channel.png` | CoRDIA-1 `ADC_BSS` |
| `frida1_adc_channel.png` | FRIDA-1 `adc` |

Regenerate all four from the FRIDA repository root:

```console
klayout -b -r docs/images/adc_layouts/render.py
```

This document uses a catalogue palette and transparent, per-layer compositing
of a selected archived cell. The shared `flow/layout/image.py` renderer uses the
PDK `.lyp` presentation for layout-review collateral and renders an opaque view.
Keep this document-specific compositing here so regenerating these illustrations
does not change the established layout-review images. Subprocess calls remain
visible in the render procedure; the geometry helpers are pure calculations.
