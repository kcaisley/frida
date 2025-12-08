"""Waveform visualization analysis - generate plots from .raw files."""

from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import raw_reader, plotting


def analyze(raw_file: Path, output_dir: Path):
    """
    Generate waveform plots from .raw file.

    Args:
        raw_file: Path to .raw file
        output_dir: Directory for output (waveforms/ subdirectory)

    Outputs:
        - <output_dir>/<name>_waveforms.pdf - Plot
    """
    print(f"  Processing: {raw_file.name}")

    # 1. Read raw file
    time, traces = raw_reader.read_raw(raw_file)

    # 2. Generate plot
    pdf_file = output_dir / f"{raw_file.stem}_waveforms.pdf"
    plotting.plot_all_traces(pdf_file, time, traces)
    print(f"    → Saved plot: {pdf_file.name}")
