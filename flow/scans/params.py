"""Shared parameters for physical and simulated ADC tests.

One :class:`AdcTbParams` instance describes one static test configuration and
therefore one typed HDF5 measurement. Time-varying analog and digital stimuli
remain inside that configuration. Instrument command pacing, FPGA capture
calibration, SPICE analyses, and simulator execution options belong to their
respective runners.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import hdl21 as h
from hdl21.prefix import G, m
from yaml import safe_load

from flow.adc import AdcParams
from flow.cdac import CdacParams, RedunStrat, get_cdac_weights

MAP_BOARD_PATH = Path(__file__).resolve().parent / "map_board.yaml"


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
    board_id = h.Param(dtype=str | None, desc="Physical board identifier", default=None)
    observed_adc = h.Param(
        dtype=int | None,
        desc="ADC routed to the comparator-output mux",
        default=None,
    )
    active_adc_mask = h.Param(
        dtype=tuple[int, ...] | None,
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
    vin_diff = h.Param(
        dtype=h.Vdc.Params | h.Vsin.Params | h.Vpwl.Params,
        desc="Differential ADC input stimulus, Vin_p - Vin_n",
        default=h.Vdc.Params(dc=0.0),
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
    if params.dut.adc_bits <= 0:
        raise ValueError("dut.adc_bits must be positive")
    if params.dut.n_cycles <= 0:
        raise ValueError("dut.n_cycles must be positive")
    get_cdac_weights(params.dut.cdac)

    # HDL21 source fields are Optional, so require the values needed by both
    # the physical and simulation backends here.
    for field in ("vdd_a", "vdd_d", "vdd_dac", "vdd_io", "vin_cm"):
        source = getattr(params, field)
        if source.dc is None:
            raise ValueError(f"{field}.dc must be set")
        try:
            source_value = float(source.dc)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field}.dc must be numeric, got {source.dc!r}") from exc
        if not math.isfinite(source_value):
            raise ValueError(f"{field}.dc must be finite, got {source.dc!r}")

    if isinstance(params.vin_diff, h.Vdc.Params):
        if params.vin_diff.dc is None:
            raise ValueError("vin_diff.dc must be set")
        vin_diff_values = (params.vin_diff.dc,)
    elif isinstance(params.vin_diff, h.Vsin.Params):
        if params.vin_diff.voff is None or params.vin_diff.vamp is None or params.vin_diff.freq is None:
            raise ValueError("vin_diff sine source requires voff, vamp, and freq")
        vin_diff_values = (params.vin_diff.voff, params.vin_diff.vamp, params.vin_diff.freq)
        if float(params.vin_diff.vamp) < 0:
            raise ValueError("vin_diff sine amplitude must not be negative")
        if float(params.vin_diff.freq) <= 0:
            raise ValueError("vin_diff sine frequency must be positive")
    elif isinstance(params.vin_diff, h.Vpwl.Params):
        if not params.vin_diff.wave.strip():
            raise ValueError("vin_diff PWL wave must not be empty")
        vin_diff_values = ()
    else:
        raise TypeError(f"unsupported vin_diff source type {type(params.vin_diff).__name__}")
    for value in vin_diff_values:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"vin_diff source values must be numeric, got {value!r}") from exc
        if not math.isfinite(numeric_value):
            raise ValueError(f"vin_diff source values must be finite, got {value!r}")

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
    sequence_length = lengths.pop()
    if sequence_length % 8:
        raise ValueError("all four sequencer patterns must contain a whole number of eight-symbol words")


def load_board_map() -> dict[str, Any]:
    """Load the physical-board inventory and calibration map."""

    return safe_load(MAP_BOARD_PATH.read_text())


def convert_sample_rate_to_baud(params: AdcTbParams, sample_rate_hz: float) -> float:
    """Convert an active ADC conversion rate to the required symbol rate.

    The active conversion spans the first through last asserted symbol on any
    of the four timing lanes. Idle padding after that span affects the complete
    pattern-repeat rate, but does not change the requested active conversion
    timing.
    """

    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    patterns = (
        params.seq_init_pattern,
        params.seq_samp_pattern,
        params.seq_comp_pattern,
        params.seq_logic_pattern,
    )
    active_indices = [
        index for index in range(len(params.seq_init_pattern)) if any(pattern[index] == "1" for pattern in patterns)
    ]
    if not active_indices:
        raise ValueError("sequencer patterns contain no active symbols")
    active_span_symbols = active_indices[-1] - active_indices[0] + 1
    return sample_rate_hz * active_span_symbols


def build_variants() -> list[AdcTbParams]:
    """Build the ADC00/ADC01 +2-symbol dynamic conversion-rate campaign."""

    board_id = "00"
    adc_index_list = (0, 1)
    # The current Si570/PLL/OSERDES path has an 80 MBd minimum. With the
    # 160-symbol active conversion this limits true active timing to 0.5 MSPS.
    active_conversion_rate_list_hz = tuple(rate * 0.25e6 for rate in range(2, 41))
    conversions = 1_000_000
    input_frequency_hz = 9_998.770151
    input_peak_v = 0.500
    input_common_mode_v = 0.600
    board_map = load_board_map()
    board = board_map["boards"][board_id]

    variants: list[AdcTbParams] = []
    for adc_index in adc_index_list:
        flavor_name = board["adc_channels"][adc_index]
        cap_weights = tuple(board_map["adc_flavors"][flavor_name]["cdac_weights"])
        dut = AdcParams(
            adc_bits=12,
            n_cycles=16,
            cdac=CdacParams(
                n_dac=11,
                n_extra=5,
                redun_strat=RedunStrat.SUBRDX2_OVLY,
                weights=cap_weights,
            ),
        )
        active_adc_mask = tuple(int(index == adc_index) for index in reversed(range(16)))
        template = AdcTbParams(
            dut=dut,
            board_id=board_id,
            observed_adc=adc_index,
            active_adc_mask=active_adc_mask,
        )
        for active_conversion_rate_hz in active_conversion_rate_list_hz:
            params = AdcTbParams(
                dut=dut,
                board_id=board_id,
                observed_adc=adc_index,
                active_adc_mask=active_adc_mask,
                symbol_rate=convert_sample_rate_to_baud(
                    template,
                    active_conversion_rate_hz,
                ),
                conversions=conversions,
                vin_cm=h.Vdc.Params(dc=input_common_mode_v),
                vin_diff=h.Vsin.Params(
                    voff=0.0,
                    vamp=input_peak_v,
                    freq=input_frequency_hz,
                ),
                seq_logic_phase_delay_symbols=2.0,
            )
            validate_params(params)
            variants.append(params)
    return variants
