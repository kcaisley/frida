#!/usr/bin/env python3
"""Run analysis on simulation results."""

import sys
from pathlib import Path
from analysis import waveforms


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_results.py <family_cell> [analysis_type]")
        print("Example: analyze_results.py samp_tgate waveforms")
        sys.exit(1)

    family_cell = sys.argv[1]
    analysis_type = sys.argv[2] if len(sys.argv) > 2 else 'waveforms'

    # Find raw files
    raw_dir = Path('results') / family_cell
    if not raw_dir.exists():
        print(f"Error: Directory {raw_dir} not found")
        print(f"Run 'make sim {family_cell}' first")
        sys.exit(1)

    raw_files = sorted(raw_dir.glob('*.raw'))
    if not raw_files:
        print(f"Error: No .raw files found in {raw_dir}")
        sys.exit(1)

    print(f"Found {len(raw_files)} .raw file(s) in {raw_dir}")

    # Run analysis (output in same directory as .raw files)
    if analysis_type == 'waveforms':
        print(f"Running waveform visualization...")
        for raw_file in raw_files:
            waveforms.analyze(raw_file, raw_dir)
        print(f"\n✓ Analysis complete! Results in {raw_dir}/")
    else:
        print(f"Error: Unknown analysis type '{analysis_type}'")
        print(f"Available types: waveforms")
        sys.exit(1)


if __name__ == '__main__':
    main()
