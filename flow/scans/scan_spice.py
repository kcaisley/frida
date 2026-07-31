"""Convert configured Spectre ADC PEX NUTASCII results into typed HDF5.

Run the Spectre decks first, then convert their existing raw files:

    ./design/spice/adc_pex_monotonic.sh
    ./design/spice/adc_pex_bss.sh
    uv run python -m flow.scans.scan_spice
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import hdl21 as h
from hdl21.prefix import m

from flow.scans.params import AdcTbParams
from flow.spice.io import convert_spectre_adc_raw_to_h5

ADC_PEX_POSTPROCESS_RUNS = (
    {
        "name": "monotonic",
        "raw": Path("build/adc_pex_monotonic/tb_adc_pex_monotonic.raw"),
        "h5": Path("build/adc_pex_monotonic/adc_00.h5"),
        "params": AdcTbParams(
            conversions=121,
            symbol_rate=200e6,
            dac_astate_p=(1,) * 16,
            dac_bstate_p=(1,) * 16,
            dac_astate_n=(1,) * 16,
            dac_bstate_n=(1,) * 16,
            vin_cm=h.Vdc.Params(dc=600 * m),
            vin_diff=h.Vpwl.Params(wave="0 -600m 154.88u 600m"),
        ),
    },
    {
        "name": "bss",
        "raw": Path("build/adc_pex_bss/tb_adc_pex_bss.raw"),
        "h5": Path("build/adc_pex_bss/adc_00.h5"),
        "params": AdcTbParams(
            conversions=121,
            symbol_rate=200e6,
            dac_astate_p=(0,) + (1,) * 15,
            dac_bstate_p=(1,) * 16,
            dac_astate_n=(0,) + (1,) * 15,
            dac_bstate_n=(1,) * 16,
            vin_cm=h.Vdc.Params(dc=600 * m),
            vin_diff=h.Vpwl.Params(wave="0 -600m 154.88u 600m"),
        ),
    },
    {
        "name": "noise",
        "raw": Path("build/adc_pex_noise/tb_adc_pex_noise.raw"),
        "h5": Path("build/adc_pex_noise/adc00_dinit0101010101010101_noise_pex.h5"),
        "params": AdcTbParams(
            conversions=121,
            symbol_rate=200e6,
            dac_astate_p=tuple(int(bit) for bit in "0101010101010101"),
            dac_bstate_p=(1,) * 16,
            dac_astate_n=tuple(int(bit) for bit in "0101010101010101"),
            dac_bstate_n=(1,) * 16,
            vin_cm=h.Vdc.Params(dc=612 * m),
            vin_diff=h.Vdc.Params(dc=0.0),
        ),
    },
)


def process_run(run: Mapping[str, object]) -> None:
    """Convert one configured ADC PEX raw file when it exists."""

    raw_path = run["raw"]
    h5_path = run["h5"]
    params = run["params"]
    if not isinstance(raw_path, Path) or not isinstance(h5_path, Path) or not isinstance(params, AdcTbParams):
        raise TypeError(f"invalid ADC PEX run configuration: {run}")
    if not raw_path.exists():
        print(
            f"warning: skipping {run['name']}; missing raw file {raw_path}",
            file=sys.stderr,
        )
        return

    print(f"processing {run['name']}: {raw_path}")
    convert_spectre_adc_raw_to_h5(
        raw_path,
        h5_path,
        params=params,
    )
    print(f"saved typed ADC measurement to {h5_path}")


def main() -> None:
    for run in ADC_PEX_POSTPROCESS_RUNS:
        process_run(run)


if __name__ == "__main__":
    main()
