"""Shared parameters for physical and simulated ADC tests.

One :class:`AdcTbParams` instance describes one static test configuration and
therefore one result CSV. Time-varying analog and digital stimuli remain inside
that configuration. Instrument command pacing, FPGA capture calibration, SPICE
analyses, and simulator execution options belong to their respective runners.
"""

from __future__ import annotations

import math
from typing import Optional, Union

import hdl21 as h
from hdl21.prefix import G, m

from flow.adc import AdcParams
from flow.cdac import CdacParams, RedunStrat


@h.paramclass
class AdcTbParams:
    """Parameters describing one ADC test and one resulting data set."""

    # DUT and environmental conditions
    temperature_c = h.Param(dtype=h.Scalar, desc="Test temperature in degrees Celsius", default=25.0)
    dut = h.Param(
        dtype=AdcParams,
        desc="ADC DUT parameters",
        default=AdcParams(
            n_cycles=16,
            cdac=CdacParams(
                n_dac=11,
                n_extra=5,
                redun_strat=RedunStrat.SUBRDX2_OVLY,
            ),
        ),
    )

    # One rate shared by all four serialized control signals.
    symbol_rate = h.Param(dtype=h.Scalar, desc="DDR symbol rate in symbols per second", default=1.6 * G)
    conversions = h.Param(dtype=int, desc="Conversions retained in the result", default=10_000)

    # Optional physical-measurement selection. Simulations leave these unset.
    board_id = h.Param(dtype=Optional[str], desc="Physical board identifier", default=None)
    observed_adc = h.Param(
        dtype=Optional[int],
        desc="ADC routed to the comparator-output mux",
        default=None,
    )
    active_adc_mask = h.Param(
        dtype=Optional[tuple[int, ...]],
        desc="ADC enable mask ordered from ADC 15 through ADC 0",
        default=None,
    )

    # Slow digital configuration. Logical one is resolved to the digital supply
    # by simulation and is programmed as one by physical measurement.
    en_init = h.Param(dtype=int, desc="Enable initialization clock", default=1)
    en_samp_p = h.Param(dtype=int, desc="Enable positive sampling clock", default=1)
    en_samp_n = h.Param(dtype=int, desc="Enable negative sampling clock", default=1)
    en_comp = h.Param(dtype=int, desc="Enable comparator clock", default=1)
    en_update = h.Param(dtype=int, desc="Enable DAC-update clock", default=1)
    dac_mode = h.Param(dtype=int, desc="Select comparator-driven DAC mode", default=1)
    dac_diffcaps = h.Param(dtype=int, desc="Enable differential capacitor controls", default=1)

    # Each DAC state is ordered from bit 15 through bit 0.
    dac_astate_p = h.Param(
        dtype=tuple[int, ...],
        desc="Positive-side DAC A initial state",
        default=(0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1),
    )
    dac_bstate_p = h.Param(
        dtype=tuple[int, ...],
        desc="Positive-side DAC B initial state",
        default=(0,) * 16,
    )
    dac_astate_n = h.Param(
        dtype=tuple[int, ...],
        desc="Negative-side DAC A initial state",
        default=(0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1),
    )
    dac_bstate_n = h.Param(
        dtype=tuple[int, ...],
        desc="Negative-side DAC B initial state",
        default=(0,) * 16,
    )

    # HDL21-native analog source definitions. Physical runners consume the same
    # fields as instrument setpoints or waveform programs.
    vdd_a = h.Param(dtype=h.Vdc.Params, desc="Analog supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_d = h.Param(dtype=h.Vdc.Params, desc="Digital supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_dac = h.Param(dtype=h.Vdc.Params, desc="DAC supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_io = h.Param(dtype=h.Vdc.Params, desc="I/O supply", default=h.Vdc.Params(dc=1200 * m))
    vin_cm = h.Param(
        dtype=h.Vdc.Params,
        desc="Input-driver common mode",
        default=h.Vdc.Params(dc=615 * m),
    )
    vin_p = h.Param(
        dtype=Union[h.Vdc.Params, h.Vsin.Params, h.Vpwl.Params],
        desc="Positive ADC input stimulus",
        default=h.Vdc.Params(dc=615 * m),
    )
    vin_n = h.Param(
        dtype=h.Vdc.Params,
        desc="Negative ADC input",
        default=h.Vdc.Params(dc=615 * m),
    )

    # Unitless digital patterns. All four use the shared symbol_rate above.
    seq_init_pattern = h.Param(
        dtype=str,
        desc="Initialization sequence",
        default="00000000" + "11111111" + "00000000" * 30,
    )
    seq_init_phase_delay_symbols = h.Param(dtype=h.Scalar, desc="INIT phase delay in symbols", default=0.0)
    seq_samp_pattern = h.Param(
        dtype=str,
        desc="Sampling sequence",
        default="00000000" * 2 + "11111111" * 2 + "00000000" * 28,
    )
    seq_samp_phase_delay_symbols = h.Param(dtype=h.Scalar, desc="SAMP phase delay in symbols", default=0.0)
    seq_comp_pattern = h.Param(
        dtype=str,
        desc="Comparator sequence",
        default="00000000" * 4 + "00001111" * 17 + "00000000" * 11,
    )
    seq_comp_phase_delay_symbols = h.Param(dtype=h.Scalar, desc="COMP phase delay in symbols", default=0.0)
    seq_logic_pattern = h.Param(
        dtype=str,
        desc="SAR-logic update sequence",
        default="00000000" + "00001111" + "00000000" * 3 + "11110000" * 16 + "00000000" * 11,
    )
    seq_logic_phase_delay_symbols = h.Param(dtype=h.Scalar, desc="LOGIC phase delay in symbols", default=0.0)


def validate_params(params: AdcTbParams) -> None:
    """Validate relationships that HDL21 field typing cannot express."""

    # Convert shared numeric parameters once and reject values which cannot
    # represent finite physical conditions.
    scalar_values = {}
    for field in (
        "temperature_c",
        "symbol_rate",
        "seq_init_phase_delay_symbols",
        "seq_samp_phase_delay_symbols",
        "seq_comp_phase_delay_symbols",
        "seq_logic_phase_delay_symbols",
    ):
        value = getattr(params, field)
        try:
            scalar_values[field] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be numeric, got {value!r}") from exc
        if not math.isfinite(scalar_values[field]):
            raise ValueError(f"{field} must be finite, got {value!r}")

    # Clock and acquisition lengths must describe a test which can run.
    if scalar_values["symbol_rate"] <= 0:
        raise ValueError("symbol_rate must be positive")
    if params.conversions <= 0:
        raise ValueError("conversions must be positive")

    # Physical selection is optional for simulation, but when present all three
    # fields must identify an enabled ADC on one board.
    measurement_fields = (params.board_id, params.observed_adc, params.active_adc_mask)
    if any(value is not None for value in measurement_fields):
        if not all(value is not None for value in measurement_fields):
            raise ValueError("board_id, observed_adc, and active_adc_mask must be set together")
        assert params.board_id is not None
        assert params.observed_adc is not None
        assert params.active_adc_mask is not None
        if not params.board_id.strip():
            raise ValueError("board_id must not be empty")
        if not 0 <= params.observed_adc < 16:
            raise ValueError("observed_adc must be in 0..15")
        if len(params.active_adc_mask) != 16:
            raise ValueError("active_adc_mask must contain exactly 16 bits")
        if any(bit not in (0, 1) for bit in params.active_adc_mask):
            raise ValueError("active_adc_mask values must be zero or one")
        mask_index = 15 - params.observed_adc
        if params.active_adc_mask[mask_index] != 1:
            raise ValueError("active_adc_mask must include observed_adc")

    # Slow configuration fields are physical logic bits rather than arbitrary
    # integers.
    for field in (
        "en_init",
        "en_samp_p",
        "en_samp_n",
        "en_comp",
        "en_update",
        "dac_mode",
        "dac_diffcaps",
    ):
        if getattr(params, field) not in (0, 1):
            raise ValueError(f"{field} must be zero or one")

    # The four initial CDAC states are fixed-width buses ordered bit 15 to bit 0.
    for field in (
        "dac_astate_p",
        "dac_bstate_p",
        "dac_astate_n",
        "dac_bstate_n",
    ):
        value = getattr(params, field)
        if len(value) != 16:
            raise ValueError(f"{field} must contain exactly 16 bits")
        if any(bit not in (0, 1) for bit in value):
            raise ValueError(f"{field} values must be zero or one")

    # All serialized lanes run from one sequencer and therefore require
    # non-empty binary patterns of equal length.
    patterns = {
        "seq_init_pattern": params.seq_init_pattern,
        "seq_samp_pattern": params.seq_samp_pattern,
        "seq_comp_pattern": params.seq_comp_pattern,
        "seq_logic_pattern": params.seq_logic_pattern,
    }
    lengths = set()
    for field, pattern in patterns.items():
        if not pattern:
            raise ValueError(f"{field} must not be empty")
        if set(pattern) - {"0", "1"}:
            raise ValueError(f"{field} must contain only zero and one")
        lengths.add(len(pattern))
    if len(lengths) != 1:
        raise ValueError("all four sequencer patterns must have equal length")


def _build_variants() -> list[AdcTbParams]:
    """Build the initial physical-measurement sweep.

    The sweep matches the current hardware characterization: each of the sixteen
    ADCs is observed independently at nominal rates from 1 to 10 MSPS. The ADC
    conversion occupies 160 serialized symbols, so those rates correspond to
    symbol rates from 160 MBd to 1.6 GBd. Other axes can be added as explicit
    lists and loops as measurement plans are finalized.
    """

    board_id_list = ["frida65a_001"]
    adc_index_list = list(range(16))
    symbol_rate_list = [rate * 160e6 for rate in range(1, 11)]
    vin_p_list = [h.Vdc.Params(dc=615 * m)]

    variants: list[AdcTbParams] = []
    for board_id in board_id_list:
        for adc_index in adc_index_list:
            for symbol_rate in symbol_rate_list:
                for vin_p in vin_p_list:
                    params = AdcTbParams(
                        board_id=board_id,
                        observed_adc=adc_index,
                        active_adc_mask=tuple(int(index == adc_index) for index in reversed(range(16))),
                        symbol_rate=symbol_rate,
                        vin_p=vin_p,
                    )
                    validate_params(params)
                    variants.append(params)
    return variants
