"""Frequency calculations and hardware control for the serializer PLL DRP.

The FPGA hardware fixes the PLLE2_ADV input divider and feedback multiplier.
Runtime control changes the Si570 input clock and a paired set of output
dividers using one integer ``N``:

    FIN = 100..200 MHz from the Si570, D = 1, M = 8
    FVCO = FIN * M / D = 800..1600 MHz
    CLKOUT0_DIVIDE = 4 * N  -> sequencer/FastRX clock = 2*FIN/N
    CLKOUT1_DIVIDE = N      -> OSERDES clock          = 8*FIN/N

The OSERDES uses DDR, so its serial line rate is twice its clock frequency.
Only ``N=2..20`` is accepted by the current FPGA DRP controller.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import logging
from time import monotonic, sleep
from typing import Any

logger = logging.getLogger(__name__)

PLL_INPUT_FREQUENCY_HZ = 200_000_000.0
PLL_DIVCLK_DIVIDE = 1
PLL_CLKFBOUT_MULT = 8
PLL_DIVIDERS = tuple(range(2, 21))
SI570_MIN_FREQUENCY_HZ = 100_000_000.0
SI570_MAX_FREQUENCY_HZ = 200_000_000.0
MIN_SYMBOL_RATE_BPS = 80_000_000.0
MAX_SYMBOL_RATE_BPS = 1_600_000_000.0


@dataclass(frozen=True)
class PllFrequency:
    """Calculated clocks for one paired output-divider value ``N``."""

    divider_n: int
    input_frequency_hz: float
    divclk_divide: int
    clkfbout_mult: int
    vco_frequency_hz: float
    clkout0_divide: int
    clkout1_divide: int
    sequencer_frequency_hz: float
    serializer_frequency_hz: float
    ddr_line_rate_bps: float


@dataclass(frozen=True)
class PllDrpStatus:
    """GPIO2 readback after a DRP request."""

    request_n: int
    applied_toggle: int
    busy: bool
    locked: bool
    error: bool
    active_n: int


def calculate_pll_frequency(
    divider_n: int,
    input_frequency_hz: float = PLL_INPUT_FREQUENCY_HZ,
    divclk_divide: int = PLL_DIVCLK_DIVIDE,
    clkfbout_mult: int = PLL_CLKFBOUT_MULT,
) -> tuple[float, float]:
    """Return ``(sequencer_hz, serializer_hz)`` for one divider ``N``.

    The defaults match the fastest FPGA setting: ``FIN=200 MHz``, ``D=1``, and
    ``M=8``. The paired output dividers are ``O0=4*N`` and ``O1=N``.
    """
    if isinstance(divider_n, bool) or not isinstance(divider_n, int) or divider_n <= 0:
        raise ValueError(f"output divider N must be a positive integer, got {divider_n!r}")
    if input_frequency_hz <= 0:
        raise ValueError("input_frequency_hz must be positive")
    if divclk_divide <= 0:
        raise ValueError("divclk_divide must be positive")
    if clkfbout_mult <= 0:
        raise ValueError("clkfbout_mult must be positive")

    vco_frequency_hz = input_frequency_hz * clkfbout_mult / divclk_divide
    clkout0_divide = 4 * divider_n
    clkout1_divide = divider_n
    sequencer_frequency_hz = vco_frequency_hz / clkout0_divide
    serializer_frequency_hz = vco_frequency_hz / clkout1_divide
    return sequencer_frequency_hz, serializer_frequency_hz


def select_pll_configuration(
    target_symbol_rate_bps: float,
    *,
    si570_min_frequency_hz: float = SI570_MIN_FREQUENCY_HZ,
    si570_max_frequency_hz: float = SI570_MAX_FREQUENCY_HZ,
    divclk_divide: int = PLL_DIVCLK_DIVIDE,
    clkfbout_mult: int = PLL_CLKFBOUT_MULT,
    dividers: Iterable[int] = PLL_DIVIDERS,
) -> tuple[float, int]:
    """Return ``(si570_frequency_hz, divider_n)`` for a symbol rate.

    OSERDES is DDR, so ``symbol_rate = 2*FIN*M/(D*N)``. The FPGA fixes
    ``D`` and ``M``; this helper searches the supported output dividers and
    chooses the highest legal Si570 frequency. It performs no hardware I/O.
    """
    if target_symbol_rate_bps <= 0:
        raise ValueError("target_symbol_rate_bps must be positive")
    if si570_min_frequency_hz <= 0 or si570_max_frequency_hz < si570_min_frequency_hz:
        raise ValueError("invalid Si570 frequency range")
    if divclk_divide <= 0 or clkfbout_mult <= 0:
        raise ValueError("PLL D and M must be positive")

    divider_values = tuple(dividers)
    candidates: list[tuple[float, int]] = []
    for divider_n in divider_values:
        if isinstance(divider_n, bool) or not isinstance(divider_n, int) or divider_n <= 0:
            raise ValueError(f"output divider N must be a positive integer, got {divider_n!r}")
        input_frequency_hz = target_symbol_rate_bps * divclk_divide * divider_n / (2.0 * clkfbout_mult)
        if si570_min_frequency_hz <= input_frequency_hz <= si570_max_frequency_hz:
            candidates.append((input_frequency_hz, divider_n))

    if not candidates:
        if not divider_values:
            raise ValueError("dividers must not be empty")
        raise ValueError(
            f"symbol rate {target_symbol_rate_bps:g} Bd is not reachable with "
            f"Si570={si570_min_frequency_hz:g}..{si570_max_frequency_hz:g} Hz and "
            f"N={min(divider_values)}..{max(divider_values)}"
        )
    return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))


def build_pll_frequency_table(
    input_frequency_hz: float,
    divclk_divide: int,
    clkfbout_mult: int,
    dividers: Iterable[int],
) -> dict[int, PllFrequency]:
    """Return a lookup from paired divider ``N`` to the resulting clocks.

    ``input_frequency_hz`` is supplied by the Si570. ``divclk_divide`` (D)
    and ``clkfbout_mult`` (M) describe the fixed hardware configuration. For every requested ``N``, the
    current firmware uses output dividers ``O0=4*N`` and ``O1=N``.

    This function performs calculation only; it does not access hardware or
    enforce device-specific PFD/VCO limits.
    """
    if input_frequency_hz <= 0:
        raise ValueError("input_frequency_hz must be positive")
    if divclk_divide <= 0:
        raise ValueError("divclk_divide must be positive")
    if clkfbout_mult <= 0:
        raise ValueError("clkfbout_mult must be positive")

    vco_frequency_hz = input_frequency_hz * clkfbout_mult / divclk_divide
    table: dict[int, PllFrequency] = {}
    for divider_n in dividers:
        sequencer_frequency_hz, serializer_frequency_hz = calculate_pll_frequency(
            divider_n,
            input_frequency_hz,
            divclk_divide,
            clkfbout_mult,
        )
        table[divider_n] = PllFrequency(
            divider_n=divider_n,
            input_frequency_hz=input_frequency_hz,
            divclk_divide=divclk_divide,
            clkfbout_mult=clkfbout_mult,
            vco_frequency_hz=vco_frequency_hz,
            clkout0_divide=4 * divider_n,
            clkout1_divide=divider_n,
            sequencer_frequency_hz=sequencer_frequency_hz,
            serializer_frequency_hz=serializer_frequency_hz,
            ddr_line_rate_bps=2 * serializer_frequency_hz,
        )
    return table


PLL_FREQUENCY_TABLE = build_pll_frequency_table(
    PLL_INPUT_FREQUENCY_HZ,
    PLL_DIVCLK_DIVIDE,
    PLL_CLKFBOUT_MULT,
    PLL_DIVIDERS,
)


def _read_pll_status(gpio: Any) -> PllDrpStatus:
    gpio.read()
    return PllDrpStatus(
        request_n=gpio["REQUEST_N"].tovalue(),
        applied_toggle=gpio["APPLIED_TOGGLE"].tovalue(),
        busy=bool(gpio["BUSY"].tovalue()),
        locked=bool(gpio["LOCKED"].tovalue()),
        error=bool(gpio["ERROR"].tovalue()),
        active_n=gpio["ACTIVE_N"].tovalue(),
    )


def set_pll_divider(
    gpio: Any,
    divider_n: int,
    *,
    timeout_s: float = 1.0,
    poll_interval_s: float = 0.001,
) -> PllDrpStatus:
    """Write one paired output divider and verify its GPIO2 readback.

    The current bitstream fixes ``D=1`` and ``M=8`` and accepts only
    ``N=2..20``. The Si570 input frequency is programmed separately. This
    function submits the toggle-based command,
    waits for completion and PLL lock, checks ``REQUEST_N`` and ``ACTIVE_N``,
    and returns the hardware status. Frequency calculation is deliberately
    separate from this hardware operation.
    """
    if divider_n not in PLL_DIVIDERS:
        raise ValueError(f"divider N must be in {PLL_DIVIDERS[0]}..{PLL_DIVIDERS[-1]}, got {divider_n!r}")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if poll_interval_s < 0:
        raise ValueError("poll_interval_s must not be negative")

    status = _read_pll_status(gpio)
    apply_toggle = 1 - status.applied_toggle

    logger.info("Applying sequencer PLL output divider N=%d", divider_n)
    gpio["REQUEST_N"] = divider_n
    gpio["APPLY_TOGGLE"] = apply_toggle
    gpio.write()

    deadline = monotonic() + timeout_s
    while True:
        status = _read_pll_status(gpio)
        acknowledged = status.applied_toggle == apply_toggle
        if acknowledged and status.error:
            raise RuntimeError(f"PLL reported an error while applying N={divider_n}")
        if acknowledged and not status.busy:
            if not status.locked or status.active_n != divider_n or status.request_n != divider_n:
                raise RuntimeError(
                    "PLL readback mismatch: "
                    f"requested={status.request_n}, active={status.active_n}, locked={int(status.locked)}"
                )
            logger.info("Sequencer PLL output divider active: N=%d, locked=1", divider_n)
            return status
        if monotonic() >= deadline:
            raise TimeoutError(f"PLL did not apply N={divider_n} within {timeout_s:g} s")
        sleep(poll_interval_s)
