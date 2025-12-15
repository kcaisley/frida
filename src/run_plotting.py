"""Utilities for loading and plotting analysis results."""

from pathlib import Path
import importlib.util
import sys


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
