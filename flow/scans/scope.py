"""Reusable oscilloscope acquisition and SCPI synchronization helpers."""

from __future__ import annotations

import time
from typing import Any

from basil.HL.tektronix_oscilloscope import response_value


DEFAULT_CAPTURE_TIMEOUT_S = 2.0


def wait_for_scope_capture(
    scope: Any,
    acquisition_count_before: int,
    timeout_s: float = DEFAULT_CAPTURE_TIMEOUT_S,
) -> None:
    """Wait for a new single-sequence acquisition to complete and stop."""
    deadline = time.monotonic() + timeout_s
    while True:
        acquisition_stopped = response_value(scope.get_acquire_state()) in {"0", "OFF", "STOP"}
        acquisition_count = int(response_value(scope.get_number_waveforms()))
        if acquisition_stopped and acquisition_count > acquisition_count_before:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"scope did not complete a new triggered acquisition within {timeout_s:g} s "
                f"(before={acquisition_count_before}, now={acquisition_count})"
            )
        time.sleep(0.01)


def wait_for_scope_armed(scope: Any, timeout_s: float = DEFAULT_CAPTURE_TIMEOUT_S) -> int:
    """Wait for a fresh acquisition to reset and arm; return its count."""
    deadline = time.monotonic() + timeout_s
    while True:
        trigger_state = response_value(scope._intf.query("TRIGger:STATE?"))
        acquisition_state = response_value(scope.get_acquire_state())
        acquisition_count = int(response_value(scope.get_number_waveforms()))
        if trigger_state in {"ARMED", "READY"} and acquisition_state in {"1", "ON", "RUN"} and acquisition_count == 0:
            return acquisition_count
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"scope did not arm a fresh acquisition within {timeout_s:g} s "
                f"(trigger_state={trigger_state}, acquisition_state={acquisition_state}, "
                f"acquisition_count={acquisition_count})"
            )
        time.sleep(0.01)
