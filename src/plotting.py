"""Utilities for loading and plotting analysis results."""

from pathlib import Path
import importlib.util
import sys
import matplotlib.pyplot as plt


def load_analysis(pkl_file):
    """
    Load analysis file and return dict of all variables.

    Usage:
        data = load_analysis('results_analysis.pkl')
        locals().update(data)
    """
    import pickle
    with open(pkl_file, 'rb') as f:
        return pickle.load(f)


def load_analysis_vars(pkl_file, globals_dict=None, locals_dict=None):
    """
    Load analysis and inject variables into namespace.

    Usage:
        load_analysis_vars('results_analysis.pkl', globals(), locals())
    """
    data = load_analysis(pkl_file)
    if locals_dict is not None:
        locals_dict.update(data)
    if globals_dict is not None:
        globals_dict.update(data)
    return data


def load_analysis_module(analysis_file):
    """Load analysis module from file path."""
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    spec = importlib.util.spec_from_file_location("analysis", analysis_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules["analysis"] = module
    spec.loader.exec_module(module)
    return module


def configure_fonts_for_pdf():
    """Configure LaTeX fonts for PDF output"""
    plt.rcParams.update({
        "text.usetex": True,       # Use LaTeX for text rendering
        "font.family": "serif",   # Use serif (LaTeX default)
        "font.serif": ["Computer Modern Roman"],  # LaTeX default font
        "font.size": 11,          # Base font size
        "axes.titlesize": 12,     # Title font size
        "axes.labelsize": 11,     # Axis label font size
        "xtick.labelsize": 10,    # X-tick label size
        "ytick.labelsize": 10,    # Y-tick label size
        "legend.fontsize": 10,    # Legend font size
    })


def configure_fonts_for_svg():
    """Configure sans-serif fonts for SVG output"""
    plt.rcParams.update({
        "text.usetex": False,      # Disable LaTeX for SVG
        "font.family": "sans-serif",  # Use sans-serif
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],  # Default sans-serif fonts
        "font.size": 11,          # Base font size
        "axes.titlesize": 12,     # Title font size
        "axes.labelsize": 11,     # Axis label font size
        "xtick.labelsize": 10,    # X-tick label size
        "ytick.labelsize": 10,    # Y-tick label size
        "legend.fontsize": 10,    # Legend font size
    })


def save_plot(filename_base):
    """
    Save plot in both PDF and SVG formats with appropriate font settings.
    
    Args:
        filename_base: Base filename without extension (e.g., 'build/figure_name')
    """
    # Save PDF version with LaTeX fonts
    configure_fonts_for_pdf()
    plt.tight_layout()
    plt.savefig(f'{filename_base}.pdf')
    
    # Save SVG version with sans-serif fonts
    configure_fonts_for_svg()
    plt.tight_layout()
    plt.savefig(f'{filename_base}.svg')


# Initialize with PDF configuration as default
configure_fonts_for_pdf()
