#!/usr/bin/env python3
"""Quick inspection tool for raw files."""

import logging
import sys
from spicelib import RawRead

from flow.common import setup_logging


def check_raw_file(raw_file):
    """Display contents and stats for a raw file."""
    logger = logging.getLogger(__name__)

    logger.info(f"\n{'=' * 70}")
    logger.info(f"Raw file: {raw_file}")
    logger.info(f"{'=' * 70}")

    # Use ngspice dialect - ltspice dialect corrupts the data even though detector identifies as ltspice
    try:
        raw = RawRead(
            str(raw_file), traces_to_read="*", dialect="ngspice", verbose=False
        )

        # Get time axis
        time = raw.get_axis()
        traces = raw.get_trace_names()

        logger.info(f"\nVariables: {len(traces)}, Time points: {len(time)}\n")

        # Collect all data
        data_dict = {"time": time}
        for name in traces:
            if name.lower() != "time":
                data_dict[name] = raw.get_wave(name)

        # Print header
        logger.info(
            f"{'time':<11s} "
            + " ".join(f"{name:>11s}" for name in traces if name.lower() != "time")
        )

        # Print first 10 points
        for i in range(min(10, len(time))):
            row = f"{time[i]:<11.2e} "
            row += " ".join(
                f"{data_dict[name][i]:>11.2e}"
                for name in traces
                if name.lower() != "time"
            )
            logger.info(row)

        # Print separator
        if len(time) > 20:
            separator = f"{'...':^11s} " + " ".join(
                f"{'...':^11s}" for _ in range(len(traces) - 1)
            )
            logger.info(separator)

        # Print last 10 points
        start_idx = max(10, len(time) - 10)
        for i in range(start_idx, len(time)):
            row = f"{time[i]:<11.2e} "
            row += " ".join(
                f"{data_dict[name][i]:>11.2e}"
                for name in traces
                if name.lower() != "time"
            )
            logger.info(row)

        logger.info(f"\n{'=' * 70}\n")
        return True

    except Exception as e:
        logger.error(f"ERROR reading file: {e}\n")
        logger.info(f"{'=' * 70}\n")
        return False


if __name__ == "__main__":
    # Setup logging
    setup_logging()

    if len(sys.argv) < 2:
        logger = logging.getLogger(__name__)
        logger.info("Usage: check_raw.py <raw_file>")
        sys.exit(1)

    raw_file = sys.argv[1]
    success = check_raw_file(raw_file)
    sys.exit(0 if success else 1)
